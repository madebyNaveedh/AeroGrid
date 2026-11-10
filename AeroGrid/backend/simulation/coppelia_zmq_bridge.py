"""AeroGrid CoppeliaSim ZeroMQ Remote API Bridge (Singleton).

Connects the Python Multi-Agent UTM architecture directly to CoppeliaSim
via the native ZeroMQ Remote API (port 23000).

Features:
  - Singleton Pattern: Guarantees a single authoritative bridge across Web server,
    PyQt5 HUD, and ROS 2 background workers, preventing multi-thread command conflicts.
  - Realistic Aerodynamic Velocity Limiting: Smooth tick-by-tick trajectory interpolation
    (max ~0.8 m/s vertical, ~1.2 m/s horizontal) preventing abrupt coordinate snaps or PID saturation.
  - Unambiguous Scene Resolution: Correctly matches Drone 1 (commercial UAS) and
    Drone 2 (HEMS / peer traffic) to their respective target dummies without cross-talk.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from typing import Any, Dict, List, Optional

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
        self.sim_time: float = 0.0

        self.lock = threading.Lock()
        self.zmq_lock = threading.Lock()
        self._stop_flight_loop = False
        self._flight_thread: Optional[threading.Thread] = None
        self._last_reconnect_try = 0.0

        # Maximum realistic multirotor aerodynamic speeds
        self.MAX_VERT_SPEED = 0.80   # m/s (~2.4s to descend 1.95m smoothly)
        self.MAX_HORIZ_SPEED = 1.20  # m/s (~1.6s to transit 1.8m without excessive tilt)

        # ----------------------------------------------------------------------
        # Fleet Configuration: Drone 1 (Primary UAS) & Drone 2 (HEMS / Peer)
        # ----------------------------------------------------------------------
        self.drone1: Dict[str, Any] = {
            "id": "UAS_CARGO_DXB_104",
            "alias": "Quadcopter",
            "quad_handle": -1,
            "target_handle": -1,
            "current_pos": [0.0, 0.0, 2.0],
            "goal_pos": [0.0, 0.0, 2.0],
            "real_pos": [0.0, 0.0, 2.0],
            "vel": [0.0, 0.0, 0.0],
            "battery_soc": 82.0,
            "status": "NOMINAL_CORRIDOR_CRUISE",
            "role": "Commercial Cargo UAS",
        }

        self.drone2: Dict[str, Any] = {
            "id": "UAS_PEER_209",
            "alias": "Quadcopter_Peer",
            "quad_handle": -1,
            "target_handle": -1,
            "current_pos": [1.2, 0.6, 2.4],
            "goal_pos": [1.2, 0.6, 2.4],
            "real_pos": [1.2, 0.6, 2.4],
            "vel": [0.0, 0.0, 0.0],
            "battery_soc": 95.0,
            "status": "HOLDING_SEPARATION",
            "role": "Commercial Fleet Peer",
        }

        # Legacy compatibility attributes for single-drone consumers
        self.quadcopter_handle: int = -1
        self.target_handle: int = -1
        self.current_target_pos: List[float] = [0.0, 0.0, 2.0]
        self.goal_target_pos: List[float] = [0.0, 0.0, 2.0]

        # Start continuous smoothing flight interpolation loop
        self._start_flight_loop()

    def _start_flight_loop(self) -> None:
        """Start the background realistic velocity interpolation thread."""
        if self._flight_thread is None or not self._flight_thread.is_alive():
            self._stop_flight_loop = False
            self._flight_thread = threading.Thread(target=self._flight_dynamics_loop, daemon=True)
            self._flight_thread.start()
            logger.info("[CoppeliaZMQ] Aerodynamic smoothing loop started (30 Hz rate limit).")

    def _flight_dynamics_loop(self) -> None:
        """Runs at ~30 Hz smoothly advancing target dummies toward goals at realistic multirotor speeds."""
        last_t = time.time()
        while not self._stop_flight_loop:
            now = time.time()
            dt = max(0.01, min(0.05, now - last_t))
            last_t = now

            self._step_smooth_flight(dt)
            time.sleep(0.033)

    def _step_smooth_flight(self, dt: float) -> None:
        """Step positions for both drones smoothly toward their respective goals."""
        with self.lock:
            # 1. Update Drone 1 position incrementally
            self._interpolate_drone(self.drone1, dt)
            # 2. Update Drone 2 position incrementally
            self._interpolate_drone(self.drone2, dt)

            # Sync legacy compatibility fields with Drone 1
            self.current_target_pos = list(self.drone1["current_pos"])
            self.goal_target_pos = list(self.drone1["goal_pos"])
            self.quadcopter_handle = self.drone1["quad_handle"]
            self.target_handle = self.drone1["target_handle"]

            d1_target = self.drone1["target_handle"]
            d1_quad = self.drone1["quad_handle"]
            d2_target = self.drone2["target_handle"]
            d2_quad = self.drone2["quad_handle"]

            d1_cpos = list(self.drone1["current_pos"])
            d2_cpos = list(self.drone2["current_pos"])

        # 3. If connected to CoppeliaSim, push smooth setpoints and poll true coordinates
        if self.is_connected and self.sim:
            with self.zmq_lock:
                try:
                    # Actuate Drone 1 target dummy
                    if d1_target != -1:
                        self.sim.setObjectPosition(d1_target, -1, d1_cpos)
                    if d1_quad != -1:
                        p1 = self.sim.getObjectPosition(d1_quad, -1)
                        self.drone1["real_pos"] = list(p1)

                    # Actuate Drone 2 target dummy
                    if d2_target != -1:
                        self.sim.setObjectPosition(d2_target, -1, d2_cpos)
                    if d2_quad != -1:
                        p2 = self.sim.getObjectPosition(d2_quad, -1)
                        self.drone2["real_pos"] = list(p2)

                    self.sim_time = self.sim.getSimulationTime()
                except Exception as e:
                    logger.debug("[CoppeliaZMQ] Error in ZeroMQ flight loop step: %s", e)

    def _interpolate_drone(self, drone: Dict[str, Any], dt: float) -> None:
        """Smoothly step target coordinates toward goal at realistic speed bounds."""
        curr = drone["current_pos"]
        goal = drone["goal_pos"]

        # Horizontal (XY) displacement & speed limiting
        dx = goal[0] - curr[0]
        dy = goal[1] - curr[1]
        dist_xy = math.hypot(dx, dy)
        max_step_xy = self.MAX_HORIZ_SPEED * dt

        if dist_xy > 0.005:
            step_xy = min(dist_xy, max_step_xy)
            curr[0] += (dx / dist_xy) * step_xy
            curr[1] += (dy / dist_xy) * step_xy
        else:
            curr[0] = goal[0]
            curr[1] = goal[1]

        # Vertical (Z) displacement & speed limiting
        dz = goal[2] - curr[2]
        dist_z = abs(dz)
        max_step_z = self.MAX_VERT_SPEED * dt

        if dist_z > 0.005:
            step_z = min(dist_z, max_step_z)
            curr[2] += math.copysign(step_z, dz)
        else:
            curr[2] = goal[2]

        # In mock / disconnected mode, real_pos directly tracks current_pos
        if not self.is_connected or drone["quad_handle"] == -1:
            drone["real_pos"] = list(curr)

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
        with self.zmq_lock:
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
        """Scan CoppeliaSim scene and accurately pair Drone 1 and Drone 2 with their target dummies."""
        if not self.sim:
            return

        try:
            objs = self.sim.getObjectsInTree(self.sim.handle_scene)

            d1_target = -1
            d2_target = -1
            d1_quad = -1
            d2_quad = -1

            generic_targets: List[Tuple[int, str]] = []
            generic_quads: List[Tuple[int, str]] = []

            for obj in objs:
                try:
                    alias = self.sim.getObjectAlias(obj)
                    alias_lower = alias.lower()

                    # Filter targets
                    if alias_lower == "target_drone1":
                        d1_target = obj
                    elif alias_lower in ("target_drone2", "target_peer", "target_hems"):
                        d2_target = obj
                    elif "target" in alias_lower:
                        generic_targets.append((obj, alias))

                    # Filter quadcopters
                    if any(k in alias_lower for k in ["quadcopter", "quadricopter", "drone", "hems"]):
                        if any(s in alias_lower for s in ["propeller", "joint", "respondable"]):
                            continue
                        if any(c in alias_lower for c in ["#", "peer", "hems", "2"]):
                            if d2_quad == -1:
                                d2_quad = obj
                        else:
                            if d1_quad == -1:
                                d1_quad = obj
                        generic_quads.append((obj, alias))
                except Exception:
                    continue

            # Fallbacks if specific aliases not present
            if d1_target == -1 and len(generic_targets) >= 1:
                d1_target = generic_targets[0][0]
            if d2_target == -1 and len(generic_targets) >= 2:
                d2_target = generic_targets[1][0]

            if d1_quad == -1 and len(generic_quads) >= 1:
                d1_quad = generic_quads[0][0]
            if d2_quad == -1 and len(generic_quads) >= 2:
                d2_quad = generic_quads[1][0]

            with self.lock:
                self.drone1["target_handle"] = d1_target
                self.drone1["quad_handle"] = d1_quad
                self.drone2["target_handle"] = d2_target
                self.drone2["quad_handle"] = d2_quad

                self.target_handle = d1_target
                self.quadcopter_handle = d1_quad

            logger.info(
                "[CoppeliaZMQ] Scene paired -> Drone 1: Quad=%d, Target=%d | Drone 2: Quad=%d, Target=%d",
                d1_quad, d1_target, d2_quad, d2_target
            )

        except Exception as e:
            logger.debug("[CoppeliaZMQ] Scene resolution encountered error: %s", e)

    def start_simulation(self) -> bool:
        """Start or resume CoppeliaSim simulation."""
        if not self.is_connected or not self.sim:
            return False
        with self.zmq_lock:
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
        with self.zmq_lock:
            try:
                self.sim.stopSimulation()
                logger.info("[CoppeliaZMQ] CoppeliaSim simulation stopped.")
                return True
            except Exception as e:
                logger.error("[CoppeliaZMQ] Error stopping simulation: %s", e)
                return False

    def set_target_altitude(self, target_z: float) -> bool:
        """Set Drone 1 goal altitude in CoppeliaSim (smooth trajectory)."""
        with self.lock:
            self.drone1["goal_pos"][2] = max(0.05, float(target_z))
        logger.info("[CoppeliaZMQ] Set Drone 1 goal altitude to %.2fm (Smooth glide)", target_z)
        return True

    def set_target_position(self, x: float, y: float, z: float, drone_id: str = "drone1") -> bool:
        """Set full 3D goal coordinates smoothly without instant coordinate teleportation."""
        with self.lock:
            if drone_id in ("drone2", "hems", "peer", "HEMS_AIR_AMBULANCE", "UAS_PEER_209"):
                self.drone2["goal_pos"] = [float(x), float(y), max(0.05, float(z))]
                target_drone = "Drone 2"
            else:
                self.drone1["goal_pos"] = [float(x), float(y), max(0.05, float(z))]
                target_drone = "Drone 1"

        logger.info("[CoppeliaZMQ] %s goal setpoint updated to [%.2f, %.2f, %.2f] (Smooth glide)", target_drone, x, y, z)

        # Trigger auto-reconnect if needed
        if not self.is_connected:
            self.connect()

        return True

    def execute_utm_action(self, action: str, target_drone_id: str = "UAS_CARGO_DXB_104") -> Dict[str, Any]:
        """Actuate a UTM Coordination Engine directive for the multi-drone fleet.
        
        Controls both Drone 1 (commercial cargo) and Drone 2 (HEMS / peer traffic)
        demonstrating realistic aerodynamic velocities, clear separation, and corridor yielding.
        """
        action = action.strip().upper()
        result = {
            "action": action,
            "drone_id": target_drone_id,
            "target_z": self.drone1["goal_pos"][2],
            "description": "",
            "actuated": False,
        }

        # ----------------------------------------------------------------------
        # Case 1: Tier 1 Manned Right-of-Way Emergency Evacuation (HEMS Incursion)
        # ----------------------------------------------------------------------
        if "EMERGENCY_DESCENT" in action or "EVACUATION" in action:
            with self.lock:
                # Drone 1 yields right-of-way: smooth emergency descent to ground deck (0.05m)
                self.drone1["goal_pos"] = [0.0, 0.0, 0.05]
                self.drone1["battery_soc"] = 21.5
                self.drone1["status"] = "EMERGENCY_LANDING_CLEARING_FOR_HEMS"

                # Drone 2 acts as HEMS air ambulance: sweeps high overhead across the corridor
                self.drone2["id"] = "HEMS_AIR_AMBULANCE"
                self.drone2["role"] = "Manned Emergency Air Ambulance"
                self.drone2["goal_pos"] = [-1.0, -0.6, 2.80]
                self.drone2["status"] = "HEMS_OVERFLIGHT_PRIORITY"

            result.update({
                "target_z": 0.05,
                "description": "EMERGENCY EVACUATION: Drone 1 gliding to ground (0.05m) yielding corridor. HEMS sweeping overhead at 2.8m.",
                "actuated": True,
            })
            logger.warning("[CoppeliaZMQ] >>> SCENARIO 1: HEMS INCURSION -> Drone 1 Landing (0.05m) | HEMS Overflight (2.8m) <<<")

        # ----------------------------------------------------------------------
        # Case 2: Tier 2 Urban Canyon 5G Shadowing / C2 Handover
        # ----------------------------------------------------------------------
        elif "DESCEND_30M" in action or "5G_CELL_HANDOVER" in action:
            with self.lock:
                # Drone 1 descends by 0.5m to 1.50m for gNodeB line-of-sight
                self.drone1["goal_pos"] = [0.0, 0.0, 1.50]
                self.drone1["battery_soc"] = 58.0
                self.drone1["status"] = "5G_CELL_HANDOVER_DESCENT"

                # Drone 2 holds station in adjacent corridor cell at 2.40m
                self.drone2["id"] = "UAS_PEER_209"
                self.drone2["role"] = "Commercial Fleet Peer"
                self.drone2["goal_pos"] = [1.2, 0.6, 2.40]
                self.drone2["status"] = "HOLDING_SEPARATION"

            result.update({
                "target_z": 1.50,
                "description": "5G HANDOVER: Drone 1 smoothly descending to 1.5m for gNodeB LOS. Drone 2 maintaining 2.4m separation.",
                "actuated": True,
            })
            logger.info("[CoppeliaZMQ] >>> SCENARIO 2: 5G HANDOVER -> Drone 1 (1.50m) | Drone 2 (2.40m) <<<")

        # ----------------------------------------------------------------------
        # Case 3: Tier 3 Critical Battery Diversion to Vertiport Pad 1
        # ----------------------------------------------------------------------
        elif "DIVERT" in action or "VERTIPORT" in action:
            with self.lock:
                # Drone 1 diverts towards Vertiport Pad 1 (-1.2, 0.8, 0.8) - within visible scene bounds
                self.drone1["goal_pos"] = [-1.2, 0.8, 0.80]
                self.drone1["battery_soc"] = 16.2
                self.drone1["status"] = "DIVERTING_TO_VERTIPORT_PAD_1"

                # Drone 2 continues nominal transit along corridor
                self.drone2["id"] = "UAS_PEER_209"
                self.drone2["role"] = "Commercial Fleet Peer"
                self.drone2["goal_pos"] = [0.6, -0.4, 2.20]
                self.drone2["status"] = "NOMINAL_TRANSIT"

            result.update({
                "target_z": 0.80,
                "description": "BATTERY DIVERT: Drone 1 navigating to Vertiport Pad 1 (-1.2, 0.8, 0.8m). Drone 2 holding corridor.",
                "actuated": True,
            })
            logger.info("[CoppeliaZMQ] >>> SCENARIO 3: VERTIPORT DIVERT -> Drone 1 (-1.2, 0.8, 0.8m) | Drone 2 transit <<<")

        # ----------------------------------------------------------------------
        # Case 4: Nominal Corridor Cruise (Reset to nominal corridor station)
        # ----------------------------------------------------------------------
        else:
            with self.lock:
                # Drone 1 at corridor center (0.0, 0.0, 2.0)
                self.drone1["goal_pos"] = [0.0, 0.0, 2.00]
                self.drone1["battery_soc"] = 82.0
                self.drone1["status"] = "NOMINAL_CORRIDOR_CRUISE"

                # Drone 2 maintaining safe lateral & altitude separation
                self.drone2["id"] = "UAS_PEER_209"
                self.drone2["role"] = "Commercial Fleet Peer"
                self.drone2["goal_pos"] = [1.2, 0.6, 2.40]
                self.drone2["status"] = "HOLDING_SEPARATION"

            result.update({
                "target_z": 2.00,
                "description": "NOMINAL CRUISE: Drone 1 centered at 2.0m. Drone 2 maintaining corridor separation at 2.4m.",
                "actuated": True,
            })
            logger.info("[CoppeliaZMQ] >>> SCENARIO 0: NOMINAL CRUISE -> Drone 1 (2.00m) | Drone 2 (2.40m) <<<")

        return result

    def read_telemetry(self) -> Dict[str, Any]:
        """Poll telemetry from in-memory cache without contention."""
        # Auto-reconnect attempt if disconnected (every 2.5 seconds)
        if not self.is_connected and (time.time() - self._last_reconnect_try > 2.5):
            self._last_reconnect_try = time.time()
            self.connect()

        with self.lock:
            d1_p = self.drone1["real_pos"] if (self.is_connected and self.drone1["quad_handle"] != -1) else self.drone1["current_pos"]
            d2_p = self.drone2["real_pos"] if (self.is_connected and self.drone2["quad_handle"] != -1) else self.drone2["current_pos"]

            sim_time = self.sim_time if self.is_connected else round(time.time() % 3600, 2)

            telemetry = {
                "connected": self.is_connected,
                "sim_time": round(sim_time, 2),
                # Fleet Drone 1
                "drone1": {
                    "id": self.drone1["id"],
                    "x": round(d1_p[0], 2),
                    "y": round(d1_p[1], 2),
                    "z": round(d1_p[2], 2),
                    "target_z": round(self.drone1["goal_pos"][2], 2),
                    "vx": round(self.drone1["vel"][0], 2),
                    "vy": round(self.drone1["vel"][1], 2),
                    "vz": round(self.drone1["vel"][2], 2),
                    "battery_soc": self.drone1["battery_soc"],
                    "status": self.drone1["status"],
                    "role": self.drone1["role"],
                },
                # Fleet Drone 2
                "drone2": {
                    "id": self.drone2["id"],
                    "x": round(d2_p[0], 2),
                    "y": round(d2_p[1], 2),
                    "z": round(d2_p[2], 2),
                    "target_z": round(self.drone2["goal_pos"][2], 2),
                    "vx": round(self.drone2["vel"][0], 2),
                    "vy": round(self.drone2["vel"][1], 2),
                    "vz": round(self.drone2["vel"][2], 2),
                    "battery_soc": self.drone2["battery_soc"],
                    "status": self.drone2["status"],
                    "role": self.drone2["role"],
                },
                # Flat fields for backwards compatibility with single-drone consumers
                "x": round(d1_p[0], 2),
                "y": round(d1_p[1], 2),
                "z": round(d1_p[2], 2),
                "vx": round(self.drone1["vel"][0], 2),
                "vy": round(self.drone1["vel"][1], 2),
                "vz": round(self.drone1["vel"][2], 2),
                "target_z": round(self.drone1["goal_pos"][2], 2),
                "battery_soc": self.drone1["battery_soc"],
                "status": "COPPELIASIM_ACTIVE" if self.is_connected else "MOCK_SIMULATION_READY",
            }

            return telemetry


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
