#!/usr/bin/env bash
# ==============================================================================
# AeroGrid UTM - Turnkey Single Launch Script
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Source ROS 2 Humble environment
if [ -f "/opt/ros/humble/setup.bash" ]; then
    source /opt/ros/humble/setup.bash
fi

# 2. Source local ROS 2 bridge workspace
if [ -f "$SCRIPT_DIR/install/setup.bash" ]; then
    source "$SCRIPT_DIR/install/setup.bash"
elif [ -f "$SCRIPT_DIR/AeroGrid/ros2_ws/install/setup.bash" ]; then
    source "$SCRIPT_DIR/AeroGrid/ros2_ws/install/setup.bash"
fi

# 3. Export Python path
export PYTHONPATH="$SCRIPT_DIR:$SCRIPT_DIR/AeroGrid:$PYTHONPATH"

# 4. Launch unified AeroGrid stack with PyQt5 Mission Control GUI
exec python3 "$SCRIPT_DIR/launch_aerogrid.py" "$@"

