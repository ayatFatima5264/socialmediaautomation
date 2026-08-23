"""Request and response shapes for the Music Library.

The licence is on every single response. Not as a footnote and not only in a
detail view — `license`, `license_label`, `can_use` and `requires_attribution`
come back on every track in every list, because the moment a track's usability
becomes something the client has to look up separately is the moment a UI ships
that forgot to.

`can_use` is computed server-side from the licence rather than left to the
client to derive. A client that decided for itself would be one release away
from disagreeing with the endpoint that actually enforces it.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TrackRead(BaseModel):
    """One track in the library."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    artist: str | None = None
    source: str
    mood: str
    genre: str
    duration_seconds: float
    bpm: int | None = None
    tags: list[str] = Field(default_factory=list)

    # ---- Licence, on every row ------------------------------------------
    license: str
    license_label: str
    license_url: str | None = None
    attribution: str | None = None
    source_url: str | None = None
    # Whether this track may be added to a project at all, and why not.
    can_use: bool
    requires_attribution: bool
    blocked_reason: str | None = None
    credit: str

    # ---- Playback --------------------------------------------------------
    # `url` is what the player loads: our own storage URL for an upload, the
    # source's URL for a catalogue track. One field, so the player does not
    # have to know which kind it has.
    url: str | None = None
    content_type: str
    size_bytes: int
    # True when the audio is ours. The UI uses it for the one honest caveat
    # worth surfacing: a catalogue track streams from its source, so it needs
    # the network and can go away if the source withdraws it.
    is_hosted: bool
    is_owned: bool
    created_at: datetime


class FacetOption(BaseModel):
    key: str
    label: str
    count: int


class MusicFacets(BaseModel):
    """The filter options, each with how many tracks are behind it."""

    moods: list[FacetOption]
    genres: list[FacetOption]
    durations: list[FacetOption]
    total: int
    uploads: int
    catalogue: int
    # One-tap searches for an empty library. See `music.suggested_queries`.
    suggestions: list[str] = Field(default_factory=list)


class TrackList(BaseModel):
    items: list[TrackRead]
    total: int
    limit: int
    offset: int
    # True when this response included a live provider search. Lets the UI say
    # "searched the catalogue" rather than leaving a short list looking like a
    # bug — see the `discover` note in the route.
    searched_catalogue: bool = False


class TrackUpload(BaseModel):
    """Metadata sent alongside an uploaded audio file.

    `confirmed_rights` is required and has no default. The user has to state
    that they may use this audio; a default of True would make the statement
    meaningless and a default of False would make every upload fail. Requiring
    it is the point.
    """

    title: str | None = Field(default=None, max_length=200)
    artist: str | None = Field(default=None, max_length=200)
    mood: str | None = None
    genre: str | None = None
    source_url: str | None = Field(default=None, max_length=500)
    attribution: str | None = None
    confirmed_rights: bool


class TrackAdd(BaseModel):
    """Add a track to a project as a music layer."""

    project_id: int
    # All optional: the defaults in `music.add_to_project` are chosen to
    # produce a usable mix without the user touching anything, and a client
    # that sends nothing gets that.
    volume: float | None = Field(default=None, ge=0.0, le=1.0)
    ducking: bool = True
    loop: bool = True
    fade_in: float | None = Field(default=None, ge=0.0, le=30.0)
    fade_out: float | None = Field(default=None, ge=0.0, le=30.0)


class AudioLayerRead(BaseModel):
    """The music layer a track became."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    asset_id: int | None = None
    role: str
    label: str | None = None
    position: int
    start_seconds: float
    duration_seconds: float | None = None
    volume: float
    fade_in: float
    fade_out: float
    ducking: bool
    loop: bool
    muted: bool
    # The licence record copied onto the layer when the track was added — the
    # thing that keeps the obligation attached to the project.
    meta: dict = Field(default_factory=dict)
    created_at: datetime


class ProjectCredits(BaseModel):
    """The credit lines a project's music obliges it to display."""

    project_id: int
    credits: list[str]
