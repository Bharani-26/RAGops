import json
import time
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Float,
    Integer,
    Text,
    DateTime,
    ForeignKey,
    select,
    func,
    Index,
    inspect,
    text,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from backend.config import settings

logger = logging.getLogger("ragops.database")

Base = declarative_base()


class RequestTrace(Base):
    __tablename__ = "request_traces"

    id = Column(String(64), primary_key=True)
    timestamp = Column(Float, default=time.time, index=True)
    query = Column(Text, nullable=False)
    answer = Column(Text, default="")
    model = Column(String(64), default="")
    latency_ms = Column(Float, default=0.0)
    status_code = Column(Integer, default=200)
    status = Column(String(32), default="success", index=True)
    top_k = Column(Integer, default=4)
    source_count = Column(Integer, default=0)
    sources_json = Column(Text, default="[]")
    stages_json = Column(Text, default="[]")
    estimated_cost = Column(Float, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    error_type = Column(String(128), nullable=True)
    error_message = Column(Text, nullable=True)
    stages = relationship("RequestStage", back_populates="trace", cascade="all, delete-orphan")
    errors = relationship("RequestError", back_populates="trace", cascade="all, delete-orphan")


class RequestStage(Base):
    __tablename__ = "request_stages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(64), ForeignKey("request_traces.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    duration_ms = Column(Float, nullable=False)
    status = Column(String(32), nullable=False, default="success")
    details = Column(Text, nullable=True)
    trace = relationship("RequestTrace", back_populates="stages")


class RequestError(Base):
    __tablename__ = "request_errors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(64), ForeignKey("request_traces.id"), nullable=False, index=True)
    error_type = Column(String(128), nullable=False)
    message = Column(Text, nullable=False)
    timestamp = Column(Float, default=time.time, index=True)
    trace = relationship("RequestTrace", back_populates="errors")


Index("ix_request_traces_timestamp_status", RequestTrace.timestamp, RequestTrace.status)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id = Column(String(64), primary_key=True)
    timestamp = Column(Float, default=time.time, index=True)
    dataset_name = Column(String(128), default="golden_eval_v1")
    dataset_id = Column(String(128), nullable=True, index=True)
    dataset_version = Column(String(64), nullable=True)
    total_samples = Column(Integer, default=0)
    completed_samples = Column(Integer, default=0)
    failed_samples = Column(Integer, default=0)
    avg_relevance = Column(Float, nullable=True)
    avg_faithfulness = Column(Float, nullable=True)
    avg_correctness = Column(Float, nullable=True)
    avg_citation_precision = Column(Float, nullable=True)
    status = Column(String(32), default="completed")
    scoring_config_json = Column(Text, default="{}")
    error_message = Column(Text, nullable=True)
    corpus_version = Column(String(64), nullable=True)
    metric_availability_json = Column(Text, default="{}")
    retrieval_latency_p50_ms = Column(Float, nullable=True)
    generation_latency_p50_ms = Column(Float, nullable=True)
    provider_model = Column(String(128), nullable=True)

    results = relationship("EvaluationResult", back_populates="run", cascade="all, delete-orphan")


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id = Column(String(64), primary_key=True)
    run_id = Column(String(64), ForeignKey("evaluation_runs.id"), index=True)
    question = Column(Text, nullable=False)
    test_case_id = Column(String(128), nullable=True, index=True)
    ground_truth = Column(Text, default="")
    reference_context = Column(Text, default="")
    expected_source = Column(String(256), nullable=True)
    generated_answer = Column(Text, default="")
    context = Column(Text, default="")
    retrieved_chunks_json = Column(Text, default="[]")
    citations_json = Column(Text, default="[]")
    relevance_score = Column(Float, nullable=True)
    faithfulness_score = Column(Float, nullable=True)
    correctness_score = Column(Float, nullable=True)
    citation_score = Column(Float, nullable=True)
    unsupported_claims_json = Column(Text, default="[]")
    citation_details_json = Column(Text, default="{}")
    status = Column(String(32), default="completed")
    error_type = Column(String(128), nullable=True)
    error_message = Column(Text, nullable=True)

    run = relationship("EvaluationRun", back_populates="results")


# Database engine and session factory
DATABASE_URL = f"sqlite:///{settings.SQLITE_DB_PATH.as_posix()}"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create all tables in SQLite database if they don't exist."""
    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError as exc:
        if "already exists" not in str(exc).lower():
            raise
        Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("request_traces")}
    migrations = {
        "error_type": "ALTER TABLE request_traces ADD COLUMN error_type VARCHAR(128)",
        "error_message": "ALTER TABLE request_traces ADD COLUMN error_message TEXT",
    }
    table_migrations = {
        "evaluation_runs": {
            "dataset_id": "ALTER TABLE evaluation_runs ADD COLUMN dataset_id VARCHAR(128)",
            "dataset_version": "ALTER TABLE evaluation_runs ADD COLUMN dataset_version VARCHAR(64)",
            "completed_samples": "ALTER TABLE evaluation_runs ADD COLUMN completed_samples INTEGER DEFAULT 0",
            "failed_samples": "ALTER TABLE evaluation_runs ADD COLUMN failed_samples INTEGER DEFAULT 0",
            "scoring_config_json": "ALTER TABLE evaluation_runs ADD COLUMN scoring_config_json TEXT DEFAULT '{}'",
            "error_message": "ALTER TABLE evaluation_runs ADD COLUMN error_message TEXT",
            "corpus_version": "ALTER TABLE evaluation_runs ADD COLUMN corpus_version VARCHAR(64)",
            "metric_availability_json": "ALTER TABLE evaluation_runs ADD COLUMN metric_availability_json TEXT DEFAULT '{}'",
            "retrieval_latency_p50_ms": "ALTER TABLE evaluation_runs ADD COLUMN retrieval_latency_p50_ms FLOAT",
            "generation_latency_p50_ms": "ALTER TABLE evaluation_runs ADD COLUMN generation_latency_p50_ms FLOAT",
            "provider_model": "ALTER TABLE evaluation_runs ADD COLUMN provider_model VARCHAR(128)",
        },
        "evaluation_results": {
            "test_case_id": "ALTER TABLE evaluation_results ADD COLUMN test_case_id VARCHAR(128)",
            "reference_context": "ALTER TABLE evaluation_results ADD COLUMN reference_context TEXT DEFAULT ''",
            "expected_source": "ALTER TABLE evaluation_results ADD COLUMN expected_source VARCHAR(256)",
            "retrieved_chunks_json": "ALTER TABLE evaluation_results ADD COLUMN retrieved_chunks_json TEXT DEFAULT '[]'",
            "citations_json": "ALTER TABLE evaluation_results ADD COLUMN citations_json TEXT DEFAULT '[]'",
            "unsupported_claims_json": "ALTER TABLE evaluation_results ADD COLUMN unsupported_claims_json TEXT DEFAULT '[]'",
            "citation_details_json": "ALTER TABLE evaluation_results ADD COLUMN citation_details_json TEXT DEFAULT '{}'",
            "status": "ALTER TABLE evaluation_results ADD COLUMN status VARCHAR(32) DEFAULT 'completed'",
            "error_type": "ALTER TABLE evaluation_results ADD COLUMN error_type VARCHAR(128)",
            "error_message": "ALTER TABLE evaluation_results ADD COLUMN error_message TEXT",
        },
    }
    with engine.begin() as connection:
        for column, statement in migrations.items():
            if column not in columns:
                connection.execute(text(statement))
        for table_name, table_columns in table_migrations.items():
            existing_columns = {
                column["name"] for column in inspect(engine).get_columns(table_name)
            }
            for column, statement in table_columns.items():
                if column not in existing_columns:
                    connection.execute(text(statement))
        # Previous versions wrote a fixed cost with zero token counts. Keep
        # those traces, but do not present the fabricated value as measured.
        connection.execute(text(
            "UPDATE request_traces SET estimated_cost = NULL "
            "WHERE (prompt_tokens IS NULL OR prompt_tokens = 0) "
            "AND (completion_tokens IS NULL OR completion_tokens = 0)"
        ))


def check_sqlite_health() -> bool:
    """Readiness probe checking SQLite connectivity."""
    try:
        with SessionLocal() as session:
            session.execute(select(1))
            return True
    except Exception:
        return False


def record_trace(
    request_id: str,
    query: str,
    answer: str,
    model: str,
    latency_ms: float,
    status_code: int,
    status: str,
    top_k: int,
    sources: List[Dict[str, Any]],
    stages: List[Dict[str, Any]],
    estimated_cost: Optional[float] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
):
    try:
        safe_sources = [
            {
                key: value
                for key, value in source.items()
                if key not in {"content_preview", "content", "page_content"}
            }
            for source in sources
        ]
        with SessionLocal() as session:
            trace = RequestTrace(
                id=request_id,
                timestamp=time.time(),
                query=query,
                answer=answer,
                model=model,
                latency_ms=latency_ms,
                status_code=status_code,
                status=status,
                top_k=top_k,
                source_count=len(sources),
                sources_json=json.dumps(safe_sources),
                stages_json=json.dumps(stages),
                estimated_cost=estimated_cost,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                error_type=error_type,
                error_message=error_message,
            )
            session.add(trace)
            for stage in stages:
                session.add(RequestStage(
                    request_id=request_id,
                    name=str(stage.get("name", "unknown")),
                    duration_ms=float(stage.get("duration_ms") or 0.0),
                    status=str(stage.get("status", "unknown")),
                    details=stage.get("details"),
                ))
                if stage.get("status") == "error":
                    session.add(RequestError(
                        request_id=request_id,
                        error_type=error_type or "stage_error",
                        message=str(stage.get("error") or error_message or "Stage failed"),
                    ))
            if error_type and error_message and not any(stage.get("status") == "error" for stage in stages):
                session.add(RequestError(
                    request_id=request_id,
                    error_type=error_type,
                    message=error_message,
                ))
            session.commit()
    except Exception:
        logger.exception("Error persisting request trace")


def refresh_missing_trace_costs() -> int:
    """Backfill costs for traces that already contain token usage."""
    if (
        settings.INPUT_PRICE_PER_MILLION_TOKENS is None
        or settings.OUTPUT_PRICE_PER_MILLION_TOKENS is None
    ):
        return 0
    with SessionLocal() as session:
        rows = session.scalars(
            select(RequestTrace).where(
                RequestTrace.estimated_cost.is_(None),
                RequestTrace.prompt_tokens.is_not(None),
                RequestTrace.completion_tokens.is_not(None),
            )
        ).all()
        for row in rows:
            row.estimated_cost = (
                row.prompt_tokens * settings.INPUT_PRICE_PER_MILLION_TOKENS / 1_000_000
                + row.completion_tokens * settings.OUTPUT_PRICE_PER_MILLION_TOKENS / 1_000_000
            )
        if rows:
            session.commit()
        return len(rows)


def get_all_traces(limit: int = 100) -> List[Dict[str, Any]]:
    refresh_missing_trace_costs()
    with SessionLocal() as session:
        query = select(RequestTrace).order_by(RequestTrace.timestamp.desc()).limit(limit)
        rows = session.scalars(query).all()
        traces = []
        for r in rows:
            traces.append({
                "id": r.id,
                "timestamp": r.timestamp,
                "query": r.query,
                "answer": r.answer,
                "model": r.model,
                "latency_ms": r.latency_ms,
                "status_code": r.status_code,
                "status": r.status,
                "top_k": r.top_k,
                "source_count": r.source_count,
                "sources": json.loads(r.sources_json) if r.sources_json else [],
                "stages": [
                    {
                        "name": stage.name,
                        "duration_ms": stage.duration_ms,
                        "status": stage.status,
                        "details": stage.details,
                    }
                    for stage in r.stages
                ] or (json.loads(r.stages_json) if r.stages_json else []),
                "estimated_cost": r.estimated_cost,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "error_type": r.error_type,
                "error_message": r.error_message,
            })
        return traces


def get_metrics_summary() -> Dict[str, Any]:
    refresh_missing_trace_costs()
    with SessionLocal() as session:
        rows = session.scalars(select(RequestTrace)).all()
        total_requests = len(rows)
        if total_requests == 0:
            return {
                "total_requests": 0,
                "p95_latency_ms": 0.0,
                "avg_latency_ms": 0.0,
                "error_rate": 0.0,
                "total_cost": 0.0,
            }

        latencies = [r.latency_ms for r in rows]
        latencies.sort()
        p95_idx = int(len(latencies) * 0.95)
        p95_latency = latencies[min(p95_idx, len(latencies) - 1)]
        avg_latency = sum(latencies) / len(latencies)

        errors = sum(1 for r in rows if r.status == "error")
        error_rate = (errors / total_requests) * 100.0
        available_costs = [r.estimated_cost for r in rows if r.estimated_cost is not None]
        total_cost = sum(available_costs) if available_costs else None

        return {
            "total_requests": total_requests,
            "p95_latency_ms": round(p95_latency, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "error_rate": round(error_rate, 2),
            "total_cost": round(total_cost, 6) if total_cost is not None else None,
        }


def get_all_evaluations() -> List[Dict[str, Any]]:
    with SessionLocal() as session:
        query = select(EvaluationRun).order_by(EvaluationRun.timestamp.desc())
        runs = session.scalars(query).all()
        return [
            {
                "id": r.id,
                "timestamp": r.timestamp,
                "dataset_name": r.dataset_name,
                "total_samples": r.total_samples,
                "retrieval_relevance": r.avg_relevance,
                "faithfulness": r.avg_faithfulness,
                "answer_correctness": r.avg_correctness,
                "citation_accuracy": r.avg_citation_precision,
                "status": r.status,
            }
            for r in runs
        ]


def clear_request_telemetry() -> int:
    """Delete request traces and their related stages/errors."""
    with SessionLocal() as session:
        traces = session.scalars(select(RequestTrace)).all()
        count = len(traces)
        for trace in traces:
            session.delete(trace)
        session.commit()
        return count


def clear_evaluation_runs() -> int:
    """Delete persisted evaluation runs and their question-level results."""
    with SessionLocal() as session:
        runs = session.scalars(select(EvaluationRun)).all()
        count = len(runs)
        for run in runs:
            session.delete(run)
        session.commit()
        return count


# Automatically initialize tables
init_db()
