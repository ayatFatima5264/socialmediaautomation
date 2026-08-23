"""Reading a script out of an uploaded document.

Subtitle Studio's second independent input: a TXT, DOCX or PDF that holds the
words, with no recording behind them. What comes out is one plain-text string,
which is exactly what `subtitles.cues_from_script` already takes — so a
document and a pasted script converge on the same timing code within one
function call of each other, and there is no second way for a document to
become cues.

**Why this is not `extract_service.extract_file`.** That one feeds the AI
Generator's prompt, and its two defining choices are wrong here: it truncates
to 6000 characters, which would silently drop the back half of a script, and
it collapses all whitespace to single spaces, which destroys the paragraph
breaks that decide where one subtitle ends and the next begins. Its DOCX
reader also joins every run with a space — Word starts a new run wherever
formatting changes, including in the middle of a word, so "important" comes
back as "import ant". Tolerable in a prompt, not in a subtitle.

Nothing here reaches the network and nothing is stored: the bytes are read,
turned into text, and dropped.
"""
from __future__ import annotations

import html
import io
import re
import zipfile
from pathlib import Path


class DocumentError(RuntimeError):
    """A document could not be read. The message is user-facing."""


# Extension -> what it is. Matched on the extension rather than the browser's
# content type because a .docx routinely arrives as application/octet-stream
# and a .txt as nothing at all.
ACCEPTED_DOCUMENTS: dict[str, str] = {
    ".txt": "text",
    ".md": "text",
    ".markdown": "text",
    ".rtf": "rtf",
    ".docx": "docx",
    ".pdf": "pdf",
}

#: A script is words, not a media file. 10 MB is a very long screenplay and
#: still small enough that reading it is instant.
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024

#: A ceiling on the text itself, so a pathological PDF cannot produce a track
#: with a hundred thousand cues in it. Roughly 90 minutes of narration.
MAX_CHARACTERS = 120_000

# Zero-width and bidi marks. Word and PDF exporters sprinkle these through
# text; they are invisible, they survive into an SRT, and they break word
# matching during alignment.
_INVISIBLE = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff]")


def accepted_extensions() -> list[str]:
    return sorted(ACCEPTED_DOCUMENTS)


# How much of a document has to read as language before it is treated as one.
# Deliberately generous: a script with a table of contents, some maths and a few
# emoji is still a script, while a renamed binary is nowhere near.
MIN_PRINTABLE_RATIO = 0.85


def _printable_ratio(text: str) -> float:
    """The share of characters that could plausibly be part of a script."""
    sample = text[:4000]
    if not sample:
        return 1.0
    readable = sum(
        1 for ch in sample if ch.isprintable() or ch in "\n\t"
    )
    return readable / len(sample)


def _clean(text: str) -> str:
    """Tidy extracted text while keeping the structure that timing needs.

    Paragraph breaks survive because `cues_from_script` splits on them; runs of
    spaces and stray blank lines do not, because they only make the cue text
    look broken.
    """
    text = _INVISIBLE.sub("", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Non-breaking and other exotic spaces read as text but are not `\s` to
    # everything downstream.
    text = text.replace("\u00a0", " ").replace("\u2028", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n", "\n", text)
    # Three or more blank lines down to one: a paragraph break is a paragraph
    # break however many empty lines the exporter wrote.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _text_document(data: bytes) -> str:
    """A plain-text or Markdown file.

    Decoded as UTF-8 first, then Latin-1, which between them cover what a text
    editor on any desktop produces. `utf-8-sig` because Notepad writes a BOM.
    """
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


def _rtf_document(data: bytes) -> str:
    """A minimal RTF reader — control words out, escaped characters in.

    Included because "save it as .rtf" is what a lot of people mean by "plain
    text", and RTF is close enough to plain text that refusing it would be a
    refusal about a file extension rather than about the content.
    """
    raw = data.decode("latin-1", errors="replace")
    if not raw.lstrip().startswith("{" + chr(92) + "rtf"):
        raise DocumentError("That does not look like a valid RTF file.")

    # \par and \line are the paragraph breaks; everything else that looks like
    # a control word is formatting.
    raw = re.sub(r"\\par[d]?\b", "\n", raw)
    raw = re.sub(r"\\line\b", "\n", raw)
    raw = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), raw)
    raw = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", raw)
    return raw.replace("{", "").replace("}", "")


def _docx_document(data: bytes) -> str:
    """A .docx, paragraph by paragraph.

    A .docx is a zip and the body is `word/document.xml`. Two details decide
    whether the result is readable:

      * **Paragraphs are split before runs are read**, so a paragraph break
        survives as a newline. Reading every `<w:t>` in the file first and
        joining them loses the document's shape entirely.
      * **Runs inside a paragraph are concatenated with nothing between them.**
        Word starts a new run wherever formatting changes — including in the
        middle of a word, which is what a spell-check correction or a tracked
        change leaves behind.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise DocumentError(
            "That file could not be opened as a Word document. If it is an "
            "older .doc, save it as .docx and try again."
        ) from exc

    # Tabs and manual line breaks are whitespace, not nothing.
    xml = re.sub(r"(?is)<w:tab[^>]*/?>", "\t", xml)
    xml = re.sub(r"(?is)<w:br[^>]*/?>", "\n", xml)

    paragraphs: list[str] = []
    for block in re.split(r"(?is)</w:p>", xml):
        runs = re.findall(r"(?is)<w:t[^>]*>(.*?)</w:t>", block)
        if not runs:
            continue
        paragraphs.append(html.unescape("".join(runs)))

    return "\n\n".join(paragraphs)


def _pdf_document(data: bytes) -> str:
    """A PDF, page by page.

    A PDF that holds a scan holds pictures of words, and pypdf correctly
    returns nothing for it. That case is caught by the caller and reported as
    what it is rather than as a broken file.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise DocumentError(
            "PDF support is not installed on the server. Upload a DOCX or TXT "
            "instead."
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 - pypdf raises a variety of errors
        raise DocumentError(
            "That file could not be read as a PDF. It may be damaged or "
            "password-protected."
        ) from exc

    return "\n\n".join(page for page in pages if page.strip())


_READERS = {
    "text": _text_document,
    "rtf": _rtf_document,
    "docx": _docx_document,
    "pdf": _pdf_document,
}


def extract(filename: str, data: bytes) -> dict:
    """Read a document into a script.

    Returns `{text, kind, word_count, character_count, truncated}`.

    Every refusal is a sentence the person who uploaded the file can act on:
    which formats are accepted, that the file is empty, that a scanned PDF has
    no text in it to read. None of them is a stack trace.
    """
    suffix = Path(filename or "").suffix.lower()
    kind = ACCEPTED_DOCUMENTS.get(suffix)

    if kind is None:
        raise DocumentError(
            f"A {suffix} file cannot be read as a script. Upload a TXT, DOCX, "
            f"PDF, RTF or Markdown file."
            if suffix
            else "That file has no extension, so it cannot be read as a "
            "script. Upload a TXT, DOCX, PDF, RTF or Markdown file."
        )

    if not data:
        raise DocumentError("That file is empty.")

    if len(data) > MAX_DOCUMENT_BYTES:
        raise DocumentError(
            f"That document is {len(data) / (1024 * 1024):.0f} MB. The limit "
            f"is {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB."
        )

    text = _clean(_READERS[kind](data))

    # A binary file renamed `.txt` decodes to control characters, and every one
    # of them survives to become cue text, an SRT line, and finally a drawtext
    # argument at render time. Nothing downstream refuses it, so it is refused
    # here — the ratio, rather than a blanket ban, because real scripts do
    # contain the odd exotic character.
    if text and _printable_ratio(text) < MIN_PRINTABLE_RATIO:
        raise DocumentError(
            "That file does not look like text. If it is a document, save it "
            "as TXT, DOCX, PDF or RTF and upload that."
        )

    if not text:
        if kind == "pdf":
            raise DocumentError(
                "No text could be read from that PDF. If it is a scan, the "
                "words are an image rather than text — export it from the "
                "original document, or paste the script instead."
            )
        raise DocumentError("No readable text could be found in that document.")

    truncated = len(text) > MAX_CHARACTERS
    if truncated:
        # Cut at a paragraph or sentence boundary rather than mid-word, so the
        # last cue is a whole thought.
        head = text[:MAX_CHARACTERS]
        cut = max(head.rfind("\n\n"), head.rfind(". "))
        text = head[: cut + 1] if cut > MAX_CHARACTERS // 2 else head

    return {
        "text": text,
        "kind": kind,
        "word_count": len(text.split()),
        "character_count": len(text),
        "truncated": truncated,
    }
