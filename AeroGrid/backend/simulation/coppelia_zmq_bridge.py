"""AeroGrid CoppeliaSim ZeroMQ Remote API Bridge.

Connects the Python Multi-Agent UTM architecture directly to CoppeliaSim
via the native ZeroMQ Remote API (port 23000).

Eliminates the need for manual Lua script editing or custom plugins inside
CoppeliaSim: preserves the Quadcopter's built-in PID rotor controller while
Python dynamically guides target waypoints and actuates UTM arbitration directives.
"""

from __future__ import annotations

import logging
import math
import os
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("aerogrid.coppelia_zmq")

# Try importing the native ZeroMQ remote API client
try:
    from coppeliasim_zmqremoteapi_client import RemoteAPIClient
    ZMQ_AVAILABLE = True
except ImportError:
    try:
        from backend.coppeliasim_zmqremoteapi_client import RemoteAPIClient  # type: ignore
        ZMQ_AVAILABLE = True
    except ImportError:
        ZMQ_AVAILABLE = False


class CoppeliaZMQBridge:
    """Cyber-physical bridge communicating with CoppeliaSim via ZeroMQ."""

    def __init__(self, host: str = "127.0.0.1", port: int = 23000):
        self.host = host
        self.port = port
        self.client: Optional[Any] = None
        self.sim: Optional[Any] = None
        self.is_connected: bool = False

        # Scene object handles
        self.quadcopter_handle: int = -1
        self.target_handle: int = -1
        self.base_altitude: float = 2.0
        self.current_target_pos: list[float] = [0.0, 0.0, 2.0]
        self.goal_target_pos: list[float] = [0.0, 0.0, 2.0]

        # Telemetry cache
        self.last_telemetry: Dict[str, Any] = {
            "connected": False,
            "sim_time": 0.0,
            "x": 0.0,
            "y": 0.0,
            "z": 2.0,
            "vx": 0.0,
            "vy": 0.0,
            "vz": 0.0,
            "battery_soc": 21.5,
            "c2_rtt_ms": 42.0,
            "packet_loss_pct": 0.10,
            "status": "DISCONNECTED",
        }

    def connect(self) -> bool:
        """Attempt to connect to CoppeliaSim ZeroMQ server."""
        if not ZMQ_AVAILABLE:
            logger.warning("[CoppeliaZMQ] coppeliasim_zmqremoteapi_client not installed.")
            return False

        import socket
        # 1. Non-blocking TCP pre-check
        try:
            with socket.create_connection((self.host, self.port), timeout=0.25):
                pass
        except (socket.timeout, ConnectionRefusedError, OSError):
            self.is_connected = False
            self.sim = None
            self.client = None
            return False

        # 2. Connect ZeroMQ client with strict timeouts
        try:
            self.client = RemoteAPIClient(host=self.host, port=self.port)
            if hasattr(self.client, "socket") and self.client.socket:
                import zmq
                self.client.socket.setsockopt(zmq.RCVTIMEO, 1000)
                self.client.socket.setsockopt(zmq.SNDTIMEO, 1000)

            self.sim = self.client.require("sim")
            sim_time = self.sim.getSimulationTime()
            self.is_connected = True
            logger.info("[CoppeliaZMQ] Successfully connected to CoppeliaSim ZMQ server at %s:%d (Sim time: %.2fs)", self.host, self.port, sim_time)
            self._resolve_scene_objects()
            return True
        except Exception as e:
            self.is_connected = False
            self.sim = None
            self.client = None
            logger.info("[CoppeliaZMQ] ZeroMQ handshake failed on %s:%d: %s", self.host, self.port, e)
            return False

    def _resolve_scene_objects(self) -> None:
        """Locate Quadcopter and target dummy handles in active CoppeliaSim scene."""
        if not self.sim:
            return

        # 1. Search for Quadcopter body handle
        quad_candidates = [
            "/Quadcopter",
            "/Quadcopter[0]",
            ":Quadcopter",
            "Quadcopter",
            "/Quadricopter",
        ]
        for cand in quad_candidates:
            try:
                handle = self.sim.getObject(cand, {"noError": True})
                if handle and handle != -1:
                    self.quadcopter_handle = handle
                    logger.info("[CoppeliaZMQ] Located Quadcopter body '%s' (Handle: %d)", cand, handle)
                    break
            except Exception:
                continue

        # 2. Search for target dummy handle
        target_candidates = [
            "/Quadcopter/target",
            "/Quadcopter[0]/target",
            "/Quadcopter_target",
            "/target",
            ":target",
            "Quadcopter_target",
            "target",
        ]
        for cand in target_candidates:
            try:
                handle = self.sim.getObject(cand, {"noError": True})
                if handle and handle != -1:
                    self.target_handle = handle
                    pos = self.sim.getObjectPosition(self.target_handle, -1)
                    self.current_target_pos = list(pos)
                    self.goal_target_pos = list(pos)
                    logger.info("[CoppeliaZMQ] Located target dummy '%s' (Handle: %d, Pos: %s)", cand, handle, pos)
                    break
            except Exception:
                continue

    def start_simulation(self) -> bool:
        """Start or resume CoppeliaSim simulation."""
        if not self.is_connected or not self.sim:
            return False
        try:
            self.sim.startSimulation()
            logger.info("[CoppeliaZMQ] CoppeliaSim simulation started.")
            return True
        except Exception as e:
            logger.error("[CoppeliaZMQ] Error starting simulation: %s", e)
            return False

    def stop_simulation(self) -> bool:
        """Stop CoppeliaSim simulation."""
        if not self.is_connected or not self.sim:
            return False
        try:
            self.sim.stopSimulation()
            logger.info("[CoppeliaZMQ] CoppeliaSim simulation stopped.")
            return True
        except Exception as e:
            logger.error("[CoppeliaZMQ] Error stopping simulation: %s", e)
            return False

    def _step_smooth_trajectory(self) -> None:
        """Smoothly step target dummy position towards goal coordinates."""
        if not self.is_connected or not self.sim or self.target_handle == -1:
            return

        need_update = False
        # Smooth interpolation step (max 0.10m per 100ms cycle = ~1.0 m/s gentle descent/ascent)
        for i in range(3):
            diff = self.goal_target_pos[i] - self.current_target_pos[i]
            if abs(diff) > 0.005:
                step = math.copysign(min(abs(diff), 0.08), diff)
                self.current_target_pos[i] += step
                need_update = True

        if need_update:
            try:
                self.sim.setObjectPosition(self.target_handle, -1, self.current_target_pos)
            except Exception as e:
                logger.debug("[CoppeliaZMQ] Error updating smooth position: %s", e)

    def read_telemetry(self) -> Dict[str, Any]:
        """Poll current telemetry from CoppeliaSim or generate simulated telemetry."""
        if self.is_connected and self.sim:
            try:
                self._step_smooth_trajectory()
                sim_time = self.sim.getSimulationTime()
                if self.quadcopter_handle != -1:
                    pos = self.sim.getObjectPosition(self.quadcopter_handle, -1)
                    vel, _ = self.sim.getObjectVelocity(self.quadcopter_handle)
                elif self.target_handle != -1:
                    pos = self.sim.getObjectPosition(self.target_handle, -1)
                    vel = [0.0, 0.0, 0.0]
                else:
                    self._resolve_scene_objects()
                    pos = self.current_target_pos
                    vel = [0.0, 0.0, 0.0]

                self.last_telemetry.update({
                    "connected": True,
                    "sim_time": round(sim_time, 2),
                    "x": round(pos[0], 2),
                    "y": round(pos[1], 2),
                    "z": round(pos[2], 2),
                    "vx": round(vel[0], 2),
                    "vy": round(vel[1], 2),
                    "vz": round(vel[2], 2),
                    "status": "COPPELIASIM_ACTIVE",
                })
                return self.last_telemetry
            except Exception as e:
                logger.warning("[CoppeliaZMQ] Telemetry poll failed: %s", e)
                self.is_connected = False

        # Fallback simulated telemetry
        t = time.time()
        self.last_telemetry.update({
            "connected": False,
            "sim_time": round(t % 3600, 2),
            "status": "MOCK_SIMULATION_READY",
        })
        return self.last_telemetry

    def set_target_altitude(self, target_z: float) -> bool:
        """Set Quadcopter goal altitude in CoppeliaSim (smooth trajectory)."""
        self.goal_target_pos[2] = max(0.05, float(target_z))
        logger.info("[CoppeliaZMQ] Setting goal altitude setpoint to %.2fm (Smooth glide)", self.goal_target_pos[2])
        return True

    def set_target_position(self, x: float, y: float, z: float) -> bool:
        """Set full 3D goal coordinates in CoppeliaSim (smooth trajectory)."""
        self.goal_target_pos = [float(x), float(y), max(0.05, float(z))]
        logger.info("[CoppeliaZMQ] Setting goal 3D setpoint to %s (Smooth glide)", self.goal_target_pos)
        return True

    def execute_utm_action(self, action: str, target_drone_id: str = "UAS_CARGO_DXB_104") -> Dict[str, Any]:
        """Actuate a UTM Coordination Engine directive via ZeroMQ."""
        action = action.strip().upper()
        result = {
            "action": action,
            "drone_id": target_drone_id,
            "target_z": self.current_target_pos[2],
            "description": "",
            "actuated": False,
        }

        # Case 1: Tier 1 Manned Right-of-Way Emergency Evacuation
        if "EMERGENCY_DESCENT" in action or "EVACUATION" in action:
            new_z = 0.05  # Ground landing level
            # Land directly down at current lateral position
            self.set_target_position(self.goal_target_pos[0], self.goal_target_pos[1], new_z)
            result.update({
                "target_z": new_z,
                "description": "EMERGENCY EVACUATION: Target lowered to ground (0.05m). Clearing airspace for HEMS.",
                "actuated": True,
            })
            logger.warning("[CoppeliaZMQ] >>> ACTUATING: EMERGENCY EVACUATION (Target Z = 0.05m) <<<")

        # Case 2: Tier 2 Urban Canyon 5G Shadowing / C2 Handover
        elif "DESCEND_30M" in action or "5G_CELL_HANDOVER" in action:
            new_z = 1.50  # Lower altitude envelope to regain 5G gNodeB LOS
            self.set_target_position(0.0, 0.0, new_z)
            result.update({
                "target_z": new_z,
                "description": f"5G HANDOVER: Lowering flight altitude by 0.5m to {new_z:.2f}m for gNodeB line-of-sight.",
                "actuated": True,
            })
            logger.info("[CoppeliaZMQ] >>> ACTUATING: 5G HANDOVER (Target Z = %.2fm) <<<", new_z)

        # Case 3: Tier 3 Critical Battery Diversion
        elif "DIVERT" in action or "VERTIPORT" in action:
            # Navigate towards Vertiport 1 coordinates (-2.0, 1.5, 0.8)
            self.set_target_position(-2.0, 1.5, 0.8)
            result.update({
                "target_z": 0.8,
                "description": "BATTERY DIVERT: Rerouting flight path towards Vertiport Pad 1 (-2.0, 1.5, 0.8m).",
                "actuated": True,
            })
            logger.info("[CoppeliaZMQ] >>> ACTUATING: VERTIPORT DIVERT (Pos: -2.0, 1.5, 0.8) <<<")

        # Case 4: Nominal Corridor Cruise (Reset to center at 2.0m)
        else:
            self.set_target_position(0.0, 0.0, 2.0)
            result.update({
                "target_z": 2.0,
                "description": "NOMINAL CRUISE: Maintaining assigned BVLOS corridor center at 2.0m (X:0, Y:0).",
                "actuated": True,
            })
            logger.info("[CoppeliaZMQ] >>> ACTUATING: NOMINAL CRUISE (Pos: 0.0, 0.0, 2.0) <<<")

        return result
