"""AeroGrid CoppeliaSim ZeroMQ Remote API Bridge.

Connects the Python Multi-Agent UTM architecture directly to CoppeliaSim
via the native ZeroMQ Remote API (port 23000).

Manages a dual-drone fleet within the Dubai Sky Dome airspace corridor:
  - Drone 1 (UAS_CARGO_DXB_104): Primary commercial delivery UAS executing
    arbitrated UTM flight directives (corridor cruise, emergency descent for HEMS,
    5G shadow altitude adjustment, vertiport divert).
  - Drone 2 (HEMS_AIR_AMBULANCE / UAS_PEER_209): Priority manned emergency vehicle or
    commercial fleet peer, demonstrating live tactical deconfliction, corridor separation,
    and fleet management.

Key Features:
  - Realistic Aerodynamic Velocity Limiting: Smooth tick-by-tick trajectory interpolation
    (max ~0.9 m/s vertical, ~1.8 m/s horizontal) preventing unnatural coordinate snapping or PID saturation.
  - Multi-Object Scene Resolution: Discovers and pairs both Quadcopter bodies and Target dummies in CoppeliaSim.
  - Auto-Spawning: If only one Quadcopter is present in the scene, dynamically loads the second model.
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
    """Cyber-physical bridge communicating with CoppeliaSim via ZeroMQ with multi-drone fleet support."""

    def __init__(self, host: str = "127.0.0.1", port: int = 23000):
        self.host = host
        self.port = port
        self.client: Optional[Any] = None
        self.sim: Optional[Any] = None
        self.is_connected: bool = False
        self.sim_time: float = 0.0

        self.lock = threading.Lock()
        self._stop_flight_loop = False
        self._flight_thread: Optional[threading.Thread] = None
        self._spawn_attempted = False
        self._last_reconnect_try = 0.0

        # Maximum realistic multirotor aerodynamic speeds
        self.MAX_VERT_SPEED = 0.90   # m/s (~2.1s to descend 1.95m)
        self.MAX_HORIZ_SPEED = 1.80  # m/s (~1.2s to transit 2.16m)

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
            "current_pos": [1.2, 0.6, 2.6],
            "goal_pos": [1.2, 0.6, 2.6],
            "real_pos": [1.2, 0.6, 2.6],
            "vel": [0.0, 0.0, 0.0],
            "battery_soc": 95.0,
            "status": "HOLDING_SEPARATION",
            "role": "Commercial Fleet Peer",
        }

        # Backwards compatibility attributes for single-drone consumers
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
            dt = max(0.01, min(0.1, now - last_t))
            last_t = now

            self._step_smooth_flight(dt)
            time.sleep(0.033)

    def _step_smooth_flight(self, dt: float) -> None:
        """Step positions for both drones smoothly toward their respective goals."""
        with self.lock:
            # 1. Update Drone 1
            self._interpolate_drone(self.drone1, dt)
            # 2. Update Drone 2
            self._interpolate_drone(self.drone2, dt)

            # Sync legacy compatibility fields with Drone 1
            self.current_target_pos = list(self.drone1["current_pos"])
            self.goal_target_pos = list(self.drone1["goal_pos"])
            self.quadcopter_handle = self.drone1["quad_handle"]
            self.target_handle = self.drone1["target_handle"]

            # 3. If connected to CoppeliaSim, push smooth setpoints and poll true coordinates
            if self.is_connected and self.sim:
                try:
                    # Actuate Drone 1 target dummy
                    if self.drone1["target_handle"] != -1:
                        self.sim.setObjectPosition(self.drone1["target_handle"], -1, self.drone1["current_pos"])
                    if self.drone1["quad_handle"] != -1:
                        p1 = self.sim.getObjectPosition(self.drone1["quad_handle"], -1)
                        v1, _ = self.sim.getObjectVelocity(self.drone1["quad_handle"])
                        self.drone1["real_pos"] = list(p1)
                        self.drone1["vel"] = list(v1)

                    # Actuate Drone 2 target dummy
                    if self.drone2["target_handle"] != -1:
                        self.sim.setObjectPosition(self.drone2["target_handle"], -1, self.drone2["current_pos"])
                    if self.drone2["quad_handle"] != -1:
                        p2 = self.sim.getObjectPosition(self.drone2["quad_handle"], -1)
                        v2, _ = self.sim.getObjectVelocity(self.drone2["quad_handle"])
                        self.drone2["real_pos"] = list(p2)
                        self.drone2["vel"] = list(v2)

                    self.sim_time = self.sim.getSimulationTime()
                except Exception as e:
                    logger.debug("[CoppeliaZMQ] Error updating CoppeliaSim in flight loop: %s", e)

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

        # In mock / disconnected mode, real_pos follows current_pos
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

        # 2. Connect ZeroMQ client with timeouts
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
            quads = []
            targets = []

            for obj in objs:
                try:
                    alias = self.sim.getObjectAlias(obj)
                    alias_lower = alias.lower()

                    if "target" in alias_lower:
                        targets.append((obj, alias))
                    elif any(k in alias_lower for k in ["quadcopter", "quadricopter", "drone", "hems"]):
                        quads.append((obj, alias))
                except Exception:
                    continue

            logger.info("[CoppeliaZMQ] Scene scan discovered %d Quadcopter(s) and %d Target(s).", len(quads), len(targets))

            # Resolve Drone 1
            if len(quads) >= 1:
                self.drone1["quad_handle"] = quads[0][0]
                self.drone1["alias"] = quads[0][1]
                self.quadcopter_handle = quads[0][0]
                logger.info("[CoppeliaZMQ] Drone 1 bound to '%s' (Handle: %d)", quads[0][1], quads[0][0])
            if len(targets) >= 1:
                self.drone1["target_handle"] = targets[0][0]
                self.target_handle = targets[0][0]
                pos1 = self.sim.getObjectPosition(targets[0][0], -1)
                self.drone1["current_pos"] = list(pos1)
                self.drone1["goal_pos"] = list(pos1)
                logger.info("[CoppeliaZMQ] Drone 1 target dummy bound to '%s' (Handle: %d, Pos: %s)", targets[0][1], targets[0][0], pos1)

            # Resolve Drone 2
            if len(quads) >= 2:
                self.drone2["quad_handle"] = quads[1][0]
                self.drone2["alias"] = quads[1][1]
                logger.info("[CoppeliaZMQ] Drone 2 bound to '%s' (Handle: %d)", quads[1][1], quads[1][0])
            if len(targets) >= 2:
                self.drone2["target_handle"] = targets[1][0]
                pos2 = self.sim.getObjectPosition(targets[1][0], -1)
                self.drone2["current_pos"] = list(pos2)
                self.drone2["goal_pos"] = list(pos2)
                logger.info("[CoppeliaZMQ] Drone 2 target dummy bound to '%s' (Handle: %d, Pos: %s)", targets[1][1], targets[1][0], pos2)
            elif len(quads) >= 2 and len(targets) == 1:
                # Drone 2 exists but only 1 target dummy found -> create dedicated target dummy for Drone 2
                try:
                    d2_target = self.sim.createDummy(0.05)
                    self.sim.setObjectAlias(d2_target, "target_drone2")
                    self.sim.setObjectPosition(d2_target, -1, self.drone2["goal_pos"])
                    self.drone2["target_handle"] = d2_target
                    logger.info("[CoppeliaZMQ] Dynamically created target dummy for Drone 2 (Handle: %d)", d2_target)
                except Exception as e:
                    logger.warning("[CoppeliaZMQ] Could not create target dummy for Drone 2: %s", e)

            # Auto-spawn second Quadcopter model if only 1 exists
            if len(quads) < 2 and not self._spawn_attempted:
                self._spawn_attempted = True
                model_cand = os.path.join(os.path.dirname(__file__), "..", "..", "coppeliasim", "Quadcopter.ttm")
                model_cand = os.path.abspath(model_cand)
                if os.path.exists(model_cand) and hasattr(self.sim, "loadModel"):
                    try:
                        h_new = self.sim.loadModel(model_cand)
                        self.sim.setObjectPosition(h_new, -1, [1.2, 0.6, 2.6])
                        self.sim.setObjectAlias(h_new, "Quadcopter_Peer")
                        logger.info("[CoppeliaZMQ] Auto-loaded 2nd Quadcopter model from %s (Handle: %d)", model_cand, h_new)
                        time.sleep(0.1)
                        # Re-scan to bind handles
                        self._resolve_scene_objects()
                    except Exception as e:
                        logger.debug("[CoppeliaZMQ] Auto-load model skipped: %s", e)

        except Exception as e:
            logger.debug("[CoppeliaZMQ] Scene resolution encountered error: %s", e)

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
                # Drone 1 yields right-of-way: smooth emergency descent to ground (0.05m)
                self.drone1["goal_pos"] = [0.0, 0.0, 0.05]
                self.drone1["battery_soc"] = 21.5
                self.drone1["status"] = "EMERGENCY_LANDING_CLEARING_FOR_HEMS"

                # Drone 2 acts as HEMS air ambulance: sweeps high overhead across the corridor
                self.drone2["id"] = "HEMS_AIR_AMBULANCE"
                self.drone2["role"] = "Manned Emergency Air Ambulance"
                self.drone2["goal_pos"] = [-1.2, -0.8, 2.8]
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

                # Drone 2 holds station in adjacent corridor cell at 2.60m
                self.drone2["id"] = "UAS_PEER_209"
                self.drone2["role"] = "Commercial Fleet Peer"
                self.drone2["goal_pos"] = [1.2, 0.6, 2.60]
                self.drone2["status"] = "HOLDING_SEPARATION"

            result.update({
                "target_z": 1.50,
                "description": "5G HANDOVER: Drone 1 smoothly descending to 1.5m for gNodeB LOS. Drone 2 maintaining 2.6m separation.",
                "actuated": True,
            })
            logger.info("[CoppeliaZMQ] >>> SCENARIO 2: 5G HANDOVER -> Drone 1 (1.50m) | Drone 2 (2.60m) <<<")

        # ----------------------------------------------------------------------
        # Case 3: Tier 3 Critical Battery Diversion to Vertiport Pad 1
        # ----------------------------------------------------------------------
        elif "DIVERT" in action or "VERTIPORT" in action:
            with self.lock:
                # Drone 1 diverts towards Vertiport Pad 1 (-1.8, 1.2, 0.8)
                self.drone1["goal_pos"] = [-1.8, 1.2, 0.80]
                self.drone1["battery_soc"] = 16.2
                self.drone1["status"] = "DIVERTING_TO_VERTIPORT_PAD_1"

                # Drone 2 continues nominal transit along corridor
                self.drone2["id"] = "UAS_PEER_209"
                self.drone2["role"] = "Commercial Fleet Peer"
                self.drone2["goal_pos"] = [0.6, -0.4, 2.20]
                self.drone2["status"] = "NOMINAL_TRANSIT"

            result.update({
                "target_z": 0.80,
                "description": "BATTERY DIVERT: Drone 1 navigating to Vertiport Pad 1 (-1.8, 1.2, 0.8m). Drone 2 holding corridor.",
                "actuated": True,
            })
            logger.info("[CoppeliaZMQ] >>> SCENARIO 3: VERTIPORT DIVERT -> Drone 1 (-1.8, 1.2, 0.8m) | Drone 2 transit <<<")

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
                self.drone2["goal_pos"] = [1.2, 0.6, 2.60]
                self.drone2["status"] = "HOLDING_SEPARATION"

            result.update({
                "target_z": 2.00,
                "description": "NOMINAL CRUISE: Drone 1 centered at 2.0m. Drone 2 maintaining corridor separation at 2.6m.",
                "actuated": True,
            })
            logger.info("[CoppeliaZMQ] >>> SCENARIO 0: NOMINAL CRUISE -> Drone 1 (2.00m) | Drone 2 (2.60m) <<<")

        return result

    def read_telemetry(self) -> Dict[str, Any]:
        """Poll telemetry from CoppeliaSim or return smooth simulated fleet telemetry."""
        # Auto-reconnect attempt if disconnected (every 2.0 seconds)
        if not self.is_connected and (time.time() - self._last_reconnect_try > 2.0):
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
