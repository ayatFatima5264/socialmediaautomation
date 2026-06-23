"""FastAPI entrypoint for the Social Media SaaS backend.

Run from the project root (social-saas/):
    venv/Scripts/uvicorn app.main:app --reload
Then open http://localhost:8000/docs
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routes import auth, posts, schedule
from app.services.scheduler import scheduler_loop

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (dev convenience; use migrations in production).
    init_db()

    # Start the background auto-publish scheduler.
    stop_event = asyncio.Event()
    task = asyncio.create_task(scheduler_loop(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        await task


app = FastAPI(
    title="Social Media SaaS API",
    description="AI-powered multi-platform social post generation.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(posts.router)
app.include_router(schedule.router)


@app.get("/")
def home() -> dict:
    return {"status": "ok", "service": "social-saas", "docs": "/docs"}
