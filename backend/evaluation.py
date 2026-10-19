"""Versioned evaluation datasets and deterministic RAG quality scoring."""

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from langchain_core.documents import Document
from sqlalchemy import select

from backend.config import settings
from backend.database import EvaluationResult, EvaluationRun, SessionLocal
from backend.generation import generate_answer
from backend.retrieval import retrieve_relevant_documents

DATASET_DIR = settings.DATA_DIR / "evaluation"
DATASET_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_DATASET_PATH = DATASET_DIR / "dataset.json"


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{2,}", (value or "").lower()))


def _overlap(left: str, right: str) -> Optional[float]:
    expected = _tokens(left)
    actual = _tokens(right)
    if not expected:
        return None
    return round(len(expected & actual) / len(expected), 4)


def score_retrieval(question: str, reference_context: str, documents: List[Document]) -> Optional[float]:
    if not documents or not reference_context:
        return 0.0 if documents else None
    retrieved = " ".join(document.page_content for document in documents)
    return _overlap(reference_context, retrieved)


def score_faithfulness(answer: str, documents: List[Document]) -> Dict[str, Any]:
    if not answer or not documents:
        return {"score": None, "unsupported_claims": []}
    context = " ".join(document.page_content for document in documents)
    claims = [claim.strip() for claim in re.split(r"(?<=[.!?])\s+", answer) if claim.strip()]
    supported = []
    unsupported = []
    for claim in claims:
        score = _overlap(claim, context) or 0.0
        (supported if score >= 0.5 else unsupported).append(claim)
    return {
        "score": round(len(supported) / len(claims), 4) if claims else None,
        "unsupported_claims": unsupported,
    }


def score_correctness(answer: str, expected_answer: str, reference_context: str) -> Optional[float]:
    if not answer or not expected_answer:
        return None
    direct = _overlap(expected_answer, answer) or 0.0
    context_support = _overlap(expected_answer, reference_context) if reference_context else direct
    return round((direct + (context_support or 0.0)) / 2, 4)


def score_citations(
    sources: List[Dict[str, Any]],
    expected_source: Optional[str],
) -> Dict[str, Any]:
    source_names = {str(source.get("source", "")).lower() for source in sources}
    if not sources and not expected_source:
        return {"score": None, "missing": [], "invalid": [], "unsupported": []}
    if not expected_source:
        return {"score": 1.0, "missing": [], "invalid": [], "unsupported": []}
    if expected_source.lower() in source_names:
        return {"score": 1.0, "missing": [], "invalid": [], "unsupported": []}
    return {
        "score": 0.0,
        "missing": [expected_source],
        "invalid": [],
        "unsupported": [],
    }


def validate_dataset(payload: Dict[str, Any]) -> Dict[str, Any]:
    dataset_id = str(payload.get("dataset_id", "")).strip()
    version = str(payload.get("version", "")).strip()
    cases = payload.get("cases")
    if not dataset_id or not re.fullmatch(r"[A-Za-z0-9_-]+", dataset_id):
        raise ValueError("dataset_id must contain only letters, numbers, underscores, or hyphens")
    if not version:
        raise ValueError("version is required")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a non-empty list")
    validated = []
    seen = set()
    for case in cases:
        case_id = str(case.get("id", "")).strip()
        question = str(case.get("question", "")).strip()
        expected = str(case.get("expected_answer", "")).strip()
        if not case_id or case_id in seen:
            raise ValueError("case IDs must be unique and non-empty")
        if not question or not expected:
            raise ValueError(f"case '{case_id}' requires question and expected_answer")
        seen.add(case_id)
        validated.append({
            "id": case_id,
            "question": question,
            "expected_answer": expected,
            "reference_context": str(case.get("reference_context", "")),
            "expected_source": case.get("expected_source"),
            "tags": case.get("tags", []),
        })
    return {
        "dataset_id": dataset_id,
        "version": version,
        "name": str(payload.get("name", dataset_id)),
        "description": str(payload.get("description", "")),
        "sample": bool(payload.get("sample", False)),
        "cases": validated,
    }


def save_dataset(payload: Dict[str, Any]) -> Dict[str, Any]:
    dataset = validate_dataset(payload)
    path = DATASET_DIR / f"{dataset['dataset_id']}_{dataset['version']}.json"
    path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    return dataset


def load_datasets() -> List[Dict[str, Any]]:
    datasets = []
    for path in sorted(DATASET_DIR.glob("*.json")):
        try:
            datasets.append(validate_dataset(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return datasets


def get_dataset(dataset_id: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
    datasets = [dataset for dataset in load_datasets() if dataset["dataset_id"] == dataset_id]
    if version:
        datasets = [dataset for dataset in datasets if dataset["version"] == version]
    return datasets[-1] if datasets else None


def _average(values: Iterable[Optional[float]]) -> Optional[float]:
    available = [value for value in values if value is not None]
    return round(sum(available) / len(available), 4) if available else None


def run_evaluation(dataset: Dict[str, Any], selected_case_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    cases = [
        case for case in dataset["cases"]
        if not selected_case_ids or case["id"] in selected_case_ids
    ]
    run_id = str(uuid.uuid4())
    results = []
    for case in cases:
        try:
            documents = retrieve_relevant_documents(case["question"])
            generated = generate_answer(case["question"], documents)
            citation_result = score_citations(generated.get("sources", []), case.get("expected_source"))
            faithfulness = score_faithfulness(generated["answer"], documents)
            results.append({
                "test_case_id": case["id"],
                "question": case["question"],
                "ground_truth": case["expected_answer"],
                "reference_context": case["reference_context"],
                "expected_source": case.get("expected_source"),
                "generated_answer": generated["answer"],
                "retrieved_chunks": [
                    {"content": document.page_content, "metadata": document.metadata}
                    for document in documents
                ],
                "citations": generated.get("sources", []),
                "relevance_score": score_retrieval(case["question"], case["reference_context"], documents),
                "faithfulness_score": faithfulness["score"],
                "correctness_score": score_correctness(
                    generated["answer"], case["expected_answer"], case["reference_context"]
                ),
                "citation_score": citation_result["score"],
                "unsupported_claims": faithfulness["unsupported_claims"],
                "citation_details": citation_result,
                "status": "completed",
            })
        except Exception as exc:
            results.append({
                "test_case_id": case["id"],
                "question": case["question"],
                "ground_truth": case["expected_answer"],
                "reference_context": case["reference_context"],
                "status": "failed",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "relevance_score": None,
                "faithfulness_score": None,
                "correctness_score": None,
                "citation_score": None,
            })
    completed = [result for result in results if result["status"] == "completed"]
    failed = len(results) - len(completed)
    run = {
        "run_id": run_id,
        "dataset_id": dataset["dataset_id"],
        "dataset_version": dataset["version"],
        "dataset_name": dataset["name"],
        "total_samples": len(results),
        "completed_samples": len(completed),
        "failed_samples": failed,
        "status": "failed" if failed == len(results) else ("partial" if failed else "completed"),
        "avg_relevance": _average(result["relevance_score"] for result in completed),
        "avg_faithfulness": _average(result["faithfulness_score"] for result in completed),
        "avg_correctness": _average(result["correctness_score"] for result in completed),
        "avg_citation_precision": _average(result["citation_score"] for result in completed),
        "scoring_config": {
            "method": "deterministic lexical overlap and source validation",
            "version": "1",
        },
        "results": results,
    }
    with SessionLocal() as session:
        db_run = EvaluationRun(
            id=run_id,
            timestamp=time.time(),
            dataset_name=run["dataset_name"],
            dataset_id=run["dataset_id"],
            dataset_version=run["dataset_version"],
            total_samples=run["total_samples"],
            completed_samples=run["completed_samples"],
            failed_samples=run["failed_samples"],
            avg_relevance=run["avg_relevance"],
            avg_faithfulness=run["avg_faithfulness"],
            avg_correctness=run["avg_correctness"],
            avg_citation_precision=run["avg_citation_precision"],
            status=run["status"],
            scoring_config_json=json.dumps(run["scoring_config"]),
        )
        session.add(db_run)
        for result in results:
            session.add(EvaluationResult(
                id=str(uuid.uuid4()),
                run_id=run_id,
                test_case_id=result["test_case_id"],
                question=result["question"],
                ground_truth=result["ground_truth"],
                reference_context=result.get("reference_context", ""),
                expected_source=result.get("expected_source"),
                generated_answer=result.get("generated_answer", ""),
                context="\n\n".join(
                    chunk.get("content", "") for chunk in result.get("retrieved_chunks", [])
                ),
                retrieved_chunks_json=json.dumps(result.get("retrieved_chunks", [])),
                citations_json=json.dumps(result.get("citations", [])),
                relevance_score=result.get("relevance_score"),
                faithfulness_score=result.get("faithfulness_score"),
                correctness_score=result.get("correctness_score"),
                citation_score=result.get("citation_score"),
                unsupported_claims_json=json.dumps(result.get("unsupported_claims", [])),
                citation_details_json=json.dumps(result.get("citation_details", {})),
                status=result["status"],
                error_type=result.get("error_type"),
                error_message=result.get("error_message"),
            ))
        session.commit()
    return run
