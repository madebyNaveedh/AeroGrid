#!/usr/bin/env python3
"""AeroGrid - Turnkey Unified Launch Orchestrator.

Launches the complete AeroGrid Multi-Agent UTM stack:
1. Sources ROS 2 Humble & AeroGrid bridge environment
2. Connects to CoppeliaSim via ZeroMQ Remote API (port 23000)
3. Spawns ROS 2 UTM command publisher (/aerogrid/utm_commands at 2 Hz)
4. Starts the Native PyQt5 Tactical Mission Control Dashboard HUD

Single command execution:
    python3 launch_aerogrid.py
or:
    ./run_aerogrid.sh
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import threading
import time

# Ensure project root and ROS 2 packages are in PYTHONPATH
WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
AEROGRID_DIR = os.path.join(WORKSPACE_ROOT, "AeroGrid")
ROS2_PKG_PATHS = [
    WORKSPACE_ROOT,
    AEROGRID_DIR,
    os.path.join(WORKSPACE_ROOT, "install/aerogrid_bridge/lib/python3.10/site-packages"),
    os.path.join(AEROGRID_DIR, "ros2_ws/src/aerogrid_bridge"),
]
for p in ROS2_PKG_PATHS:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [AeroGrid] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("aerogrid.launcher")

# Global background subprocesses
background_processes: list[subprocess.Popen] = []


def signal_handler(sig, frame):
    """Graceful termination of all spawned processes."""
    logger.info("Termination signal received. Shutting down AeroGrid subsystems...")
    for p in background_processes:
        try:
            p.terminate()
            p.wait(timeout=2)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def check_and_start_coppelia(auto_start_sim: bool = False):
    """Check if CoppeliaSim is running; if not, optionally launch it."""
    import socket
    for port in [23000, 23001, 23002]:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                logger.info("CoppeliaSim ZeroMQ server detected and reachable on port %d.", port)
                return
        except (socket.timeout, ConnectionRefusedError, OSError):
            continue

    logger.info("CoppeliaSim is not running on ports 23000-23002.")

    launcher_script = os.path.join(WORKSPACE_ROOT, "coppeliaSim.sh")
    if auto_start_sim and os.path.exists(launcher_script):
        logger.info("Auto-launching CoppeliaSim via %s...", launcher_script)
        try:
            proc = subprocess.Popen(
                [launcher_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setpgrp,
            )
            background_processes.append(proc)
            logger.info("Waiting for CoppeliaSim ZeroMQ server to initialize...")
            for _ in range(25):
                time.sleep(0.5)
                for port in [23000, 23001, 23002]:
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                            logger.info("CoppeliaSim ZMQ is ready on port %d!", port)
                            return
                    except OSError:
                        continue
        except Exception as e:
            logger.warning("Could not auto-launch CoppeliaSim: %s. You can start it manually via ./coppeliaSim.sh", e)


def start_web_server_thread(port: int = 8080):
    """Start the AeroGrid Web HUD server in a background daemon thread."""
    def _server_worker():
        try:
            from backend.server import run_server
            run_server(port=port)
        except Exception as e:
            logger.debug("Web server error: %s", e)

    t = threading.Thread(target=_server_worker, daemon=True)
    t.start()
    logger.info("Web Mission Control HUD accessible at: http://localhost:%d", port)


def start_ros2_publisher_thread():
    """Start the ROS 2 UTM command publisher in a background daemon thread."""
    def _ros2_worker():
        try:
            import rclpy
            from aerogrid_bridge.utm_publisher import UTMBridgeNode

            if not rclpy.ok():
                rclpy.init()
            node = UTMBridgeNode()
            logger.info("ROS 2 UTM Bridge Node active. Publishing on /aerogrid/utm_commands (2 Hz)...")
            rclpy.spin(node)
        except ImportError:
            logger.info("rclpy not directly loaded in this process; standalone ROS 2 launch available via: ros2 run aerogrid_bridge utm_publisher")
        except Exception as e:
            logger.debug("ROS 2 background worker ended: %s", e)

    t = threading.Thread(target=_ros2_worker, daemon=True)
    t.start()


def main():
    parser = argparse.ArgumentParser(description="AeroGrid Unified Multi-Agent UTM Launcher")
    parser.add_argument("--coppelia", action="store_true", default=True, help="Auto-launch CoppeliaSim GUI if not already running (default: enabled)")
    parser.add_argument("--no-coppelia", action="store_true", help="Do not attempt to auto-launch CoppeliaSim")
    parser.add_argument("--no-ros", action="store_true", help="Disable embedded ROS 2 publisher")
    args = parser.parse_args()

    print("=" * 80)
    print("  AEROGRID UTM - UNIFIED MULTI-AGENT LAUNCHER (ITU AI FOR GOOD)")
    print("=" * 80)

    # Auto-detect active X11 display if unset
    if not os.environ.get("DISPLAY"):
        for cand in [":1", ":0"]:
            if os.path.exists(f"/tmp/.X11-unix/X{cand[1:]}"):
                os.environ["DISPLAY"] = cand
                logger.info("Auto-detected active X11 display: %s", cand)
                break

    # 1. Check or start CoppeliaSim (auto-start enabled by default unless --no-coppelia)
    should_auto_coppelia = not args.no_coppelia
    check_and_start_coppelia(auto_start_sim=should_auto_coppelia)

    # 2. Start Web Mission Control HUD Server
    start_web_server_thread(port=8080)

    # 3. Start ROS 2 Publisher
    if not args.no_ros:
        start_ros2_publisher_thread()

    print("\n" + "=" * 80)
    print("  AEROGRID MISSION CONTROL HUD - ACCESS CHANNELS:")
    print("  * WEB GLASS COCKPIT HUD: http://localhost:8080  (or http://127.0.0.1:8080)")
    print(f"  * NATIVE DESKTOP HUD:    Active on Display {os.environ.get('DISPLAY', 'None')}")
    print("=" * 80 + "\n")

    # 4. Launch PyQt5 Tactical Mission Control Dashboard
    try:
        logger.info("Launching Native PyQt5 Tactical Mission Control Dashboard on %s...", os.environ.get("DISPLAY"))
        from PyQt5.QtWidgets import QApplication
        from AeroGrid.frontend.gui_dashboard import AeroGridTacticalHUD

        app = QApplication.instance() or QApplication(sys.argv)
        hud = AeroGridTacticalHUD()
        hud.show()

        logger.info("AeroGrid Tactical Mission Control is live!")
        sys.exit(app.exec_())
    except Exception as e:
        logger.warning("Could not launch native desktop GUI window (%s).", e)
        logger.info("Serving Web Mission Control HUD in foreground at http://localhost:8080")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

