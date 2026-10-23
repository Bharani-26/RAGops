"""Read-only metrics over persisted RAG request traces."""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from backend.database import (
    RequestError,
    RequestStage,
    RequestTrace,
    SessionLocal,
    refresh_missing_trace_costs,
)


def percentile(values: List[float], percentile_value: float) -> Optional[float]:
    """Return a linearly interpolated percentile (NumPy-compatible method)."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    rank = (len(ordered) - 1) * percentile_value / 100
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 2)


def _timestamp(value: Optional[datetime]) -> Optional[float]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _filtered_query(
    status: Optional[str],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
):
    query = select(RequestTrace).order_by(RequestTrace.timestamp.desc())
    conditions = []
    if status:
        conditions.append(RequestTrace.status == status)
    if date_from:
        conditions.append(RequestTrace.timestamp >= _timestamp(date_from))
    if date_to:
        conditions.append(RequestTrace.timestamp <= _timestamp(date_to))
    return query.where(*conditions) if conditions else query


def _trace_dict(trace: RequestTrace) -> Dict[str, Any]:
    return {
        "request_id": trace.id,
        "timestamp": trace.timestamp,
        "query": trace.query,
        "model": trace.model,
        "status": trace.status,
        "status_code": trace.status_code,
        "latency_ms": trace.latency_ms,
        "retrieved_chunks": trace.source_count,
        "sources": json.loads(trace.sources_json) if trace.sources_json else [],
        "input_tokens": trace.prompt_tokens,
        "output_tokens": trace.completion_tokens,
        "estimated_cost": trace.estimated_cost,
        "error_type": trace.error_type,
        "error_message": trace.error_message,
    }


def get_overview(
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> Dict[str, Any]:
    refresh_missing_trace_costs()
    with SessionLocal() as session:
        rows = session.scalars(_filtered_query(status, date_from, date_to)).all()
    total = len(rows)
    successful = sum(row.status == "success" for row in rows)
    latencies = [row.latency_ms for row in rows if row.status == "success"]
    costs = [row.estimated_cost for row in rows if row.estimated_cost is not None]
    return {
        "total_requests": total,
        "success_count": successful,
        "failure_count": total - successful,
        "success_rate": round(successful / total * 100, 2) if total else 0.0,
        "average_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "p50_latency_ms": percentile(latencies, 50),
        "p95_latency_ms": percentile(latencies, 95),
        "estimated_cost": round(sum(costs), 8) if costs else None,
        "cost_available": bool(costs),
        "token_usage_available": any(
            row.prompt_tokens is not None or row.completion_tokens is not None for row in rows
        ),
        "metric_rules": {
            "latency": "Successful requests only; p50/p95 use linear interpolation.",
            "cost": "Only records with available token usage and configured pricing.",
        },
    }


def get_requests(
    page: int,
    page_size: int,
    status: Optional[str],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> Dict[str, Any]:
    refresh_missing_trace_costs()
    with SessionLocal() as session:
        rows = session.scalars(_filtered_query(status, date_from, date_to)).all()
    start = (page - 1) * page_size
    return {
        "page": page,
        "page_size": page_size,
        "total": len(rows),
        "requests": [_trace_dict(row) for row in rows[start:start + page_size]],
    }


def get_request_detail(request_id: str) -> Optional[Dict[str, Any]]:
    with SessionLocal() as session:
        trace = session.get(RequestTrace, request_id)
        if trace is None:
            return None
        result = _trace_dict(trace)
        result["stages"] = [
            {
                "name": stage.name,
                "duration_ms": stage.duration_ms,
                "status": stage.status,
                "details": stage.details,
            }
            for stage in trace.stages
        ]
        result["errors"] = [
            {
                "error_type": error.error_type,
                "message": error.message,
                "timestamp": error.timestamp,
            }
            for error in trace.errors
        ]
        return result


def get_latency(
    status: Optional[str],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> Dict[str, Any]:
    with SessionLocal() as session:
        rows = session.scalars(_filtered_query(status, date_from, date_to)).all()
    successful = [row for row in rows if row.status == "success"]
    return {
        "points": [
            {
                "timestamp": row.timestamp,
                "latency_ms": row.latency_ms,
                "retrieved_chunks": row.source_count,
            }
            for row in reversed(successful)
        ],
        "p50_latency_ms": percentile([row.latency_ms for row in successful], 50),
        "p95_latency_ms": percentile([row.latency_ms for row in successful], 95),
    }


def get_errors(
    limit: int,
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> Dict[str, Any]:
    with SessionLocal() as session:
        query = select(RequestError).order_by(RequestError.timestamp.desc())
        conditions = []
        if date_from:
            conditions.append(RequestError.timestamp >= _timestamp(date_from))
        if date_to:
            conditions.append(RequestError.timestamp <= _timestamp(date_to))
        if conditions:
            query = query.where(*conditions)
        errors = session.scalars(query.limit(limit)).all()
    grouped: Dict[str, Dict[str, Any]] = {}
    for error in errors:
        item = grouped.setdefault(error.error_type, {"error_type": error.error_type, "count": 0, "recent": []})
        item["count"] += 1
        if len(item["recent"]) < 5:
            item["recent"].append({
                "request_id": error.request_id,
                "message": error.message,
                "timestamp": error.timestamp,
            })
    return {"errors": list(grouped.values()), "total": len(errors)}


def get_costs(
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> Dict[str, Any]:
    refresh_missing_trace_costs()
    with SessionLocal() as session:
        rows = session.scalars(_filtered_query(None, date_from, date_to)).all()
    available = [row for row in rows if row.estimated_cost is not None]
    return {
        "points": [
            {
                "timestamp": row.timestamp,
                "input_tokens": row.prompt_tokens,
                "output_tokens": row.completion_tokens,
                "estimated_cost": row.estimated_cost,
            }
            for row in reversed(available)
        ],
        "total_estimated_cost": round(sum(row.estimated_cost for row in available), 8) if available else None,
        "total_input_tokens": (
            sum(row.prompt_tokens for row in available if row.prompt_tokens is not None) or None
        ),
        "total_output_tokens": (
            sum(row.completion_tokens for row in available if row.completion_tokens is not None) or None
        ),
        "cost_available": bool(available),
    }
