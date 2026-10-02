"""The voice catalogue's cost.

`list_voices` is called on every render of Voice Studio and on every synthesis,
because the synthesiser has to know which provider owns the requested voice. It
also fans out to every provider in the chain. Those two facts together mean the
list page and the synthesise button are each waiting on a network round trip per
provider, including one whose catalogue is currently answering 401.

QA recorded Voice Studio's catalogue taking multiple seconds to appear. The fix
has two halves — ask the providers at the same time instead of in turn, and
remember the answer for a short while — and this file holds both down.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from app.services.video import voice as voice_service
from app.services.video.providers import MediaProviderError, Voice


class SlowProvider:
    """A provider whose catalogue takes `delay` seconds to answer."""

    def __init__(self, name: str, delay: float, voices: list[str] | None = None):
        self.name = name
        self.delay = delay
        self.calls = 0
        self._voices = [
            Voice(
                id=f"{name}-{index}",
                label=f"{name.title()} {index}",
                language="en-US",
                language_label="English (US)",
                gender="female",
                provider=self.name,
            )
            for index in (voices or [1])
        ]

    async def list_voices(self) -> list[Voice]:
        self.calls += 1
        await asyncio.sleep(self.delay)
        return list(self._voices)


class BrokenProvider(SlowProvider):
    async def list_voices(self) -> list[Voice]:
        self.calls += 1
        await asyncio.sleep(self.delay)
        raise MediaProviderError("401 unauthorised")


@pytest.fixture(autouse=True)
def clear_cache():
    voice_service.invalidate_voice_catalogue()
    yield
    voice_service.invalidate_voice_catalogue()


def install(monkeypatch, *providers):
    monkeypatch.setattr(
        "app.services.video.voice.get_tts_providers", lambda: list(providers)
    )


# ---------------------------------------------------------------------------
# At the same time, not in turn.
# ---------------------------------------------------------------------------


def test_a_slow_provider_does_not_delay_the_others(monkeypatch):
    """Serially, the page waits for the sum of every provider's round trip.

    The two delays are equal on purpose: with one fast and one slow provider,
    asking them together and asking them in turn differ by the fast provider's
    time, which is too small to assert on. Three equal ones differ by a factor
    of three, and the assertion below sits between the two answers.
    """
    providers = [SlowProvider(f"p{index}", 0.3) for index in range(3)]
    install(monkeypatch, *providers)

    started = time.monotonic()
    voices = asyncio.run(voice_service.list_voices())
    elapsed = time.monotonic() - started

    assert {voice.provider for voice in voices} == {"p0", "p1", "p2"}, (
        "a slow provider must not remove the other voices"
    )
    assert elapsed < 0.6, (
        f"took {elapsed:.2f}s for three 0.3s providers — "
        f"that is {elapsed / 0.3:.1f} round trips, so they were asked in turn"
    )


def test_every_provider_is_still_asked_when_one_fails(monkeypatch):
    """Failure and order are separate concerns: a broken catalogue is skipped,
    and it does not stop the chain."""
    broken = BrokenProvider("broken", 0.01)
    working = SlowProvider("working", 0.01)

    install(monkeypatch, broken, working)

    voices = asyncio.run(voice_service.list_voices())

    assert broken.calls == 1
    assert working.calls == 1
    assert [voice.provider for voice in voices] == ["working"]


# ---------------------------------------------------------------------------
# Remembered, briefly.
# ---------------------------------------------------------------------------


def test_the_catalogue_is_asked_for_once_not_once_per_view(monkeypatch):
    provider = SlowProvider("edge", 0.01)
    install(monkeypatch, provider)

    first = asyncio.run(voice_service.list_voices())
    second = asyncio.run(voice_service.list_voices())
    third = asyncio.run(voice_service.list_voices())

    assert provider.calls == 1, "three views, three catalogue round trips"
    assert [v.id for v in first] == [v.id for v in third]


def test_the_cached_list_is_a_copy(monkeypatch):
    """A caller that mutates the list it was given must not edit the cache for
    the next caller — the cache is shared, the list is not."""
    install(monkeypatch, SlowProvider("edge", 0.0, voices=[1, 2, 3]))

    first = asyncio.run(voice_service.list_voices())
    first.clear()

    assert len(asyncio.run(voice_service.list_voices())) == 3


def test_refresh_bypasses_the_cache(monkeypatch):
    """The reason the TTL is short, and the reason this escape hatch exists."""
    provider = SlowProvider("edge", 0.0)
    install(monkeypatch, provider)

    asyncio.run(voice_service.list_voices())
    asyncio.run(voice_service.list_voices(refresh=True))

    assert provider.calls == 2


def test_an_empty_catalogue_is_not_cached(monkeypatch):
    """Caching the failure would keep the dropdown empty for a minute after
    someone fixed the key that caused it."""
    broken = BrokenProvider("broken", 0.0)
    install(monkeypatch, broken)

    assert asyncio.run(voice_service.list_voices()) == []
    assert asyncio.run(voice_service.list_voices()) == []
    assert broken.calls == 2, "a failure was served from the cache"


def test_the_cache_expires(monkeypatch):
    """Not forever. A user who has just entered a key should not have to wait
    out a cache to see their voices."""
    provider = SlowProvider("edge", 0.0)
    install(monkeypatch, provider)

    asyncio.run(voice_service.list_voices())
    monkeypatch.setattr(voice_service, "_CATALOGUE_TTL_SECONDS", 0.0)
    asyncio.run(voice_service.list_voices())

    assert provider.calls == 2


def test_one_refresh_at_a_time(monkeypatch):
    """A burst of concurrent requests should cost one fan-out, not one each —
    that burst is the reason the cache exists."""
    provider = SlowProvider("edge", 0.05)
    install(monkeypatch, provider)

    async def burst():
        return await asyncio.gather(*(voice_service.list_voices() for _ in range(8)))

    results = asyncio.run(burst())

    assert provider.calls == 1, (
        f"{provider.calls} fan-outs for 8 concurrent requests — "
        f"the refresh lock is not being shared"
    )
    assert all(len(result) == 1 for result in results)


def test_every_caller_in_one_loop_shares_the_same_lock():
    """The bug the previous test catches, in the smallest form: a lock minted
    per caller is not a lock."""
    async def in_one_loop():
        first = voice_service._refresh_lock()
        second = voice_service._refresh_lock()
        await asyncio.sleep(0)
        return first is second

    assert asyncio.run(in_one_loop()) is True


def test_the_cache_survives_a_second_event_loop(monkeypatch):
    """The refresh lock must not be pinned to the first loop that awaited it.

    Each of those `asyncio.run` calls is a different loop, and an `asyncio.Lock`
    that remembers its first loop raises `is bound to a different event loop` on
    the second. Uvicorn would never show it; a test does, which is a cheap
    warning that the next caller might not.
    """
    provider = SlowProvider("edge", 0.0)
    install(monkeypatch, provider)

    for _ in range(3):
        assert len(asyncio.run(voice_service.list_voices())) == 1

    voice_service.invalidate_voice_catalogue()
    assert len(asyncio.run(voice_service.list_voices())) == 1


# ---------------------------------------------------------------------------
# The order is the same whichever way it was assembled.
# ---------------------------------------------------------------------------


def test_the_order_does_not_depend_on_which_provider_was_slowest(monkeypatch):
    """Featured languages first, then alphabetical. A concurrent fan-out makes
    arrival order arbitrary, so the sort cannot be left to it."""
    late = SlowProvider("late", 0.2)
    early = SlowProvider("early", 0.0)

    install(monkeypatch, late, early)
    concurrent = asyncio.run(voice_service.list_voices())

    install(monkeypatch, early, late)
    voice_service.invalidate_voice_catalogue()
    sequential_order_source = asyncio.run(voice_service.list_voices())

    assert [v.id for v in concurrent] == [v.id for v in sequential_order_source]
    assert [v.id for v in concurrent] == ["early-1", "late-1"]
