import sqlite3
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from backend.config import settings

DB_PATH = settings.CHROMA_PERSIST_DIR.parent / "ragops_observability.db"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS traces (
        id TEXT PRIMARY KEY,
        timestamp REAL,
        query TEXT,
        answer TEXT,
        model TEXT,
        latency_ms REAL,
        status_code INTEGER,
        status TEXT,
        top_k INTEGER,
        source_count INTEGER,
        sources_json TEXT,
        stages_json TEXT,
        estimated_cost REAL
    )
    """)
    conn.commit()
    conn.close()


init_db()


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
    estimated_cost: float,
):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO traces (
            id, timestamp, query, answer, model, latency_ms, status_code,
            status, top_k, source_count, sources_json, stages_json, estimated_cost
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request_id,
            time.time(),
            query,
            answer,
            model,
            latency_ms,
            status_code,
            status,
            top_k,
            len(sources),
            json.dumps(sources),
            json.dumps(stages),
            estimated_cost,
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Failed to record trace: {e}")


def get_all_traces(limit: int = 100) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM traces ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    traces = []
    for r in rows:
        traces.append({
            "id": r["id"],
            "timestamp": r["timestamp"],
            "query": r["query"],
            "answer": r["answer"],
            "model": r["model"],
            "latency_ms": r["latency_ms"],
            "status_code": r["status_code"],
            "status": r["status"],
            "top_k": r["top_k"],
            "source_count": r["source_count"],
            "sources": json.loads(r["sources_json"]) if r["sources_json"] else [],
            "stages": json.loads(r["stages_json"]) if r["stages_json"] else [],
            "estimated_cost": r["estimated_cost"],
        })
    return traces


def get_metrics_summary() -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT latency_ms, status, estimated_cost, timestamp FROM traces")
    rows = cursor.fetchall()
    conn.close()

    total_requests = len(rows)
    if total_requests == 0:
        return {
            "total_requests": 0,
            "p95_latency_ms": 0.0,
            "avg_latency_ms": 0.0,
            "error_rate": 0.0,
            "total_cost": 0.0,
            "recent_volume": [],
            "recent_latency": [],
        }

    latencies = [r["latency_ms"] for r in rows]
    latencies.sort()
    p95_idx = int(len(latencies) * 0.95)
    p95_latency = latencies[min(p95_idx, len(latencies) - 1)]
    avg_latency = sum(latencies) / len(latencies)

    errors = sum(1 for r in rows if r["status"] == "error")
    error_rate = (errors / total_requests) * 100.0
    total_cost = sum(r["estimated_cost"] for r in rows)

    return {
        "total_requests": total_requests,
        "p95_latency_ms": round(p95_latency, 2),
        "avg_latency_ms": round(avg_latency, 2),
        "error_rate": round(error_rate, 2),
        "total_cost": round(total_cost, 6),
    }

