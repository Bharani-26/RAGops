from typing import List, Dict, Any, Optional
from langchain_core.documents import Document
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.config import settings

STRICT_RAG_SYSTEM_PROMPT = """You are RAGOps Assistant, a reliable and factual question-answering assistant for RAG systems.
Your task is to answer the user's question STRICTLY and ONLY based on the retrieved context provided below.

Rules:
1. Ground every statement in the provided context.
2. If the context does not contain enough information to answer the question, clearly state: "The retrieved context does not contain sufficient information to answer this question."
3. Do NOT assume, extrapolate, or fabricate details or citations outside the provided text.
4. Keep the answer clear, objective, and concise.
"""


def get_llm(model_name: Optional[str] = None, temperature: Optional[float] = None) -> ChatGoogleGenerativeAI:
    """Initialize Gemini LLM instance."""
    if not settings.GOOGLE_API_KEY or "your_gemini" in settings.GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY is not configured. Please set a valid key in .env.")
    
    return ChatGoogleGenerativeAI(
        model=model_name or settings.LLM_MODEL,
        temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
        google_api_key=settings.GOOGLE_API_KEY,
    )


def format_context(documents: List[Document]) -> str:
    """Format retrieved document chunks into clean text blocks for the prompt."""
    if not documents:
        return "No relevant context found."
    
    formatted_chunks = []
    for i, doc in enumerate(documents, start=1):
        source = doc.metadata.get("source", "Unknown")
        chunk_idx = doc.metadata.get("chunk_index", "N/A")
        formatted_chunks.append(
            f"--- Context Chunk {i} [Source: {source}, Chunk: {chunk_idx}] ---\n{doc.page_content}"
        )
    return "\n\n".join(formatted_chunks)


def extract_content_text(content: Any) -> str:
    """Safely extract plain text from LangChain message content (handles string or structured block lists)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                text_parts.append(part["text"])
            elif isinstance(part, str):
                text_parts.append(part)
        return "\n".join(text_parts).strip()
    return str(content).strip()


def generate_answer(
    query: str,
    retrieved_documents: List[Document],
    llm: Optional[ChatGoogleGenerativeAI] = None,
) -> Dict[str, Any]:
    """Generate grounded answer from retrieved context with strict grounding rules."""
    context_str = format_context(retrieved_documents)
    
    prompt_user_message = (
        f"Context:\n{context_str}\n\n"
        f"Question: {query}\n\n"
        f"Answer:"
    )
    
    model = llm or get_llm()
    messages = [
        SystemMessage(content=STRICT_RAG_SYSTEM_PROMPT),
        HumanMessage(content=prompt_user_message)
    ]
    
    response = model.invoke(messages)
    answer_text = extract_content_text(response.content)
    usage_metadata = getattr(response, "usage_metadata", None) or {}
    prompt_tokens = usage_metadata.get("input_tokens")
    completion_tokens = usage_metadata.get("output_tokens")
    
    # Compile sources and reference metadata
    sources = []
    for doc in retrieved_documents:
        sources.append({
            "source": doc.metadata.get("source", "Unknown"),
            "chunk_index": doc.metadata.get("chunk_index", 0),
            "total_chunks": doc.metadata.get("total_chunks", 1),
            "page_number": doc.metadata.get("page_number"),
            "chunk_id": doc.metadata.get("chunk_id"),
            "citation": (
                f"{doc.metadata.get('source', 'Unknown')}"
                f" (page {doc.metadata.get('page_number')})"
                if doc.metadata.get("page_number") is not None
                else doc.metadata.get("source", "Unknown")
            ),
            "content_preview": doc.page_content[:150] + ("..." if len(doc.page_content) > 150 else ""),
            "metadata": doc.metadata,
        })
    
    return {
        "answer": answer_text,
        "sources": sources,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }
