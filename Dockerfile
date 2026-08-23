# ---------------------------------------------------------------------------
# AutoSocial AI — backend (FastAPI + Uvicorn) production image.
# Portable: runs on Render, Railway, Fly.io, or any VPS/container host.
#
#   docker build -t autosocial-api .
#   docker run -p 8000:8000 --env-file .env.production autosocial-api
#
# The app reads all configuration from environment variables (see
# .env.production.example) — never bake secrets into the image.
# ---------------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Video Studio is not pure Python. Every upload is probed, every render and
# export is encoded, and every caption and thumbnail is drawn — all of it by
# these two packages, neither of which python:*-slim ships:
#
#   ffmpeg            the ffmpeg and ffprobe binaries the whole video pipeline
#                     shells out to. Without it an upload fails at the probe,
#                     so nothing downstream ever runs.
#   fonts-dejavu-core DejaVuSans / DejaVuSans-Bold. Every font family the
#                     compositor and the thumbnail renderer offer falls back to
#                     DejaVu, so with no fonts installed `drawtext` draws
#                     nothing and text layers come out blank.
#
# Installed before the Python dependencies so this layer caches across code and
# requirements changes alike.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first so Docker layer-caches them across code changes.
# psycopg[binary] bundles its own libpq, so no extra system packages are needed.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Application code only (the backend does not need the frontend or tests).
COPY app ./app

# Migrations ship with the image. app.database.run_migrations() calls
# `alembic upgrade head` on startup — this container is the only place a
# migration can run, because Render has no release phase. Without these two the
# call finds no alembic.ini, logs a warning and skips, and the Video Studio
# tables silently never exist in production.
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations

# Most hosts inject the listening port via $PORT; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# Single instance: the background scheduler loop has no distributed lock, so
# running multiple replicas would double-publish scheduled posts.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
