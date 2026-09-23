from __future__ import annotations

import psycopg

from .config import Settings


async def database_is_available(current_settings: Settings) -> tuple[bool, str | None]:
    """Return a safe status and never expose connection details to an API caller."""
    try:
        async with await psycopg.AsyncConnection.connect(
            current_settings.postgres_conninfo,
            connect_timeout=current_settings.db_connect_timeout_seconds,
        ) as connection:
            await connection.execute("SELECT 1")
        return True, None
    except Exception as exc:  # noqa: BLE001 - health must convert provider errors safely.
        return False, type(exc).__name__

