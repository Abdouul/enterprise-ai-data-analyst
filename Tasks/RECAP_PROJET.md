# Récapitulatif du projet — Enterprise AI Data Analyst

Récapitulatif point par point de ce qui a été réalisé, aligné sur les 4 phases de
[Task_summary.md](Task_summary.md). Pour chaque phase : objectif, ce qui a été fait, et le code clé appliqué.

> **Stack** : ETL Python → SQLite + Qdrant → agent ReAct LangGraph (Gemini) → API FastAPI → Docker → Google Cloud Run.

---

## Vue d'ensemble (flux logique)

1. **Dataset** : 10 documents financiers texte dans `data/raw_txts/`.
2. **SQL** : création de `data/finance.db` (table `financials`).
3. **Parsing** des documents (`.txt`/`.pdf`) + extraction de metadata.
4. **Nettoyage** du texte (mojibake, normalisation).
5. **Chunking sémantique** (par sections, pas taille fixe).
6. **Ingestion Qdrant** avec embeddings locaux `all-MiniLM-L6-v2` + payload JSON.
7. **Agent ReAct** avec 2 outils : `execute_sql` + `search_vector_db`.
8. **API FastAPI** (`/health`, `/ask`) → conteneurisée → déployée sur Cloud Run.
9. **Évaluation RAGAS** + suivi des coûts (FinOps).

---

## Phase 1 — Vector ETL Pipeline (Data Engineering)

**Objectif** : parser, nettoyer, chunker sémantiquement, embarquer (HuggingFace local) et insérer dans une Vector DB dockerisée, avec metadata JSON par vecteur.

### Ce qui a été fait
- Dataset de 10 documents (Alphabet, Amazon, Apple, ExxonMobil, Goldman Sachs, Meta, Microsoft, NVIDIA, Pfizer, Tesla).
- Base SQL `financials` reproductible.
- Pipeline ETL automatisé : parse → clean → chunk → ingest.
- Embeddings locaux `sentence-transformers/all-MiniLM-L6-v2` (384 dim, cosine).
- Qdrant dockerisé (`docker-compose.yml`), collection `finance_docs`.
- Payload metadata par vecteur : `company_name`, `document_year`, `document_period`, `document_type`, `section_title`, `page`, `source_file`.

### Code clé

**Table SQL** — [src/etl/create_finance_db.py](../src/etl/create_finance_db.py)
```python
CREATE TABLE financials (
    company_name TEXT NOT NULL,
    year INTEGER NOT NULL,
    revenue_billion_usd REAL NOT NULL,
    net_income_billion_usd REAL NOT NULL,
    report_type TEXT NOT NULL,
    industry TEXT NOT NULL,
    PRIMARY KEY (company_name, year, report_type)
)
```

**Chunking sémantique (par sections, pas taille fixe)** — [src/etl/chunking.py](../src/etl/chunking.py)
```python
def sectionize(text): ...        # découpe par titres/headings détectés
def chunk_section(section_text, max_words=220, overlap_sentences=1): ...  # regroupe les paragraphes + overlap
```

**Ingestion Qdrant + embeddings locaux** — [src/etl/ingest_qdrant.py](../src/etl/ingest_qdrant.py)
```python
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
client = QdrantClient(url=qdrant_url, api_key=api_key)  # api_key requis pour Qdrant Cloud
client.recreate_collection(collection, VectorParams(size=384, distance=Distance.COSINE))
vector = model.encode(record["text"]).tolist()
client.upsert(collection, points=[PointStruct(id=..., vector=vector, payload=payload)])
```

**Pipeline complet** — [src/etl/run_phase1.py](../src/etl/run_phase1.py)
```python
create_finance_db(db_path)              # SQL
parse_directory(input_dir, parsed)      # parsing .txt/.pdf
clean_jsonl(parsed, cleaned)            # nettoyage
build_chunks(cleaned, chunks, 220, 1)   # chunking sémantique
if ingest: ingest_chunks(chunks, ...)   # embeddings + Qdrant
```

### Commandes
```bash
docker compose up -d qdrant
python -m src.etl.run_phase1 --ingest          # local
# Qdrant Cloud :
$env:QDRANT_URL="https://xxxx.gcp.cloud.qdrant.io:6333"; $env:QDRANT_API_KEY="<cle>"
python -m src.etl.run_phase1 --ingest
```

---

## Phase 2 — Agentic State Machine (AI Engineering)

**Objectif** : agent ReAct LangGraph avec 2 outils — `execute_sql` (avec boucle de récupération d'erreur) et `search_vector_db` (filtres metadata stricts via Pydantic *avant* la recherche sémantique).

### Ce qui a été fait
- Agent ReAct via `create_react_agent` (LangGraph) connecté à Gemini `gemini-2.5-flash`.
- Outil SQL read-only + boucle d'auto-réparation + renvoi du schéma à l'agent.
- Outil vectoriel avec extraction de filtres Pydantic (Gemini lite) + repli heuristique.
- **Fallback multi-clés Gemini** : rotation automatique sur 429/timeout.

### Code clé

**Construction de l'agent** — [src/agent/graph.py](../src/agent/graph.py)
```python
from langgraph.prebuilt import create_react_agent
llm = build_chat_model(api_key=api_key)   # ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
return create_react_agent(llm, tools=[execute_sql, search_vector_db], state_modifier=SYSTEM_PROMPT)
```

**Outil 1 — SQL avec boucle de récupération d'erreur** — [src/agent/tools_sql.py](../src/agent/tools_sql.py)
```python
@tool
def execute_sql(query: str) -> dict:
    # SELECT only ; tente une réparation déterministe (table/colonne/```sql```)
    # sinon renvoie {error, schema, hint} pour que l'agent corrige et re-tente
```

**Outil 2 — Recherche vectorielle avec filtres Pydantic stricts** — [src/agent/tools_vector.py](../src/agent/tools_vector.py)
```python
class VectorSearchFilters(BaseModel):
    company_name: str | None
    document_year: int | None
    document_period: str | None
    document_type: str | None

# 1) extraction filtres AVANT la recherche (Gemini lite -> structured output, sinon heuristique)
filters = extract_filters_with_instructor(query) or extract_filters_heuristic(query)
# 2) recherche sémantique filtrée
results = client.search(collection, query_vector=vector, query_filter=to_qdrant_filter(filters), limit=limit)
```

**Fallback multi-clés (résilience)** — [src/agent/graph.py](../src/agent/graph.py)
```python
def run_agent(question):
    keys = gemini_api_keys()  # GCP_API_KEY, GCP_API_KEY2, GCP_API_KEY3, ...
    for index, key in enumerate(keys):
        try:
            return build_react_agent(api_key=key).invoke(...)
        except Exception as exc:
            if is_retryable_llm_error(exc) and not last:  # 429 / timeout / 503...
                continue  # -> rotation vers la clé suivante
            ...
```
> Note technique : toutes les clés sont `.strip()`ées (un `\n` final cassait l'en-tête gRPC → « Illegal header value » → timeout sur `/ask`).

---

## Phase 3 — Cloud Deployment & FinOps (Cloud Computing)

**Objectif** : Dockerfile exposant l'agent en API FastAPI, déploiement sur Google Cloud Run, et log du coût en tokens de chaque exécution.

### Ce qui a été fait
- API FastAPI (`/health`, `/ask`).
- Image Docker (torch CPU-only, CA d'entreprise Zscaler, utilisateur non-root).
- `docker-compose.yml` : services `api` + `qdrant`.
- Déploiement Cloud Run via Cloud Build (build distant) + secrets dans Secret Manager.
- Recherche vectorielle serverless branchée sur **Qdrant Cloud**.
- Suivi de coût en tokens (`CostTracker`).

### Code clé

**API FastAPI** — [src/api/main.py](../src/api/main.py)
```python
app = FastAPI(title="Enterprise AI Data Analyst")

@app.get("/health")
def health(): return {"status": "ok"}

@app.post("/ask")
def ask(request: AskRequest): return answer_question(request.question, limit=request.limit)
```

**FinOps — suivi du coût en tokens** — [src/agent/cost_tracker.py](../src/agent/cost_tracker.py)
```python
@dataclass
class CostTracker:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    @property
    def estimated_cost_usd(self) -> float:
        return round(self.prompt_tokens/1000*... + self.completion_tokens/1000*..., 6)
```

**Dockerfile (extrait)** — [Dockerfile](../Dockerfile)
```dockerfile
FROM python:3.11-slim
COPY corporate-ca.crt /usr/local/share/ca-certificates/   # proxy Zscaler
RUN pip install torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu  # CPU-only
USER appuser                                               # non-root
EXPOSE 8000
CMD ["sh","-c","uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

### Déploiement Cloud Run
```powershell
# Secrets créés SANS newline final (fichier temporaire) : gcp-api-key, gcp-api-key-2/3, qdrant-key
gcloud run deploy enterprise-ai-analyst --source . --region europe-west1 --port 8000 `
  --allow-unauthenticated --memory 2Gi --cpu 2 --timeout 300 `
  --set-env-vars "AGENT_MODEL=gemini-2.5-flash,FILTER_EXTRACTION_MODEL=gemini-2.5-flash-lite,QDRANT_URL=https://...:6333" `
  --set-secrets "GCP_API_KEY=gcp-api-key:latest,GCP_API_KEY2=gcp-api-key-2:latest,GCP_API_KEY3=gcp-api-key-3:latest,QDRANT_API_KEY=qdrant-key:latest"
```
> Tout est automatisé par `deploy.ps1`. Détails de containerisation dans [CONTAINERIZATION.md](CONTAINERIZATION.md).

**État vérifié** : `/ask` répond en 200 (ex. « Apple's revenue in 2024 was $85.8 billion USD. »), collection Qdrant Cloud `finance_docs` verte (137 points, 384 dim).

---

## Phase 4 — Architecture Report (Evaluation)

**Objectif** : `REPORT.md` avec diagramme d'architecture, évaluation RAGAS (5 requêtes) et analyse de coût.

### Ce qui a été fait
- [REPORT.md](../REPORT.md) : architecture, conformité Phase 1, agent + résilience, déploiement.
- Script d'évaluation RAGAS — [src/evaluation/ragas_eval.py](../src/evaluation/ragas_eval.py) (chargement dataset, colonnes `question/answer/contexts/ground_truth`).
- Requêtes de démo dans [demo_queries.md](../demo_queries.md).

---

## Points clés à retenir

- **Modèles** : `AGENT_MODEL=gemini-2.5-flash` (tool calling), `FILTER_EXTRACTION_MODEL=gemini-2.5-flash-lite` (extraction filtres). `gemini-3*` retombe auto sur `gemini-2.5-flash`.
- **Variables d'env** : `GCP_API_KEY` (+ `GCP_API_KEY2/3` fallback), `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION=finance_docs`, `FINANCE_DB_PATH=data/finance.db`.
- **Secrets** : toujours créés **sans `\n` final** (fichier temporaire + `WriteAllText`), IAM `secretAccessor` au compte de service runtime.
- **Sécurité** : ne jamais committer `src/.env` ; régénérer toute clé exposée.
- **Git** : commit local OK, **pas de `git push`** sans accord explicite.
- **PowerShell** : pour le multi-ligne, préférer un `.ps1` exécuté via `powershell -ExecutionPolicy Bypass -File .\script.ps1` (le collage multi-ligne se corrompt).

## Pistes d'amélioration
- Tests automatisés ETL/API + CI GitHub Actions.
- Index payload sur la collection Qdrant Cloud (filtres plus rapides).
