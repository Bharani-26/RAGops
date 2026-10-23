import uuid
import time
import logging
import json
from datetime import datetime
from typing import List, Optional, Literal
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.config import settings
from backend.ingestion import (
    validate_file,
    extract_pages_and_text,
    chunk_document,
    sanitize_filename,
    generate_unique_server_filename,
    content_sha256,
)
from backend.retrieval import (
    store_documents,
    retrieve_relevant_documents,
    check_chroma_health,
    find_document_by_hash,
    list_stored_documents,
    get_stored_document,
    list_stored_chunks,
)
from backend.generation import generate_answer
from backend.database import (
    record_trace,
    get_all_traces,
    get_metrics_summary,
    get_all_evaluations,
    check_sqlite_health,
    SessionLocal,
    EvaluationRun,
)
from backend.observability import (
    get_overview,
    get_requests,
    get_request_detail,
    get_latency,
    get_errors,
    get_costs,
)
from backend.evaluation import (
    get_dataset,
    load_datasets,
    run_evaluation,
    save_dataset,
)

logger = logging.getLogger("ragops.routes")
router = APIRouter(prefix="/api/rag", tags=["RAG Pipeline"])
observability_router = APIRouter(prefix="/api/observability", tags=["Observability"])
evaluation_router = APIRouter(prefix="/api/evaluations", tags=["Evaluations"])


class ChunkMetadata(BaseModel):
    source: str
    chunk_index: int
    total_chunks: int
    page_number: Optional[int] = None
    chunk_id: Optional[str] = None
    content_preview: str
    metadata: dict
    citation: Optional[str] = None


class DocumentUploadResponse(BaseModel):
    message: str
    filename: str
    doc_id: str
    total_chunks: int
    chunk_ids: List[str]


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Question to answer using the indexed knowledge base")
    top_k: Optional[int] = Field(default=None, ge=1, le=20, description="Number of context chunks to retrieve")


class QueryResponse(BaseModel):
    request_id: str
    query: str
    answer: str
    sources: List[ChunkMetadata]
    retrieval_latency_ms: float = 0.0
    generation_latency_ms: float = 0.0


def _estimate_cost(prompt_tokens: Optional[int], completion_tokens: Optional[int]) -> Optional[float]:
    if (
        prompt_tokens is None
        or completion_tokens is None
        or settings.INPUT_PRICE_PER_MILLION_TOKENS is None
        or settings.OUTPUT_PRICE_PER_MILLION_TOKENS is None
    ):
        return None
    return (
        prompt_tokens * settings.INPUT_PRICE_PER_MILLION_TOKENS / 1_000_000
        + completion_tokens * settings.OUTPUT_PRICE_PER_MILLION_TOKENS / 1_000_000
    )


@router.get("/ready")
async def readiness_check():
    """
    Readiness probe verifying persistent storage connectivity:
    ChromaDB vector store and SQLite telemetry database.
    """
    chroma_ok = check_chroma_health()
    sqlite_ok = check_sqlite_health()
    is_ready = chroma_ok and sqlite_ok

    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if is_ready else "degraded",
        "chromadb": "accessible" if chroma_ok else "unreachable",
        "sqlite": "accessible" if sqlite_ok else "unreachable",
        "storage_paths": {
            "chroma_dir": str(settings.CHROMA_PERSIST_DIR),
            "sqlite_db": str(settings.SQLITE_DB_PATH),
            "uploads_dir": str(settings.UPLOAD_DIR),
        }
    }


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    chunk_size: Optional[int] = Form(None),
    chunk_overlap: Optional[int] = Form(None),
):
    """
    Upload and index a document (.txt or .pdf).
    Extracts text and page numbers, chunks with metadata, generates embeddings,
    and indexes into persistent ChromaDB.
    """
    original_name = file.filename or "uploaded_file.txt"
    safe_clean_name = sanitize_filename(original_name)
    server_filename = generate_unique_server_filename(original_name)
    doc_id = str(uuid.uuid4())

    try:
        content = await file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {str(e)}"
        )

    # 1. Format and content validation
    try:
        validate_file(safe_clean_name, content)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    existing = find_document_by_hash(content_sha256(content))
    if existing:
        return DocumentUploadResponse(
            message="Document already indexed; existing chunks were reused",
            filename=existing["filename"],
            doc_id=existing["doc_id"],
            total_chunks=len(existing["chunk_ids"]),
            chunk_ids=existing["chunk_ids"],
        )

    # 2. Text and page extraction
    try:
        pages = extract_pages_and_text(safe_clean_name, content)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error during document extraction: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document parsing error: {str(e)}"
        )

    # 3. Save raw file copy to data/uploads/
    target_file_path = settings.UPLOAD_DIR / server_filename
    try:
        with open(target_file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Failed to persist raw file to disk: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store raw file on server."
        )

    # 4. Chunking with document and page metadata
    try:
        chunks = chunk_document(
            pages=pages,
            source_name=safe_clean_name,
            doc_id=doc_id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            extra_metadata={
                "server_filename": server_filename,
                "content_sha256": content_sha256(content),
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # 5. Embedding and indexing in persistent ChromaDB
    try:
        chunk_ids = store_documents(chunks)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error during document indexing: {e}")
        target_file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to index document in vector store: {str(e)}"
        )

    return DocumentUploadResponse(
        message="Document uploaded and indexed successfully into persistent storage",
        filename=safe_clean_name,
        doc_id=doc_id,
        total_chunks=len(chunks),
        chunk_ids=chunk_ids,
    )


@router.get("/documents")
async def list_documents():
    """List documents represented by persisted Chroma metadata."""
    return {"documents": list_stored_documents()}


@router.get("/chunks")
async def list_chunks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    document_id: Optional[str] = Query(None),
    filename: Optional[str] = Query(None),
):
    """List persisted Chroma chunks for document inspection."""
    try:
        return list_stored_chunks(
            page=page,
            page_size=page_size,
            document_id=document_id,
            filename=filename,
        )
    except Exception as exc:
        logger.error("Failed to list Chroma chunks: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read stored document chunks.",
        ) from exc


@router.get("/documents/{document_id}")
async def document_detail(document_id: str):
    document = get_stored_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


@router.post("/query", response_model=QueryResponse)
async def query_rag(request: QueryRequest):
    """
    Query the indexed documents.
    Retrieves the most semantically relevant chunks from persistent ChromaDB
    and generates a grounded response.
    Records telemetry trace in SQLite database.
    """
    request_id = str(uuid.uuid4())
    start_time = time.time()
    stages = []
    
    # 1. Retrieval from persistent Chroma
    retrieval_start = time.time()
    try:
        retrieved_docs = retrieve_relevant_documents(query=request.query, top_k=request.top_k)
        retrieval_ms = (time.time() - retrieval_start) * 1000
        stages.append({
            "name": "ChromaDB Vector Retrieval",
            "duration_ms": round(retrieval_ms, 2),
            "status": "success",
            "details": f"Retrieved {len(retrieved_docs)} candidate chunks."
        })
    except ValueError as e:
        record_trace(
            request_id=request_id, query=request.query, answer="", model=settings.LLM_MODEL,
            latency_ms=round((time.time() - start_time) * 1000, 2), status_code=500,
            status="error", top_k=request.top_k or settings.DEFAULT_TOP_K,
            sources=[], stages=[{"name": "Retrieval", "status": "error", "error": str(e)}],
            estimated_cost=None,
            error_type=type(e).__name__,
            error_message=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error retrieving documents: {e}")
        record_trace(
            request_id=request_id, query=request.query, answer="", model=settings.LLM_MODEL,
            latency_ms=round((time.time() - start_time) * 1000, 2), status_code=500,
            status="error", top_k=request.top_k or settings.DEFAULT_TOP_K,
            sources=[], stages=[{"name": "Retrieval", "status": "error", "error": str(e)}],
            estimated_cost=None,
            error_type=type(e).__name__,
            error_message=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retrieval error: {str(e)}"
        )

    # 2. Generation with Gemini. Avoid a paid model call when retrieval has
    # no context that could support a grounded answer.
    if not retrieved_docs:
        no_context_answer = (
            "The retrieved context does not contain sufficient information "
            "to answer this question."
        )
        total_latency_ms = round((time.time() - start_time) * 1000, 2)
        record_trace(
            request_id=request_id,
            query=request.query,
            answer=no_context_answer,
            model=settings.LLM_MODEL,
            latency_ms=total_latency_ms,
            status_code=200,
            status="success",
            top_k=request.top_k or settings.DEFAULT_TOP_K,
            sources=[],
            stages=stages,
            estimated_cost=None,
        )
        return QueryResponse(
            request_id=request_id,
            query=request.query,
            answer=no_context_answer,
            sources=[],
            retrieval_latency_ms=round(retrieval_ms, 2),
            generation_latency_ms=0.0,
        )

    generation_start = time.time()
    try:
        generation_res = generate_answer(query=request.query, retrieved_documents=retrieved_docs)
        generation_ms = (time.time() - generation_start) * 1000
        stages.append({
            "name": "Gemini Grounded Generation",
            "duration_ms": round(generation_ms, 2),
            "status": "success",
            "details": f"Model: {settings.LLM_MODEL}"
        })
    except ValueError as e:
        record_trace(
            request_id=request_id, query=request.query, answer="", model=settings.LLM_MODEL,
            latency_ms=round((time.time() - start_time) * 1000, 2), status_code=500,
            status="error", top_k=request.top_k or settings.DEFAULT_TOP_K,
            sources=[], stages=stages + [{"name": "Generation", "status": "error", "error": str(e)}],
            estimated_cost=None,
            error_type=type(e).__name__,
            error_message=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error generating answer: {e}")
        record_trace(
            request_id=request_id, query=request.query, answer="", model=settings.LLM_MODEL,
            latency_ms=round((time.time() - start_time) * 1000, 2), status_code=500,
            status="error", top_k=request.top_k or settings.DEFAULT_TOP_K,
            sources=[], stages=stages + [{"name": "Generation", "status": "error", "error": str(e)}],
            estimated_cost=None,
            error_type=type(e).__name__,
            error_message=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generation model error: {str(e)}"
        )

    total_latency_ms = round((time.time() - start_time) * 1000, 2)
    prompt_tokens = generation_res.get("prompt_tokens")
    completion_tokens = generation_res.get("completion_tokens")
    estimated_cost = _estimate_cost(prompt_tokens, completion_tokens)

    record_trace(
        request_id=request_id,
        query=request.query,
        answer=generation_res["answer"],
        model=settings.LLM_MODEL,
        latency_ms=total_latency_ms,
        status_code=200,
        status="success",
        top_k=request.top_k or settings.DEFAULT_TOP_K,
        sources=generation_res["sources"],
        stages=stages,
        estimated_cost=estimated_cost,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )

    return QueryResponse(
        request_id=request_id,
        query=request.query,
        answer=generation_res["answer"],
        sources=generation_res["sources"],
        retrieval_latency_ms=round(retrieval_ms, 2),
        generation_latency_ms=round(generation_ms, 2),
    )


@router.get("/traces")
async def get_traces():
    """Retrieve recorded request traces from SQLite database."""
    return {"traces": get_all_traces()}


@router.get("/metrics")
async def get_metrics():
    """Retrieve aggregate observability metrics computed from SQLite traces."""
    return get_metrics_summary()


@router.get("/evaluations")
async def get_evaluations():
    """Retrieve evaluation benchmark runs from SQLite database."""
    return {"evaluations": get_all_evaluations()}


@router.get("/settings")
async def get_application_settings():
    """Expose safe server settings without exposing secrets."""
    has_api_key = bool(settings.GOOGLE_API_KEY and "your_gemini" not in settings.GOOGLE_API_KEY)
    return {
        "project_name": settings.PROJECT_NAME,
        "api_key_configured": has_api_key,
        "embedding_model": settings.EMBEDDING_MODEL,
        "llm_model": settings.LLM_MODEL,
        "temperature": settings.LLM_TEMPERATURE,
        "default_chunk_size": settings.DEFAULT_CHUNK_SIZE,
        "default_chunk_overlap": settings.DEFAULT_CHUNK_OVERLAP,
        "default_top_k": settings.DEFAULT_TOP_K,
        "chroma_collection": settings.CHROMA_COLLECTION_NAME,
        "storage_paths": {
            "uploads": str(settings.UPLOAD_DIR),
            "chroma": str(settings.CHROMA_PERSIST_DIR),
            "sqlite_db": str(settings.SQLITE_DB_PATH),
        }
    }


# Public API aliases retained separately from the legacy /api/rag routes used
# by the existing frontend.
public_router = APIRouter(prefix="/api", tags=["Documents and RAG"])


@public_router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document_public(
        file: UploadFile = File(...),
        chunk_size: Optional[int] = Form(None),
        chunk_overlap: Optional[int] = Form(None),
):
        return await upload_document(file, chunk_size, chunk_overlap)


@public_router.get("/documents")
async def list_documents_public():
        return await list_documents()


@public_router.get("/documents/{document_id}")
async def document_detail_public(document_id: str):
        return await document_detail(document_id)


@public_router.post("/rag/query", response_model=QueryResponse)
async def query_rag_public(request: QueryRequest):
        return await query_rag(request)


@observability_router.get("/overview")
async def observability_overview(
    status_filter: Optional[Literal["success", "error"]] = Query(None, alias="status"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be before date_to")
    return get_overview(status_filter, date_from, date_to)


@observability_router.get("/requests")
async def observability_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    status_filter: Optional[Literal["success", "error"]] = Query(None, alias="status"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be before date_to")
    return get_requests(page, page_size, status_filter, date_from, date_to)


@observability_router.get("/requests/{request_id}")
async def observability_request_detail(request_id: str):
    result = get_request_detail(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Request trace not found")
    return result


@observability_router.get("/latency")
async def observability_latency(
    status_filter: Optional[Literal["success", "error"]] = Query(None, alias="status"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be before date_to")
    return get_latency(status_filter, date_from, date_to)


@observability_router.get("/errors")
async def observability_errors(
    limit: int = Query(100, ge=1, le=500),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be before date_to")
    return get_errors(limit, date_from, date_to)


@observability_router.get("/costs")
async def observability_costs(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be before date_to")
    return get_costs(date_from, date_to)


class EvaluationDatasetRequest(BaseModel):
    dataset_id: str
    version: str
    name: str
    description: str = ""
    sample: bool = False
    cases: List[dict]


class EvaluationRunRequest(BaseModel):
    dataset_id: str
    version: Optional[str] = None
    case_ids: Optional[List[str]] = None


def _run_summary(run) -> dict:
    scoring_config = json.loads(run.scoring_config_json or "{}")
    return {
        "run_id": run.id,
        "timestamp": run.timestamp,
        "dataset_id": run.dataset_id,
        "dataset_version": run.dataset_version,
        "dataset_name": run.dataset_name,
        "total_samples": run.total_samples,
        "completed_samples": run.completed_samples,
        "failed_samples": run.failed_samples,
        "status": run.status,
        "avg_relevance": run.avg_relevance,
        "avg_faithfulness": run.avg_faithfulness,
        "avg_correctness": run.avg_correctness,
        "avg_citation_precision": run.avg_citation_precision,
        "scoring_config": scoring_config,
        "metric_availability": scoring_config.get("metric_availability", {}),
        "threshold_status": scoring_config.get("threshold_status", "not_configured"),
        "threshold_failures": scoring_config.get("threshold_failures", []),
        "error_message": run.error_message,
    }


@evaluation_router.get("/datasets")
async def evaluation_datasets():
    return {"datasets": load_datasets()}


@evaluation_router.post("/datasets")
async def create_evaluation_dataset(request: EvaluationDatasetRequest):
    try:
        return save_dataset(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@evaluation_router.get("/datasets/{dataset_id}")
async def evaluation_dataset_detail(dataset_id: str, version: Optional[str] = Query(None)):
    dataset = get_dataset(dataset_id, version)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Evaluation dataset not found")
    return dataset


@evaluation_router.post("/run")
async def execute_evaluation(request: EvaluationRunRequest):
    dataset = get_dataset(request.dataset_id, request.version)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Evaluation dataset not found")
    try:
        return run_evaluation(dataset, request.case_ids)
    except Exception as exc:
        logger.exception("Evaluation run failed")
        raise HTTPException(status_code=500, detail="Evaluation run failed; check server logs.")


@evaluation_router.get("/runs")
async def evaluation_runs():
    with SessionLocal() as session:
        runs = session.scalars(select(EvaluationRun).order_by(EvaluationRun.timestamp.desc())).all()
        return {"runs": [_run_summary(run) for run in runs]}


@evaluation_router.get("/latest")
async def latest_evaluation():
    with SessionLocal() as session:
        run = session.scalars(select(EvaluationRun).order_by(EvaluationRun.timestamp.desc())).first()
        if run is None:
            raise HTTPException(status_code=404, detail="No evaluation runs found")
        return await evaluation_run_detail(run.id)


@evaluation_router.get("/runs/{run_id}")
async def evaluation_run_detail(run_id: str):
    with SessionLocal() as session:
        run = session.get(EvaluationRun, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Evaluation run not found")
        result = _run_summary(run)
        result["results"] = [
            {
                "id": item.id,
                "test_case_id": item.test_case_id,
                "question": item.question,
                "ground_truth": item.ground_truth,
                "reference_context": item.reference_context,
                "expected_source": item.expected_source,
                "generated_answer": item.generated_answer,
                "retrieved_chunks": json.loads(item.retrieved_chunks_json or "[]"),
                "citations": json.loads(item.citations_json or "[]"),
                "relevance_score": item.relevance_score,
                "faithfulness_score": item.faithfulness_score,
                "correctness_score": item.correctness_score,
                "citation_score": item.citation_score,
                "unsupported_claims": json.loads(item.unsupported_claims_json or "[]"),
                "citation_details": json.loads(item.citation_details_json or "{}"),
                "status": item.status,
                "error_type": item.error_type,
                "error_message": item.error_message,
            }
            for item in run.results
        ]
        return result
