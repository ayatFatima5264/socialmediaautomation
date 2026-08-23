"""Aligning a written script against what was actually said.

The combined input: a recording *and* the script the speaker was working from.
Each answers a question the other cannot.

    The audio knows **when** every word was said, and **which words were
    actually said**.
    The script knows **how those words are spelled** — the product name, the
    person's name, the punctuation, the capitalisation.

So the rule this module implements is one sentence: *timing and content come
from the audio; wording comes from the script only where the two already
agree*. A speaker who skips a paragraph gets subtitles without that paragraph.
A speaker who ad-libs a sentence gets subtitles with it. Nobody gets a subtitle
containing words that were never spoken, because the script is never a source
of content — only of spelling for content the audio already established.

**Why diff, and not a model.** This is the same problem `diff` solves, and
`difflib` solves it exactly, for free, offline, in milliseconds, with a
reproducible answer. An LLM asked to "merge these two texts" would be slower,
cost money per transcription, and — the disqualifying part — would happily
invent a sentence that appears in neither input. A deterministic aligner
cannot: every output word is copied from one side or the other.

Matching happens on *atoms* rather than on the words as written. An atom is a
word reduced to what it sounds like: lowercased, stripped of punctuation, and
with contractions expanded, so "we're gonna" and "we are going to" are the same
four atoms and align perfectly rather than looking like a wholesale rewrite.
That is what makes the common case — a speaker reading a script naturally —
come out as a match rather than as a pile of differences.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.services.video import subtitles as engine

# ---------------------------------------------------------------------------
# Atoms
# ---------------------------------------------------------------------------

# Informal and contracted forms, expanded so both sides of the comparison say
# the same thing. Each maps to the atoms the expanded form produces, which is
# why a value is a tuple: "gonna" is one written word and two spoken ones.
#
# Only forms whose expansion is unambiguous are here. "ain't" is not, and a
# wrong expansion is worse than an unmatched word — an unmatched word costs a
# small difference, a wrong one costs a wrong subtitle.
_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "gonna": ("going", "to"),
    "wanna": ("want", "to"),
    "gotta": ("got", "to"),
    "kinda": ("kind", "of"),
    "sorta": ("sort", "of"),
    "outta": ("out", "of"),
    "lotta": ("lot", "of"),
    "lemme": ("let", "me"),
    "gimme": ("give", "me"),
    "dunno": ("do", "not", "know"),
    "cause": ("because",),
    "til": ("until",),
    "till": ("until",),
    "im": ("i", "am"),
    "ive": ("i", "have"),
    "ill": ("i", "will"),
    "id": ("i", "would"),
    "lets": ("let", "us"),
    "cant": ("can", "not"),
    "cannot": ("can", "not"),
    "wont": ("will", "not"),
    "shant": ("shall", "not"),
    "dont": ("do", "not"),
    "doesnt": ("does", "not"),
    "didnt": ("did", "not"),
    "isnt": ("is", "not"),
    "arent": ("are", "not"),
    "wasnt": ("was", "not"),
    "werent": ("were", "not"),
    "hasnt": ("has", "not"),
    "havent": ("have", "not"),
    "hadnt": ("had", "not"),
    "wouldnt": ("would", "not"),
    "couldnt": ("could", "not"),
    "shouldnt": ("should", "not"),
    "mustnt": ("must", "not"),
    "were": ("we", "are"),  # only reached for "we're"; see `_atoms`
    "youre": ("you", "are"),
    "theyre": ("they", "are"),
    "its": ("it", "is"),
    "thats": ("that", "is"),
    "whats": ("what", "is"),
    "wheres": ("where", "is"),
    "theres": ("there", "is"),
    "heres": ("here", "is"),
    "hes": ("he", "is"),
    "shes": ("she", "is"),
    "whos": ("who", "is"),
    "youve": ("you", "have"),
    "weve": ("we", "have"),
    "theyve": ("they", "have"),
    "youll": ("you", "will"),
    "well": ("we", "will"),  # only reached for "we'll"
    "theyll": ("they", "will"),
    "itll": ("it", "will"),
    "hell": ("he", "will"),  # only reached for "he'll"
    "shell": ("she", "will"),  # only reached for "she'll"
    "youd": ("you", "would"),
    "wed": ("we", "would"),
    "theyd": ("they", "would"),
    "hed": ("he", "would"),
    "shed": ("she", "would"),
}

# Expansions that are only correct for a form that *had* an apostrophe. "were"
# is a word in its own right, and expanding the past tense of "to be" into "we
# are" would corrupt every sentence containing it. These are applied only when
# the original token actually carried an apostrophe.
_APOSTROPHE_ONLY = {
    "were", "well", "hell", "shell", "its", "id", "ill", "im", "shed", "wed",
    # "the cause of it" and "he lets me" are ordinary words; only "'cause" and
    # "let's" are the contractions.
    "cause", "lets",
}

_APOSTROPHES = str.maketrans({"’": "'", "ʼ": "'", "´": "'", "`": "'"})

# What counts as a word character for the purpose of stripping punctuation off
# the ends of a token. Digits stay: "30" and "2026" are words a script says.
_EDGE_PUNCTUATION = re.compile(r"^[^\w'’]+|[^\w'’]+$", re.UNICODE)


def _atoms(token: str) -> tuple[str, ...]:
    """The comparison key(s) for one written word.

    Returns an empty tuple for a token that is only punctuation — an em dash on
    its own line is not a word, and treating it as one would make every cue
    around it look changed.
    """
    core = _EDGE_PUNCTUATION.sub("", token.translate(_APOSTROPHES)).lower()
    if not core:
        return ()

    had_apostrophe = "'" in core
    core = core.replace("'", "").replace("-", "").replace("—", "")
    if not core:
        return ()

    expansion = _EXPANSIONS.get(core)
    if expansion is not None and (had_apostrophe or core not in _APOSTROPHE_ONLY):
        return expansion
    return (core,)


def _sequence(tokens: list[str]) -> tuple[list[str], list[int]]:
    """Flatten tokens into atoms, remembering which token each atom came from.

    The two lists are parallel: `keys[i]` is an atom and `owners[i]` is the
    index of the token that produced it. That mapping is what lets a diff
    computed over atoms be replayed over whole words.
    """
    keys: list[str] = []
    owners: list[int] = []
    for index, token in enumerate(tokens):
        for atom in _atoms(token):
            keys.append(atom)
            owners.append(index)
    return keys, owners


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

#: Below this *coverage* the script is not a script for this recording, and
#: rather than corrupting a perfectly good transcript with words from an
#: unrelated document the alignment is declined and said so.
#:
#: Coverage — the share of the spoken words the script accounts for — rather
#: than a symmetric similarity, because the two texts are not symmetric. A
#: forty-minute script recorded one section at a time is a *correct* pairing
#: with 5% overall similarity and 100% coverage, and a symmetric measure would
#: throw it out. What matters is whether the script explains what was said, not
#: whether it says only that.
MIN_COVERAGE = 0.35

#: Within a single differing run, how alike the two versions must be before the
#: script's wording is adopted. Above it the difference reads as a
#: transcription slip or a spelling ("Zaions" heard as "Zions"); below it, the
#: speaker said something else, and something else is what they get.
MIN_RUN_SIMILARITY = 0.55

#: A run whose script side is much longer than its audio side is not a
#: correction, it is text that was not spoken. Adopting it would put words in
#: the speaker's mouth, which is the one thing this must never do.
MAX_RUN_GROWTH = 1.5

#: Where "a few differences" becomes worth warning about, as a share of the
#: script. Below it, a handful of ad-libbed words is normal delivery.
WARN_DIFFERENCE_SHARE = 0.08

#: …and the floor in absolute words, so a two-sentence script does not warn
#: because one word moved.
WARN_DIFFERENCE_WORDS = 6


def _ratio(left: list[str], right: list[str]) -> float:
    """How alike two runs of atoms are, compared as characters.

    Character-level rather than atom-level on purpose: "Zaions" against
    "Zions" is one atom against one atom, which as a sequence comparison is
    simply "different". As characters it is 0.8 alike, which is the signal that
    tells a misheard word from a different word.
    """
    return SequenceMatcher(None, " ".join(left), " ".join(right)).ratio()


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------


def align(cues: list[dict], script: str, *, style: dict | None = None) -> tuple[list[dict], dict]:
    """Correct a transcribed track against the script it was read from.

    `cues` are the transcription's cues — real timings, real spoken content.
    `script` is the reference wording. Returns `(cues, report)`.

    The cues that come back keep the timings they arrived with. Only the words
    change, and only where the script and the audio already agree closely
    enough that the difference is spelling rather than speech.

    The report is not decoration: it carries `applied`, which says whether the
    script was used at all, and the counts behind the warning the studio shows
    when a delivery diverged from its script. A caller that ignores it still
    gets correct cues; a caller that shows it can tell the user *why* their
    subtitles say something their document does not.
    """
    style = style or engine.preset(engine.DEFAULT_PRESET)
    max_chars = int(style.get("max_chars_per_line", engine.DEFAULT_MAX_CHARS_PER_LINE))
    max_lines = int(style.get("max_lines", engine.DEFAULT_MAX_LINES))

    source = engine.normalize(cues or [])

    # Every spoken word, in order, tagged with the cue it was said in. The cue
    # index is the carrier of timing: whatever a word is replaced by inherits
    # the span of the words it replaced.
    spoken: list[str] = []
    spoken_cue: list[int] = []
    for index, cue in enumerate(source):
        for token in (cue.get("text") or "").split():
            spoken.append(token)
            spoken_cue.append(index)

    written = (script or "").split()

    if not spoken or not written:
        return source, _report(
            applied=False,
            status="empty",
            similarity=0.0,
            message=(
                "There was nothing to compare — the script or the transcript "
                "was empty, so the subtitles are exactly as transcribed."
            ),
        )

    spoken_keys, spoken_owner = _sequence(spoken)
    written_keys, written_owner = _sequence(written)

    if not spoken_keys or not written_keys:
        return source, _report(
            applied=False,
            status="empty",
            similarity=0.0,
            message=(
                "No words could be read out of the script, so the subtitles "
                "are exactly as transcribed."
            ),
        )

    matcher = SequenceMatcher(None, spoken_keys, written_keys, autojunk=False)
    opcodes = matcher.get_opcodes()
    similarity = matcher.ratio()

    # How much of what was said the script accounts for. This, not `ratio()`,
    # decides whether the script is usable — see MIN_COVERAGE.
    coverage = sum(
        i2 - i1 for tag, i1, i2, _, _ in opcodes if tag == "equal"
    ) / len(spoken_keys)

    if coverage < MIN_COVERAGE:
        return source, _report(
            applied=False,
            status="unmatched",
            similarity=similarity,
            coverage=coverage,
            message=(
                "That script does not appear to match this recording, so it "
                "was not used. The subtitles are exactly as transcribed."
            ),
        )

    # Atom index -> token index, extended by one so the end of the sequence has
    # an answer too. An opcode boundary that lands inside a multi-atom word
    # resolves to that whole word, which is then handled by whichever side of
    # the boundary reaches it first — the cursor below keeps that consistent.
    def _boundary(owners: list[int], total: int, atom_index: int) -> int:
        return owners[atom_index] if atom_index < len(owners) else total

    output: list[tuple[str, int]] = []  # (word, cue index)
    matched = corrected = kept = skipped = added = 0

    spoken_cursor = 0
    written_cursor = 0

    for tag, i1, i2, j1, j2 in opcodes:
        spoken_end = max(spoken_cursor, _boundary(spoken_owner, len(spoken), i2))
        written_end = max(written_cursor, _boundary(written_owner, len(written), j2))

        said = spoken[spoken_cursor:spoken_end]
        said_cues = spoken_cue[spoken_cursor:spoken_end]
        wrote = written[written_cursor:written_end]

        spoken_cursor, written_cursor = spoken_end, written_end

        if tag == "equal":
            # The same words. Take the script's spelling — its capitalisation,
            # its punctuation, its version of the product name — over the
            # audio's timing. This is the whole point of supplying a script.
            output.extend(_place(wrote or said, said_cues))
            matched += len(said)
            # Not counted as a correction. The words were already the same —
            # what came from the script here is punctuation and capitalisation,
            # and reporting "37 words corrected" for restoring full stops would
            # make a perfect match look like a rewrite.

        elif tag == "replace":
            keys_said = spoken_keys[i1:i2]
            keys_wrote = written_keys[j1:j2]
            close_enough = (
                _ratio(keys_said, keys_wrote) >= MIN_RUN_SIMILARITY
                and len(keys_wrote) <= len(keys_said) * MAX_RUN_GROWTH + 1
            )
            if close_enough and wrote:
                # A misheard word or a small rephrasing: the script is the
                # better spelling of what was said.
                output.extend(_place(wrote, said_cues))
                corrected += len(said)
            else:
                # Genuinely different speech. What was said is what appears,
                # and the script's version of this passage is dropped — which
                # is counted, because "your document said something else here"
                # is exactly what the mismatch warning is about.
                output.extend(_place(said, said_cues))
                kept += len(said)
                skipped += len(wrote)

        elif tag == "delete":
            # Spoken, but not in the script — an aside, a repeated word, an
            # "um". It was said, so it stays.
            output.extend(_place(said, said_cues))
            added += len(said)

        elif tag == "insert":
            # In the script, but never spoken. It does not become a subtitle:
            # there is no audio under it, and inventing one would caption
            # silence.
            skipped += len(wrote)

    # Anything after the last opcode (only reachable when a boundary landed
    # mid-word) still belongs to the track.
    if spoken_cursor < len(spoken):
        output.extend(
            _place(spoken[spoken_cursor:], spoken_cue[spoken_cursor:])
        )
        added += len(spoken) - spoken_cursor

    rebuilt = _rebuild(source, output, max_chars=max_chars, max_lines=max_lines)

    if not rebuilt:
        # Belt and braces: alignment must never empty a track. If it somehow
        # did, the transcription is the answer.
        return source, _report(
            applied=False,
            status="unmatched",
            similarity=similarity,
            coverage=coverage,
            message=(
                "The script could not be lined up with this recording, so the "
                "subtitles are exactly as transcribed."
            ),
        )

    differences = kept + skipped + added
    share = differences / max(1, len(written_keys))
    notable = differences >= WARN_DIFFERENCE_WORDS and share >= WARN_DIFFERENCE_SHARE

    status = "aligned" if coverage >= 0.85 and not notable else "partial"

    return rebuilt, _report(
        applied=True,
        status=status,
        similarity=similarity,
        coverage=coverage,
        matched_words=matched,
        corrected_words=corrected,
        kept_words=kept,
        skipped_words=skipped,
        added_words=added,
        message=_message(corrected, kept, skipped, added),
        warning=(
            "Some differences were found between your script and the spoken "
            "audio. Subtitle timing is based on the audio, and significant "
            "spoken differences were preserved."
            if notable
            else None
        ),
    )


def _place(words: list[str], cue_indices: list[int]) -> list[tuple[str, int]]:
    """Attach words to the cues the run they replace was spoken in.

    Usually a run sits inside one cue and every word goes there. When it spans
    a cue boundary the words are dealt out in proportion, so a correction that
    covers the seam between two cues does not dump all of its text into the
    first one and leave the second silent.
    """
    if not words:
        return []
    if not cue_indices:
        return []
    if len(set(cue_indices)) == 1:
        return [(word, cue_indices[0]) for word in words]

    spread = len(cue_indices)
    return [
        (word, cue_indices[min(spread - 1, index * spread // len(words))])
        for index, word in enumerate(words)
    ]


def _rebuild(
    source: list[dict], output: list[tuple[str, int]], *, max_chars: int, max_lines: int
) -> list[dict]:
    """Put the aligned words back on the timings they came from.

    The rebuilt segments go through `cues_from_segments`, which is the same
    function the plain transcription path uses — so an aligned track and a
    transcribed one are wrapped and split by identical rules, and "was a script
    involved" is not something a downstream consumer can tell from the shape of
    the cues.
    """
    by_cue: dict[int, list[str]] = {}
    for word, cue_index in output:
        by_cue.setdefault(cue_index, []).append(word)

    segments = [
        {"start": cue["start"], "end": cue["end"], "text": " ".join(by_cue[index])}
        for index, cue in enumerate(source)
        if by_cue.get(index)
    ]

    return engine.cues_from_segments(
        segments, max_chars_per_line=max_chars, max_lines=max_lines
    )


def _message(corrected: int, kept: int, skipped: int, added: int) -> str:
    """One sentence saying what the script actually changed."""
    parts: list[str] = []
    if corrected:
        parts.append(f"{corrected} word{'' if corrected == 1 else 's'} corrected from your script")
    if kept:
        parts.append(f"{kept} kept as spoken")
    if added:
        parts.append(f"{added} spoken but not in the script")
    if skipped:
        parts.append(f"{skipped} in the script but not spoken")

    if not parts:
        return "Your script matched the audio exactly. Nothing needed changing."
    return "Timing is from the audio. " + ", ".join(parts) + "."


def _report(
    *,
    applied: bool,
    status: str,
    similarity: float,
    coverage: float = 0.0,
    matched_words: int = 0,
    corrected_words: int = 0,
    kept_words: int = 0,
    skipped_words: int = 0,
    added_words: int = 0,
    message: str | None = None,
    warning: str | None = None,
) -> dict:
    return {
        "applied": applied,
        "status": status,
        "similarity": round(float(similarity), 4),
        "coverage": round(float(coverage), 4),
        "matched_words": matched_words,
        "corrected_words": corrected_words,
        "kept_words": kept_words,
        "skipped_words": skipped_words,
        "added_words": added_words,
        "message": message,
        "warning": warning,
    }
