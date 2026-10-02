"""The one place that decides what a provider failure looks like over HTTP.

The QA report found the same outage answering 422 from one route and 502 from
another, because six route modules each had their own hand-written mapper:

    video_ai._http        503 / 429 / 422
    video_repurpose._http 503 / 429 / 422
    video_subtitles._http 429 / 503 / 502 / 422
    video_voice._http     429 / 503 / 502 / 422
    ads._guard            503 / 502
    posts                 three inline copies of 503 / 502

All of them agreed on 503 for an unconfigured provider and all of them fell
through to **422** — "your request was unprocessable" — when the provider itself
failed at request time. The caller had typed nothing wrong, so 422 was the wrong
answer for them, and a client that retries on 5xx would give up on a fault that
retrying fixes.

The mapping, and the reason for each:

    503  the deployment is missing something (no API key)
         -> retrying cannot help; the operator has to act
    429  the account or the app hit a quota
         -> retryable, but only after a wait
    502  the provider failed at request time
         -> the dependency let us down, not the user
    422  the request itself is unprocessable
         -> kept for `UnsupportedVoiceError`, where the caller really did ask
            for something impossible. Everything else that reaches here is a
            provider fault and is never 422.

That last line is the one that changes behaviour: a generic provider failure was
422 in five of the six mappers and is now 502 everywhere.

Two rules make the agreement hold in practice:

  * the chain is followed, so a service that wrapped the provider error
    (`raise ScriptError(...) from exc`) still reports the outage as one;
  * `UnsupportedVoiceError` stays 422, because that one really is the caller's
    input to correct.

Nothing here echoes an upstream response body back to the client. The full
exception is logged instead, so operators keep the detail and a caller cannot
be handed a provider's internals — or anything that looked like a key.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import HTTPException

from app.services.providers.base import ProviderConfigError, ProviderError
from app.services.video.metering import UsageLimitExceeded
from app.services.video.providers.base import (
    MediaProviderConfigError,
    MediaProviderError,
    UnsupportedVoiceError,
)

log = logging.getLogger(__name__)

#: Stable machine-readable code per status, so a client can branch on the
#: reason without parsing an English sentence.
CONFIG_ERROR_CODE = "provider_not_configured"
USAGE_ERROR_CODE = "usage_limit_exceeded"
UNSUPPORTED_VOICE_CODE = "unsupported_voice"
UPSTREAM_ERROR_CODE = "provider_unavailable"
EMPTY_OUTPUT_CODE = "provider_empty_response"


@dataclass(frozen=True)
class ProviderFailure:
    """A provider fault, resolved to something safe to send over HTTP."""

    status_code: int
    message: str
    code: str


def classify(exc: Exception) -> ProviderFailure:
    """Decide the status and the message for a provider fault.

    Order matters: the config and usage errors are subclasses of the general
    provider errors, so they have to be tested for first.
    """
    if isinstance(exc, (ProviderConfigError, MediaProviderConfigError)):
        # The detail is safe and is the whole point: an operator needs to know
        # *which* key is missing, and it is our own message saying so.
        return ProviderFailure(
            status_code=503,
            message=str(exc) or "This deployment has no provider API key set.",
            code=CONFIG_ERROR_CODE,
        )

    if isinstance(exc, UsageLimitExceeded):
        return ProviderFailure(
            status_code=429,
            message=str(exc) or "You have reached this deployment's usage limit.",
            code=USAGE_ERROR_CODE,
        )

    if isinstance(exc, UnsupportedVoiceError):
        # The only genuine 422 here: the caller named a voice this deployment
        # cannot speak, which is their input to correct.
        return ProviderFailure(
            status_code=422,
            message=str(exc) or "That voice is not available on this deployment.",
            code=UNSUPPORTED_VOICE_CODE,
        )

    log.warning("provider request failed", exc_info=exc)
    return ProviderFailure(
        status_code=502,
        message="The AI provider didn't return a usable response. Try again.",
        code=UPSTREAM_ERROR_CODE,
    )


#: How far to follow `__cause__` / `__context__`. A provider failure is wrapped
#: at most once or twice on the way out; the cap is only there so a cycle in a
#: hand-built chain cannot hang a request.
CHAIN_LIMIT = 10


def provider_fault(exc: BaseException) -> Exception | None:
    """The provider error behind `exc`, or None if there isn't one.

    Services wrap a provider failure rather than re-raising it —

        except ProviderError as exc:
            raise ScriptError(f"The script could not be generated: {exc}") from exc

    — so the outage reaches the route wearing a `ScriptError`. Reading only the
    outermost type is what made `video_ai` answer 422 while `ads` answered 502
    for the same Groq outage. The chain is walked so both agree.

    The cause is also how a genuine input problem stays a 422: `build_brief`
    rejecting an empty topic raises a bare `ScriptError` with no provider error
    anywhere behind it, and that is correctly the caller's to fix.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    for _ in range(CHAIN_LIMIT):
        if current is None or id(current) in seen:
            return None
        seen.add(id(current))
        if isinstance(current, (ProviderError, MediaProviderError, UsageLimitExceeded)):
            return current
        current = current.__cause__ or current.__context__
    return None


def provider_failure(exc: Exception) -> ProviderFailure | None:
    """Classify `exc` if it is a provider fault, else None.

    None means "not a provider problem" — a missing asset, a revision conflict,
    an unusable edit. Those codes are route-specific and belong to the route.
    """
    fault = provider_fault(exc)
    return classify(fault) if fault is not None else None


def provider_http_error(exc: Exception) -> HTTPException | None:
    """`raise provider_http_error(exc) or ...` — None for non-provider errors."""
    failure = provider_failure(exc)
    if failure is None:
        return None
    return HTTPException(
        status_code=failure.status_code,
        detail=failure.message,
        headers={"X-Error-Code": failure.code},
    )


def http_error(exc: Exception) -> HTTPException:
    """`raise http_error(exc) from exc`, for routes that only catch provider errors.

    A type nobody registered is reported as 502 rather than 422: treating an
    unrecognised fault as the caller's fault is exactly the mistake this module
    exists to stop.
    """
    failure = provider_failure(exc) or classify(exc)
    return HTTPException(
        status_code=failure.status_code,
        detail=failure.message,
        headers={"X-Error-Code": failure.code},
    )


def empty_output(what: str) -> HTTPException:
    """A 200 whose body is empty because the model gave us nothing.

    Same class of fault as an upstream failure and the same status: the
    dependency answered, but with nothing usable in it.
    """
    return HTTPException(
        status_code=502,
        detail=f"The model returned no {what}.",
        headers={"X-Error-Code": EMPTY_OUTPUT_CODE},
    )
