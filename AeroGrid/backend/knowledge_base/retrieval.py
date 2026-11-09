"""AeroGrid Policy Retrieval Module.

Provides regulatory, telecommunications, and fleet operational knowledge
retrieval for UTM agents. Acts as a mock interface for future Vector DB / RAG integration.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from backend.knowledge_base.vector_store import VectorStore

logger = logging.getLogger("aerogrid.retrieval")


class PolicyRetriever:
    """RAG Policy Retrieval Engine for UTM regulatory knowledge bases.

    Hybrid retriever that queries the persisted ChromaDB (from Phase 3 ingestion)
    when present, with seamless fallback to the local embedded VectorStore.
    """

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        chroma_persist_dir: Optional[str] = None,
        collection_name: str = "uae_aviation_telecom_policies",
    ) -> None:
        """Initialize the policy retriever."""
        self.vector_store = vector_store or VectorStore()
        self.chroma_store: Optional[Any] = None

        # Attempt to connect to persisted ChromaDB if available
        chroma_dir = chroma_persist_dir or str(
            Path(__file__).resolve().parent / "vector_db"
        )
        if Path(chroma_dir).exists():
            try:
                self._init_chroma(chroma_dir, collection_name)
            except Exception as e:
                logger.debug("ChromaDB not active (%s). Using local VectorStore.", e)

        logger.info(
            "PolicyRetriever initialized (ChromaDB: %s, Local Chunks: %d).",
            "Active" if self.chroma_store else "Standby (Local VectorStore)",
            len(self.vector_store.chunks),
        )

    def _init_chroma(self, persist_dir: str, collection_name: str) -> None:
        """Attempt to bind Chroma vector database."""
        import os
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError:
            try:
                from langchain_community.embeddings import HuggingFaceEmbeddings
            except ImportError:
                return

        try:
            from langchain_chroma import Chroma
        except ImportError:
            try:
                from langchain_community.vectorstores import Chroma
            except ImportError:
                return

        embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self.chroma_store = Chroma(
            persist_directory=persist_dir,
            collection_name=collection_name,
            embedding_function=embeddings,
        )
        logger.info("Bound to ChromaDB at %s (collection: %s)", persist_dir, collection_name)

    def query_policy(self, domain: str, query: str, top_k: int = 2) -> List[Dict[str, str]]:
        """Query the regulatory knowledge base for relevant policy excerpts.

        Args:
            domain: Domain identifier ('aviation', 'telecom', 'fleet', 'coordination', or 'all').
            query: Natural language or telemetry keyword query.
            top_k: Maximum number of citations to return.

        Returns:
            A list of dictionary citations with 'source', 'excerpt', and 'clause_id' keys.
        """
        # If Chroma is active, query it first
        if self.chroma_store is not None:
            try:
                docs = self.chroma_store.similarity_search(query, k=top_k)
                if docs:
                    return [
                        {
                            "clause_id": d.metadata.get("clause_id", "UAE-POLICY"),
                            "source": d.metadata.get("filename", d.metadata.get("source", "UAE Law")),
                            "excerpt": d.page_content.strip(),
                        }
                        for d in docs
                    ]
            except Exception as exc:
                logger.warning("Chroma similarity search failed (%s). Falling back to local index.", exc)

        # Local VectorStore retrieval
        results = self.vector_store.search(domain=domain, query=query, top_k=top_k)

        citations: List[Dict[str, str]] = [
            {
                "clause_id": item.get("clause_id", "POLICY-REF"),
                "source": item["source"],
                "excerpt": item["excerpt"],
            }
            for item in results
        ]

        logger.debug(
            "PolicyRetriever returned %d citations for domain='%s' query='%s'",
            len(citations),
            domain,
            query[:40],
        )
        return citations

