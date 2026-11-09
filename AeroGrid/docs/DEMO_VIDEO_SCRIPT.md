# AeroGrid – Official 7-Minute Demonstration Video Script & Storyboard
**Submission Track:** ITU AI for Good Sandbox Hackathon: United Arab Emirates  
**Project:** AeroGrid – Multi-Agent Decision Support & Digital Twin for Unmanned Traffic Management (UTM)  
**Presenter:** Mohammed Naveedh M (@madebyNaveedh)  
**Maximum Duration:** 7:00 Minutes  
**Target Audience:** ITU AI for Good Hackathon Evaluation Panel & Dubai Civil Aviation Authority (DCAA) Stakeholders  

---

## Technical Setup Before Recording
1. **Screen Layout (Dual-Window Split 1920x1080):**
   - **Left Half (960x1080):** AeroGrid Mission Control Glass Cockpit HUD (Dark theme, real-time radar sweep, agent cards, telemetry gauges, and arbitration banner).
   - **Right Half (960x1080):** CoppeliaSim Quadcopter Digital Twin simulation window (ZeroMQ connected on port 23000, 3D Dubai Sky Dome corridor scene).
2. **Launch Command:**
   ```bash
   ./run_aerogrid.sh
   ```
3. **Audio:** High-clarity microphone, confident and precise pacing.

---

## Detailed Video Timeline & Script

---

### [0:00 – 1:00] Act 1: Introduction & The Dubai Sky Dome Challenge
- **Visual:** Title card with ITU AI for Good UAE Hackathon logo, UAE flag, and AeroGrid banner. Transition to screen capture showing CoppeliaSim quadcopter hovering steadily in the 3D scene alongside the Mission Control HUD.
- **Presenter Narration:**
  > *"Greetings, distinguished judges and delegates of the ITU AI for Good Sandbox Hackathon. My name is Mohammed Naveedh, and today I am proud to present **AeroGrid** — an Unmanned Traffic Management multi-agent decision support system and cyber-physical digital twin designed for the UAE's visionary **Dubai Sky Dome** initiative.*
  >
  > *As autonomous drones transition into commercial delivery, infrastructure inspection, and critical medical transport across Dubai, airspace safety no longer depends on the aircraft alone. A drone simultaneously contends with temporary flight restrictions, 5G cellular command-and-control handovers, localized desert microbursts, and battery depletion. Crucially, these systems are managed by separate entities — civil aviation authorities, telecom operators, and commercial fleet managers — each seeing only a fraction of the operational picture.*
  >
  > *AeroGrid operationalizes the **ITU-T Y.3172** machine learning architectural framework and the **ITU AI Readiness Framework 2.0** to reconcile cross-institutional decisions in real time while preserving human-in-the-loop statutory authority."*

---

### [1:00 – 2:15] Act 2: Multi-Agent Architecture & ITU-T Y.3172 Pipeline Mapping
- **Visual:** Camera zooms into the Mission Control HUD, highlighting the 3 domain cards on the right and the arbitration verdict at the bottom.
- **Presenter Narration:**
  > *"Let's examine how AeroGrid structures this collaboration without violating organizational boundaries. AeroGrid implements four role-specific agents grounded in statutory law:
  >
  > 1. **The Aviation Safety Agent:** Operates under UAE Federal Decree-Law No. 26 of 2022 and GCAA CAR Part IV, monitoring tactical separation buffers and emergency right-of-way.
  > 2. **The Telecom C2 Agent:** Evaluates 5G cellular link metrics under TDRA Unmanned Aircraft Radio Regulations v2.0, enforcing strict latency bounds under 100 milliseconds and packet loss under 1%.
  > 3. **The Fleet Operations Agent:** Balances battery State-of-Charge, motor endurance, and delivery mission constraints.
  > 4. **The Coordination Agent:** Implements Dimension 7 of the ITU AI Readiness Framework — **Intent-Splitting**. Rather than overruling institutional mandates, it evaluates trade-offs, highlights missing facts, and synthesizes a ranked recommendation for the human authorizer.
  >
  > Every step maps directly to ITU-T Y.3172 nodes: Source telemetry at the **SRC** node, local buffering via SQLite Write-Ahead Logging at the **C** node, automated privacy redaction at the **PP** node, policy evaluation at the **P** node, and human oversight at the **SINK** dashboard."*

---

### [2:15 – 4:30] Act 3: Live Progressive Error Scenario (T0 – T5) & Physical Actuation
- **Visual:** Focus on the Scenario Buttons and simultaneous CoppeliaSim 3D quadcopter movement.
- **Presenter Narration:**
  > *"Now, let's demonstrate the progressive incident scenario from Section 5 of our Technical Report, where information arrives piecemeal across agents.
  >
  > **[Click Scenario 0: Nominal Cruise]**  
  > In baseline cruise at 2.0 meters, all 5 avionics telemetry gauges show nominal health: altitude 120m, speed 22.5 m/s, battery 88%, latency 32 ms. The drone holds station in the Dubai BVLOS corridor.
  >
  > **[Click Scenario 1: T0–T1 HEMS Air Ambulance Incursion]**  
  > Watch the radar sweep: a manned Helicopter Emergency Medical Service (HEMS) incursion is detected 820 meters away. Look at the agents:
  > - The Aviation Agent immediately requests an `EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION` with 0.98 confidence, citing UAE Law 26 Article 14.
  > - Simultaneously, the Fleet Agent warns that abrupt maneuvers consume critical battery.
  > - Look at the **Arbitration Verdict**: The Coordination Engine enforces Tier 1 Airspace Safety Priority, ruling that life-safety manned right-of-way strictly subordinates fleet energy preferences.
  > - Notice the CoppeliaSim quadcopter: Over ZeroMQ port 23000, Python smoothly commands the quadcopter to descend to safe ground buffer level (0.05m) without causing PID rotor tumbling.
  >
  > **[Click Scenario 2: T2 Urban 5G Shadow Zone]**  
  > Next, the drone encounters an urban canyon cellular shadow. Latency spikes to 280ms, violating TDRA Article 4.2.
  > - The Telecom Agent immediately flags critical C2 degradation.
  > - The Arbitration Engine commands a controlled descent of 0.5m to re-establish line-of-sight with ground gNodeB base stations. Watch the 3D twin smoothly adjust altitude in real time.
  >
  > **[Click Scenario 3: T3–T4 Battery Critical Divert]**  
  > Now, severe desert winds trigger a battery reserve warning below 20%.
  > - The Fleet Agent flags imminent motor cut-off and requests diversion to Vertiport Pad 1.
  > - The Coordination Engine confirms the safe landing corridor, overrides non-critical mission waypoints, and guides the quadcopter safely to the vertiport landing pad."*

---

### [4:30 – 5:45] Act 4: The Vector Knowledge Base & Legal Citation Engine
- **Visual:** Transition to a terminal window showing `python3 AeroGrid/backend/knowledge_base/query_kb.py` in action, highlighting retrieved chunks, similarity scores, and metadata.
- **Presenter Narration:**
  > *"A critical requirement of the ITU AI for Good Sandbox is grounding agent reasoning in verifiable regulatory knowledge.
  >
  > Adapting the reference implementation from `CrashingGuru/ITUAIReadiness`, we constructed a vector Knowledge Base indexing 11 comprehensive UAE and international regulatory documents, including Dubai Law 4/2020, UAE Federal Decree-Law 26, TDRA Spectrum Regulations v2.0, the UAE Personal Data Protection Law (PDPL), and ITU-T Y.3172.
  >
  > Using `all-MiniLM-L6-v2` embeddings stored in ChromaDB, our agents query the legal corpus semantically. When we query *'TDRA C2 latency packet loss radio spectrum'*, the engine retrieves Article 4.2 with sub-millisecond precision, extracting the exact 100ms threshold.
  >
  > Every recommendation includes document provenance and page citations, and is logged to our SQLite Write-Ahead Logging audit database with cryptographic hash chaining — ensuring tamper-evident accountability."*

---

### [5:45 – 6:30] Act 5: Controversies & The 6 Policy Gaps (G1 – G6)
- **Visual:** Technical Report Section 6 summary graphic highlighting Gaps G1 through G6.
- **Presenter Narration:**
  > *"AeroGrid directly confronts the legal and policy friction points of autonomous UTM:
  >
  > - **The Controversy:** Who bears liability when an automated network priority change causes a secondary drone to drop link and crash? Current laws protect RF spectrum but are silent on AI-directed telecom resource reallocation. AeroGrid doesn't pretend to solve this politically; instead, it generates an immutable evidentiary audit trail proving exactly what each agent knew, what the Coordination Engine warned, and what the human authorized.
  > - **Privacy Escalation:** When accident investigators request onboard video showing citizens on Dubai streets, AeroGrid's Pre-Processing (PP) node automatically redacts identifiable biometric data under UAE PDPL Article 13 before storage.
  >
  > We synthesized our findings into six concrete policy gaps (G1 through G6) — from cross-domain latency SLAs to edge node energy benchmarks — submitted as actionable contributions to ITU-T study groups."*

---

### [6:30 – 7:00] Act 6: Conclusion & Repository Verification
- **Visual:** Displaying the public GitHub repository at `https://github.com/madebyNaveedh/AeroGrid` showing passing test suite, documentation, and MIT license.
- **Presenter Narration:**
  > *"In conclusion, AeroGrid demonstrates how ITU-T Y.3172 standards and UAE regulatory frameworks combine to create a safe, explainable, and ethically grounded Unmanned Traffic Management system.
  >
  > The complete codebase, vector Knowledge Base, 5-page Technical Report, CoppeliaSim digital twin bridge, and test suite are 100% open source and publicly accessible on GitHub at `madebyNaveedh/AeroGrid`.
  >
  > Thank you for your consideration, and we look forward to advancing autonomous aviation for the global good."*
