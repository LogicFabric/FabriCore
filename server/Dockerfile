# Use python 3.10 slim as base
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    vulkan-tools \
    libvulkan1 \
    mesa-vulkan-drivers \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /server

# Install Python dependencies first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Expose port
EXPOSE 8000

# Run commands
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
