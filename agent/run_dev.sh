#!/bin/bash
# Agent Development Runner
# This script runs the agent in development mode

cd "$(dirname "$0")"

echo "=== FabriCore Agent Development Runner ==="
echo ""

# Ensure dependencies
go mod tidy

echo "Starting Agent..."
echo "Usage: go run cmd/agent/main.go --server \"ws://SERVER_IP:8000/api/v1/ws\" --token \"your-token\""
echo ""

# Default to localhost - change SERVER_IP to your Docker host IP
SERVER_IP="${SERVER_IP:-127.0.0.1}"

go run cmd/agent/main.go --server "ws://${SERVER_IP}:8000/api/v1/ws" --token "dev-token"
