# AeroGrid: Multi-Agent Unmanned Traffic Management (UTM) & Cyber-Physical Digital Twin

[![ITU AI for Good](https://img.shields.io/badge/ITU-AI%20for%20Good%20Hackathon-blue.svg)](https://aiforgood.itu.int/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)
[![ROS 2 Humble](https://img.shields.io/badge/ROS%202-Humble%20Hawksbill-orange.svg)](https://docs.ros.org/en/humble/)
[![CoppeliaSim](https://img.shields.io/badge/CoppeliaSim-4.7%2B-blueviolet.svg)](https://www.coppeliarobotics.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**AeroGrid** is a modular, multi-agent Unmanned Traffic Management (UTM) prototype engineered for the **ITU AI for Good Hackathon**. It coordinates autonomous drone operations across high-density urban airspaces and Beyond Visual Line of Sight (BVLOS) corridors through regulatory-grounded multi-agent reasoning, statutory conflict arbitration, a ZeroMQ cyber-physical digital twin in CoppeliaSim, and a high-performance native PyQt5 Tactical Mission Control HUD.

---

## 🏛️ System Architecture

AeroGrid enforces a **strict separation of concerns**: domain agents never execute actions directly. Instead, they ingest telemetry, query policy regulations via RAG, and output structured Pydantic recommendations. A statutory **Coordination Engine** resolves competing priorities according to aviation law, commits immutable audit records to SQLite WAL, and dispatches directives to cyber-physical actuators over ZeroMQ and ROS 2.

```
                            +-------------------------------------+
                            |      Tactical Airspace Telemetry    |
                            |   (UAS State, Airspace, Telecom)    |
                            +------------------+------------------+
                                               |
                     +-------------------------+-------------------------+
                     |                         |                         |
                     v                         v                         v
          +---------------------+   +---------------------+   +---------------------+
          |    Aviation Agent   |   |    Telecom Agent    |   |     Fleet Agent     |
          |  (Airspace Safety)  |   |    (C2 Link QoS)    |   |   (Logistics & SoC) |
          +----------+----------+   +----------+----------+   +----------+----------+
                     |                         |                         |
                     | Policy Query (RAG)      | Policy Query (RAG)      | Policy Query (RAG)
                     v                         v                         v
               [PolicyRetriever]         [PolicyRetriever]         [PolicyRetriever]
            (UAE Law 26 / GCAA Part IV)   (TDRA 5030-5091 MHz)     (AeroGrid Fleet SOP)
                     |                         |                         |
                     +-------------------------+-------------------------+
                                               |
                     Outputs Strict Pydantic AgentResponse (Action, Justification, Conf)
                                               v
                            +-------------------------------------+
                            |         CoordinationEngine          |
                            |   Statutory Priority Arbitration    |
                            +------------------+------------------+
                                               |
                               +---------------+---------------+
                               |                               |
                               v                               v
             +-----------------------------------+   +-----------------------------------+
             |       SQLite WAL Audit Engine     |   |   ZeroMQ & ROS 2 Humble Bridge    |
             |   Cryptographic Parent-Child Link |   |  Topic: /aerogrid/utm_commands    |
             |   + Apache Parquet Analytics      |   |  Port: 23000 (CoppeliaSim ZMQ)    |
             +-----------------------------------+   +-----------------+-----------------+
                                                                       |
                                                                       v
                                                     +-----------------------------------+
                                                     |    CoppeliaSim 3D Digital Twin    |
                                                     |  Smooth Autonomous Quadcopter     |
                                                     +-----------------------------------+
```

---

## ⚖️ Statutory Conflict Arbitration Hierarchy

AeroGrid implements the **ASTM F3411** / **ISO 23629** precedence matrix:

| Priority Tier | Domain Authority | Statutory Mandate | Overriding Precedence |
|---|---|---|---|
| **Tier 1** | **Aviation Safety Agent** | UAE Federal Decree-Law No. 26 Art. 14, GCAA CAR Part IV UAS.406 | **Absolute Right-of-Way**: Yielding to manned aircraft (HEMS) and airspace deconfliction strictly overrides telecommunication preferences and commercial delivery deadlines. |
| **Tier 2** | **Telecom C2 Agent** | TDRA Spectrum Guidelines (5030–5091 MHz), ICAO Annex 10 | **Link Integrity**: Command & Control link QoS degradation (RTT > 100ms, loss > 1%) forces immediate altitude adjustments / cell handovers, overriding economic schedules. |
| **Tier 3** | **Fleet Operations Agent** | AeroGrid Fleet SOP Sec 4.2 | **Logistics & Energy**: Governs cruise speed, delivery SLAs, and low-battery vertiport diversion under nominal airspace conditions. |

---

## 🚀 Key Capabilities

* **ZeroMQ CoppeliaSim Bridge**: Communicates directly with CoppeliaSim on port 23000 using `coppeliasim_zmqremoteapi_client`. Preserves the factory Quadcopter's flight PID dynamics while dynamically updating setpoint waypoints with smooth trajectory interpolation.
* **Native PyQt5 Mission Control HUD**: Dark-mode aerospace tactical interface featuring an animated 30 FPS radar sweep, dynamic target markers (HEMS, NFZ, 5G shadow cell, Vertiport), real-time telemetry meters, multi-agent deliberation cards, and live SQLite WAL audit log feeds.
* **ROS 2 Humble Integration**: Full `ament_python` bridge package publishing verified JSON commands on `/aerogrid/utm_commands` at 2 Hz with in-memory deduplication.
* **Cryptographic SQLite WAL Audit Engine**: Every arbitration decision is signed with SHA-256 context hashing and relational parent-decision tracking (`PRAGMA journal_mode=WAL`), with one-click export to Apache Parquet via Pandas and PyArrow.
* **RAG Regulatory Knowledge Base**: Vectorized ingestion pipeline (`ingest_uae_policies.py`) processing UAE civil aviation and telecommunications regulatory PDFs using LangChain and ChromaDB (`all-MiniLM-L6-v2`).

---

## 📦 Directory Structure

```
AIforGood/
├── launch_aerogrid.py              # Unified system launcher
├── run_aerogrid.sh                 # Turnkey one-click executable bash runner
├── coppeliaSim.sh                  # CoppeliaSim smart environment launcher
├── ingest_uae_policies.py          # Regulatory PDF vectorization script
├── requirements.txt                # Python dependencies
├── AeroGrid/
│   ├── backend/
│   │   ├── main.py                 # Multi-agent simulation scenarios runner
│   │   ├── config.py               # Pydantic Settings configuration
│   │   ├── agents/
│   │   │   ├── base_agent.py       # BaseAgent abstract class & Pydantic schemas
│   │   │   ├── aviation_agent.py   # Tier 1 Civil aviation safety evaluator
│   │   │   ├── telecom_agent.py    # Tier 2 C2 spectrum link QoS evaluator
│   │   │   ├── fleet_agent.py      # Tier 3 Logistics & battery reserve evaluator
│   │   │   └── coordination_agent.py # Priority hierarchy conflict engine
│   │   ├── simulation/
│   │   │   └── coppelia_zmq_bridge.py # CoppeliaSim ZeroMQ remote API bridge
│   │   ├── knowledge_base/
│   │   │   ├── retrieval.py        # Hybrid PolicyRetriever (ChromaDB + Local)
│   │   │   └── vector_store.py     # High-speed cosine TF-IDF vector store
│   │   └── audit/
│   │       ├── logger.py           # SQLite WAL AuditEngine & Parquet exporter
│   │       └── aerogrid_audit.db   # Persistent WAL audit database
│   ├── frontend/
│   │   ├── gui_dashboard.py        # Native PyQt5 Tactical Mission Control HUD
│   │   └── index.html              # Web HUD prototype
│   ├── ros2_ws/
│   │   └── src/aerogrid_bridge/    # ROS 2 Humble ament_python package
│   │       ├── package.xml
│   │       ├── setup.py
│   │       └── aerogrid_bridge/
│   │           └── utm_publisher.py # 2 Hz SQLite polling publisher
│   ├── coppeliasim/
│   │   ├── quadcopter_utm_controller.lua # ROS 2 Lua child script
│   │   └── README.md               # 3D Digital twin integration guide
│   ├── data/uae_policies/          # Regulatory seed documents
│   └── tests/                      # Automated unit test suite (13 tests)
```

---

## ⚡ Quickstart Guide

### 1. Prerequisites
- **Ubuntu 22.04 LTS** (or compatible Linux)
- **Python 3.10+** with `PyQt5`, `pydantic`, `pyzmq`, `cbor2`
- **ROS 2 Humble** (`/opt/ros/humble`)
- **CoppeliaSim Edu** (v4.7+)

### 2. Launch CoppeliaSim
```bash
./coppeliaSim.sh
```
In CoppeliaSim:
1. In the left Model Browser, drag `robots` &rarr; `mobile` &rarr; **`Quadcopter`** into the scene.
2. Leave the script untouched.
3. Click the **Play** button.

### 3. Launch AeroGrid Mission Control
In a new terminal:
```bash
./run_aerogrid.sh
```

---

## 🎮 Interactive Scenarios

The PyQt5 Mission Control GUI allows instant switching between conflict scenarios:

* **`0: Nominal Cruise (2.0m)`**: Baseline safe BVLOS corridor hover. All agents in consensus.
* **`1: HEMS Emergency`**: Air ambulance intruder detected at 820m. Aviation Safety Agent overrules Fleet SLA &rarr; Quadcopter descends to ground level ($0.05\,\text{m}$) to clear the corridor.
* **`2: Urban 5G Shadow`**: 5G link degradation (RTT 295ms, loss 3.8%). Telecom Agent overrules delivery speed &rarr; Quadcopter descends by $0.5\,\text{m}$ to regain Line-of-Sight.
* **`3: Battery Divert`**: Battery reserve drops to 14.2%. Fleet Agent requests emergency divert &rarr; Quadcopter safely steers toward Vertiport Pad 1.

---

## 🧪 Testing & Verification

Run the full automated test suite (13 tests verifying WAL mode, Pydantic validation, conflict hierarchy, and closed-loop actuation):
```bash
PYTHONPATH=AeroGrid:. python3 -m unittest discover -s AeroGrid/tests -v
```

---

## 👥 Authors & Acknowledgments

- **Developer**: Mohammed Naveedh M ([@madebyNaveedh](https://github.com/madebyNaveedh))
- **Event**: ITU AI for Good Global Summit Hackathon
- **Reference Repository**: [CrashingGuru/ITUAIReadiness](https://github.com/CrashingGuru/ITUAIReadiness)
- **License**: MIT License
