# MAVSDK Connection Settings
SITL_SYSTEM_ADDRESS = "udp://:14550" # Default MAVLink UDP port for ArduPilot SITL

# Ollama API Settings (will be used in Phase 3)
OLLAMA_API_URL = "http://localhost:11434/api/generate" # Default Ollama API endpoint
OLLAMA_MODEL_NAME = "llama3:8b" # Example model, choose one you've downloaded/installed

# General Drone Parameters (example, can be expanded)
DEFAULT_TAKEOFF_ALTITUDE_M = 10.0
CRITICAL_BATTERY_PERCENTAGE = 20.0
