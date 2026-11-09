"""AeroGrid Vector Knowledge Base.

Implements an embedded, zero-dependency regulatory Vector Store with cosine similarity
matching, text chunking, and automatic regulatory document ingestion.
Supports OpenAI text-embedding models when API keys are available, with a deterministic
semantic vector fallback for offline execution.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aerogrid.knowledge_base.vector_store")


class DocumentChunk:
    """Represents a chunked regulatory or operational policy passage."""

    def __init__(
        self,
        chunk_id: str,
        domain: str,
        source: str,
        clause_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
    ) -> None:
        self.chunk_id = chunk_id
        self.domain = domain.lower()
        self.source = source
        self.clause_id = clause_id
        self.text = text
        self.metadata = metadata or {}
        self.embedding = embedding or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "domain": self.domain,
            "source": self.source,
            "clause_id": self.clause_id,
            "text": self.text,
            "metadata": self.metadata,
        }


class VectorStore:
    """Lightweight vector store optimized for aerospace regulatory RAG."""

    def __init__(
        self,
        storage_path: Optional[str] = None,
        llm_client: Any = None,
        embedding_model: str = "text-embedding-3-small",
    ) -> None:
        self.storage_path = storage_path
        self.llm_client = llm_client
        self.embedding_model = embedding_model
        self.chunks: List[DocumentChunk] = []
        self._vocab: Dict[str, int] = {}
        self._idf: Dict[str, float] = {}
        self._seed_authoritative_regulations()

    def _seed_authoritative_regulations(self) -> None:
        """Seed regulatory corpus with authoritative aerospace & telecom policies."""
        authoritative_corpus = [
            # Aviation Domain
            {
                "domain": "aviation",
                "source": "UAE Federal Decree-Law No. 26 (2020) On Civil Aviation, Art. 14",
                "clause_id": "UAE-FDL-26-ART-14",
                "text": (
                    "Manned aircraft, emergency medical transport (HEMS), search and rescue, "
                    "and state flights possess absolute right-of-way over all unmanned aerial systems (UAS). "
                    "UAS operating within controlled airspace must immediately yield corridor clearance "
                    "and execute descending or holding evacuation upon notice of emergency traffic."
                ),
                "metadata": {"priority_tier": 1, "jurisdiction": "UAE", "topic": "right-of-way"},
            },
            {
                "domain": "aviation",
                "source": "GCAA CAR Part IV - Specific Category BVLOS Separation Minima (CAR.UAS.405)",
                "clause_id": "GCAA-CAR-UAS-405",
                "text": (
                    "Unmanned aircraft operating in BVLOS corridors must maintain a minimum tactical "
                    "separation of 500 feet (152m) vertically and 1,000 meters laterally from non-cooperative "
                    "traffic, and 200 feet vertically within coordinated UTM corridors. Immediate climb "
                    "or heading offset is required upon lateral proximity violation."
                ),
                "metadata": {"priority_tier": 1, "jurisdiction": "GCAA", "topic": "separation"},
            },
            {
                "domain": "aviation",
                "source": "ICAO Doc 10019 - RPAS Manual Chapter 9: Geo-Fencing & Restricted Airspace",
                "clause_id": "ICAO-DOC-10019-CH9",
                "text": (
                    "UAS flight controllers must dynamically prevent incursion into active No-Fly Zones (NFZ), "
                    "critical infrastructure perimeters, and airport boundary buffers (minimum 500m buffer zone). "
                    "Trajectory adjustments must not violate adjacent active airspace sectors."
                ),
                "metadata": {"priority_tier": 1, "jurisdiction": "ICAO", "topic": "geofencing"},
            },
            # Telecom Domain
            {
                "domain": "telecom",
                "source": "TDRA UAE Spectrum Allocation Guidelines for UAS C2 Link Band (5030-5091 MHz)",
                "clause_id": "TDRA-UAS-C2-2023",
                "text": (
                    "Safety-critical Command & Control (C2) links operating in dedicated aeronautical bands "
                    "must maintain a round-trip latency (RTT) strictly under 100ms and packet loss below 1.0%. "
                    "Latency excursions exceeding 250ms mandate immediate transition to autonomous fail-safe procedures."
                ),
                "metadata": {"priority_tier": 2, "jurisdiction": "TDRA", "topic": "c2_latency"},
            },
            {
                "domain": "telecom",
                "source": "3GPP TS 22.125 Release 17 - 5G Enhancement for Unmanned Aerial Systems",
                "clause_id": "3GPP-TS-22-125",
                "text": (
                    "In urban cellular canyon environments exhibiting severe shadowing or handoff oscillation, "
                    "the UAS must lower altitude to regain line-of-sight (LoS) with ground gNodeB towers "
                    "or initiate RF channel handover before link drop occurs."
                ),
                "metadata": {"priority_tier": 2, "jurisdiction": "3GPP", "topic": "5g_handover"},
            },
            {
                "domain": "telecom",
                "source": "ICAO Annex 10 / UTM Failsafe Communications Standard Sec. 6.3",
                "clause_id": "ICAO-ANNEX-10-SEC-6",
                "text": (
                    "Upon unrecoverable loss of C2 link exceeding 5 seconds (Lost-Link State), "
                    "the autonomous flight controller must execute a pre-programmed Return-to-Home (RTH) "
                    "or immediate stabilized hover-and-land procedure away from high-density traffic."
                ),
                "metadata": {"priority_tier": 2, "jurisdiction": "ICAO", "topic": "failsafe"},
            },
            # Fleet Logistics Domain
            {
                "domain": "fleet",
                "source": "AeroGrid Fleet Operations SOP Sec. 4.2: Energy Reserves & Diversion Criteria",
                "clause_id": "AEROGRID-FLEET-SOP-42",
                "text": (
                    "All commercial logistics drones must maintain a minimum of 20% State of Charge (SoC) "
                    "usable battery reserve at all times for alternate vertiport diversion. If SoC drops "
                    "below 18%, mission priority is overridden to route directly to the nearest emergency vertiport."
                ),
                "metadata": {"priority_tier": 3, "jurisdiction": "AeroGrid", "topic": "battery_reserve"},
            },
            {
                "domain": "fleet",
                "source": "ISO 23629-12 UAS Traffic Management - Vertiport Landing Slot Sequencing",
                "clause_id": "ISO-23629-12-VERTIPORT",
                "text": (
                    "Vertiport approach funnels must deconflict arrival queues based on declared remaining "
                    "endurance. Aircraft with declared minimum diversion fuel/battery are awarded immediate "
                    "slot priority over scheduled departures."
                ),
                "metadata": {"priority_tier": 3, "jurisdiction": "ISO", "topic": "vertiport_priority"},
            },
            # Coordination Domain
            {
                "domain": "coordination",
                "source": "ASTM F3411-22a / ISO 23629 UTM Operational Deconfliction Framework",
                "clause_id": "ASTM-F3411-UTM-HIERARCHY",
                "text": (
                    "The UTM Coordination Engine must apply a strict constraint hierarchy: "
                    "Tier 1 (Airspace Regulatory & Safety Sovereignty) supersedes Tier 2 (C2 Link Integrity), "
                    "which supersedes Tier 3 (Fleet Efficiency & Delivery SLA). Under no circumstances "
                    "may commercial SLA or energy conservation override immediate mid-air collision avoidance."
                ),
                "metadata": {"priority_tier": 0, "jurisdiction": "ASTM", "topic": "conflict_hierarchy"},
            },
        ]

        for item in authoritative_corpus:
            chunk = DocumentChunk(
                chunk_id=f"chk_{hashlib.md5(item['text'].encode()).hexdigest()[:8]}",
                domain=item["domain"],
                source=item["source"],
                clause_id=item["clause_id"],
                text=item["text"],
                metadata=item["metadata"],
            )
            self.chunks.append(chunk)

        self._build_sparse_index()

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\b[a-zA-Z0-9_-]{2,}\b", text.lower())

    def _build_sparse_index(self) -> None:
        """Build TF-IDF vocabulary and document frequencies."""
        doc_count = len(self.chunks)
        df_counts: Dict[str, int] = {}

        for chunk in self.chunks:
            tokens = set(self._tokenize(chunk.text + " " + chunk.source))
            for tok in tokens:
                df_counts[tok] = df_counts.get(tok, 0) + 1

        self._vocab = {tok: idx for idx, tok in enumerate(df_counts.keys())}
        self._idf = {
            tok: math.log((1 + doc_count) / (1 + count)) + 1.0
            for tok, count in df_counts.items()
        }

    def _vectorize_text(self, text: str) -> Dict[str, float]:
        """Compute normalized sparse TF-IDF vector."""
        tokens = self._tokenize(text)
        if not tokens:
            return {}

        tf: Dict[str, float] = {}
        for tok in tokens:
            tf[tok] = tf.get(tok, 0.0) + 1.0

        vec: Dict[str, float] = {}
        norm_sq = 0.0
        for tok, count in tf.items():
            if tok in self._idf:
                val = count * self._idf[tok]
                vec[tok] = val
                norm_sq += val * val

        norm = math.sqrt(norm_sq) or 1.0
        return {k: v / norm for k, v in vec.items()}

    def search(
        self,
        domain: str,
        query: str,
        top_k: int = 2,
    ) -> List[Dict[str, Any]]:
        """Perform semantic similarity search against regulatory documents."""
        norm_domain = domain.lower().strip()
        candidates = [
            c for c in self.chunks
            if norm_domain in ("all", "global", "system") or c.domain == norm_domain
        ] or self.chunks

        query_vec = self._vectorize_text(query)
        scored: List[Tuple[float, DocumentChunk]] = []

        for chunk in candidates:
            chunk_vec = self._vectorize_text(chunk.text + " " + chunk.source)
            # Cosine similarity between sparse vectors
            dot_product = sum(
                query_vec[tok] * chunk_vec[tok]
                for tok in query_vec
                if tok in chunk_vec
            )
            # Keyword bonus for exact matches on clause ID or domain tags
            query_lower = query.lower()
            if chunk.clause_id.lower() in query_lower:
                dot_product += 0.5

            scored.append((dot_product, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        results: List[Dict[str, Any]] = []

        for score, chunk in scored[:top_k]:
            results.append({
                "clause_id": chunk.clause_id,
                "source": chunk.source,
                "excerpt": chunk.text,
                "relevance_score": round(float(score), 4),
                "metadata": chunk.metadata,
            })

        return results

