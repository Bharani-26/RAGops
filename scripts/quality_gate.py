"""Validate evaluation inputs and enforce configured quality thresholds.

This script intentionally does not call Gemini. CI uses deterministic scoring
tests; a real evaluation report can be supplied separately with --metrics-file.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

METRICS = (
    "retrieval_relevance",
    "faithfulness",
    "answer_correctness",
    "citation_accuracy",
)


def load_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path}")
    return value


def validate_dataset(path: Path) -> Dict[str, Any]:
    dataset = load_json(path)
    if not dataset.get("dataset_id") or not dataset.get("version"):
        raise ValueError("dataset_id and version are required")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a non-empty list")
    ids = [case.get("id") for case in cases]
    if any(not case.get("question") or not case.get("expected_answer") for case in cases):
        raise ValueError("every case requires question and expected_answer")
    if len(ids) != len(set(ids)) or any(not case_id for case_id in ids):
        raise ValueError("case IDs must be unique and non-empty")
    return dataset


def _numeric(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def normalize_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    aliases = {
        "retrieval_relevance": "avg_relevance",
        "faithfulness": "avg_faithfulness",
        "answer_correctness": "avg_correctness",
        "citation_accuracy": "avg_citation_precision",
    }
    return {
        metric: metrics.get(metric, metrics.get(alias))
        for metric, alias in aliases.items()
    }


def evaluate_gate(config: Dict[str, Any], metrics: Optional[Dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    minimums = config.get("minimum_scores") or {}
    regressions = config.get("maximum_regression") or {}
    baseline = config.get("baseline")
    if metrics is None:
        enabled = [metric for metric in METRICS if _numeric(minimums.get(metric)) is not None]
        if enabled:
            return [f"metrics are required because thresholds are enabled: {', '.join(enabled)}"]
        if baseline:
            return ["metrics are required because a baseline is configured"]
        return failures
    for metric in METRICS:
        actual = _numeric(metrics.get(metric))
        minimum = _numeric(minimums.get(metric))
        if minimum is not None and actual is None:
            failures.append(f"{metric}: score is unavailable but minimum is {minimum}")
        elif minimum is not None and actual < minimum:
            failures.append(f"{metric}: {actual:.4f} is below minimum {minimum:.4f}")
        tolerance = _numeric(regressions.get(metric))
        baseline_value = _numeric((baseline or {}).get(metric)) if isinstance(baseline, dict) else None
        if tolerance is not None and baseline_value is not None:
            if actual is None:
                failures.append(f"{metric}: score is unavailable for baseline comparison")
            elif actual < baseline_value - tolerance:
                failures.append(
                    f"{metric}: {actual:.4f} regressed beyond baseline {baseline_value:.4f} "
                    f"with tolerance {tolerance:.4f}"
                )
    return failures


def summary(config: Dict[str, Any], metrics: Optional[Dict[str, Any]], failures: list[str]) -> str:
    lines = [
        "## RAGOps quality gate",
        "",
        f"- Dataset: `{config.get('dataset_id', 'unknown')}` v`{config.get('dataset_version', 'unknown')}`",
        f"- Sample dataset: `{bool(config.get('sample_dataset'))}`",
        "- Threshold policy: configured minimums and optional baseline regression tolerance",
        "",
        "| Metric | Actual | Minimum | Baseline |",
        "|---|---:|---:|---:|",
    ]
    for metric in METRICS:
        actual = (metrics or {}).get(metric)
        minimum = (config.get("minimum_scores") or {}).get(metric)
        baseline = (config.get("baseline") or {}).get(metric) if isinstance(config.get("baseline"), dict) else None
        lines.append(f"| {metric} | {actual if actual is not None else 'unavailable'} | {minimum if minimum is not None else 'disabled'} | {baseline if baseline is not None else 'none'} |")
    lines.extend(["", "### Result", "PASS" if not failures else "FAIL"])
    if failures:
        lines.extend(["", "### Failures", *[f"- {failure}" for failure in failures]])
    elif metrics is None:
        lines.extend(["", "No real evaluation metrics were supplied. Deterministic scoring tests and dataset validation still ran; quality thresholds remain disabled until a reviewed baseline is configured."])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--metrics-file", type=Path)
    args = parser.parse_args()
    try:
        dataset = validate_dataset(args.dataset)
        config = load_json(args.config)
        if config.get("dataset_id") != dataset["dataset_id"] or config.get("dataset_version") != dataset["version"]:
            raise ValueError("quality config dataset does not match the validated dataset")
        metrics = normalize_metrics(load_json(args.metrics_file)) if args.metrics_file else None
        failures = evaluate_gate(config, metrics)
        report = summary(config, metrics, failures)
        print(report)
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            Path(summary_path).write_text(report, encoding="utf-8")
        return 1 if failures else 0
    except ValueError as exc:
        print(f"QUALITY GATE INFRASTRUCTURE ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
