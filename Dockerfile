# Dockerfile for FERPA Feedback Pipeline - Google Drive Processor
# Optimized for Cloud Run deployment with 2GB RAM, 4 vCPU

# Use Python 3.11 slim as base image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Cloud Run sets PORT environment variable
    PORT=8080

# Install system dependencies
# - gcc, g++: Required for building some Python packages
# - libffi-dev: Required for cffi (used by cryptography)
# - libxml2-dev, libxslt1-dev: Required for lxml (used by python-docx)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Set working directory
WORKDIR /app

# Copy project files
# Copy pyproject.toml first for better layer caching
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install project with cloud dependencies
RUN pip install -e ".[cloud]"

# Change ownership to non-root user
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Run the application
# Use gunicorn with uvicorn workers for production
# --workers: Number of worker processes (adjust based on Cloud Run CPU)
# --timeout: Worker timeout (Cloud Run requests can take up to 60 minutes)
# --keep-alive: Keep connections alive for reuse
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "1", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--timeout", "3600", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "ferpa_feedback.gdrive.cloud_handler:app"]
