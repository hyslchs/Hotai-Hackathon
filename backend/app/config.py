from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    raw_data_path: str
    processed_data_dir: str
    allowed_origins: tuple[str, ...]
    demo_mode: bool
    demo_fallback_enabled: bool
    log_level: str
    google_places_api_key: str = ""
    google_routes_api_key: str = ""
    provider_timeout_seconds: float = 2.5
    db_connect_timeout_seconds: float = 2.5

    @classmethod
    def from_env(cls) -> "Settings":
        origins = tuple(
            item.strip()
            for item in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
            if item.strip()
        )
        return cls(
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql+psycopg://postgres:postgres@localhost:5432/yoxi",
            ),
            raw_data_path=os.getenv(
                "RAW_DATA_PATH",
                str(Path("data") / "raw" / "yoxi_數據資料.csv"),
            ),
            processed_data_dir=os.getenv("PROCESSED_DATA_DIR", str(Path("data") / "processed")),
            allowed_origins=origins,
            demo_mode=_as_bool(os.getenv("DEMO_MODE"), True),
            demo_fallback_enabled=_as_bool(os.getenv("DEMO_FALLBACK_ENABLED"), True),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            google_places_api_key=os.getenv("GOOGLE_PLACES_API_KEY", "").strip(),
            google_routes_api_key=os.getenv("GOOGLE_ROUTES_API_KEY", "").strip(),
            provider_timeout_seconds=float(os.getenv("PROVIDER_TIMEOUT_SECONDS", "2.5")),
        )

    @property
    def postgres_conninfo(self) -> str:
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)


settings = Settings.from_env()
