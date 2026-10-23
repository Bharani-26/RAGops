# RAGOps Security Policy

RAGOps is intended for local, single-user development. It has no authentication, authorization, or tenant isolation. A deployment that is reachable by multiple users must add identity checks and a per-user document namespace before it is considered safe.

Uploaded filenames are sanitized, uploads are limited to TXT and PDF files, and files are capped at 25 MB. API keys are read from environment configuration and are not returned by the settings endpoint. Local runtime data, uploads, ChromaDB files, and SQLite databases are excluded from version control.

The evaluation corpus uses a dedicated ChromaDB collection named by configuration. Reset commands are restricted to that evaluation collection and never delete ordinary user documents.
