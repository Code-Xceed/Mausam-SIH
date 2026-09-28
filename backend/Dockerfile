# Mausam Next-Gen backend — FastAPI + Uvicorn
# Python 3.12: numpy 2.5.x requires >=3.12, and CI (setup-python 3.12) verifies
# these pins on 3.12. Build context is the REPO ROOT (see render.yaml), so
# fixture data at /mock_fixtures is available to the image without duplication.
FROM python:3.12-slim AS base

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

# Single worker: alert_store + CAP poller are in-memory per process —
# multiple workers would split-brain the alert state on a single instance.
# PORT is injected by most hosts (Render/Railway); 8000 is the local default.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
