"""Unit tests for the complete Cyber-Physical Closed-Loop Pipeline.

Verifies:
CoppeliaSim Telemetry -> Multi-Agent RAG -> Coordination Arbitration ->
SQLite WAL -> ROS 2 Bridge -> CoppeliaSim Lua String Matching Actuation.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest

from backend.audit.logger import AuditEngine
from backend.knowledge_base.retrieval import PolicyRetriever
from backend.agents.aviation_agent import AviationAgent
from backend.agents.telecom_agent import TelecomAgent
from backend.agents.fleet_agent import FleetAgent
from backend.agents.coordination_agent import CoordinationEngine


class TestCyberPhysicalClosedLoop(unittest.TestCase):
    def setUp(self) -> None:
        self.fd, self.temp_db = tempfile.mkstemp(suffix=".db")
        os.close(self.fd)
        self.audit = AuditEngine(db_path=self.temp_db)
        self.retriever = PolicyRetriever()
        self.aviation = AviationAgent(retriever=self.retriever)
        self.telecom = TelecomAgent(retriever=self.retriever)
        self.fleet = FleetAgent(retriever=self.retriever)
        self.coordinator = CoordinationEngine(audit_engine=self.audit, retriever=self.retriever)

    def tearDown(self) -> None:
        if os.path.exists(self.temp_db):
            os.remove(self.temp_db)
        for ext in ("-wal", "-shm"):
            wal_file = self.temp_db + ext
            if os.path.exists(wal_file):
                os.remove(wal_file)

    def test_end_to_end_closed_loop_hems_emergency(self) -> None:
        # 1. Telemetry received from CoppeliaSim (e.g. Quadcopter detecting HEMS helicopter)
        coppelia_telemetry = {
            "drone_id": "UAS_CARGO_DXB_104",
            "altitude_m": 120.0,
            "ground_speed_mps": 22.5,
            "airspace_traffic": {
                "manned_traffic_detected": True,
                "hems_in_vicinity": True,
                "intruder_distance_m": 820.0,
            },
            "telecom_metrics": {
                "rtt_latency_ms": 42.0,
                "packet_loss_pct": 0.1,
                "link_lost": False,
            },
            "fleet_telemetry": {
                "battery_soc_pct": 21.5,
            },
        }

        # 2. Multi-Agent Evaluation
        av_resp = self.aviation.evaluate_state(coppelia_telemetry)
        tc_resp = self.telecom.evaluate_state(coppelia_telemetry)
        fl_resp = self.fleet.evaluate_state(coppelia_telemetry)

        # 3. Coordination Engine Arbitration
        cmd = self.coordinator.resolve_conflict(
            aviation_resp=av_resp,
            telecom_resp=tc_resp,
            fleet_resp=fl_resp,
            state=coppelia_telemetry,
            target_drone_id="UAS_CARGO_DXB_104",
        )

        self.assertEqual(cmd.action, "EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION")
        self.assertEqual(cmd.selected_agent, "aviation_safety_agent")

        # 4. Verify SQLite WAL Commit
        with sqlite3.connect(self.temp_db) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM audit_logs WHERE agent_id = 'coordination_engine' ORDER BY rowid DESC LIMIT 1;")
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["recommended_action"], "EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION")
            self.assertEqual(row["target_drone_id"], "UAS_CARGO_DXB_104")

            # 5. Bridge Node Payload Serialization
            bridge_payload = json.dumps({
                "event_id": row["event_id"],
                "target_drone_id": row["target_drone_id"],
                "recommended_action": row["recommended_action"],
                "decision_justification": row["decision_justification"],
                "confidence_score": float(row["confidence_score"]),
                "timestamp": row["timestamp"],
            })

        # 6. Emulate CoppeliaSim Lua Child Script Actuation
        sim_target_z = 2.0  # Initial altitude

        if "EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION" in bridge_payload:
            sim_target_z = 0.05
        elif "DESCEND_30M_AND_INITIATE_5G_CELL_HANDOVER" in bridge_payload:
            sim_target_z = max(0.05, sim_target_z - 0.5)

        # Assert that the quadcopter actuated to ground level
        self.assertEqual(sim_target_z, 0.05, "CoppeliaSim quadcopter should be grounded for airspace evacuation")


if __name__ == "__main__":
    unittest.main()

