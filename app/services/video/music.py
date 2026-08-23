"""The Music Library — a licensed catalogue, plus whatever the user uploads.

Music is the one asset in this module where getting it wrong is a legal problem
rather than a quality problem, so the whole design is arranged around one rule:

    **A track cannot exist in this library without a recorded licence, and
    cannot be added to a project unless that licence permits commercial use.**

Both halves are enforced here, not in the UI. `MusicTrack.license` is NOT NULL
with no default, so there is no code path that inserts a track of unknown
provenance; and `add_to_project` checks `track.can_use` before it writes an
audio layer, so a track the library shows as unusable stays unusable even if
somebody calls the endpoint directly.

**Where the catalogue comes from.** Openverse — the same keyless, CC-indexed
source `image_service.py` already uses for stock photos, but its `/v1/audio/`
endpoint. Every result carries an explicit licence code, a licence URL and a
creator, which is exactly the metadata this module refuses to work without. The
search is restricted to `license_type=commercial`, so a track that cannot be
used in a business video does not come back at all.

**The catalogue is cached, not mirrored — until a track is picked.** A search
stores the *metadata* and previews the audio from the source's URL. Downloading
every search result would mean paying to store thousands of tracks nobody
picked, and re-hosting somebody else's file is a bigger licensing claim than
linking to it.

But the moment a track is added to a project, `ensure_stored` fetches it into
our own storage. That is not an optimisation — the renderer reads its inputs
from object storage and nowhere else, so a layer that pointed at a third-party
URL was attached, credited, and silent in the export. Fetching at pick time
rather than render time also puts the failure where the user can act on it: a
dead link is a message while they are still choosing, not a render that dies
twenty minutes later.

**Uploads.** The user's own file goes through the normal asset pipeline into
object storage with de-duplication on, and gets a `license="user"` row: they
told us they have the right to use it, and we record that they said so along
with whatever source they named.
"""
from __future__ import annotations

import logging

import httpx
from sqlalchemy import String, func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.music_track import (
    MUSIC_GENRES,
    MUSIC_LICENSES,
    MUSIC_MOODS,
    MusicTrack,
)
from app.models.video_asset import VideoAsset
from app.models.video_audio import VideoAudio
from app.models.video_project import VideoProject
from app.services.video import assets as asset_service

logger = logging.getLogger(__name__)


class MusicError(RuntimeError):
    """A music operation was refused. The message is user-facing."""


class TrackNotFound(MusicError):
    """No such track — or it belongs to somebody else."""


class LicenseRefused(MusicError):
    """The track's licence does not permit this use.

    Its own class because the UI treats it differently from a validation error:
    it is not something the user can fix by changing their input, so the
    message explains the licence rather than asking them to try again.
    """


# ---------------------------------------------------------------------------
# Facets
# ---------------------------------------------------------------------------

# The duration filter, as named buckets rather than two number boxes. People
# choose music for a 30-second Reel or a three-minute explainer, not for
# "between 47 and 112 seconds". `max` is None on the last one — open-ended.
DURATION_BUCKETS = (
    {"key": "short", "label": "Under 30s", "min": 0.0, "max": 30.0},
    {"key": "medium", "label": "30s – 1 min", "min": 30.0, "max": 60.0},
    {"key": "long", "label": "1 – 3 min", "min": 60.0, "max": 180.0},
    {"key": "extended", "label": "Over 3 min", "min": 180.0, "max": None},
)

_BUCKETS_BY_KEY = {bucket["key"]: bucket for bucket in DURATION_BUCKETS}

# Human labels for the moods and genres the model stores as slugs. Kept next to
# the filter code rather than in the model, because they are presentation and
# the model is storage.
MOOD_LABELS = {
    "uplifting": "Uplifting",
    "calm": "Calm",
    "energetic": "Energetic",
    "dramatic": "Dramatic",
    "happy": "Happy",
    "sad": "Sad",
    "inspiring": "Inspiring",
    "dark": "Dark",
    "playful": "Playful",
    "professional": "Professional",
    "other": "Other",
}

GENRE_LABELS = {
    "cinematic": "Cinematic",
    "electronic": "Electronic",
    "acoustic": "Acoustic",
    "hiphop": "Hip-hop",
    "rock": "Rock",
    "jazz": "Jazz",
    "classical": "Classical",
    "ambient": "Ambient",
    "folk": "Folk",
    "world": "World",
    "other": "Other",
}

LICENSE_LABELS = {
    "cc0": "CC0 — public domain dedication",
    "pdm": "Public domain",
    "by": "CC BY — credit required",
    "by-sa": "CC BY-SA — credit, share alike",
    "by-nc": "CC BY-NC — non-commercial only",
    "by-nd": "CC BY-ND — no derivatives",
    "by-nc-sa": "CC BY-NC-SA — non-commercial only",
    "by-nc-nd": "CC BY-NC-ND — non-commercial only",
    "user": "Supplied by you",
}


# ---------------------------------------------------------------------------
# Classifying a track
# ---------------------------------------------------------------------------
# Openverse has no "mood" field — it has free-text tags written by whoever
# uploaded the track. Mapping those onto a closed vocabulary is what makes a
# mood filter usable at all: without it the filter has four hundred values,
# most of them appearing once.
#
# Deliberately keyword matching and not a model. It is wrong sometimes, and the
# cost of being wrong is a track filed under "calm" that somebody thinks is
# "ambient" — which they will hear in the preview before they use it. Anything
# unmatched becomes "other" rather than being guessed at.

_MOOD_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("uplifting", ("uplifting", "upbeat", "positive", "optimistic", "bright", "hopeful")),
    ("calm", ("calm", "relax", "peaceful", "gentle", "soft", "meditat", "chill", "sleep")),
    ("energetic", ("energetic", "energy", "driving", "workout", "sport", "power", "fast", "intense")),
    ("dramatic", ("dramatic", "epic", "trailer", "tension", "suspense", "orchestral", "battle")),
    ("happy", ("happy", "joy", "cheerful", "fun", "sunny", "feelgood", "feel good")),
    ("sad", ("sad", "melanchol", "sorrow", "emotional", "lonely", "nostalg")),
    ("inspiring", ("inspir", "motivat", "achieve", "success", "triumph", "anthem")),
    ("dark", ("dark", "sinister", "horror", "eerie", "ominous", "creepy", "tense")),
    ("playful", ("playful", "quirky", "funny", "comic", "silly", "cartoon", "whimsic")),
    ("professional", ("corporate", "business", "professional", "presentation", "background", "tech")),
)

_GENRE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cinematic", ("cinematic", "film", "score", "trailer", "soundtrack", "epic")),
    ("electronic", ("electronic", "edm", "synth", "techno", "house", "dubstep", "trance", "dance")),
    ("acoustic", ("acoustic", "guitar", "piano", "unplugged", "singer")),
    ("hiphop", ("hip hop", "hip-hop", "hiphop", "rap", "trap", "beat", "boom bap")),
    ("rock", ("rock", "metal", "punk", "grunge", "indie rock")),
    ("jazz", ("jazz", "swing", "blues", "saxophone", "bebop")),
    ("classical", ("classical", "baroque", "symphony", "orchestra", "violin", "chamber")),
    ("ambient", ("ambient", "drone", "atmospher", "soundscape", "texture", "pad")),
    ("folk", ("folk", "country", "bluegrass", "banjo", "americana")),
    ("world", ("world", "latin", "afro", "reggae", "celtic", "indian", "arabic", "asian")),
)


def _haystack(*parts) -> str:
    """Everything a classifier should look at, lowercased and flattened.

    Accepts strings and lists of strings/dicts because Openverse's `tags` are
    `[{"name": "piano"}]`, its `genres` are plain strings, and the title is a
    string — and all three are worth reading.
    """
    words: list[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, str):
            words.append(part)
        elif isinstance(part, (list, tuple)):
            for item in part:
                if isinstance(item, str):
                    words.append(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("title")
                    if name:
                        words.append(str(name))
    return " ".join(words).lower()


def classify_mood(text: str) -> str:
    """The first mood whose keywords appear, or "other"."""
    for mood, keywords in _MOOD_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return mood
    return "other"


def classify_genre(text: str) -> str:
    """The first genre whose keywords appear, or "other"."""
    for genre, keywords in _GENRE_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return genre
    return "other"


def normalize_mood(value: str | None) -> str:
    slug = (value or "").strip().lower().replace(" ", "")
    return slug if slug in MUSIC_MOODS else "other"


def normalize_genre(value: str | None) -> str:
    slug = (value or "").strip().lower().replace("-", "").replace(" ", "")
    return slug if slug in MUSIC_GENRES else "other"


def normalize_license(value: str | None) -> str | None:
    """A licence code we recognise, or None.

    None is a rejection, not a default. Every caller treats it as "do not store
    this track" — see the module docstring.
    """
    slug = (value or "").strip().lower()
    return slug if slug in MUSIC_LICENSES else None


# ---------------------------------------------------------------------------
# Openverse
# ---------------------------------------------------------------------------

# Same identification header the image search sends. Openverse asks API clients
# to say who they are, and an anonymous client gets a lower rate limit.
_HEADERS = {"User-Agent": "AutoSocialAI/1.0 (+https://autosocial.ai)"}

# A search should not hang a page. Openverse is usually fast; when it is not,
# the library falls back to what is already cached, which is a working screen
# rather than a spinner.
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _external_key(item: dict) -> str | None:
    identifier = item.get("id") or item.get("identifier")
    return f"openverse:{identifier}" if identifier else None


def _duration_seconds(item: dict) -> float:
    """Openverse reports duration in milliseconds, and often not at all.

    Zero rather than None when it is missing: the column is NOT NULL and a
    track with an unknown length still belongs in the library — it just never
    matches a duration filter, which is the honest outcome.
    """
    raw = item.get("duration")
    try:
        value = float(raw or 0) / 1000.0
    except (TypeError, ValueError):
        return 0.0
    return round(value, 2) if value > 0 else 0.0


def _normalize_openverse(item: dict) -> dict | None:
    """One Openverse result as the fields `MusicTrack` needs, or None to skip.

    Returns None — rather than a row with gaps — when the result has no audio
    URL or no licence we recognise. Both are disqualifying: a track that cannot
    be played is not a track, and a track whose licence we cannot name is
    exactly what this module exists to keep out.
    """
    stream_url = item.get("url")
    key = _external_key(item)
    license_code = normalize_license(item.get("license"))

    if not stream_url or not key or not license_code:
        return None

    title = (item.get("title") or "Untitled track").strip()[:200]
    creator = (item.get("creator") or "").strip()[:200] or None

    tags = [
        str(tag.get("name"))
        for tag in (item.get("tags") or [])
        if isinstance(tag, dict) and tag.get("name")
    ][:20]

    text = _haystack(title, tags, item.get("genres"), item.get("category"))

    # The licence version matters — "CC BY" without "4.0" is not a citable
    # licence — so it is folded into the URL Openverse gives us and, failing
    # that, reconstructed from the code and version it reports.
    license_url = item.get("license_url")
    if not license_url and license_code not in ("cc0", "pdm", "user"):
        version = item.get("license_version") or "4.0"
        license_url = f"https://creativecommons.org/licenses/{license_code}/{version}/"

    return {
        "external_key": key,
        "title": title,
        "artist": creator,
        "source": "openverse",
        "mood": classify_mood(text),
        "genre": classify_genre(text),
        "duration_seconds": _duration_seconds(item),
        "tags": tags,
        "license": license_code,
        "license_url": license_url,
        "attribution": (item.get("attribution") or "").strip() or None,
        "source_url": item.get("foreign_landing_url") or item.get("detail_url"),
        "stream_url": stream_url,
        # Openverse renders a peaks JSON at `waveform`; it is a URL, not audio,
        # and the player never depends on it.
        "preview_url": item.get("waveform") or None,
        "content_type": f"audio/{(item.get('filetype') or 'mpeg').lower()}",
        "size_bytes": int(item.get("filesize") or 0),
    }


async def fetch_openverse(query: str, *, page_size: int = 20) -> list[dict]:
    """Search Openverse for openly-licensed audio.

    `license_type=commercial` is not a preference — it is the filter that keeps
    tracks this app may not use out of the catalogue entirely. `mature=false`
    for the same reason the image search sets it.

    Never raises. A search that fails returns an empty list and logs, because
    the library's own rows are still worth showing and a music screen that
    errors because a third party is slow is a worse outcome than a short list.
    """
    cleaned = (query or "").strip()
    if not cleaned:
        return []

    url = f"{settings.openverse_base.rstrip('/')}/v1/audio/"
    params = {
        "q": cleaned,
        "page_size": max(1, min(page_size, 50)),
        "license_type": "commercial",
        "mature": "false",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            results = response.json().get("results") or []
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Openverse audio search for %r failed: %s", cleaned, exc)
        return []

    normalized = [_normalize_openverse(item) for item in results]
    return [item for item in normalized if item is not None]


def cache_tracks(db: Session, rows: list[dict], *, commit: bool = True) -> list[MusicTrack]:
    """Insert or update catalogue rows, matched on `external_key`.

    Upsert rather than insert, so the same search run twice does not double the
    catalogue. The returned list is in the order given, which is the relevance
    order the provider chose — worth preserving, because it is better than any
    ordering we could apply to a text search.
    """
    if not rows:
        return []

    keys = [row["external_key"] for row in rows]
    existing = {
        track.external_key: track
        for track in db.scalars(
            select(MusicTrack).where(MusicTrack.external_key.in_(keys))
        ).all()
    }

    out: list[MusicTrack] = []
    for row in rows:
        track = existing.get(row["external_key"])
        if track is None:
            track = MusicTrack(user_id=None, **row)
            db.add(track)
        else:
            # A catalogue row is the provider's data; refresh it rather than
            # keeping a stale copy. A user's upload is never matched here —
            # uploads have no external_key.
            for field, value in row.items():
                setattr(track, field, value)
            track.is_active = True
        out.append(track)

    if commit:
        db.commit()
        for track in out:
            db.refresh(track)
    else:
        db.flush()

    return out


async def discover(db: Session, query: str, *, page_size: int = 20) -> list[MusicTrack]:
    """Search the provider and fold the results into the catalogue.

    Returns the tracks, already persisted. Called when a user searches for
    something the local catalogue has little of — see `search_tracks`, which
    decides when it is worth reaching out.
    """
    rows = await fetch_openverse(query, page_size=page_size)
    return cache_tracks(db, rows)


# ---------------------------------------------------------------------------
# The library
# ---------------------------------------------------------------------------


def _visible(user_id: int):
    """Rows this user may see: the shared catalogue plus their own uploads."""
    return select(MusicTrack).where(
        MusicTrack.is_active.is_(True),
        or_(MusicTrack.user_id.is_(None), MusicTrack.user_id == user_id),
    )


def _filtered(
    user_id: int,
    *,
    search: str | None,
    mood: str | None,
    genre: str | None,
    duration: str | None,
    source: str | None,
):
    """The library query with every filter applied.

    Shared by the listing and the count for the same reason the media library
    shares its builder: a total that disagrees with the rows on screen is worse
    than no total.
    """
    query = _visible(user_id)

    if search:
        # Every word, against everything that describes the track.
        #
        # Titles are the *least* useful field here: catalogue music is called
        # "berceusounette" and "Chicken Hiccups", and what makes it findable is
        # its tags, mood and genre. Matching the title and artist alone meant a
        # search for "guitar" returned nothing while the catalogue held eight
        # tracks tagged guitar.
        #
        # And each word separately, not the phrase: "upbeat guitar" as one LIKE
        # requires those two words adjacent and in that order, so it misses
        # "Upbeat Acoustic Guitar" — which is exactly how people search for
        # music. Every word must appear somewhere, which keeps two words
        # narrower than one rather than broader.
        for word in search.strip().lower().split()[:8]:
            pattern = f"%{word}%"
            query = query.where(
                or_(
                    func.lower(MusicTrack.title).like(pattern),
                    func.lower(func.coalesce(MusicTrack.artist, "")).like(pattern),
                    func.lower(MusicTrack.mood).like(pattern),
                    func.lower(MusicTrack.genre).like(pattern),
                    # `tags` is a JSON array; comparing it as text matches a tag
                    # anywhere in it on both SQLite and Postgres, which is all
                    # this needs — the alternative is a per-dialect JSON
                    # operator for a search box.
                    func.lower(func.cast(MusicTrack.tags, String)).like(pattern),
                )
            )

    if mood and mood in MUSIC_MOODS:
        query = query.where(MusicTrack.mood == mood)
    if genre and genre in MUSIC_GENRES:
        query = query.where(MusicTrack.genre == genre)

    bucket = _BUCKETS_BY_KEY.get((duration or "").lower())
    if bucket:
        # `> 0` excludes tracks of unknown length rather than filing them all
        # under "Under 30s", which is what a plain `>= 0` would do.
        query = query.where(MusicTrack.duration_seconds > 0)
        query = query.where(MusicTrack.duration_seconds >= bucket["min"])
        if bucket["max"] is not None:
            query = query.where(MusicTrack.duration_seconds < bucket["max"])

    if source == "uploads":
        query = query.where(MusicTrack.user_id == user_id)
    elif source == "catalogue":
        query = query.where(MusicTrack.user_id.is_(None))

    return query


def search_tracks(
    db: Session,
    *,
    user_id: int,
    search: str | None = None,
    mood: str | None = None,
    genre: str | None = None,
    duration: str | None = None,
    source: str | None = None,
    limit: int = 40,
    offset: int = 0,
) -> tuple[list[MusicTrack], int]:
    """A page of the library, and the total the filters match.

    Uploads first, then newest. Somebody's own track is the one they are most
    likely to be looking for, and burying it under a catalogue that grows with
    every search would make the upload feature feel broken.
    """
    query = _filtered(
        user_id,
        search=search,
        mood=mood,
        genre=genre,
        duration=duration,
        source=source,
    )

    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)

    rows = list(
        db.scalars(
            query.order_by(
                # NULL user_id (the catalogue) sorts after a real one. Written
                # as a boolean expression rather than `nullsfirst` because
                # SQLite and Postgres disagree about where NULLs go by default.
                MusicTrack.user_id.is_(None),
                MusicTrack.created_at.desc(),
                MusicTrack.id.desc(),
            )
            .limit(min(limit, 100))
            .offset(max(offset, 0))
        ).all()
    )
    return rows, total


def get_track(db: Session, *, user_id: int, track_id: int) -> MusicTrack:
    """One track this user is allowed to see.

    Ownership is in the query, not a check afterwards — the rule every other
    service in this module follows.
    """
    track = db.scalars(
        _visible(user_id).where(MusicTrack.id == track_id)
    ).first()
    if track is None:
        raise TrackNotFound("That track does not exist.")
    return track


def facets(db: Session, *, user_id: int) -> dict:
    """The filter options, with a live count on each.

    Counts come from the rows this user can actually see, so a mood with
    nothing behind it can be rendered as disabled instead of as a filter that
    silently empties the list.
    """
    base = _visible(user_id).subquery()

    def _counts(column_name: str) -> dict[str, int]:
        column = getattr(base.c, column_name)
        rows = db.execute(
            select(column, func.count()).select_from(base).group_by(column)
        ).all()
        return {str(value): int(total or 0) for value, total in rows}

    mood_counts = _counts("mood")
    genre_counts = _counts("genre")

    duration_counts = {}
    for bucket in DURATION_BUCKETS:
        condition = base.c.duration_seconds >= bucket["min"]
        statement = select(func.count()).select_from(base).where(
            base.c.duration_seconds > 0, condition
        )
        if bucket["max"] is not None:
            statement = statement.where(base.c.duration_seconds < bucket["max"])
        duration_counts[bucket["key"]] = int(db.scalar(statement) or 0)

    total = int(db.scalar(select(func.count()).select_from(base)) or 0)
    uploads = int(
        db.scalar(
            select(func.count()).select_from(base).where(base.c.user_id == user_id)
        )
        or 0
    )

    return {
        "moods": [
            {"key": key, "label": MOOD_LABELS[key], "count": mood_counts.get(key, 0)}
            for key in MUSIC_MOODS
        ],
        "genres": [
            {"key": key, "label": GENRE_LABELS[key], "count": genre_counts.get(key, 0)}
            for key in MUSIC_GENRES
        ],
        "durations": [
            {
                "key": bucket["key"],
                "label": bucket["label"],
                "count": duration_counts.get(bucket["key"], 0),
            }
            for bucket in DURATION_BUCKETS
        ],
        "total": total,
        "uploads": uploads,
        "catalogue": total - uploads,
    }


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

# Audio types the music library takes. Narrower than `assets.ACCEPTED_TYPES`,
# which also holds video and subtitles: an MP4 is not a music track, and
# accepting one here would put a video file in a list of things that get mixed
# under a voice-over.
UPLOAD_TYPES = frozenset(
    {
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/mp4",
        "audio/m4a",
        "audio/x-m4a",
        "audio/aac",
        "audio/ogg",
        "audio/flac",
    }
)


def upload_track(
    db: Session,
    *,
    user_id: int,
    data: bytes,
    content_type: str,
    filename: str | None,
    title: str | None = None,
    artist: str | None = None,
    mood: str | None = None,
    genre: str | None = None,
    source_url: str | None = None,
    attribution: str | None = None,
    confirmed_rights: bool = False,
) -> MusicTrack:
    """Store somebody's own music track.

    `confirmed_rights` is required and is not a formality. The user is telling
    us they hold or have been granted the right to use this audio; without that
    statement there is nothing distinguishing an upload from a copyrighted
    track someone found, and this library's entire premise is that we never
    hold one of those. The claim is recorded on the row.

    The bytes are de-duplicated: uploading the same MP3 twice reuses the stored
    object. A second *track row* is still refused rather than created, so the
    library does not show the same file twice under two names.
    """
    if not confirmed_rights:
        raise LicenseRefused(
            "Confirm you have the right to use this track before uploading it."
        )

    normalized_type = asset_service.normalize_content_type(content_type, filename)
    if normalized_type not in UPLOAD_TYPES:
        raise MusicError(
            f"{normalized_type} is not an audio file the music library can take."
        )

    asset = asset_service.store_asset(
        db,
        user_id=user_id,
        kind="music",
        data=data,
        content_type=normalized_type,
        title=(title or filename or "Untitled track"),
        filename=filename,
        dedupe=True,
        meta={"source": "music_upload"},
    )

    # The asset may be one this user already had — that is what dedupe does.
    # A second track row pointing at it would put the same file in the library
    # twice, so the existing track is returned instead.
    existing = db.scalars(
        select(MusicTrack).where(
            MusicTrack.user_id == user_id, MusicTrack.asset_id == asset.id
        )
    ).first()
    if existing is not None:
        return existing

    fallback = (title or filename or "Untitled track").rsplit(".", 1)[0]
    text = _haystack(fallback, artist, mood, genre)

    track = MusicTrack(
        user_id=user_id,
        external_key=None,
        title=fallback.strip()[:200] or "Untitled track",
        artist=(artist or "").strip()[:200] or None,
        source="upload",
        mood=normalize_mood(mood) if mood else classify_mood(text),
        genre=normalize_genre(genre) if genre else classify_genre(text),
        duration_seconds=float(asset.duration_seconds or 0.0),
        tags=[],
        license="user",
        license_url=None,
        attribution=(attribution or "").strip() or None,
        source_url=(source_url or "").strip() or None,
        asset_id=asset.id,
        stream_url=None,
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
    )
    db.add(track)
    db.commit()
    db.refresh(track)
    return track


def delete_track(db: Session, *, user_id: int, track: MusicTrack) -> None:
    """Remove one of this user's uploaded tracks, and its audio.

    A catalogue row is refused: it is shared, and one user deleting it would
    take it out of everybody's library. Hiding it for one account is a
    per-user preference this library does not have and does not need.
    """
    if track.user_id != user_id:
        raise MusicError("Catalogue tracks cannot be deleted.")

    asset_id = track.asset_id
    db.delete(track)
    db.commit()

    if asset_id is not None:
        asset = db.get(VideoAsset, asset_id)
        if asset is not None:
            asset_service.delete_asset(db, asset)


# ---------------------------------------------------------------------------
# Using a track
# ---------------------------------------------------------------------------

# What a music bed is worth relative to speech. 0.18 rather than something
# nearer 1.0 because an auto-added track at full volume drowning the voice-over
# is the single most common way a generated video comes out unusable — see the
# note on VideoAudio.volume.
DEFAULT_MUSIC_VOLUME = 0.18
DEFAULT_FADE_SECONDS = 1.5


# ---------------------------------------------------------------------------
# Getting a catalogue track into a renderable state
# ---------------------------------------------------------------------------
# A catalogue row holds metadata and a URL at somebody else's origin. The
# renderer only takes inputs from our own object storage, and the timeline
# bridge in `storyboard._music_layers` skips a layer with no stored audio — so
# a catalogue track added to a project used to be attached, credited, listed in
# the project's audio, and completely silent in the export.
#
# Fetching it on the way in is what closes that. It happens when the user picks
# the track, not when they render: a render that stops to download from a third
# party is a render that fails for a reason the user cannot act on.

FETCH_TIMEOUT = 60.0

AUDIO_TYPES = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/ogg": "ogg",
    "audio/vorbis": "ogg",
    "audio/flac": "flac",
    "audio/x-flac": "flac",
    "audio/mp4": "m4a",
    "audio/aac": "aac",
    "audio/webm": "webm",
}


async def fetch_audio(url: str) -> tuple[bytes, str]:
    """Download a track, or raise. Returns `(bytes, content_type)`.

    The type is checked after the response arrives rather than guessed from the
    URL: a catalogue link that redirects to an HTML landing page is common, and
    storing that as audio would produce a track that fails at the encoder
    instead of here.
    """
    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "AutoSocialAI/1.0 (+https://autosocial.ai)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.content
            content_type = (
                response.headers.get("content-type", "").split(";")[0].strip().lower()
            )
    except httpx.HTTPError as exc:
        raise MusicError(f"That track could not be downloaded: {exc}") from exc

    if content_type not in AUDIO_TYPES:
        raise MusicError(
            "That track's link did not return audio. It may have been removed "
            "from the source."
        )

    limit = settings.video_max_upload_mb * 1024 * 1024
    if not data:
        raise MusicError("That track's link returned an empty file.")
    if len(data) > limit:
        raise MusicError(
            f"That track is larger than the {settings.video_max_upload_mb} MB limit."
        )

    return data, content_type


async def ensure_stored(db: Session, *, track: MusicTrack, user_id: int) -> MusicTrack:
    """Make sure a track has audio in our own storage, fetching it if not.

    An upload already has an asset and is returned untouched. A catalogue track
    is downloaded once and keeps the asset, so picking the same track for a
    second project costs nothing — `store_asset` de-duplicates on checksum, so
    two users picking the same track share the bytes.
    """
    if track.asset_id is not None:
        return track

    if not track.stream_url:
        raise MusicError(
            f"“{track.title}” has no audio to fetch. Try another track."
        )

    data, content_type = await fetch_audio(track.stream_url)
    extension = AUDIO_TYPES[content_type]

    asset = asset_service.store_asset(
        db,
        user_id=user_id,
        kind="music",
        data=data,
        content_type=content_type,
        title=track.title[:200],
        filename=f"{track.id}-{track.title[:40]}.{extension}",
        dedupe=True,
        meta={
            "music_track_id": track.id,
            "license": track.license,
            "attribution": track.attribution,
            "source_url": track.source_url,
        },
    )

    track.asset_id = asset.id
    if not track.duration_seconds and asset.duration_seconds:
        track.duration_seconds = float(asset.duration_seconds)
    db.commit()
    db.refresh(track)

    logger.info(
        "Fetched catalogue track %s into asset %s (%s bytes)",
        track.id, asset.id, len(data),
    )
    return track


def add_to_project(
    db: Session,
    *,
    user_id: int,
    track: MusicTrack,
    project: VideoProject,
    volume: float | None = None,
    ducking: bool = True,
    loop: bool = True,
    fade_in: float | None = None,
    fade_out: float | None = None,
) -> VideoAudio:
    """Add a track to a project as a music layer.

    **The licence gate.** A track whose licence does not permit commercial use
    is refused here, at the point of use, not merely hidden in the listing —
    the library shows those tracks greyed with the reason, and a UI that hides
    a rule is a UI that eventually stops enforcing it.

    Nothing is copied. An uploaded track's layer points at the same asset the
    library row does; a catalogue track's layer carries the stream URL. One
    track in ten projects is one file.

    The licence, the credit line and the source travel onto the layer's `meta`.
    That is what makes the obligation survive: the catalogue row can change or
    go inactive later, and the project still knows what it agreed to when the
    track was added.
    """
    if project.user_id != user_id:
        raise MusicError("That project belongs to a different account.")

    if not track.can_use:
        raise LicenseRefused(
            f"“{track.title}” is licensed {LICENSE_LABELS.get(track.license, track.license)}. "
            f"It cannot be used in a business video."
        )

    if track.asset_id is None and not track.stream_url:
        raise MusicError(f"“{track.title}” has no audio to add.")

    # After any existing music, so adding a second bed does not silently
    # replace the first in the mix order.
    #
    # No `or -1` fallback on the scalar: the first track sits at position 0,
    # and `0 or -1` is -1 in Python, which would hand the second track position
    # 0 as well. COALESCE already guarantees a value, so the None check is
    # explicit instead.
    highest = db.scalar(
        select(func.coalesce(func.max(VideoAudio.position), -1)).where(
            VideoAudio.project_id == project.id, VideoAudio.role == "music"
        )
    )
    position = (-1 if highest is None else int(highest)) + 1

    layer = VideoAudio(
        project_id=project.id,
        asset_id=track.asset_id,
        role="music",
        label=track.title[:200],
        position=position,
        start_seconds=0.0,
        # None means "as long as the source is". The renderer trims the bed to
        # the video; committing to a length here would be wrong the moment a
        # scene is added.
        duration_seconds=None,
        volume=DEFAULT_MUSIC_VOLUME if volume is None else max(0.0, min(float(volume), 1.0)),
        fade_in=DEFAULT_FADE_SECONDS if fade_in is None else max(0.0, float(fade_in)),
        fade_out=DEFAULT_FADE_SECONDS if fade_out is None else max(0.0, float(fade_out)),
        ducking=bool(ducking),
        loop=bool(loop),
        meta={
            "track_id": track.id,
            "source": track.source,
            # The whole licence record, copied. See the docstring.
            "license": track.license,
            "license_url": track.license_url,
            "attribution": track.attribution,
            "credit": track.credit_line(),
            "requires_attribution": track.needs_attribution,
            "source_url": track.source_url,
            # Only for a catalogue track: the renderer fetches this. An upload
            # has an asset and does not need it.
            "stream_url": track.stream_url,
        },
    )
    db.add(layer)
    db.commit()
    db.refresh(layer)

    _place_on_timeline(db, project=project, layer=layer, track=track)

    logger.info(
        "Added track %s (%s) to project %s as music layer %s",
        track.id, track.license, project.id, layer.id,
    )
    return layer


def _place_on_timeline(
    db: Session, *, project: VideoProject, layer: VideoAudio, track: MusicTrack
) -> None:
    """Put the new layer on the project's timeline straight away.

    `storyboard._music_layers` folds these rows in when a project is *rebuilt*
    from its storyboard, which covers the AI flow. It does not cover a project
    someone built by hand in the editor: there, adding music succeeded, showed a
    credit, and then nothing played — the layer sat in the audio inbox waiting
    for a rebuild that never comes.

    `meta.audio_layer_id` is the same marker the rebuild uses, so folding in
    later recognises this clip instead of stacking a duplicate on top of it.
    """
    from app.services.video import projects as project_service
    from app.services.video import timeline as tl

    if layer.asset_id is None:
        return

    asset = db.get(VideoAsset, layer.asset_id)
    if asset is None:
        return

    document = tl.normalize(project.timeline or {})

    # A bed is trimmed to the picture, never the other way round. Taking the
    # track's own length would make adding two minutes of music turn a
    # six-second Reel into a two-minute one — the video the user actually made
    # followed by silence over a black frame.
    visual = max(
        (
            clip["start"] + clip["duration"]
            for track in document["tracks"]
            if track["id"] in ("video", "text")
            for clip in track["clips"]
        ),
        default=0.0,
    )
    natural = float(layer.duration_seconds or asset.duration_seconds or 30.0)
    length = min(natural, visual) if visual > 0 else natural

    try:
        document, _ = tl.add_clip(
            document,
            track_id="audio",
            clip={
                "kind": "audio",
                "asset_id": asset.id,
                "duration": length,
                "volume": float(layer.volume),
                "fade_in": float(layer.fade_in),
                "fade_out": float(layer.fade_out),
                "role": "music",
                "label": layer.label or track.title[:200],
                "meta": {"audio_layer_id": layer.id},
            },
            at=float(layer.start_seconds or 0.0),
        )
    except tl.TimelineError as exc:
        # The layer is real and credited either way. A full audio track is not
        # a reason to fail the request the user actually made.
        logger.warning(
            "Could not place music layer %s on project %s: %s", layer.id, project.id, exc
        )
        return

    project_service.update_project(db, project=project, patch={"timeline": document})


def project_credits(db: Session, project_id: int) -> list[str]:
    """The credit lines a project's music obliges it to show.

    Read from the layers rather than from the tracks, so a project keeps its
    obligation even if the catalogue row is gone. Only licences that actually
    require attribution produce a line — padding the list with CC0 tracks
    would make the real requirements easy to miss.
    """
    layers = db.scalars(
        select(VideoAudio).where(
            VideoAudio.project_id == project_id, VideoAudio.role == "music"
        )
    ).all()

    credits: list[str] = []
    for layer in layers:
        meta = layer.meta or {}
        if not meta.get("requires_attribution"):
            continue
        line = meta.get("attribution") or meta.get("credit")
        if line and line not in credits:
            credits.append(line)
    return credits


def suggested_queries() -> list[str]:
    """Starting points for an empty search box.

    The catalogue is fetched on demand, so a first visit has nothing in it. A
    row of one-tap searches is what turns that from an empty screen into a
    library — and these are the moods this app's users actually make videos in.
    """
    return [
        "uplifting corporate",
        "calm piano",
        "energetic electronic",
        "cinematic trailer",
        "lofi hip hop",
        "acoustic guitar",
        "ambient background",
        "inspiring motivation",
    ]
