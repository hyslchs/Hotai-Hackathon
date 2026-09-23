from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import Settings
from backend.app.db import session_factory
from pipeline.loading.serving import load_serving_artifacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("data/features/phase3_taipei"),
    )
    args = parser.parse_args()
    factory = session_factory(Settings.from_env())
    with factory.begin() as session:
        result = load_serving_artifacts(session, args.artifact_root)
    print(
        "serving_load_ready "
        + " ".join(f"{key}={value}" for key, value in sorted(result.items()))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
