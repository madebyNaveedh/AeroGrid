# AeroGrid Knowledge Base: UAE Aerospace, Telecom & ITU AI Governance Corpus

**Adapted from ITU AI Readiness Framework Reference:**  
[https://github.com/CrashingGuru/ITUAIReadiness](https://github.com/CrashingGuru/ITUAIReadiness)  
**Standard Compliance:** ITU-T Y.3172 (Machine Learning in Future Networks) & ITU AI Readiness Framework 2.0  

---

## 1. Overview
The AeroGrid Knowledge Base (KB) provides structured, semantic retrieval for autonomous and semi-autonomous multi-agent Unmanned Traffic Management (UTM). It grounds every agent recommendation in statutory UAE federal laws, Dubai Civil Aviation Authority (DCAA) directives, Telecommunications and Digital Government Regulatory Authority (TDRA) spectrum regulations, and international standards.

By embedding official policy documents into a high-dimensional vector space using **ChromaDB** and `sentence-transformers/all-MiniLM-L6-v2`, AeroGrid ensures that domain agents (Aviation Safety, Telecom C2, Fleet Operations, and Coordination) cite specific legal articles, threshold values, and mandated separation rules with deterministic provenance.

---

## 2. Regulatory & Policy Document Corpus
The Knowledge Base indexes 11 official regulatory instruments across three primary domains:

| Document Title | Issuing Body | Domain | Key Covered Articles / Thresholds |
| :--- | :--- | :--- | :--- |
| **Dubai Law No. (4) of 2020** *(as amended by Law 10/2023)* | Government of Dubai / DCAA | Dubai Sky Dome & Airspace | Art. 5 (Sky Dome Infrastructure), Art. 25 (Operator Emergency Plans & Incident Notice), Art. 26 (Corridor Separation), Art. 31 (Manned Right-of-Way), Art. 36 (Privacy & Minimization), Arts. 38–40 (Third-Party Liability). |
| **UAE Federal Decree-Law No. (26) of 2022** | UAE Federal Government / GCAA | Federal Civil Aviation | Art. 14 (Manned Aircraft Absolute Right-of-Way), Art. 22 (Airspace Classification & Emergency Corridors), Art. 45 (BVLOS Commercial Transport Authorizations). |
| **GCAA CAR Part IV (UAS Operations BVLOS)** | General Civil Aviation Authority | Airspace Separation | CAR.UAS.405 (Tactical Separation: 500 ft vertical, 1,000m horizontal buffer from manned corridors), CAR.UAS.410 (Autonomous Fail-Safe Landing). |
| **TDRA Regulations on UAS Radio Systems v2.0** | TDRA | C2 Spectrum & Telecom | Art. 3.5 (Data Protection & Crypto Authentication), Art. 4.1 (5030–5091 MHz Dedicated Band), Art. 4.2 (5G QoS Thresholds: RTT < 100ms, Packet Loss < 1.0%, Critical degradation at RTT > 250ms). |
| **TDRA UAE Spectrum Guidelines (UAS C2 Link)** | TDRA | Spectrum & QoS | Sec. 4.1 (C2 Link Reliability Metrics), Sec. 4.3 (Urban Canyon Shadowing & Handover Protocols). |
| **UAE Federal Decree-Law No. (45) of 2021 (PDPL)** | UAE Federal Government | Data Protection | Art. 4 (Purpose Limitation & Minimization), Art. 13 (De-identification & Automated Redaction), Art. 22 (Incident Severity Retention Classes). |
| **ITU-T Y.3172 (06/2019)** | International Telecommunication Union | Network ML Architecture | Pipeline Node Specifications: SRC (Data Source), C (Collector), PP (Pre-Processing), M (Model), P (Policy Gate), D (Distributor), SINK (Human Oversight / Dashboard). |
| **ITU AI Ready Report 2.0 (01/2026)** | International Telecommunication Union | AI Readiness Framework | Dimensions 1 (Data/Model Marketplace), 3 (Cross-Domain Correlation), 4 (Contextualization), 5 (Workflow Integration), 6 (Human Interface), 7 (Intent-Splitting), 8/9 (Human Oversight), 10 (Explainability & Audit), 13 (Digital/Edge Infrastructure). |
| **EU U-Space Regulation (EU) 2021/664** | European Commission / EASA | International Baseline | Common Information Services (CIS), Tactical Geo-Awareness, Weather & Traffic Deconfliction Services. |
| **3GPP Releases 15–18 (NR Support for UAVs)** | 3GPP | Cellular UAS Standards | TS 22.125 / TS 23.256: Aerial UE Subscription, Command & Control (C2) latency guarantees, Cell handover optimization. |

---

## 3. Architecture & Pipeline Mapping (ITU-T Y.3172)

```
[SRC] Raw Regulatory PDFs & Standards (data/uae_policies/)
         │
         ▼
[PP] Text Extraction (pypdf) & Recursive Chunking (chunk_size=1000, overlap=200)
         │
         ▼
[M] Semantic Embeddings Engine (all-MiniLM-L6-v2, 384-dim normalized vectors)
         │
         ▼
[C] Persistent Vector Store (ChromaDB at AeroGrid/backend/knowledge_base/vector_db)
         │
         ▼
[P] Policy Gate & Multi-Agent Retrieval (AeroGrid Domain Agents)
         │
         ▼
[D] Structured Citation & Cryptographic Audit Logger (SQLite WAL)
         │
         ▼
[SINK] Mission Control Glass Cockpit HUD & Human Authorizer Decision
```

---

## 4. How to Ingest & Query the Knowledge Base

### Running Vector Ingestion
To rebuild or update the vector database from the regulatory PDFs:
```bash
python3 ingest_uae_policies.py \
    --pdf-dir data/uae_policies \
    --persist-dir AeroGrid/backend/knowledge_base/vector_db
```

### CLI Semantic Query Tool
Query the knowledge base directly using the interactive CLI utility:
```bash
python3 AeroGrid/backend/knowledge_base/query_kb.py "HEMS emergency right of way separation"
```

Sample output:
```text
===========================================================================
  AEROGRID KNOWLEDGE BASE (ITU-T Y.3172 / UAE REGULATORY POLICIES)
===========================================================================
 Query Text : 'HEMS emergency right of way separation'
 Vector DB  : AeroGrid/backend/knowledge_base/vector_db
 Top-K Hits : 3
---------------------------------------------------------------------------
[Hit #1] Relevance Score: 0.5892 | File: UAE_Federal_Decree_Law_No_26_of_2022_Civil_Aviation.pdf
Domain: aviation
--------------------------------------------------
Article (14) - Priority and Right-of-Way in Shared Airspace
Manned aircraft, emergency medical services (HEMS), search and rescue flights,
and state security aircraft maintain absolute, unconditional right-of-way over
all unmanned aircraft systems (UAS) operating within civil airspace.
```

### Programmatic Python Usage in Agents
```python
from AeroGrid.backend.knowledge_base.retrieval import PolicyRetriever

retriever = PolicyRetriever()
results = retriever.query("tactical separation minima BVLOS corridor 500 feet", top_k=2)

for citation in results:
    print(f"Citation: {citation['document']} - {citation['text']}")
```

---

## 5. Provenance & Cryptographic Audit Integrity
Every semantic retrieval performed by a domain agent:
1. Calculates a SHA-256 hash of the input query context.
2. Attaches the exact policy document name, page number, and chunk ID.
3. Records the agent's confidence score and reasoning justification.
4. Persists the decision record to the SQLite Write-Ahead Logging (`PRAGMA journal_mode=WAL`) audit trail with an immutable `event_id`.
