from __future__ import annotations

import argparse
import statistics
import time
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import Settings
from backend.app.db import session_factory
from backend.app.recommendation import recommend


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=50)
    args = parser.parse_args()
    if args.iterations < 10:
        raise ValueError("iterations must be at least 10")
    factory = session_factory(Settings.from_env())
    samples = []
    with factory.begin() as session:
        for _ in range(args.iterations):
            started = time.perf_counter()
            recommend(
                session,
                "demo_rider_full",
                25.0478,
                121.5170,
                datetime.fromisoformat("2026-09-17T18:30:00+08:00"),
            )
            samples.append((time.perf_counter() - started) * 1000)
    ordered = sorted(samples)
    p95 = ordered[round((len(ordered) - 1) * 0.95)]
    print(
        f"recommendation_benchmark iterations={args.iterations} "
        f"p50_ms={statistics.median(samples):.3f} p95_ms={p95:.3f}"
    )
    if p95 >= 750:
        raise SystemExit("p95 exceeds Phase 4 threshold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
