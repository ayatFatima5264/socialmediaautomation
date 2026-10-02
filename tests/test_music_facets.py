"""BUG-11: the Music Library's mood and genre facets are empty after a
successful upload.

QA's sequence, verbatim:

    Upload 201, track id 1, mood=other, genre=other, can_use true
    GET /api/video/music/facets   mood and genre both 0

The track is stored and the filters are all at zero, so the library looks empty
to anyone who uses the facets to browse it.

The closed-list design is deliberate and stays: free-text moods scraped from
Openverse produce forty near-synonyms and a filter nobody can use, and anything
unmapped lands in "other". So the question is not "should `other` be in the
list" — it is — it is why a track that *is* counted is not showing up in the
counts.
"""
from __future__ import annotations

import struct
from pathlib import Path

from tests.conftest import WAV_BYTES

REPO_ROOT = Path(__file__).resolve().parent.parent
MUSIC_PAGE = REPO_ROOT / "frontend" / "src" / "pages" / "video" / "MusicLibrary.jsx"
API_JS = REPO_ROOT / "frontend" / "src" / "lib" / "api.js"

# Two distinguishable uploads. The same bytes are a duplicate by design — the
# library de-duplicates on content, so "upload twice" is one track, not two.
OTHER_WAV = (
    b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
    b"\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x10\x00"
    + struct.pack("<h", 4096) * 32
)


def upload(studio_client, headers, audio=WAV_BYTES, name="mine.wav", **fields):
    form = {"confirmed_rights": "true", **fields}
    return studio_client.post(
        "/api/video/music/upload",
        headers=headers,
        files={"file": (name, audio, "audio/wav")},
        data=form,
    )


def facets(studio_client, headers):
    response = studio_client.get("/api/video/music/facets", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def library(studio_client, headers, **params):
    response = studio_client.get("/api/video/music", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def counts(rows):
    return {row["key"]: row["count"] for row in rows}


# ---------------------------------------------------------------------------
# The reported sequence.
# ---------------------------------------------------------------------------


def test_an_upload_shows_up_in_the_facets(studio_client, headers):
    """The exact QA observation: upload succeeds, both facets read zero."""
    created = upload(studio_client, headers).json()
    assert created["mood"] == "other", "this test describes the reported case"
    assert created["genre"] == "other"

    data = facets(studio_client, headers)

    assert data["total"] == 1, "the track is not in the library the facets count"
    assert counts(data["moods"])["other"] == 1, (
        f"the uploaded track is not counted under any mood: {data['moods']}"
    )
    assert counts(data["genres"])["other"] == 1, (
        f"the uploaded track is not counted under any genre: {data['genres']}"
    )


def test_a_named_mood_is_counted_under_that_mood(studio_client, headers):
    """Not just `other` — a track the user described should land in its own
    bucket, or the filter is decorative."""
    upload(studio_client, headers, mood="calm", genre="jazz")

    data = facets(studio_client, headers)

    assert counts(data["moods"])["calm"] == 1
    assert counts(data["genres"])["jazz"] == 1


def test_the_facet_total_agrees_with_the_listing(studio_client, headers):
    """A total that disagrees with the rows on screen is worse than no total —
    that is the same reason the listing and the count share `_filtered`."""
    upload(studio_client, headers)
    upload(studio_client, headers, audio=OTHER_WAV, name="other.wav")

    data = facets(studio_client, headers)
    listed = library(studio_client, headers)

    total = sum(counts(data["moods"]).values())
    assert total == data["total"] == len(listed["items"]), (
        f"facets count {total}, facets total says {data['total']}, "
        f"the listing has {len(listed['items'])}"
    )
    assert sum(counts(data["genres"]).values()) == data["total"]


def test_counts_do_not_leak_across_users(studio_client, headers, other_headers):
    """The counts are of what this user can see. Another user's upload must not
    appear in mine, or the filter leads to an empty list."""
    upload(studio_client, headers)
    upload(
        studio_client,
        other_headers,
        audio=OTHER_WAV,
        name="theirs.wav",
        mood="calm",
        genre="jazz",
    )

    mine = facets(studio_client, headers)
    theirs = facets(studio_client, other_headers)

    assert mine["total"] == 1, "another user's upload leaked into my counts"
    assert counts(mine["moods"])["calm"] == 0
    assert counts(theirs["moods"])["calm"] == 1
    assert counts(theirs["genres"])["jazz"] == 1


def test_every_bucket_in_the_closed_list_is_reported(studio_client, headers):
    """A stable shape: an empty mood is reported at zero rather than omitted, so
    the filter row does not reflow as the library fills in."""
    data = facets(studio_client, headers)

    from app.models.music_track import MUSIC_GENRES, MUSIC_MOODS

    assert [row["key"] for row in data["moods"]] == list(MUSIC_MOODS)
    assert [row["key"] for row in data["genres"]] == list(MUSIC_GENRES)
    assert "other" in MUSIC_MOODS and "other" in MUSIC_GENRES, (
        "if `other` is excluded the fallback bucket is where every upload goes"
    )


def test_filtering_by_the_reported_mood_returns_the_track(studio_client, headers):
    """The reason facets exist. A non-zero count that filters to nothing is the
    same bug wearing a different hat."""
    track = upload(studio_client, headers).json()

    items = library(studio_client, headers, mood="other")["items"]

    assert [item["id"] for item in items] == [track["id"]]


# ---------------------------------------------------------------------------
# The other half of the finding: an upload with no way to describe itself.
#
# The counts above were already correct. What made "mood and genre both 0" the
# *only* possible outcome is that the upload modal asked for a title, an artist,
# a source and a licence — and never a mood or a genre, so every upload was
# `other` by construction, and an `other` track is what you get when the
# library holds one track.
# ---------------------------------------------------------------------------


def test_the_upload_form_offers_a_mood_and_a_genre():
    """Without these two controls the bug cannot be fixed from the browser."""
    source = MUSIC_PAGE.read_text(encoding="utf-8")

    assert "<span className=\"label\">Mood (optional)</span>" in source
    assert "<span className=\"label\">Genre (optional)</span>" in source
    assert "setForm({ ...form, mood: event.target.value })" in source
    assert "setForm({ ...form, genre: event.target.value })" in source


def test_the_upload_mood_choices_come_from_the_facet_list():
    """One closed list. Options hardcoded here would drift from the buckets the
    server counts, and the drift is invisible until someone filters by a mood
    that does not exist."""
    source = MUSIC_PAGE.read_text(encoding="utf-8")

    assert "library.facets?.moods" in source
    assert "library.facets?.genres" in source


def test_the_api_layer_forwards_the_chosen_mood_and_genre():
    """The controls in the modal are worth nothing if the form drops them."""
    api_source = API_JS.read_text(encoding="utf-8")

    assert "['mood', fields.mood]" in api_source
    assert "['genre', fields.genre]" in api_source


def test_an_upload_may_name_its_mood_and_genre(studio_client, headers):
    """The end-to-end path the new controls drive."""
    track = upload(studio_client, headers, mood="calm", genre="jazz").json()

    assert track["mood"] == "calm"
    assert track["genre"] == "jazz"


def test_leaving_them_blank_still_uploads(studio_client, headers):
    """Both are optional. The modal must not turn "I am not sure" into a
    refused upload."""
    response = upload(studio_client, headers, mood="", genre="")

    assert response.status_code == 201, response.text
    assert response.json()["mood"] == "other"


def test_a_mood_the_server_does_not_know_falls_back_rather_than_failing(
    studio_client, headers
):
    """The closed list is deliberate. A stale or hand-edited option should land
    in `other`, not 422 an upload the user is entitled to make."""
    track = upload(studio_client, headers, mood="aggressive", genre="dubstep").json()

    assert track["mood"] == "other", "an unknown mood must not become a new bucket"
    assert track["genre"] == "other"
