from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routes import router as rag_router, public_router, observability_router, evaluation_router

app = FastAPI(
    title="RAGOps",
    description="AI observability and evaluation platform for RAG applications",
    version="0.2.0"
)

# Enable CORS for future frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include RAG router
app.include_router(rag_router)
app.include_router(public_router)
app.include_router(observability_router)
app.include_router(evaluation_router)


@app.get("/")
def read_root():
    return {
        "project": "RAGOps",
        "status": "running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


@app.get("/api/health")
def api_health_check():
    return {"status": "healthy"}


@app.get("/api/health/ready")
def api_readiness_check():
    from backend.database import check_sqlite_health
    from backend.retrieval import check_chroma_health

    chroma_ok = check_chroma_health()
    sqlite_ok = check_sqlite_health()
    return {
        "status": "ready" if chroma_ok and sqlite_ok else "degraded",
        "chromadb": "accessible" if chroma_ok else "unreachable",
        "sqlite": "accessible" if sqlite_ok else "unreachable",
    }
