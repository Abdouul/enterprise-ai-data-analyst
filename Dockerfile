docker build -t enterprise-ai-analyst .# syntax=docker/dockerfile:1

# ----------------------------------------------------------------------------
# Enterprise AI Data Analyst - FastAPI + LangGraph agent container
# Packages the LangGraph ReAct agent and exposes it as a FastAPI REST endpoint.
# ----------------------------------------------------------------------------
FROM python:3.11-slim

# Keep logs unbuffered and avoid writing .pyc files.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 0) Trust the corporate proxy (Zscaler) root + intermediate CAs so pip/TLS work
#    behind the MITM proxy. corporate-ca.crt is the full Windows trust bundle
#    (roots + intermediates) exported from the host.
COPY corporate-ca.crt /usr/local/share/ca-certificates/corporate-ca.crt
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && update-ca-certificates \
    && cat /usr/local/share/ca-certificates/corporate-ca.crt >> /etc/ssl/certs/ca-certificates.crt \
    && rm -rf /var/lib/apt/lists/*
# Point pip and Python/requests at the system CA bundle (now includes the CAs).
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

# 1) Install dependencies first so this layer is cached unless requirements change.
COPY requirements.txt .
# Install CPU-only torch first so sentence-transformers does NOT pull the huge
# NVIDIA CUDA stack (useless without a GPU and the cause of download timeouts).
RUN pip install --no-cache-dir --timeout 180 --retries 10 \
    torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --timeout 180 --retries 10 -r requirements.txt

# 2) Copy the application code (secrets and local artifacts excluded via .dockerignore).
COPY . .

# 3) Run as a non-root user for security.
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

# 4) Document the port the FastAPI app listens on.
EXPOSE 8000

# 5) Healthcheck hits the FastAPI /health endpoint (uses stdlib, no curl needed).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health').getcode()==200 else sys.exit(1)"]

# 6) Start the FastAPI REST endpoint, listening on all interfaces.
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
