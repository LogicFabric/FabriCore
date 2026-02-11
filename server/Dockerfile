# Use python 3.10 slim as base
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
# - glslc: The command-line shader compiler required by llama.cpp (REPLACES google-shaderc-tools)
# - libshaderc-dev: Development headers
# - mesa-vulkan-drivers: AMD RADV driver
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    libopenblas-dev \
    vulkan-tools \
    libvulkan-dev \
    libvulkan1 \
    mesa-vulkan-drivers \
    glslang-tools \
    libshaderc-dev \
    glslc \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /server

# Install Python dependencies first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build llama-cpp-python with Vulkan support
# We force a reinstall to ensure it recompiles with the new glslc compiler found
RUN CMAKE_ARGS="-DGGML_VULKAN=ON" pip install llama-cpp-python --no-cache-dir --force-reinstall --upgrade

# Copy project
COPY . .

# Expose port
EXPOSE 8000

# Run commands
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
