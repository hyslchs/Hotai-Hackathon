from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.error import URLError
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.recommendation import RESTAURANTS
from pipeline.loading.serving import artifact_paths


def _check(label: str, ok: bool, detail: str) -> bool:
    print(f"{'PASS' if ok else 'FAIL'} {label}: {detail}")
    return ok


def _get(url: str) -> tuple[int | None, bytes | None]:
    try:
        with urlopen(url, timeout=5) as response:
            return response.status, response.read()
    except (URLError, TimeoutError):
        return None, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed pre-demo readiness check.")
    parser.add_argument("--artifact-root", type=Path, default=Path("data/features/phase3_taipei"))
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--frontend-url", default="http://localhost:5173")
    args = parser.parse_args()
    checks: list[bool] = []

    env_file = PROJECT_ROOT / ".env"
    env_values = {}
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                env_values[key.strip()] = value.strip()
    checks.append(_check("local configuration", bool(env_values.get("RIDER_HASH_SALT")), ".env has a non-empty rider hash salt" if env_values.get("RIDER_HASH_SALT") else "set RIDER_HASH_SALT in .env"))

    paths = artifact_paths(args.artifact_root)
    missing = [str(path) for path in paths.values() if not path.is_file()]
    checks.append(_check("serving artifacts", not missing, "all required aggregate artifacts are present" if not missing else "missing: " + ", ".join(missing)))
    fare_path = paths["fare_estimates"]
    fare_ok = False
    if fare_path.is_file():
        artifact = json.loads(fare_path.read_text(encoding="utf-8"))
        fare_ok = artifact.get("artifact_type") == "train_fare_estimates" and artifact.get("split") == "train" and bool(artifact.get("estimates"))
    checks.append(_check("historical fare artifact", fare_ok, "Train-only aggregate fare contexts are available" if fare_ok else "rebuild fare estimates from permitted Train data"))
    checks.append(_check("fallback restaurants", len(RESTAURANTS) >= 5, f"{len(RESTAURANTS)} synthetic fallback restaurants are available"))

    live_status, _ = _get(args.backend_url.rstrip("/") + "/health/live")
    ready_status, _ = _get(args.backend_url.rstrip("/") + "/health/ready")
    checks.append(_check("backend liveness", live_status == 200, f"HTTP {live_status}" if live_status else "backend is not reachable"))
    checks.append(_check("backend readiness", ready_status == 200, f"HTTP {ready_status}" if ready_status else "database/model is not ready"))
    frontend_status, frontend_body = _get(args.frontend_url.rstrip("/") + "/")
    frontend_ok = frontend_status == 200 and frontend_body is not None and b"root" in frontend_body
    checks.append(_check("frontend", frontend_ok, f"HTTP {frontend_status}" if frontend_status else "frontend is not reachable"))

    if all(checks):
        print("DEMO READY: services, permitted artifacts, and fallback prerequisites passed.")
        return 0
    print("DEMO NOT READY: fix each FAIL line before presenting.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
