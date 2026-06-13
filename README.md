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
python -m src.etl.create_finance_db --db-path data/finance.db
python -m src.etl.parse_documents --input data/raw_txts --output data/cleaned/parsed.jsonl
python -m src.etl.clean_text --input data/cleaned/parsed.jsonl --output data/cleaned/cleaned.jsonl
python -m src.etl.chunking --input data/cleaned/cleaned.jsonl --output data/cleaned/chunks.jsonl
```

Pipeline complet sans ingestion:

```bash
python -m src.etl.run_phase1
```

Cette commande recree aussi `data/finance.db` avec la table SQL `financials`.

Pipeline complet avec Qdrant et embeddings HuggingFace locaux:

```bash
docker compose up -d qdrant
python -m src.etl.run_phase1 --ingest
```

Ingestion vers un cluster **Qdrant Cloud** (au lieu du Qdrant local) :

```powershell
$env:QDRANT_URL = "https://xxxx.gcp.cloud.qdrant.io:6333"
$env:QDRANT_API_KEY = "<ta_cle_qdrant_cloud>"
python -m src.etl.run_phase1 --ingest
```
## API

### En local (developpement)

```bash
uvicorn src.api.main:app --reload
```

### Conteneurisee (API + Qdrant)

```bash
docker build -t enterprise-ai-analyst .
docker compose up -d
docker compose ps
```

Le `GCP_API_KEY` est injecte au runtime via `env_file: ./src/.env` (jamais
inclus dans l'image). Derriere un proxy d'entreprise (Zscaler), la CA est
integree a l'image via `corporate-ca.crt`. Detail complet dans
`Tasks/CONTAINERIZATION.md`.

### Tester l'API

```bash
curl "http://localhost:8000/health"
# {"status":"ok"}

curl -X POST "http://localhost:8000/ask" -H "Content-Type: application/json" \
  -d "{\"question\":\"What was Apple revenue in 2024?\",\"limit\":5}"
# {"question":"...","context":[],"sql_result":null,
#  "answer":"Apple's revenue in 2024 was $85.8 billion USD."}
```

Documentation interactive (Swagger UI) : http://localhost:8000/docs

### Deploiement serverless (Google Cloud Run)

L'API peut etre deployee en serverless sur **Google Cloud Run** (HTTPS auto,
scale-to-zero, facturation a l'usage via les credits gratuits GCP). L'image est
construite a distance par Cloud Build, poussee dans Artifact Registry, puis
lancee par Cloud Run. La cle Gemini est injectee depuis **Secret Manager**, et
la base SQLite `data/finance.db` est deja incluse dans l'image (les questions
chiffrees fonctionnent sans Qdrant).

Pour la recherche vectorielle en serverless, brancher un **Qdrant Cloud** (cluster
gratuit) : renseigne `$QdrantUrl` dans `deploy.ps1` et `QDRANT_API_KEY` dans
`src/.env`, ingere les donnees vers ce cluster
(`python -m src.etl.run_phase1 --ingest` avec `QDRANT_URL`/`QDRANT_API_KEY`
pointant dessus), puis redeploie. Pour la resilience, ajoute aussi tes cles
Gemini de secours (`GCP_API_KEY2`, `GCP_API_KEY3`) dans `src/.env` : `deploy.ps1`
cree les secrets correspondants et les injecte automatiquement.

Le script `deploy.ps1` enchaine toutes les etapes (auth, activation des APIs,
Artifact Registry, secret, build + deploiement). Renseigne d'abord `$ProjectId`
en haut du script et `GCP_API_KEY` dans `src/.env`, puis :

```powershell
# Deploiement complet (lit GCP_API_KEY depuis src/.env)
powershell -ExecutionPolicy Bypass -File .\deploy.ps1
```

Tester le service deploye (l'URL est affichee en fin de script) :

```powershell
$URL = "https://enterprise-ai-analyst-xxxx.europe-west1.run.app"
curl "$URL/health"
curl -X POST "$URL/ask" -H "Content-Type: application/json" `
  -d "{\"question\":\"What was Apple revenue in 2024?\",\"limit\":5}"
```

Supprimer le service apres la demo (pour eviter tout cout) :

```powershell
gcloud run services delete enterprise-ai-analyst --region europe-west1
```

## Variables d'environnement

- `GCP_API_KEY` (ou `GEMINI_API_KEY` / `GOOGLE_API_KEY`): cle API Google Gemini,
  requise pour l'agent. A placer dans `src/.env`.
- `GCP_API_KEY2`, `GCP_API_KEY3`, `GCP_API_KEY4` (optionnelles): cles Gemini de
  secours. L'agent bascule automatiquement sur la cle suivante quand une cle est
  rate-limitee (`429`) ou en timeout (voir `gemini_api_keys()` dans
  `src/agent/graph.py`).
- `LLM_PROVIDER`: fournisseur LLM, par defaut `gemini`. Mettre `openai` pour
  utiliser OpenAI (necessite alors `OPENAI_API_KEY`).
- `AGENT_MODEL`: modele de l'agent, par defaut `gemini-2.5-flash`. Les modeles
  `gemini-3*` retombent automatiquement sur `gemini-2.5-flash` pour le tool
  calling LangGraph.
- `FILTER_EXTRACTION_MODEL`: modele lite pour l'extraction de filtres metadata
  du tool vectoriel, par defaut `gemini-2.5-flash-lite`.
- `QDRANT_URL`: URL Qdrant, par defaut `http://localhost:6333`. Pour Qdrant
  Cloud, utiliser l'endpoint du cluster avec le port `:6333`
  (ex: `https://xxxx.gcp.cloud.qdrant.io:6333`).
- `QDRANT_API_KEY` (optionnelle): cle API Qdrant Cloud. Requise uniquement
  lorsque `QDRANT_URL` pointe vers un cluster Qdrant Cloud.
- `QDRANT_COLLECTION`: collection Qdrant, par defaut `finance_docs`.
- `FINANCE_DB_PATH`: chemin SQLite, par defaut `data/finance.db`.

> Securite : ne commitez jamais `src/.env`. Si une cle a ete exposee, revoquez-la
> et generez-en une nouvelle.

## Phase 2 - Agent LangGraph

La couche agent est dans `src/agent/`.

- `execute_sql`: outil SQL read-only sur `data/finance.db`, avec retour d'erreur et schema pour permettre la correction par l'agent.
- `search_vector_db`: outil Qdrant qui extrait d'abord des filtres metadata stricts via un modele Gemini lite (sortie structuree Pydantic), avec repli heuristique si aucune cle n'est disponible.
- `graph.py`: construit le ReAct agent LangGraph avec ces deux outils.

Pour lancer le vrai agent ReAct, configure `GCP_API_KEY` (ou `GEMINI_API_KEY` /
`GOOGLE_API_KEY`) dans `src/.env`. Sans cle, l'API garde un fallback de recherche
vectorielle simple.

### Resilience multi-cles

L'agent accepte plusieurs cles Gemini (`GCP_API_KEY`, puis `GCP_API_KEY2`,
`GCP_API_KEY3`, `GCP_API_KEY4`). A l'execution, `run_agent()` essaie chaque cle
dans l'ordre et bascule sur la suivante quand une cle renvoie une erreur de quota
(`429`) ou un timeout. Si toutes les cles sont epuisees, un message clair est
renvoye. En production (Cloud Run), chaque cle est stockee dans un secret dedie
(`gcp-api-key`, `gcp-api-key-2`, `gcp-api-key-3`) injecte sous le meme nom de
variable ; `deploy.ps1` cree ces secrets automatiquement a partir de `src/.env`.
