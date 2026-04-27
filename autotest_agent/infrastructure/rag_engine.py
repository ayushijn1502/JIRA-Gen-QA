"""
RAG Engine -- indexes Python files into a FAISS vector store so the
agents can ask "show me code that does X" and get relevant snippets back.

How it works (in plain English):
1. Walk a directory and read every .py file.
2. Chop each file into overlapping chunks (so we don't cut a function in half).
3. Turn each chunk into a numeric "embedding" using a sentence-transformer model.
4. Store those embeddings in a FAISS index (fast nearest-neighbour search).
5. At query time, embed the question the same way and find the closest chunks.

Usage:
    engine = RAGEngine(embedding_model="all-MiniLM-L6-v2", chunk_size=1500)
    engine.index_codebase("./target_framework")
    results = engine.query("How do we mock HTTP calls in tests?", top_k=3)
"""

from __future__ import annotations

from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from autotest_agent.domain.ports import RAGPort


class RAGEngine(RAGPort):
    """
    Concrete implementation of RAGPort.
    Uses HuggingFace sentence-transformers for embeddings and FAISS
    for the vector store.  Everything runs locally -- no API calls
    needed for the embedding step.
    """

    def __init__(
        self,
        embedding_model: str = "all-MiniLM-L6-v2",
        chunk_size: int = 1500,
        chunk_overlap: int = 200,
        top_k: int = 5,
    ) -> None:
        self._embeddings = HuggingFaceEmbeddings(model_name=embedding_model)
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\nclass ", "\ndef ", "\n\n", "\n", " "],
        )
        self._top_k = top_k
        self._store: FAISS | None = None

    def index_codebase(self, path: str) -> None:
        """
        Read every .py file under `path`, split into chunks, embed them,
        and build a FAISS index.  Call this once at startup or whenever
        the codebase changes.
        """
        documents = self._load_python_files(path)
        if not documents:
            return
        chunks = self._splitter.create_documents(
            texts=[doc["content"] for doc in documents],
            metadatas=[{"source": doc["source"]} for doc in documents],
        )
        self._store = FAISS.from_documents(chunks, self._embeddings)

    def query(self, question: str, top_k: int | None = None) -> list[str]:
        """
        Find the most relevant code chunks for a natural-language question.
        Returns a list of code strings, most relevant first.
        """
        if self._store is None:
            return []
        k = top_k or self._top_k
        results = self._store.similarity_search(question, k=k)
        return [doc.page_content for doc in results]

    @staticmethod
    def _load_python_files(path: str) -> list[dict[str, str]]:
        """
        Walk a directory tree and return a list of dicts
        with 'source' (file path) and 'content' (file text)
        for every .py file found.
        """
        root = Path(path)
        if not root.exists():
            return []
        documents: list[dict[str, str]] = []
        for py_file in sorted(root.rglob("*.py")):
            if "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if content.strip():
                documents.append({"source": str(py_file), "content": content})
        return documents
