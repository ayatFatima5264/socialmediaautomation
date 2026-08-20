"""Render one Reel from a real image URL, to eyeball the pan/zoom by hand.

Lives in scripts/ rather than the repo root on purpose: named test_*.py there,
pytest would collect it, find no tests, and fail the whole run on the import.

    python scripts/make_test_reel.py [image_url] [duration] [zoom]
"""
from __future__ import annotations

import asyncio
import sys

from app.services.video_service import generate_image_video

IMAGE_URL = "https://picsum.photos/1080/1920"


async def main() -> None:
    image_url = sys.argv[1] if len(sys.argv) > 1 else IMAGE_URL
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    zoom = float(sys.argv[3]) if len(sys.argv) > 3 else 1.08

    output = await generate_image_video(
        image_url,
        duration=duration,
        width=1080,
        height=1920,
        zoom=zoom,
        # An explicit path: without one the file is an unnamed temp file that
        # nothing cleans up. Gitignored (*.mp4).
        output_path="test_reel.mp4",
    )

    print(f"VIDEO CREATED: {output}")


if __name__ == "__main__":
    asyncio.run(main())
