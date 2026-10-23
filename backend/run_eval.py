"""Run the reproducible RAG evaluation and export a JSON report."""

import argparse
import json
import sys
from pathlib import Path

from backend.evaluation import run_evaluation, validate_dataset
from backend.evaluation_config import enabled_metrics, validate_quality_config
from backend.config import settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=settings.DATA_DIR / "evaluation" / "dataset.json")
    parser.add_argument("--config", type=Path, default=Path("config/rag_quality.json"))
    parser.add_argument("--report", type=Path, default=settings.DATA_DIR / "evaluation" / "latest_report.json")
    parser.add_argument("--no-provider", action="store_true", help="Do not call Gemini; report provider metrics as unavailable.")
    parser.add_argument("--retrieval-only", action="store_true", help="Evaluate retrieval evidence without generating answers.")
    parser.add_argument("--collection", default=settings.EVALUATION_COLLECTION_NAME)
    parser.add_argument("--corpus-version", default=settings.EVALUATION_CORPUS_VERSION)
    args = parser.parse_args()
    try:
        dataset = validate_dataset(json.loads(args.dataset.read_text(encoding="utf-8")))
        config = json.loads(args.config.read_text(encoding="utf-8"))
        validate_quality_config(config, dataset)
        provider_available = not args.no_provider and bool(
            settings.GOOGLE_API_KEY and "your_gemini" not in settings.GOOGLE_API_KEY
        )
        report = run_evaluation(
            dataset,
            provider_available=provider_available,
            quality_config=config,
            collection_name=args.collection,
            corpus_version=args.corpus_version,
            retrieval_only=args.retrieval_only,
        )
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({
            "run_id": report["run_id"],
            "status": report["status"],
            "threshold_status": report["threshold_status"],
            "metric_availability": report["metric_availability"],
            "report": str(args.report),
        }, indent=2))
        if report["threshold_status"] in {"failed", "unavailable"} and enabled_metrics(config):
            return 1
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"EVALUATION CONFIGURATION ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
