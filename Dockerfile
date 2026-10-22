# ==============================================================================
# Production Dockerfile for Disaster Intelligence & Copernicus Sentinel-1 Platform
# Deploys FastAPI Backend + Copernicus SAR Bridge on Render, Railway, or Cloud VM
# ==============================================================================

FROM python:3.11-slim

# Install system dependencies for GDAL, rasterio, and geospatial image processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgdal-dev \
    gdal-bin \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set GDAL environment variables for compilation
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

WORKDIR /app

# Install Python dependencies (JSON array syntax required for paths with spaces)
COPY ["Disaster API/requirements.txt", "./requirements.txt"]
RUN pip install --no-cache-dir -r requirements.txt \
    fastapi>=0.110.0 \
    uvicorn[standard]>=0.28.0 \
    requests>=2.31.0 \
    pyyaml>=6.0 \
    numpy>=1.24.0 \
    rasterio>=1.3.8

# Copy backend application source code and Copernicus fetch engine
COPY ["Disaster API", "/app/Disaster API"]
COPY fetchengine /app/fetchengine
COPY run_server.py /app/run_server.py

# Ensure runs directory exists
RUN mkdir -p /app/fetchengine/runs

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV HOST=0.0.0.0
ENV ENVIRONMENT=production

EXPOSE 8000

# Start FastAPI server via run_server.py (safely handles directory spaces & dynamic $PORT)
CMD ["python", "run_server.py"]
