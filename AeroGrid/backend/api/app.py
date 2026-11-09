"""AeroGrid FastAPI Operational Service.

Provides real-time REST and WebSocket endpoints for drone telemetry ingestion,
multi-agent conflict arbitration, SQLite WAL audit inspection, and dashboard serving.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse
    from pydantic import BaseModel, Field
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    BaseModel = object  # type: ignore[misc,assignment]

from backend.config import settings
from backend.audit.logger import AuditEngine
from backend.knowledge_base.retrieval import PolicyRetriever
from backend.agents.aviation_agent import AviationAgent
from backend.agents.telecom_agent import TelecomAgent
from backend.agents.fleet_agent import FleetAgent
from backend.agents.coordination_agent import CoordinationEngine

logger = logging.getLogger("aerogrid.api")

# Initialize backend singletons
audit_engine = AuditEngine(db_path=settings.db_path)
policy_retriever = PolicyRetriever()
aviation_agent = AviationAgent(retriever=policy_retriever)
telecom_agent = TelecomAgent(retriever=policy_retriever)
fleet_agent = FleetAgent(retriever=policy_retriever)
coordinator = CoordinationEngine(audit_engine=audit_engine, retriever=policy_retriever)

FRONTEND_HTML = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


if HAS_FASTAPI:
    app = FastAPI(
        title="AeroGrid UTM Operational API",
        version="0.1.0",
        description="Modular Multi-Agent UTM Coordination & Audit Service",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    class TelemetryPayload(BaseModel):  # type: ignore[misc]
        drone_id: str = Field(default="UAS_CARGO_DXB_104", description="UAS registration identifier")
        timestamp: Optional[str] = Field(default=None, description="ISO-8601 UTC timestamp")
        altitude_m: float = Field(default=120.0, description="Altitude in meters above ground level")
        ground_speed_mps: float = Field(default=22.5, description="Ground speed in m/s")
        airspace_traffic: Dict[str, Any] = Field(
            default_factory=lambda: {
                "manned_traffic_detected": False,
                "hems_in_vicinity": False,
                "intruder_distance_m": 4500,
            }
        )
        telecom_metrics: Dict[str, Any] = Field(
            default_factory=lambda: {
                "rtt_latency_ms": 42.0,
                "packet_loss_pct": 0.1,
                "link_lost": False,
            }
        )
        fleet_telemetry: Dict[str, Any] = Field(
            default_factory=lambda: {
                "battery_soc_pct": 65.0,
                "cargo_type": "standard_parcel",
                "expedited_medical_payload": False,
            }
        )

    @app.get("/", summary="Serve Interactive Airspace Dashboard")
    async def serve_dashboard():
        if FRONTEND_HTML.exists():
            return FileResponse(str(FRONTEND_HTML))
        return JSONResponse({"status": "AeroGrid API Active", "version": "0.1.0"})

    @app.get("/health", summary="Health check endpoint")
    async def health_check():
        return {
            "status": "healthy",
            "environment": settings.aerogrid_env,
            "database": audit_engine.db_path,
            "agents": ["aviation_safety_agent", "telecom_c2_agent", "fleet_ops_agent", "coordination_engine"],
        }

    @app.post("/api/v1/telemetry/evaluate", summary="Evaluate drone telemetry and arbitrate conflicts")
    async def evaluate_telemetry(payload: TelemetryPayload):
        state = payload.dict() if hasattr(payload, "dict") else payload.model_dump()
        drone_id = state.get("drone_id", "UAS_01")

        # Step 1: Parallel Agent Evaluation
        av_resp = aviation_agent.evaluate_state(state)
        tc_resp = telecom_agent.evaluate_state(state)
        fl_resp = fleet_agent.evaluate_state(state)

        # Step 2: Multi-Agent Conflict Arbitration
        cmd = coordinator.resolve_conflict(
            aviation_resp=av_resp,
            telecom_resp=tc_resp,
            fleet_resp=fl_resp,
            state=state,
            target_drone_id=drone_id,
        )

        return {
            "target_drone_id": drone_id,
            "operational_command": cmd.model_dump() if hasattr(cmd, "model_dump") else cmd.__dict__,
            "agent_deliberations": {
                "aviation": av_resp.model_dump() if hasattr(av_resp, "model_dump") else av_resp.__dict__,
                "telecom": tc_resp.model_dump() if hasattr(tc_resp, "model_dump") else tc_resp.__dict__,
                "fleet": fl_resp.model_dump() if hasattr(fl_resp, "model_dump") else fl_resp.__dict__,
            },
        }

    @app.get("/api/v1/audit/logs", summary="List recent SQLite WAL audit logs")
    async def get_audit_logs(limit: int = 50):
        logs = audit_engine.get_all_logs()
        return {"total_records": len(logs), "logs": logs[-limit:]}

    @app.get("/api/v1/audit/trail/{context_hash}", summary="Get audit lineage for a specific context hash")
    async def get_audit_trail(context_hash: str):
        trail = audit_engine.get_audit_trail_by_context(context_hash)
        if not trail:
            raise HTTPException(status_code=404, detail="Context hash not found in audit database")
        return {"context_hash": context_hash, "trail": trail}

    @app.post("/api/v1/audit/export/parquet", summary="Export SQLite WAL logs to Parquet")
    async def export_parquet():
        export_path = Path(settings.parquet_dir) / "utm_audit_trace.parquet"
        try:
            target = audit_engine.export_to_parquet(str(export_path))
            return {"status": "success", "exported_path": target}
        except ImportError as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/knowledge-base/search", summary="Search regulatory knowledge base")
    async def search_kb(domain: str = "aviation", query: str = "separation minima"):
        results = policy_retriever.query_policy(domain=domain, query=query, top_k=3)
        return {"domain": domain, "query": query, "results": results}

    @app.websocket("/api/v1/ws/simulation")
    async def simulation_websocket(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                # Stream simulated telemetry tick every 1.0 second
                state = {
                    "drone_id": "UAS_CARGO_DXB_104",
                    "altitude_m": 120.0,
                    "ground_speed_mps": 22.5,
                    "airspace_traffic": {"intruder_distance_m": 820, "manned_traffic_detected": True, "hems_in_vicinity": True},
                    "telecom_metrics": {"rtt_latency_ms": 42.0, "packet_loss_pct": 0.1},
                    "fleet_telemetry": {"battery_soc_pct": 21.5},
                }
                av = aviation_agent.evaluate_state(state)
                tc = telecom_agent.evaluate_state(state)
                fl = fleet_agent.evaluate_state(state)
                cmd = coordinator.resolve_conflict(av, tc, fl, state, "UAS_CARGO_DXB_104")

                await websocket.send_json({
                    "type": "SIM_TICK",
                    "action": cmd.action,
                    "confidence": cmd.confidence_score,
                    "target_drone_id": cmd.target_drone_id,
                    "audit_event_id": cmd.audit_event_id,
                })
                await asyncio.sleep(1.0)
        except WebSocketDisconnect:
            logger.info("Simulation WebSocket client disconnected.")

else:
    app = None  # type: ignore[assignment]


def main() -> None:
    if not HAS_FASTAPI:
        print("[ERROR] FastAPI and Uvicorn are required to run the AeroGrid Operational API.")
        print("Install them via: pip install fastapi uvicorn")
        return

    import uvicorn
    uvicorn.run("backend.api.app:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()

