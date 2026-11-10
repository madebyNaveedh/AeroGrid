"""AeroGrid CoppeliaSim ZeroMQ Remote API Bridge (Singleton).

Connects the Python Multi-Agent UTM architecture directly to CoppeliaSim
via the native ZeroMQ Remote API (port 23000).

Eliminates background thread contention by performing smooth, rate-limited
trajectory stepping synchronously during telemetry polling cycles.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

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
    """Authoritative Cyber-physical bridge communicating with CoppeliaSim via ZeroMQ."""

    def __init__(self, host: str = "127.0.0.1", port: int = 23000):
        self.host = host
        self.port = port
        self.client: Optional[Any] = None
        self.sim: Optional[Any] = None
        self.is_connected: bool = False
        self.lock = threading.Lock()
        self._last_reconnect_try = 0.0

        # Scene object handles
        self.quadcopter_handle: int = -1
        self.target_handle: int = -1
        self.quad2_handle: int = -1
        self.target2_handle: int = -1

        # Smooth setpoints for Drone 1 (Primary UAS)
        self.current_target_pos: List[float] = [0.0, 0.0, 2.0]
        self.goal_target_pos: List[float] = [0.0, 0.0, 2.0]

        # Smooth setpoints for Drone 2 (HEMS / Peer UAS)
        self.current_target2_pos: List[float] = [1.2, 0.6, 2.4]
        self.goal_target2_pos: List[float] = [1.2, 0.6, 2.4]

        # Fleet Telemetry Cache
        self.drone1_telemetry: Dict[str, Any] = {
            "id": "UAS_CARGO_DXB_104",
            "x": 0.0, "y": 0.0, "z": 2.0,
            "vx": 0.0, "vy": 0.0, "vz": 0.0,
            "target_z": 2.0,
            "battery_soc": 82.0,
            "status": "NOMINAL_CORRIDOR_CRUISE",
            "role": "Commercial Cargo UAS",
        }

        self.drone2_telemetry: Dict[str, Any] = {
            "id": "UAS_PEER_209",
            "x": 1.2, "y": 0.6, "z": 2.4,
            "vx": 0.0, "vy": 0.0, "vz": 0.0,
            "target_z": 2.4,
            "battery_soc": 95.0,
            "status": "HOLDING_SEPARATION",
            "role": "Commercial Fleet Peer",
        }

        self.last_telemetry: Dict[str, Any] = {
            "connected": False,
            "sim_time": 0.0,
            "x": 0.0, "y": 0.0, "z": 2.0,
            "vx": 0.0, "vy": 0.0, "vz": 0.0,
            "target_z": 2.0,
            "battery_soc": 82.0,
            "c2_rtt_ms": 35.0,
            "packet_loss_pct": 0.05,
            "status": "DISCONNECTED",
            "drone1": self.drone1_telemetry,
            "drone2": self.drone2_telemetry,
        }

    def connect(self) -> bool:
        """Attempt to connect to CoppeliaSim ZeroMQ server."""
        if not ZMQ_AVAILABLE:
            logger.warning("[CoppeliaZMQ] coppeliasim_zmqremoteapi_client not installed.")
            return False

        import socket
        try:
            with socket.create_connection((self.host, self.port), timeout=0.25):
                pass
        except (socket.timeout, ConnectionRefusedError, OSError):
            self.is_connected = False
            self.sim = None
            self.client = None
            return False

        try:
            self.client = RemoteAPIClient(host=self.host, port=self.port)
            if hasattr(self.client, "socket") and self.client.socket:
                import zmq
                self.client.socket.setsockopt(zmq.RCVTIMEO, 1000)
                self.client.socket.setsockopt(zmq.SNDTIMEO, 1000)

            self.sim = self.client.require("sim")
            sim_time = self.sim.getSimulationTime()
            self.is_connected = True
            logger.info("[CoppeliaZMQ] Connected to CoppeliaSim ZMQ server at %s:%d (Sim time: %.2fs)", self.host, self.port, sim_time)

            # Auto-start simulation if stopped
            sim_state = self.sim.getSimulationState()
            if sim_state == self.sim.simulation_stopped:
                self.sim.startSimulation()
                logger.info("[CoppeliaZMQ] Simulation automatically started.")

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

        try:
            objs = self.sim.getObjectsInTree(self.sim.handle_scene)
            quads: List[Tuple[int, str]] = []
            targets: List[Tuple[int, str]] = []

            for obj in objs:
                try:
                    alias = self.sim.getObjectAlias(obj)
                    alias_lower = alias.lower()
                    if "target" in alias_lower:
                        targets.append((obj, alias))
                    elif any(k in alias_lower for k in ["quadcopter", "quadricopter", "drone", "hems"]):
                        if any(s in alias_lower for s in ["propeller", "joint", "respondable", "shadow"]):
                            continue
                        quads.append((obj, alias))
                except Exception:
                    continue

            # Assign Drone 1
            if len(quads) >= 1:
                self.quadcopter_handle = quads[0][0]
                logger.info("[CoppeliaZMQ] Located Drone 1 Quadcopter '%s' (Handle: %d)", quads[0][1], quads[0][0])
            if len(targets) >= 1:
                self.target_handle = targets[0][0]
                pos = self.sim.getObjectPosition(self.target_handle, -1)
                self.current_target_pos = list(pos)
                logger.info("[CoppeliaZMQ] Located Drone 1 target '%s' (Handle: %d, Pos: %s)", targets[0][1], targets[0][0], pos)

            # Assign Drone 2 if present
            if len(quads) >= 2:
                self.quad2_handle = quads[1][0]
                logger.info("[CoppeliaZMQ] Located Drone 2 Quadcopter '%s' (Handle: %d)", quads[1][1], quads[1][0])
            if len(targets) >= 2:
                self.target2_handle = targets[1][0]
                pos2 = self.sim.getObjectPosition(self.target2_handle, -1)
                self.current_target2_pos = list(pos2)
                logger.info("[CoppeliaZMQ] Located Drone 2 target '%s' (Handle: %d, Pos: %s)", targets[1][1], targets[1][0], pos2)

        except Exception as e:
            logger.debug("[CoppeliaZMQ] Error resolving scene objects: %s", e)

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
        """Step target dummy positions towards goal coordinates smoothly (no instant teleportation)."""
        if not self.is_connected or not self.sim:
            # Step in simulation mode
            for i in range(3):
                diff1 = self.goal_target_pos[i] - self.current_target_pos[i]
                if abs(diff1) > 0.005:
                    step1 = math.copysign(min(abs(diff1), 0.06), diff1)
                    self.current_target_pos[i] += step1

                diff2 = self.goal_target2_pos[i] - self.current_target2_pos[i]
                if abs(diff2) > 0.005:
                    step2 = math.copysign(min(abs(diff2), 0.06), diff2)
                    self.current_target2_pos[i] += step2
            return

        # Drone 1 smooth step (max 0.06m per 100ms cycle = ~0.6 m/s calm, realistic flight)
        need_update1 = False
        for i in range(3):
            diff = self.goal_target_pos[i] - self.current_target_pos[i]
            if abs(diff) > 0.005:
                step = math.copysign(min(abs(diff), 0.06), diff)
                self.current_target_pos[i] += step
                need_update1 = True

        if need_update1 and self.target_handle != -1:
            try:
                self.sim.setObjectPosition(self.target_handle, -1, self.current_target_pos)
            except Exception:
                pass

        # Drone 2 smooth step
        need_update2 = False
        for i in range(3):
            diff = self.goal_target2_pos[i] - self.current_target2_pos[i]
            if abs(diff) > 0.005:
                step = math.copysign(min(abs(diff), 0.06), diff)
                self.current_target2_pos[i] += step
                need_update2 = True

        if need_update2 and self.target2_handle != -1:
            try:
                self.sim.setObjectPosition(self.target2_handle, -1, self.current_target2_pos)
            except Exception:
                pass

    def read_telemetry(self) -> Dict[str, Any]:
        """Poll telemetry from CoppeliaSim and advance smooth setpoints."""
        # Auto-reconnect if disconnected (every 2.0s)
        if not self.is_connected and (time.time() - self._last_reconnect_try > 2.0):
            self._last_reconnect_try = time.time()
            self.connect()

        with self.lock:
            # 1. Advance smooth trajectory step
            self._step_smooth_trajectory()

            if self.is_connected and self.sim:
                try:
                    sim_time = self.sim.getSimulationTime()
                    if self.quadcopter_handle != -1:
                        pos1 = self.sim.getObjectPosition(self.quadcopter_handle, -1)
                        vel1, _ = self.sim.getObjectVelocity(self.quadcopter_handle)
                    elif self.target_handle != -1:
                        pos1 = self.sim.getObjectPosition(self.target_handle, -1)
                        vel1 = [0.0, 0.0, 0.0]
                    else:
                        pos1 = self.current_target_pos
                        vel1 = [0.0, 0.0, 0.0]

                    # Read Drone 2 if handle resolved
                    if self.quad2_handle != -1:
                        pos2 = self.sim.getObjectPosition(self.quad2_handle, -1)
                        vel2, _ = self.sim.getObjectVelocity(self.quad2_handle)
                    elif self.target2_handle != -1:
                        pos2 = self.sim.getObjectPosition(self.target2_handle, -1)
                        vel2 = [0.0, 0.0, 0.0]
                    else:
                        pos2 = self.current_target2_pos
                        vel2 = [0.0, 0.0, 0.0]

                    self.drone1_telemetry.update({
                        "x": round(pos1[0], 2), "y": round(pos1[1], 2), "z": round(pos1[2], 2),
                        "vx": round(vel1[0], 2), "vy": round(vel1[1], 2), "vz": round(vel1[2], 2),
                        "target_z": round(self.goal_target_pos[2], 2),
                    })

                    self.drone2_telemetry.update({
                        "x": round(pos2[0], 2), "y": round(pos2[1], 2), "z": round(pos2[2], 2),
                        "vx": round(vel2[0], 2), "vy": round(vel2[1], 2), "vz": round(vel2[2], 2),
                        "target_z": round(self.goal_target2_pos[2], 2),
                    })

                    self.last_telemetry.update({
                        "connected": True,
                        "sim_time": round(sim_time, 2),
                        "x": round(pos1[0], 2), "y": round(pos1[1], 2), "z": round(pos1[2], 2),
                        "vx": round(vel1[0], 2), "vy": round(vel1[1], 2), "vz": round(vel1[2], 2),
                        "target_z": round(self.goal_target_pos[2], 2),
                        "battery_soc": self.drone1_telemetry["battery_soc"],
                        "status": "COPPELIASIM_ACTIVE",
                        "drone1": self.drone1_telemetry,
                        "drone2": self.drone2_telemetry,
                    })
                    return self.last_telemetry
                except Exception as e:
                    logger.debug("[CoppeliaZMQ] Telemetry poll error: %s", e)
                    self.is_connected = False

            # Disconnected / Simulated Telemetry
            t = time.time()
            d1_p = self.current_target_pos
            d2_p = self.current_target2_pos

            self.drone1_telemetry.update({
                "x": round(d1_p[0], 2), "y": round(d1_p[1], 2), "z": round(d1_p[2], 2),
                "target_z": round(self.goal_target_pos[2], 2),
            })
            self.drone2_telemetry.update({
                "x": round(d2_p[0], 2), "y": round(d2_p[1], 2), "z": round(d2_p[2], 2),
                "target_z": round(self.goal_target2_pos[2], 2),
            })

            self.last_telemetry.update({
                "connected": False,
                "sim_time": round(t % 3600, 2),
                "x": round(d1_p[0], 2), "y": round(d1_p[1], 2), "z": round(d1_p[2], 2),
                "target_z": round(self.goal_target_pos[2], 2),
                "battery_soc": self.drone1_telemetry["battery_soc"],
                "status": "MOCK_SIMULATION_READY",
                "drone1": self.drone1_telemetry,
                "drone2": self.drone2_telemetry,
            })
            return self.last_telemetry

    def set_target_altitude(self, target_z: float) -> bool:
        """Set Drone 1 goal altitude (smooth trajectory)."""
        self.goal_target_pos[2] = max(0.05, float(target_z))
        logger.info("[CoppeliaZMQ] Setting goal altitude setpoint to %.2fm (Smooth glide)", self.goal_target_pos[2])
        return True

    def set_target_position(self, x: float, y: float, z: float) -> bool:
        """Set Drone 1 3D goal coordinates smoothly."""
        self.goal_target_pos = [float(x), float(y), max(0.05, float(z))]
        logger.info("[CoppeliaZMQ] Setting Drone 1 goal setpoint to %s (Smooth glide)", self.goal_target_pos)
        return True

    def set_target2_position(self, x: float, y: float, z: float) -> bool:
        """Set Drone 2 3D goal coordinates smoothly."""
        self.goal_target2_pos = [float(x), float(y), max(0.05, float(z))]
        logger.info("[CoppeliaZMQ] Setting Drone 2 goal setpoint to %s (Smooth glide)", self.goal_target2_pos)
        return True

    def execute_utm_action(self, action: str, target_drone_id: str = "UAS_CARGO_DXB_104") -> Dict[str, Any]:
        """Actuate UTM arbitration directives smoothly."""
        action = action.strip().upper()
        result = {
            "action": action,
            "drone_id": target_drone_id,
            "target_z": self.current_target_pos[2],
            "description": "",
            "actuated": False,
        }

        # Case 1: Tier 1 Manned Right-of-Way Emergency Evacuation (HEMS Incursion)
        if any(k in action for k in ["EMERGENCY_DESCENT", "EVACUATION", "HEMS"]):
            self.set_target_position(0.0, 0.0, 0.05)
            self.set_target2_position(-1.0, -0.6, 2.80)
            self.drone1_telemetry["battery_soc"] = 21.5
            self.drone1_telemetry["status"] = "EMERGENCY_LANDING_CLEARING_FOR_HEMS"
            self.drone2_telemetry["id"] = "HEMS_AIR_AMBULANCE"
            self.drone2_telemetry["role"] = "Manned Emergency Air Ambulance"
            self.drone2_telemetry["status"] = "HEMS_OVERFLIGHT_PRIORITY"
            result.update({
                "target_z": 0.05,
                "description": "EMERGENCY EVACUATION: Target lowered to ground (0.05m). Clearing airspace for HEMS.",
                "actuated": True,
            })
            logger.warning("[CoppeliaZMQ] >>> SCENARIO 1: HEMS EVACUATION (Drone 1 -> 0.05m | HEMS -> 2.80m) <<<")

        # Case 2: Tier 2 Urban Canyon 5G Shadowing
        elif any(k in action for k in ["DESCEND_30M", "5G_CELL_HANDOVER", "GNODEB", "5G", "SHADOW", "RESTORE"]):
            self.set_target_position(0.0, 0.0, 1.50)
            self.set_target2_position(1.2, 0.6, 2.40)
            self.drone1_telemetry["battery_soc"] = 58.0
            self.drone1_telemetry["status"] = "5G_CELL_HANDOVER_DESCENT"
            self.drone2_telemetry["id"] = "UAS_PEER_209"
            self.drone2_telemetry["role"] = "Commercial Fleet Peer"
            self.drone2_telemetry["status"] = "HOLDING_SEPARATION"
            result.update({
                "target_z": 1.50,
                "description": "5G HANDOVER: Lowering flight altitude by 0.5m to 1.5m for gNodeB line-of-sight.",
                "actuated": True,
            })
            logger.info("[CoppeliaZMQ] >>> SCENARIO 2: 5G HANDOVER (Drone 1 -> 1.50m) <<<")

        # Case 3: Tier 3 Critical Battery Diversion
        elif any(k in action for k in ["DIVERT", "VERTIPORT", "BATTERY"]):
            self.set_target_position(-1.2, 0.8, 0.80)
            self.set_target2_position(0.6, -0.4, 2.20)
            self.drone1_telemetry["battery_soc"] = 16.2
            self.drone1_telemetry["status"] = "DIVERTING_TO_VERTIPORT_PAD_1"
            self.drone2_telemetry["id"] = "UAS_PEER_209"
            self.drone2_telemetry["role"] = "Commercial Fleet Peer"
            self.drone2_telemetry["status"] = "NOMINAL_TRANSIT"
            result.update({
                "target_z": 0.80,
                "description": "BATTERY DIVERT: Rerouting flight path towards Vertiport Pad 1 (-1.2, 0.8, 0.8m).",
                "actuated": True,
            })
            logger.info("[CoppeliaZMQ] >>> SCENARIO 3: VERTIPORT DIVERT (Drone 1 -> -1.2, 0.8, 0.8m) <<<")

        # Case 4: Nominal Corridor Cruise (Reset to center at 2.0m)
        else:
            self.set_target_position(0.0, 0.0, 2.00)
            self.set_target2_position(1.2, 0.6, 2.40)
            self.drone1_telemetry["battery_soc"] = 82.0
            self.drone1_telemetry["status"] = "NOMINAL_CORRIDOR_CRUISE"
            self.drone2_telemetry["id"] = "UAS_PEER_209"
            self.drone2_telemetry["role"] = "Commercial Fleet Peer"
            self.drone2_telemetry["status"] = "HOLDING_SEPARATION"
            result.update({
                "target_z": 2.00,
                "description": "NOMINAL CRUISE: Maintaining assigned BVLOS corridor center at 2.0m.",
                "actuated": True,
            })
            logger.info("[CoppeliaZMQ] >>> SCENARIO 0: NOMINAL CRUISE (Drone 1 -> 2.00m) <<<")

        return result


# ------------------------------------------------------------------------------
# Authoritative Singleton Accessor
# ------------------------------------------------------------------------------
_shared_bridge: Optional[CoppeliaZMQBridge] = None
_bridge_lock = threading.Lock()


def get_coppelia_bridge(host: str = "127.0.0.1", port: int = 23000) -> CoppeliaZMQBridge:
    """Retrieve the authoritative CoppeliaZMQBridge singleton instance."""
    global _shared_bridge
    with _bridge_lock:
        if _shared_bridge is None:
            _shared_bridge = CoppeliaZMQBridge(host=host, port=port)
            _shared_bridge.connect()
        return _shared_bridge
