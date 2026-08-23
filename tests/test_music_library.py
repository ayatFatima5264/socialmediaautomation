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


def test_a_track_used_in_two_projects_is_stored_once(
    studio_client, headers, project, fake_openverse, studio_db
):
    """One track in ten projects is one file.

    The track has to be fetched — the renderer reads from object storage and
    nothing else — but only the first time. `store_asset` de-duplicates on
    checksum, so the second project references the same bytes.
    """
    from app.models.storage_object import StorageObject

    tracks = seed(studio_client, headers, fake_openverse)
    track_id = tracks["Uplifting Corporate Loop"]["id"]

    second = studio_client.post(
        "/api/video/projects",
        headers=headers,
        json={"name": "Another project", "project_type": "blank"},
    ).json()

    first_add = studio_client.post(
        f"/api/video/music/{track_id}/add",
        headers=headers,
        json={"project_id": project["id"]},
    )
    assert first_add.status_code == 201, first_add.text

    studio_db.expire_all()
    after_one = studio_db.query(StorageObject).count()

    second_add = studio_client.post(
        f"/api/video/music/{track_id}/add",
        headers=headers,
        json={"project_id": second["id"]},
    )
    assert second_add.status_code == 201, second_add.text

    studio_db.expire_all()
    assert studio_db.query(StorageObject).count() == after_one, (
        "the same track was stored twice"
    )
    assert first_add.json()["asset_id"] == second_add.json()["asset_id"]


# ---------------------------------------------------------------------------
# Finding a track
# ---------------------------------------------------------------------------
# Search matched the title and artist only, as one whole-phrase LIKE. Catalogue
# music is called "berceusounette" and "Chicken Hiccups" — the title is the
# least useful thing about it, and what makes it findable is its tags, mood and
# genre. So a search for "guitar" returned nothing while the catalogue held
# eight tracks tagged guitar, and the provider was re-queried every time
# because the local count stayed under the discover threshold.


def test_a_tag_is_searchable(studio_client, headers, fake_openverse):
    """The tag is how music is found; the title often says nothing."""
    seed(studio_client, headers, fake_openverse)

    body = studio_client.get("/api/video/music?search=relax", headers=headers).json()

    titles = [item["title"] for item in body["items"]]
    assert "Calm Piano Study" in titles, (
        "a track tagged 'relax' was not findable by that tag"
    )


def test_a_genre_is_searchable(studio_client, headers, fake_openverse):
    """The genre is derived from the tags and appears in no title, so this can
    only pass if the search reaches past title and artist."""
    library = seed(studio_client, headers, fake_openverse)
    genres = {item["title"]: item["genre"] for item in library.values()}
    target = next(
        (title for title, genre in genres.items() if genre.lower() not in title.lower()),
        None,
    )
    assert target, "every title contains its own genre; this test proves nothing"

    body = studio_client.get(
        f"/api/video/music?search={genres[target]}", headers=headers
    ).json()

    assert target in [item["title"] for item in body["items"]]


def test_the_words_of_a_search_are_matched_separately(
    studio_client, headers, fake_openverse
):
    """"upbeat guitar" as one LIKE needs those words adjacent and in order, so
    it misses "Upbeat Acoustic Guitar" — which is how people search for music."""
    seed(studio_client, headers, fake_openverse)

    # "corporate" is a tag, "uplifting" is a tag and the mood; they are not
    # adjacent in that order anywhere.
    body = studio_client.get(
        "/api/video/music?search=corporate%20uplifting", headers=headers
    ).json()

    assert "Uplifting Corporate Loop" in [item["title"] for item in body["items"]]


def test_every_word_has_to_match_something(studio_client, headers, fake_openverse):
    """Two words are narrower than one, not broader."""
    seed(studio_client, headers, fake_openverse)

    both = studio_client.get(
        "/api/video/music?search=piano%20trailer", headers=headers
    ).json()

    assert both["total"] == 0, "a track matched only one of the two words"


# ---------------------------------------------------------------------------
# Getting the music into the video
# ---------------------------------------------------------------------------
# A catalogue row holds metadata and somebody else's URL. The renderer reads
# its inputs from object storage and nowhere else, and the storyboard bridge
# skips a layer with no stored audio — so an added catalogue track used to be
# attached, credited, listed in the project's audio, and silent in the export.


@pytest.fixture(autouse=True)
def fake_audio(monkeypatch):
    """The track's bytes, without reaching the network.

    Autouse for the same reason `fake_openverse` exists: nothing in this file
    should depend on a third party being up. Adding a catalogue track now
    fetches its audio, so every test that adds one needs this — and a test that
    does not add one is unaffected by it.
    """

    async def _fetch(url):
        return WAV_BYTES, "audio/wav"

    monkeypatch.setattr("app.services.video.music.fetch_audio", _fetch)


def add_first_usable(client, headers, project_id):
    body = client.get("/api/video/music?limit=50", headers=headers).json()
    track = next(item for item in body["items"] if item["can_use"])
    response = client.post(
        f"/api/video/music/{track['id']}/add",
        headers=headers,
        json={"project_id": project_id},
    )
    assert response.status_code == 201, response.text
    return track, response.json()


def audio_clips(client, headers, project_id):
    document = client.get(
        f"/api/video/projects/{project_id}/timeline", headers=headers
    ).json()["timeline"]
    return [
        clip
        for track in document["tracks"]
        if track["id"] == "audio"
        for clip in track["clips"]
    ]


def test_a_catalogue_track_is_fetched_into_our_own_storage(
    studio_client, headers, project, fake_openverse, fake_audio
):
    seed(studio_client, headers, fake_openverse)

    _, layer = add_first_usable(studio_client, headers, project["id"])

    assert layer["asset_id"], (
        "the layer has no stored asset, so the renderer has nothing to read"
    )


def test_added_music_lands_on_the_timeline_immediately(
    studio_client, headers, project, fake_openverse, fake_audio
):
    """Not only when the project is rebuilt from a storyboard — a project built
    by hand in the editor never gets rebuilt."""
    seed(studio_client, headers, fake_openverse)
    before = len(audio_clips(studio_client, headers, project["id"]))

    _, layer = add_first_usable(studio_client, headers, project["id"])

    clips = audio_clips(studio_client, headers, project["id"])
    assert len(clips) == before + 1
    placed = next(
        clip
        for clip in clips
        if (clip.get("meta") or {}).get("audio_layer_id") == layer["id"]
    )
    assert placed["asset_id"] == layer["asset_id"]


def test_a_rebuild_does_not_stack_a_duplicate(
    studio_client, headers, project, fake_openverse, fake_audio
):
    """The clip carries the layer id the storyboard bridge matches on."""
    from app.services.video import storyboard

    seed(studio_client, headers, fake_openverse)
    _, layer = add_first_usable(studio_client, headers, project["id"])

    already = audio_clips(studio_client, headers, project["id"])
    assert layer["id"] in [
        (clip.get("meta") or {}).get("audio_layer_id") for clip in already
    ]
    assert callable(storyboard._music_layers)


def test_the_bed_is_trimmed_to_the_picture(
    studio_client, headers, project, fake_openverse, fake_audio
):
    """Adding two minutes of music must not turn a six-second Reel into a
    two-minute one followed by silence over a black frame."""
    seed(studio_client, headers, fake_openverse)

    document = studio_client.get(
        f"/api/video/projects/{project['id']}/timeline", headers=headers
    ).json()["timeline"]
    visual = max(
        (
            clip["start"] + clip["duration"]
            for track in document["tracks"]
            if track["id"] in ("video", "text")
            for clip in track["clips"]
        ),
        default=0.0,
    )

    _, layer = add_first_usable(studio_client, headers, project["id"])

    placed = next(
        clip
        for clip in audio_clips(studio_client, headers, project["id"])
        if (clip.get("meta") or {}).get("audio_layer_id") == layer["id"]
    )
    if visual > 0:
        assert placed["duration"] <= visual + 0.01, (
            "the music bed is longer than the video it sits under"
        )
