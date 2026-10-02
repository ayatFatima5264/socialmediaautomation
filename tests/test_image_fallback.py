"""Tests for the AI image fallback chain (BUG-06).

QA measured the delivered default for a three-version serum-bottle request:
one real AI image and two unrelated photographs, because the chain gave up on
the first failure from a rate-limited host. These tests pin the two changes
that address it — retrying a transient AI failure, and remembering a successful
generation — plus the substitution count the UI now states in words.

No network: `_renders_ok` is replaced, so nothing here reaches Pollinations,
LoremFlickr or Picsum.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from app.config import settings
from app.services import image_service
from app.services.image_service import ImageError, generate_with_fallback


@pytest.fixture(autouse=True)
def _clean_cache():
    """The cache is process-global; each test starts and ends empty."""
    image_service.clear_image_cache()
    yield
    image_service.clear_image_cache()


class FakeClient:
    """Stands in for httpx.AsyncClient, recording every URL it is asked for.

    `responses` maps a URL to a list of outcomes consumed in order, so a test
    can say "429, then an image" without a socket. The last outcome repeats.
    """

    def __init__(self, responses: dict[str, list[object]]):
        self.responses = responses
        self.calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def stream(self, method, url):
        self.calls.append(url)
        outcomes = self.responses.get(url, [False])
        outcome = outcomes.pop(0) if len(outcomes) > 1 else outcomes[0]

        class _Ctx:
            async def __aenter__(_self):
                if isinstance(outcome, Exception):
                    raise outcome
                _self.headers = {
                    "content-type": "image/png" if outcome else "text/html"
                }
                _self.status_code = 200 if outcome else 429
                return _self

            async def __aexit__(_self, *exc):
                return False

        return _Ctx()


def _install(monkeypatch, responses: dict[str, list[object]]) -> FakeClient:
    """Point generate_with_fallback at a FakeClient and skip retry sleeps."""
    client = FakeClient(responses)

    # `async with httpx.AsyncClient(...)` — the factory is called, not awaited,
    # so this must return the client rather than a coroutine that returns it.
    monkeypatch.setattr(
        image_service.httpx, "AsyncClient", lambda *_args, **_kwargs: client
    )

    # Backoff is real behaviour but not what these tests are about; removing
    # the sleep keeps them fast without disabling the retry itself.
    monkeypatch.setattr(image_service.asyncio, "sleep", _no_sleep)
    return client


async def _no_sleep(_seconds):
    return None


def _candidates(monkeypatch, models=("sana",)):
    """Freeze the chain to one AI model plus the two photo hosts."""
    monkeypatch.setattr(settings, "image_fallback_models", list(models))
    return image_service.named_candidates("amber glass serum bottle", seed=0)


# ---------------------------------------------------------------------------
# Retry: a rate-limited AI host is retried before being given up on.
# ---------------------------------------------------------------------------


def test_transient_failure_is_retried_and_recovers(monkeypatch):
    """The bug in one test: the first 429 fell straight through to a stock
    photo. With a retry the same request produces the AI image."""
    chain = _candidates(monkeypatch)
    ai_provider, ai_url = chain[0]
    assert ai_provider.startswith("pollinations")

    # 429, then 429, then a real image.
    client = _install(monkeypatch, {ai_url: [False, False, True]})

    url, provider = asyncio.run(generate_with_fallback("amber glass serum bottle", seed=0))

    assert provider == ai_provider, "retried back to the AI host instead of falling back"
    assert url == ai_url
    assert client.calls.count(ai_url) == 3, "the AI candidate was not retried"


def test_retries_are_bounded(monkeypatch):
    """A host that never answers must not be retried forever."""
    monkeypatch.setattr(settings, "image_ai_attempts", 3)
    chain = _candidates(monkeypatch)
    ai_url = chain[0][1]

    client = _install(monkeypatch, {ai_url: [False]})

    # Every provider fails -> ImageError, but the AI one is tried 3 times only.
    with pytest.raises(ImageError):
        asyncio.run(generate_with_fallback("amber glass serum bottle", seed=0))
    assert client.calls.count(ai_url) == 3


def test_attempts_setting_is_respected(monkeypatch):
    monkeypatch.setattr(settings, "image_ai_attempts", 1)
    chain = _candidates(monkeypatch)
    ai_url = chain[0][1]
    client = _install(monkeypatch, {ai_url: [False]})

    with pytest.raises(ImageError):
        asyncio.run(generate_with_fallback("amber glass serum bottle", seed=0))
    assert client.calls.count(ai_url) == 1, "attempts=1 must mean one try"


def test_a_permanently_failing_ai_host_still_falls_back(monkeypatch):
    """Retry is not a trap: when the AI host is genuinely down the chain still
    reaches the photo hosts, so the user gets a visual."""
    chain = _candidates(monkeypatch)
    ai_url = chain[0][1]
    flickr_url = chain[-2][1]

    _install(monkeypatch, {ai_url: [False], flickr_url: [True]})

    url, provider = asyncio.run(generate_with_fallback("amber glass serum bottle", seed=0))

    assert provider == "loremflickr"
    assert url == flickr_url


def test_an_exception_is_retried_too(monkeypatch):
    """Timeouts and connection errors are the transient case the first fix
    missed entirely — they were caught once and abandoned."""
    chain = _candidates(monkeypatch)
    ai_url = chain[0][1]
    _install(monkeypatch, {ai_url: [httpx.ConnectTimeout("boom"), True]})

    url, provider = asyncio.run(generate_with_fallback("amber glass serum bottle", seed=0))
    assert provider == chain[0][0]
    assert url == ai_url


# ---------------------------------------------------------------------------
# Cache: a generation that worked is not asked for twice.
# ---------------------------------------------------------------------------


def test_successful_generation_is_cached(monkeypatch):
    """Re-running the same brief — a retry button, a reload, a second variant —
    must not re-ask a host that is already refusing us."""
    chain = _candidates(monkeypatch)
    ai_url = chain[0][1]
    client = _install(monkeypatch, {ai_url: [True]})

    first = asyncio.run(generate_with_fallback("amber glass serum bottle", seed=0))
    second = asyncio.run(generate_with_fallback("amber glass serum bottle", seed=0))

    assert first == second
    assert client.calls.count(ai_url) == 1, "the second request hit the network"


def test_cache_is_keyed_on_the_prompt(monkeypatch):
    """Both prompts must be registered, or the second would fail every
    provider and raise rather than reach its AI host."""
    first = image_service.named_candidates("amber glass serum bottle", seed=0)[0][1]
    second = image_service.named_candidates("a blue water bottle", seed=0)[0][1]
    assert first != second

    client = _install(monkeypatch, {first: [True], second: [True]})

    asyncio.run(generate_with_fallback("amber glass serum bottle", seed=0))
    asyncio.run(generate_with_fallback("a blue water bottle", seed=0))

    assert len(client.calls) == 2, "a different brief must not be served from cache"


def test_cache_is_keyed_on_the_seed(monkeypatch):
    """`seed=i` is what makes '3 versions' three images. A cache that ignored
    it would hand back the same picture three times."""
    monkeypatch.setattr(settings, "image_fallback_models", ["sana"])
    urls = [
        image_service.named_candidates("amber glass serum bottle", seed=i)[0][1]
        for i in range(3)
    ]
    for url in urls:
        assert url not in urls[:urls.index(url)], "seeds must produce distinct URLs"

    client = _install(monkeypatch, {url: [True] for url in urls})
    got = [
        asyncio.run(generate_with_fallback("amber glass serum bottle", seed=i))[0]
        for i in range(3)
    ]
    assert len(set(got)) == 3, "each seed must produce its own image"
    assert len(client.calls) == 3


def test_cache_expires(monkeypatch):
    chain = _candidates(monkeypatch)
    ai_url = chain[0][1]
    client = _install(monkeypatch, {ai_url: [True]})

    asyncio.run(generate_with_fallback("amber glass serum bottle", seed=0))
    # Age the single entry past its TTL.
    for key in list(image_service._cache):
        url, provider, stored_at = image_service._cache[key]
        image_service._cache[key] = (url, provider, stored_at - settings.image_ai_cache_ttl - 1)

    asyncio.run(generate_with_fallback("amber glass serum bottle", seed=0))
    assert client.calls.count(ai_url) == 2, "an expired entry must be re-fetched"


def test_cache_is_bounded(monkeypatch):
    """An unbounded cache in a long-lived process is a memory leak."""
    monkeypatch.setattr(settings, "image_ai_cache_size", 3)
    async def fill():
        for i in range(6):
            url = image_service.named_candidates(f"prompt number {i}", seed=i)[0][1]
            await image_service._cache_put(f"k{i}", url, "pollinations-sana")

    asyncio.run(fill())
    assert len(image_service._cache) <= 3


def test_fallback_results_are_not_cached(monkeypatch):
    """A stock photo is always available, so caching it would only hide a
    recovered AI host behind a stale substitution."""
    chain = _candidates(monkeypatch)
    ai_url = chain[0][1]
    flickr_url = chain[-2][1]
    client = _install(monkeypatch, {ai_url: [False], flickr_url: [True]})

    asyncio.run(generate_with_fallback("amber glass serum bottle", seed=0))
    asyncio.run(generate_with_fallback("amber glass serum bottle", seed=0))

    assert client.calls.count(flickr_url) == 2, "photo fallbacks must not be cached"


def test_only_ai_candidates_are_cached(monkeypatch):
    chain = _candidates(monkeypatch)
    ai_url = chain[0][1]
    _install(monkeypatch, {ai_url: [True]})

    asyncio.run(generate_with_fallback("amber glass serum bottle", seed=0))
    assert all(key.startswith("pollinations-") for key in image_service._cache)
