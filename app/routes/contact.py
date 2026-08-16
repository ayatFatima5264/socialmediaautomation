"""Public contact-form endpoint.

    POST /api/contact  — accept a message from the marketing site's form

The contract the marketing site depends on: a 200 here means the message is
committed to the database. Notifying the team by email is attempted after the
commit and is allowed to fail — see app/models/contact_message.py for why that
ordering matters.

No authentication: the form is on a public page, and requiring an account
defeats its purpose. Abuse is handled by three cheap defences instead — a
per-IP rate limit, a honeypot field, and the schema's length caps.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.contact_message import ContactMessage
from app.schemas.contact import ContactAccepted, ContactCreate
from app.services import email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["contact"])

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
# In-process and intentionally so: this is a low-traffic public form, and a
# Redis dependency for it would be more moving parts than the thing it guards.
# The consequences are worth stating plainly — the window resets on deploy, and
# each instance counts separately, so a multi-instance deploy allows N times the
# limit. Both are acceptable for "stop a bot hammering the form"; neither would
# be acceptable for, say, login throttling.
_RATE_LIMIT = 5           # submissions...
_RATE_WINDOW = 60 * 60    # ...per IP per hour

_hits: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    """Best-effort client IP.

    Render and Vercel both put the real address first in X-Forwarded-For, and
    the socket peer is a load balancer. Falls back to the peer when the header
    is absent (direct local requests).
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def _rate_limited(ip: str) -> bool:
    """Record this attempt and report whether the caller is over the limit."""
    now = time.monotonic()
    window = _hits[ip]
    while window and now - window[0] > _RATE_WINDOW:
        window.popleft()
    if len(window) >= _RATE_LIMIT:
        return True
    window.append(now)

    # Drop IPs whose windows have emptied, so the dict can't grow without
    # bound on a long-running process.
    if len(_hits) > 2048:
        for key in [k for k, v in _hits.items() if not v]:
            del _hits[key]
    return False


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/contact",
    response_model=ContactAccepted,
    status_code=status.HTTP_200_OK,
    summary="Send a message from the public contact form",
)
def submit_contact(
    data: ContactCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> ContactAccepted:
    ip = _client_ip(request)

    # A filled honeypot is a bot. Answer exactly as we would a real submission
    # so it cannot detect the trap, but store nothing.
    if data.website:
        logger.info("Contact honeypot triggered from %s — discarded", ip)
        return ContactAccepted()

    if _rate_limited(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many messages from this address. Please try again later, "
            "or email us directly.",
        )

    row = ContactMessage(
        name=data.name,
        email=str(data.email),
        message=data.message,
        ip_address=ip,
        user_agent=(request.headers.get("user-agent") or "")[:400] or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # Best-effort notification. A failure here is logged and recorded on the
    # row; it never turns a stored message into an error for the submitter.
    sent = email_service.send_contact_notification(
        name=row.name, email=row.email, message=row.message
    )
    if sent != row.emailed:
        row.emailed = sent
        db.commit()

    return ContactAccepted()
