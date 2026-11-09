#!/usr/bin/env python3
"""AeroGrid ROS 2 Telemetry Bridge Node: telemetry_bridge_node.

Subscribes to `/aerogrid/drone_telemetry` from CoppeliaSim or real drone GCS,
passes the telemetry to AeroGrid multi-agent evaluation (Aviation, Telecom, Fleet),
arbitrates conflicts via the CoordinationEngine, and commits immutable decision
records to the SQLite WAL database.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Add AeroGrid backend to Python search path
AEROGRID_ROOT = Path(__file__).resolve().parents[4]
if str(AEROGRID_ROOT) not in sys.path:
    sys.path.insert(0, str(AEROGRID_ROOT))

from backend.config import settings
from backend.audit.logger import AuditEngine
from backend.knowledge_base.retrieval import PolicyRetriever
from backend.agents.aviation_agent import AviationAgent
from backend.agents.telecom_agent import TelecomAgent
from backend.agents.fleet_agent import FleetAgent
from backend.agents.coordination_agent import CoordinationEngine

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from std_msgs.msg import String
    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False
    Node = object  # type: ignore[misc,assignment]


class TelemetryBridgeNode(Node):  # type: ignore[misc]
    """ROS 2 Node ingesting drone telemetry and running multi-agent arbitration."""

    def __init__(self) -> None:
        if not HAS_RCLPY:
            raise ImportError("rclpy is not installed. Please source ROS 2 Humble.")

        super().__init__("telemetry_bridge_node")

        # Configurable ROS Parameters
        self.declare_parameter("telemetry_topic", "/aerogrid/drone_telemetry")
        self.declare_parameter("db_path", "")

        telemetry_topic = self.get_parameter("telemetry_topic").get_parameter_value().string_value
        configured_db = self.get_parameter("db_path").get_parameter_value().string_value
        db_path = configured_db or str(AEROGRID_ROOT / "backend" / "audit" / "aerogrid_audit.db")

        # Initialize AeroGrid Multi-Agent Engine Singletons
        self.audit_engine = AuditEngine(db_path=db_path)
        self.retriever = PolicyRetriever()
        self.aviation_agent = AviationAgent(retriever=self.retriever)
        self.telecom_agent = TelecomAgent(retriever=self.retriever)
        self.fleet_agent = FleetAgent(retriever=self.retriever)
        self.coordinator = CoordinationEngine(
            audit_engine=self.audit_engine,
            retriever=self.retriever,
        )

        # Configure ROS 2 Subscription
        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self._subscription = self.create_subscription(
            String,
            telemetry_topic,
            self._telemetry_callback,
            qos_profile,
        )

        self.get_logger().info("=" * 70)
        self.get_logger().info("  AEROGRID TELEMETRY INGESTION BRIDGE ACTIVE")
        self.get_logger().info(f"  * Node Name:         {self.get_name()}")
        self.get_logger().info(f"  * Subscribed Topic:  {telemetry_topic}")
        self.get_logger().info(f"  * SQLite WAL Audit:  {self.audit_engine.db_path}")
        self.get_logger().info("=" * 70)

    def _telemetry_callback(self, msg: String) -> None:
        """Receive drone telemetry, run agents, arbitrate conflict, and commit to WAL."""
        try:
            telemetry_data = json.loads(msg.data)
        except json.JSONDecodeError as exc:
            self.get_logger().error(f"Failed to parse telemetry JSON: {exc}")
            return

        drone_id = telemetry_data.get("drone_id", "UAS_UNKNOWN")

        # Construct canonical simulation state
        state: Dict[str, Any] = {
            "drone_id": drone_id,
            "timestamp": telemetry_data.get("timestamp"),
            "altitude_m": telemetry_data.get("altitude_m", 120.0),
            "ground_speed_mps": telemetry_data.get("ground_speed_mps", 20.0),
            "airspace_traffic": telemetry_data.get("airspace_traffic", {}),
            "telecom_metrics": telemetry_data.get("telecom_metrics", {}),
            "fleet_telemetry": telemetry_data.get("fleet_telemetry", {}),
        }

        # Step 1: Multi-Agent Evaluation
        av_resp = self.aviation_agent.evaluate_state(state)
        tc_resp = self.telecom_agent.evaluate_state(state)
        fl_resp = self.fleet_agent.evaluate_state(state)

        # Step 2: Conflict Arbitration & SQLite WAL Commit
        cmd = self.coordinator.resolve_conflict(
            aviation_resp=av_resp,
            telecom_resp=tc_resp,
            fleet_resp=fl_resp,
            state=state,
            target_drone_id=drone_id,
        )

        self.get_logger().info(
            f"[CLOSED-LOOP DECISION] Drone: {drone_id} -> Action: {cmd.action} "
            f"(Conf: {cmd.confidence_score:.2f}, Deciding Agent: {cmd.selected_agent}, Event: {cmd.audit_event_id})"
        )


def main(args: Optional[list] = None) -> None:
    if not HAS_RCLPY:
        print("[ERROR] rclpy is required. Please source ROS 2 Humble first.")
        return

    rclpy.init(args=args)
    node = TelemetryBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Shutting down telemetry bridge...")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

