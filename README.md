# Mausam Next-Gen — SIH26076

> **SIH Problem Statement ID:** SIH26076 · **Ministry:** Ministry of Earth Sciences (MoES) / IMD
> **One-liner:** Offline-first, crash-proof weather platform with Server-Driven UI, LinUCB personalization, and CAP disaster lifeline mode.

## Repository Layout

```
mausam-nextgen/
├── backend/            # FastAPI gateway, SDUI composer, LinUCB engine (Python 3.11+)
│   ├── app/
│   │   ├── main.py           # ASGI entrypoint
│   │   ├── core/             # Settings, logging
│   │   ├── models/           # Pydantic v2 WeatherContext canonical schemas
│   │   ├── routers/          # /health, /v1/weather, /v1/sdui, /v1/telemetry
│   │   └── services/         # Gateway adapters, SDUI composer, Bandit (Phase 1+)
│   ├── tests/          # Pytest suite
│   └── requirements.txt
├── mobile/             # Flutter 3.24+ client (Material 3, Hive, RxDart)
├── ml/                 # LinUCB bandit research, replay evaluation, priors
├── mock_fixtures/      # Authentic seed data for the offline demo harness
├── docs/               # Architecture decisions, pitch material
└── docker-compose.yml  # backend + Redis 7
```

## Quick Start (Backend)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows Git Bash: source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env           # optional; defaults work without Redis
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs for the interactive OpenAPI UI.

### Docker

```bash
docker compose up --build
```

Starts the FastAPI backend on :8000 and Redis 7 on :6379. The backend runs without Redis too — cache is a strict performance layer, not a dependency.

## Key API Surface (Phase 0)

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness + config summary (non-sensitive) |
| `GET /ready` | Redis/deps readiness probe |
| `GET /v1/weather/context?lat=&lon=` | Unified WeatherContext (live-first + fixture fallback) |
| `GET /v1/sdui/home?lat=&lon=&personas=health,commuter` | Persona-ranked SDUI widget nodes; Brotli + ETag/304 |
| `POST /v1/telemetry/interaction` | Bandit reward ingestion stub (204, Phase 5 wires logic) |

The SDUI contract lives in `contracts/sdui_v1.schema.json` — backend composer and
Flutter registry both implement it; unknown widget types degrade gracefully on the client.

## Environment Variables

See `backend/.env.example`. Highlights: `API_MODE` (`LIVE`/`HYBRID`/`SEED`), `REDIS_URL`, `LIVE_TIMEOUT_MS`.

## Development Conventions

- **Python ≥ 3.11**, Pydantic v2, async-first, type hints everywhere.
- **Mobile:** Flutter 3.24+, Material 3, `hive_ce` (not deprecated `hive`), official `maplibre_gl`.
- Every phase in `MASTER_TASK_LIST.md` has acceptance criteria — run the relevant test before checking off.
- Commit style: `feat:`, `fix:`, `chore:`, `docs:` prefixes.
