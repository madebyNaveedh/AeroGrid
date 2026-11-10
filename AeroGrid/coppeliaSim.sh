#!/bin/bash
# ==============================================================================
# AeroGrid - CoppeliaSim Smart Launcher (Ubuntu 22.04 + ROS 2 Humble)
# ==============================================================================
set -e

# 1. Source ROS 2 Humble
if [ -f "/opt/ros/humble/setup.bash" ]; then
    source /opt/ros/humble/setup.bash
fi

# Auto-detect X11 Display if unset
if [ -z "$DISPLAY" ]; then
    if [ -S "/tmp/.X11-unix/X1" ]; then
        export DISPLAY=:1
    elif [ -S "/tmp/.X11-unix/X0" ]; then
        export DISPLAY=:0
    fi
fi

# 2. Source AeroGrid ROS 2 workspace
WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$WORKSPACE_DIR/install/setup.bash" ]; then
    source "$WORKSPACE_DIR/install/setup.bash"
elif [ -f "$HOME/AIforGood/install/setup.bash" ]; then
    source "$HOME/AIforGood/install/setup.bash"
fi

# 3. Locate CoppeliaSim directory
CANDIDATE_DIRS=(
    "$HOME/CoppeliaSim"
    "$HOME/Downloads/CoppeliaSim_Edu_V4_10_0_rev0_Ubuntu22_04"
    "$HOME/Downloads/CoppeliaSim_Edu_V4_7_0_rev4_Ubuntu22_04"
    "$HOME/Downloads/CoppeliaSim_Edu_V4_6_0_rev0_Ubuntu22_04"
    "/opt/CoppeliaSim"
)

COPPELIA_DIR=""
for dir in "${CANDIDATE_DIRS[@]}"; do
    if [ -x "$dir/coppeliaSim" ] || [ -x "$dir/coppeliaSim.sh" ]; then
        COPPELIA_DIR="$dir"
        break
    fi
done

if [ -z "$COPPELIA_DIR" ]; then
    AUTO_BIN=$(find "$HOME" "/opt" -maxdepth 3 -name "coppeliaSim" -type f 2>/dev/null | head -n 1)
    if [ -n "$AUTO_BIN" ]; then
        COPPELIA_DIR="$(dirname "$AUTO_BIN")"
    fi
fi

if [ -z "$COPPELIA_DIR" ]; then
    echo "[ERROR] CoppeliaSim binary not found in standard directories: ${CANDIDATE_DIRS[*]}"
    echo "Please ensure CoppeliaSim is unpacked in ~/CoppeliaSim or ~/Downloads."
    exit 1
fi

echo "[AeroGrid] CoppeliaSim found at: $COPPELIA_DIR"
echo "[AeroGrid] ROS 2 Humble environment loaded."
echo "[AeroGrid] Starting CoppeliaSim..."
cd "$COPPELIA_DIR"
exec ./coppeliaSim.sh "$@"
