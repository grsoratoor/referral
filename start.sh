#!/bin/bash

# Path to your virtual environment
VENV_PATH="./venv"

# Check if the virtual environment exists
if [ -e "$VENV_PATH/bin/activate" ]; then
    # Activate the virtual environment
    source "$VENV_PATH/bin/activate"
    echo "Virtual environment activated."
else
    echo "Virtual environment not found at $VENV_PATH."
    exit 1
fi

# Check if the process is running
if pgrep -f "main.py --$1" > /dev/null; then
    echo "Killing existing process..."
    pkill -f "main.py --$1"
else
    echo "No existing process found."
fi

# Start the process
echo "Starting new process..."
nohup python3 main.py --"$1" > /dev/null 2>&1 &
echo "New process started."

# Deactivate the virtual environment
deactivate
echo "Virtual environment deactivated."
