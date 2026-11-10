#!/usr/bin/env bash
# ==============================================================================
# AeroGrid - Turnkey All-in-One Multi-Agent UTM & ROS 2 Bridge Runner
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "===================================================================="
echo "  AEROGRID (ITU AI FOR GOOD HACKATHON) - ONE-CLICK DEMONSTRATION"
echo "===================================================================="

# 1. Source ROS 2 Humble environment
echo "[1/4] Sourcing ROS 2 Humble and local bridge workspace..."
if [ -f "/opt/ros/humble/setup.bash" ]; then
    source /opt/ros/humble/setup.bash
    echo "  + Sourced /opt/ros/humble/setup.bash"
fi

if [ -f "$SCRIPT_DIR/install/setup.bash" ]; then
    source "$SCRIPT_DIR/install/setup.bash"
    echo "  + Sourced $SCRIPT_DIR/install/setup.bash"
elif [ -f "$SCRIPT_DIR/AeroGrid/ros2_ws/install/setup.bash" ]; then
    source "$SCRIPT_DIR/AeroGrid/ros2_ws/install/setup.bash"
    echo "  + Sourced $SCRIPT_DIR/AeroGrid/ros2_ws/install/setup.bash"
fi

# 2. Optional unit test verification suite (run with --test)
if [[ "$*" == *"--test"* ]]; then
    echo ""
    echo "[TEST] Running automated system verification suite..."
    export HF_HUB_OFFLINE=1
    PYTHONPATH="$SCRIPT_DIR/py_packages:$SCRIPT_DIR/AeroGrid:$SCRIPT_DIR" python3 -m unittest discover -s "$SCRIPT_DIR/AeroGrid/tests" -v
fi

# 3. Launch AeroGrid Unified Mission Control (PyQt5 HUD, Web HUD, ROS 2, CoppeliaSim)
echo ""
echo "[2/2] Launching AeroGrid Unified Stack..."
exec "$SCRIPT_DIR/run_aerogrid.sh" "$@"
