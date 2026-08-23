"""Video templates: the built-in library, preview, and saving your own.

`test_video_api.py` covers that the system set is seeded and categorised. What
is tested here is the part a user can change:

  * **A template stores configuration, not a video.** Saving one from a project
    must copy the canvas, the caption style and the shape of the scenes — and
    must NOT copy the script, the media, or a timeline full of ids that mean
    nothing in a different project. This is the requirement most easily got
    wrong, because copying everything looks like it works until the second
    project made from the template turns out to be a duplicate of the first.
  * **Ownership.** A saved template is private; a built-in one cannot be
    deleted by anybody.
  * **Using a template makes a real project**, and the two are then unrelated.
"""
from __future__ import annotations


def save_template(client, headers, project_id, **body):
    payload = {"project_id": project_id, "name": "My Setup", **body}
    return client.post("/api/video/templates", headers=headers, json=payload)


def build_project(client, headers, **body):
    response = client.post("/api/video/projects", headers=headers, json=body or {})
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


def test_a_template_can_be_opened_for_preview(studio_client, headers):
    """"Preview" shows the storyboard, which is what the choice turns on."""
    body = studio_client.get(
        "/api/video/templates/listicle_shorts", headers=headers
    ).json()

    assert body["name"] == "Top 5 List"
    assert [scene["title"] for scene in body["scenes"]][:2] == ["Hook", "Point 1"]
    assert body["subtitle_style"], "a template without a caption style is not one"
    assert body["layout"]["safe_area"], "the safe area is what keeps text off the UI"


def test_a_vertical_template_keeps_text_clear_of_the_platform_ui(
    studio_client, headers
):
    """TikTok's caption rail covers the bottom fifth of the frame."""
    body = studio_client.get(
        "/api/video/templates/tiktok_hook", headers=headers
    ).json()

    safe = body["layout"]["safe_area"]
    assert safe["bottom"] >= 0.2
    assert safe["right"] >= 0.15


def test_an_unknown_template_is_a_404(studio_client, headers):
    assert studio_client.get(
        "/api/video/templates/no-such-thing", headers=headers
    ).status_code == 404


# ---------------------------------------------------------------------------
# Using one
# ---------------------------------------------------------------------------


def test_using_a_template_builds_a_project_with_its_canvas_and_scenes(
    studio_client, headers
):
    project = build_project(
        studio_client, headers, template_key="listicle_shorts", project_type="blank"
    )

    assert project["template_key"] == "listicle_shorts"
    assert project["aspect_ratio"] == "9:16"
    assert project["scene_count"] == 7


def test_a_project_survives_its_template_being_deleted(studio_client, headers):
    """`template_key` records where a project came from. It is not a link."""
    source = build_project(studio_client, headers)
    saved = save_template(studio_client, headers, source["id"], name="Throwaway").json()

    made = build_project(studio_client, headers, template_key=saved["key"])
    studio_client.delete(f"/api/video/templates/{saved['key']}", headers=headers)

    still_there = studio_client.get(
        f"/api/video/projects/{made['id']}", headers=headers
    )
    assert still_there.status_code == 200
    assert still_there.json()["template_key"] == saved["key"]


# ---------------------------------------------------------------------------
# Saving your own
# ---------------------------------------------------------------------------


def test_saving_a_template_captures_the_setup_but_not_the_content(
    studio_client, headers, studio_db
):
    """The requirement that makes a template a template.

    Copying the script would make every project built from it a duplicate of
    the one it was saved from.
    """
    from app.models.video_scene import VideoScene

    project = build_project(studio_client, headers, platform="tiktok")

    studio_db.add_all([
        VideoScene(
            project_id=project["id"],
            position=index,
            title=title,
            text="Words the user wrote and does not want repeated.",
            duration_seconds=4.0,
            transition="fade",
        )
        for index, title in enumerate(("Hook", "Middle", "End"))
    ])
    studio_db.commit()

    saved = save_template(
        studio_client, headers, project["id"], name="My TikTok Setup"
    ).json()

    # The shape is kept…
    assert [scene["title"] for scene in saved["scenes"]] == ["Hook", "Middle", "End"]
    assert all(scene["duration_seconds"] == 4.0 for scene in saved["scenes"])
    assert saved["aspect_ratio"] == "9:16"
    assert saved["platform"] == "tiktok"

    # …and the words are not.
    assert all(scene["text"] == "" for scene in saved["scenes"])


def test_a_saved_template_carries_no_timeline_from_its_project(
    studio_client, headers, studio_db
):
    """A timeline references this project's clips by id.

    Carrying those ids into a template would produce new projects whose
    timeline points at nothing.
    """
    from app.models.video_template import VideoTemplate

    project = build_project(studio_client, headers)
    studio_client.patch(
        f"/api/video/projects/{project['id']}",
        headers=headers,
        json={"timeline": {"version": 1, "tracks": [
            {"id": "video", "kind": "video", "label": "Video",
             "clips": [{"id": "clip-1", "asset_id": 99}]},
        ]}},
    )

    saved = save_template(studio_client, headers, project["id"]).json()

    row = studio_db.query(VideoTemplate).filter_by(key=saved["key"]).one()
    clips = [
        clip
        for track in row.definition["timeline"]["tracks"]
        for clip in track["clips"]
    ]
    assert clips == [], "the template carried the project's clips"


def test_scenes_can_be_left_out_of_a_saved_template(studio_client, headers, studio_db):
    from app.models.video_scene import VideoScene

    project = build_project(studio_client, headers)
    studio_db.add(
        VideoScene(project_id=project["id"], position=0, title="One", duration_seconds=5.0)
    )
    studio_db.commit()

    saved = save_template(
        studio_client, headers, project["id"], include_scenes=False
    ).json()

    assert saved["scenes"] == []


def test_a_saved_template_appears_in_your_library_and_sorts_first(
    studio_client, headers
):
    project = build_project(studio_client, headers)
    save_template(studio_client, headers, project["id"], name="Mine").json()

    body = studio_client.get("/api/video/templates", headers=headers).json()

    assert body["templates"][0]["name"] == "Mine"
    assert body["templates"][0]["is_system"] is False
    # The built-ins are still there.
    assert any(t["is_system"] for t in body["templates"])


def test_owned_only_returns_just_your_templates(studio_client, headers):
    project = build_project(studio_client, headers)
    save_template(studio_client, headers, project["id"], name="Mine")

    body = studio_client.get(
        "/api/video/templates?owned_only=true", headers=headers
    ).json()

    assert [t["name"] for t in body["templates"]] == ["Mine"]


def test_another_account_never_sees_your_saved_template(
    studio_client, headers, other_headers
):
    project = build_project(studio_client, headers)
    save_template(studio_client, headers, project["id"], name="Private Setup")

    body = studio_client.get("/api/video/templates", headers=other_headers).json()

    assert "Private Setup" not in [t["name"] for t in body["templates"]]


def test_two_users_can_save_templates_with_the_same_name(
    studio_client, headers, other_headers
):
    """`key` is unique table-wide, so it is namespaced by user.

    Without that, the first person to save "Product Promo" takes the name away
    from everybody else — including from the system set.
    """
    mine = build_project(studio_client, headers)
    theirs = build_project(studio_client, other_headers)

    a = save_template(studio_client, headers, mine["id"], name="Product Promo")
    b = save_template(studio_client, other_headers, theirs["id"], name="Product Promo")

    assert a.status_code == 201, a.text
    assert b.status_code == 201, b.text
    assert a.json()["key"] != b.json()["key"]
    # And neither collided with the built-in of that name.
    assert a.json()["key"] != "product_promo"


def test_saving_the_same_name_twice_gets_a_free_key(studio_client, headers):
    project = build_project(studio_client, headers)

    first = save_template(studio_client, headers, project["id"], name="Setup").json()
    second = save_template(studio_client, headers, project["id"], name="Setup").json()

    assert first["key"] != second["key"]


def test_you_cannot_save_a_template_from_someone_elses_project(
    studio_client, headers, other_headers
):
    theirs = build_project(studio_client, other_headers)

    response = save_template(studio_client, headers, theirs["id"])

    assert response.status_code == 404


def test_a_template_needs_a_name(studio_client, headers):
    project = build_project(studio_client, headers)

    response = save_template(studio_client, headers, project["id"], name="   ")

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Deleting
# ---------------------------------------------------------------------------


def test_you_can_delete_your_own_template(studio_client, headers):
    project = build_project(studio_client, headers)
    saved = save_template(studio_client, headers, project["id"], name="Mine").json()

    assert studio_client.delete(
        f"/api/video/templates/{saved['key']}", headers=headers
    ).status_code == 204

    body = studio_client.get("/api/video/templates", headers=headers).json()
    assert "Mine" not in [t["name"] for t in body["templates"]]


def test_a_built_in_template_cannot_be_deleted(studio_client, headers):
    """It is shared. One account deleting it would empty everybody's library."""
    response = studio_client.delete(
        "/api/video/templates/listicle_shorts", headers=headers
    )

    assert response.status_code == 422
    assert studio_client.get(
        "/api/video/templates/listicle_shorts", headers=headers
    ).status_code == 200


def test_you_cannot_delete_someone_elses_template(
    studio_client, headers, other_headers
):
    theirs_project = build_project(studio_client, other_headers)
    theirs = save_template(
        studio_client, other_headers, theirs_project["id"], name="Theirs"
    ).json()

    response = studio_client.delete(
        f"/api/video/templates/{theirs['key']}", headers=headers
    )

    assert response.status_code == 422
