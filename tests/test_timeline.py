"""The timeline engine — the document the editor, the preview and the renderer
all share.

These tests are pure: no database, no ffmpeg, no HTTP. That is the point of the
module being pure, and it is what makes it affordable to test the arithmetic
properly — which matters, because trim and split arithmetic with a speed factor
is the part of an editor that is quietly wrong for months.

What is asserted here:

  * **Normalization repairs rather than rejects.** A v1 document, a clip with
    missing fields, a NaN — all have to come out usable, because they exist in
    the database already.
  * **The video track is a sequence and the audio track is a mix.** The
    difference is the whole reason the compositor can be written the way it is.
  * **Trim and split respect speed.** A 2x clip consumes two seconds of source
    per second of timeline, in both directions.
  * **An edit that cannot be honoured is refused, not fudged.**
"""
from __future__ import annotations

import pytest

from app.services.video import timeline as tl


def build(video=(), audio=(), text=()):
    """A document from three lists of partial clips."""
    return tl.normalize(
        {
            "version": 2,
            "tracks": [
                {"id": "video", "clips": list(video)},
                {"id": "audio", "clips": list(audio)},
                {"id": "text", "clips": list(text)},
            ],
        }
    )


def clips(document, track_id="video"):
    return tl.get_track(document, track_id)["clips"]


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def test_an_empty_project_normalizes_to_three_tracks():
    document = tl.normalize(None)

    assert [track["id"] for track in document["tracks"]] == ["video", "audio", "text"]
    assert tl.is_empty(document)
    assert tl.duration(document) == 0.0


def test_a_version_one_document_keeps_its_subtitles():
    """v1 had a separate subtitles track. Dropping it would delete captions."""
    document = tl.normalize(
        {
            "version": 1,
            "tracks": [
                {"id": "text", "kind": "text", "clips": [{"text": "Title"}]},
                {"id": "video", "kind": "video", "clips": []},
                {"id": "audio", "kind": "audio", "clips": []},
                {"id": "subtitles", "kind": "subtitles", "clips": [{"text": "Caption"}]},
            ],
        }
    )

    words = [clip["text"] for clip in clips(document, "text")]
    assert set(words) == {"Title", "Caption"}
    assert document["version"] == tl.TIMELINE_VERSION


def test_a_clip_with_nothing_on_it_still_renders():
    """An older client's clip must not reach the compositor with no scale."""
    document = build(video=[{"kind": "video", "asset_id": 3}])
    clip = clips(document)[0]

    assert clip["scale"] == 1.0
    assert clip["fit"] == "cover"
    assert clip["speed"] == 1.0
    assert clip["crop"] == {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0}
    assert clip["id"].startswith("c_")


def test_junk_numbers_are_coerced_rather_than_propagated():
    document = build(
        video=[{"kind": "video", "scale": "not a number", "rotation": float("nan"),
                "duration": None, "speed": 99}]
    )
    clip = clips(document)[0]

    assert clip["scale"] == 1.0
    assert clip["rotation"] == 0.0
    assert clip["duration"] == 5.0
    assert clip["speed"] == tl.MAX_SPEED


def test_a_crop_cannot_remove_the_whole_frame():
    """A zero-width scale is an ffmpeg error nobody can act on."""
    document = build(video=[{"kind": "video", "crop": {"left": 0.8, "right": 0.8}}])
    crop = clips(document)[0]["crop"]

    assert crop["left"] + crop["right"] <= 0.95


def test_an_inverted_trim_is_discarded():
    document = build(video=[{"kind": "video", "trim_start": 10, "trim_end": 4}])
    assert clips(document)[0]["trim_end"] is None


def test_an_image_clip_has_no_speed_or_audio():
    """A still has no timebase — speed on one means nothing to the renderer."""
    document = build(video=[{"kind": "image", "speed": 2.0, "volume": 1.0}])
    clip = clips(document)[0]

    assert clip["speed"] == 1.0
    assert clip["volume"] == 0.0
    assert clip["muted"] is True


def test_a_colour_that_could_break_the_filter_graph_is_refused():
    """An unvalidated colour lands inside an ffmpeg filter argument."""
    document = build(text=[{"kind": "text", "color": "red'; drawbox=", "outline": "#0f0"}])
    clip = clips(document, "text")[0]

    assert clip["color"] == "#FFFFFF"
    assert clip["outline"] == "#0F0"


def test_rgba_colours_from_the_subtitle_presets_survive():
    document = build(text=[{"kind": "text", "background": "rgba(0,0,0,0.35)"}])
    assert clips(document, "text")[0]["background"] == "#00000059"


def test_duplicate_clip_ids_are_made_unique():
    """Two clips with one id makes every edit ambiguous."""
    document = build(
        video=[{"id": "same", "kind": "video"}, {"id": "same", "kind": "video", "start": 9}]
    )
    ids = [clip["id"] for clip in clips(document)]
    assert len(set(ids)) == 2


def test_a_clip_cannot_be_put_on_a_track_that_does_not_take_it():
    document = build(audio=[{"kind": "video", "asset_id": 1}])
    # Coerced to the track's own kind rather than kept as a video clip on the
    # audio track, which the compositor has no filter for.
    assert clips(document, "audio")[0]["kind"] == "audio"


# ---------------------------------------------------------------------------
# The video track is a sequence
# ---------------------------------------------------------------------------


def test_overlapping_video_clips_are_repaired_on_load():
    """A bad import must not reach the renderer overlapping."""
    document = build(
        video=[
            {"kind": "video", "start": 0, "duration": 10},
            {"kind": "video", "start": 3, "duration": 5},
        ]
    )
    first, second = clips(document)

    assert second["start"] == 10.0
    assert first["start"] + first["duration"] <= second["start"] + 1e-6


def test_audio_clips_are_allowed_to_overlap():
    """Voice-over and music playing together is the point of the mix."""
    document = build(
        audio=[
            {"kind": "audio", "start": 0, "duration": 30, "role": "music"},
            {"kind": "audio", "start": 2, "duration": 10, "role": "voiceover"},
        ]
    )
    music, voice = clips(document, "audio")

    assert music["start"] == 0.0
    assert voice["start"] == 2.0, "the mix was flattened into a sequence"


def test_text_clips_are_allowed_to_overlap():
    document = build(
        text=[
            {"kind": "text", "text": "A", "start": 0, "duration": 10},
            {"kind": "text", "text": "B", "start": 1, "duration": 3},
        ]
    )
    assert [clip["start"] for clip in clips(document, "text")] == [0.0, 1.0]


# ---------------------------------------------------------------------------
# Add
# ---------------------------------------------------------------------------


def test_adding_without_a_position_appends():
    document = build(video=[{"kind": "video", "start": 0, "duration": 4}])

    document, added = tl.add_clip(
        document, track_id="video", clip={"kind": "video", "duration": 3}
    )

    assert added["start"] == 4.0
    assert tl.duration(document) == 7.0


def test_adding_where_a_clip_already_is_is_refused():
    """The user picked a spot. Silently moving their clip is worse than a no."""
    document = build(video=[{"kind": "video", "start": 0, "duration": 10}])

    with pytest.raises(tl.TimelineError, match="already a clip"):
        tl.add_clip(
            document, track_id="video", clip={"kind": "video", "duration": 2}, at=5
        )


def test_audio_can_be_added_over_existing_audio():
    document = build(audio=[{"kind": "audio", "start": 0, "duration": 30}])

    document, added = tl.add_clip(
        document, track_id="audio", clip={"kind": "audio", "duration": 5}, at=3
    )

    assert added["start"] == 3.0
    assert len(clips(document, "audio")) == 2


# ---------------------------------------------------------------------------
# Move
# ---------------------------------------------------------------------------


def test_moving_a_clip_changes_only_its_start():
    document = build(video=[{"id": "a", "kind": "video", "start": 0, "duration": 4}])

    document = tl.move_clip(document, clip_id="a", start=6)
    clip = clips(document)[0]

    assert clip["start"] == 6.0
    assert clip["duration"] == 4.0
    assert clip["trim_start"] == 0.0


def test_moving_a_video_clip_onto_another_is_refused():
    document = build(
        video=[
            {"id": "a", "kind": "video", "start": 0, "duration": 4},
            {"id": "b", "kind": "video", "start": 10, "duration": 4},
        ]
    )

    with pytest.raises(tl.TimelineError, match="overlap"):
        tl.move_clip(document, clip_id="b", start=2)


def test_a_locked_clip_does_not_move():
    document = build(
        video=[{"id": "a", "kind": "video", "start": 0, "duration": 4, "locked": True}]
    )

    with pytest.raises(tl.TimelineError, match="locked"):
        tl.move_clip(document, clip_id="a", start=6)


# ---------------------------------------------------------------------------
# Trim
# ---------------------------------------------------------------------------


def test_trimming_the_end_keeps_the_in_point():
    document = build(
        video=[{"id": "a", "kind": "video", "start": 2, "duration": 10, "trim_start": 3}]
    )

    document = tl.trim_clip(document, clip_id="a", edge="end", to=8)
    clip = clips(document)[0]

    assert clip["start"] == 2.0
    assert clip["duration"] == 6.0
    assert clip["trim_start"] == 3.0
    assert clip["trim_end"] == 9.0  # 3 + 6


def test_trimming_the_start_moves_the_in_point_with_the_clip():
    """The frames under the playhead must not slide when the head is dragged."""
    document = build(
        video=[{"id": "a", "kind": "video", "start": 0, "duration": 10, "trim_start": 0}]
    )

    document = tl.trim_clip(document, clip_id="a", edge="start", to=4)
    clip = clips(document)[0]

    assert clip["start"] == 4.0
    assert clip["duration"] == 6.0
    assert clip["trim_start"] == 4.0, "the source in-point did not follow the edge"


def test_trimming_accounts_for_speed():
    """A 2x clip consumes two seconds of source per second of timeline."""
    document = build(
        video=[
            {"id": "a", "kind": "video", "start": 0, "duration": 10,
             "trim_start": 0, "speed": 2.0}
        ]
    )

    document = tl.trim_clip(document, clip_id="a", edge="end", to=4)
    clip = clips(document)[0]

    assert clip["duration"] == 4.0
    assert clip["trim_end"] == 8.0, "the out-point ignored the speed factor"


def test_a_clip_cannot_be_trimmed_to_nothing():
    document = build(video=[{"id": "a", "kind": "video", "start": 0, "duration": 10}])

    with pytest.raises(tl.TimelineError, match="entirely"):
        tl.trim_clip(document, clip_id="a", edge="end", to=0.01)


def test_trimming_into_the_next_clip_is_refused():
    document = build(
        video=[
            {"id": "a", "kind": "video", "start": 0, "duration": 4},
            {"id": "b", "kind": "video", "start": 4, "duration": 4},
        ]
    )

    with pytest.raises(tl.TimelineError, match="overlap"):
        tl.trim_clip(document, clip_id="a", edge="end", to=6)


# ---------------------------------------------------------------------------
# Split
# ---------------------------------------------------------------------------


def test_splitting_produces_two_adjacent_clips_covering_the_original():
    document = build(
        video=[{"id": "a", "kind": "video", "start": 0, "duration": 10, "trim_start": 0}]
    )

    document, (left_id, right_id) = tl.split_clip(document, clip_id="a", at=4)
    left, right = clips(document)

    assert left_id == "a", "the left half should keep the id a selection points at"
    assert (left["start"], left["duration"]) == (0.0, 4.0)
    assert (right["start"], right["duration"]) == (4.0, 6.0)
    assert right["id"] == right_id
    # No gap and no overlap.
    assert left["start"] + left["duration"] == right["start"]


def test_splitting_advances_the_right_halfs_in_point():
    document = build(
        video=[{"id": "a", "kind": "video", "start": 0, "duration": 10, "trim_start": 5}]
    )

    document, _ = tl.split_clip(document, clip_id="a", at=4)
    left, right = clips(document)

    assert left["trim_start"] == 5.0
    assert left["trim_end"] == 9.0
    assert right["trim_start"] == 9.0, "the right half would replay the left half"


def test_splitting_accounts_for_speed():
    document = build(
        video=[{"id": "a", "kind": "video", "start": 0, "duration": 10,
                "trim_start": 0, "speed": 2.0}]
    )

    document, _ = tl.split_clip(document, clip_id="a", at=4)
    left, right = clips(document)

    assert left["trim_end"] == 8.0
    assert right["trim_start"] == 8.0


def test_splitting_audio_does_not_duplicate_the_fades():
    """Both halves keeping both fades is audible."""
    document = build(
        audio=[{"id": "a", "kind": "audio", "start": 0, "duration": 10,
                "fade_in": 1.0, "fade_out": 2.0}]
    )

    document, _ = tl.split_clip(document, clip_id="a", at=5)
    left, right = clips(document, "audio")

    assert (left["fade_in"], left["fade_out"]) == (1.0, 0.0)
    assert (right["fade_in"], right["fade_out"]) == (0.0, 2.0)


def test_splitting_at_the_very_edge_is_refused():
    document = build(video=[{"id": "a", "kind": "video", "start": 0, "duration": 10}])

    with pytest.raises(tl.TimelineError, match="further into the clip"):
        tl.split_clip(document, clip_id="a", at=0.01)
    with pytest.raises(tl.TimelineError, match="further into the clip"):
        tl.split_clip(document, clip_id="a", at=9.999)


# ---------------------------------------------------------------------------
# Delete and reorder
# ---------------------------------------------------------------------------


def test_deleting_leaves_a_gap_by_default():
    document = build(
        video=[
            {"id": "a", "kind": "video", "start": 0, "duration": 4},
            {"id": "b", "kind": "video", "start": 4, "duration": 4},
        ]
    )

    document = tl.delete_clip(document, clip_id="a")

    assert [clip["id"] for clip in clips(document)] == ["b"]
    assert clips(document)[0]["start"] == 4.0


def test_a_ripple_delete_closes_the_gap():
    document = build(
        video=[
            {"id": "a", "kind": "video", "start": 0, "duration": 4},
            {"id": "b", "kind": "video", "start": 4, "duration": 4},
        ]
    )

    document = tl.delete_clip(document, clip_id="a", ripple=True)

    assert clips(document)[0]["start"] == 0.0


def test_reordering_lays_clips_out_back_to_back():
    document = build(
        video=[
            {"id": "a", "kind": "video", "start": 0, "duration": 4},
            {"id": "b", "kind": "video", "start": 4, "duration": 6},
            {"id": "c", "kind": "video", "start": 10, "duration": 2},
        ]
    )

    document = tl.reorder_clips(document, track_id="video", clip_ids=["c", "a", "b"])

    assert [(c["id"], c["start"]) for c in clips(document)] == [
        ("c", 0.0),
        ("a", 2.0),
        ("b", 6.0),
    ]


def test_a_partial_reorder_is_refused():
    """Otherwise it silently drops the clips it forgot to mention."""
    document = build(
        video=[
            {"id": "a", "kind": "video", "start": 0, "duration": 4},
            {"id": "b", "kind": "video", "start": 4, "duration": 4},
        ]
    )

    with pytest.raises(tl.TimelineError, match="exactly once"):
        tl.reorder_clips(document, track_id="video", clip_ids=["a"])


def test_only_the_video_track_can_be_reordered():
    """Reordering a mix means nothing — the clips are not in a queue."""
    document = build(audio=[{"id": "a", "kind": "audio"}])

    with pytest.raises(tl.TimelineError, match="Only the video track"):
        tl.reorder_clips(document, track_id="audio", clip_ids=["a"])


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def test_updating_applies_the_inspector_controls():
    document = build(video=[{"id": "a", "kind": "video", "start": 0, "duration": 4}])

    document = tl.update_clip(
        document,
        clip_id="a",
        patch={"scale": 1.4, "x": 0.1, "rotation": 90, "speed": 1.5, "volume": 0.3},
    )
    clip = clips(document)[0]

    assert (clip["scale"], clip["x"], clip["rotation"]) == (1.4, 0.1, 90.0)
    assert (clip["speed"], clip["volume"]) == (1.5, 0.3)


def test_an_update_cannot_move_a_clip():
    """Moving is `move_clip`, which checks overlaps. A patch would bypass it."""
    document = build(video=[{"id": "a", "kind": "video", "start": 2, "duration": 4}])

    document = tl.update_clip(document, clip_id="a", patch={"start": 99})

    assert clips(document)[0]["start"] == 2.0


def test_an_update_cannot_change_what_a_clip_is():
    document = build(video=[{"id": "a", "kind": "video", "start": 0, "duration": 4}])

    document = tl.update_clip(
        document, clip_id="a", patch={"kind": "text", "id": "hijacked"}
    )
    clip = clips(document)[0]

    assert clip["id"] == "a"
    assert clip["kind"] == "video"


def test_an_update_that_would_overlap_is_refused():
    document = build(
        video=[
            {"id": "a", "kind": "video", "start": 0, "duration": 4},
            {"id": "b", "kind": "video", "start": 4, "duration": 4},
        ]
    )

    with pytest.raises(tl.TimelineError, match="overlap"):
        tl.update_clip(document, clip_id="a", patch={"duration": 8})


def test_a_locked_clip_can_still_be_unlocked():
    document = build(
        video=[{"id": "a", "kind": "video", "start": 0, "duration": 4, "locked": True}]
    )

    document = tl.update_clip(document, clip_id="a", patch={"locked": False})

    assert clips(document)[0]["locked"] is False


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def test_duration_is_the_end_of_the_last_clip_on_any_track():
    document = build(
        video=[{"kind": "video", "start": 0, "duration": 4}],
        audio=[{"kind": "audio", "start": 0, "duration": 12}],
    )
    assert tl.duration(document) == 12.0


def test_asset_ids_are_listed_once_each_in_order():
    document = build(
        video=[
            {"kind": "video", "asset_id": 7, "start": 0, "duration": 2},
            {"kind": "video", "asset_id": 7, "start": 2, "duration": 2},
            {"kind": "video", "asset_id": 3, "start": 4, "duration": 2},
        ],
        audio=[{"kind": "audio", "asset_id": 9}],
    )
    assert tl.asset_ids(document) == [7, 3, 9]


def test_the_summary_reports_what_the_export_dialog_needs():
    document = build(
        video=[{"kind": "video", "duration": 6}],
        text=[{"kind": "text", "text": "Hi", "duration": 2}],
    )
    summary = tl.summary(document)

    assert summary["duration_seconds"] == 6.0
    assert summary["total_clips"] == 2
    assert summary["has_video"] is True
    assert summary["has_audio"] is False
    assert summary["has_text"] is True


def test_operations_do_not_mutate_the_document_they_were_given():
    """The undo stack is a list of documents. Mutation would corrupt history."""
    document = build(video=[{"id": "a", "kind": "video", "start": 0, "duration": 4}])
    before = tl.duration(document)

    tl.move_clip(document, clip_id="a", start=20)
    tl.delete_clip(document, clip_id="a")
    tl.update_clip(document, clip_id="a", patch={"duration": 9})

    assert tl.duration(document) == before
    assert len(clips(document)) == 1
