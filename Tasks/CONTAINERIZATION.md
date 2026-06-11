# Containerization — FastAPI + LangGraph agent

This guide documents, step by step, how the Enterprise AI Data Analyst is
packaged into a Docker image that exposes the LangGraph ReAct agent as a
FastAPI REST endpoint.

## Goal

Package the FastAPI app in `src/api/main.py` (which drives the LangGraph agent
in `src/agent/graph.py`) into a portable container exposing:

- `GET /health` — liveness probe
- `POST /ask` — body `{ "question": "...", "limit": 5 }`

## Architecture recap

```
Client ──HTTP──▶ FastAPI (uvicorn, port 8000)
                   └─ answer_question() ─▶ LangGraph ReAct agent
                                              ├─ execute_sql   ─▶ SQLite (data/finance.db)
                                              ├─ search_vector_db ─▶ Qdrant (http://qdrant:6333)
                                              └─ LLM ─▶ Google Gemini (needs GCP_API_KEY)
```

Runtime dependencies: **Qdrant** (vector search), **SQLite** file, and the
**Gemini API** (outbound HTTPS).

## Files involved

| File | Role |
|------|------|
| `Dockerfile` | Builds the API image |
| `.dockerignore` | Keeps secrets / junk out of the build context |
| `docker-compose.yml` | Runs `api` + `qdrant` together, injects env |
| `requirements.txt` | Python dependencies installed in the image |
| `src/api/main.py` | FastAPI entrypoint (`app`) |
| `src/.env` | Local secrets (`GCP_API_KEY`) — injected, never baked in |

---

## Step-by-step

### 1. Base image
Use `python:3.11-slim` — small, and compatible with the project's pinned
dependencies in `requirements.txt`.

### 2. Environment defaults
Set `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1` so logs stream
immediately and no `.pyc` files are written. `PIP_NO_CACHE_DIR=1` keeps the
image smaller.

### 3. Working directory
`WORKDIR /app` is the root for the build and the running container.

### 4. Cache-friendly dependency install
Copy **only** `requirements.txt` first, then `pip install`. Because Docker
caches layers, editing application code no longer triggers a full reinstall of
dependencies — only changes to `requirements.txt` do.

### 5. Copy application code
`COPY . .` brings in `src/`, `data/finance.db`, etc. Secrets and local clutter
are excluded by `.dockerignore`.

### 6. Keep secrets out of the image (`.dockerignore`)
`.dockerignore` excludes `src/.env`, `.env`, `.venv/`, `.git/`, caches, docs,
and regenerable ETL artifacts. The `GCP_API_KEY` is therefore **never** copied
into an image layer.

### 7. Run as non-root
A dedicated `appuser` (uid 1000) owns `/app` and runs the process. This follows
container security best practices (no root inside the container).

### 8. Expose the API port
`EXPOSE 8000` documents the port. Uvicorn is started with
`--host 0.0.0.0 --port 8000` so the server is reachable from outside the
container, not just from `localhost` inside it.

### 9. Healthcheck
A `HEALTHCHECK` calls `GET /health` using the Python standard library
(`urllib`), avoiding the need to install `curl`. Orchestrators use it to know
when the service is ready/healthy.

### 10. Start command
`CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]`
launches the FastAPI REST endpoint.

### 11. Inject configuration at runtime
Configuration is passed as environment variables, **not** build args:

- `GCP_API_KEY` — Gemini key (from `src/.env` via compose `env_file`)
- `QDRANT_URL` — `http://qdrant:6333` inside the compose network
- `QDRANT_COLLECTION` — Qdrant collection name (default `finance_docs`)
- `FINANCE_DB_PATH` — `/app/data/finance.db`
- `AGENT_MODEL` / `FILTER_EXTRACTION_MODEL` — Gemini model overrides

### 12. Orchestrate with Qdrant
`docker-compose.yml` runs the `api` service alongside `qdrant`, mounts
`./data` as a volume (so `finance.db` persists and is shared), and wires
`QDRANT_URL` to the internal `qdrant` hostname.

---

## Build & run

### Option A — standalone container

```bash
docker build -t enterprise-ai-analyst .
docker run -p 8000:8000 -e GCP_API_KEY=YOUR_KEY enterprise-ai-analyst
```

> Standalone has no Qdrant, so `search_vector_db` will fail to connect unless
> you also point `QDRANT_URL` at a reachable Qdrant instance.

### Option B — full stack with Qdrant (recommended)

```bash
docker compose up --build
```

This starts both `api` (port 8000) and `qdrant` (ports 6333/6334). The
`GCP_API_KEY` is read from `src/.env` via `env_file`.

## Verify

```bash
# Liveness
curl http://localhost:8000/health
# => {"status":"ok"}

# Ask the agent
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What was Apple revenue in 2024 and what are the Q3 risks?"}'
```

## Notes & gotchas

- **Secrets**: `src/.env` is mounted via `env_file` at runtime and excluded from
  the image by `.dockerignore`. Rotate any key that has been shared.
- **Corporate proxy / SSL**: outbound calls to Gemini may go through a corporate
  proxy. `truststore` (in `requirements.txt`) lets Python trust the OS cert
  store; in a Linux container you may instead need to mount the corporate root
  CA and set `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE`.
- **Gemini quota**: a `429 RESOURCE_EXHAUSTED` means the model has no quota on
  the key; switch `AGENT_MODEL` or enable billing for that model.

---

## Build troubleshooting log

The first build attempts failed for two unrelated reasons. Both are fixed in
the current `Dockerfile` / `requirements.txt`.

### Issue 1 — LangChain dependency conflict

```
langchain 0.3.13 depends on langchain-core <0.4.0
langchain-google-genai 4.2.5 depends on langchain-core >=1.3.2
ERROR: ResolutionImpossible
```

**Cause**: pip had grabbed the newest `langchain-google-genai` (4.x), which
requires `langchain-core` 1.x — incompatible with the pinned `langchain 0.3.13`
/ `langgraph 0.2.60` stack. It "worked" locally only because pip had silently
upgraded `langchain-core` to 1.x, leaving an inconsistent environment; the clean
Docker resolver refused it.

**Fix**: pin a compatible 2.x release in `requirements.txt`:

```
langchain-google-genai==2.1.5   # depends on langchain-core <0.4, matches langchain 0.3.13
```

### Issue 2 — torch pulls the full CUDA stack and times out

```
Downloading torch-2.12.0 ... (532.2 MB)
Downloading nvidia_cudnn_cu13 ... (366.2 MB)
TimeoutError: The read operation timed out
ERROR: failed to build ... exit code: 2
```

**Cause**: `sentence-transformers` (used at runtime to embed the query before
the Qdrant search) depends on `torch`. On Linux, the latest `torch` pulls the
entire NVIDIA CUDA runtime (cuDNN, cuBLAS, NCCL, ...), hundreds of MB to GB.
The container has no GPU, so these are useless — and the huge downloads time out
behind the slow corporate proxy.

**Fix**: install **CPU-only** torch from the PyTorch CPU wheel index *before*
installing the rest, and raise pip's timeout/retries:

```dockerfile
RUN pip install --no-cache-dir --timeout 180 --retries 10 \
    torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --timeout 180 --retries 10 -r requirements.txt
```

Because the CPU `torch` already satisfies `sentence-transformers`'
`torch>=1.11.0` constraint, the second install does not re-pull the CUDA
packages. The CPU wheel is ~187 MB instead of ~900 MB+, so it builds far faster
and avoids the timeout.

### Issue 3 — pip SSL error inside the container (corporate proxy CA)

```
SSLError(SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED]
self-signed certificate in certificate chain'))
```

**Cause**: the corporate proxy (Zscaler) intercepts HTTPS and re-signs traffic
with its own root CA. On the host, `truststore` makes Python trust the Windows
cert store, but the `python:3.11-slim` container does **not** contain that CA,
so pip cannot verify the package hosts.

Note `--trusted-host download.pytorch.org` did **not** help, because PyTorch
redirects the actual wheel download to a different host
(`download-r2.pytorch.org`); `--trusted-host` only whitelists the exact host
listed.

**Fix**: bake the corporate CA bundle into the image and point pip/TLS at it.

1. Export the Windows trust store (roots + intermediates) to a PEM file on the
   host (see `export_ca.ps1`), producing `corporate-ca.crt`.
2. In the `Dockerfile`, install it into the system trust store and point pip,
   `requests` and OpenSSL at the resulting bundle:

```dockerfile
COPY corporate-ca.crt /usr/local/share/ca-certificates/corporate-ca.crt
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && update-ca-certificates \
    && cat /usr/local/share/ca-certificates/corporate-ca.crt >> /etc/ssl/certs/ca-certificates.crt \
    && rm -rf /var/lib/apt/lists/*
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
```

The `cat ... >>` append guarantees the full bundle is present even though
`update-ca-certificates` does not always split a multi-cert file. The same
bundle also lets the running container reach Gemini through the proxy.

> `corporate-ca.crt` contains only public/corporate CA certificates (no private
> keys), so it is safe to ship in the image. It is environment-specific, so
> regenerate it on your own machine via `export_ca.ps1` if you are behind a
> different proxy.

