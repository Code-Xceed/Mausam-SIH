# Architecture Decisions — Mausam Next-Gen (SIH26076)

Status: living document. Each decision records *why*, since jury Q&A and
future teammates both ask that question.

## AD-001 — PostGIS deferred; CAP polygons via pure Python geometry

**Decision:** Docker stack is FastAPI + Redis only. When Phase 6 needs
polygon-vs-geohash checks, use `shapely` (pure Python, no DB).

**Why:** A fifth stateful component (Postgres+PostGIS) adds demo fragility
and ops overhead for a problem the standard library + shapely already
solves. Fewer moving parts = fewer 2am hackathon failures.

## AD-002 — Android-only for SIH

**Decision:** `mobile/` targets Android (minSDK 24) exclusively for the
hackathon. iOS directories exist but stay unconfigured.

**Why:** SIH judging happens on Android test devices. Splitting attention
to iOS doubles CI/device-matrix work for zero jury value. (DPR's iOS
target survives only as a post-hackathon line item.)

## AD-003 — `hive_ce`, not `hive`

**Decision:** Flutter local storage uses `hive_ce` (community edition).

**Why:** The original `hive` package is discontinued/maintenance-mode;
`hive_ce` keeps the same API with active fixes. Documented in pubspec.

## AD-004 — Fixture-first demo harness (API_MODE toggle)

**Decision:** `API_MODE=LIVE|HYBRID|SEED` env toggle. HYBRID (default)
will try live endpoints with a 1200ms budget, then fall back to
`mock_fixtures/`. Phase 0 ships SEED/HYBRID with fixtures only; Phase 1
adds live adapters behind the same `WeatherGateway` facade.

**Why:** The #1 way SIH weather demos die is live government API failure
mid-pitch. The demo runs on SEED with airplane mode on; HYBRID proves the
live path exists. Fixtures are retimed at load (`_retime_fixture`) so
timestamps are always "now" — judges never see stale data.

## AD-005 — Category fields are derived, never trusted

**Decision:** `AirQualityIndex.category` is a Pydantic `computed_field`
derived from the integer AQI via the official CPCB bucket table. Adapters
must not pass upstream category strings through.

**Why:** Upstream feeds disagree on bucketing; deriving client-visible
buckets server-side keeps every persona threshold and UI color decision
consistent.

## AD-006 — Cache is a performance layer, not a dependency

**Decision:** The backend boots, serves fixtures, and passes tests with
Redis absent. `Cache` no-ops gracefully and `/ready` reports the state.

**Why:** `docker compose up` should be the *fast* path, not the only path.
A dead Redis must never take the demo down with it.
