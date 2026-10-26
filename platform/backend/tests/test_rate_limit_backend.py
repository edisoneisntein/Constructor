"""Backend de limitación de tasa compartido (§14, §21 Fase 13)."""

from __future__ import annotations

from app.core.rate_limit import (
    DatabaseRateLimiter,
    SlidingWindowLimiter,
    get_rate_limit_backend,
)
from app.db.database import Database
from app.core.ids import utcnow_iso


def _database(tmp_path) -> Database:
    database = Database(tmp_path / "rl.sqlite3")
    database.initialize(utcnow_iso())
    return database


def test_sliding_window_limits_in_process():
    limiter = SlidingWindowLimiter()
    assert limiter.check("k", limit=2, window_seconds=60).allowed is True
    assert limiter.check("k", limit=2, window_seconds=60).allowed is True
    denied = limiter.check("k", limit=2, window_seconds=60)
    assert denied.allowed is False
    assert denied.retry_after_seconds >= 1


def test_database_limiter_is_shared_between_instances(tmp_path):
    database = _database(tmp_path)
    first = DatabaseRateLimiter(database)
    second = DatabaseRateLimiter(database)
    assert first.check("api:org", limit=2, window_seconds=60).allowed is True
    assert second.check("api:org", limit=2, window_seconds=60).allowed is True
    denied = second.check("api:org", limit=2, window_seconds=60)
    assert denied.allowed is False
    assert first.check("api:org", limit=2, window_seconds=60).allowed is False


def test_database_limiter_isolates_keys(tmp_path):
    database = _database(tmp_path)
    limiter = DatabaseRateLimiter(database)
    assert limiter.check("api:a", limit=1, window_seconds=60).allowed is True
    assert limiter.check("api:a", limit=1, window_seconds=60).allowed is False
    assert limiter.check("api:b", limit=1, window_seconds=60).allowed is True


def test_zero_limit_disables(tmp_path):
    database = _database(tmp_path)
    limiter = DatabaseRateLimiter(database)
    assert limiter.check("api:x", limit=0, window_seconds=60).allowed is True


def test_backend_selection_follows_settings(monkeypatch, tmp_path):
    from app.core.config import reset_settings_cache

    monkeypatch.setenv("SIREP_DATABASE_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("SIREP_STORAGE_ROOT", str(tmp_path / "storage"))

    from app.core import rate_limit

    monkeypatch.setenv("SIREP_RATE_LIMIT_BACKEND", "database")
    reset_settings_cache()
    rate_limit.reset_rate_limiter()
    assert isinstance(rate_limit.get_rate_limit_backend(), DatabaseRateLimiter)

    monkeypatch.setenv("SIREP_RATE_LIMIT_BACKEND", "memory")
    reset_settings_cache()
    rate_limit.reset_rate_limiter()
    assert isinstance(rate_limit.get_rate_limit_backend(), type(rate_limit._InProcessBackend()))

    rate_limit.reset_rate_limiter()
    reset_settings_cache()


def test_enforced_through_http(monkeypatch, tmp_path):
    """El middleware aplica el límite del backend configurado sobre la API."""

    monkeypatch.setenv("SIREP_DATABASE_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("SIREP_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("SIREP_ENV", "test")
    monkeypatch.setenv("SIREP_SECRET_KEY", "test-key")
    monkeypatch.setenv("SIREP_RATE_LIMIT_BACKEND", "database")
    monkeypatch.setenv("SIREP_RATE_LIMIT_AUTH_PER_MINUTE", "2")

    from app.core.config import reset_settings_cache
    from app.core.rate_limit import reset_rate_limiter
    from app.db.session import reset_database

    reset_settings_cache()
    reset_database()
    reset_rate_limiter()

    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as client:
        payload = {
            "email": "rl@example.com",
            "password": "supersecret123",
            "display_name": "RL",
            "organization_name": "RLOrg",
        }
        assert client.post("/api/v1/auth/register", json=payload).status_code == 201
        assert client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]}).status_code == 200
        limited = client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]})
        assert limited.status_code == 429, limited.text
        assert "Retry-After" in limited.headers

    reset_database()
    reset_settings_cache()
    reset_rate_limiter()
