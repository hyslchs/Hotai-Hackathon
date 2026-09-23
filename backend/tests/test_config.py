from __future__ import annotations

from backend.app.config import Settings


def test_config_has_safe_defaults(monkeypatch):
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:5173, http://localhost:4173")
    loaded = Settings.from_env()

    assert loaded.allowed_origins == ("http://localhost:5173", "http://localhost:4173")
    assert loaded.demo_mode is True
    assert loaded.demo_fallback_enabled is True
    assert "postgresql" in loaded.postgres_conninfo
    assert "+psycopg" not in loaded.postgres_conninfo

