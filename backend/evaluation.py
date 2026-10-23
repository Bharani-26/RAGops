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
from backend.evaluation_config import enabled_metrics, evaluate_thresholds, validate_quality_config

DATASET_DIR = settings.DATA_DIR / "evaluation"
DATASET_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_DATASET_PATH = DATASET_DIR / "dataset.json"


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{2,}", (value or "").lower()))


def _f1(left: str, right: str) -> Optional[float]:
    expected = _tokens(left)
    actual = _tokens(right)
    if not expected:
        return None
    overlap = len(expected & actual)
    if not overlap or not actual:
        return 0.0
    precision = overlap / len(actual)
    recall = overlap / len(expected)
    return round(2 * precision * recall / (precision + recall), 4)


def score_retrieval(
    question: str,
    reference_context: str,
    documents: List[Document],
    expected_source: Optional[str] = None,
) -> Optional[float]:
    if not documents or not reference_context:
        return None
    retrieved = " ".join(document.page_content for document in documents)
    context_score = _f1(reference_context, retrieved)
    source_score = None
    if expected_source:
        source_score = float(any(
            str(document.metadata.get("source", "")).lower() == expected_source.lower()
            for document in documents
        ))
    available = [score for score in (context_score, source_score) if score is not None]
    return round(sum(available) / len(available), 4) if available else None


def score_faithfulness(answer: str, documents: List[Document]) -> Dict[str, Any]:
    if not answer or not documents:
        return {"score": None, "unsupported_claims": []}
    context = " ".join(document.page_content for document in documents)
    claims = [claim.strip() for claim in re.split(r"(?<=[.!?])\s+", answer) if claim.strip()]
    supported = []
    unsupported = []
    for claim in claims:
        score = _f1(claim, context) or 0.0
        (supported if score >= 0.5 else unsupported).append(claim)
    return {
        "score": round(len(supported) / len(claims), 4) if claims else None,
        "unsupported_claims": unsupported,
    }


def score_correctness(answer: str, expected_answer: str, reference_context: str) -> Optional[float]:
    if not answer or not expected_answer:
        return None
    return _f1(expected_answer, answer)


def score_citations(
    sources: List[Dict[str, Any]],
    expected_source: Optional[str],
) -> Dict[str, Any]:
    if not expected_source:
        return {"score": None, "missing": [], "invalid": [], "unsupported": []}
    source_names = {str(source.get("source", "")).lower() for source in sources}
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
        reference_context = str(case.get("reference_context", "")).strip()
        expected_source = str(case.get("expected_source", "")).strip()
        if not question or not expected or not reference_context or not expected_source:
            raise ValueError(
                f"case '{case_id}' requires question, expected_answer, reference_context, and expected_source"
            )
        seen.add(case_id)
        validated.append({
            "id": case_id,
            "question": question,
            "expected_answer": expected,
            "reference_context": reference_context,
            "expected_source": expected_source,
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


def run_evaluation(
    dataset: Dict[str, Any],
    selected_case_ids: Optional[List[str]] = None,
    provider_available: Optional[bool] = None,
    quality_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cases = [
        case for case in dataset["cases"]
        if not selected_case_ids or case["id"] in selected_case_ids
    ]
    run_id = str(uuid.uuid4())
    results = []
    if provider_available is None:
        provider_available = bool(settings.GOOGLE_API_KEY and "your_gemini" not in settings.GOOGLE_API_KEY)
    for case in cases:
        base_result = {
            "test_case_id": case["id"],
            "question": case["question"],
            "ground_truth": case["expected_answer"],
            "reference_context": case["reference_context"],
            "expected_source": case.get("expected_source"),
        }
        if not provider_available:
            results.append({
                **base_result,
                "status": "unavailable",
                "error_type": "ProviderUnavailable",
                "error_message": "Gemini credentials are not configured.",
                "generated_answer": "",
                "retrieved_chunks": [],
                "citations": [],
                "unsupported_claims": [],
                "citation_details": {},
                "relevance_score": None,
                "faithfulness_score": None,
                "correctness_score": None,
                "citation_score": None,
            })
            continue
        try:
            documents = retrieve_relevant_documents(case["question"])
            generated = generate_answer(case["question"], documents)
            citation_result = score_citations(generated.get("sources", []), case.get("expected_source"))
            faithfulness = score_faithfulness(generated["answer"], documents)
            results.append({
                **base_result,
                "generated_answer": generated["answer"],
                "retrieved_chunks": [
                    {"content": document.page_content, "metadata": document.metadata}
                    for document in documents
                ],
                "citations": generated.get("sources", []),
                "relevance_score": score_retrieval(
                    case["question"], case["reference_context"], documents, case.get("expected_source")
                ),
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
                **base_result,
                "status": "failed",
                "error_type": type(exc).__name__,
                "error_message": "Evaluation case failed; see server logs for details.",
                "generated_answer": "",
                "retrieved_chunks": [],
                "citations": [],
                "unsupported_claims": [],
                "citation_details": {},
                "relevance_score": None,
                "faithfulness_score": None,
                "correctness_score": None,
                "citation_score": None,
            })
    completed = [result for result in results if result["status"] == "completed"]
    unavailable = [result for result in results if result["status"] == "unavailable"]
    failed = len(results) - len(completed) - len(unavailable)
    run = {
        "run_id": run_id,
        "dataset_id": dataset["dataset_id"],
        "dataset_version": dataset["version"],
        "dataset_name": dataset["name"],
        "total_samples": len(results),
        "completed_samples": len(completed),
        "failed_samples": failed,
        "status": (
            "unavailable" if unavailable == results
            else "failed" if failed == len(results)
            else "partial" if failed or unavailable else "completed"
        ),
        "avg_relevance": _average(result["relevance_score"] for result in completed),
        "avg_faithfulness": _average(result["faithfulness_score"] for result in completed),
        "avg_correctness": _average(result["correctness_score"] for result in completed),
        "avg_citation_precision": _average(result["citation_score"] for result in completed),
        "scoring_config": {
            "method": "token F1 for facts plus exact source validation",
            "version": "2",
            "metric_limitations": {
                "retrieval_relevance": "Combines reference-context token F1 and expected-source hit; it is not semantic relevance.",
                "faithfulness": "Sentence support uses token F1 threshold 0.5; it is not entailment.",
                "answer_correctness": "Expected-answer token F1 is deterministic fact coverage, not a human or LLM judgment.",
                "citation_accuracy": "Requires the expected source to be cited among retrieved sources.",
            },
        },
        "results": results,
    }
    metrics = {
        "retrieval_relevance": run["avg_relevance"],
        "faithfulness": run["avg_faithfulness"],
        "answer_correctness": run["avg_correctness"],
        "citation_accuracy": run["avg_citation_precision"],
    }
    enabled = enabled_metrics(quality_config or {})
    threshold_failures = evaluate_thresholds(quality_config or {}, metrics) if quality_config else []
    run["metric_availability"] = {key: value is not None for key, value in metrics.items()}
    run["threshold_status"] = (
        "failed" if threshold_failures else
        "unavailable" if enabled and any(metrics[key] is None for key in enabled) else
        "not_configured" if not enabled else "passed"
    )
    run["threshold_failures"] = threshold_failures
    run["scoring_config"]["metric_availability"] = run["metric_availability"]
    run["scoring_config"]["threshold_status"] = run["threshold_status"]
    run["scoring_config"]["threshold_failures"] = threshold_failures
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
