#!/bin/bash
set -e

echo "Starting PX4 SITL with Gazebo (Iris model)..."
PX4_AUTOPILOT_DIR="~/p2/PX4-Autopilot"

# Check if the PX4-Autopilot directory exists
if [ ! -d "$PX4_AUTOPILOT_DIR" ]; then
    echo "Error: PX4-Autopilot directory not found at $PX4_AUTOPILOT_DIR"
    echo "Please clone PX4-Autopilot into this location or update the PX4_AUTOPILOT_DIR variable in this script."
    echo "You can clone it using: git clone https://github.com/PX4/PX4-Autopilot.git $PX4_AUTOPILOT_DIR"
    exit 1
fi

# Navigate to the PX4-Autopilot directory
cd "$PX4_AUTOPILOT_DIR"

# Build PX4 for SITL with Gazebo
echo "Building PX4 for SITL Gazebo..."
make px4_sitl gazebo || true

echo "Launching PX4 SITL with Gazebo... (Press Ctrl+C in this terminal to stop)"
echo "MAVLink connection will be available on UDP:127.0.0.1:14550"

exec make px4_sitl gazebo
