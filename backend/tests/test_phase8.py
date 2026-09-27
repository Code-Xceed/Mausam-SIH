"""Phase 8 backend tests — i18n (TASK-062), geo tiles/boundaries (TASK-059/060),
public alerts feed (TASK-055 data half), DPDP purge (TASK-072)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.alert_store import alert_store
from app.services.i18n import GLOSSARY, UI_STRINGS, translate_bundle, translate_text


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------- #
# TASK-062: i18n
# --------------------------------------------------------------------------- #


class TestI18n:
    def test_languages_endpoint(self, client: TestClient) -> None:
        data = client.get("/v1/i18n/languages").json()
        codes = [l["code"] for l in data["languages"]]
        assert set(codes) >= {"en", "hi", "ta", "bn", "te", "mr"}
        assert data["default"] == "en"

    def test_strings_bundle_hindi(self, client: TestClient) -> None:
        data = client.get("/v1/i18n/strings/hi").json()
        assert data["lang"] == "hi"
        assert data["strings"]["app_title"] != "Mausam Next-Gen"
        assert data["strings"]["offline_banner"] != UI_STRINGS["offline_banner"]["en"]
        # glossary maps conditions too
        assert data["glossary"]["rain"] != "rain"

    def test_strings_unknown_lang_404(self, client: TestClient) -> None:
        assert client.get("/v1/i18n/strings/xx").status_code == 404

    def test_glossary_translation_deterministic(self) -> None:
        assert translate_text("rain", "hi") == "बारिश"
        assert translate_text("rain", "hi") == translate_text("rain", "hi")
        assert translate_text("nonexistent-term", "hi") == "nonexistent-term"  # passthrough
        assert translate_text("rain", "en") == "rain"

    def test_bundle_translation_translates_leaves(self) -> None:
        out = translate_bundle({"condition": "rain", "nested": {"a": "Good"}}, "ta")
        assert out["condition"] == "மழை"
        assert out["nested"]["a"] == "நல்ல"

    def test_translate_endpoint_glossary(self, client: TestClient) -> None:
        res = client.post("/v1/i18n/translate", json={"text": "rain", "target_lang": "hi"})
        assert res.status_code == 200
        body = res.json()
        assert body["translated"] == "बारिश"
        assert body["engine"] == "glossary"

    def test_translate_endpoint_props(self, client: TestClient) -> None:
        res = client.post(
            "/v1/i18n/translate",
            json={"text": "Moderate", "target_lang": "mr", "props": {"cat": "Severe"}},
        )
        assert res.json()["props"]["cat"] == "तीव्र"

    def test_glossary_covers_all_five(self) -> None:
        for term, tr in GLOSSARY.items():
            for lang in ("hi", "ta", "bn", "te", "mr"):
                assert lang in tr, f"term '{term}' missing '{lang}'"


# --------------------------------------------------------------------------- #
# TASK-059/060: geo
# --------------------------------------------------------------------------- #


class TestGeo:
    def test_boundaries_featurecollection(self, client: TestClient) -> None:
        data = client.get("/v1/geo/boundaries").json()
        assert data["type"] == "FeatureCollection"
        names = {f["properties"]["name"] for f in data["features"]}
        assert "Delhi (NCT)" in names and "Maharashtra" in names
        for f in data["features"]:
            assert f["properties"]["schematic"] is True  # honest schematic flag
            assert set(f["properties"]) <= {"name", "code", "schematic", "source"}

    @staticmethod
    def _tile_for(lat: float, lon: float, z: int) -> tuple[int, int]:
        """Slippy-map tile numbers for a coordinate (standard Web Mercator)."""
        import math

        n = 2**z
        x = int((lon + 180.0) / 360.0 * n)
        lat_rad = math.radians(lat)
        y = int((1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)
        return x, y

    def test_tile_delhi_zoom11(self, client: TestClient) -> None:
        from app.services.geo_tiles import slippy_tile_bbox

        x, y = self._tile_for(28.61, 77.21, 11)
        bbox = slippy_tile_bbox(11, x, y)
        assert bbox[0] <= 28.61 <= bbox[2] and bbox[1] <= 77.21 <= bbox[3]
        data = client.get(f"/v1/geo/tile/11/{x}/{y}.json").json()
        assert data["tile"] == {"z": 11, "x": x, "y": y}
        kinds = {f["properties"]["kind"] for f in data["features"]}
        assert "boundary" in kinds

    def test_tile_budget_under_60kb(self, client: TestClient) -> None:
        # TASK-059 acceptance: worst-case tile stays under budget.
        import json as _json

        for zxy in [(5, 21, 13), (8, 171, 70), (0, 0, 0), (11, *self._tile_for(28.61, 77.21, 11))]:
            data = client.get(f"/v1/geo/tile/{zxy[0]}/{zxy[1]}/{zxy[2]}.json")
            raw = _json.dumps(data.json(), separators=(",", ":")).encode()
            assert len(raw) < 60_000, f"tile {zxy} payload {len(raw)} B exceeds 60 KB"

    def test_tile_with_active_alert_contains_cap_feature(self, client: TestClient) -> None:
        from datetime import UTC, datetime, timedelta

        alert_store.put(
            {
                "identifier": "geo-test-1",
                "event": "Cyclone Warning",
                "severity": "Severe",
                "headline": "h",
                "expires": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "polygons": [[[19.0, 72.6], [19.0, 73.4], [18.4, 73.4], [18.4, 72.6], [19.0, 72.6]]],
            }
        )
        x, y = self._tile_for(18.7, 73.0, 7)  # Konkan coast tile
        data = client.get(f"/v1/geo/tile/7/{x}/{y}.json").json()
        kinds = {f["properties"]["kind"] for f in data["features"]}
        assert "cap_alert" in kinds

    def test_tile_out_of_range_404(self, client: TestClient) -> None:
        assert client.get("/v1/geo/tile/13/0/0.json").status_code == 404
        assert client.get("/v1/geo/tile/5/99/0.json").status_code == 404


# --------------------------------------------------------------------------- #
# TASK-055 data half: public alerts feed
# --------------------------------------------------------------------------- #


class TestAlertsFeed:
    def test_active_alerts_geojson_style(self, client: TestClient) -> None:
        alert_store.clear_all()
        from datetime import UTC, datetime, timedelta

        alert_store.put(
            {
                "identifier": "feed-1",
                "event": "Cyclone Warning",
                "severity": "Extreme",
                "headline": "h",
                "expires": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "polygons": [[[19.0, 72.6], [19.0, 73.4], [18.4, 73.4], [18.4, 72.6], [19.0, 72.6]]],
            }
        )
        data = client.get("/v1/alerts/active").json()
        assert data["type"] == "FeatureCollection" and data["count"] == 1
        f = data["features"][0]
        assert f["fill_color"] == "#B71C1C"
        assert f["polygons"][0][0] == [19.0, 72.6]

    def test_empty_feed(self, client: TestClient) -> None:
        alert_store.clear_all()
        data = client.get("/v1/alerts/active").json()
        assert data["count"] == 0 and data["features"] == []


# --------------------------------------------------------------------------- #
# TASK-072 backend half: DPDP purge
# --------------------------------------------------------------------------- #


class TestDpdpPurge:
    def test_purge_removes_telemetry_and_favorites(self, client: TestClient) -> None:
        from app.routers.telemetry import EVENT_LOG

        h = "deadbeefcafebabe"
        EVENT_LOG.append({"ts": 0, "device_id_hash": h, "event": "click"})
        EVENT_LOG.append({"ts": 1, "device_id_hash": "other", "event": "click"})
        client.post("/v1/favorites/sync", json={"device_id_hash": h, "favorites": [
            {"name": "Mumbai", "lat": 19.0, "lon": 72.8}]})
        res = client.post("/v1/privacy/purge", json={"device_id_hash": h})
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "purged"
        assert all(e.get("device_id_hash") != h for e in EVENT_LOG)
        # other devices untouched
        assert any(e.get("device_id_hash") == "other" for e in EVENT_LOG)

    def test_purge_idempotent(self, client: TestClient) -> None:
        res = client.post("/v1/privacy/purge", json={"device_id_hash": "aa" * 8})
        assert res.status_code == 200
        res2 = client.post("/v1/privacy/purge", json={"device_id_hash": "aa" * 8})
        assert res2.status_code == 200

    def test_purge_requires_valid_hash(self, client: TestClient) -> None:
        assert client.post("/v1/privacy/purge", json={"device_id_hash": "x"}).status_code == 422
