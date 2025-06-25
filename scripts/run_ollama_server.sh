#!/bin/bash

# This script starts the Ollama server and pulls the specified LLM model
# for a direct (non-Docker) Ollama installation.

# Exit immediately if a command exits with a non-zero status.
set -e

echo "Starting Ollama server..."

# Define the model name to pull.
# !!! IMPORTANT: This should match OLLAMA_MODEL_NAME in config/settings.py !!!
OLLAMA_MODEL="llama3:8b" # Example: gemma:2b, llama2, mistral

# Check if Ollama CLI is installed and in PATH
if ! command -v ollama &> /dev/null
then
    echo "Ollama command not found. Please ensure Ollama is installed directly on your VM and added to PATH."
    echo "Installation instructions: https://ollama.com/download"
    exit 1
fi

# Start the Ollama server in the background (important for long-running service)
# This command typically starts the Ollama daemon.
echo "Launching Ollama daemon..."
# You might need to use `nohup ollama serve &` or a systemd service for persistent backgrounding.
# For simple script execution, `ollama serve` will run in the foreground.
# If you want it truly in the background and detached from the terminal:
nohup ollama serve > ollama.log 2>&1 &
# Give it a moment to fully start
sleep 5

echo "Attempting to pull model '${OLLAMA_MODEL}'..."
# Pull the model using the Ollama CLI
ollama pull "${OLLAMA_MODEL}"

echo "Ollama server is running and model '${OLLAMA_MODEL}' is ready."
echo "You can test it with: curl http://localhost:11434/api/generate -d '{\"model\": \"${OLLAMA_MODEL}\", \"prompt\": \"Why is the sky blue?\"}'"
echo "To stop Ollama (if running in foreground or via nohup, you might need to find its PID):"
echo "  pgrep ollama"
echo "  kill <PID>"
