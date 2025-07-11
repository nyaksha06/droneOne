#!/bin/bash


set -e

echo "Starting Ollama server..."


# !!! IMPORTANT: This should match OLLAMA_MODEL_NAME in config/settings.py !!!
OLLAMA_MODEL="llama3.2:3b" 

# Check if Ollama CLI is installed and in PATH
if ! command -v ollama &> /dev/null
then
    echo "Ollama command not found. Please ensure Ollama is installed directly on your VM and added to PATH."
    echo "Installation instructions: https://ollama.com/download"
    exit 1
fi


echo "Launching Ollama daemon..."

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
