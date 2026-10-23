# RAGOps Platform Manual

RAGOps is a local observability platform for retrieval-augmented generation applications. It uses persistent ChromaDB for vector storage and SQLite for request traces and evaluation records. The platform accepts TXT and PDF documents, extracts text, splits it into overlapping chunks, retrieves relevant chunks, and generates grounded answers with source citations.

The standard upload limit is 25 MB. The default chunk size is 500 characters and the default overlap is 50 characters. The default retrieval value is four chunks. Gemini supplies embeddings and grounded answer generation when a valid provider key is configured.

The readiness endpoint checks both ChromaDB and SQLite. The Document Explorer reads stored chunk text and metadata from the existing collection. Evaluation runs are stored in SQLite and can export JSON reports. Ordinary CI uses isolated temporary storage and does not call Gemini.
