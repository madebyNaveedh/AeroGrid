# AeroGrid (Phase 1) - Multi-Agent UTM Prototype

A modular, multi-agent Unmanned Traffic Management (UTM) architecture designed with strict separation of concerns, regulatory RAG policy grounding, priority-based conflict arbitration, and immutable SQLite WAL audit logging.

## Architectural Overview

```
                      +-----------------------------+
                      |   UTM Simulation State      |
                      | (Telemetry, Hazards, Link)  |
                      +--------------+--------------+
                                     |
           +-------------------------+-------------------------+
           |                         |                         |
           v                         v                         v
+---------------------+   +---------------------+   +---------------------+
|   Aviation Agent    |   |    Telecom Agent    |   |     Fleet Agent     |
| (Airspace Safety)   |   |   (C2 Link QoS)     |   |   (Logistics/SoC)   |
+----------+----------+   +----------+----------+   +----------+----------+
           |                         |                         |
           | Queries Policy RAG      | Queries Policy RAG      | Queries Policy RAG
           v                         v                         v
     [PolicyRetriever]         [PolicyRetriever]         [PolicyRetriever]
 (UAE Law 26, GCAA, ICAO)      (TDRA, 3GPP 5G, ICAO)     (AeroGrid Fleet SOP)
           |                         |                         |
           +-------------------------+-------------------------+
                                     |
           Outputs Strict Pydantic AgentResponse (Action, Rationale, Citations)
                                     v
                      +-----------------------------+
                      |     CoordinationEngine      |
                      |  (Priority Conflict Matrix) |
                      +--------------+--------------+
                                     |
                      Issues Validated OperationalCommand
                                     |
                                     v
                      +-----------------------------+
                      |   AuditEngine (SQLite WAL)  |
                      |  Parent-Child Provenance    |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      | Apache Parquet Analytics    |
                      |    (Pandas & PyArrow)       |
                      +-----------------------------+
```

### Statutory Precedence Hierarchy (ASTM F3411 / ISO 23629)
1. **Tier 1 (Aviation / Airspace Safety)**: Immediate collision avoidance, manned aircraft & HEMS right-of-way, and geofence containment strictly supersede all other priorities.
2. **Tier 2 (Telecom / C2 Link Reliability)**: Command & Control link degradation triggers autonomous failsafe (hover/RTH), overriding commercial schedules.
3. **Tier 3 (Fleet Logistics & Energy)**: Governs route optimization, delivery speed, and vertiport landing sequences under nominal conditions.

---

## Directory Structure

```
AeroGrid/
├── backend/
│   ├── main.py                     # End-to-end simulation runner with 3 conflict scenarios
│   ├── config.py                   # Pydantic Settings & environment manager
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base_agent.py           # Abstract BaseAgent & strict AgentResponse Pydantic schema
│   │   ├── aviation_agent.py       # GCAA/ICAO airspace separation & HEMS right-of-way
│   │   ├── telecom_agent.py        # TDRA C2 link QoS, 5G latency & failsafe monitoring
│   │   ├── fleet_agent.py          # Battery reserve (20% SoC), cargo SLAs & vertiport sequencing
│   │   └── coordination_agent.py   # Multi-agent conflict resolution & audit linker
│   ├── knowledge_base/
│   │   ├── __init__.py
│   │   └── retrieval.py            # Mock RAG PolicyRetriever seeded with aerospace & RF law
│   └── audit/
│       ├── __init__.py
│       ├── logger.py               # AuditEngine with SQLite WAL & Parquet export
│       └── exports/                # Parquet analytics export directory
├── tests/
│   ├── __init__.py
│   └── test_aerogrid.py            # Complete unit test suite (WAL mode, schemas, agents)
├── requirements.txt                # Production dependencies (Pydantic, Pandas, PyArrow, etc.)
└── .env.example                    # Environment variable configuration template
```

---

## ROS 2 Humble Bridge (CoppeliaSim Integration)

The `aerogrid_bridge` package bridges the SQLite WAL audit database to ROS 2 topics:
- **Topic**: `/aerogrid/utm_commands` (`std_msgs/msg/String`)
- **Polling Rate**: 2.0 Hz
- **De-duplication**: In-memory `event_id` tracking guarantees only new coordination decisions are transmitted.

### Build and Run ROS 2 Bridge
```bash
# 1. Source ROS 2 Humble
source /opt/ros/humble/setup.bash

# 2. Build the workspace
cd AeroGrid/ros2_ws
colcon build --packages-select aerogrid_bridge
source install/setup.bash

# 3. Run the bridge node
ros2 run aerogrid_bridge utm_publisher
```

### CoppeliaSim 3D Subscriber Example (Lua / Python)
```lua
function sysCall_init()
    sub = simROS2.createSubscription('/aerogrid/utm_commands', 'std_msgs/msg/String', 'utm_callback')
end

function utm_callback(msg)
    local cmd = json.decode(msg.data)
    sim.addLog(sim.verbosity_scriptinfos, "CoppeliaSim received UTM Action: " .. cmd.recommended_action .. " for " .. cmd.target_drone_id)
end
```

### 2. Configure Environment (Optional)
```bash
cp .env.example .env
# To use live LLM completions, set OPENAI_API_KEY and MOCK_LLM_MODE=false
```

### 3. Run the Simulation Pipeline
```bash
python3 backend/main.py
```

### 4. Run the Unit Test Suite
```bash
python3 -m unittest discover -s tests -v
```

---

## Phase 3: Knowledge Base Vectorization (ITU AI Readiness Stack)

Adapted from the reference repository [`CrashingGuru/ITUAIReadiness`](https://github.com/CrashingGuru/ITUAIReadiness).

Vectorizes UAE aerospace, telecommunications, and aviation regulatory PDFs:
- **PDF Directory**: `data/uae_policies/`
- **Text Splitter**: `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)`
- **Embedding Model**: `sentence-transformers/all-MiniLM-L6-v2`
- **Persistence Target**: `../AeroGrid/backend/knowledge_base/vector_db` (ChromaDB)

### Run Knowledge Base Ingestion
```bash
# 1. Install vectorization stack
pip install langchain langchain-community langchain-text-splitters langchain-chroma langchain-huggingface chromadb sentence-transformers pypdf

# 2. Place UAE PDFs into data/uae_policies/
# Example files:
#   - UAE_Federal_Decree_Law_No_26_Civil_Aviation.pdf
#   - GCAA_CAR_Part_IV_UAS_Operations_BVLOS.pdf
#   - TDRA_UAE_Spectrum_Guidelines_UAS_C2_Link.pdf

# 3. Execute vectorization script
python3 ingest_uae_policies.py
```

