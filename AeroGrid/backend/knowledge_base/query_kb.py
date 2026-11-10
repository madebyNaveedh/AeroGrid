#!/usr/bin/env python3
"""AeroGrid Knowledge Base Query CLI & Verification Utility.

Allows hackathon evaluators and domain agents to perform semantic similarity
queries against the persisted ChromaDB vector database of UAE civil aviation,
TDRA telecom regulations, and ITU-T standards.

Adapted from the ITU AI Readiness Framework reference repository:
https://github.com/CrashingGuru/ITUAIReadiness
"""

import argparse
import os
import sys
from pathlib import Path

# Add py_packages to path
curr = Path(__file__).resolve()
candidates = [
    curr.parent / "py_packages",
    curr.parent.parent / "py_packages",
    curr.parent.parent.parent / "py_packages",
    curr.parent.parent.parent.parent / "py_packages",
    Path("/home/mohammed/AIforGood/py_packages"),
]
for pkg in candidates:
    if pkg.exists():
        sys.path.insert(0, str(pkg))
        break

for parent in [curr.parent, curr.parent.parent, curr.parent.parent.parent, curr.parent.parent.parent.parent]:
    if (parent / "AeroGrid").exists():
        REPO_ROOT = parent
        break
else:
    REPO_ROOT = curr.parent

sys.path.insert(0, str(REPO_ROOT))

# Ensure offline huggingface cache usage
os.environ["HF_HUB_OFFLINE"] = "1"


def query_kb(query_text: str, top_k: int = 3, collection_name: str = "uae_aviation_telecom_policies"):
    persist_dir = REPO_ROOT / "AeroGrid" / "backend" / "knowledge_base" / "vector_db"
    if not persist_dir.exists():
        persist_dir = REPO_ROOT / "backend" / "knowledge_base" / "vector_db"
    if not persist_dir.exists():
        persist_dir = curr.parent / "vector_db"

    try:
        from langchain_chroma import Chroma
        from langchain_huggingface import HuggingFaceEmbeddings
    except ImportError:
        try:
            from langchain_community.vectorstores import Chroma
            from langchain_community.embeddings import HuggingFaceEmbeddings
        except ImportError as e:
            print(f"[ERROR] Required dependencies not installed: {e}")
            sys.exit(1)

    print(f"\n" + "=" * 75)
    print(f"  AEROGRID KNOWLEDGE BASE (ITU-T Y.3172 / UAE REGULATORY POLICIES)")
    print(f"=" * 75)
    print(f" Query Text : '{query_text}'")
    print(f" Vector DB  : {persist_dir}")
    print(f" Top-K Hits : {top_k}")
    print("-" * 75)

    emb = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    db = Chroma(
        persist_directory=str(persist_dir),
        embedding_function=emb,
        collection_name=collection_name,
    )

    results = db.similarity_search_with_relevance_scores(query_text, k=top_k)

    if not results:
        print(" [!] No matching regulatory articles found.")
        return []

    for rank, (doc, score) in enumerate(results, 1):
        fn = doc.metadata.get("filename", Path(doc.metadata.get("source", "Unknown")).name)
        domain = doc.metadata.get("domain", "General")
        print(f"\n[Hit #{rank}] Relevance Score: {score:.4f} | File: {fn}")
        print(f"Domain: {domain}")
        print("-" * 50)
        print(doc.page_content.strip())
        print("." * 75)

    return results


def main():
    parser = argparse.ArgumentParser(description="Query AeroGrid Vector Knowledge Base")
    parser.add_argument("query", type=str, nargs="?", default="HEMS emergency right of way separation",
                        help="Semantic query text (default: 'HEMS emergency right of way separation')")
    parser.add_argument("--top-k", "-k", type=int, default=3, help="Number of retrieved results (default: 3)")
    args = parser.parse_args()

    query_kb(args.query, top_k=args.top_k)


if __name__ == "__main__":
    main()
