"""Test alur auth: login, me, logout, dan proteksi 401."""
from fastapi.testclient import TestClient
from backend.main import app


def test_health_and_unauth():
    with TestClient(app) as client:
        # /api/health publik
        r = client.get("/api/health")
        assert r.status_code == 200, f"health expected 200, got {r.status_code}"

        # Tanpa login, /me harus 401
        r = client.get("/api/auth/me")
        assert r.status_code == 401, f"me expected 401, got {r.status_code}"


def test_login_flow():
    with TestClient(app) as client:
        # Login benar
        r = client.post("/api/auth/login", json={"username": "admin", "password": "agiltampan"})
        assert r.status_code == 200, f"login expected 200, got {r.status_code} {r.text}"
        assert r.json()["ok"] is True

        # /me setelah login (cookie session ikut otomatis)
        r = client.get("/api/auth/me")
        assert r.status_code == 200, f"me expected 200, got {r.status_code}"
        assert r.json()["username"] == "admin"

        # Login salah → 401
        r = client.post("/api/auth/login", json={"username": "admin", "password": "salah"})
        assert r.status_code == 401, f"bad login expected 401, got {r.status_code}"

        # Logout
        r = client.post("/api/auth/logout")
        assert r.status_code == 200
        r = client.get("/api/auth/me")
        assert r.status_code == 401, f"after logout me expected 401, got {r.status_code}"