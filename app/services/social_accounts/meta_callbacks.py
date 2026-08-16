"""Meta's `signed_request` — the payload behind deauthorize / data-deletion.

Meta calls an app's uninstall and delete callbacks with a single form field:

    signed_request = base64url(signature) + "." + base64url(payload)

where `signature` is HMAC-SHA256 of the *encoded payload string* keyed with the
app secret, and `payload` is JSON carrying at least `user_id` and `issued_at`.

Verifying that signature is the whole security boundary for these endpoints:
they are public by necessity (Meta calls them with no session), so an
unverified request is simply an anonymous POST claiming a user id. Only the
signature proves it came from Meta.

Comparison is constant-time, and nothing here ever logs the secret, the raw
`signed_request`, or the decoded payload.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from collections.abc import Iterable

logger = logging.getLogger(__name__)


def _b64url_decode(value: str) -> bytes:
    """Decode base64url, restoring the padding Meta strips."""
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def parse_signed_request(signed_request: str | None, app_secret: str | None) -> dict | None:
    """Return the payload if the signature verifies, else None.

    None covers every failure — malformed, wrong algorithm, bad signature, no
    configured secret — because the caller's response must not differ between
    them. A distinguishable error would turn the endpoint into an oracle for
    guessing valid payloads.
    """
    if not signed_request or not app_secret:
        return None

    try:
        encoded_sig, encoded_payload = signed_request.split(".", 1)
        signature = _b64url_decode(encoded_sig)
        payload = json.loads(_b64url_decode(encoded_payload))
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        logger.info("Meta callback: signed_request was malformed")
        return None

    if not isinstance(payload, dict):
        return None
    # Meta only signs with HMAC-SHA256; anything else is a downgrade attempt.
    if str(payload.get("algorithm", "")).upper().replace("-", "") != "HMACSHA256":
        logger.info("Meta callback: unexpected signed_request algorithm")
        return None

    expected = hmac.new(
        app_secret.encode("utf-8"), encoded_payload.encode("utf-8"), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(expected, signature):
        logger.warning("Meta callback: signed_request signature did not verify")
        return None

    return payload


def parse_signed_request_any(
    signed_request: str | None, app_secrets: Iterable[str | None]
) -> dict | None:
    """Verify against several app secrets; return the first payload that checks.

    Facebook/Instagram and Threads can live in separate Meta apps with separate
    secrets, while Meta gives an app a single data-deletion callback URL. One
    endpoint therefore has to be able to verify a call from either app, so every
    configured secret is tried and the request is rejected only if none matches.

    Order carries no meaning and no result is leaked between attempts, so this
    cannot be used to learn which app a signature belongs to.
    """
    for secret in app_secrets:
        payload = parse_signed_request(signed_request, secret)
        if payload is not None:
            return payload
    return None


def user_id_of(payload: dict | None) -> str | None:
    """The platform user id the request is about, as a string."""
    if not payload:
        return None
    user_id = payload.get("user_id")
    return str(user_id) if user_id else None
