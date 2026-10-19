import io
import uuid
import re
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
import pypdf
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.config import settings

ALLOWED_EXTENSIONS = {".txt", ".pdf"}
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB max


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename and prepend a short unique token to prevent collision,
    path traversal, and executable execution.
    """
    safe_name = Path(filename).name
    # Keep only alphanumeric, dash, underscore, and dot
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", safe_name)
    cleaned = cleaned.lstrip(".")
    if not cleaned:
        cleaned = "document.txt"
    return cleaned


def generate_unique_server_filename(original_filename: str) -> str:
    """Generate safe, collision-resistant server filename."""
    clean = sanitize_filename(original_filename)
    unique_prefix = uuid.uuid4().hex[:8]
    return f"{unique_prefix}_{clean}"


def validate_file(filename: str, content: bytes) -> str:
    """Validate file extension and size constraints."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file format '{ext}'. Only .txt and .pdf files are supported.")
    if not content or len(content.strip()) == 0:
        raise ValueError("Uploaded file is empty (0 bytes).")
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"Uploaded file exceeds maximum allowed size ({MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB).")
    return ext


def content_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extract_pages_and_text(filename: str, content: bytes) -> List[Dict[str, Any]]:
    """
    Extract text along with page number metadata.
    Returns list of dicts: [{"text": "...", "page_number": int}]
    """
    ext = validate_file(filename, content)
    if ext == ".txt":
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                decoded = content.decode("latin-1")
            except Exception as e:
                raise ValueError(f"Failed to decode text file: {e}")
        return [{"text": decoded, "page_number": 1}]

    elif ext == ".pdf":
        try:
            reader = pypdf.PdfReader(io.BytesIO(content))
            pages = []
            for i, page in enumerate(reader.pages, start=1):
                page_str = page.extract_text() or ""
                if page_str.strip():
                    pages.append({"text": page_str, "page_number": i})
            
            if not pages:
                raise ValueError("No extractable text found in the PDF.")
            return pages
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Failed to parse PDF document: {e}")
    else:
        raise ValueError(f"Unsupported extension: {ext}")


def chunk_document(
    pages: List[Dict[str, Any]],
    source_name: str,
    doc_id: str,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> List[Document]:
    """
    Split text into chunks with rich metadata: doc_id, chunk_id, page_number,
    source, total_chunks, and character length.
    """
    size = chunk_size if chunk_size is not None else settings.DEFAULT_CHUNK_SIZE
    overlap = chunk_overlap if chunk_overlap is not None else settings.DEFAULT_CHUNK_OVERLAP

    if size <= 0:
        raise ValueError("chunk_size must be greater than 0.")
    if overlap < 0 or overlap >= size:
        raise ValueError("chunk_overlap must be non-negative and strictly less than chunk_size.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", " ", ""],
    )

    all_chunks: List[Document] = []
    base_meta = extra_metadata or {}
    
    # Track overall chunk index across pages
    global_chunk_idx = 0
    # First pass: collect all chunks to compute total count
    intermediate: List[tuple[str, int]] = []
    for page in pages:
        page_chunks = splitter.split_text(page["text"])
        for chunk in page_chunks:
            intermediate.append((chunk, page["page_number"]))

    total_chunks = len(intermediate)
    for idx, (chunk_text, page_num) in enumerate(intermediate):
        chunk_id = f"{doc_id}_c{idx}"
        metadata = {
            **base_meta,
            "doc_id": doc_id,
            "chunk_id": chunk_id,
            "source": source_name,
            "page_number": page_num,
            "chunk_index": idx,
            "total_chunks": total_chunks,
            "chunk_char_length": len(chunk_text),
        }
        all_chunks.append(Document(page_content=chunk_text, metadata=metadata))

    return all_chunks
