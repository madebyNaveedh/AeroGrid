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

# 2. Run automated validation test suite
echo ""
echo "[2/4] Running automated system verification suite (13 tests)..."
export HF_HUB_OFFLINE=1
PYTHONPATH="$SCRIPT_DIR/py_packages:$SCRIPT_DIR/AeroGrid:$SCRIPT_DIR" python3 -m unittest discover -s "$SCRIPT_DIR/AeroGrid/tests" -v

# 3. Run multi-agent conflict simulation pipeline
echo ""
echo "[3/4] Running AeroGrid Multi-Agent UTM Pipeline (3 Challenge Scenarios)..."
python3 "$SCRIPT_DIR/AeroGrid/backend/main.py"

# 4. Launch Tactical Mission Control Dashboard
echo ""
echo "[4/4] Launching AeroGrid Unified Stack (PyQt5 Tactical HUD)..."
exec "$SCRIPT_DIR/run_aerogrid.sh" "$@"
