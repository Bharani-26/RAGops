import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "RAGOps"
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    
    # Models
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "models/gemini-embedding-001")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-3.8-flash")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.0"))
    INPUT_PRICE_PER_MILLION_TOKENS: Optional[float] = (
        float(os.getenv("INPUT_PRICE_PER_MILLION_TOKENS"))
        if os.getenv("INPUT_PRICE_PER_MILLION_TOKENS")
        else None
    )
    OUTPUT_PRICE_PER_MILLION_TOKENS: Optional[float] = (
        float(os.getenv("OUTPUT_PRICE_PER_MILLION_TOKENS"))
        if os.getenv("OUTPUT_PRICE_PER_MILLION_TOKENS")
        else None
    )
    
    # Persistent Local Storage Paths
    DATA_DIR: Path = Path(os.getenv("RAGOPS_DATA_DIR", str(BASE_DIR / "data")))
    UPLOAD_DIR: Path = Path(os.getenv("RAGOPS_UPLOAD_DIR", str(DATA_DIR / "uploads")))
    CHROMA_PERSIST_DIR: Path = Path(
        os.getenv("RAGOPS_CHROMA_PERSIST_DIR", str(DATA_DIR / "chroma"))
    )
    SQLITE_DB_PATH: Path = Path(
        os.getenv("RAGOPS_SQLITE_DB_PATH", str(DATA_DIR / "ragops.db"))
    )
    CHROMA_COLLECTION_NAME: str = "ragops_documents"
    
    # Chunking configurations
    DEFAULT_CHUNK_SIZE: int = int(os.getenv("DEFAULT_CHUNK_SIZE", "500"))
    DEFAULT_CHUNK_OVERLAP: int = int(os.getenv("DEFAULT_CHUNK_OVERLAP", "50"))
    
    # Retrieval
    DEFAULT_TOP_K: int = int(os.getenv("DEFAULT_TOP_K", "4"))


settings = Settings()

# Ensure persistent directories exist
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
