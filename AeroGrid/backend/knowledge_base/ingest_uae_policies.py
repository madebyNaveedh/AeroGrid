#!/usr/bin/env python3
"""AeroGrid Knowledge Base Vectorization Script (Phase 3).

Adapted from the ITU AI Readiness Framework reference repository:
https://github.com/CrashingGuru/ITUAIReadiness

Ingests UAE aerospace, telecommunications, and aviation regulatory PDFs,
chunks policy text using RecursiveCharacterTextSplitter, computes semantic
embeddings with sentence-transformers/all-MiniLM-L6-v2, and persists
the vector database into ChromaDB for AeroGrid UTM multi-agent retrieval.
"""

from __future__ import annotations

import argparse
import glob
import logging
import os
import sys
from pathlib import Path
from typing import Any, List, Optional

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("aerogrid.kb_ingestion")


# ------------------------------------------------------------------------------
# Dependency Verification and Adaptive Imports (LangChain & ChromaDB)
# ------------------------------------------------------------------------------
def check_dependencies() -> bool:
    """Verify presence of required LangChain and ChromaDB libraries."""
    missing = []
    for mod, pkg in [
        ("langchain", "langchain"),
        ("chromadb", "chromadb"),
        ("sentence_transformers", "sentence-transformers"),
        ("pypdf", "pypdf"),
    ]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)

    if missing:
        logger.error(
            "Missing required dependencies for Knowledge Base vectorization:\n"
            "  %s\n\n"
            "Install them via pip:\n"
            "  pip install langchain langchain-community langchain-text-splitters "
            "langchain-chroma langchain-huggingface chromadb sentence-transformers pypdf",
            ", ".join(missing),
        )
        return False
    return True


def get_langchain_components():
    """Dynamically import LangChain loaders, splitters, embeddings, and Chroma."""
    # 1. Text Splitter
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError:
        from langchain.text_splitter import RecursiveCharacterTextSplitter  # type: ignore

    # 2. Document Loaders
    try:
        from langchain_community.document_loaders import PyPDFDirectoryLoader, PyPDFLoader
    except ImportError:
        from langchain.document_loaders import PyPDFDirectoryLoader, PyPDFLoader  # type: ignore

    # 3. Embeddings
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
    except ImportError:
        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings
        except ImportError:
            from langchain.embeddings import HuggingFaceEmbeddings  # type: ignore

    # 4. Chroma Vector Store
    try:
        from langchain_chroma import Chroma
    except ImportError:
        try:
            from langchain_community.vectorstores import Chroma
        except ImportError:
            from langchain.vectorstores import Chroma  # type: ignore

    return {
        "RecursiveCharacterTextSplitter": RecursiveCharacterTextSplitter,
        "PyPDFDirectoryLoader": PyPDFDirectoryLoader,
        "PyPDFLoader": PyPDFLoader,
        "HuggingFaceEmbeddings": HuggingFaceEmbeddings,
        "Chroma": Chroma,
    }


# ------------------------------------------------------------------------------
# Core Ingestion Pipeline
# ------------------------------------------------------------------------------
class UAEPoliciesIngestor:
    """Data Engineering pipeline for ingesting and vectorizing UAE policies."""

    def __init__(
        self,
        pdf_dir: str = "data/uae_policies",
        persist_dir: str = "../AeroGrid/backend/knowledge_base/vector_db",
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        model_name: str = "all-MiniLM-L6-v2",
        collection_name: str = "uae_aviation_telecom_policies",
    ) -> None:
        self.pdf_dir = Path(pdf_dir).resolve()
        self.persist_dir = Path(persist_dir).resolve()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.model_name = model_name
        self.collection_name = collection_name

    def validate_environment(self) -> List[Path]:
        """Validate that target PDF directory exists and contains valid PDF files.

        Returns:
            List of validated PDF Path objects.

        Raises:
            FileNotFoundError: If pdf_dir does not exist or has no PDF files.
        """
        logger.info("Verifying source directory: %s", self.pdf_dir)

        if not self.pdf_dir.exists():
            self.pdf_dir.mkdir(parents=True, exist_ok=True)
            raise FileNotFoundError(
                f"[ERROR] Source PDF directory '{self.pdf_dir}' did not exist. "
                "Directory created. Please place UAE regulatory PDFs (e.g. GCAA CAR Part IV, "
                "UAE Federal Decree-Law No. 26, TDRA Spectrum Guidelines) here and re-run."
            )

        # Scan for PDF files
        pdf_files = sorted(list(self.pdf_dir.glob("*.pdf")) + list(self.pdf_dir.glob("*.PDF")))

        if not pdf_files:
            raise FileNotFoundError(
                f"[ERROR] No PDF files found in directory: '{self.pdf_dir}'.\n"
                "Please add UAE regulatory documents to this directory before running ingestion.\n"
                "Expected files include:\n"
                "  - UAE_Federal_Decree_Law_No_26_Civil_Aviation.pdf\n"
                "  - GCAA_CAR_Part_IV_UAS_Operations_BVLOS.pdf\n"
                "  - TDRA_UAE_Spectrum_Guidelines_UAS_C2_Link.pdf"
            )

        logger.info("Found %d regulatory PDF file(s) for processing:", len(pdf_files))
        for idx, f in enumerate(pdf_files, 1):
            size_kb = f.stat().st_size / 1024.0
            logger.info("  [%d] %s (%.1f KB)", idx, f.name, size_kb)

        return pdf_files

    def load_documents(self, pdf_files: List[Path], loader_cls: Any) -> List[Any]:
        """Load and extract text pages from PDFs with per-file error handling."""
        logger.info("Loading document pages from %d PDF file(s)...", len(pdf_files))
        all_docs = []
        failed_files = []

        for pdf_path in pdf_files:
            try:
                loader = loader_cls(str(pdf_path))
                docs = loader.load()
                for doc in docs:
                    # Enrich metadata
                    doc.metadata["filename"] = pdf_path.name
                    doc.metadata["jurisdiction"] = "UAE"
                    # Tag domain based on filename heuristics
                    fn_lower = pdf_path.name.lower()
                    if "gcaa" in fn_lower or "aviation" in fn_lower or "decree" in fn_lower:
                        doc.metadata["domain"] = "aviation"
                    elif "tdra" in fn_lower or "spectrum" in fn_lower or "c2" in fn_lower:
                        doc.metadata["domain"] = "telecom"
                    else:
                        doc.metadata["domain"] = "general"

                all_docs.extend(docs)
                logger.info("  + Successfully loaded %d page(s) from '%s'", len(docs), pdf_path.name)
            except Exception as exc:
                logger.warning("  - [WARNING] Failed to parse PDF '%s': %s", pdf_path.name, exc)
                failed_files.append((pdf_path.name, str(exc)))

        if not all_docs:
            raise RuntimeError(
                f"Failed to extract text from any PDF files in '{self.pdf_dir}'. "
                f"Errors: {failed_files}"
            )

        logger.info("Total document pages loaded: %d", len(all_docs))
        return all_docs

    def chunk_documents(self, raw_docs: List[Any], splitter_cls: Any) -> List[Any]:
        """Chunk text pages using RecursiveCharacterTextSplitter."""
        logger.info(
            "Chunking text with RecursiveCharacterTextSplitter (chunk_size=%d, chunk_overlap=%d)...",
            self.chunk_size,
            self.chunk_overlap,
        )

        text_splitter = splitter_cls(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
            is_separator_regex=False,
        )

        chunks = text_splitter.split_documents(raw_docs)
        logger.info("Generated %d policy chunks from %d page(s).", len(chunks), len(raw_docs))

        if chunks:
            sample = chunks[0]
            logger.debug(
                "Sample chunk metadata: %s | Length: %d chars",
                sample.metadata,
                len(sample.page_content),
            )

        return chunks

    def build_and_persist_vector_db(
        self,
        chunks: List[Any],
        embeddings_cls: Any,
        chroma_cls: Any,
    ) -> Any:
        """Embed text chunks and persist them into Chroma vector database."""
        logger.info(
            "Initializing sentence-transformer embeddings model: '%s'...",
            self.model_name,
        )
        embeddings = embeddings_cls(
            model_name=self.model_name,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

        # Ensure persist directory exists
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Persisting Chroma vector DB to target directory: %s", self.persist_dir)

        # Initialize and populate Chroma vector store
        vector_store = chroma_cls.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=str(self.persist_dir),
            collection_name=self.collection_name,
        )

        # In modern Chroma (>= 0.4.0), persistence is automatic; call persist() if supported
        if hasattr(vector_store, "persist"):
            try:
                vector_store.persist()
            except Exception:
                pass

        logger.info(
            "[SUCCESS] Chroma vector DB successfully built and persisted at: %s",
            self.persist_dir,
        )
        return vector_store

    def verify_retrieval(self, vector_store: Any) -> None:
        """Run verification semantic queries to confirm retriever functionality."""
        logger.info("=" * 70)
        logger.info("  KNOWLEDGE BASE RETRIEVAL VERIFICATION")
        logger.info("=" * 70)

        test_queries = [
            ("aviation", "manned aircraft HEMS right of way emergency separation"),
            ("aviation", "tactical separation minima BVLOS corridor 500 feet"),
            ("telecom", "C2 link latency 100ms packet loss failsafe"),
        ]

        for domain, query in test_queries:
            logger.info("Verification Query [%s]: '%s'", domain, query)
            results = vector_store.similarity_search_with_score(query, k=2)
            for rank, (doc, score) in enumerate(results, 1):
                source = doc.metadata.get("filename", "Unknown")
                page = doc.metadata.get("page", 0)
                excerpt = doc.page_content.strip().replace("\n", " ")[:140]
                logger.info(
                    "  -> Rank #%d (distance: %.4f) [%s, p.%s]: \"%s...\"",
                    rank,
                    score,
                    source,
                    page,
                    excerpt,
                )
            logger.info("-" * 70)


# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="AeroGrid UAE Regulatory PDF Knowledge Base Ingestion Script"
    )
    parser.add_argument(
        "--pdf-dir",
        type=str,
        default="data/uae_policies",
        help="Directory containing source UAE regulatory PDFs (default: data/uae_policies)",
    )
    parser.add_argument(
        "--persist-dir",
        type=str,
        default="../AeroGrid/backend/knowledge_base/vector_db",
        help="Target persistence directory for Chroma vector store "
             "(default: ../AeroGrid/backend/knowledge_base/vector_db)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Text chunk size in characters (default: 1000)",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=200,
        help="Overlap between adjacent chunks in characters (default: 200)",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default="all-MiniLM-L6-v2",
        help="HuggingFace / sentence-transformers embedding model (default: all-MiniLM-L6-v2)",
    )
    parser.add_argument(
        "--collection-name",
        type=str,
        default="uae_aviation_telecom_policies",
        help="Chroma collection name (default: uae_aviation_telecom_policies)",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip test retrieval verification query",
    )

    args = parser.parse_args()

    # 1. Dependency Check
    if not check_dependencies():
        return 1

    components = get_langchain_components()

    # 2. Pipeline Execution
    ingestor = UAEPoliciesIngestor(
        pdf_dir=args.pdf_dir,
        persist_dir=args.persist_dir,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        model_name=args.model_name,
        collection_name=args.collection_name,
    )

    try:
        # Step A: Validate PDFs
        pdf_files = ingestor.validate_environment()

        # Step B: Load Pages
        raw_docs = ingestor.load_documents(pdf_files, components["PyPDFLoader"])

        # Step C: Chunk Text
        chunks = ingestor.chunk_documents(raw_docs, components["RecursiveCharacterTextSplitter"])

        # Step D: Embed and Store in Chroma
        vector_store = ingestor.build_and_persist_vector_db(
            chunks,
            components["HuggingFaceEmbeddings"],
            components["Chroma"],
        )

        # Step E: Verify Retrieval
        if not args.skip_verify:
            ingestor.verify_retrieval(vector_store)

        logger.info(
            "[ALL DONE] Knowledge Base vectorization complete. "
            "AeroGrid agents can now query %s",
            ingestor.persist_dir,
        )
        return 0

    except FileNotFoundError as fnf_err:
        logger.error(str(fnf_err))
        return 2
    except Exception as exc:
        logger.exception("Unexpected error during knowledge base ingestion: %s", exc)
        return 3


if __name__ == "__main__":
    sys.exit(main())
