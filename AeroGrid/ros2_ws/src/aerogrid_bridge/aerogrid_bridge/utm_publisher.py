#!/usr/bin/env python3
"""AeroGrid ROS 2 Bridge Node: utm_bridge_node.

Polls the SQLite WAL audit database for new coordination decisions from the
AeroGrid UTM backend at 2 Hz and publishes JSON-serialized operational commands
to the ROS 2 topic `/aerogrid/utm_commands` for consumption by CoppeliaSim 3D.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, Optional

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from std_msgs.msg import String
    HAS_RCLPY = True
except ImportError:
    # Fallback placeholder for non-ROS environments during linting / offline testing
    HAS_RCLPY = False
    Node = object  # type: ignore[misc,assignment]


class UTMBridgeNode(Node):  # type: ignore[misc]
    """ROS 2 Node bridging SQLite WAL audit logs to CoppeliaSim via /aerogrid/utm_commands."""

    def __init__(self) -> None:
        if not HAS_RCLPY:
            raise ImportError(
                "rclpy or std_msgs is not available. Please source your ROS 2 environment: "
                "source /opt/ros/humble/setup.bash"
            )

        super().__init__("utm_bridge_node")

        # Declare configurable parameters
        self.declare_parameter("db_path", "")
        self.declare_parameter("poll_frequency", 2.0)  # 2 Hz
        self.declare_parameter("topic_name", "/aerogrid/utm_commands")

        # Resolve SQLite DB Path
        configured_db = self.get_parameter("db_path").get_parameter_value().string_value
        self.db_path = self._resolve_db_path(configured_db)
        self.topic_name = self.get_parameter("topic_name").get_parameter_value().string_value
        poll_freq = self.get_parameter("poll_frequency").get_parameter_value().double_value

        # In-memory tracking of the latest processed event ID to prevent topic spamming
        self._last_event_id: Optional[str] = None

        # Configure ROS 2 Publisher with Reliable QoS
        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self._publisher = self.create_publisher(String, self.topic_name, qos_profile)

        # Create 2 Hz polling timer (0.5s period)
        timer_period = 1.0 / poll_freq if poll_freq > 0 else 0.5
        self._timer = self.create_timer(timer_period, self._poll_database_callback)

        self.get_logger().info("=" * 70)
        self.get_logger().info("  AEROGRID ROS 2 BRIDGE (HUMBLE) INITIALIZED")
        self.get_logger().info(f"  * Node Name:       {self.get_name()}")
        self.get_logger().info(f"  * Published Topic: {self.topic_name} (std_msgs/String)")
        self.get_logger().info(f"  * Polling Rate:    {poll_freq:.1f} Hz")
        self.get_logger().info(f"  * SQLite WAL DB:   {self.db_path}")
        self.get_logger().info("=" * 70)

    def _resolve_db_path(self, explicit_path: str) -> str:
        """Resolve database path with fallback checks across common repository layouts."""
        if explicit_path and Path(explicit_path).is_file():
            return str(Path(explicit_path).resolve())

        # Candidate relative paths from ros2_ws or project root
        candidates = [
            # Explicit if provided
            Path(explicit_path) if explicit_path else None,
            # Current working directory / backend / audit
            Path.cwd() / "backend" / "audit" / "aerogrid_audit.db",
            Path.cwd() / "AeroGrid" / "backend" / "audit" / "aerogrid_audit.db",
            # Relative to this script: ros2_ws/src/aerogrid_bridge/aerogrid_bridge/../../../../backend/audit
            Path(__file__).resolve().parents[4] / "backend" / "audit" / "aerogrid_audit.db",
            # Standard absolute project path
            Path("/home/mohammed/AIforGood/AeroGrid/backend/audit/aerogrid_audit.db"),
        ]

        for p in candidates:
            if p and p.is_file():
                return str(p.resolve())

        # Fallback to default expected path
        default_path = Path.cwd() / "backend" / "audit" / "aerogrid_audit.db"
        return str(default_path.resolve())

    def _get_db_connection(self) -> Optional[sqlite3.Connection]:
        """Open a read-only SQLite connection configured for concurrent WAL reading."""
        if not os.path.exists(self.db_path):
            self.get_logger().warn(
                f"SQLite database file not found at '{self.db_path}'. Waiting for AeroGrid backend to create it...",
                throttle_duration_sec=5.0,
            )
            return None

        try:
            # Open with URI read-only flag to avoid locking writers in WAL mode
            conn = sqlite3.connect(
                f"file:{self.db_path}?mode=ro",
                uri=True,
                timeout=5.0,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute("PRAGMA query_only = ON;")
            return conn
        except sqlite3.Error as exc:
            self.get_logger().error(f"Failed to connect to SQLite database: {exc}")
            return None

    def _poll_database_callback(self) -> None:
        """Poll audit_logs for new coordination_engine operational commands at 2 Hz."""
        conn = self._get_db_connection()
        if conn is None:
            return

        try:
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
            row = cursor.fetchone()

            if row is None:
                # No coordination commands recorded yet
                return

            event_id = row["event_id"]

            # Only publish if this is a brand new command (in-memory de-duplication)
            if event_id == self._last_event_id:
                return

            # Update in-memory state
            self._last_event_id = event_id

            # Extract fields per specification
            recommended_action = row["recommended_action"]
            decision_justification = row["decision_justification"]

            # Handle target_drone_id (from column or default fallback)
            target_drone_id = (
                row["target_drone_id"]
                if "target_drone_id" in row.keys() and row["target_drone_id"]
                else "UAS_DEFAULT_01"
            )

            # Construct structured JSON payload for CoppeliaSim
            payload: Dict[str, Any] = {
                "event_id": event_id,
                "target_drone_id": target_drone_id,
                "recommended_action": recommended_action,
                "decision_justification": decision_justification,
                "confidence_score": float(row["confidence_score"]),
                "timestamp": row["timestamp"],
                "context_hash": row["context_hash"],
            }

            json_str = json.dumps(payload, indent=2)

            # Publish to ROS 2 topic
            msg = String()
            msg.data = json.dumps(payload)  # Compact wire payload
            self._publisher.publish(msg)

            # Heavy logging per specification
            self.get_logger().info(
                f"\n>>> [ROS 2 BRIDGE] Published Operational Command to {self.topic_name} <<<\n"
                f"  * Event ID:        {event_id}\n"
                f"  * Target Drone:    {target_drone_id}\n"
                f"  * Action:          {recommended_action}\n"
                f"  * Confidence:      {row['confidence_score']:.2f}\n"
                f"  * Full JSON Payload Transmitted:\n{json_str}\n"
                f"{'-' * 70}"
            )

        except sqlite3.Error as exc:
            self.get_logger().error(f"Error querying SQLite database: {exc}")
        finally:
            conn.close()


def main(args: Optional[list] = None) -> None:
    """Entry point for utm_bridge_node."""
    if not HAS_RCLPY:
        print("[ERROR] rclpy is required to run the ROS 2 node.")
        print("Please source ROS 2 Humble first: source /opt/ros/humble/setup.bash")
        return

    rclpy.init(args=args)
    node = UTMBridgeNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("UTM Bridge Node interrupted by user. Shutting down...")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

