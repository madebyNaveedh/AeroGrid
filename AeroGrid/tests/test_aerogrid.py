"""AeroGrid Unit Test Suite.

Verifies SQLite WAL audit logging, policy retrieval, response validation,
domain agent reasoning, and hierarchical conflict coordination.
Compatible with standard unittest and pytest.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.audit.logger import AuditEngine
from backend.knowledge_base.retrieval import PolicyRetriever
from backend.agents.base_agent import AgentResponse, BaseAgent
from backend.agents.aviation_agent import AviationAgent
from backend.agents.telecom_agent import TelecomAgent
from backend.agents.fleet_agent import FleetAgent
from backend.agents.coordination_agent import CoordinationEngine, OperationalCommand


class TestAuditEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.fd, self.temp_db = tempfile.mkstemp(suffix=".db")
        os.close(self.fd)

    def tearDown(self) -> None:
        if os.path.exists(self.temp_db):
            os.remove(self.temp_db)
        for ext in ("-wal", "-shm"):
            wal_file = self.temp_db + ext
            if os.path.exists(wal_file):
                os.remove(wal_file)

    def test_wal_journal_mode_and_schema(self) -> None:
        engine = AuditEngine(db_path=self.temp_db)
        with sqlite3.connect(self.temp_db) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode;")
            mode = cur.fetchone()[0]
            self.assertEqual(mode.lower(), "wal")

            cur.execute("PRAGMA table_info(audit_logs);")
            columns = {row[1]: row[2] for row in cur.fetchall()}
            expected_cols = [
                "event_id",
                "agent_id",
                "context_hash",
                "recommended_action",
                "decision_justification",
                "retrieved_policy_sources",
                "confidence_score",
                "timestamp",
                "parent_decision_id",
            ]
            for col in expected_cols:
                self.assertIn(col, columns)

    def test_insert_and_retrieve_log(self) -> None:
        engine = AuditEngine(db_path=self.temp_db)
        event_id = engine.insert_log(
            agent_id="test_agent",
            context_hash="hash_123456",
            recommended_action="CLIMB_100M",
            decision_justification="Test conflict avoidance",
            retrieved_policy_sources=["GCAA CAR Part IV"],
            confidence_score=0.95,
            parent_decision_id="parent_root_1",
        )
        self.assertTrue(event_id.startswith("evt_"))

        record = engine.get_log(event_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["agent_id"], "test_agent")
        self.assertEqual(record["recommended_action"], "CLIMB_100M")
        self.assertEqual(record["confidence_score"], 0.95)
        self.assertEqual(record["parent_decision_id"], "parent_root_1")

    def test_parquet_export_or_import_error(self) -> None:
        engine = AuditEngine(db_path=self.temp_db)
        engine.insert_log(
            agent_id="test_agent",
            context_hash="hash_test",
            recommended_action="HOVER",
            decision_justification="Justification",
            retrieved_policy_sources=["Policy A"],
            confidence_score=0.9,
        )
        target_parquet = os.path.join(tempfile.gettempdir(), "test_audit.parquet")
        try:
            exported = engine.export_to_parquet(target_parquet)
            self.assertTrue(os.path.exists(exported))
            os.remove(exported)
        except ImportError as e:
            self.assertIn("Pandas and PyArrow are required", str(e))


class TestPolicyRetriever(unittest.TestCase):
    def test_query_policy_citations(self) -> None:
        retriever = PolicyRetriever()
        citations = retriever.query_policy("aviation", "separation collision")
        self.assertGreater(len(citations), 0)
        first = citations[0]
        self.assertIn("source", first)
        self.assertIn("excerpt", first)
        self.assertGreater(len(first["source"]), 5)
        self.assertGreater(len(first["excerpt"]), 10)

    def test_query_telecom_policy(self) -> None:
        retriever = PolicyRetriever()
        citations = retriever.query_policy("telecom", "latency C2 lost-link")
        self.assertGreater(len(citations), 0)
        has_relevant = any("TDRA" in c["source"] or "ICAO" in c["source"] or "3GPP" in c["source"] for c in citations)
        self.assertTrue(has_relevant)


class TestAgentResponseValidation(unittest.TestCase):
    def test_valid_agent_response(self) -> None:
        resp = AgentResponse(
            recommended_action="DIVERT_TO_VERTIPORT",
            justification="Battery below 18% reserve limit",
            confidence=0.92,
            policy_citations=["AeroGrid Fleet SOP Sec 4.2"],
        )
        self.assertEqual(resp.recommended_action, "DIVERT_TO_VERTIPORT")
        self.assertEqual(resp.confidence, 0.92)

    def test_invalid_confidence_bounds(self) -> None:
        with self.assertRaises(ValueError):
            AgentResponse(
                recommended_action="TEST_ACTION",
                justification="Testing invalid confidence",
                confidence=1.5,  # Exceeds 1.0 limit
            )


class TestDomainAgentsAndCoordination(unittest.TestCase):
    def setUp(self) -> None:
        self.fd, self.temp_db = tempfile.mkstemp(suffix=".db")
        os.close(self.fd)

    def tearDown(self) -> None:
        if os.path.exists(self.temp_db):
            os.remove(self.temp_db)
        for ext in ("-wal", "-shm"):
            wal_file = self.temp_db + ext
            if os.path.exists(wal_file):
                os.remove(wal_file)

    def test_tier1_aviation_safety_overrides_fleet(self) -> None:
        audit = AuditEngine(db_path=self.temp_db)
        retriever = PolicyRetriever()
        aviation = AviationAgent(retriever=retriever)
        telecom = TelecomAgent(retriever=retriever)
        fleet = FleetAgent(retriever=retriever)
        coordinator = CoordinationEngine(audit_engine=audit, retriever=retriever)

        # Simulation state: Manned helicopter proximity vs low battery
        state = {
            "drone_id": "TEST_UAS_01",
            "airspace_traffic": {
                "manned_traffic_detected": True,
                "hems_in_vicinity": True,
                "intruder_distance_m": 700,
            },
            "telecom_metrics": {
                "rtt_latency_ms": 40,
                "packet_loss_pct": 0.1,
                "link_lost": False,
            },
            "fleet_telemetry": {
                "battery_soc_pct": 21.0,
                "expedited_medical_payload": False,
            },
        }

        av_resp = aviation.evaluate_state(state)
        tc_resp = telecom.evaluate_state(state)
        fl_resp = fleet.evaluate_state(state)

        self.assertTrue("EMERGENCY" in av_resp.recommended_action or "EVACUATION" in av_resp.recommended_action)

        cmd = coordinator.resolve_conflict(
            aviation_resp=av_resp,
            telecom_resp=tc_resp,
            fleet_resp=fl_resp,
            state=state,
            target_drone_id="TEST_UAS_01",
        )

        self.assertEqual(cmd.selected_agent, "aviation_safety_agent")
        self.assertEqual(cmd.action, av_resp.recommended_action)
        self.assertTrue(cmd.conflict_detected)
        self.assertGreaterEqual(len(cmd.overruled_recommendations), 1)
        self.assertTrue(cmd.audit_event_id.startswith("evt_"))

        # Verify logs in DB
        logs = audit.get_all_logs()
        self.assertEqual(len(logs), 4)  # 3 agent logs + 1 coordination root log


if __name__ == "__main__":
    unittest.main()
