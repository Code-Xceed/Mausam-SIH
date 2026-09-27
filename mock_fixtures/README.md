# mock_fixtures/ — Authentic Seed Data (Demo Harness)

Fixtures replayed by the backend when `API_MODE=SEED`, or on live-timeout
in `HYBRID` mode (TASK-014/015). Timestamps are **retimed to "now"** at
load by `backend/app/services/gateway.py::_retime_fixture`, so demos never
look stale.

| File | Coverage | Status |
|---|---|---|
| `weather_context_delhi.json` | Delhi: haze, AQI 187, evening thunderstorm (health persona) | ✅ Phase 0 |
| `weather_context_kochi.json` | Kochi: swell 12s / 1.1m, yellow flag (surfer persona) | ✅ Phase 1 |
| `weather_context_vidarbha.json` | Vidarbha: GKMS crop advisories, soil 18% (farmer persona) | ✅ Phase 1 |
| `weather_context_mumbai.json` | Mumbai: heavy rain, Severe nowcast, red flag (commuter persona) | ✅ Phase 1 |
| `weather_context_shimla.json` | Shimla: 11°C mist, 900m visibility (mountain variety) | ✅ Phase 1 |
| `cap_alerts.xml` | NDMA CAP: Severe cyclone polygon (Konkan) + Moderate rainfall polygon | ✅ Phase 1 |

Fixture quality bar: values must be *plausible*, not random — a meteorology
judge should not be able to spot them as fake at a glance.
