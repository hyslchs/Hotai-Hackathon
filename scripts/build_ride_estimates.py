from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.features.ride_estimates import build_fare_estimate_artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/processed/trips_clean.parquet"))
    parser.add_argument("--output", type=Path, default=Path("data/features/phase3_taipei/ride/fare_estimates.json"))
    args = parser.parse_args()
    rows = pq.read_table(
        args.input,
        columns=["split", "model_eligible", "fare_midpoint", "distance_km", "period", "pickup_region"],
    ).to_pylist()
    artifact = build_fare_estimate_artifact(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"fare_estimates_ready accepted_rows={artifact['accepted_row_count']} estimates={len(artifact['estimates'])} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
