import logging
from typing import List, Optional, Any, Dict
import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from backend.config import settings

logger = logging.getLogger("ragops.retrieval")


def get_embedding_model() -> GoogleGenerativeAIEmbeddings:
    """Initialize Google Generative AI embeddings model."""
    if not settings.GOOGLE_API_KEY or "your_gemini" in settings.GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY is not configured. Please set a valid key in .env.")
    return GoogleGenerativeAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
    )


def get_vector_store(
    embedding_model: Optional[Any] = None,
    collection_name: Optional[str] = None,
) -> Chroma:
    """
    Initialize or load persistent Chroma vector store from settings.CHROMA_PERSIST_DIR.
    Ensures collections and vectors survive FastAPI restarts.
    """
    client = chromadb.PersistentClient(path=str(settings.CHROMA_PERSIST_DIR))
    collection = collection_name or settings.CHROMA_COLLECTION_NAME
    existing = next(
        (item for item in client.list_collections()
         if item.name == collection),
        None,
    )
    expected_model = settings.EMBEDDING_MODEL
    if existing and existing.metadata:
        stored_model = existing.metadata.get("embedding_model")
        if stored_model and stored_model != expected_model:
            raise ValueError(
                f"Chroma collection uses embedding model '{stored_model}', "
                f"but the application is configured for '{expected_model}'. "
                "Use a new collection and reindex documents; do not delete the existing collection."
            )
    elif not existing:
        client.get_or_create_collection(
            name=collection,
            metadata={
                "embedding_provider": "google_gemini",
                "embedding_model": expected_model,
            },
        )

    embeddings = embedding_model or get_embedding_model()
    return Chroma(
        collection_name=collection,
        embedding_function=embeddings,
        persist_directory=str(settings.CHROMA_PERSIST_DIR),
    )


def check_chroma_health(vector_store: Optional[Chroma] = None) -> bool:
    """Readiness probe checking ChromaDB accessibility."""
    try:
        # Check if collection exists or can be opened
        import chromadb
        client = chromadb.PersistentClient(path=str(settings.CHROMA_PERSIST_DIR))
        client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
            metadata={
                "embedding_provider": "google_gemini",
                "embedding_model": settings.EMBEDDING_MODEL,
            },
        )
        return True
    except Exception:
        return False


def store_documents(documents: List[Document], vector_store: Optional[Chroma] = None) -> List[str]:
    """
    Index documents into the persistent Chroma store with unique chunk IDs and metadata.
    """
    if not documents:
        return []
    store = vector_store or get_vector_store()
    ids = [
        doc.metadata.get("chunk_id") or f"{doc.metadata.get('source', 'doc')}_{doc.metadata.get('chunk_index', i)}"
        for i, doc in enumerate(documents)
    ]
    # Upsert is intentionally avoided: ids are document-scoped and the route
    # checks content hashes before this function is called.
    store.add_documents(documents=documents, ids=ids)
    return ids


def find_document_by_hash(content_sha256: str) -> Optional[Dict[str, Any]]:
    """Return an existing document summary for an idempotent upload."""
    client = chromadb.PersistentClient(path=str(settings.CHROMA_PERSIST_DIR))
    collection = client.get_or_create_collection(name=settings.CHROMA_COLLECTION_NAME)
    result = collection.get(
        where={"content_sha256": content_sha256},
        include=["metadatas"],
        limit=1,
    )
    metadatas = result.get("metadatas") or []
    if not metadatas:
        return None
    metadata = metadatas[0]
    document_id = metadata.get("doc_id")
    if not document_id:
        return None
    chunk_result = collection.get(
        where={"doc_id": document_id},
        include=["metadatas"],
    )
    chunk_metadata = chunk_result.get("metadatas") or []
    return {
        "doc_id": document_id,
        "filename": metadata.get("source", "document"),
        "chunk_ids": [
            item.get("chunk_id")
            for item in chunk_metadata
            if item.get("chunk_id")
        ],
    }


def list_stored_documents() -> List[Dict[str, Any]]:
    """Build document listings from persisted Chroma metadata."""
    client = chromadb.PersistentClient(path=str(settings.CHROMA_PERSIST_DIR))
    collection = client.get_or_create_collection(name=settings.CHROMA_COLLECTION_NAME)
    result = collection.get(include=["metadatas"])
    grouped: Dict[str, Dict[str, Any]] = {}
    for metadata in result.get("metadatas") or []:
        document_id = metadata.get("doc_id")
        if not document_id:
            continue
        if document_id not in grouped:
            grouped[document_id] = {
                "document_id": document_id,
                "doc_id": document_id,
                "filename": metadata.get("source", "document"),
                "server_filename": metadata.get("server_filename"),
                "content_sha256": metadata.get("content_sha256"),
                "chunk_count": metadata.get("total_chunks", 0),
            }
    for document in grouped.values():
        server_name = document.get("server_filename")
        if server_name:
            path = settings.UPLOAD_DIR / server_name
            if path.is_file():
                document["size_bytes"] = path.stat().st_size
                document["modified_at"] = path.stat().st_mtime
    return sorted(grouped.values(), key=lambda item: item["filename"].lower())


def get_stored_document(document_id: str) -> Optional[Dict[str, Any]]:
    """Return persisted metadata and chunk details for one document."""
    client = chromadb.PersistentClient(path=str(settings.CHROMA_PERSIST_DIR))
    collection = client.get_or_create_collection(name=settings.CHROMA_COLLECTION_NAME)
    result = collection.get(
        where={"doc_id": document_id},
        include=["metadatas", "documents"],
    )
    metadatas = result.get("metadatas") or []
    if not metadatas:
        return None
    first = metadatas[0]
    return {
        "document_id": document_id,
        "doc_id": document_id,
        "filename": first.get("source", "document"),
        "server_filename": first.get("server_filename"),
        "chunk_count": len(metadatas),
        "chunks": [
            {
                "chunk_id": metadata.get("chunk_id"),
                "chunk_index": metadata.get("chunk_index"),
                "page_number": metadata.get("page_number"),
                "content_preview": (
                    (result.get("documents") or [""] * len(metadatas))[index][:200]
                ),
            }
            for index, metadata in enumerate(metadatas)
        ],
    }


def list_stored_chunks(
    page: int = 1,
    page_size: int = 20,
    document_id: Optional[str] = None,
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """List persisted Chroma chunks with pagination and optional filters."""
    if page < 1:
        raise ValueError("page must be greater than or equal to 1")
    if page_size < 1 or page_size > 100:
        raise ValueError("page_size must be between 1 and 100")

    client = chromadb.PersistentClient(path=str(settings.CHROMA_PERSIST_DIR))
    collection = client.get_or_create_collection(name=settings.CHROMA_COLLECTION_NAME)
    result = collection.get(include=["metadatas", "documents"])
    metadatas = result.get("metadatas") or []
    documents = result.get("documents") or []
    chunks: List[Dict[str, Any]] = []
    for index, metadata in enumerate(metadatas):
        current_document_id = metadata.get("doc_id")
        current_filename = metadata.get("source", "document")
        if document_id and current_document_id != document_id:
            continue
        if filename and filename.lower() not in current_filename.lower():
            continue
        chunks.append({
            "chunk_id": metadata.get("chunk_id"),
            "document_id": current_document_id,
            "filename": current_filename,
            "page_number": metadata.get("page_number"),
            "metadata": metadata,
            "text": documents[index] if index < len(documents) else "",
        })

    chunks.sort(key=lambda item: (
        str(item.get("filename") or "").lower(),
        str(item.get("document_id") or ""),
        item.get("metadata", {}).get("chunk_index", 0),
    ))
    total = len(chunks)
    start = (page - 1) * page_size
    page_chunks = chunks[start:start + page_size]
    grouped: Dict[str, Dict[str, Any]] = {}
    for chunk in chunks:
        key = chunk["document_id"]
        if not key:
            continue
        if key not in grouped:
            grouped[key] = {
                "document_id": key,
                "filename": chunk["filename"],
                "chunk_count": 0,
            }
        grouped[key]["chunk_count"] += 1

    return {
        "chunks": page_chunks,
        "documents": sorted(grouped.values(), key=lambda item: item["filename"].lower()),
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


def retrieve_relevant_documents(
    query: str,
    top_k: Optional[int] = None,
    vector_store: Optional[Chroma] = None,
    collection_name: Optional[str] = None,
) -> List[Document]:
    """Retrieve top-k relevant chunks based on semantic similarity."""
    k = top_k if top_k is not None and top_k > 0 else settings.DEFAULT_TOP_K
    store = vector_store or get_vector_store(collection_name=collection_name)
    return store.similarity_search(query=query, k=k)
