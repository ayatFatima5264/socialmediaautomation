"""The model identifiers the app ships with.

A retired model ID is the quietest kind of broken: the config loads, the app
boots, the key is present, and the request is answered with a 404 that names
the model rather than the thing the user did. QA hit exactly this — the primary
provider was decommissioned, every generation fell through to a backup, and
nothing in the UI said why the backup was always being used.

These tests cannot check Google's and Groq's live catalogues — that needs
network and an API key, and a test that fails when a vendor has an outage is a
test people learn to ignore. So they check the two things that *are* ours to
get right: that the identifiers are ones we have confirmed answer, and that
every file which states a default states the same one.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.config import Settings, settings

REPO_ROOT = Path(__file__).resolve().parent.parent

# The value the code ships with, before any `.env` is read. Separated from
# `settings` on purpose: the effective value depends on the machine, and a
# machine with a stale `.env` must not be able to make the shipped default look
# wrong. `test_the_running_config_is_not_on_a_retired_model` covers that case.
SHIPPED = {
    "gemini_model": Settings.model_fields["gemini_model"].default,
    "groq_model": Settings.model_fields["groq_model"].default,
}

# Confirmed retired, with the live call that proved it. Kept as a list because
# the failure mode is a re-paste from an old branch or an old tutorial, and a
# named entry is easier to recognise than a pattern.
RETIRED = {
    "gemini-2.0-flash": "Google retired it; the call returns 404 "
    "`models/gemini-2.0-flash is not found`.",
    "llama-3.3-70b-versatile": "decommissioned on Groq; the call returns 404 "
    "`model_not_found`.",
}


def env_models(path: Path) -> dict[str, str]:
    """`FOO=bar` pairs in an env file, comments and blanks skipped."""
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        found[key.strip()] = value.strip()
    return found


ENV_FILES = [
    pytest.param(REPO_ROOT / ".env.example", id=".env.example"),
    pytest.param(
        REPO_ROOT / ".env.production.example", id=".env.production.example"
    ),
]


@pytest.mark.parametrize("name", sorted(RETIRED), ids=lambda name: name)
def test_a_retired_model_is_not_the_shipped_default(name: str):
    assert SHIPPED[_key_for(name)] != name, (
        f"{name} is the default in config.py again. {RETIRED[name]}"
    )


@pytest.mark.parametrize("name", sorted(RETIRED), ids=lambda name: name)
def test_a_retired_model_is_not_stated_in_an_env_example(name: str):
    for path in (REPO_ROOT / ".env.example", REPO_ROOT / ".env.production.example"):
        values = env_models(path)
        for key, value in values.items():
            if not key.endswith("_MODEL"):
                continue
            assert value != name, f"{path.name} ships {key}={name}. {RETIRED[name]}"


@pytest.mark.parametrize("name", sorted(RETIRED), ids=lambda name: name)
def test_the_running_config_is_not_on_a_retired_model(name: str):
    """The effective value, `.env` included.

    This is the assertion that would have caught QA's finding, because a local
    `.env` pinning a decommissioned id keeps every generation on the fallback
    provider while the code in front of you looks correct.
    """
    assert getattr(settings, _key_for(name)) != name, (
        f"this machine is running on {name}. {RETIRED[name]} "
        f"Fix the *_MODEL line in your .env."
    )


def _key_for(model: str) -> str:
    return "gemini_model" if model.startswith("gemini") else "groq_model"


@pytest.mark.parametrize("path", ENV_FILES)
def test_the_example_env_files_agree_with_the_shipped_defaults(path: Path):
    """A `.env.example` that disagrees with `config.py` is worse than neither:
    a new install copies the example, and the example is what they read to find
    out what the option does."""
    values = env_models(path)

    assert values.get("GEMINI_MODEL") == SHIPPED["gemini_model"]
    assert values.get("GROQ_MODEL") == SHIPPED["groq_model"]


def test_the_model_ids_are_well_formed():
    """Cheap shape checks. These catch a truncated paste or a stray quote that
    the provider would reject at request time."""
    for value in SHIPPED.values():
        assert re.fullmatch(r"[a-z0-9][a-z0-9.\-/]*", value), (
            f"unexpected model id: {value!r}"
        )
    assert "/" not in SHIPPED["gemini_model"], (
        "Gemini ids are unprefixed; a vendor prefix here 404s"
    )
