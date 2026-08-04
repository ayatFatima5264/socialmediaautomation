"""Pluggable vision backends for image categorisation.

The categoriser asks one question — "score this image against these labels" —
and three different engines can answer it. They are tried best-first and the
first one whose dependencies are installed wins, so the same command works on
whatever the machine happens to have.

    clip-torch   transformers + torch. Best accuracy. Heaviest install, and
                 torch lags new Python releases by months.
    clip-onnx    onnxruntime + tokenizers. Same CLIP weights, no torch —
                 roughly a quarter of the install, and onnxruntime ships
                 wheels for Python versions torch has not reached yet.
    heuristic    Pillow only. No vision model at all: classifies from colour,
                 brightness and composition. Weak, but it always runs, so a
                 library can be built today and re-tagged later.

Adding a fourth is one class with `available()` and `score()`. Nothing in the
Media Library knows which one produced its metadata — the manifest format is
the contract, not the model.
"""
from __future__ import annotations

import colorsys


class VisionBackend:
    """Score an image against text labels. Implementations return one float
    per label, in the order given, summing to roughly 1."""

    name = "base"

    @classmethod
    def available(cls) -> bool:
        raise NotImplementedError

    def prepare(self, prompts: list[str]) -> None:
        """Encode the label side once — it never changes between images."""

    def score(self, image) -> list[float]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# CLIP via torch
# ---------------------------------------------------------------------------

class TorchClipBackend(VisionBackend):
    name = "clip-torch"
    model_id = "openai/clip-vit-base-patch32"

    @classmethod
    def available(cls) -> bool:
        try:
            import torch  # noqa: F401
            from transformers import CLIPModel  # noqa: F401
            return True
        except Exception:
            return False

    def __init__(self):
        import torch
        from transformers import CLIPModel, CLIPProcessor

        self.torch = torch
        self.model = CLIPModel.from_pretrained(self.model_id)
        self.processor = CLIPProcessor.from_pretrained(self.model_id)
        self.model.eval()
        self.text_features = None

    def prepare(self, prompts):
        with self.torch.no_grad():
            inputs = self.processor(text=prompts, return_tensors="pt", padding=True)
            feats = self.model.get_text_features(**inputs)
            self.text_features = feats / feats.norm(dim=-1, keepdim=True)

    def score(self, image):
        with self.torch.no_grad():
            inputs = self.processor(images=image, return_tensors="pt")
            feats = self.model.get_image_features(**inputs)
            feats = feats / feats.norm(dim=-1, keepdim=True)
            return (feats @ self.text_features.T).softmax(dim=-1)[0].tolist()


# ---------------------------------------------------------------------------
# CLIP via ONNX Runtime — same weights, no torch
# ---------------------------------------------------------------------------

class OnnxClipBackend(VisionBackend):
    """CLIP through onnxruntime, using the ONNX export published for
    transformers.js. Downloads once to the HuggingFace cache, then offline."""

    name = "clip-onnx"
    repo = "Xenova/clip-vit-base-patch32"

    @classmethod
    def available(cls) -> bool:
        try:
            import numpy  # noqa: F401
            import onnxruntime  # noqa: F401
            from huggingface_hub import hf_hub_download  # noqa: F401
            from tokenizers import Tokenizer  # noqa: F401
            return True
        except Exception:
            return False

    def __init__(self):
        import numpy as np
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        self.np = np
        text_path = hf_hub_download(self.repo, "onnx/text_model.onnx")
        vision_path = hf_hub_download(self.repo, "onnx/vision_model.onnx")
        tok_path = hf_hub_download(self.repo, "tokenizer.json")

        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.text_session = ort.InferenceSession(text_path, opts, providers=["CPUExecutionProvider"])
        self.vision_session = ort.InferenceSession(vision_path, opts, providers=["CPUExecutionProvider"])
        self.tokenizer = Tokenizer.from_file(tok_path)
        self.tokenizer.enable_padding(length=77)
        self.tokenizer.enable_truncation(max_length=77)
        # Exports disagree on the text inputs: some take the attention mask,
        # some take only the ids and rely on CLIP's causal mask plus its
        # argmax-of-ids pooling to find the EOS position. Feed whatever this
        # graph actually declares rather than assuming one export's shape.
        self.text_inputs = {i.name for i in self.text_session.get_inputs()}
        self.text_features = None

    def _normalise(self, arr):
        return arr / self.np.linalg.norm(arr, axis=-1, keepdims=True)

    def prepare(self, prompts):
        encoded = self.tokenizer.encode_batch(prompts)
        feed = {"input_ids": self.np.array([e.ids for e in encoded], dtype=self.np.int64)}
        if "attention_mask" in self.text_inputs:
            feed["attention_mask"] = self.np.array(
                [e.attention_mask for e in encoded], dtype=self.np.int64
            )
        out = self.text_session.run(None, feed)
        self.text_features = self._normalise(out[0])

    def score(self, image):
        np = self.np
        # CLIP's preprocessing: 224px centre crop, then channel normalisation
        # with the constants the model was trained on.
        img = image.convert("RGB").resize((224, 224))
        arr = np.asarray(img, dtype=np.float32) / 255.0
        mean = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
        std = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
        arr = (arr - mean) / std
        arr = arr.transpose(2, 0, 1)[None, ...]

        out = self.vision_session.run(None, {"pixel_values": arr})
        feats = self._normalise(out[0])
        logits = (feats @ self.text_features.T)[0] * 100.0
        exp = np.exp(logits - logits.max())
        return (exp / exp.sum()).tolist()


# ---------------------------------------------------------------------------
# No model at all
# ---------------------------------------------------------------------------

class HeuristicBackend(VisionBackend):
    """Pillow-only fallback.

    Cannot recognise subjects, so it does not pretend to: it reads colour,
    brightness and saturation and nudges the labels those correlate with —
    warm and saturated toward food, cool and desaturated toward office and
    technology, green toward nature. Every image still gets a label and a
    palette, and re-running with a real backend later overwrites the guesses.
    """

    name = "heuristic"

    # Which labels each visual signal supports.
    SIGNALS = {
        "warm": ("Food", "Restaurant", "Beauty", "Lifestyle"),
        "cool": ("Technology", "SaaS", "Office", "Finance", "Business"),
        "green": ("Nature", "Travel"),
        "bright": ("Lifestyle", "Beauty", "Fashion", "Ecommerce"),
        "dark": ("Technology", "SaaS", "Finance"),
        "muted": ("Office", "Business", "Real Estate", "Interior"),
        "vivid": ("Food", "Fashion", "Travel", "Fitness"),
    }

    @classmethod
    def available(cls) -> bool:
        try:
            from PIL import Image  # noqa: F401
            return True
        except Exception:
            return False

    def __init__(self):
        self.labels: list[str] = []

    def prepare(self, prompts):
        # Prompts arrive as sentences; the caller also gives us the label names
        # through `set_labels`, because phrasing is meaningless here.
        self.n = len(prompts)

    def set_labels(self, labels: list[str]) -> None:
        self.labels = labels

    def score(self, image):
        small = image.convert("RGB").resize((32, 32))
        pixels = list(small.getdata())
        n = len(pixels)
        r = sum(p[0] for p in pixels) / n / 255
        g = sum(p[1] for p in pixels) / n / 255
        b = sum(p[2] for p in pixels) / n / 255
        h, l, s = colorsys.rgb_to_hls(r, g, b)

        active = set()
        if r > b + 0.04:
            active.add("warm")
        if b > r + 0.04:
            active.add("cool")
        if g > r and g > b:
            active.add("green")
        active.add("bright" if l > 0.55 else "dark" if l < 0.32 else "muted")
        if s > 0.35:
            active.add("vivid")

        weights = []
        for label in self.labels:
            score = 0.05
            for signal in active:
                if label in self.SIGNALS.get(signal, ()):
                    score += 1.0
            weights.append(score)
        total = sum(weights) or 1.0
        return [w / total for w in weights]


# Best first. The categoriser walks this list and takes the first that runs.
BACKENDS = [TorchClipBackend, OnnxClipBackend, HeuristicBackend]


def select_backend(preferred: str | None = None):
    """Instantiate the best available backend, or the named one."""
    candidates = BACKENDS
    if preferred:
        candidates = [b for b in BACKENDS if b.name == preferred]
        if not candidates:
            raise SystemExit(
                f"Unknown backend {preferred!r}. Choose from: "
                + ", ".join(b.name for b in BACKENDS)
            )
        if not candidates[0].available():
            raise SystemExit(f"Backend {preferred!r} is not installed.")

    for backend in candidates:
        if backend.available():
            return backend()

    raise SystemExit(
        "No vision backend available. Install at least Pillow:\n"
        "    pip install Pillow"
    )
