# Rapport Projet

## Objectif

Construire un analyste IA d'entreprise capable d'extraire des informations depuis des PDF financiers, de les indexer dans une base vectorielle, puis de repondre a des questions via une API.

## Architecture

1. Dataset Phase 1: 10 documents financiers texte dans `data/raw_txts/`.
2. Creation de `data/finance.db` avec la table relationnelle `financials`.
3. Parsing `.txt` et `.pdf` avec extraction de metadata.
4. Nettoyage texte, normalisation et correction de mojibake courant.
5. Decoupage semantique par sections et paragraphes, pas par taille fixe brute.
6. Ingestion dans Qdrant avec embeddings Sentence Transformers `all-MiniLM-L6-v2`.
7. Reponse via outils SQL et vectoriels exposes a l'agent.
8. Evaluation optionnelle avec RAGAS.

## Phase 1 - Conformite

- Dataset: 10 documents complexes sur Alphabet, Amazon, Apple, ExxonMobil, Goldman Sachs, Meta, Microsoft, NVIDIA, Pfizer et Tesla.
- Nettoyage avant ingestion: `src/etl/clean_text.py`.
- Chunking semantique: `src/etl/chunking.py` detecte les sections et groupe les paragraphes.
- Embeddings locaux: `sentence-transformers/all-MiniLM-L6-v2`.
- Vector DB dockerisee: service Qdrant dans `docker-compose.yml`.
- Metadata JSON par vecteur: `company_name`, `document_year`, `document_period`, `document_type`, `section_title`, `page`, `source_file`.
- SQL: `src/etl/create_finance_db.py` recree `data/finance.db` avec `financials(company_name, year, revenue_billion_usd, net_income_billion_usd, report_type, industry)`.

## Prochaines etapes

- Ajouter un schema SQL metier dans `finance.db`.
- Connecter `src/agent/graph.py` a un LLM de production.
- Ajouter des tests automatises pour l'ETL et l'API.
- Ajouter une CI GitHub Actions.

## Lancement (containerisation, health check, question à l'agent)

### Prerequis

- Docker Desktop demarre.
- Cle Gemini renseignee dans `src/.env` :
  ```env
  GCP_API_KEY=ta_cle_gemini
  ```
- (Optionnel) Choix des modeles via variables d'environnement (valeurs par
  defaut dans `docker-compose.yml` : `gemini-2.5-flash` et
  `gemini-2.5-flash-lite`) :
  ```powershell
  $env:AGENT_MODEL="gemini-2.5-flash"
  $env:FILTER_EXTRACTION_MODEL="gemini-2.5-flash-lite"
  ```

### 1. Construire l'image

```powershell
docker build -t enterprise-ai-analyst .
```

### 2. Lancer la stack (API + Qdrant)

```powershell
docker compose up -d
```

Verifier l'etat des conteneurs :

```powershell
docker compose ps
```

### 3. Health check

```powershell
curl http://localhost:8000/health
# Reponse attendue : {"status":"ok"}
```

Equivalent PowerShell natif :

```powershell
(Invoke-WebRequest -Uri http://localhost:8000/health -UseBasicParsing).Content
```

### 4. Poser une question a l'agent

```powershell
$body = '{"question":"What was Apple revenue in 2024?","limit":5}'
(Invoke-WebRequest -Uri http://localhost:8000/ask `
  -Method Post -ContentType "application/json" `
  -Body $body -UseBasicParsing).Content
# Exemple de reponse :
# {"question":"What was Apple revenue in 2024?","context":[],"sql_result":null,
#  "answer":"Apple's revenue in 2024 was $85.8 billion USD."}
```

Variante `curl` (Linux/macOS ou Git Bash) :

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What was Apple revenue in 2024?","limit":5}'
```

Documentation interactive (Swagger UI) : http://localhost:8000/docs

### 5. Logs et arret

```powershell
docker compose logs api --tail 40   # consulter les logs de l'API
docker compose down                 # arreter et supprimer les conteneurs
```

### Notes

- Le `GCP_API_KEY` est injecte au runtime via `env_file: ./src/.env`, jamais
  inclus dans l'image.
- Derriere un proxy d'entreprise (Zscaler), la CA est integree a l'image
  (`corporate-ca.crt`, genere par `export_ca.ps1`).
- `torch` est installe en version CPU-only pour eviter le telechargement de la
  pile CUDA NVIDIA inutile.
- Le detail complet de la containerisation est dans `Tasks/CONTAINERIZATION.md`.
