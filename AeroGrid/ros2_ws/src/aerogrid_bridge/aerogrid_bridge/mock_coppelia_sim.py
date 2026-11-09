#!/usr/bin/env python3
"""AeroGrid Mock CoppeliaSim Simulator Node.

Simulates a 3D CoppeliaSim Quadcopter operating in Dubai/Abu Dhabi airspace:
1. Publishes realistic drone telemetry to `/aerogrid/drone_telemetry` (1 Hz).
2. Cycles through the 3 ITU Hackathon operational scenarios:
   - Scenario 1: Approaching HEMS medical helicopter (Airspace Safety Conflict).
   - Scenario 2: High-rise urban canyon 5G shadowing (C2 QoS Degradation).
   - Scenario 3: Critical battery reserve depletion (<18% SoC).
3. Subscribes to `/aerogrid/utm_commands`, parses commands, and simulates
   the physical kinematic response (altitude adjustment, grounding, divert).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from std_msgs.msg import String
    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False
    Node = object  # type: ignore[misc,assignment]


class MockCoppeliaSimNode(Node):  # type: ignore[misc]
    """ROS 2 Node emulating the CoppeliaSim 3D drone interface."""

    def __init__(self) -> None:
        if not HAS_RCLPY:
            raise ImportError("rclpy is required. Please source ROS 2 Humble first.")

        super().__init__("mock_coppelia_sim_node")

        # Telemetry publisher to trigger AeroGrid multi-agent evaluation
        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self._telemetry_pub = self.create_publisher(String, "/aerogrid/drone_telemetry", qos_profile)

        # Command subscriber from AeroGrid utm_bridge_node
        self._command_sub = self.create_subscription(
            String,
            "/aerogrid/utm_commands",
            self._command_callback,
            qos_profile,
        )

        # Simulation state variables
        self.drone_id = "UAS_CARGO_DXB_104"
        self.current_altitude = 2.0  # Default initial target altitude per Phase 4
        self.current_scenario_idx = 0
        self.tick_count = 0

        # Define the 3 ITU Hackathon Scenarios
        self.scenarios = [
            {
                "name": "Scenario 1: Manned HEMS Medical Helicopter Incursion",
                "telemetry": {
                    "drone_id": "UAS_CARGO_DXB_104",
                    "altitude_m": 120.0,
                    "ground_speed_mps": 22.5,
                    "airspace_traffic": {
                        "manned_traffic_detected": True,
                        "hems_in_vicinity": True,
                        "intruder_distance_m": 820.0,
                        "closing_velocity_mps": 65.0,
                    },
                    "telecom_metrics": {
                        "rtt_latency_ms": 42.0,
                        "packet_loss_pct": 0.1,
                        "link_lost": False,
                    },
                    "fleet_telemetry": {
                        "battery_soc_pct": 21.5,
                        "cargo_type": "standard_parcel",
                    },
                },
            },
            {
                "name": "Scenario 2: Dense Urban Canyon 5G Shadowing Spike",
                "telemetry": {
                    "drone_id": "UAS_DELIVERY_AUH_209",
                    "altitude_m": 90.0,
                    "ground_speed_mps": 18.0,
                    "airspace_traffic": {
                        "manned_traffic_detected": False,
                        "intruder_distance_m": 4500.0,
                    },
                    "telecom_metrics": {
                        "rtt_latency_ms": 295.0,
                        "packet_loss_pct": 3.8,
                        "urban_canyon_shadowing": True,
                    },
                    "fleet_telemetry": {
                        "battery_soc_pct": 58.0,
                        "cargo_type": "high_value_retail",
                    },
                },
            },
            {
                "name": "Scenario 3: Critical Battery Depletion (<18% SoC)",
                "telemetry": {
                    "drone_id": "UAS_MED_SHJ_311",
                    "altitude_m": 105.0,
                    "ground_speed_mps": 20.0,
                    "airspace_traffic": {
                        "manned_traffic_detected": False,
                        "intruder_distance_m": 8000.0,
                    },
                    "telecom_metrics": {
                        "rtt_latency_ms": 38.0,
                        "packet_loss_pct": 0.05,
                    },
                    "fleet_telemetry": {
                        "battery_soc_pct": 16.2,
                        "expedited_medical_payload": True,
                    },
                },
            },
        ]

        # 1 Hz Telemetry Emission Timer
        self._timer = self.create_timer(4.0, self._publish_telemetry_tick)

        self.get_logger().info("=" * 70)
        self.get_logger().info("  MOCK COPPELIASIM QUADCOPTER SIMULATOR INITIALIZED")
        self.get_logger().info("  * Emulating CoppeliaSim Lua Child Script")
        self.get_logger().info("  * Emitting Telemetry to: /aerogrid/drone_telemetry")
        self.get_logger().info("  * Listening for Commands on: /aerogrid/utm_commands")
        self.get_logger().info("  * Initial Target Altitude: 2.0m")
        self.get_logger().info("=" * 70)

    def _publish_telemetry_tick(self) -> None:
        """Cycle through scenarios and emit simulated CoppeliaSim drone telemetry."""
        scenario = self.scenarios[self.current_scenario_idx]
        telemetry = scenario["telemetry"]

        msg = String()
        msg.data = json.dumps(telemetry)
        self._telemetry_pub.publish(msg)

        self.get_logger().info(
            f"\n[COPPELIASIM UPLINK -> ROS 2] Emitted Telemetry for {scenario['name']}\n"
            f"  * Drone ID:   {telemetry['drone_id']}\n"
            f"  * Altitude:   {telemetry['altitude_m']}m\n"
            f"  * Speed:      {telemetry['ground_speed_mps']} m/s\n"
            f"  * Battery:    {telemetry['fleet_telemetry']['battery_soc_pct']}%\n"
            f"  * C2 RTT:     {telemetry['telecom_metrics']['rtt_latency_ms']} ms"
        )

        # Advance to next scenario on subsequent ticks
        self.current_scenario_idx = (self.current_scenario_idx + 1) % len(self.scenarios)

    def _command_callback(self, msg: String) -> None:
        """Emulate CoppeliaSim Lua quadcopter_utm_controller.lua actuation."""
        payload = msg.data

        # String matching per Phase 4 requirements
        if "EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION" in payload:
            prev_alt = self.current_altitude
            self.current_altitude = 0.05
            self.get_logger().info(
                f"\n>>> [COPPELIASIM ACTUATION TRIGGERED] <<<\n"
                f"  * Directive: EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION\n"
                f"  * Action:    Grounding Quadcopter for HEMS airspace evacuation!\n"
                f"  * Altitude:  Target Z changed from {prev_alt:.2f}m to {self.current_altitude:.2f}m (Ground Level)\n"
                f"{'-' * 70}"
            )

        elif "DESCEND_30M_AND_INITIATE_5G_CELL_HANDOVER" in payload:
            prev_alt = self.current_altitude
            self.current_altitude = max(0.05, self.current_altitude - 0.5)
            self.get_logger().info(
                f"\n>>> [COPPELIASIM ACTUATION TRIGGERED] <<<\n"
                f"  * Directive: DESCEND_30M_AND_INITIATE_5G_CELL_HANDOVER\n"
                f"  * Action:    Dropping target Z by 0.5m to restore 5G gNodeB line-of-sight!\n"
                f"  * Altitude:  Target Z changed from {prev_alt:.2f}m to {self.current_altitude:.2f}m\n"
                f"{'-' * 70}"
            )

        elif "EMERGENCY_DIVERT_TO_NEAREST_VERTIPORT" in payload:
            self.get_logger().info(
                f"\n>>> [COPPELIASIM ACTUATION TRIGGERED] <<<\n"
                f"  * Directive: EMERGENCY_DIVERT_TO_NEAREST_VERTIPORT\n"
                f"  * Action:    Updating flight plan waypoint to nearest Vertiport Pad 1!\n"
                f"{'-' * 70}"
            )

        else:
            self.get_logger().info(
                f"[COPPELIASIM] Received Command: {payload[:80]}... No altitude override required."
            )


def main(args: Optional[list] = None) -> None:
    if not HAS_RCLPY:
        print("[ERROR] rclpy is required. Please source ROS 2 Humble first.")
        return

    rclpy.init(args=args)
    node = MockCoppeliaSimNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Shutting down mock CoppeliaSim node...")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

