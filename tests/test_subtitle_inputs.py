"""Subtitle Studio's independent inputs, and what happens when two are given.

The rule this file exists to hold to account: **at least one input is required
and every additional one is optional.** A recording alone, a document alone, a
pasted script alone and an existing subtitle file alone each have to produce a
usable track, and a recording *with* its script has to produce a better one
without the script ever becoming a prerequisite.

**On "do not create mock subtitle data".** Nothing here hand-writes a cue and
asserts on it as though a model produced it. The document tests build real
files — a real DOCX zip with a real `word/document.xml`, a real PDF written by
pypdf — and read them with the shipping reader. The alignment tests build their
"transcript" with `cues_from_segments`, which is the same function the live
Whisper path calls, and then align it with the shipping aligner. The only thing
substituted anywhere in the subtitle suite is the HTTP call to the speech
vendor, and that lives in `test_subtitle_studio.py`.
"""
from __future__ import annotations

import io
import zipfile

import pytest

from app.services.video import alignment
from app.services.video import documents
from app.services.video import subtitles as engine

from tests.conftest import register

# The script a speaker was reading from. Deliberately ordinary sentences: the
# aligner's job is the everyday case of somebody reading a page aloud.
SCRIPT = (
    "Today we are going to learn how AI works.\n\n"
    "It's actually pretty simple once you break it down.\n\n"
    "Let's get started."
)

# What the recording of that reading sounds like to a speech model: contracted
# where the speaker contracted, one genuine mishearing ("brake" for "break"),
# one filler, one ad-lib, and no punctuation to speak of. Every difference here
# is one a real transcript has.
SPOKEN_SEGMENTS = [
    {"start": 0.0, "end": 2.6, "text": "Today we're gonna learn how AI works"},
    {"start": 2.7, "end": 6.1, "text": "It's actually pretty simple once you brake it down"},
    {"start": 6.2, "end": 9.4, "text": "um so let's get started right now"},
]


def transcribed() -> list[dict]:
    """A transcript-shaped track, built by the shipping transcript path."""
    return engine.cues_from_segments(SPOKEN_SEGMENTS)


def docx_bytes(paragraphs: list[str]) -> bytes:
    """A real .docx — a real zip holding a real `word/document.xml`.

    Written out longhand rather than with python-docx because the reader under
    test parses this XML directly, and a fixture built by the same library that
    writes it would only prove the library round-trips.

    The first paragraph is deliberately split across two `<w:t>` runs, which is
    what Word does whenever formatting changes mid-word. A reader that joins
    runs with a space turns that word into two.
    """
    body = []
    for index, text in enumerate(paragraphs):
        if index == 0 and len(text) > 6:
            head, tail = text[:4], text[4:]
            runs = f"<w:r><w:t>{head}</w:t></w:r><w:r><w:t>{tail}</w:t></w:r>"
        else:
            runs = f"<w:r><w:t>{text}</w:t></w:r>"
        body.append(f"<w:p>{runs}</w:p>")

    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body)}</w:body></w:document>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
            'package/2006/content-types"><Default Extension="xml" '
            'ContentType="application/xml"/></Types>',
        )
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def pdf_bytes(lines: list[str]) -> bytes:
    """A real PDF with a real text layer, assembled byte by byte.

    Written out rather than produced by a library because the point of the test
    is that *the reader* pulls text out of a PDF. A fixture built by the same
    library that reads it would only prove pypdf round-trips its own output.

    This is the minimum a PDF can be: header, catalogue, page tree, one page
    with a Helvetica font resource, one content stream holding `BT … Tj … ET`
    text objects, an xref table and a trailer.
    """
    content = "".join(
        f"BT /F1 12 Tf 72 {720 - index * 18} Td "
        f"({line.replace(chr(92), '').replace('(', '').replace(')', '')}) Tj ET\n"
        for index, line in enumerate(lines)
    ).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


# ===========================================================================
# 1. Reading a document
# ===========================================================================


def test_a_text_file_keeps_its_paragraph_breaks():
    raw = "First paragraph here.\r\n\r\n\r\n\r\nSecond paragraph here.\r\n".encode("utf-8")

    result = documents.extract("script.txt", raw)

    assert result["kind"] == "text"
    # Paragraph structure survives, because that is what decides where one
    # subtitle ends and the next begins.
    assert result["text"] == "First paragraph here.\n\nSecond paragraph here."
    assert result["word_count"] == 6


def test_a_utf8_bom_does_not_become_a_visible_character():
    result = documents.extract("script.txt", "﻿Hello there.".encode("utf-8-sig"))

    assert result["text"] == "Hello there."


def test_a_docx_is_read_paragraph_by_paragraph_without_splitting_words():
    raw = docx_bytes(["Important announcement today.", "The second paragraph."])

    result = documents.extract("script.docx", raw)

    assert result["kind"] == "docx"
    # The first paragraph was written as two runs mid-word. Joining runs with a
    # space would give "Impo rtant announcement today."
    assert result["text"] == "Important announcement today.\n\nThe second paragraph."


def test_a_docx_with_escaped_entities_comes_back_unescaped():
    raw = docx_bytes(["Rock &amp; roll &lt;live&gt;"])

    assert documents.extract("s.docx", raw)["text"] == "Rock & roll <live>"


def test_a_pdf_is_read_into_text():
    raw = pdf_bytes(["Today we are going to learn.", "It is simple."])

    result = documents.extract("script.pdf", raw)

    assert result["kind"] == "pdf"
    assert "Today we are going to learn." in result["text"]
    assert "It is simple." in result["text"]


def test_an_unsupported_extension_is_refused_by_name():
    with pytest.raises(documents.DocumentError) as exc:
        documents.extract("recording.mp4", b"\x00\x01")

    # The message names what is accepted rather than what went wrong inside.
    assert ".mp4" in str(exc.value)
    assert "PDF" in str(exc.value) and "DOCX" in str(exc.value)


def test_an_empty_document_is_refused():
    with pytest.raises(documents.DocumentError, match="empty"):
        documents.extract("script.txt", b"")


def test_a_document_of_only_whitespace_is_refused():
    with pytest.raises(documents.DocumentError, match="No readable text"):
        documents.extract("script.txt", b"   \n\n\t  \n")


def test_a_corrupt_docx_is_refused_with_a_sentence_not_a_traceback():
    with pytest.raises(documents.DocumentError) as exc:
        documents.extract("script.docx", b"this is not a zip file at all")

    assert "Word document" in str(exc.value)
    assert "Traceback" not in str(exc.value)


def test_a_corrupt_pdf_is_refused():
    with pytest.raises(documents.DocumentError) as exc:
        documents.extract("script.pdf", b"%PDF-1.4 truncated nonsense")

    assert "PDF" in str(exc.value)


def test_a_pdf_with_no_text_layer_says_so_rather_than_looking_broken():
    """A scanned PDF holds pictures of words. That is worth saying out loud."""
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)

    with pytest.raises(documents.DocumentError) as exc:
        documents.extract("scan.pdf", buffer.getvalue())

    assert "scan" in str(exc.value).lower()


def test_a_document_over_the_size_limit_is_refused_before_it_is_parsed():
    oversized = b"a" * (documents.MAX_DOCUMENT_BYTES + 1)

    with pytest.raises(documents.DocumentError, match="limit"):
        documents.extract("script.txt", oversized)


def test_a_very_long_document_is_cut_at_a_sentence_and_says_it_was():
    raw = ("This is a sentence about a thing. " * 8000).encode("utf-8")

    result = documents.extract("long.txt", raw)

    assert result["truncated"] is True
    assert len(result["text"]) <= documents.MAX_CHARACTERS
    # Cut at a boundary, not mid-word.
    assert result["text"].endswith(".")


# ===========================================================================
# 2. A document on its own becomes cues
# ===========================================================================


def test_document_text_times_into_cues_exactly_like_a_pasted_script():
    """One timing path, whichever way the words arrived.

    A document and a pasted script differ only in how the text was obtained. If
    they went through different timing code, the same words would produce two
    different tracks — which is the bug this asserts cannot happen.
    """
    text = documents.extract("script.txt", SCRIPT.encode("utf-8"))["text"]

    from_document = engine.cues_from_script(text, duration_seconds=30)
    from_paste = engine.cues_from_script(SCRIPT, duration_seconds=30)

    assert from_document == from_paste


def test_a_target_duration_fits_the_document_to_it_exactly():
    text = documents.extract("script.txt", SCRIPT.encode("utf-8"))["text"]

    cues = engine.cues_from_script(text, duration_seconds=60)

    assert engine.total_duration(cues) == pytest.approx(60.0, abs=0.01)
    assert cues[0]["start"] == 0.0


def test_without_a_duration_the_length_comes_from_reading_speed():
    text = documents.extract("script.txt", SCRIPT.encode("utf-8"))["text"]

    slow = engine.cues_from_script(text, wpm=90)
    fast = engine.cues_from_script(text, wpm=200)

    # Configurable, and it actually configures something.
    assert engine.total_duration(slow) > engine.total_duration(fast)


# ===========================================================================
# 3. Aligning a script against what was said
# ===========================================================================


def test_alignment_never_moves_a_timestamp():
    """The one invariant. Timing comes from the audio, always."""
    spoken = transcribed()

    aligned, report = alignment.align(spoken, SCRIPT)

    assert report["applied"] is True
    assert aligned[0]["start"] == spoken[0]["start"]
    assert engine.total_duration(aligned) == pytest.approx(
        engine.total_duration(spoken), abs=0.001
    )
    # Every cue still sits inside the span the audio gave it.
    for cue in aligned:
        assert any(
            segment["start"] - 0.001 <= cue["start"] and cue["end"] <= segment["end"] + 0.001
            for segment in SPOKEN_SEGMENTS
        )


def test_a_contraction_is_recognised_as_the_same_words():
    """"we're gonna" and "we are going to" are one difference, not four."""
    aligned, report = alignment.align(transcribed(), SCRIPT)
    text = flat(aligned)

    # The script's wording wins where the two agree.
    assert "we are going to learn" in text
    assert "gonna" not in text
    assert report["similarity"] > 0.7


def flat(cues: list[dict]) -> str:
    """One line of text for the whole track.

    Cues are wrapped to the reading limits, so "break it down" legitimately
    arrives with a newline inside it. Asserting on the words means flattening
    the wrapping first.
    """
    return " ".join(" ".join(cue["text"].split()) for cue in cues)


def test_an_obvious_mishearing_is_corrected_from_the_script():
    aligned, _ = alignment.align(transcribed(), SCRIPT)
    text = flat(aligned)

    # "brake it down" heard, "break it down" written, and they are close enough
    # that the script is the better spelling of what was said.
    assert "break it down" in text
    assert "brake" not in text


def test_words_spoken_but_absent_from_the_script_are_kept():
    """The speaker's ad-lib is content. It was said, so it stays."""
    aligned, report = alignment.align(transcribed(), SCRIPT)
    text = flat(aligned)

    assert "right now" in text
    assert report["added_words"] >= 2


def test_a_sentence_the_speaker_skipped_never_appears():
    """The disqualifying failure: captioning silence.

    The script has a sentence the recording does not. It must not be in the
    subtitles at any timestamp, because there is no audio under it.
    """
    script = SCRIPT.replace(
        "Let's get started.",
        "There is nothing at all to be afraid of. Let's get started.",
    )

    aligned, report = alignment.align(transcribed(), script)
    text = flat(aligned).lower()

    assert "afraid" not in text
    assert "nothing at all" not in text
    assert report["skipped_words"] >= 7


def test_a_wholly_different_script_is_declined_rather_than_forced():
    """Low confidence keeps the audio. A script that is not this script is not
    allowed to overwrite a perfectly good transcript."""
    spoken = transcribed()

    aligned, report = alignment.align(
        spoken,
        "The quarterly revenue figures for the northern region exceeded "
        "projections by twelve percent across every product line, and the "
        "board has approved an increase to the marketing budget.",
    )

    assert report["applied"] is False
    assert report["status"] == "unmatched"
    assert aligned == spoken
    assert "does not appear to match" in (report["message"] or "")


def test_a_recording_of_one_section_of_a_long_script_is_still_a_match():
    """The asymmetry that a symmetric similarity score gets wrong.

    Somebody records a forty-minute script one section at a time. Each take
    matches its section perfectly and matches 95% of the document not at all —
    which as an overall *similarity* looks like an unrelated document. What
    decides is coverage: does the script explain what was said?
    """
    long_script = SCRIPT + "\n\n" + (
        "Later in the video we will cover training data, model weights, "
        "gradient descent and the transformer architecture. "
    ) * 12

    aligned, report = alignment.align(transcribed(), long_script)

    assert report["applied"] is True
    assert report["coverage"] > 0.8
    # …even though the two texts as a whole barely resemble each other.
    assert report["similarity"] < 0.35
    # And the ninety percent of the script that was never spoken stays out.
    assert "transformer" not in flat(aligned).lower()


def test_a_major_divergence_warns_without_blocking():
    """A speaker who went off-script gets a warning and a usable track."""
    script = (
        "Today we are going to learn how AI works. "
        "It's actually pretty simple once you break it down. "
        "We will cover neural networks, training data, weights and biases, "
        "gradient descent, back propagation, and the transformer architecture "
        "in considerable technical detail. "
        "Let's get started."
    )

    aligned, report = alignment.align(transcribed(), script)

    assert report["applied"] is True
    assert report["warning"]
    assert "timing is based on the audio" in report["warning"].lower()
    # Non-blocking: there is still a track, and it is the spoken one — the
    # paragraph the speaker never read is simply not in it.
    assert len(aligned) >= 2
    assert "gradient descent" not in flat(aligned)


def test_a_perfect_reading_reports_that_nothing_needed_changing():
    spoken = engine.cues_from_segments(
        [
            {"start": 0.0, "end": 3.0, "text": "Today we are going to learn how AI works"},
            {"start": 3.1, "end": 6.0, "text": "Let us get started"},
        ]
    )

    aligned, report = alignment.align(
        spoken, "Today we are going to learn how AI works. Let us get started."
    )

    assert report["applied"] is True
    assert report["kept_words"] == 0
    assert report["added_words"] == 0
    assert report["skipped_words"] == 0
    # Punctuation restored from the script is not reported as a correction —
    # calling that "38 words corrected" would make a perfect match look like a
    # rewrite.
    assert report["corrected_words"] == 0
    assert "matched the audio exactly" in report["message"]
    assert flat(aligned).endswith("started.")


def test_alignment_never_invents_a_word_that_is_in_neither_input():
    aligned, _ = alignment.align(transcribed(), SCRIPT)

    vocabulary = {
        word.strip(".,!?'\"").lower()
        for source in (SCRIPT, " ".join(s["text"] for s in SPOKEN_SEGMENTS))
        for word in source.split()
    }
    for cue in aligned:
        for word in cue["text"].split():
            assert word.strip(".,!?'\"").lower() in vocabulary


def test_an_empty_script_leaves_the_transcript_alone():
    spoken = transcribed()

    aligned, report = alignment.align(spoken, "   ")

    assert report["applied"] is False
    assert report["status"] == "empty"
    assert aligned == spoken


def test_aligning_respects_the_styles_reading_limits():
    """An aligned track is wrapped by the same rules as a transcribed one."""
    style = engine.preset("tiktok")

    aligned, _ = alignment.align(transcribed(), SCRIPT, style=style)

    limit = style["max_chars_per_line"]
    for cue in aligned:
        for line in cue["text"].split("\n"):
            # A single word longer than the limit is left over-long by design;
            # anything else must fit.
            assert len(line) <= limit or " " not in line


# ===========================================================================
# 4. The routes
# ===========================================================================


@pytest.fixture()
def subs_headers(studio_client) -> dict:
    return register(studio_client, email="subinputs@example.com")


def test_from_document_returns_both_cues_and_the_text(studio_client, subs_headers):
    """A document is two inputs in one, so the response carries both.

    On its own the cues are the answer; alongside a recording the text is, and
    the studio posts it to /align rather than uploading the file twice.
    """
    response = studio_client.post(
        "/api/video/subtitles/from-document",
        headers=subs_headers,
        files={"file": ("script.docx", docx_bytes([SCRIPT]), "")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "docx"
    assert body["filename"] == "script.docx"
    assert body["word_count"] > 10
    assert body["cues"], "a document on its own has to produce a track"
    assert "how AI works" in body["text"]


def test_from_document_flags_estimated_timing_and_honours_a_target_length(
    studio_client, subs_headers
):
    raw = SCRIPT.encode("utf-8")

    estimated = studio_client.post(
        "/api/video/subtitles/from-document",
        headers=subs_headers,
        files={"file": ("script.txt", raw, "text/plain")},
    ).json()
    fitted = studio_client.post(
        "/api/video/subtitles/from-document",
        headers=subs_headers,
        files={"file": ("script.txt", raw, "text/plain")},
        data={"duration_seconds": "45"},
    ).json()

    # No audio behind it, so the API says the timing is a guess.
    assert estimated["estimated"] is True
    assert fitted["estimated"] is False
    assert fitted["duration_seconds"] == pytest.approx(45.0, abs=0.01)


def test_from_document_refuses_an_unreadable_file_with_a_readable_reason(
    studio_client, subs_headers
):
    response = studio_client.post(
        "/api/video/subtitles/from-document",
        headers=subs_headers,
        files={"file": ("script.docx", b"definitely not a zip", "")},
    )

    assert response.status_code == 422
    assert "Word document" in response.json()["detail"]


def test_from_document_refuses_an_empty_file(studio_client, subs_headers):
    response = studio_client.post(
        "/api/video/subtitles/from-document",
        headers=subs_headers,
        files={"file": ("script.txt", b"", "text/plain")},
    )

    assert response.status_code == 422
    assert "empty" in response.json()["detail"]


def test_from_document_refuses_a_media_file(studio_client, subs_headers):
    response = studio_client.post(
        "/api/video/subtitles/from-document",
        headers=subs_headers,
        files={"file": ("clip.mp4", b"\x00\x01\x02", "video/mp4")},
    )

    assert response.status_code == 422
    assert "cannot be read as a script" in response.json()["detail"]


def test_align_corrects_wording_and_reports_what_it_did(studio_client, subs_headers):
    response = studio_client.post(
        "/api/video/subtitles/align",
        headers=subs_headers,
        json={"cues": transcribed(), "script": SCRIPT},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["alignment"]["applied"] is True
    assert body["cue_count"] == len(body["cues"])
    text = " ".join(" ".join(cue["text"].split()) for cue in body["cues"])
    assert "we are going to" in text
    assert "break it down" in text


def test_align_on_an_empty_track_is_refused(studio_client, subs_headers):
    response = studio_client.post(
        "/api/video/subtitles/align",
        headers=subs_headers,
        json={"cues": [], "script": SCRIPT},
    )

    assert response.status_code == 422
    assert "no subtitles to align" in response.json()["detail"]


def test_align_works_on_an_imported_track_not_only_a_transcribed_one(
    studio_client, subs_headers
):
    """An SRT from somewhere else has real timings too.

    This is why alignment is its own endpoint rather than a flag on
    /transcribe: correcting an imported file against the original script is the
    same operation, and it would be unreachable otherwise.
    """
    srt = engine.to_srt(transcribed()).encode("utf-8")

    imported = studio_client.post(
        "/api/video/subtitles/import",
        headers=subs_headers,
        files={"file": ("track.srt", srt, "application/x-subrip")},
    ).json()

    aligned = studio_client.post(
        "/api/video/subtitles/align",
        headers=subs_headers,
        json={"cues": imported["cues"], "script": SCRIPT},
    ).json()

    assert aligned["alignment"]["applied"] is True
    assert aligned["duration_seconds"] == pytest.approx(imported["duration_seconds"], abs=0.01)


def test_an_aligned_track_exports_as_ordinary_srt_and_vtt(studio_client, subs_headers):
    """Whatever the input, what comes out is a subtitle file like any other."""
    aligned = studio_client.post(
        "/api/video/subtitles/align",
        headers=subs_headers,
        json={"cues": transcribed(), "script": SCRIPT},
    ).json()

    stored = studio_client.post(
        "/api/video/subtitles/export",
        headers=subs_headers,
        json={"cues": aligned["cues"], "format": "srt", "title": "aligned"},
    )
    assert stored.status_code == 201

    asset_id = stored.json()["id"]
    for fmt, marker in (("srt", "-->"), ("vtt", "WEBVTT")):
        download = studio_client.get(
            f"/api/video/subtitles/files/{asset_id}/download?format={fmt}",
            headers=subs_headers,
        )
        assert download.status_code == 200
        assert marker in download.text

    # And the timings survived the round trip.
    reparsed = engine.parse(
        studio_client.get(
            f"/api/video/subtitles/files/{asset_id}/download?format=srt",
            headers=subs_headers,
        ).text
    )
    assert len(reparsed) == len(aligned["cues"])
    assert reparsed[0]["start"] == pytest.approx(aligned["cues"][0]["start"], abs=0.001)


# ---------------------------------------------------------------------------
# What a document upload is allowed to be
# ---------------------------------------------------------------------------


def test_a_binary_file_renamed_txt_is_refused():
    """It decoded to control characters, and every one of them became cue text
    — which would reach an SRT line and then a drawtext argument."""
    from app.services.video import documents

    with pytest.raises(documents.DocumentError) as excinfo:
        documents.extract("payload.txt", bytes(range(256)) * 40)

    assert "does not look like text" in str(excinfo.value)


def test_a_script_with_symbols_and_accents_is_still_text():
    """The guard is a ratio, not a blanket ban — real scripts have odd
    characters in them and must not be caught by it."""
    from app.services.video import documents

    body = "Café — 5% a year, ≈ £1,200. “Worth it?” … Yes! 🎉"
    result = documents.extract("script.txt", body.encode("utf-8"))

    assert result["word_count"] > 5


@pytest.mark.parametrize("wpm", [0, -50, 1e9])
def test_an_impossible_reading_speed_does_not_produce_an_absurd_track(wpm):
    """At wpm=0 a ten-word script became a ten-minute track whose first cue ran
    for four minutes."""
    from app.services.video import subtitles as engine

    cues = engine.cues_from_script(
        "Welcome to the channel. Today we look at compound interest.", wpm=wpm
    )

    assert cues
    assert engine.total_duration(cues) < 60


def test_both_script_endpoints_bound_the_reading_speed(studio_client, headers):
    """The JSON route validated it and the upload route did not."""
    json_route = studio_client.post(
        "/api/video/subtitles/from-script",
        headers=headers,
        json={"text": "Hello there friend.", "words_per_minute": 0},
    )
    upload_route = studio_client.post(
        "/api/video/subtitles/from-document",
        headers=headers,
        files={"file": ("s.txt", b"Hello there friend.", "text/plain")},
        data={"words_per_minute": "0"},
    )

    assert json_route.status_code == 422
    assert upload_route.status_code == 422
