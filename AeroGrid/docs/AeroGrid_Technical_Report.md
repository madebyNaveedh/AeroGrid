# AI for Good Sandbox Hackathon – AeroGrid
**Submission Track:** ITU AI for Good Sandbox Hackathon: United Arab Emirates  
**Authors:** Mohammed Naveedh M (@madebyNaveedh)  
**Repository:** [https://github.com/madebyNaveedh/AeroGrid](https://github.com/madebyNaveedh/AeroGrid)  
**Standard Architecture Reference:** ITU-T Y.3172 & ITU AI Ready Report 2.0  

---

## 1. Introduction
Drones are moving beyond isolated demonstrations into delivery, inspection, emergency response and other services. As the number of flights grows, safe operation depends on more than the drone itself. A flight may be affected at the same time by a temporary airspace restriction, a weak command-and-control link, congestion in a mobile network, changing weather or a low battery. These conditions are usually monitored by different organisations and systems. During an incident, the information may arrive at different times and each organisation may have only part of the picture.

**AeroGrid** is our attempt to show what decision support for that moment could look like. It brings together four role-specific agents: **Aviation Authority**, **Telecom Infrastructure**, **Fleet Operations**, and **Coordination**. Each sees a different slice of the situation, works under a different institutional mandate, and retrieves from a knowledge base (KB) of national laws and regulations. They hand one human authorizer a single reconciled recommendation with every step logged. AeroGrid does not issue flight clearances, exercise regulatory powers or directly command aircraft. The aim is to make cross-domain decisions easier to review, explain and coordinate.

The project is directly relevant to initiatives such as the **Dubai Sky Dome**, which Dubai Civil Aviation Authority (DCAA) describes as a planned virtual airspace infrastructure connecting locations through drone routes and facilities, supported by regulatory services and a drone traffic-management system. This report focuses on transferable policy and standards questions, supported by UAE source material and global examples.

---

## 2. Description of the Use Case
Consider a scenario where a hospital asks for a dedicated aerial corridor for medical-supply drones (HEMS). The corridor is already in use by commercial cargo drones. At the same time, a mobile cell nearby becomes congested, so the emergency operator asks for its control links to be prioritized.

### Current Practice
The aviation authority looks at the corridor and what it does to flights already in the air. The telecom operator checks whether it can prioritize traffic without hurting other critical connections. Commercial operators have to work out for themselves what the new restriction and the network change mean for their missions. The emergency operator just needs its drones to stay connected.

### Gaps in What Exists
Although these organisations have their own systems and established responsibilities, their assessments may rely on different information, operate independently and prioritise different operational requirements. A decision taken independently by one organisation could therefore create unintended consequences for another. For example, approving an emergency flight corridor without considering communication coverage and reliability, or prioritizing network resources without identifying the drones that could be affected, may leave important operational risks unaddressed.

### AeroGrid Multi-Agent Architecture
AeroGrid addresses this through four institutional AI agents, each with one defined responsibility:
1. **Aviation Authority Agent:** Checks authorisation status, airspace class, separation risk, emergency priority and possible safe landing areas against aviation rules (`UAE Federal Decree-Law No. 26/2022`, `Dubai Law 4/2020`, `GCAA CAR Part IV`).
2. **Telecom Infrastructure Agent:** Monitors C2 link availability, latency, congestion and spare capacity. It can recommend prioritisation but cannot touch a live network directly (`TDRA Unmanned Aircraft Radio Systems Regulations v2.0`).
3. **Fleet Operations Agent:** Evaluates battery state of charge (SoC), route feasibility, telemetry quality, weather exposure and mission limits for the aircraft affected (`ASTM F3411`, operator SOPs).
4. **Coordination Agent:** Compares domain agent findings, flags statutory conflicts and missing evidence, and formulates ranked options, including reasons not to proceed. It strictly respects statutory mandates and does not arbitrarily overrule safety minimums.

---

## 3. Use-Case Requirements (ITU-T Y.3172 Pipeline Nodes)
Requirements are specified per pipeline node as defined in ITU-T Y.3172:

### 1. Data Acquisition and Ingestion (SRC, C)
- **R1 – SRC:** UAV telemetry and network KPIs collected every second and weather advisories every minute, using only TDRA-authorised spectrum or licensed mobile services.
- **R2 – C:** Edge collectors keep a local buffer (SQLite with Write-Ahead Logging `PRAGMA journal_mode=WAL`) and write compressed history (Parquet), allowing fleets to join or leave without restarting the pipeline.

### 2. Data Processing and Privacy (PP)
- **R3 – PP:** Video and personal data are removed or pseudonymised before storage; each data type has an enforced retention period; units and timestamps are harmonised. Complies with:
  - *Dubai Law No. 4 of 2020* Art. 36 (Privacy and Data Protection)
  - *TDRA Radio Systems Regulations v2.0* Art. 3.5
  - *UAE Federal Decree-Law No. 45 of 2021* (Personal Data Protection Law - PDPL)

### 3. Model Development and Validation (M)
- **R4 – M:** Prediction models (link quality, congestion, battery drain, route reserve) are versioned and validated in an isolated sandbox before reaching the live pipeline (per ITU-T Y.3172 §8).

### 4. Policy Evaluation (P)
- **R5 – P:** Every recommendation passes a policy gate check against the vector Knowledge Base. Any actuation affecting a third party's flight or service requires explicit human approval.

### 5. Decision Distribution and Human Oversight (D, SINK)
- **R6 – D:** Decision records carry complete rationale, empirical evidence, cited regulatory articles (with document version), agent deliberation traces, and route to authorized endpoints.
- **R7 – SINK:** Authorized human operator reviews, approves, edits, or rejects recommendations via a Mission Control Glass Cockpit HUD (available in English and Arabic), logging any overrides.

---

## 4. Mapping to ITU-T Y.3172, ITU AI Readiness 2.0, and UAE Policies

| Node | AeroGrid Component | AI Readiness 2.0 Dimension | Regulatory / Standard Documents |
| :--- | :--- | :--- | :--- |
| **SRC** | UAV telemetry, 5G cell KPIs, weather feed (R1) | Digital infrastructure (Dim 13); Contextualization and regional impact (Dim 4); Data & model marketplace (Dim 1) | TDRA Unmanned Aircraft Radio Systems Regulations v2.0 (Art. 4.1, 4.2) |
| **C** | Edge collectors at cell sites and vehicle gateways (R2) | Digital infrastructure: edge, connectivity, energy (Dim 13); Cross-domain correlation (Dim 3) | PDPL (storage, transfer); TDRA Art. 3.5; SQLite WAL |
| **PP** | Minimisation, pseudonymisation, schema harmonisation (R3) | Data and model marketplace: standard formats, privacy (Dim 1) | UAE PDPL (Decree-Law 45/2021); Dubai Law 4/2020 Art. 36 |
| **M** | Link, congestion, and battery models; domain agents (R4) | Model properties (Dim 1); Guardrails against hallucination (Dim 2); Granular priorities (Dim 12) | UAE National Strategy for AI 2031; UAE Charter for the Development and Use of AI |
| **P** | Policy gate and Coordination Agent (R5) | AI and policies (Dim 10); Strategy alignment, intent split across institutions (Dim 7); Workflow integration (Dim 5) | Federal Decree-Law 26/2022; Dubai Law 4/2020 (Arts. 5, 25, 26, 31) as amended by Law 10/2023 |
| **D** | Decision record builder and dispatcher (R6) | Explainability and audit (Dim 10); Time from detection to response (Dim 5) | Dubai Law 4/2020 Art. 25.14 (incident notice); PDPL |
| **SINK** | Human authorizer dashboard (Mission Control HUD) (R7) | Human interface (Dim 6); Collaboration with AI (Dim 8); Impact of humans in AI integration (Dim 9); AI for inclusion (Dim 11) | UAE AI Charter on human oversight; Dubai Sky Dome; DCAA / DANS integration target |

> **Intent Splitting (Dimension 7):** The Coordination Agent decomposes high-level intent (*"Safely deconflict emergency corridor while preserving active airspace operations"*) into domain sub-intents:
> - *Aviation sub-intent:* Enforce vertical and horizontal separation minimums.
> - *Telecom sub-intent:* Reallocate cell capacity / QoS profiles without dropping control links.
> - *Fleet sub-intent:* Calculate glide slopes and divert trajectories within reserve energy budgets.

---

## 5. Progressive Error Scenarios (T0 – T5)
The scenario engine injects events sequentially across disparate agents to evaluate decision support under incomplete, distributed information:

| Stage | New Event (Observing Agent) | Expected Agent Behaviour & Policy Question |
| :--- | :--- | :--- |
| **T0** | Emergency HEMS fleet requests corridor & communication priority. *(Aviation, Fleet)* | Aviation checks flight authorization, airspace restrictions, and priority. Coordination establishes baseline picture and flags pending telecom inputs. |
| **T1** | 5G cell site becomes congested; payload video and telemetry degrade. *(Telecom only)* | Telecom evaluates capacity and suggests QoS re-allocation. *Policy Question:* Who possesses the legal authority to prioritize emergency C2 traffic, and how are affected civilian operators informed? |
| **T2** | Commercial drone reports escalating C2 RTT latency and dropped control packets. *(Fleet)* | Fleet flags loss-of-link risk; Aviation verifies separation buffers. Coordination enforces rule: *AI advice must never be treated as an automated flight-control override.* |
| **T3** | Localized microburst wind warning affects corridor and spikes battery draw. *(Fleet, Aviation)* | Fleet recalculates reserve margins; Aviation identifies safe emergency landing sites (Vertiports). Outdated T0–T1 advisories are marked superseded. |
| **T4** | Agents generate conflicting options: preserve corridor vs. reroute vs. suspend flights. *(Coordination)* | Coordination Agent exposes trade-offs, confidence scores, and affected parties. System refuses to fabricate an arbitrary optimum when safety constraints clash. |
| **T5** | Human authority reviews unified incident brief in SINK Mission Control HUD. *(Human SINK)* | Human reviewer approves, modifies, or rejects recommendation. Immutable decision record generated with cryptographic hash, source versions, and override rationale. |

### Controversy: Liability When AI Advice Contributes to a Loss
*Scenario:* At T4, human authorizer approves network priority for an emergency drone. As a consequence of bandwidth reallocation, a commercial drone suffers C2 link loss and emergency-lands on a private roof.
- *Commercial Operator Claim:* Loss occurred due to automated AI prioritization advice.
- *Telecom Operator Claim:* Action followed statutory authority instruction.
- *Legal Gap:* Dubai Law 4/2020 mandates emergency plans and third-party liability insurance (Arts. 25, 38–40), but does not define liability apportionment when loss of control stems from an authority-mandated network change.
- *AeroGrid Resolution:* AeroGrid preserves an indisputable SQLite WAL audit trace: exact knowledge state at T0–T5, specific KB passages cited, trade-off warnings logged by Coordination, and human approval signature.

### Escalation: From Liability to Privacy Protection
Insurers request onboard video recordings from T1–T4 to investigate the landing incident, capturing identifiable pedestrians on city streets.
- *Policy Clash:* Civil litigation disclosure vs. *Dubai Law 4/2020 Art. 36*, *TDRA Art. 3.5*, and *UAE PDPL (Decree-Law 45/2021)*.
- *AeroGrid Privacy Guardrails:* The Pre-Processing (PP) node automatically strips and blurs identifiable personal data prior to database ingestion. Unredacted raw feeds are sealed; secondary commercial access is blocked programmatically; release requests require formal joint Data Protection and Aviation Authority sign-off.

---

## 6. Identified Policy and Standards Gaps (G1 – G6)

| ID | Domain Gap | Statutory / Standard Context | AeroGrid Contribution |
| :--- | :--- | :--- | :--- |
| **G1** | **Inter-domain automated decision latency:** No agreed timing between telecom and aviation authorities when decision windows are sub-second. | Dubai Law 4/2020 Art. 19 covers RF only; TDRA v2.0 Art. 4.2 allows mobile network usage without priority rules; EU U-space 2021/664 omits cross-domain SLA timing. | Formulated cross-domain SLA template with explicit response-time bounds per incident severity class, submitted as input to ITU-T Y.3172. |
| **G2** | **Liability for AI-advised network priority changes:** Unclear liability when a network reallocation causes secondary UAS flight disruption. | 3GPP Rel 15–18 specifies UAV identification and connectivity, but lacks aviation liability rules. UAE Law 26/2022 silent on network-induced loss of separation. | Machine-readable consent flags in service-level agreements (SLAs) and liability indemnification models. |
| **G3** | **Standardized inter-agent audit format:** Lack of evidentiary logging standards for autonomous multi-agent negotiations under legal review. | EU AI Act Arts. 12 & 14 mandate record-keeping and oversight but do not specify agent-to-agent negotiation message schemas. | Open standardized audit schema (`event_id`, `agent_id`, `context_hash`, `kb_citations`, `reasoning_trace`, `human_verdict`) with SHA-256 provenance chains. |
| **G4** | **Cross-regulatory AI mandate boundaries:** Jurisdictional ambiguity between civil aviation (GCAA/DCAA) and telecommunications (TDRA) over AI agents operating across boundaries. | GCAA regulates national airspace; DCAA regulates Dubai Sky Dome; TDRA regulates spectrum. No joint governance framework exists for multi-agent UTM systems. | Machine-readable institutional mandate map embedded in the Knowledge Base, constraining agent recommendation scope. |
| **G5** | **Edge platform benchmarking and energy metrics:** Absence of standardized energy and compute readiness metrics for edge UTM nodes. | ITU AI Readiness Framework 2.0 identifies energy readiness as an essential dimension requiring per-node telemetry. | Per-node execution time (ms) and estimated power consumption (mW) logged at every pipeline step (SRC to SINK). |
| **G6** | **Privacy minimization vs. forensic accident retention:** Tension between strict data erasure rules and aviation accident investigation requirements. | UAE PDPL and Dubai Law Art. 36 mandate privacy minimization/deletion; aviation safety bodies require long-term black-box flight data retention. | Tiered retention classes tied to incident classification levels, ensuring automated blurring while preserving cryptographically verifiable telemetry. |

---

## 7. References
1. **ITU-T Y.3172 (06/2019):** *Architectural framework for machine learning in future networks including IMT-2020.* International Telecommunication Union.
2. **ITU AI Ready Report 2.0 (01/2026):** *AI Ready – Analysis Towards a Standardized Readiness Framework.* International Telecommunication Union.
3. **Dubai Media Office (2020):** *Dubai Sky Dome initiative announcement.* Dubai Civil Aviation Authority (DCAA).
4. **Dubai Law No. (4) of 2020:** *Regulating Unmanned Aircraft in the Emirate of Dubai,* as amended by Law No. (10) of 2023. Dubai Legislation Portal.
5. **UAE ICAO Information Paper IP/31:** *UAE UTM Regulations and Operations.* ICAO MIDANPIRG.
6. **TDRA (28 Dec 2022):** *Regulations on Unmanned Aircraft Radio Systems, Version 2.0.* Telecommunications and Digital Government Regulatory Authority.
7. **TDRA Press Release (22 July 2026):** *Third Edition of Unmanned Aircraft Radio Systems Regulatory Framework.*
8. **UAE Federal Decree-Law No. (45) of 2021:** *Protection of Personal Data (PDPL).* United Arab Emirates.
9. **European Commission (2021):** *Commission Implementing Regulation (EU) 2021/664 on the regulatory framework for the U-space.*
10. **3GPP (Releases 15–18):** *NR Support for Unmanned Aerial Vehicles (UAV).* 3rd Generation Partnership Project.
