from unittest.mock import patch
from pathlib import Path

import pytest
import json
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from backend.evaluation import (
    score_citations,
    score_correctness,
    score_faithfulness,
    score_retrieval,
    validate_dataset,
    run_evaluation,
)
from backend.evaluation_config import validate_quality_config
from backend.run_eval import main as run_eval_main
from backend.evaluation_corpus import corpus_status
from backend.main import app
from backend.config import settings
from backend.database import EvaluationRun, SessionLocal


client = TestClient(app)


def test_dataset_validation_rejects_duplicate_or_empty_cases():
    with pytest.raises(ValueError):
        validate_dataset({
            "dataset_id": "invalid dataset",
            "version": "1",
            "cases": [],
        })
    with pytest.raises(ValueError):
        validate_dataset({
            "dataset_id": "valid",
            "version": "1",
            "cases": [
                {"id": "same", "question": "one", "expected_answer": "answer"},
                {"id": "same", "question": "two", "expected_answer": "answer"},
            ],
        })
    with pytest.raises(ValueError):
        validate_dataset({
            "dataset_id": "valid",
            "version": "1",
            "cases": [{"id": "case", "question": "q", "expected_answer": "a"}],
        })


def test_quality_config_rejects_invalid_thresholds():
    dataset = {
        "dataset_id": "valid",
        "version": "1",
        "cases": [{
            "id": "case",
            "question": "q",
            "expected_answer": "a",
            "reference_context": "context",
            "expected_source": "doc.txt",
        }],
    }
    with pytest.raises(ValueError, match="between 0 and 1"):
        validate_quality_config({
            "dataset_id": "valid",
            "dataset_version": "1",
            "minimum_scores": {"faithfulness": 1.2},
        }, dataset)


def test_metric_scoring_distinguishes_supported_and_unsupported_content():
    documents = [Document(
        page_content="RAGOps stores vectors in persistent ChromaDB.",
        metadata={"source": "README.md"},
    )]
    assert score_retrieval(
        "Where are vectors stored?",
        "persistent ChromaDB vectors",
        documents,
    ) > 0
    faithfulness = score_faithfulness(
        "RAGOps stores vectors in persistent ChromaDB. It runs on Mars.",
        documents,
    )
    assert faithfulness["score"] == 0.5
    assert faithfulness["unsupported_claims"] == ["It runs on Mars."]
    assert score_correctness(
        "Persistent ChromaDB stores the vectors.",
        "RAGOps stores vectors in ChromaDB.",
        "Persistent ChromaDB vectors",
    ) > 0
    assert score_citations([{"source": "README.md"}], "README.md")["score"] == 1.0
    assert score_citations([], "README.md")["missing"] == ["README.md"]


def test_dataset_and_run_api_errors():
    response = client.post("/api/evaluations/datasets", json={
        "dataset_id": "bad id",
        "version": "1",
        "name": "Invalid",
        "cases": [],
    })
    assert response.status_code == 422
    assert client.post("/api/evaluations/run", json={"dataset_id": "missing"}).status_code == 404


def test_run_evaluation_records_partial_failure():
    dataset = {
        "dataset_id": "test",
        "version": "1",
        "name": "Test",
        "description": "",
        "sample": True,
        "cases": [
            {
                "id": "ok",
                "question": "What is stored?",
                "expected_answer": "ChromaDB",
                "reference_context": "ChromaDB stores vectors.",
                "expected_source": "a.txt",
            },
            {
                "id": "bad",
                "question": "This call fails",
                "expected_answer": "answer",
                "reference_context": "context",
                "expected_source": "b.txt",
            },
        ],
    }
    with patch("backend.evaluation.retrieve_relevant_documents") as retrieve, \
         patch("backend.evaluation.generate_answer") as generate:
        retrieve.side_effect = [
            [Document(page_content="ChromaDB stores vectors.", metadata={"source": "a.txt"})],
            RuntimeError("mock provider failure"),
        ]
        generate.return_value = {
            "answer": "ChromaDB stores vectors.",
            "sources": [{"source": "a.txt"}],
        }
        response = client.post("/api/evaluations/datasets", json=dataset)
        assert response.status_code == 200
        run = client.post("/api/evaluations/run", json={
            "dataset_id": "test",
            "version": "1",
        })
    assert run.status_code == 200
    payload = run.json()
    assert payload["status"] == "partial"
    assert payload["completed_samples"] == 1
    assert payload["failed_samples"] == 1
    assert any(item["status"] == "failed" for item in payload["results"])
    with SessionLocal() as session:
        stored_run = session.get(EvaluationRun, payload["run_id"])
        session.delete(stored_run)
        session.commit()
    Path(settings.DATA_DIR / "evaluation" / "test_1.json").unlink(missing_ok=True)


def test_unavailable_provider_is_explicit_and_persisted():
    dataset = {
        "dataset_id": "unavailable_test",
        "version": "1",
        "name": "Unavailable",
        "cases": [{
            "id": "case",
            "question": "q",
            "expected_answer": "a",
            "reference_context": "context",
            "expected_source": "doc.txt",
        }],
    }
    result = run_evaluation(dataset, provider_available=False)
    assert result["status"] == "unavailable"
    assert result["metric_availability"]["faithfulness"] is False
    with SessionLocal() as session:
        stored = session.get(EvaluationRun, result["run_id"])
        assert stored is not None
        session.delete(stored)
        session.commit()


def test_evaluation_corpus_is_separate_from_user_collection():
    status = corpus_status()
    assert status["collection"] != settings.CHROMA_COLLECTION_NAME
    assert status["corpus_version"] == settings.EVALUATION_CORPUS_VERSION
    assert status["document_count"] >= 3


def test_evaluation_rejects_normal_user_collection(monkeypatch):
    monkeypatch.setattr(settings, "EVALUATION_COLLECTION_NAME", settings.CHROMA_COLLECTION_NAME)
    with pytest.raises(ValueError, match="normal user"):
        corpus_status()


def test_run_eval_reports_json_and_fails_enabled_unavailable_threshold(tmp_path, monkeypatch):
    dataset = {
        "dataset_id": "cli_test",
        "version": "1",
        "name": "CLI test",
        "sample": True,
        "cases": [{
            "id": "case",
            "question": "q",
            "expected_answer": "a",
            "reference_context": "context",
            "expected_source": "doc.txt",
        }],
    }
    dataset_path = tmp_path / "dataset.json"
    config_path = tmp_path / "config.json"
    report_path = tmp_path / "report.json"
    dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
    config_path.write_text(json.dumps({
        "dataset_id": "cli_test",
        "dataset_version": "1",
        "minimum_scores": {"faithfulness": 0.8},
        "maximum_regression": {},
        "baseline": None,
    }), encoding="utf-8")
    monkeypatch.setattr("sys.argv", [
        "run_eval", "--dataset", str(dataset_path), "--config", str(config_path),
        "--no-provider", "--report", str(report_path),
    ])
    assert run_eval_main() == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["threshold_status"] == "failed"
    assert report["metric_availability"]["faithfulness"] is False
    with SessionLocal() as session:
        stored = session.get(EvaluationRun, report["run_id"])
        session.delete(stored)
        session.commit()
