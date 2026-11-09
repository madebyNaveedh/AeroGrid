"""AeroGrid UTM - CoppeliaSim Python Controller.

Implements the drone flight control loop in CoppeliaSim using the Python API or
standalone ROS 2 node communicating with CoppeliaSim via ZeroMQ / simROS2.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aerogrid.coppeliasim")


class CoppeliaSimDroneController:
    """Manages CoppeliaSim drone kinematics in response to AeroGrid UTM operational commands."""

    def __init__(self, drone_id: str = "UAS_CARGO_DXB_104") -> None:
        self.drone_id = drone_id
        self.current_altitude = 120.0
        self.target_altitude = 120.0
        self.battery_soc = 85.0
        self.is_diverting = False
        self.is_holding = False
        logger.info("CoppeliaSim Drone Controller initialized for %s", self.drone_id)

    def handle_utm_command(self, raw_json_payload: str) -> Dict[str, Any]:
        """Parse incoming JSON payload from /aerogrid/utm_commands and execute maneuver."""
        try:
            cmd = json.loads(raw_json_payload)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse UTM command payload: %s", exc)
            return {"status": "error", "message": "invalid_json"}

        target_drone = cmd.get("target_drone_id")
        if target_drone != self.drone_id and target_drone != "ALL":
            # Command intended for another UAS instance
            return {"status": "ignored", "target": target_drone}

        action = cmd.get("recommended_action", "")
        event_id = cmd.get("event_id", "")
        confidence = cmd.get("confidence_score", 0.0)

        logger.info(
            ">>> [CoppeliaSim] Executing Command for %s: %s (Event: %s, Conf: %.2f)",
            self.drone_id, action, event_id, confidence
        )

        # Actuation logic
        if action == "EMERGENCY_DESCENT_AND_CORRIDOR_EVACUATION":
            self.target_altitude = max(15.0, self.current_altitude - 40.0)
            logger.warning("Corridor evacuation initiated: descending to %.1fm", self.target_altitude)

        elif action == "DESCEND_30M_AND_INITIATE_5G_CELL_HANDOVER":
            self.target_altitude = max(20.0, self.current_altitude - 30.0)
            logger.info("Cellular line-of-sight recovery: descending to %.1fm", self.target_altitude)

        elif action == "EMERGENCY_DIVERT_TO_NEAREST_VERTIPORT":
            self.is_diverting = True
            logger.warning("Emergency diversion vector engaged toward alternate vertiport.")

        elif action == "TRIGGER_C2_FAILSAFE_HOVER_HOLD":
            self.is_holding = True
            logger.warning("C2 link failsafe active: holding position.")

        elif action in ("MAINTAIN_ASSIGNED_AIRSPACE_CORRIDOR", "CONTINUE_PLANNED_ECONOMIC_FLIGHT_PLAN"):
            logger.info("Nominal flight profile maintained.")

        return {
            "status": "executed",
            "drone_id": self.drone_id,
            "action": action,
            "target_altitude": self.target_altitude,
        }

    def generate_telemetry_snapshot(self) -> Dict[str, Any]:
        """Construct standard telemetry packet for /aerogrid/drone_telemetry."""
        # Kinematic update step
        if abs(self.current_altitude - self.target_altitude) > 0.5:
            step = (self.target_altitude - self.current_altitude) * 0.15
            self.current_altitude += step

        self.battery_soc = max(0.0, self.battery_soc - 0.01)

        return {
            "drone_id": self.drone_id,
            "altitude_m": round(self.current_altitude, 2),
            "ground_speed_mps": 22.0,
            "telecom_metrics": {
                "rtt_latency_ms": 42.0,
                "packet_loss_pct": 0.15,
                "link_lost": False,
            },
            "fleet_telemetry": {
                "battery_soc_pct": round(self.battery_soc, 1),
                "is_diverting": self.is_diverting,
            },
        }

