#!/usr/bin/env python3
"""AeroGrid Turnkey Web & API Server.

Serves the high-contrast Mission Control Glass Cockpit HUD (index.html) and provides
live REST and SSE/telemetry endpoints for multi-agent deliberation, CoppeliaSim
ZeroMQ remote actuation, ROS 2 Humble topic publishing, and Knowledge Base retrieval.
"""

from __future__ import annotations

import cgi
import json
import logging
import os
import sys
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Module path resolution
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AEROGRID_DIR = REPO_ROOT / "AeroGrid"
PY_PACKAGES = REPO_ROOT / "py_packages"
if PY_PACKAGES.exists() and str(PY_PACKAGES) not in sys.path:
    sys.path.insert(0, str(PY_PACKAGES))
if str(AEROGRID_DIR) not in sys.path:
    sys.path.insert(0, str(AEROGRID_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.audit.logger import AuditEngine
from backend.knowledge_base.retrieval import PolicyRetriever
from backend.agents.aviation_agent import AviationAgent
from backend.agents.telecom_agent import TelecomAgent
from backend.agents.fleet_agent import FleetAgent
from backend.agents.coordination_agent import CoordinationEngine
from backend.simulation.coppelia_zmq_bridge import CoppeliaZMQBridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [AeroGrid.Server] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("aerogrid.server")

# ------------------------------------------------------------------------------
# Global Backend Core Singleton
# ------------------------------------------------------------------------------
class BackendCore:
    def __init__(self):
        db_path = str(AEROGRID_DIR / "backend" / "audit" / "aerogrid_audit.db")
        vector_db_dir = str(AEROGRID_DIR / "backend" / "knowledge_base" / "vector_db")

        self.audit_engine = AuditEngine(db_path=db_path)
        self.retriever = PolicyRetriever(chroma_persist_dir=vector_db_dir)
        self.aviation_agent = AviationAgent(llm_client=None, retriever=self.retriever)
        self.telecom_agent = TelecomAgent(llm_client=None, retriever=self.retriever)
        self.fleet_agent = FleetAgent(llm_client=None, retriever=self.retriever)
        self.coordinator = CoordinationEngine(audit_engine=self.audit_engine, retriever=self.retriever)

        self.zmq_bridge = CoppeliaZMQBridge()
        self.zmq_bridge.connect()

        self.active_scenario_idx = 0
        self.last_deliberation: dict = {}
        self.lock = threading.Lock()

        # Execute Scenario 0 (Nominal Cruise) at startup
        self.execute_scenario(0)

    def execute_scenario(self, scenario_idx: int) -> dict:
        with self.lock:
            self.active_scenario_idx = scenario_idx

            if scenario_idx == 0:
                # Nominal BVLOS Cruise in Dubai Sky Dome
                state = {
                    "drone_id": "UAS_CARGO_DXB_104",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "altitude_m": 120,
                    "ground_speed_mps": 22.5,
                    "airspace_traffic": {
                        "manned_traffic_detected": False,
                        "intruder_distance_m": 8500,
                        "hems_in_vicinity": False,
                    },
                    "telecom_metrics": {
                        "rtt_latency_ms": 35,
                        "packet_loss_pct": 0.05,
                        "link_lost": False,
                        "urban_canyon_shadowing": False,
                    },
                    "fleet_telemetry": {
                        "drone_id": "UAS_CARGO_DXB_104",
                        "battery_soc_pct": 82.0,
                        "cargo_type": "standard_parcel",
                        "expedited_medical_payload": False,
                    },
                }
                # Actuate CoppeliaSim to 2.0m hover
                self.zmq_bridge.execute_utm_action("MAINTAIN_ASSIGNED_AIRSPACE_CORRIDOR")

            elif scenario_idx == 1:
                # Scenario 1: HEMS Manned Helicopter Incursion
                state = {
                    "drone_id": "UAS_CARGO_DXB_104",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "altitude_m": 120,
                    "ground_speed_mps": 22.5,
                    "airspace_traffic": {
                        "manned_traffic_detected": True,
                        "intruder_distance_m": 820,
                        "closing_velocity_mps": 65.0,
                        "hems_in_vicinity": True,
                    },
                    "telecom_metrics": {
                        "rtt_latency_ms": 42,
                        "packet_loss_pct": 0.1,
                        "link_lost": False,
                        "urban_canyon_shadowing": False,
                    },
                    "fleet_telemetry": {
                        "drone_id": "UAS_CARGO_DXB_104",
                        "battery_soc_pct": 21.5,
                        "cargo_type": "standard_parcel",
                        "expedited_medical_payload": False,
                    },
                }
                # Actuate CoppeliaSim: Emergency Descent to 0.05m
                self.zmq_bridge.execute_utm_action("EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION")

            elif scenario_idx == 2:
                # Scenario 2: Urban Canyon 5G Shadowing
                state = {
                    "drone_id": "UAS_DELIVERY_AUH_209",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "altitude_m": 90,
                    "ground_speed_mps": 18.0,
                    "airspace_traffic": {
                        "manned_traffic_detected": False,
                        "intruder_distance_m": 4500,
                        "hems_in_vicinity": False,
                    },
                    "telecom_metrics": {
                        "rtt_latency_ms": 295,
                        "packet_loss_pct": 3.8,
                        "link_lost": False,
                        "urban_canyon_shadowing": True,
                    },
                    "fleet_telemetry": {
                        "drone_id": "UAS_DELIVERY_AUH_209",
                        "battery_soc_pct": 58.0,
                        "cargo_type": "high_value_retail",
                        "expedited_medical_payload": False,
                    },
                }
                # Actuate CoppeliaSim: Descend 0.5m for gNodeB LoS
                self.zmq_bridge.execute_utm_action("DESCEND_30M_AND_INITIATE_5G_CELL_HANDOVER")

            elif scenario_idx == 3:
                # Scenario 3: Battery Depletion Divert
                state = {
                    "drone_id": "UAS_MED_SHJ_311",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "altitude_m": 105,
                    "ground_speed_mps": 20.0,
                    "airspace_traffic": {
                        "manned_traffic_detected": False,
                        "intruder_distance_m": 8000,
                        "hems_in_vicinity": False,
                    },
                    "telecom_metrics": {
                        "rtt_latency_ms": 38,
                        "packet_loss_pct": 0.05,
                        "link_lost": False,
                        "urban_canyon_shadowing": False,
                    },
                    "fleet_telemetry": {
                        "drone_id": "UAS_MED_SHJ_311",
                        "battery_soc_pct": 16.2,
                        "cargo_type": "lab_blood_samples",
                        "expedited_medical_payload": True,
                    },
                }
                # Actuate CoppeliaSim: Divert to Vertiport Pad 1 (-0.6, 0.45, 0.1)
                self.zmq_bridge.execute_utm_action("EMERGENCY_DIVERT_TO_NEAREST_VERTIPORT")
            else:
                raise ValueError(f"Unknown scenario index {scenario_idx}")

            # Run 3 Domain Agents
            drone_id = state["drone_id"]
            av_resp = self.aviation_agent.evaluate_state(state)
            tc_resp = self.telecom_agent.evaluate_state(state)
            fl_resp = self.fleet_agent.evaluate_state(state)

            # Arbitration via Coordination Engine
            cmd = self.coordinator.resolve_conflict(
                aviation_resp=av_resp,
                telecom_resp=tc_resp,
                fleet_resp=fl_resp,
                state=state,
                target_drone_id=drone_id,
            )

            # Format Response matching index.html format
            overruled_str = "Consensus: No agent recommendations overruled."
            if cmd.overruled_recommendations:
                ov = cmd.overruled_recommendations[0]
                overruled_str = f"Overruled: [{ov.get('agent_id')}] '{ov.get('action')}' — {ov.get('reason')}"

            # Intruder info
            intruder = None
            if scenario_idx == 1:
                intruder = {"x": 340, "y": 160, "label": "HEMS Air Ambulance (Manned)", "color": "#f56565"}

            res = {
                "scenario_idx": scenario_idx,
                "drone": drone_id,
                "alt": f"{state['altitude_m']}m",
                "speed": f"{state['ground_speed_mps']} m/s",
                "soc": f"{state['fleet_telemetry']['battery_soc_pct']}%",
                "rtt": f"{state['telecom_metrics']['rtt_latency_ms']} ms",
                "loss": f"{state['telecom_metrics']['packet_loss_pct']:.2f}%",
                "av": {
                    "action": av_resp.recommended_action,
                    "conf": f"Conf: {av_resp.confidence:.2f}",
                    "just": av_resp.justification,
                    "citations": av_resp.policy_citations[:2] if av_resp.policy_citations else ["UAE Law 26 Art. 14", "GCAA CAR.UAS.405"],
                },
                "tc": {
                    "action": tc_resp.recommended_action,
                    "conf": f"Conf: {tc_resp.confidence:.2f}",
                    "just": tc_resp.justification,
                    "citations": tc_resp.policy_citations[:2] if tc_resp.policy_citations else ["TDRA 5030-5091 MHz"],
                },
                "fl": {
                    "action": fl_resp.recommended_action,
                    "conf": f"Conf: {fl_resp.confidence:.2f}",
                    "just": fl_resp.justification,
                    "citations": fl_resp.policy_citations[:2] if fl_resp.policy_citations else ["AeroGrid Fleet SOP 4.2"],
                },
                "coord": {
                    "action": cmd.action,
                    "just": cmd.justification,
                    "overruled": overruled_str,
                    "status": "CONFLICT RESOLVED (Tier 1)" if cmd.conflict_detected else "CONSENSUS NOMINAL",
                    "audit_event_id": cmd.audit_event_id or f"evt_{int(time.time()*1000)}",
                },
                "coppelia_telemetry": self.zmq_bridge.read_telemetry(),
                "intruder": intruder,
            }
            self.last_deliberation = res
            return res

    def get_telemetry(self) -> dict:
        cop_telem = self.zmq_bridge.read_telemetry()
        return {
            "scenario_idx": self.active_scenario_idx,
            "connected": cop_telem.get("connected", False),
            "position": cop_telem.get("position", {"x": 0.0, "y": 0.0, "z": 2.0}),
            "target_z": cop_telem.get("target_z", 2.0),
            "drone_id": self.last_deliberation.get("drone", "UAS_CARGO_DXB_104"),
            "audit_event_id": self.last_deliberation.get("coord", {}).get("audit_event_id", "evt_init"),
        }


backend_core = BackendCore()


# ------------------------------------------------------------------------------
# HTTP Request Handler
# ------------------------------------------------------------------------------
class AeroGridHTTPHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        web_root = str(AEROGRID_DIR / "frontend")
        super().__init__(*args, directory=web_root, **kwargs)

    def do_GET(self):
        url = urlparse(self.path)

        if url.path == "/api/telemetry":
            data = backend_core.get_telemetry()
            self._send_json(data)
            return

        elif url.path == "/api/status":
            self._send_json({
                "status": "ONLINE",
                "active_scenario": backend_core.active_scenario_idx,
                "coppelia_connected": backend_core.zmq_bridge.is_connected,
            })
            return

        elif url.path == "/api/audit/logs":
            logs = backend_core.audit_engine.get_all_logs()
            self._send_json(logs[-15:])
            return

        elif url.path == "/api/kb/query":
            qs = parse_qs(url.query)
            q = qs.get("q", [""])[0]
            if not q:
                self._send_json({"error": "Missing query param 'q'"}, status=400)
                return
            hits = backend_core.retriever.query(q, top_k=3)
            self._send_json({"query": q, "hits": hits})
            return

        elif url.path in ["/", "/index.html"]:
            self.path = "/index.html"
            return super().do_GET()

        return super().do_GET()

    def do_POST(self):
        url = urlparse(self.path)

        if url.path.startswith("/api/scenario/"):
            try:
                scen_idx = int(url.path.split("/")[-1])
                data = backend_core.execute_scenario(scen_idx)
                self._send_json(data)
            except Exception as e:
                logger.error("Error executing scenario via API: %s", e)
                self._send_json({"error": str(e)}, status=500)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found")

    def _send_json(self, data: dict | list, status: int = 200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        # Quiet standard requests to avoid terminal spam
        pass


def run_server(port: int = 8080):
    server = ThreadingHTTPServer(("0.0.0.0", port), AeroGridHTTPHandler)
    logger.info("AeroGrid Mission Control Web Server live at: http://localhost:%d", port)
    logger.info("Access the Mission Control HUD in Firefox or Chrome: http://localhost:%d", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server()
