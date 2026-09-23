from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def ensure_rider_hash_salt(env_path: Path) -> bool:
    """Populate a blank local salt without printing or replacing a configured value."""
    lines = env_path.read_text(encoding="utf-8").splitlines()
    replacement = f"RIDER_HASH_SALT={secrets.token_urlsafe(32)}"
    for index, line in enumerate(lines):
        if line.startswith("RIDER_HASH_SALT="):
            if line != "RIDER_HASH_SALT=":
                return False
            lines[index] = replacement
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
    lines.append(replacement)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def main() -> int:
    if sys.version_info[:2] != (3, 12):
        print(
            "BLOCKED: Phase 0 requires Python 3.12; "
            f"found {sys.version.split()[0]}",
            file=sys.stderr,
        )
        return 2

    env_path = ROOT / ".env"
    example_path = ROOT / ".env.example"
    if not env_path.exists():
        env_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
        print("created .env from .env.example")
    else:
        print("kept existing .env")

    if ensure_rider_hash_salt(env_path):
        print("configured local RIDER_HASH_SALT (value not shown)")
    else:
        print("kept existing RIDER_HASH_SALT")

    for relative in ("data/raw", "data/processed", "data/reports", "data/demo"):
        (ROOT / relative).mkdir(parents=True, exist_ok=True)

    print("bootstrap prerequisites are ready; dependency installation follows from Makefile")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
