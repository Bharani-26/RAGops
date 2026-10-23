import io
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from backend.main import app
from backend.config import settings
from backend.database import record_trace, get_all_traces, get_metrics_summary, check_sqlite_health
from backend.retrieval import store_documents, retrieve_relevant_documents, get_vector_store, check_chroma_health

client = TestClient(app)


def test_read_root():
    """Verify root endpoint remains intact."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "project": "RAGOps",
        "status": "running"
    }


def test_health_check():
    """Verify health endpoint remains intact."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy"
    }


def test_requested_health_aliases():
    assert client.get("/api/health").json() == {"status": "healthy"}
    response = client.get("/api/health/ready")
    assert response.status_code in (200, 503)
    assert response.json()["status"] in ("ready", "degraded")


def test_readiness_probe():
    """Verify persistent storage readiness check endpoint."""
    response = client.get("/api/rag/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ready", "degraded")
    assert "chromadb" in data
    assert "sqlite" in data
    assert "storage_paths" in data


def test_clear_runtime_data_scopes():
    with patch("backend.routes.clear_stored_documents", return_value=3) as clear_documents, \
         patch("backend.routes.clear_request_telemetry", return_value=4) as clear_telemetry, \
         patch("backend.routes.clear_evaluation_runs", return_value=2) as clear_evaluations:
        response = client.delete("/api/rag/data/all")

    assert response.status_code == 200
    assert response.json() == {
        "scope": "all",
        "deleted": 9,
        "message": "Cleared 9 runtime records from all.",
    }
    clear_documents.assert_called_once()
    clear_telemetry.assert_called_once()
    clear_evaluations.assert_called_once()


# =========================================================================
# Upload & Ingestion Tests
# =========================================================================

def test_upload_txt_success():
    """Test successful text file upload and indexing with mocked storage."""
    file_content = b"FastAPI is a modern, fast web framework for building APIs with Python."
    files = {"file": ("framework_info.txt", io.BytesIO(file_content), "text/plain")}

    with patch("backend.routes.store_documents") as mock_store:
        mock_store.return_value = ["test_chunk_id_0"]
        response = client.post("/api/rag/upload", files=files)
        
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "framework_info.txt"
        assert "doc_id" in data
        assert data["total_chunks"] >= 1
        assert "test_chunk_id_0" in data["chunk_ids"]
        assert mock_store.called


def test_upload_pdf_success():
    """Test successful PDF upload and text extraction with mocked pypdf & storage."""
    fake_pdf = b"%PDF-1.4 simulated pdf binary content"
    files = {"file": ("test_paper.pdf", io.BytesIO(fake_pdf), "application/pdf")}

    with patch("backend.ingestion.pypdf.PdfReader") as mock_pdf_reader, \
         patch("backend.routes.store_documents") as mock_store:
        
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Retrieval Augmented Generation enhances LLMs with external facts."
        mock_pdf_reader.return_value.pages = [mock_page]
        mock_store.return_value = ["test_paper_c0"]

        response = client.post("/api/rag/upload", files=files)
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "test_paper.pdf"
        assert "doc_id" in data
        assert data["total_chunks"] >= 1
        assert "test_paper_c0" in data["chunk_ids"]


def test_upload_empty_file_fails():
    """Test that uploading empty file fails with 400 Bad Request."""
    files = {"file": ("empty.txt", io.BytesIO(b""), "text/plain")}
    response = client.post("/api/rag/upload", files=files)
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_upload_invalid_extension_fails():
    """Test that uploading executable or unsupported file extension fails with 400."""
    files = {"file": ("script.exe", io.BytesIO(b"executable binary"), "application/octet-stream")}
    response = client.post("/api/rag/upload", files=files)
    assert response.status_code == 400
    assert "unsupported file format" in response.json()["detail"].lower()


def test_duplicate_upload_reuses_existing_chunks():
    files = {"file": ("framework_info.txt", io.BytesIO(b"same content"), "text/plain")}
    existing = {
        "filename": "framework_info.txt",
        "doc_id": "existing-document",
        "chunk_ids": ["existing-document_c0"],
    }
    with patch("backend.routes.find_document_by_hash", return_value=existing), \
         patch("backend.routes.store_documents") as mock_store:
        response = client.post("/api/documents/upload", files=files)
    assert response.status_code == 200
    assert response.json()["doc_id"] == "existing-document"
    assert response.json()["chunk_ids"] == ["existing-document_c0"]
    mock_store.assert_not_called()


def test_list_documents_endpoint():
    """Verify GET /api/rag/documents lists uploaded files."""
    response = client.get("/api/rag/documents")
    assert response.status_code == 200
    assert "documents" in response.json()
    assert isinstance(response.json()["documents"], list)


def test_list_chunks_endpoint():
    expected = {
        "chunks": [{
            "chunk_id": "doc-1_c0",
            "document_id": "doc-1",
            "filename": "notes.txt",
            "page_number": 1,
            "metadata": {"chunk_index": 0},
            "text": "Stored chunk text",
        }],
        "documents": [{"document_id": "doc-1", "filename": "notes.txt", "chunk_count": 1}],
        "page": 1,
        "page_size": 10,
        "total": 1,
        "total_pages": 1,
    }
    with patch("backend.routes.list_stored_chunks", return_value=expected):
        response = client.get("/api/rag/chunks?filename=notes&page_size=10")
    assert response.status_code == 200
    assert response.json() == expected
# =========================================================================
# Query & Observability Tests
# =========================================================================

def test_query_rag_success_and_trace_recording():
    """Test querying the RAG pipeline with mocked retrieval & LLM, and verify SQLite trace logging."""
    mock_doc = Document(
        page_content="RAGOps provides evaluation and observability for RAG architectures.",
        metadata={"source": "ragops_overview.txt", "chunk_index": 0, "total_chunks": 1, "page_number": 1}
    )

    with patch("backend.routes.retrieve_relevant_documents") as mock_retrieve, \
         patch("backend.routes.generate_answer") as mock_generate:
        
        mock_retrieve.return_value = [mock_doc]
        mock_generate.return_value = {
            "answer": "RAGOps provides evaluation and observability.",
            "sources": [{
                "source": "ragops_overview.txt",
                "chunk_index": 0,
                "total_chunks": 1,
                "content_preview": mock_doc.page_content,
                "metadata": mock_doc.metadata
            }]
        }

        response = client.post("/api/rag/query", json={"query": "What does RAGOps provide?", "top_k": 3})
        assert response.status_code == 200
        data = response.json()
        assert "request_id" in data
        assert data["query"] == "What does RAGOps provide?"
        assert data["answer"] == "RAGOps provides evaluation and observability."
        assert len(data["sources"]) == 1

        # Verify trace was stored in SQLite
        traces = get_all_traces(limit=10)
        matching_trace = next((t for t in traces if t["id"] == data["request_id"]), None)
        assert matching_trace is not None
        assert matching_trace["query"] == "What does RAGOps provide?"
        assert matching_trace["status"] == "success"
        assert len(matching_trace["stages"]) >= 2


def test_query_rag_out_of_context():
    """Test model properly answers when context does not contain answer."""
    with patch("backend.routes.retrieve_relevant_documents") as mock_retrieve, \
         patch("backend.routes.generate_answer") as mock_generate:
        
        mock_retrieve.return_value = []
        mock_generate.return_value = {
            "answer": "The retrieved context does not contain sufficient information to answer this question.",
            "sources": []
        }

        response = client.post("/api/rag/query", json={"query": "Who landed on Mars in 1840?"})
        assert response.status_code == 200
        data = response.json()
        assert "not contain sufficient information" in data["answer"]
        assert len(data["sources"]) == 0


def test_query_rag_empty_query_fails():
    """Test that sending an empty query fails validation."""
    response = client.post("/api/rag/query", json={"query": ""})
    assert response.status_code == 422


# =========================================================================
# ChromaDB Persistence & Restart Verification
# =========================================================================

class MockEmbeddingFunction:
    """Deterministic mock embedding function for fast unit tests without Gemini network calls."""
    def embed_documents(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]

    def embed_query(self, text):
        return [0.1, 0.2, 0.3]


def test_chroma_persistence_across_restarts():
    """
    Directly verify that Chroma vector store persists collections and chunks
    to disk and survives application restarts (re-instantiating Chroma instance).
    """
    temp_dir = tempfile.mkdtemp(prefix="test_chroma_persist_")
    try:
        mock_emb = MockEmbeddingFunction()

        # Step 1: Open Chroma in a clean persist directory and add documents
        from langchain_chroma import Chroma
        test_store1 = Chroma(
            collection_name="restart_test_collection",
            embedding_function=mock_emb,
            persist_directory=temp_dir,
        )
        doc1 = Document(
            page_content="ChromaDB persists vector data locally across application restarts.",
            metadata={"source": "persistence_guide.txt", "chunk_index": 0, "page_number": 1, "doc_id": "doc_101"}
        )
        test_store1.add_documents([doc1], ids=["doc_101_c0"])

        # Verify initial retrieval
        res1 = test_store1.similarity_search("How does ChromaDB persist data?", k=1)
        assert len(res1) == 1
        assert "persists vector data locally" in res1[0].page_content

        # Step 2: Simulate application shutdown/restart by destroying store1 reference
        del test_store1

        # Step 3: Re-open Chroma from the same persist directory
        test_store2 = Chroma(
            collection_name="restart_test_collection",
            embedding_function=mock_emb,
            persist_directory=temp_dir,
        )

        # Retrieve again without re-indexing
        res2 = test_store2.similarity_search("How does ChromaDB persist data?", k=1)
        assert len(res2) == 1
        assert res2[0].page_content == doc1.page_content
        assert res2[0].metadata["source"] == "persistence_guide.txt"
        assert res2[0].metadata["page_number"] == 1
        assert res2[0].metadata["doc_id"] == "doc_101"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
