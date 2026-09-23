from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.evaluation.validation import evaluate_validation
from pipeline.evaluation.personalized import run_personalized_evaluation
from pipeline.features.aggregate import build_taipei_features
from pipeline.features.areas import (
    AreaConfig,
    assign_points,
    fit_taipei_area_model,
    load_area_artifact,
)
from pipeline.features.ranking import recommend_demo_areas
from pipeline.features.personalization import build_personalization_artifact


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _local_env_value(name: str) -> str:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return ""
    prefix = f"{name}="
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def _demo_evidence(
    area_artifact_dir: Path,
    feature_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    area = load_area_artifact(area_artifact_dir)
    features = json.loads(feature_path.read_text(encoding="utf-8"))
    first_area = sorted(
        area["metadata"]["areas"],
        key=lambda item: item["area_id"],
    )[0]
    dense_point = first_area["centroid"]
    fallback_candidates = [
        (25.399, 121.999),
        (25.395, 121.985),
        (24.705, 121.995),
        (25.010, 121.205),
    ]
    fallback_point = None
    for latitude, longitude in fallback_candidates:
        assignment = assign_points(
            area["model"],
            [(latitude, longitude)],
            area["metadata"]["cluster_to_area"],
        )[0]
        if assignment.source == "fallback":
            fallback_point = {
                "latitude": latitude,
                "longitude": longitude,
                "assignment_source": assignment.source,
                "region": assignment.region,
            }
            break
    if fallback_point is None:
        fallback_point = {
            "latitude": fallback_candidates[0][0],
            "longitude": fallback_candidates[0][1],
            "assignment_source": "fallback_probe_not_found",
            "region": "Taipei",
        }

    dense = recommend_demo_areas(
        area,
        features,
        float(dense_point["latitude"]),
        float(dense_point["longitude"]),
        "dinner",
        "weekday",
    )
    fallback = recommend_demo_areas(
        area,
        features,
        float(fallback_point["latitude"]),
        float(fallback_point["longitude"]),
        "dinner",
        "weekday",
    )
    evidence = {
        "artifact_version": "phase3-taipei-demo-evidence-v1",
        "scope": "Taipei Demo only",
        "test_used": False,
        "scenarios": {
            "verified_area": {
                "input": {
                    "latitude": dense_point["latitude"],
                    "longitude": dense_point["longitude"],
                    "period": "dinner",
                    "weekday_class": "weekday",
                },
                "response": dense,
            },
            "fallback_area": {
                "input": {
                    "latitude": fallback_point["latitude"],
                    "longitude": fallback_point["longitude"],
                    "period": "dinner",
                    "weekday_class": "weekday",
                },
                "response": fallback,
            },
        },
    }
    path = output_dir / "demo_evidence.json"
    _write_json(path, evidence)
    return {"evidence": evidence, "path": path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Taipei Demo Phase 3 pipeline")
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "data" / "processed" / "trips_clean.parquet",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "features" / "phase3_taipei",
    )
    parser.add_argument(
        "--stage",
        choices=(
            "all",
            "area",
            "features",
            "personalize",
            "smoke-evaluate",
            "evaluate",
            "demo",
        ),
        default="all",
    )
    parser.add_argument("--sample-size", type=int, default=200_000)
    args = parser.parse_args(argv)

    input_path = args.input.resolve()
    output_dir = args.output_dir.resolve()
    area_dir = output_dir / "area"
    feature_dir = output_dir / "features"
    personalization_dir = output_dir / "personalization"
    evaluation_dir = output_dir / "evaluation"
    area_config = AreaConfig(sample_size=args.sample_size)

    if args.stage in {"all", "area"}:
        area_result = fit_taipei_area_model(input_path, area_dir, area_config)
        print(
            "phase3_area_ready "
            f"model_version={area_result['metadata']['model_version']} "
            f"areas={len(area_result['metadata']['areas'])} "
            f"artifact_hash={area_result['metadata']['artifact_hash']}"
        )
    if args.stage in {"all", "features"}:
        feature_result = build_taipei_features(
            input_path,
            area_dir,
            feature_dir,
        )
        print(
            "phase3_features_ready "
            f"rows={len(feature_result['artifact']['features'])} "
            f"feature_hash={feature_result['artifact']['feature_hash']} "
            f"coverage={feature_result['artifact']['destination_coverage']:.6f}"
        )
    if args.stage in {"all", "personalize"}:
        personalization_result = build_personalization_artifact(
            input_path,
            area_dir,
            personalization_dir,
            _local_env_value("RIDER_HASH_SALT"),
        )
        counts = personalization_result["metadata"]["rider_counts"]
        print(
            "phase3_personalization_ready "
            f"full={counts['full']} light={counts['light']} cold={counts['cold']} "
            f"artifact_hash={personalization_result['metadata']['artifact_hash']}"
        )
    if args.stage == "smoke-evaluate":
        evaluation_result = evaluate_validation(
            input_path,
            area_dir,
            feature_dir / "feature_artifact.json",
            evaluation_dir,
        )
        print(
            "phase3_validation_ready "
            f"taipei_rows={evaluation_result['report']['validation_taipei_rows']} "
            f"coverage={evaluation_result['report']['validation_destination_coverage']:.6f}"
        )
    if args.stage in {"all", "evaluate"}:
        evaluation_result = run_personalized_evaluation(
            input_path,
            area_dir,
            feature_dir / "feature_artifact.json",
            personalization_dir,
            evaluation_dir,
            _local_env_value("RIDER_HASH_SALT"),
        )
        selected = evaluation_result["report"]["locked_config"]["selected_model"]
        print(
            "phase3_personalized_evaluation_ready "
            f"selected_model={selected} "
            f"report_hash={evaluation_result['report']['report_hash']}"
        )
    if args.stage in {"all", "demo"}:
        demo_result = _demo_evidence(
            area_dir,
            feature_dir / "feature_artifact.json",
            output_dir,
        )
        print(f"phase3_demo_evidence={demo_result['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
