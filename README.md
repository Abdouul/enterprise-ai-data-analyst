# Enterprise AI Data Analyst

Assistant analytique pour documents financiers d'entreprise. Le projet combine un pipeline ETL documentaire, une base SQL locale, une recherche vectorielle Qdrant et une API FastAPI.

## Structure

- `data/raw_txts/`: dataset Phase 1 de 10 documents financiers texte.
- `data/cleaned/`: texte nettoye et chunks exportes.
- `data/finance.db`: base SQLite locale.
- `src/etl/`: parsing, nettoyage, chunking et ingestion Qdrant.
- `src/agent/`: outils SQL/vectoriels, graphe agentique et suivi des couts.
- `src/api/`: API FastAPI.
- `src/evaluation/`: evaluation RAGAS.

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Lancer Qdrant

```bash
docker compose up -d qdrant
```

## Phase 1 - Vector ETL Pipeline

Le dataset contient 10 documents financiers d'entreprise dans `data/raw_txts/`. Chaque chunk recoit un payload JSON avec au minimum `company_name`, `document_year`, `document_period`, `document_type`, `section_title`, `page` et `source_file`.

```bash
python -m src.etl.parse_documents --input data/raw_txts --output data/cleaned/parsed.jsonl
python -m src.etl.clean_text --input data/cleaned/parsed.jsonl --output data/cleaned/cleaned.jsonl
python -m src.etl.chunking --input data/cleaned/cleaned.jsonl --output data/cleaned/chunks.jsonl
```

Pipeline complet sans ingestion:

```bash
python -m src.etl.run_phase1
```

Pipeline complet avec Qdrant et embeddings HuggingFace locaux:

```bash
docker compose up -d qdrant
python -m src.etl.run_phase1 --ingest
```
## API

```bash
uvicorn src.api.main:app --reload
```

Ensuite:

```bash
curl "http://localhost:8000/health"
curl -X POST "http://localhost:8000/ask" -H "Content-Type: application/json" -d "{\"question\":\"Quels sont les risques principaux ?\"}"
```

## Variables d'environnement

- `OPENAI_API_KEY`: cle API OpenAI si le graphe agentique est connecte a un modele.
- `QDRANT_URL`: URL Qdrant, par defaut `http://localhost:6333`.
- `QDRANT_COLLECTION`: collection Qdrant, par defaut `finance_docs`.
- `FINANCE_DB_PATH`: chemin SQLite, par defaut `data/finance.db`.
