"""Phase 3 tests — favorites sync server (local-first dual-write mirror)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


def test_push_pull_roundtrip(client: TestClient) -> None:
    h = "a1b2c3d4e5f6g7h8"
    res = client.post(
        "/v1/favorites/sync",
        json={
            "device_id_hash": h,
            "favorites": [
                {"name": "Anand Vihar", "lat": 28.65, "lon": 77.31},
                {"name": "Kochi Beach", "lat": 9.93, "lon": 76.27},
            ],
        },
    )
    assert res.status_code == 204

    pulled = client.get(f"/v1/favorites/sync/{h}")
    assert pulled.status_code == 200
    favs = pulled.json()["favorites"]
    assert len(favs) == 2
    assert favs[0]["name"] == "Anand Vihar"
    assert favs[0]["added_at"]  # server stamps if client omits


def test_push_replaces_not_merges(client: TestClient) -> None:
    h = "b2c3d4e5f6g7h8i9"
    client.post(
        "/v1/favorites/sync",
        json={"device_id_hash": h, "favorites": [{"name": "A", "lat": 1, "lon": 2}]},
    )
    client.post(
        "/v1/favorites/sync",
        json={"device_id_hash": h, "favorites": [{"name": "B", "lat": 3, "lon": 4}]},
    )
    favs = client.get(f"/v1/favorites/sync/{h}").json()["favorites"]
    assert len(favs) == 1 and favs[0]["name"] == "B"


def test_purge(client: TestClient) -> None:
    h = "c3d4e5f6g7h8i9j0"
    client.post(
        "/v1/favorites/sync",
        json={"device_id_hash": h, "favorites": [{"name": "X", "lat": 1, "lon": 2}]},
    )
    assert client.delete(f"/v1/favorites/sync/{h}").status_code == 204
    assert client.get(f"/v1/favorites/sync/{h}").json()["favorites"] == []


def test_validation_errors(client: TestClient) -> None:
    # short device hash
    assert client.post(
        "/v1/favorites/sync", json={"device_id_hash": "short", "favorites": []}
    ).status_code == 422
    # too many favorites
    many = [{"name": f"f{i}", "lat": 1, "lon": 2} for i in range(51)]
    assert client.post(
        "/v1/favorites/sync", json={"device_id_hash": "abcdefgh12345678", "favorites": many}
    ).status_code == 422
    # bad name
    assert client.post(
        "/v1/favorites/sync",
        json={"device_id_hash": "abcdefgh12345678", "favorites": [{"name": "", "lat": 1, "lon": 2}]},
    ).status_code == 422


def test_purge_unknown_hash_is_idempotent(client: TestClient) -> None:
    assert client.delete("/v1/favorites/sync/zzzz0000zzzz0000").status_code == 204
