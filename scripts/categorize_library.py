"""Offline image categorisation for the Media Library's default set.

Classifies a folder of images into marketing categories — no cloud API, no
paid service, no training. Labels are scored zero-shot, so the category list
below is data, not a trained model: edit it and re-run.

The vision engine is pluggable (see vision_backends.py) and the best installed
one is chosen automatically:

    clip-torch   transformers + torch. Best accuracy, heaviest install.
    clip-onnx    onnxruntime + tokenizers. Same CLIP weights without torch —
                 the option to reach for when torch has no wheel for your
                 Python version.
    heuristic    Pillow only. Colour-based guesses, always runs.

Only Pillow is required. Everything else is optional, and re-running with a
better backend overwrites the labels without re-importing the files.

Files are never duplicated. An image that is both "Office" and "SaaS" is stored
once and listed under both in metadata.json, which is what the Media Library
reads — folders-per-category would mean the same bytes on disk several times.

Paths in the manifest are relative to the output folder ("full/ab12.webp"),
never absolute. That is what lets the library be served from somewhere other
than /public later: uploading this folder to a bucket and setting
VITE_MEDIA_BASE_URL moves every image without re-running this script.

Usage
-----
    python scripts/categorize_library.py SOURCE [--out DIR] [--limit N]

    SOURCE   folder of images to scan
    --out    where to write processed images + metadata.json
             (default: frontend/public/media-library)
    --limit  stop after N unique images, for a quick trial run
    --full-width / --thumb-width   output sizes in pixels

Why it resizes
--------------
Unsplash originals average ~3 MB. Shipping those would put gigabytes in git and
make the library grid download megabytes per thumbnail. Designs render at
1080-1920px, so a 1600px WebP loses nothing visible and costs ~7% of the bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from vision_backends import BACKENDS, select_backend

# ---------------------------------------------------------------------------
# The label sets. Both are plain data — add a category and re-run.
#
# CLIP compares an image against a *sentence*, not a bare word, and the phrasing
# matters: "a photo of a restaurant interior" scores far more reliably than
# "Restaurant". So each label carries the prompt used to score it.
# ---------------------------------------------------------------------------
CATEGORIES = {
    "SaaS": "a screenshot or photo of software, a dashboard, or a laptop showing an app",
    "Technology": "a photo of technology, computers, circuit boards, or electronic devices",
    "Business": "a photo of business people working, a meeting, or a handshake",
    "Office": "a photo of an office interior, desks, or a modern workspace",
    "Finance": "a photo of finance, money, banking, charts, or investment",
    "Healthcare": "a photo of healthcare, a doctor, a hospital, or medical equipment",
    "Restaurant": "a photo of a restaurant, a cafe interior, or food being served",
    "Food": "a photo of food, a prepared dish, or ingredients",
    "Fitness": "a photo of fitness, a gym, exercise, or sport",
    "Beauty": "a photo of beauty, cosmetics, skincare, or a salon",
    "Fashion": "a photo of fashion, clothing, or a style portrait",
    "Ecommerce": "a photo of shopping, retail products, packaging, or a delivery parcel",
    "Real Estate": "a photo of a house, a building exterior, or property for sale",
    "Interior": "a photo of an interior, furniture, or home decor",
    "Travel": "a photo of travel, a landmark, a beach, or a holiday destination",
    "Education": "a photo of education, students, a classroom, or books",
    "Lifestyle": "a lifestyle photo of everyday life, people relaxing, or a home scene",
    "Nature": "a photo of nature, landscape, plants, or wildlife",
}

# Finer-grained descriptors, scored the same way. These become searchable tags,
# so the library can answer "coffee" or "laptop" without a category for each.
TAGS = {
    "people": "a photo containing people",
    "laptop": "a laptop computer",
    "phone": "a mobile phone or smartphone",
    "coffee": "coffee, a coffee cup, or a barista",
    "desk": "a desk or work surface",
    "meeting": "a group meeting or discussion",
    "outdoor": "an outdoor scene",
    "indoor": "an indoor scene",
    "minimal": "a minimal, clean composition with lots of empty space",
    "colorful": "a bright, colourful, saturated image",
    "dark": "a dark, moody, low-light image",
    "closeup": "a close-up macro shot of an object",
    "workspace": "a workspace or home office",
    "team": "a team of people working together",
    "product": "a product photographed on a plain background",
    "city": "a city, street, or urban skyline",
    "beach": "a beach, sea, or coastline",
    "plant": "plants or greenery",
}

# A category is assigned when CLIP is at least this confident, so an image can
# carry several labels — or, if nothing fits, just the single best one.
CATEGORY_THRESHOLD = 0.10
TAG_THRESHOLD = 0.12
MAX_CATEGORIES = 4
MAX_TAGS = 6

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def die(message: str) -> None:
    print(f"\n  {message}\n", file=sys.stderr)
    raise SystemExit(1)


def load_pillow():
    """Pillow is the one hard requirement — everything else is a backend."""
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        die("Pillow is missing.  Install with:  pip install Pillow")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def renormalise(scores: list[float]) -> list[float]:
    """Rescale a slice of a softmax so it sums to 1 on its own."""
    total = sum(scores)
    if not total:
        return [1 / len(scores)] * len(scores) if scores else []
    return [s / total for s in scores]


def orientation_of(width: int, height: int) -> str:
    ratio = width / height if height else 1
    if ratio > 1.05:
        return "landscape"
    if ratio < 0.95:
        return "portrait"
    return "square"


def dominant_colors(image, count: int = 4) -> list[str]:
    """Most prominent colours, sampled from a small downscale."""
    small = image.convert("RGB").resize((48, 48))
    quantised = small.quantize(colors=8, method=2)
    palette = quantised.getpalette() or []
    ranked = sorted(quantised.getcolors() or [], reverse=True)
    out = []
    for _, index in ranked[:count]:
        r, g, b = palette[index * 3 : index * 3 + 3]
        out.append(f"#{r:02x}{g:02x}{b:02x}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path, help="folder of images to scan")
    ap.add_argument("--out", type=Path, default=Path("frontend/public/media-library"))
    ap.add_argument("--limit", type=int, default=0, help="stop after N images")
    ap.add_argument("--full-width", type=int, default=1600)
    ap.add_argument("--thumb-width", type=int, default=400)
    ap.add_argument("--quality", type=int, default=80)
    ap.add_argument(
        "--rebuild",
        action="store_true",
        help="reprocess every image from scratch, discarding the existing index",
    )
    ap.add_argument(
        "--backend",
        choices=[b.name for b in BACKENDS],
        help="force a vision backend (default: best available)",
    )
    args = ap.parse_args()

    if not args.source.is_dir():
        die(f"Not a folder: {args.source}")

    load_pillow()
    from PIL import Image

    files = sorted(p for p in args.source.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES)
    if not files:
        die(f"No images found under {args.source}")
    print(f"  found {len(files)} files")

    backend = select_backend(args.backend)
    print(f"  vision backend: {backend.name}")
    if backend.name == "heuristic":
        print("    (no vision model installed — labels are colour-based guesses.")
        print("     Re-run with clip-onnx or clip-torch to replace them.)")

    cat_names = list(CATEGORIES)
    tag_names = list(TAGS)
    if hasattr(backend, "set_labels"):
        backend.set_labels(cat_names + tag_names)
    backend.prepare([CATEGORIES[k] for k in cat_names] + [TAGS[k] for k in tag_names])

    full_dir = args.out / "full"
    thumb_dir = args.out / "thumb"
    full_dir.mkdir(parents=True, exist_ok=True)
    thumb_dir.mkdir(parents=True, exist_ok=True)

    # ---- Incremental import ------------------------------------------------
    #
    # The manifest is the library's index, not just its output. Reading it back
    # is what makes a second import additive: anything whose bytes are already
    # known is skipped untouched, so its id, thumbnail and hand-checked tags
    # survive. Ids are derived from the content hash, so they are stable across
    # runs by construction — nothing has to remember them.
    #
    # --rebuild is the deliberate escape hatch: it discards the index and
    # reprocesses everything, which is what you want after changing the label
    # set or moving to a better vision backend.
    manifest = args.out / "index.json"
    assets = []
    existing_hashes: set[str] = set()
    if manifest.exists() and not args.rebuild:
        try:
            previous = json.loads(manifest.read_text(encoding="utf-8"))
            assets = previous.get("assets", [])
            existing_hashes = {a.get("hash") for a in assets if a.get("hash")}
            print(f"  existing library: {len(assets)} images")
        except (OSError, ValueError) as err:
            die(f"Could not read {manifest}: {err}\n  Use --rebuild to start over.")
    elif args.rebuild and manifest.exists():
        print("  --rebuild: reprocessing the whole library")

    seen: dict[str, str] = {}
    added = 0
    already = 0
    duplicates = 0
    failures = 0
    category_counts: Counter[str] = Counter()

    for i, path in enumerate(files, 1):
        if args.limit and added >= args.limit:
            break
        try:
            digest = sha256(path)
            # Already in the library from an earlier import — leave it alone.
            if digest in existing_hashes:
                already += 1
                continue
            # The same bytes are processed once. This folder has 67 files with a
            # " (1)" suffix; without this they would ship twice.
            if digest in seen:
                duplicates += 1
                continue
            seen[digest] = path.name

            image = Image.open(path)
            image.load()
            image = image.convert("RGB")

            scores = backend.score(image)
            # Categories and tags are scored in one pass, so they land in one
            # distribution and compete: "a photo of food" and "coffee" split
            # probability that neither then clears its threshold. Renormalising
            # each group by its own sum is exactly the softmax restricted to
            # that group, which is what the two thresholds are calibrated for.
            cat_scores = renormalise(scores[: len(cat_names)])
            tag_scores = renormalise(scores[len(cat_names) :])

            ranked_cats = sorted(
                zip(cat_names, cat_scores), key=lambda kv: kv[1], reverse=True
            )
            categories = [k for k, s in ranked_cats[:MAX_CATEGORIES] if s >= CATEGORY_THRESHOLD]
            # Never leave an image unlabelled — the best guess beats nothing,
            # and an unfindable image may as well not be in the library.
            if not categories:
                categories = [ranked_cats[0][0]]

            ranked_tags = sorted(
                zip(tag_names, tag_scores), key=lambda kv: kv[1], reverse=True
            )
            tags = [k for k, s in ranked_tags[:MAX_TAGS] if s >= TAG_THRESHOLD]

            stem = digest[:16]
            full_name = f"{stem}.webp"
            thumb_name = f"{stem}.webp"

            def save(img, dest: Path, target_w: int) -> tuple[int, int]:
                out = img
                if img.width > target_w:
                    h = round(img.height * target_w / img.width)
                    out = img.resize((target_w, h), Image.LANCZOS)
                out.save(dest, "WEBP", quality=args.quality, method=4)
                return out.size

            # The dimensions that go in the manifest are the ones actually
            # written, not the source's. An Unsplash original is ~5000px wide
            # and what ships is 1600, so recording the source would have the
            # library reporting a size no file it serves actually has.
            width, height = save(image, full_dir / full_name, args.full_width)
            save(image, thumb_dir / thumb_name, args.thumb_width)

            assets.append(
                {
                    "file": f"full/{full_name}",
                    "thumb": f"thumb/{thumb_name}",
                    "source_file": path.name,
                    "hash": digest,
                    "title": categories[0],
                    "categories": categories,
                    "tags": tags,
                    "keywords": sorted({*(c.lower() for c in categories), *tags}),
                    "width": width,
                    "height": height,
                    "orientation": orientation_of(width, height),
                    "colors": dominant_colors(image),
                }
            )
            added += 1
            category_counts.update(categories)

            if i % 25 == 0 or i == len(files):
                print(f"    {i}/{len(files)}  new {added}  known {already}  dupes {duplicates}")

        except Exception as err:  # a bad file must not end the run
            failures += 1
            print(f"    skipped {path.name}: {err}")

    manifest.write_text(
        json.dumps({"version": 1, "backend": backend.name, "assets": assets}, indent=2), encoding="utf-8"
    )

    print(f"\n  wrote {manifest}")
    print(f"  {len(assets)} images · {duplicates} duplicates skipped · {failures} failed")
    print("\n  categories:")
    for name, n in category_counts.most_common():
        print(f"    {name:<14} {n}")


if __name__ == "__main__":
    main()
