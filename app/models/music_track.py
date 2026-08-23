"""MusicTrack ORM model — one track in the Music Library.

The Music Library is deliberately its own table rather than a `kind="music"`
view over `video_assets`, because a track carries things a file does not:

  * **A licence.** Every row records what the track is licensed under, where
    that licence text lives, and who has to be credited. Nothing without a
    recorded licence can be added to a project — see `can_use` below. That is
    the whole reason this model exists as a first-class thing: a music bed
    under a published video is the single most expensive mistake this module
    could ship, so the permission travels with the row and is checked at the
    point of use, not remembered by whoever added it.
  * **Search facets.** Mood, genre and duration are what people actually pick
    music by. They are columns, so the library filters in SQL rather than
    pulling every track into Python to sort it.

Two kinds of row, told apart by `source`:

  * **Catalogue** (`user_id` NULL) — openly-licensed tracks discovered through
    Openverse, the same keyless CC-licensed index the stock-image search
    already uses. The bytes stay at `stream_url` on the source; we cache the
    metadata so search, filters and the licence survive the API being slow or
    unreachable. `asset_id` is NULL.
  * **Upload** (`user_id` set, `source="upload"`) — somebody's own file. The
    bytes go through the normal asset pipeline into object storage, and
    `asset_id` points at the resulting `VideoAsset`. The user states the
    licence on upload; we record what they said rather than assuming.

Adding a track to a project does NOT copy audio. It creates a `VideoAudio`
layer referencing the same asset (upload) or carrying the stream URL and the
licence in its `meta` (catalogue). One track used in ten projects is one file.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Where a row came from. Not a label — it decides whether the bytes are ours
# (`upload`, read through the storage layer) or somebody else's (`openverse`,
# streamed from the source under its licence).
MUSIC_SOURCES = ("upload", "openverse", "builtin")

# The moods the library filters by. A closed list on purpose: free-text moods
# scraped from a provider produce forty near-synonyms and a filter nobody can
# use. Anything that does not map lands in "other".
MUSIC_MOODS = (
    "uplifting",
    "calm",
    "energetic",
    "dramatic",
    "happy",
    "sad",
    "inspiring",
    "dark",
    "playful",
    "professional",
    "other",
)

MUSIC_GENRES = (
    "cinematic",
    "electronic",
    "acoustic",
    "hiphop",
    "rock",
    "jazz",
    "classical",
    "ambient",
    "folk",
    "world",
    "other",
)

# Licence codes we are willing to record. Openverse returns these verbatim.
# `user` is what an upload gets: the account holder asserted the right to use
# it and named the source. There is no code here for "unknown" — a track with
# no licence is not stored.
MUSIC_LICENSES = (
    "cc0",
    "pdm",
    "by",
    "by-sa",
    "by-nc",
    "by-nd",
    "by-nc-sa",
    "by-nc-nd",
    "user",
)

# Licences that permit commercial use. A social post for a business is
# commercial, so an `nc` track cannot be added to a project — the library shows
# it, greyed, with the reason, rather than hiding it and leaving the user to
# wonder why a search returned nothing.
COMMERCIAL_LICENSES = frozenset({"cc0", "pdm", "by", "by-sa", "user"})

# Licences that require the creator to be credited. Recorded on the project so
# the credit can be produced later, when the video is published.
ATTRIBUTION_LICENSES = frozenset(
    {"by", "by-sa", "by-nc", "by-nd", "by-nc-sa", "by-nc-nd"}
)


class MusicTrack(Base):
    __tablename__ = "music_tracks"
    __table_args__ = {"info": {"alembic_only": True}}

    id: Mapped[int] = mapped_column(primary_key=True)

    # NULL for the shared catalogue, set for somebody's upload. Every query in
    # music.py filters on `user_id IS NULL OR user_id = :me`, the same rule
    # templates follow.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, default=None
    )

    # Stable identity for a catalogue row: "openverse:<provider-id>". Unique,
    # so re-running a search that returns the same track updates it instead of
    # inserting a second copy — this is what stops the catalogue growing a
    # duplicate every time somebody searches "calm piano".
    external_key: Mapped[str | None] = mapped_column(
        String(160), unique=True, index=True, default=None
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    artist: Mapped[str | None] = mapped_column(String(200), default=None)

    source: Mapped[str] = mapped_column(
        String(20), default="upload", index=True, nullable=False
    )

    # ---- Facets ----------------------------------------------------------
    mood: Mapped[str] = mapped_column(String(30), default="other", index=True, nullable=False)
    genre: Mapped[str] = mapped_column(String(30), default="other", index=True, nullable=False)
    # Indexed: the duration filter ("under 30s", "1–3 minutes") is a range scan
    # and the library is expected to hold thousands of catalogue rows.
    duration_seconds: Mapped[float] = mapped_column(
        Float, default=0.0, index=True, nullable=False
    )
    bpm: Mapped[int | None] = mapped_column(Integer, default=None)
    # Free-text keywords from the source, kept for search but never filtered
    # on — they are the provider's vocabulary, not ours.
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # ---- Licence ---------------------------------------------------------
    # Not nullable, and there is no default. A row cannot exist without one.
    license: Mapped[str] = mapped_column(String(20), nullable=False)
    license_url: Mapped[str | None] = mapped_column(String(500), default=None)
    # The credit line to show, exactly as it should appear.
    attribution: Mapped[str | None] = mapped_column(Text, default=None)
    # Where the track came from, so a licence claim can be checked by a human.
    source_url: Mapped[str | None] = mapped_column(String(500), default=None)

    # ---- Where the audio is ---------------------------------------------
    # Exactly one of these is set. `asset_id` for an upload (our storage);
    # `stream_url` for a catalogue track (the source's). Keeping both columns
    # rather than normalising to an asset is what makes the catalogue free:
    # searching does not download 3 MB per result into a bucket we pay for.
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("video_assets.id", ondelete="CASCADE"), index=True, default=None
    )
    stream_url: Mapped[str | None] = mapped_column(String(1000), default=None)
    # A small waveform image or preview clip from the source, when it offers
    # one. Purely decorative; the player never depends on it.
    preview_url: Mapped[str | None] = mapped_column(String(1000), default=None)
    content_type: Mapped[str] = mapped_column(
        String(120), default="audio/mpeg", nullable=False
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Hidden from the library without being deleted — how a catalogue row whose
    # source went away stops being offered while any project already using it
    # keeps its licence record.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ---- Licence questions, answered on the row --------------------------
    # Properties rather than columns: they are derived from `license`, and a
    # stored copy is a stored copy that can disagree with it.

    @property
    def allows_commercial(self) -> bool:
        return (self.license or "").lower() in COMMERCIAL_LICENSES

    @property
    def needs_attribution(self) -> bool:
        return (self.license or "").lower() in ATTRIBUTION_LICENSES

    @property
    def can_use(self) -> bool:
        """Whether this track may be added to a project.

        Commercial use is the test because this app exists to post on behalf of
        businesses. A track that fails it is still listed and still previewable
        — the user should be able to see what they cannot use and why.
        """
        return bool(self.is_active) and self.allows_commercial

    def credit_line(self) -> str:
        """The one-line credit a video using this track has to carry."""
        parts = [self.title]
        if self.artist:
            parts.append(f"by {self.artist}")
        code = (self.license or "").lower()
        if code == "cc0":
            parts.append("(CC0)")
        elif code == "pdm":
            parts.append("(Public Domain)")
        elif code == "user":
            parts.append("(supplied by the uploader)")
        else:
            parts.append(f"(CC {code.upper()})")
        return " ".join(parts)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<MusicTrack id={self.id} title={self.title!r} "
            f"mood={self.mood} license={self.license}>"
        )
