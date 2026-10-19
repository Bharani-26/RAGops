import uuid

from backend.database import RequestTrace, SessionLocal, record_trace
from backend.observability import get_overview, get_request_detail, percentile
from backend.routes import _estimate_cost


def test_percentile_uses_linear_interpolation():
    assert percentile([10, 20, 30, 40], 50) == 25.0
    assert percentile([10, 20, 30, 40], 95) == 38.5
    assert percentile([], 95) is None


def test_cost_estimation_requires_usage_and_pricing(monkeypatch):
    monkeypatch.setattr("backend.routes.settings.INPUT_PRICE_PER_MILLION_TOKENS", 1.0)
    monkeypatch.setattr("backend.routes.settings.OUTPUT_PRICE_PER_MILLION_TOKENS", 2.0)
    assert _estimate_cost(1000, 500) == 0.002
    assert _estimate_cost(None, 500) is None


def test_successful_trace_persists_stages_and_optional_usage():
    request_id = f"test-{uuid.uuid4()}"
    record_trace(
        request_id=request_id,
        query="metrics test",
        answer="answer",
        model="test-model",
        latency_ms=120.0,
        status_code=200,
        status="success",
        top_k=2,
        sources=[{"source": "test.txt", "content_preview": "must not be logged"}],
        stages=[
            {"name": "retrieval", "duration_ms": 20.0, "status": "success"},
            {"name": "generation", "duration_ms": 100.0, "status": "success"},
        ],
    )
    detail = get_request_detail(request_id)
    assert detail is not None
    assert len(detail["stages"]) == 2
    assert detail["estimated_cost"] is None
    assert detail["input_tokens"] is None
    assert all("content_preview" not in source for source in detail.get("sources", []))
    with SessionLocal() as session:
        trace = session.get(RequestTrace, request_id)
        session.delete(trace)
        session.commit()


def test_failed_trace_is_counted_and_has_error_detail():
    request_id = f"test-{uuid.uuid4()}"
    record_trace(
        request_id=request_id,
        query="failed metrics test",
        answer="",
        model="test-model",
        latency_ms=40.0,
        status_code=500,
        status="error",
        top_k=2,
        sources=[],
        stages=[{"name": "generation", "duration_ms": 40.0, "status": "error", "error": "provider unavailable"}],
        error_type="ProviderError",
        error_message="provider unavailable",
    )
    detail = get_request_detail(request_id)
    assert detail is not None
    assert detail["error_type"] == "ProviderError"
    assert detail["errors"][0]["error_type"] == "ProviderError"
    with SessionLocal() as session:
        trace = session.get(RequestTrace, request_id)
        session.delete(trace)
        session.commit()


def test_empty_overview_has_no_fabricated_latency_or_cost(monkeypatch):
    class EmptyResult:
        def all(self):
            return []

    class EmptySession:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def scalars(self, _query):
            return EmptyResult()

    monkeypatch.setattr("backend.observability.SessionLocal", lambda: EmptySession())
    overview = get_overview()
    assert overview["total_requests"] == 0
    assert overview["average_latency_ms"] is None
    assert overview["p95_latency_ms"] is None
    assert overview["estimated_cost"] is None
