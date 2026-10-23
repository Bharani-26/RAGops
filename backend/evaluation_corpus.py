"""Isolated, versioned evaluation corpus management."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List

import chromadb
from langchain_core.documents import Document

from backend.config import BASE_DIR, settings
from backend.ingestion import chunk_document
from backend.retrieval import get_embedding_model

CORPUS_DIR = BASE_DIR / "data" / "evaluation_corpus"
CORPUS_VERSION_FILE = CORPUS_DIR / "VERSION"


def _evaluation_collection_name() -> str:
    if settings.EVALUATION_COLLECTION_NAME == settings.CHROMA_COLLECTION_NAME:
        raise ValueError(
            "Evaluation collection must be different from the normal user collection."
        )
    return settings.EVALUATION_COLLECTION_NAME


def corpus_documents() -> List[Path]:
    return sorted(path for path in CORPUS_DIR.glob("*.md") if path.is_file())


def corpus_status() -> Dict[str, Any]:
    collection_name = _evaluation_collection_name()
    client = chromadb.PersistentClient(path=str(settings.CHROMA_PERSIST_DIR))
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={
            "corpus_version": settings.EVALUATION_CORPUS_VERSION,
            "embedding_model": settings.EMBEDDING_MODEL,
            "purpose": "isolated_evaluation",
        },
    )
    return {
        "collection": collection_name,
        "corpus_version": settings.EVALUATION_CORPUS_VERSION,
        "document_count": len(corpus_documents()),
        "chunk_count": collection.count(),
        "embedding_model": settings.EMBEDDING_MODEL,
        "persist_path": str(settings.CHROMA_PERSIST_DIR),
    }


def prepare_corpus(reset: bool = False) -> Dict[str, Any]:
    if not corpus_documents():
        raise ValueError("No versioned evaluation corpus documents were found")
    collection_name = _evaluation_collection_name()
    client = chromadb.PersistentClient(path=str(settings.CHROMA_PERSIST_DIR))
    existing = next(
        (item for item in client.list_collections() if item.name == collection_name),
        None,
    )
    if reset and existing:
        client.delete_collection(collection_name)
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={
            "corpus_version": settings.EVALUATION_CORPUS_VERSION,
            "embedding_model": settings.EMBEDDING_MODEL,
            "purpose": "isolated_evaluation",
        },
    )
    embedding_model = get_embedding_model()
    all_chunks: List[Document] = []
    for path in corpus_documents():
        content = path.read_text(encoding="utf-8")
        doc_id = f"eval-{hashlib.sha256(path.name.encode()).hexdigest()[:12]}"
        all_chunks.extend(chunk_document(
            [{"text": content, "page_number": 1}],
            source_name=path.name,
            doc_id=doc_id,
            extra_metadata={
                "evaluation_corpus": True,
                "corpus_version": settings.EVALUATION_CORPUS_VERSION,
                "document_id": doc_id,
            },
        ))
    if all_chunks:
        ids = [chunk.metadata["chunk_id"] for chunk in all_chunks]
        try:
            embeddings = embedding_model.embed_documents(
                [chunk.page_content for chunk in all_chunks]
            )
            collection.upsert(
                ids=ids,
                documents=[chunk.page_content for chunk in all_chunks],
                metadatas=[chunk.metadata for chunk in all_chunks],
                embeddings=embeddings,
            )
        except Exception as exc:
            raise RuntimeError(
                "Evaluation corpus embedding failed; verify Gemini credentials and provider access."
            ) from exc
    status = corpus_status()
    if status["chunk_count"] == 0:
        raise RuntimeError("Evaluation corpus preparation indexed zero chunks.")
    return status


def reset_corpus() -> Dict[str, Any]:
    collection_name = _evaluation_collection_name()
    client = chromadb.PersistentClient(path=str(settings.CHROMA_PERSIST_DIR))
    if any(item.name == collection_name for item in client.list_collections()):
        client.delete_collection(collection_name)
    return corpus_status()
