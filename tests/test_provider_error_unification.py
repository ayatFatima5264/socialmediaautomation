"""Tests for BUG-09: one status for a provider outage, everywhere.

The QA report found the same outage answering 422 from `/api/video/ai/*` and 502
from `/api/ads/*`, because six route modules each had their own mapper and five
of them fell through to 422 — "your request was unprocessable" — for a failure
the caller had nothing to do with.

`app.api_errors` is now the single place that decides status and message. These
tests pin the two things that matter:

  * a provider fault answers 502 from every route, including the ones that
    reach it wrapped in a service error;
  * a genuine input problem is still 422, so the fix did not flatten the
    distinction the other way.

Nothing here touches the network: the provider is either patched or the error is
raised directly.
"""
from __future__ import annotations

import re

import pytest

from app.api_errors import classify, provider_failure, provider_http_error
from app.services.providers.base import ProviderConfigError, ProviderError
from app.services.video import scripting
from app.services.video.metering import UsageLimitExceeded
from app.services.video.providers.base import (
    MediaProviderConfigError,
    MediaProviderError,
    UnsupportedVoiceError,
)

BRIEF = {
    "topic": "Why sleep beats a second coffee",
    "tone": "friendly",
    "audience": "people in their twenties",
    "duration_seconds": 30,
    "platform": "youtube_shorts",
    "content_type": "educational",
    "instructions": "Use one concrete example.",
    "visual_mode": "natural",
}


# ---------------------------------------------------------------------------
# The mapping itself.
# ---------------------------------------------------------------------------


def test_a_provider_failure_is_502():
    assert classify(ProviderError("503 from groq")).status_code == 502
    assert classify(MediaProviderError("connection reset")).status_code == 502


def test_a_missing_key_is_503():
    """The operator has to act, so retrying is pointless."""
    failure = classify(ProviderConfigError("GROQ_API_KEY is not set"))
    assert failure.status_code == 503
    # The detail survives: knowing *which* key is the whole point.
    assert "GROQ_API_KEY" in failure.message


def test_a_quota_is_429():
    assert classify(UsageLimitExceeded("out of credits", 5, 5)).status_code == 429


def test_an_unsupported_voice_stays_422():
    """The one caller-correctable provider error. Flipping this to 502 would
    tell someone to retry a request that can never succeed."""
    assert classify(UnsupportedVoiceError("no voice 'x'")).status_code == 422


def test_the_message_does_not_echo_the_upstream():
    """A provider's response body is not ours to hand back — it can carry
    internals, or something shaped like a key."""
    failure = classify(ProviderError("401: bad key sk-live-abcdef123456"))
    assert "sk-live" not in failure.message
    assert failure.status_code == 502


# ---------------------------------------------------------------------------
# Finding the outage through a service wrapper.
# ---------------------------------------------------------------------------


def test_a_wrapped_outage_is_still_a_provider_fault():
    """`scripting` wraps rather than re-raises, so the outage reaches the route
    wearing a ScriptError. Reading only the outer type is what made this 422."""
    try:
        try:
            raise ProviderError("503 Service Unavailable from groq")
        except ProviderError as exc:
            raise scripting.ScriptError(f"The script could not be generated: {exc}") from exc
    except scripting.ScriptError as exc:
        assert provider_failure(exc).status_code == 502


def test_a_bare_service_error_is_not_a_provider_fault():
    """A brief with no topic is the caller's to fix, and there is no provider
    error anywhere behind it — so the route keeps its own 422."""
    try:
        scripting.build_brief(topic="")
    except scripting.ScriptError as exc:
        assert provider_failure(exc) is None
    else:
        pytest.fail("an empty topic should have been rejected")


def test_the_voice_service_keeps_the_cause():
    """The gap that let a voice outage keep answering 422.

    `generate_voice` collects the failure in `last_error` and raises after the
    fallback loop. That raise had no `from`, so the chain ended there and
    `provider_fault` found nothing — the outage was indistinguishable from a
    bad request, in the one route whose whole job is to be reliable.
    """
    import inspect

    from app.services.video import voice as voice_service

    source = inspect.getsource(voice_service)
    assert "raise VoiceError(message) from last_error" in source, (
        "the voice service drops the provider cause again; an outage will be "
        "reported as 422"
    )


def test_a_cyclic_cause_chain_terminates():
    """A hand-built `a.__cause__ = b; b.__cause__ = a` must not hang a request."""
    first = ProviderError("a")
    second = ProviderError("b")
    first.__cause__ = second
    second.__cause__ = first
    assert provider_failure(first).status_code == 502


# ---------------------------------------------------------------------------
# The routes agree.
# ---------------------------------------------------------------------------


def test_the_video_route_answers_502_not_422(studio_client, headers, monkeypatch):
    """The exact regression: a Groq outage behind the script generator.

    Before this change `/api/video/ai/script` answered 422 and `/api/ads/copy`
    answered 502 for the same outage, so a client could not tell a retryable
    fault from a malformed request.
    """
    async def _outage(*_args, **_kwargs):
        try:
            raise ProviderError("503 Service Unavailable from groq")
        except ProviderError as exc:
            raise scripting.ScriptError(f"The script could not be generated: {exc}") from exc

    monkeypatch.setattr(scripting, "generate_script", _outage)

    response = studio_client.post("/api/video/ai/script", headers=headers, json=BRIEF)

    assert response.status_code == 502, response.text
    assert response.headers.get("X-Error-Code") == "provider_unavailable"


def test_the_ads_route_answers_the_same(studio_client, headers, monkeypatch):
    """The other side of the same outage, asserted against the video route so
    the two cannot drift apart again."""
    from app.services import ads_service

    async def _outage(*_args, **_kwargs):
        raise ProviderError("503 Service Unavailable from groq")

    monkeypatch.setattr(ads_service, "generate_ad_copy", _outage)

    response = studio_client.post(
        "/api/ads/copy",
        headers=headers,
        json={
            "product": "Serum",
            "audience": "Women 25-40",
            "offer": "20% off",
            "platform": "facebook",
            "tone": "friendly",
            "cta": "Shop Now",
            "variants": 1,
        },
    )

    assert response.status_code == 502, response.text
    assert response.headers.get("X-Error-Code") == "provider_unavailable"


def test_a_missing_key_reads_the_same_from_both_routes(studio_client, headers, monkeypatch):
    """503 is the other half of the agreement."""
    from app.services import ads_service

    async def _unconfigured(*_args, **_kwargs):
        raise ProviderConfigError("GROQ_API_KEY is not set")

    async def _script_unconfigured(*_args, **_kwargs):
        # Wrapped the way the real service wraps it: `except ProviderError` also
        # catches the config subclass, so an unconfigured provider arrives as a
        # ScriptError with the real cause behind it.
        try:
            raise MediaProviderConfigError("GEMINI_API_KEY is not set")
        except MediaProviderConfigError as exc:
            raise scripting.ScriptError(f"The script could not be generated: {exc}") from exc

    monkeypatch.setattr(ads_service, "generate_ad_copy", _unconfigured)
    monkeypatch.setattr(scripting, "generate_script", _script_unconfigured)

    ads = studio_client.post(
        "/api/ads/copy",
        headers=headers,
        json={
            "product": "Serum",
            "audience": "Women 25-40",
            "offer": "20% off",
            "platform": "facebook",
            "tone": "friendly",
            "cta": "Shop Now",
            "variants": 1,
        },
    )
    video = studio_client.post("/api/video/ai/script", headers=headers, json=BRIEF)

    assert ads.status_code == video.status_code == 503
    assert ads.headers.get("X-Error-Code") == "provider_not_configured"
    assert video.headers.get("X-Error-Code") == "provider_not_configured"


def test_a_bad_request_is_still_422(studio_client, headers):
    """The other direction: fixing the provider mapping must not have turned
    every rejection into a 502.

    An empty body fails schema validation before any provider is reached, which
    is exactly why it must not depend on a key being configured.
    """
    response = studio_client.post("/api/ads/copy", headers=headers, json={})
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# No route grows a second opinion.
# ---------------------------------------------------------------------------


ROUTE_DIR = "app/routes"


def test_no_route_keeps_its_own_provider_mapping():
    """The six hand-written mappers are gone. A route that wants a provider
    status asks `app.api_errors`; it does not decide one itself."""
    from pathlib import Path

    offenders = []
    for path in Path(ROUTE_DIR).glob("*.py"):
        source = path.read_text(encoding="utf-8")
        # A route that catches a provider error and maps it by hand.
        if re_search_mapped(source):
            offenders.append(path.name)
    assert not offenders, f"still mapping provider errors by hand: {offenders}"


def re_search_mapped(source: str) -> bool:
    """True if the file both catches a provider error and returns a status for it
    without going through `app.api_errors`."""
    import re

    catches_provider = re.search(
        r"except[^:]*\b(ProviderError|ProviderConfigError|MediaProviderError|"
        r"MediaProviderConfigError|UsageLimitExceeded)\b",
        source,
    )
    if not catches_provider:
        return False
    # `raise http_error(exc)` / `provider_http_error(exc)` is the sanctioned path.
    if "from app.api_errors import" in source:
        return False
    return bool(re.search(r"status_code=50[23].*str\(exc\)", source))


def test_no_route_branches_on_the_error_taxonomy():
    """Routes may still *catch* a `ProviderError` — they have to name it to
    catch it. What they must not do is branch on its type to pick a status, since
    that is the second opinion `app.api_errors` replaced.

    `isinstance(exc, ProviderConfigError)` inside a route is the tell.
    """
    from pathlib import Path

    offenders = []
    for path in Path(ROUTE_DIR).glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r"isinstance\([^)]*Provider\w*Error", source):
            offenders.append(f"{path.name}: {match.group(0)}")
    assert not offenders, (
        "a route is choosing a status by error type again: " + ", ".join(offenders)
    )
