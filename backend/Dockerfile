# Mausam Next-Gen backend — FastAPI + Uvicorn
# Build context is the REPO ROOT (see docker-compose.yml), so fixture data
# at /mock_fixtures is available to the image without duplication.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Dependency layer first for build caching
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App + demo fixtures
COPY backend/app ./app
COPY mock_fixtures ./mock_fixtures

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
