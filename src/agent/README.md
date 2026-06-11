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

If `OPENAI_API_KEY` and `instructor` are available, filter extraction uses Instructor. Otherwise it falls back to a deterministic local extractor.

## Run

Start Qdrant and ingest Phase 1 first:

```bash
docker compose up -d qdrant
python -m src.etl.run_phase1 --ingest
```

Run the full ReAct agent with an OpenAI key:

```bash
set OPENAI_API_KEY=your_key_here
python -c "from src.agent.graph import run_agent; print(run_agent('What was Apple revenue in 2024 and what did the Q3 report say about risks?'))"
```

The code also loads environment variables from `.env` and `src/.env`, so local
development can use either file.

Without `OPENAI_API_KEY`, the FastAPI compatibility wrapper still performs vector retrieval, but it does not run the full LangGraph reasoning loop.
