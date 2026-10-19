import json
from pathlib import Path

import pytest

from scripts.quality_gate import evaluate_gate, main, validate_dataset


def test_quality_gate_passes_configured_thresholds():
    config = {
        "minimum_scores": {"faithfulness": 0.8},
        "maximum_regression": {},
        "baseline": None,
    }
    assert evaluate_gate(config, {"faithfulness": 0.9}) == []


def test_quality_gate_fails_below_threshold():
    config = {
        "minimum_scores": {"faithfulness": 0.8},
        "maximum_regression": {},
        "baseline": None,
    }
    assert "below minimum" in evaluate_gate(config, {"faithfulness": 0.7})[0]


def test_quality_gate_rejects_missing_metric_when_threshold_enabled():
    config = {
        "minimum_scores": {"faithfulness": 0.8},
        "maximum_regression": {},
        "baseline": None,
    }
    assert "unavailable" in evaluate_gate(config, {"faithfulness": None})[0]


def test_missing_baseline_does_not_enable_relative_gate():
    config = {
        "minimum_scores": {},
        "maximum_regression": {"faithfulness": 0.05},
        "baseline": None,
    }
    assert evaluate_gate(config, {"faithfulness": 0.0}) == []


def test_quality_gate_detects_regression():
    config = {
        "minimum_scores": {},
        "maximum_regression": {"faithfulness": 0.05},
        "baseline": {"faithfulness": 0.9},
    }
    assert "regressed" in evaluate_gate(config, {"faithfulness": 0.8})[0]


def test_quality_gate_requires_metrics_when_thresholds_are_enabled():
    config = {
        "minimum_scores": {"faithfulness": 0.8},
        "maximum_regression": {},
        "baseline": None,
    }
    assert "metrics are required" in evaluate_gate(config, None)[0]


def test_dataset_validation_rejects_invalid_structure(tmp_path: Path):
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps({
        "dataset_id": "invalid",
        "version": "1",
        "cases": [{"id": "duplicate", "question": "", "expected_answer": "x"}],
    }), encoding="utf-8")
    with pytest.raises(ValueError):
        validate_dataset(path)


def test_quality_gate_reports_configuration_errors_as_infrastructure_failure(
    tmp_path: Path, monkeypatch
):
    config = tmp_path / "config.json"
    dataset = tmp_path / "dataset.json"
    config.write_text("{", encoding="utf-8")
    dataset.write_text(json.dumps({
        "dataset_id": "valid",
        "version": "1",
        "cases": [{"id": "case-1", "question": "q", "expected_answer": "a"}],
    }), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        ["quality_gate.py", "--config", str(config), "--dataset", str(dataset)],
    )
    assert main() == 2
