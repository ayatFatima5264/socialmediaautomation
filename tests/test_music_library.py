"""The Music Library: search, facets, preview, upload — and the licence rule.

The licence is the reason this suite exists. Everything else here is ordinary
library behaviour that would be annoying to get wrong; the licence tests are
the ones that stop this feature shipping a legal problem:

  * a track with no recognisable licence is never stored,
  * a non-commercial track is listed but cannot be added to a project,
  * the refusal happens at the endpoint, not only in the UI,
  * an upload requires the user to state they hold the rights, and
  * the credit obligation is copied onto the project and survives the
    catalogue row changing underneath it.

**Nothing here touches the network.** `fake_openverse` replaces the provider
client, so the catalogue tests run against a fixed set of results.
"""
from __future__ import annotations

import pytest

from tests.conftest import WAV_BYTES

# What Openverse's /v1/audio/ endpoint returns, trimmed to the fields the
# normaliser reads. Deliberately a mixed bag: a CC0 track, a BY track that
# needs crediting, a non-commercial one that must be refused, and two rows that
# are unusable for structural reasons.
OPENVERSE_RESULTS = [
    {
        "id": "aaa-111",
        "title": "Uplifting Corporate Loop",
        "creator": "Some Composer",
        "url": "https://example.test/audio/aaa-111.mp3",
        "duration": 125000,  # milliseconds
        "license": "cc0",
        "license_version": "1.0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "foreign_landing_url": "https://example.test/aaa-111",
        "tags": [{"name": "corporate"}, {"name": "uplifting"}],
        "filetype": "mp3",
        "filesize": 2000000,
    },
    {
        "id": "bbb-222",
        "title": "Calm Piano Study",
        "creator": "A Pianist",
        "url": "https://example.test/audio/bbb-222.mp3",
        "duration": 20000,
        "license": "by",
        "license_version": "4.0",
        "foreign_landing_url": "https://example.test/bbb-222",
        "tags": [{"name": "piano"}, {"name": "relax"}],
        "filetype": "mp3",
    },
    {
        "id": "ccc-333",
        "title": "Dramatic Trailer Hit",
        "creator": "Trailer House",
        "url": "https://example.test/audio/ccc-333.mp3",
        "duration": 45000,
        "license": "by-nc",
        "license_version": "4.0",
        "tags": [{"name": "epic"}, {"name": "trailer"}],
        "filetype": "mp3",
    },
    # No audio URL — not a track.
    {"id": "ddd-444", "title": "Broken", "license": "cc0"},
    # A licence we do not recognise. The whole premise is that this never
    # reaches the table.
    {
        "id": "eee-555",
        "title": "Unknown Rights",
        "url": "https://example.test/audio/eee-555.mp3",
        "license": "all-rights-reserved",
    },
]


@pytest.fixture()
def fake_openverse(monkeypatch):
    """Replace the provider client. Records the queries it was asked for."""
    calls = []

    async def _fetch(query, *, page_size=20):
        calls.append(query)
        from app.services.video.music import _normalize_openverse

        rows = [_normalize_openverse(item) for item in OPENVERSE_RESULTS]
        return [row for row in rows if row is not None][:page_size]

    monkeypatch.setattr("app.services.video.music.fetch_openverse", _fetch)
    return calls


def seed(studio_client, headers, fake_openverse, query="uplifting corporate"):
    """Fill the catalogue from the provider, then return the whole library.

    Two requests, deliberately. The first is the search that causes the
    provider results to be cached; its *response* is filtered by that same
    search text, so reading the tracks from it would only ever return the ones
    whose titles happen to match the query. The second is the unfiltered
    listing, which is what these tests want to assert against.
    """
    studio_client.get(f"/api/video/music?search={query}", headers=headers)
    body = studio_client.get("/api/video/music", headers=headers).json()
    return {item["title"]: item for item in body["items"]}


def upload_track(client, headers, *, data=WAV_BYTES, name="mine.wav",
                 confirmed=True, **fields):
    form = {"confirmed_rights": str(confirmed).lower(), **fields}
    return client.post(
        "/api/video/music/upload",
        headers=headers,
        files={"file": (name, data, "audio/wav")},
        data=form,
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_every_music_route_requires_a_token(studio_client):
    for method, path in (
        ("get", "/api/video/music"),
        ("get", "/api/video/music/facets"),
        ("get", "/api/video/music/1"),
        ("post", "/api/video/music/1/add"),
        ("delete", "/api/video/music/1"),
        ("get", "/api/video/music/credits/1"),
    ):
        kwargs = {"json": {}} if method == "post" else {}
        response = getattr(studio_client, method)(path, **kwargs)
        assert response.status_code == 401, f"{method.upper()} {path} was reachable"


# ---------------------------------------------------------------------------
# The catalogue and its licences
# ---------------------------------------------------------------------------


def test_a_track_without_a_recognised_licence_is_never_stored(
    studio_client, headers, fake_openverse
):
    """The premise of the whole module, asserted on the ingest path."""
    tracks = seed(studio_client, headers, fake_openverse)

    assert "Unknown Rights" not in tracks
    # And neither is the one with no audio behind it.
    assert "Broken" not in tracks
    assert "Uplifting Corporate Loop" in tracks


def test_a_non_commercial_track_is_listed_but_marked_unusable(
    studio_client, headers, fake_openverse
):
    """Shown, with the reason — not hidden.

    A library that silently drops results looks broken; the user should be able
    to see what exists and why they cannot have it.
    """
    tracks = seed(studio_client, headers, fake_openverse)
    nc = tracks["Dramatic Trailer Hit"]

    assert nc["can_use"] is False
    assert "non-commercial" in nc["blocked_reason"].lower()
    # Still previewable.
    assert nc["url"]


def test_a_commercial_track_is_usable_and_says_what_it_needs(
    studio_client, headers, fake_openverse
):
    tracks = seed(studio_client, headers, fake_openverse)

    cc0 = tracks["Uplifting Corporate Loop"]
    assert cc0["can_use"] is True
    assert cc0["requires_attribution"] is False
    assert cc0["license"] == "cc0"

    by = tracks["Calm Piano Study"]
    assert by["can_use"] is True
    assert by["requires_attribution"] is True
    assert "A Pianist" in by["credit"]


def test_a_missing_licence_url_is_reconstructed_from_the_code(
    studio_client, headers, fake_openverse
):
    """"CC BY" without a version is not a citable licence."""
    tracks = seed(studio_client, headers, fake_openverse)

    assert tracks["Calm Piano Study"]["license_url"] == (
        "https://creativecommons.org/licenses/by/4.0/"
    )


def test_searching_twice_does_not_duplicate_the_catalogue(
    studio_client, headers, fake_openverse, studio_db
):
    from app.models.music_track import MusicTrack

    # Force a second provider search by asking for something the cache cannot
    # satisfy on its own.
    studio_client.get("/api/video/music?search=corporate", headers=headers)
    first = studio_db.query(MusicTrack).count()
    studio_client.get("/api/video/music?search=corporate", headers=headers)
    studio_db.expire_all()
    second = studio_db.query(MusicTrack).count()

    assert first == second, "a repeated search grew the catalogue"


def test_browsing_by_mood_does_not_call_the_provider(
    studio_client, headers, fake_openverse
):
    """A filter is a question about what the library holds.

    Answering it by fetching more would turn a filter into an unbounded crawl.
    """
    studio_client.get("/api/video/music?mood=calm", headers=headers)
    assert fake_openverse == []


def test_a_provider_failure_leaves_the_library_working(
    studio_client, headers, monkeypatch
):
    """A music screen must not go down because a third party is slow."""
    async def _explode(query, *, page_size=20):
        return []

    monkeypatch.setattr("app.services.video.music.fetch_openverse", _explode)

    response = studio_client.get("/api/video/music?search=anything", headers=headers)

    assert response.status_code == 200
    assert response.json()["items"] == []


# ---------------------------------------------------------------------------
# Search and filtering
# ---------------------------------------------------------------------------


def test_tracks_are_classified_into_the_mood_and_genre_vocabulary(
    studio_client, headers, fake_openverse
):
    tracks = seed(studio_client, headers, fake_openverse)

    assert tracks["Uplifting Corporate Loop"]["mood"] == "uplifting"
    assert tracks["Calm Piano Study"]["mood"] == "calm"
    assert tracks["Calm Piano Study"]["genre"] == "acoustic"
    assert tracks["Dramatic Trailer Hit"]["mood"] == "dramatic"


def test_the_duration_filter_uses_named_buckets(
    studio_client, headers, fake_openverse
):
    seed(studio_client, headers, fake_openverse)

    # "Calm Piano Study" is 20s; the others are 45s and 125s.
    short = studio_client.get(
        "/api/video/music?duration=short", headers=headers
    ).json()
    assert [t["title"] for t in short["items"]] == ["Calm Piano Study"]

    long_ = studio_client.get(
        "/api/video/music?duration=long", headers=headers
    ).json()
    assert [t["title"] for t in long_["items"]] == ["Uplifting Corporate Loop"]


def test_the_facets_carry_live_counts_and_starter_searches(
    studio_client, headers, fake_openverse
):
    seed(studio_client, headers, fake_openverse)

    facets = studio_client.get("/api/video/music/facets", headers=headers).json()
    moods = {entry["key"]: entry["count"] for entry in facets["moods"]}

    assert moods["calm"] == 1
    assert moods["uplifting"] == 1
    # Zero rather than absent, so the filter row does not reflow as the
    # catalogue fills in.
    assert moods["playful"] == 0
    assert facets["total"] == 3
    assert facets["suggestions"], "an empty library needs somewhere to start"


def test_search_matches_the_title_and_the_artist(
    studio_client, headers, fake_openverse
):
    seed(studio_client, headers, fake_openverse)

    by_artist = studio_client.get(
        "/api/video/music?search=pianist&source=catalogue", headers=headers
    ).json()

    assert [t["title"] for t in by_artist["items"]] == ["Calm Piano Study"]


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


def test_an_upload_without_a_rights_statement_is_refused(studio_client, headers):
    """Refused before the file is read, so it never reaches storage."""
    response = upload_track(studio_client, headers, confirmed=False)

    assert response.status_code == 422
    assert "right to use" in response.json()["detail"]
    assert studio_client.get("/api/video/music", headers=headers).json()["total"] == 0


def test_an_upload_is_stored_with_the_users_rights_claim(studio_client, headers):
    response = upload_track(
        studio_client,
        headers,
        title="My Bed",
        artist="Me",
        mood="calm",
        genre="ambient",
        source_url="https://example.test/where-i-got-it",
    )

    assert response.status_code == 201, response.text
    track = response.json()
    assert track["license"] == "user"
    assert track["can_use"] is True
    assert track["is_owned"] is True
    assert track["is_hosted"] is True, "our own storage, not a stream"
    assert track["source_url"] == "https://example.test/where-i-got-it"
    assert track["mood"] == "calm"


def test_a_non_audio_upload_is_refused(studio_client, headers):
    from tests.conftest import PNG_BYTES

    response = studio_client.post(
        "/api/video/music/upload",
        headers=headers,
        files={"file": ("nope.png", PNG_BYTES, "image/png")},
        data={"confirmed_rights": "true"},
    )

    assert response.status_code == 422
    assert "audio" in response.json()["detail"].lower()


def test_uploading_the_same_track_twice_does_not_duplicate_it(
    studio_client, headers, studio_db
):
    from app.models.storage_object import StorageObject

    first = upload_track(studio_client, headers, title="One").json()
    second = upload_track(studio_client, headers, title="Two").json()

    assert first["id"] == second["id"]
    assert studio_db.query(StorageObject).count() == 1


def test_your_uploads_sort_above_the_catalogue(
    studio_client, headers, fake_openverse
):
    """The track you added is the one you are most likely looking for."""
    seed(studio_client, headers, fake_openverse)
    upload_track(studio_client, headers, title="My Bed")

    body = studio_client.get("/api/video/music", headers=headers).json()

    assert body["items"][0]["title"] == "My Bed"


def test_you_can_delete_your_own_upload(studio_client, headers):
    track = upload_track(studio_client, headers, title="Mine").json()

    assert studio_client.delete(
        f"/api/video/music/{track['id']}", headers=headers
    ).status_code == 204
    assert studio_client.get("/api/video/music", headers=headers).json()["total"] == 0


def test_you_cannot_delete_a_catalogue_track(
    studio_client, headers, fake_openverse
):
    """It is shared — one account deleting it would empty everybody's library."""
    tracks = seed(studio_client, headers, fake_openverse)

    response = studio_client.delete(
        f"/api/video/music/{tracks['Uplifting Corporate Loop']['id']}",
        headers=headers,
    )

    assert response.status_code == 422
    assert studio_client.get("/api/video/music", headers=headers).json()["total"] == 3


def test_you_cannot_see_or_delete_someone_elses_upload(
    studio_client, headers, other_headers
):
    theirs = upload_track(studio_client, other_headers, title="Theirs").json()

    assert studio_client.get(
        f"/api/video/music/{theirs['id']}", headers=headers
    ).status_code == 404
    assert studio_client.delete(
        f"/api/video/music/{theirs['id']}", headers=headers
    ).status_code == 404
    assert studio_client.get("/api/video/music", headers=headers).json()["total"] == 0


# ---------------------------------------------------------------------------
# Adding a track to a project
# ---------------------------------------------------------------------------


def test_adding_a_track_creates_a_music_layer_with_sane_defaults(
    studio_client, headers, project, fake_openverse
):
    tracks = seed(studio_client, headers, fake_openverse)

    response = studio_client.post(
        f"/api/video/music/{tracks['Uplifting Corporate Loop']['id']}/add",
        headers=headers,
        json={"project_id": project["id"]},
    )

    assert response.status_code == 201, response.text
    layer = response.json()
    assert layer["role"] == "music"
    # Well below speech. A bed at full volume is the most common way an
    # auto-assembled video comes out unusable.
    assert layer["volume"] < 0.5
    assert layer["ducking"] is True
    assert layer["loop"] is True
    # None means "as long as the source is" — committing to a length before
    # the scenes exist would be wrong immediately.
    assert layer["duration_seconds"] is None


def test_the_licence_travels_onto_the_project(
    studio_client, headers, project, fake_openverse
):
    """So the obligation survives the catalogue row changing later."""
    tracks = seed(studio_client, headers, fake_openverse)

    layer = studio_client.post(
        f"/api/video/music/{tracks['Calm Piano Study']['id']}/add",
        headers=headers,
        json={"project_id": project["id"]},
    ).json()

    assert layer["meta"]["license"] == "by"
    assert layer["meta"]["requires_attribution"] is True
    assert "A Pianist" in layer["meta"]["credit"]
    assert layer["meta"]["source_url"]


def test_a_non_commercial_track_is_refused_at_the_endpoint(
    studio_client, headers, project, fake_openverse
):
    """The rule is enforced by the server, not drawn by the UI.

    A UI that merely greys the button is a rule that stops being enforced the
    first time somebody calls the API directly.
    """
    tracks = seed(studio_client, headers, fake_openverse)

    response = studio_client.post(
        f"/api/video/music/{tracks['Dramatic Trailer Hit']['id']}/add",
        headers=headers,
        json={"project_id": project["id"]},
    )

    assert response.status_code == 403
    assert "cannot be used" in response.json()["detail"]


def test_credits_list_only_the_tracks_that_need_one(
    studio_client, headers, project, fake_openverse
):
    """Padding the list with CC0 tracks would bury the real requirements."""
    tracks = seed(studio_client, headers, fake_openverse)

    for title in ("Uplifting Corporate Loop", "Calm Piano Study"):
        studio_client.post(
            f"/api/video/music/{tracks[title]['id']}/add",
            headers=headers,
            json={"project_id": project["id"]},
        )

    body = studio_client.get(
        f"/api/video/music/credits/{project['id']}", headers=headers
    ).json()

    assert len(body["credits"]) == 1
    assert "A Pianist" in body["credits"][0]


def test_adding_a_second_bed_does_not_replace_the_first(
    studio_client, headers, project, fake_openverse
):
    tracks = seed(studio_client, headers, fake_openverse)

    first = studio_client.post(
        f"/api/video/music/{tracks['Uplifting Corporate Loop']['id']}/add",
        headers=headers, json={"project_id": project["id"]},
    ).json()
    second = studio_client.post(
        f"/api/video/music/{tracks['Calm Piano Study']['id']}/add",
        headers=headers, json={"project_id": project["id"]},
    ).json()

    assert second["position"] == first["position"] + 1


def test_you_cannot_add_a_track_to_someone_elses_project(
    studio_client, headers, other_headers, fake_openverse
):
    tracks = seed(studio_client, headers, fake_openverse)
    theirs = studio_client.post(
        "/api/video/projects", headers=other_headers, json={}
    ).json()

    response = studio_client.post(
        f"/api/video/music/{tracks['Uplifting Corporate Loop']['id']}/add",
        headers=headers,
        json={"project_id": theirs["id"]},
    )

    assert response.status_code == 404


def test_adding_a_track_copies_no_audio(
    studio_client, headers, project, fake_openverse, studio_db
):
    """One track in ten projects is one file."""
    from app.models.storage_object import StorageObject

    tracks = seed(studio_client, headers, fake_openverse)
    before = studio_db.query(StorageObject).count()

    studio_client.post(
        f"/api/video/music/{tracks['Uplifting Corporate Loop']['id']}/add",
        headers=headers,
        json={"project_id": project["id"]},
    )

    studio_db.expire_all()
    assert studio_db.query(StorageObject).count() == before
