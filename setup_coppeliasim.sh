#!/usr/bin/env bash
# ==============================================================================
# AeroGrid - Automated CoppeliaSim Setup Script (Ubuntu 22.04 + ROS 2 Humble)
# ==============================================================================
set -e

INSTALL_DIR="$HOME/CoppeliaSim"
ARCHIVE_NAME="CoppeliaSim_Edu_V4_7_0_rev4_Ubuntu22_04.tar.xz"
DOWNLOAD_URL="https://downloads.coppeliarobotics.com/V4_7_0_rev4/${ARCHIVE_NAME}"

echo "===================================================================="
echo "  AEROGRID - AUTOMATED COPPELIASIM SETUP FOR UBUNTU 22.04"
echo "===================================================================="

if [ -f "$INSTALL_DIR/coppeliaSim.sh" ]; then
    echo "[INFO] CoppeliaSim is already installed at: $INSTALL_DIR"
else
    echo "[1/4] Downloading CoppeliaSim Edu for Ubuntu 22.04 (~450MB)..."
    cd "$HOME"
    if [ ! -f "$ARCHIVE_NAME" ]; then
        wget -c "$DOWNLOAD_URL" -O "$ARCHIVE_NAME"
    fi

    echo "[2/4] Extracting archive into $INSTALL_DIR..."
    mkdir -p "$INSTALL_DIR"
    tar -xf "$ARCHIVE_NAME" -C "$INSTALL_DIR" --strip-components=1
    rm -f "$ARCHIVE_NAME"
    echo "[OK] Extracted successfully."
fi

# Create a symlink in the user's home and project directories so ./coppeliaSim.sh works anywhere!
echo "[3/4] Creating launcher shortcuts..."
ln -sf "$INSTALL_DIR/coppeliaSim.sh" "$HOME/coppeliaSim.sh"
ln -sf "$INSTALL_DIR/coppeliaSim.sh" "$HOME/AIforGood/coppeliaSim.sh" 2>/dev/null || true
ln -sf "$INSTALL_DIR/coppeliaSim.sh" "$HOME/AIforGood/AeroGrid/coppeliaSim.sh" 2>/dev/null || true

echo "[4/4] Verifying simROS2 plugin for ROS 2 Humble..."
if [ -f "$INSTALL_DIR/libsimExtROS2.so" ] || [ -f "$INSTALL_DIR/libsimExtROS2Interface.so" ]; then
    echo "[OK] ROS 2 plugin verified."
fi

echo "===================================================================="
echo "  [SUCCESS] CoppeliaSim installation complete!"
echo "  To launch CoppeliaSim with ROS 2 Humble, simply run:"
echo "    cd ~/AIforGood && ./coppeliaSim.sh"
echo "===================================================================="
