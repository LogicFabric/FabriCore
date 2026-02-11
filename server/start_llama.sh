#!/bin/bash
set -e

CONFIG_FILE="/app/llm_models/llama_args.txt"
BINARY="/app/llama-server"

echo "LD_LIBRARY_PATH is: $LD_LIBRARY_PATH"
export GGML_BACKENDS_PATH=/app
echo "GGML_BACKENDS_PATH is: $GGML_BACKENDS_PATH"

echo "Contents of /app:"
ls -F /app

# The release might need a generic libggml-cpu.so symlink
if [ -f "/app/libggml-cpu-x64.so" ] && [ ! -f "/app/libggml-cpu.so" ]; then
    echo "Creating symlink libggml-cpu.so -> libggml-cpu-x64.so"
    ln -s /app/libggml-cpu-x64.so /app/libggml-cpu.so
fi

echo "Checking for llama-server binary at $BINARY..."
if [ ! -f "$BINARY" ]; then
    echo "ERROR: llama-server binary not found at $BINARY"
    FOUND=$(find /app -name "llama-server" -type f | head -n 1)
    if [ -n "$FOUND" ]; then
        BINARY="$FOUND"
        echo "Found fallback at $BINARY"
    else
        exit 127
    fi
fi

echo "Binary library dependencies (ldd):"
ldd "$BINARY" || echo "ldd failed but continuing..."

if [ -f "$CONFIG_FILE" ]; then
    ARGS=$(cat "$CONFIG_FILE")
    echo "Starting llama-server with args: $ARGS"
    exec "$BINARY" $ARGS
else
    echo "No config file found at $CONFIG_FILE."
    echo "Waiting for model configuration from the Python server... (Container will remain idle)"
    
    # Stay alive so the container doesn't exit.
    # The Python server will restart this container after writing the config.
    while [ ! -f "$CONFIG_FILE" ]; do
        sleep 5
    done
    
    # If the file appeared, we can either exec it now or let the restart handle it.
    # Restart is cleaner as it ensures a fresh state.
    echo "Config file detected! Restarting llama-server..."
    ARGS=$(cat "$CONFIG_FILE")
    exec "$BINARY" $ARGS
fi
