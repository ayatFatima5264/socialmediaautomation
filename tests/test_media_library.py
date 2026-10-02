"""The Media Library: search, filter, preview, reuse, delete — and dedupe.

What is worth testing here is what the library promises the user and what
nothing else in the suite covers:

  * **Duplicate storage does not happen.** The same bytes uploaded twice must
    produce one object and one row. This is the requirement the whole
    `checksum` column exists for, so it gets tested at the route, not only in
    the service.
  * **A file in use is not deleted by accident.** The guard is the difference
    between a library and a trap door.
  * **Reuse is not the same as deletion.** Attach and detach move a file in and
    out of a project without touching the file.
  * **One account never sees another's files.** Asserted on every read path
    rather than assumed from the query.
"""
from __future__ import annotations

from tests.conftest import PNG_BYTES, SRT_BYTES, WAV_BYTES, png_bytes


def upload(client, headers, *, data=PNG_BYTES, name="clip.png", kind="image",
           content_type="image/png", title=None, project_id=None):
    """Upload a file through the real endpoint."""
    form = {"kind": kind}
    if title:
        form["title"] = title
    if project_id:
        form["project_id"] = str(project_id)
    response = client.post(
        "/api/video/media/upload",
        headers=headers,
        files={"file": (name, data, content_type)},
        data=form,
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_every_media_route_requires_a_token(studio_client):
    """A route that forgot its dependency is invisible to service tests."""
    for method, path in (
        ("get", "/api/video/media"),
        ("get", "/api/video/media/uploads"),
        ("post", "/api/video/media/uploads/import"),
        ("patch", "/api/video/media/1"),
        ("post", "/api/video/media/1/attach?project_id=1"),
        ("post", "/api/video/media/1/detach"),
        ("delete", "/api/video/media/1"),
    ):
        kwargs = {"json": {}} if method in ("post", "patch") else {}
        response = getattr(studio_client, method)(path, **kwargs)
        assert response.status_code == 401, f"{method.upper()} {path} was reachable"


# ---------------------------------------------------------------------------
# Avoiding duplicate storage
# ---------------------------------------------------------------------------


def test_the_same_file_uploaded_twice_is_stored_once(studio_client, headers, studio_db):
    """The requirement the checksum column exists for."""
    from app.models.storage_object import StorageObject
    from app.models.video_asset import VideoAsset

    first = upload(studio_client, headers, title="Beach")
    second = upload(studio_client, headers, title="Beach again")

    assert second["id"] == first["id"], "a duplicate upload created a second row"

    # And, more importantly, a second *object*. A row that points at a
    # duplicated object is still a duplicated storage bill.
    assert studio_db.query(VideoAsset).count() == 1
    assert studio_db.query(StorageObject).count() == 1


def test_different_bytes_are_stored_separately(studio_client, headers):
    first = upload(studio_client, headers, data=png_bytes(32, 32), name="a.png")
    second = upload(studio_client, headers, data=png_bytes(48, 48), name="b.png")
    assert first["id"] != second["id"]


def test_the_same_bytes_under_a_different_kind_are_separate(studio_client, headers):
    """The same MP3 as a voice-over and as a music bed are two library items.

    The kind decides where the object lives and how the library groups it, so
    matching on the digest alone would merge two things the user thinks of as
    different.
    """
    audio = upload(
        studio_client, headers, data=WAV_BYTES, name="t.wav",
        kind="upload", content_type="audio/wav",
    )
    music = upload(
        studio_client, headers, data=WAV_BYTES, name="t.wav",
        kind="music", content_type="audio/wav",
    )
    assert audio["id"] != music["id"]


def test_one_users_file_is_not_reused_for_another(studio_client, headers, other_headers):
    """De-duplication is per account, deliberately.

    Sharing the object across users would make one person's delete take away
    another's file, and would leak that somebody else has it.
    """
    mine = upload(studio_client, headers)
    theirs = upload(studio_client, other_headers)
    assert mine["id"] != theirs["id"]


# ---------------------------------------------------------------------------
# Listing, searching and filtering
# ---------------------------------------------------------------------------


def test_the_library_lists_only_your_own_files(studio_client, headers, other_headers):
    upload(studio_client, headers, title="Mine")
    upload(studio_client, other_headers, data=png_bytes(48, 48), title="Theirs")

    body = studio_client.get("/api/video/media", headers=headers).json()

    assert [item["title"] for item in body["items"]] == ["Mine"]
    assert body["total"] == 1


def test_search_matches_the_title_and_the_original_filename(studio_client, headers):
    upload(studio_client, headers, name="IMG_4821.png", title="Sunset over the bay")
    upload(studio_client, headers, data=png_bytes(48, 48), name="other.png", title="Logo")

    by_title = studio_client.get(
        "/api/video/media?search=sunset", headers=headers
    ).json()
    assert [item["title"] for item in by_title["items"]] == ["Sunset over the bay"]

    # People look for "the one called beach" and for "IMG_4821" — only one of
    # those is the title.
    by_filename = studio_client.get(
        "/api/video/media?search=img_4821", headers=headers
    ).json()
    assert [item["title"] for item in by_filename["items"]] == ["Sunset over the bay"]


def test_the_filter_tabs_map_to_storage_kinds(studio_client, headers):
    upload(studio_client, headers, kind="image", name="a.png")
    upload(studio_client, headers, kind="subtitle", name="a.srt",
           data=SRT_BYTES, content_type="application/x-subrip")

    images = studio_client.get("/api/video/media?filter=image", headers=headers).json()
    assert {item["kind"] for item in images["items"]} == {"image"}

    subtitles = studio_client.get(
        "/api/video/media?filter=subtitle", headers=headers
    ).json()
    assert {item["kind"] for item in subtitles["items"]} == {"subtitle"}


def test_an_unknown_filter_shows_the_library_rather_than_nothing(studio_client, headers):
    """A stale bookmark should not look like data loss."""
    upload(studio_client, headers)

    body = studio_client.get(
        "/api/video/media?filter=nonsense", headers=headers
    ).json()

    assert len(body["items"]) == 1


def test_the_filter_bar_carries_live_counts(studio_client, headers):
    upload(studio_client, headers, kind="image", name="a.png")
    upload(studio_client, headers, kind="subtitle", name="a.srt",
           data=SRT_BYTES, content_type="application/x-subrip")

    body = studio_client.get("/api/video/media", headers=headers).json()
    counts = {entry["key"]: entry["count"] for entry in body["filters"]}

    assert counts["all"] == 2
    assert counts["image"] == 1
    assert counts["subtitle"] == 1
    # Present at zero rather than missing, so the tab row is a stable shape.
    assert counts["music"] == 0


def test_the_total_reflects_the_filters_but_storage_does_not(studio_client, headers):
    upload(studio_client, headers, kind="image", name="a.png")
    upload(studio_client, headers, kind="subtitle", name="a.srt",
           data=SRT_BYTES, content_type="application/x-subrip")

    body = studio_client.get("/api/video/media?filter=image", headers=headers).json()

    assert body["total"] == 1, "the total must match what the filter shows"
    # "How much am I using" is not changed by a filter.
    assert body["storage_bytes"] == len(PNG_BYTES) + len(SRT_BYTES)


def test_paging_is_stable_and_reports_the_unpaged_total(studio_client, headers):
    for index in range(5):
        upload(studio_client, headers, data=png_bytes(32 + index * 8, 32),
               name=f"{index}.png", title=f"Clip {index}")

    first = studio_client.get(
        "/api/video/media?limit=2&offset=0", headers=headers
    ).json()
    second = studio_client.get(
        "/api/video/media?limit=2&offset=2", headers=headers
    ).json()

    assert first["total"] == 5 and second["total"] == 5
    assert len(first["items"]) == 2 and len(second["items"]) == 2
    # No overlap: the sort has an id tiebreak, so equal timestamps cannot
    # reshuffle the pages.
    assert not {i["id"] for i in first["items"]} & {i["id"] for i in second["items"]}


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


def test_every_item_carries_a_playable_url(studio_client, headers):
    item = upload(studio_client, headers, data=WAV_BYTES, name="t.wav",
                  kind="upload", content_type="audio/wav")

    assert item["url"].endswith(
        f"/api/storage/o/{item['url'].rsplit('/', 1)[-1]}"
    )

    # And it actually serves the bytes, which is what "preview" means.
    token = item["url"].rsplit("/", 1)[-1]
    response = studio_client.get(f"/api/storage/o/{token}")
    assert response.status_code == 200
    assert response.content == WAV_BYTES


def test_probing_records_the_dimensions_so_the_ui_need_not_decode(studio_client, headers):
    """Measured on ingest, not claimed by the client.

    The timeline lays a clip out from these numbers, so they have to come from
    the file itself — a width the uploader could assert is a width that can be
    wrong.
    """
    item = upload(studio_client, headers, data=png_bytes(64, 48), name="wide.png")

    assert item["width"] == 64
    assert item["height"] == 48


# ---------------------------------------------------------------------------
# Reuse
# ---------------------------------------------------------------------------


def test_attach_makes_a_file_available_in_a_project(studio_client, headers, project):
    item = upload(studio_client, headers)

    attached = studio_client.post(
        f"/api/video/media/{item['id']}/attach?project_id={project['id']}",
        headers=headers,
    ).json()

    assert attached["project_id"] == project["id"]


def test_detach_keeps_the_file(studio_client, headers, project):
    item = upload(studio_client, headers)
    studio_client.post(
        f"/api/video/media/{item['id']}/attach?project_id={project['id']}",
        headers=headers,
    )

    detached = studio_client.post(
        f"/api/video/media/{item['id']}/detach", headers=headers
    ).json()

    assert detached["project_id"] is None
    # Still in the library. "Remove from this project" is not "throw away".
    body = studio_client.get("/api/video/media", headers=headers).json()
    assert [i["id"] for i in body["items"]] == [item["id"]]


def test_you_cannot_attach_a_file_to_someone_elses_project(
    studio_client, headers, other_headers
):
    item = upload(studio_client, headers)
    theirs = studio_client.post(
        "/api/video/projects", headers=other_headers, json={}
    ).json()

    response = studio_client.post(
        f"/api/video/media/{item['id']}/attach?project_id={theirs['id']}",
        headers=headers,
    )

    # 404, not 403: telling the two apart is what makes an id space
    # enumerable.
    assert response.status_code == 404


def test_renaming_keeps_the_original_filename_searchable(studio_client, headers):
    item = upload(studio_client, headers, name="IMG_4821.png", title="IMG_4821")

    renamed = studio_client.patch(
        f"/api/video/media/{item['id']}",
        headers=headers,
        json={"title": "Sunset over the bay"},
    ).json()

    assert renamed["title"] == "Sunset over the bay"
    assert renamed["filename"] == "IMG_4821.png"

    found = studio_client.get(
        "/api/video/media?search=img_4821", headers=headers
    ).json()
    assert len(found["items"]) == 1


# ---------------------------------------------------------------------------
# Usage and deletion
# ---------------------------------------------------------------------------


def test_an_unused_file_reports_no_usage_and_deletes(studio_client, headers):
    item = upload(studio_client, headers)
    assert item["usage"] == []

    assert studio_client.delete(
        f"/api/video/media/{item['id']}", headers=headers
    ).status_code == 204
    assert studio_client.get("/api/video/media", headers=headers).json()["total"] == 0


def test_a_file_a_project_is_using_is_not_deleted_by_accident(
    studio_client, headers, project, studio_db
):
    """The guard that makes this a library rather than a trap door."""
    from app.models.video_project import VideoProject

    item = upload(studio_client, headers, title="Cover")

    row = studio_db.get(VideoProject, project["id"])
    row.thumbnail_asset_id = item["id"]
    studio_db.commit()

    response = studio_client.delete(f"/api/video/media/{item['id']}", headers=headers)

    assert response.status_code == 409
    # The message must name what is using it — "something is using this" is not
    # enough to decide with.
    assert project["name"] in response.json()["detail"]

    # And the file is still there.
    assert studio_client.get("/api/video/media", headers=headers).json()["total"] == 1


def test_usage_is_reported_on_the_listing(studio_client, headers, project, studio_db):
    from app.models.video_project import VideoProject

    item = upload(studio_client, headers)
    row = studio_db.get(VideoProject, project["id"])
    row.thumbnail_asset_id = item["id"]
    studio_db.commit()

    body = studio_client.get("/api/video/media", headers=headers).json()
    usage = body["items"][0]["usage"]

    assert usage == [
        {
            "project_id": project["id"],
            "project_name": project["name"],
            "role": "thumbnail",
        }
    ]


def test_force_deletes_a_file_that_is_in_use(studio_client, headers, project, studio_db):
    """Once the user has seen the list and said yes anyway."""
    from app.models.video_project import VideoProject

    item = upload(studio_client, headers)
    row = studio_db.get(VideoProject, project["id"])
    row.thumbnail_asset_id = item["id"]
    studio_db.commit()

    response = studio_client.delete(
        f"/api/video/media/{item['id']}?force=true", headers=headers
    )

    assert response.status_code == 204
    # The project survives with an empty thumbnail — a hole to fill, not
    # structure that vanished.
    studio_db.expire_all()
    assert studio_db.get(VideoProject, project["id"]).thumbnail_asset_id is None


def test_you_cannot_delete_someone_elses_file(studio_client, headers, other_headers):
    theirs = upload(studio_client, other_headers)

    response = studio_client.delete(
        f"/api/video/media/{theirs['id']}", headers=headers
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# The rest of AutoSocial's media library
# ---------------------------------------------------------------------------


def make_upload(studio_client, headers) -> dict:
    """Put an image in `media_assets` the way the post composer does."""
    response = studio_client.post(
        "/api/media",
        headers=headers,
        files={"file": ("photo.png", PNG_BYTES, "image/png")},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def test_composer_uploads_are_listed_as_their_own_source(studio_client, headers):
    make_upload(studio_client, headers)

    body = studio_client.get("/api/video/media/uploads", headers=headers).json()

    assert body["total"] == 1
    assert body["items"][0]["filename"] == "photo.png"
    # Not yet in Video Studio.
    assert body["items"][0]["imported_asset_id"] is None
    # And they are not in the studio library either — importing is a step.
    assert studio_client.get("/api/video/media", headers=headers).json()["total"] == 0


def test_importing_a_composer_upload_brings_it_into_the_studio(studio_client, headers):
    make_upload(studio_client, headers)
    uploads = studio_client.get("/api/video/media/uploads", headers=headers).json()
    media_id = uploads["items"][0]["id"]

    imported = studio_client.post(
        "/api/video/media/uploads/import", headers=headers, json={"media_id": media_id}
    ).json()

    assert imported["kind"] == "image"
    assert studio_client.get("/api/video/media", headers=headers).json()["total"] == 1

    # The listing now says so, so the button can read "In your library".
    again = studio_client.get("/api/video/media/uploads", headers=headers).json()
    assert again["items"][0]["imported_asset_id"] == imported["id"]


def test_importing_twice_does_not_store_twice(studio_client, headers, studio_db):
    from app.models.storage_object import StorageObject

    make_upload(studio_client, headers)
    uploads = studio_client.get("/api/video/media/uploads", headers=headers).json()
    media_id = uploads["items"][0]["id"]

    first = studio_client.post(
        "/api/video/media/uploads/import", headers=headers, json={"media_id": media_id}
    ).json()
    second = studio_client.post(
        "/api/video/media/uploads/import", headers=headers, json={"media_id": media_id}
    ).json()

    assert first["id"] == second["id"]
    assert studio_db.query(StorageObject).count() == 1


def test_importing_leaves_the_composer_upload_alone(studio_client, headers):
    """A scheduled post may still be pointing at its URL."""
    original = make_upload(studio_client, headers)
    uploads = studio_client.get("/api/video/media/uploads", headers=headers).json()

    studio_client.post(
        "/api/video/media/uploads/import",
        headers=headers,
        json={"media_id": uploads["items"][0]["id"]},
    )

    still_there = studio_client.get(f"/api/media/{original['token']}")
    assert still_there.status_code == 200


def test_you_cannot_import_someone_elses_upload(studio_client, headers, other_headers):
    make_upload(studio_client, other_headers)
    theirs = studio_client.get(
        "/api/video/media/uploads", headers=other_headers
    ).json()["items"][0]

    response = studio_client.post(
        "/api/video/media/uploads/import",
        headers=headers,
        json={"media_id": theirs["id"]},
    )

    assert response.status_code == 404


def test_the_words_of_a_search_are_matched_in_any_order(studio_client, headers):
    """One LIKE over the whole phrase needs the words adjacent and in order, so
    "reel demo" missed "QA Demo Reel" — and nobody remembers their own file
    names in order."""
    upload(studio_client, headers, name="clip.png", title="QA Demo Reel")

    forwards = studio_client.get(
        "/api/video/media?search=Demo%20Reel", headers=headers
    ).json()
    backwards = studio_client.get(
        "/api/video/media?search=Reel%20Demo", headers=headers
    ).json()

    assert forwards["total"] >= 1
    assert backwards["total"] == forwards["total"]


def test_every_word_of_a_media_search_has_to_match(studio_client, headers):
    """Two words are narrower than one, not broader."""
    upload(studio_client, headers, name="clip.png", title="QA Demo Reel")

    body = studio_client.get(
        "/api/video/media?search=Reel%20nonexistentword", headers=headers
    ).json()

    assert body["total"] == 0

# ---------------------------------------------------------------------------
# An unnamed upload is filed by what it is, not by a default
# ---------------------------------------------------------------------------


def upload_unnamed(client, headers, *, data=PNG_BYTES, name="photo.png",
                   content_type="image/png", title=None):
    """Upload through the real endpoint with no `kind` in the form at all.

    The Media Library's upload control sends a file and nothing else — there is
    no "what is this for" picker on that screen — so this is what every file a
    user drops into their library actually looks like on the wire.
    """
    form = {}
    if title:
        form["title"] = title
    response = client.post(
        "/api/video/media/upload",
        headers=headers,
        files={"file": (name, data, content_type)},
        data=form,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_an_unnamed_png_is_filed_as_an_image(studio_client, headers):
    """The bug: the form defaulted `kind` to the string `upload`, so a photo
    dropped into the library was stored as `upload` and appeared under no tab
    at all — and under Audio."""
    item = upload_unnamed(studio_client, headers)

    assert item["kind"] == "image"
    assert item["content_type"] == "image/png"

    images = studio_client.get(
        "/api/video/media?filter=image", headers=headers
    ).json()
    assert [row["id"] for row in images["items"]] == [item["id"]]

    audio = studio_client.get(
        "/api/video/media?filter=audio", headers=headers
    ).json()
    assert audio["items"] == [], "a photo showed up under the Audio tab"


def test_an_unnamed_mp4_is_filed_as_a_video(studio_client, headers, small_video):
    item = upload_unnamed(
        studio_client, headers,
        data=small_video, name="clip.mp4", content_type="video/mp4",
    )

    assert item["kind"] == "video"

    videos = studio_client.get(
        "/api/video/media?filter=video", headers=headers
    ).json()
    assert [row["id"] for row in videos["items"]] == [item["id"]]


def test_an_unnamed_audio_file_is_filed_as_an_upload(studio_client, headers):
    """`upload` is the right answer for audio, and is left alone.

    The storage vocabulary has no `audio` kind, and inventing one would mean
    rewriting every stored object's key. The Audio tab matches on content type
    instead, so the file is still findable under the tab that matters.
    """
    item = upload_unnamed(
        studio_client, headers,
        data=WAV_BYTES, name="take.wav", content_type="audio/wav",
    )
    assert item["kind"] == "upload"

    audio = studio_client.get(
        "/api/video/media?filter=audio", headers=headers
    ).json()
    assert [row["id"] for row in audio["items"]] == [item["id"]]


def test_only_images_and_videos_are_inferred_anything_else_stays_an_upload():
    """`subtitle` means a parsed cue list, not a raw .srt, so filing an
    unclassifiable file as one would put it in the editor's track picker where
    it cannot load. Conservative is correct here, and it is checked on the
    function rather than through the route because the route rejects most of
    these files anyway — an SRT arrives with `kind=subtitle`, which is
    explicit, and the inferrer is never asked."""
    from app.services.video.assets import kind_for_content

    assert kind_for_content("image/png") == "image"
    assert kind_for_content("image/jpeg") == "image"
    assert kind_for_content("video/mp4") == "video"
    assert kind_for_content("video/quicktime") == "video"

    # Extension fallback: browsers send nothing for an .srt, and plenty of
    # desktop clients send octet-stream for anything unusual.
    assert kind_for_content("", "clip.mp4") == "video"
    assert kind_for_content("application/octet-stream", "photo.JPG") == "image"

    # Everything else keeps the catch-all.
    assert kind_for_content("audio/wav") == "upload"
    assert kind_for_content("application/x-subrip", "captions.srt") == "upload"
    assert kind_for_content("text/vtt") == "upload"
    assert kind_for_content("application/octet-stream") == "upload"
    assert kind_for_content("") == "upload"


def test_an_explicit_kind_is_still_believed(studio_client, headers):
    """The studios know what they are making and say so — an MP3 that is a
    voice-over must stay a voice-over, not be re-filed as a plain upload."""
    item = upload(
        studio_client, headers,
        data=WAV_BYTES, name="vo.wav", content_type="audio/wav", kind="voice",
    )
    assert item["kind"] == "voice"

    voice_tab = studio_client.get(
        "/api/video/media?filter=voice", headers=headers
    ).json()
    assert [row["id"] for row in voice_tab["items"]] == [item["id"]]


def test_an_unknown_kind_is_refused_rather_than_silently_replaced(studio_client, headers):
    """`build_key` falls an unknown kind back to `upload`, so accepting one
    here would store the file under a name that is not in the vocabulary while
    reporting the caller's string back in the response."""
    response = studio_client.post(
        "/api/video/media/upload",
        headers=headers,
        files={"file": ("photo.png", PNG_BYTES, "image/png")},
        data={"kind": "banana"},
    )

    assert response.status_code == 422, response.text
    assert "banana" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Rows that are already in the database
# ---------------------------------------------------------------------------


def test_a_photo_stored_under_the_old_default_still_shows_under_images(
    studio_client, headers, studio_db
):
    """The filter matches on content type as well as kind.

    The 0004 migration re-files the obvious rows, but a deployment that has not
    run it yet — and anything arriving through another path — still has files
    stored as `kind='upload'` that are plainly images. Those must be findable
    now, not only after a migration.
    """
    from app.models.video_asset import VideoAsset

    item = upload(studio_client, headers, kind="upload", name="legacy.png")
    studio_db.execute(
        VideoAsset.__table__.update()
        .where(VideoAsset.id == item["id"])
        .values(kind="upload")
    )
    studio_db.commit()

    images = studio_client.get(
        "/api/video/media?filter=image", headers=headers
    ).json()
    assert [row["id"] for row in images["items"]] == [item["id"]]

    # And it must not also appear under Audio, which is where it used to sit.
    audio = studio_client.get(
        "/api/video/media?filter=audio", headers=headers
    ).json()
    assert audio["items"] == []


def test_the_filter_counts_agree_with_what_the_filter_returns(studio_client, headers):
    """A count that disagrees with the list it labels is worse than no count.

    The tabs are unions of kinds and content types, so this is the only place
    that catches a row being counted into one tab and listed in another.
    """
    upload_unnamed(studio_client, headers, name="a.png", title="A")
    upload_unnamed(
        studio_client, headers,
        data=png_bytes(48, 48), name="b.png", title="B",
    )
    upload(
        studio_client, headers, data=WAV_BYTES, name="vo.wav",
        content_type="audio/wav", kind="voice",
    )
    upload(
        studio_client, headers, data=SRT_BYTES, name="a.srt",
        content_type="application/x-subrip", kind="subtitle",
    )

    body = studio_client.get("/api/video/media", headers=headers).json()
    counts = {entry["key"]: entry["count"] for entry in body["filters"]}

    for key in counts:
        if key == "all":
            continue
        listed = studio_client.get(
            f"/api/video/media?filter={key}", headers=headers
        ).json()
        assert listed["total"] == counts[key], (
            f"the {key} tab says {counts[key]} but returns {listed['total']}"
        )
        assert listed["total"] == len(listed["items"]), key

    # A voice-over is in the Audio tab and the Voice-over tab, so the tabs do
    # not sum to "All" — and must not be made to.
    assert counts["voice"] == 1
    assert counts["audio"] == 1
    assert counts["all"] == 4
