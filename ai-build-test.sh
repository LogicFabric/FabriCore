#!/bin/bash

echo "🤖 Initiating AI Build-Only Validation..."

# ---------------------------------------------------------
# 1. BUILD THE GO AGENT
# ---------------------------------------------------------
echo "----------------------------------------"
echo "🔨 Step 1: Compiling Go Agent..."
echo "----------------------------------------"
docker compose -f /home/basti/Docker/FabriCore/docker-compose.yml up agent-build-test --build --abort-on-container-exit
AGENT_EXIT=$?

if [ $AGENT_EXIT -ne 0 ]; then
    echo "❌ ERROR: Agent compilation failed. Please check the syntax or imports."
    exit 1
fi

# Verify the binary physically exists
if [ ! -f "/home/basti/Git/FabriCore/agent/bin/fabricore-agent" ]; then
    echo "❌ ERROR: Agent compiled, but binary was not found in the bin/ directory."
    exit 1
fi

# ---------------------------------------------------------
# 2. BUILD THE PYTHON SERVER IMAGE
# ---------------------------------------------------------
echo "----------------------------------------"
echo "🌐 Step 2: Building Python Server Image..."
echo "----------------------------------------"
cd /home/basti/Git/FabriCore/server

# Using 'build' instead of 'up' guarantees we test the assembly without executing the server
docker compose build
SERVER_EXIT=$?

if [ $SERVER_EXIT -ne 0 ]; then
    echo "❌ ERROR: Server Docker image failed to build. Check requirements.txt or Dockerfile."
    exit 1
fi

# ---------------------------------------------------------
# 3. SUCCESS
# ---------------------------------------------------------
echo "----------------------------------------"
echo "🎉 ALL BUILDS PASSED!"
echo "The code compiles and the images assemble without errors."
echo "Returning control for manual validation."
exit 0
