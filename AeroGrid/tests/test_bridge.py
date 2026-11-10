"""Unit tests for the AeroGrid ROS 2 Bridge database logic.

Validates that polling, event de-duplication, and JSON payload formatting
function properly against SQLite WAL audit records.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest

from backend.audit.logger import AuditEngine


class TestBridgeDatabaseLogic(unittest.TestCase):
    def setUp(self) -> None:
        self.fd, self.temp_db = tempfile.mkstemp(suffix=".db")
        os.close(self.fd)
        self.audit = AuditEngine(db_path=self.temp_db)

    def tearDown(self) -> None:
        if os.path.exists(self.temp_db):
            os.remove(self.temp_db)
        for ext in ("-wal", "-shm"):
            wal_file = self.temp_db + ext
            if os.path.exists(wal_file):
                os.remove(wal_file)

    def _query_latest_command(self, conn: sqlite3.Connection):
        query = """
        SELECT
            event_id,
            agent_id,
            context_hash,
            recommended_action,
            decision_justification,
            confidence_score,
            timestamp,
            target_drone_id
        FROM audit_logs
        WHERE agent_id = 'coordination_engine'
        ORDER BY rowid DESC
        LIMIT 1;
        """
        cursor = conn.execute(query)
        return cursor.fetchone()

    def test_database_polling_and_deduplication(self) -> None:
        # Step 1: Insert an initial command
        evt1 = self.audit.insert_log(
            agent_id="coordination_engine",
            context_hash="hash_001",
            recommended_action="DESCEND_30M",
            decision_justification="Urban canyon C2 restoration",
            retrieved_policy_sources=["TDRA-UAS-C2-2023"],
            confidence_score=0.90,
            target_drone_id="UAS_AUH_101",
        )

        with sqlite3.connect(self.temp_db) as conn:
            conn.row_factory = sqlite3.Row
            row = self._query_latest_command(conn)
            self.assertIsNotNone(row)
            self.assertEqual(row["event_id"], evt1)
            self.assertEqual(row["target_drone_id"], "UAS_AUH_101")
            self.assertEqual(row["recommended_action"], "DESCEND_30M")

            # Emulate node state tracking
            last_event_id = row["event_id"]

            # Query again without new inserts -> should de-duplicate
            row_again = self._query_latest_command(conn)
            self.assertEqual(row_again["event_id"], last_event_id)
            is_new = row_again["event_id"] != last_event_id
            self.assertFalse(is_new, "Should not treat same event as new command")

        # Step 2: Insert a second command
        evt2 = self.audit.insert_log(
            agent_id="coordination_engine",
            context_hash="hash_002",
            recommended_action="EMERGENCY_DIVERT",
            decision_justification="Critically low battery",
            retrieved_policy_sources=["AEROGRID-FLEET-SOP-42"],
            confidence_score=0.96,
            target_drone_id="UAS_DXB_202",
        )

        with sqlite3.connect(self.temp_db) as conn:
            conn.row_factory = sqlite3.Row
            row_new = self._query_latest_command(conn)
            self.assertIsNotNone(row_new)
            self.assertEqual(row_new["event_id"], evt2)
            is_new = row_new["event_id"] != last_event_id
            self.assertTrue(is_new, "Should detect new event ID")

            # Validate formatting of payload
            payload = {
                "event_id": row_new["event_id"],
                "target_drone_id": row_new["target_drone_id"],
                "recommended_action": row_new["recommended_action"],
                "decision_justification": row_new["decision_justification"],
                "confidence_score": float(row_new["confidence_score"]),
                "timestamp": row_new["timestamp"],
            }
            json_payload = json.dumps(payload)
            parsed = json.loads(json_payload)
            self.assertEqual(parsed["target_drone_id"], "UAS_DXB_202")
            self.assertEqual(parsed["recommended_action"], "EMERGENCY_DIVERT")


class TestCoppeliaZMQBridge(unittest.TestCase):
    """Validates multi-drone fleet coordination, realistic aerodynamic velocity limiting, and telemetry."""

    def setUp(self) -> None:
        from backend.simulation.coppelia_zmq_bridge import CoppeliaZMQBridge
        self.bridge = CoppeliaZMQBridge()

    def test_bridge_fleet_initialization(self) -> None:
        """Verify both Drone 1 and Drone 2 are properly initialized."""
        self.assertIn("drone1_telemetry", self.bridge.__dict__)
        self.assertIn("drone2_telemetry", self.bridge.__dict__)
        self.assertEqual(self.bridge.drone1_telemetry["id"], "UAS_CARGO_DXB_104")
        self.assertEqual(self.bridge.goal_target_pos, [0.0, 0.0, 2.0])
        self.assertEqual(self.bridge.goal_target2_pos, [1.2, 0.6, 2.4])

    def test_realistic_velocity_limiting(self) -> None:
        """Verify vertical and horizontal steps never exceed aerodynamic speed bounds."""
        self.bridge.current_target_pos = [0.0, 0.0, 2.0]
        self.bridge.goal_target_pos = [0.0, 0.0, 0.05]

        self.bridge._step_smooth_trajectory()

        # In a single step, change in Z should be at most 0.06m
        actual_step = 2.0 - self.bridge.current_target_pos[2]
        self.assertLessEqual(actual_step, 0.061)
        self.assertGreater(self.bridge.current_target_pos[2], 1.90, "Drone must NOT jump directly to 0.05m")

    def test_multi_drone_scenario_actuation(self) -> None:
        """Verify all 4 scenario directives properly command both drones."""
        # 1. Scenario 1: HEMS Manned Incursion
        res1 = self.bridge.execute_utm_action("EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION")
        self.assertTrue(res1["actuated"])
        self.assertEqual(self.bridge.goal_target_pos, [0.0, 0.0, 0.05])
        self.assertEqual(self.bridge.goal_target2_pos, [-1.0, -0.6, 2.80])
        self.assertEqual(self.bridge.drone2_telemetry["id"], "HEMS_AIR_AMBULANCE")

        # 2. Scenario 2: 5G Shadowing Handover
        res2 = self.bridge.execute_utm_action("DESCEND_30M_AND_INITIATE_5G_CELL_HANDOVER")
        self.assertTrue(res2["actuated"])
        self.assertEqual(self.bridge.goal_target_pos, [0.0, 0.0, 1.50])
        self.assertEqual(self.bridge.goal_target2_pos, [1.2, 0.6, 2.40])

        # 3. Scenario 3: Battery Divert
        res3 = self.bridge.execute_utm_action("EMERGENCY_DIVERT_TO_NEAREST_VERTIPORT")
        self.assertTrue(res3["actuated"])
        self.assertEqual(self.bridge.goal_target_pos, [-1.2, 0.8, 0.80])
        self.assertEqual(self.bridge.goal_target2_pos, [0.6, -0.4, 2.20])

        # 4. Scenario 0: Nominal Cruise Reset
        res0 = self.bridge.execute_utm_action("MAINTAIN_ASSIGNED_AIRSPACE_CORRIDOR")
        self.assertTrue(res0["actuated"])
        self.assertEqual(self.bridge.goal_target_pos, [0.0, 0.0, 2.00])
        self.assertEqual(self.bridge.goal_target2_pos, [1.2, 0.6, 2.40])

    def test_telemetry_payload_fleet_structure(self) -> None:
        """Verify read_telemetry returns full multi-drone fleet telemetry."""
        telem = self.bridge.read_telemetry()
        self.assertIn("drone1", telem)
        self.assertIn("drone2", telem)
        self.assertIn("x", telem["drone1"])
        self.assertIn("z", telem["drone1"])
        self.assertIn("battery_soc", telem["drone1"])
        self.assertIn("x", telem["drone2"])
        self.assertIn("z", telem["drone2"])
        self.assertEqual(telem["drone1"]["id"], "UAS_CARGO_DXB_104")

    def test_telemetry_payload_fleet_structure(self) -> None:
        """Verify read_telemetry returns full multi-drone fleet telemetry."""
        telem = self.bridge.read_telemetry()
        self.assertIn("drone1", telem)
        self.assertIn("drone2", telem)
        self.assertIn("x", telem["drone1"])
        self.assertIn("z", telem["drone1"])
        self.assertIn("battery_soc", telem["drone1"])
        self.assertIn("x", telem["drone2"])
        self.assertIn("z", telem["drone2"])
        self.assertEqual(telem["drone1"]["id"], "UAS_CARGO_DXB_104")


if __name__ == "__main__":
    unittest.main()

