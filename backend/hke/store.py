"""Chroma vector DB storage for the Historical Knowledge Engine.

Embedding model: nomic-embed-text via Ollama (local, free).
Falls back to Chroma's default (all-MiniLM-L6-v2) if Ollama is unreachable.

Supports hierarchical chunking (parent/child for Gutenberg) and
section-based chunking (for Wikipedia).
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import chromadb

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "chroma"

logger = logging.getLogger("chronos.hke.store")

_client: Optional[chromadb.ClientAPI] = None
_embedding_fn = None


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        DB_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(DB_PATH))
    return _client


def _get_embedding_function():
    """Get nomic-embed-text via Ollama, falling back to default if unavailable."""
    global _embedding_fn
    if _embedding_fn is not None:
        return _embedding_fn

    try:
        from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
        fn = OllamaEmbeddingFunction(
            url="http://localhost:11434/api/embeddings",
            model_name="nomic-embed-text",
        )
        # Probe with a test embed to confirm Ollama is reachable
        fn(["test"])
        _embedding_fn = fn
        logger.info("Using nomic-embed-text via Ollama for embeddings")
        return _embedding_fn
    except Exception as exc:
        logger.warning(
            "Ollama nomic-embed-text unavailable (%s), falling back to default embedder",
            exc,
        )
        _embedding_fn = None
        return None


def get_or_create_collection(era_key: str) -> chromadb.Collection:
    client = _get_client()
    ef = _get_embedding_function()
    kwargs = {"name": f"era_{era_key}", "metadata": {"hnsw:space": "cosine"}}
    if ef is not None:
        kwargs["embedding_function"] = ef
    return client.get_or_create_collection(**kwargs)


def delete_collection(era_key: str) -> None:
    """Delete a collection for re-indexing."""
    try:
        client = _get_client()
        client.delete_collection(f"era_{era_key}")
    except Exception:
        pass


def add_chunks(
    collection: chromadb.Collection,
    texts: List[str],
    metadatas: List[dict],
    ids: Optional[List[str]] = None,
) -> None:
    """Add text chunks to a Chroma collection in batches.

    If `ids` is provided, use those; otherwise generate random IDs.
    """
    if ids is None:
        ids = [uuid.uuid4().hex[:16] for _ in texts]
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i : i + batch_size]
        batch_meta = metadatas[i : i + batch_size]
        batch_ids = ids[i : i + batch_size]
        collection.add(
            documents=batch_texts,
            metadatas=batch_meta,
            ids=batch_ids,
        )


def query_collection(
    era_key: str,
    query_text: str,
    n_results: int = 5,
) -> List[str]:
    """Retrieve the top-k most relevant chunks for a query.

    For hierarchical Gutenberg chunks, retrieves child chunks first,
    then returns their parent context for richer LLM input.
    """
    try:
        client = _get_client()
        ef = _get_embedding_function()
        kwargs = {"name": f"era_{era_key}"}
        if ef is not None:
            kwargs["embedding_function"] = ef
        collection = client.get_collection(**kwargs)
        results = collection.query(
            query_texts=[query_text],
            n_results=n_results,
            include=["documents", "metadatas"],
        )
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        parent_ids_needed: List[str] = []
        direct_texts: List[str] = []

        for doc, meta in zip(docs, metas):
            chunk_type = meta.get("chunk_type", "")
            if chunk_type == "child":
                pid = meta.get("parent_id")
                if pid:
                    parent_ids_needed.append(pid)
                else:
                    direct_texts.append(doc)
            else:
                direct_texts.append(doc)

        if parent_ids_needed:
            unique_pids = list(dict.fromkeys(parent_ids_needed))
            try:
                parent_results = collection.get(
                    ids=unique_pids,
                    include=["documents"],
                )
                parent_docs = parent_results.get("documents", [])
                direct_texts.extend(parent_docs)
            except Exception:
                pass

        return direct_texts
    except Exception:
        return []


def query_collection_with_metadata(
    era_key: str,
    query_text: str,
    n_results: int = 5,
) -> List[Dict]:
    """Like query_collection but returns dicts with text + metadata."""
    try:
        client = _get_client()
        ef = _get_embedding_function()
        kwargs = {"name": f"era_{era_key}"}
        if ef is not None:
            kwargs["embedding_function"] = ef
        collection = client.get_collection(**kwargs)
        results = collection.query(
            query_texts=[query_text],
            n_results=n_results,
            include=["documents", "metadatas"],
        )
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        return [
            {"text": doc, "metadata": meta}
            for doc, meta in zip(docs, metas)
        ]
    except Exception:
        return []
