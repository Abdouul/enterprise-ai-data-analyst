# Phase 2 - Agentic State Machine

This folder contains the Phase 2 agent layer.

## Files

- `graph.py`: builds the LangGraph ReAct agent.
- `tools_sql.py`: exposes `execute_sql`, the SQLite tool for structured numeric data.
- `tools_vector.py`: exposes `search_vector_db`, the Qdrant tool for unstructured document search.
- `cost_tracker.py`: helper for later token/cost accounting.

## Tools

### `execute_sql`

Use this for structured questions such as:

```text
What was Apple's revenue in 2024?
Which company has the highest net income?
Compare Microsoft and Meta revenue.
```

The tool only allows `SELECT` queries and returns schema information when a query fails. This lets the ReAct agent recover by trying a corrected SQL query.

### `search_vector_db`

Use this for document evidence questions such as:

```text
What did Apple's Q3 2024 report say about supply chain risks?
What AI risks are mentioned in Alphabet's Q1 transcript?
```

Before semantic search, it extracts strict Pydantic metadata filters:

- `company_name`
- `document_year`
- `document_period`
- `document_type`

If a Gemini key (`GCP_API_KEY`) is available, filter extraction uses a lite
Gemini model (`FILTER_EXTRACTION_MODEL`, default `gemini-2.5-flash-lite`) with
structured Pydantic output. Otherwise it falls back to a deterministic local
extractor. The tool reads `QDRANT_URL` / `QDRANT_API_KEY`, so it works against a
local Qdrant or a Qdrant Cloud cluster.

## Multi-key fallback

`run_agent()` accepts several Gemini keys and rotates between them when one is
rate-limited (`429`) or times out. Keys are read, in order, from `GCP_API_KEY`,
`GCP_API_KEY2`, `GCP_API_KEY3`, `GCP_API_KEY4` (also `GEMINI_API_KEY` /
`GOOGLE_API_KEY`). When every key is exhausted, a clear quota message is
returned instead of raising.

## Run

Start Qdrant and ingest Phase 1 first:

```bash
docker compose up -d qdrant
python -m src.etl.run_phase1 --ingest
```

Run the full ReAct agent with a Gemini key:

```bash
set GCP_API_KEY=your_key_here
python -c "from src.agent.graph import run_agent; print(run_agent('What was Apple revenue in 2024 and what did the Q3 report say about risks?'))"
```

The code also loads environment variables from `.env` and `src/.env`, so local
development can use either file.

Without a Gemini key, the FastAPI compatibility wrapper still performs vector
retrieval, but it does not run the full LangGraph reasoning loop.
