"""HTTP range responses — what makes audio and video actually playable.

A browser does not fetch media the way it fetches an image. It opens the file
with `Range: bytes=0-`, reads the header, then seeks by asking for the byte
range it wants. A server that answers every one of those with a plain 200 and
the whole body is not merely inefficient:

  * **Chrome's media pipeline stalls.** An `<audio>` element pointed at a route
    with no range support sits at `HAVE_NOTHING` with `duration = NaN` and
    never plays. This is not theoretical — it is the bug this module was
    written to fix.
  * **Seeking is impossible.** Dragging a playhead is a range request. Without
    one the only way to reach the middle of a file is to download all of it.
  * **A 40 MB render is sent in full to play its first second.**

So this is not an optimisation. Range support is the difference between a media
route that works and one that does not.

Only needed for the database-backed storage; R2 speaks ranges natively and that
path redirects to it. Which is the usual shape of these two backends: the
development one has to reimplement what the production one gets from the vendor.
"""
from __future__ import annotations

import re

from fastapi import Response

# `bytes=START-END`, either end optional. A multi-range request
# ("bytes=0-99,200-299") is deliberately not supported: it requires a multipart
# response, no browser media stack sends one, and answering it wrongly is worse
# than declining it — a request we cannot satisfy correctly falls back to 200,
# which is what the RFC allows.
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Resolve a Range header to inclusive (start, end), or None for the whole file.

    Returns None when there is no header, when it is not a single byte range,
    or when it is syntactically invalid — all of which the RFC says to answer
    with the entire representation rather than an error.

    Raises ValueError when the range is well-formed but cannot be satisfied
    (a start past the end of the file), which is a 416.
    """
    if not header:
        return None

    match = _RANGE.match(header.strip())
    if not match:
        return None

    raw_start, raw_end = match.groups()

    if not raw_start and not raw_end:
        return None  # "bytes=-" is meaningless

    if not raw_start:
        # A suffix range: "bytes=-500" means the LAST 500 bytes, not the first.
        # Getting this backwards serves the wrong part of the file, and the
        # only symptom is audio that starts in the wrong place.
        length = int(raw_end)
        if length <= 0:
            raise ValueError("A suffix range must ask for at least one byte.")
        start = max(0, size - length)
        return start, size - 1

    start = int(raw_start)
    if start >= size:
        raise ValueError("The range starts past the end of the file.")

    end = int(raw_end) if raw_end else size - 1
    # A client may ask for more than exists; the answer is what there is.
    end = min(end, size - 1)
    if end < start:
        raise ValueError("The range ends before it starts.")

    return start, end


def ranged_response(
    data: bytes,
    *,
    content_type: str,
    range_header: str | None = None,
    cache_control: str = "public, max-age=31536000, immutable",
    filename: str | None = None,
) -> Response:
    """Serve bytes, honouring a Range header when one is present.

    Always advertises `Accept-Ranges: bytes` — including on the full-body
    response, because that header is how the client learns it is allowed to
    seek at all.
    """
    size = len(data)
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": cache_control,
        # These bytes are cached for a year, and the same URL is fetched both by
        # a plain <img> (no Origin, so no CORS headers on the response) and by a
        # crossOrigin canvas image. Without Vary, the browser reuses the former
        # for the latter, and the canvas load fails on a missing
        # Access-Control-Allow-Origin. Vary keys the cache on Origin instead.
        "Vary": "Origin",
    }
    if filename:
        safe = filename.replace('"', "")
        headers["Content-Disposition"] = f'inline; filename="{safe}"'

    try:
        window = parse_range(range_header, size)
    except ValueError:
        # 416 must state the real size, so the client can ask again correctly.
        return Response(
            status_code=416,
            headers={**headers, "Content-Range": f"bytes */{size}"},
        )

    if window is None:
        headers["Content-Length"] = str(size)
        return Response(content=data, media_type=content_type, headers=headers)

    start, end = window
    chunk = data[start : end + 1]
    headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    headers["Content-Length"] = str(len(chunk))

    return Response(
        content=chunk,
        status_code=206,
        media_type=content_type,
        headers=headers,
    )
