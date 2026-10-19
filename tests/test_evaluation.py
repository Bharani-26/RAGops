from unittest.mock import patch
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from backend.evaluation import (
    score_citations,
    score_correctness,
    score_faithfulness,
    score_retrieval,
    validate_dataset,
)
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
            },
            {
                "id": "bad",
                "question": "This call fails",
                "expected_answer": "answer",
                "reference_context": "context",
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
