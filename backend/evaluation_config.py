from __future__ import annotations

from typing import Any, Dict, Optional

METRICS = (
    "retrieval_relevance",
    "faithfulness",
    "answer_correctness",
    "citation_accuracy",
)


def numeric(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def validate_quality_config(config: Dict[str, Any], dataset: Dict[str, Any]) -> Dict[str, Any]:
    if config.get("dataset_id") != dataset.get("dataset_id"):
        raise ValueError("quality config dataset_id does not match the dataset")
    if config.get("dataset_version") != dataset.get("version"):
        raise ValueError("quality config dataset_version does not match the dataset")
    minimums = config.get("minimum_scores") or {}
    regressions = config.get("maximum_regression") or {}
    baseline = config.get("baseline")
    if not isinstance(minimums, dict) or not isinstance(regressions, dict):
        raise ValueError("minimum_scores and maximum_regression must be objects")
    if baseline is not None and not isinstance(baseline, dict):
        raise ValueError("baseline must be an object or null")
    for section_name, section in (("minimum_scores", minimums), ("maximum_regression", regressions)):
        unknown = set(section) - set(METRICS)
        if unknown:
            raise ValueError(f"{section_name} contains unknown metrics: {', '.join(sorted(unknown))}")
        for metric, value in section.items():
            if value is None:
                continue
            parsed = numeric(value)
            if parsed is None or not 0 <= parsed <= 1:
                raise ValueError(f"{section_name}.{metric} must be a number between 0 and 1")
    if baseline is not None:
        unknown = set(baseline) - set(METRICS)
        if unknown:
            raise ValueError(f"baseline contains unknown metrics: {', '.join(sorted(unknown))}")
        for metric, value in baseline.items():
            if value is None:
                continue
            parsed = numeric(value)
            if parsed is None or not 0 <= parsed <= 1:
                raise ValueError(f"baseline.{metric} must be a number between 0 and 1")
    for metric in METRICS:
        tolerance = numeric(regressions.get(metric))
        if tolerance is not None and numeric((baseline or {}).get(metric)) is None:
            raise ValueError(f"maximum_regression.{metric} requires baseline.{metric}")
    return config


def enabled_metrics(config: Dict[str, Any]) -> set[str]:
    minimums = config.get("minimum_scores") or {}
    regressions = config.get("maximum_regression") or {}
    baseline = config.get("baseline") or {}
    return {
        metric for metric in METRICS
        if numeric(minimums.get(metric)) is not None
        or (numeric(regressions.get(metric)) is not None and numeric(baseline.get(metric)) is not None)
    }


def evaluate_thresholds(config: Dict[str, Any], metrics: Dict[str, Any]) -> list[str]:
    failures: list[str] = []
    minimums = config.get("minimum_scores") or {}
    regressions = config.get("maximum_regression") or {}
    baseline = config.get("baseline") or {}
    for metric in METRICS:
        actual = numeric(metrics.get(metric))
        minimum = numeric(minimums.get(metric))
        if minimum is not None and actual is None:
            failures.append(f"{metric}: score is unavailable but minimum is {minimum}")
        elif minimum is not None and actual < minimum:
            failures.append(f"{metric}: {actual:.4f} is below minimum {minimum:.4f}")
        tolerance = numeric(regressions.get(metric))
        baseline_value = numeric(baseline.get(metric))
        if tolerance is not None and baseline_value is not None:
            if actual is None:
                failures.append(f"{metric}: score is unavailable for baseline comparison")
            elif actual < baseline_value - tolerance:
                failures.append(
                    f"{metric}: {actual:.4f} regressed beyond baseline {baseline_value:.4f} "
                    f"with tolerance {tolerance:.4f}"
                )
    return failures
