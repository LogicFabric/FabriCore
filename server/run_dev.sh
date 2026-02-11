#!/bin/bash
cd "$(dirname "$0")"

echo "Starting Server with Docker Compose..."
# Check if docker is available
if ! command -v docker &> /dev/null; then
    echo "Error: docker is not installed."
    exit 1
fi

# Build and Start
docker-compose up --build
