"""Extract source text from URLs and uploaded documents.

Powers the AI Generator's "Create From" sources (blog / website / product
URLs, YouTube links, and PDF / DOCX / TXT uploads). Everything reduces to a
plain-text "source" string that feeds the normal post-generation prompt, so
the generated output stays identical regardless of where the input came from.
"""
from __future__ import annotations

import html
import io
import re
import zipfile
from urllib.parse import urlparse

import httpx

from app.config import settings

# Keep extracted text bounded so prompts stay within model limits.
MAX_CHARS = 6000

_YT_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"}


class ExtractError(Exception):
    """Content extraction failed (bad URL, unreadable page, parse error)."""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def _html_to_text(raw: str) -> tuple[str, str]:
    """Return (title, body_text) from raw HTML using light, dependency-free parsing."""
    raw = re.sub(r"(?is)<(script|style|noscript|template)[^>]*>.*?</\1>", " ", raw)

    title = ""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    if m:
        title = _clean(m.group(1))

    # Prefer real content tags; fall back to a full strip if that's too thin.
    chunks = re.findall(r"(?is)<(?:p|h1|h2|h3|li|blockquote)[^>]*>(.*?)</", raw)
    body = _clean(" ".join(re.sub(r"(?is)<[^>]+>", " ", c) for c in chunks))
    if len(body) < 200:
        body = _clean(re.sub(r"(?is)<[^>]+>", " ", raw))
    return title, body[:MAX_CHARS]


def _is_youtube(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in _YT_HOSTS


async def extract_url(url: str) -> dict:
    """Fetch a URL and return {title, text, source}. Handles YouTube via oEmbed."""
    url = (url or "").strip()
    if not url:
        raise ExtractError("Enter a URL first.")
    if "://" not in url:
        url = "https://" + url

    try:
        async with httpx.AsyncClient(
            timeout=settings.ai_request_timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AutoSocialAI/1.0)"},
        ) as client:
            if _is_youtube(url):
                oe = await client.get(
                    "https://www.youtube.com/oembed",
                    params={"url": url, "format": "json"},
                )
                if oe.status_code != 200:
                    raise ExtractError("Couldn't read that YouTube video.")
                data = oe.json()
                title = data.get("title", "")
                author = data.get("author_name", "")
                text = (
                    f"A social media post about the YouTube video titled "
                    f"'{title}'" + (f" by {author}" if author else "") + "."
                )
                return {"title": title, "text": text, "source": "youtube"}

            resp = await client.get(url)
            if resp.status_code != 200:
                raise ExtractError(f"Page returned status {resp.status_code}.")
            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype and "text" not in ctype:
                raise ExtractError("That URL is not a readable web page.")
            title, body = _html_to_text(resp.text)
            if not body:
                raise ExtractError("No readable text found on that page.")
            return {"title": title, "text": body, "source": "url"}
    except httpx.HTTPError as exc:
        raise ExtractError(f"Couldn't fetch that URL: {exc}") from exc


def extract_file(filename: str, data: bytes) -> dict:
    """Extract text from an uploaded PDF / DOCX / TXT file."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        text = _pdf_text(data)
    elif name.endswith(".docx"):
        text = _docx_text(data)
    elif name.endswith((".txt", ".md", ".markdown")):
        text = data.decode("utf-8", errors="ignore")
    else:
        raise ExtractError("Unsupported file type. Upload a PDF, DOCX, or TXT.")

    text = _clean(text)
    if not text:
        raise ExtractError("Couldn't extract any text from that file.")
    return {"title": filename, "text": text[:MAX_CHARS], "source": "file"}


def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ExtractError("PDF support is not installed on the server.") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - pypdf raises various errors
        raise ExtractError("That doesn't look like a valid PDF.") from exc
    return " ".join((page.extract_text() or "") for page in reader.pages)


def _docx_text(data: bytes) -> str:
    # A .docx is a zip; the body lives in word/document.xml as <w:t> runs.
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ExtractError("That doesn't look like a valid DOCX.") from exc
    xml = re.sub(r"(?is)</w:p>", "\n", xml)  # keep paragraph breaks
    runs = re.findall(r"(?is)<w:t[^>]*>(.*?)</w:t>", xml)
    return " ".join(html.unescape(r) for r in runs)
