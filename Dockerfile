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

# Install dependencies first so Docker layer-caches them across code changes.
# psycopg[binary] bundles its own libpq, so no extra system packages are needed.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Application code only (the backend does not need the frontend or tests).
COPY app ./app

# Most hosts inject the listening port via $PORT; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# Single instance: the background scheduler loop has no distributed lock, so
# running multiple replicas would double-publish scheduled posts.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
