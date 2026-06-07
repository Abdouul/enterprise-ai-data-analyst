# Rapport Projet

## Objectif

Construire un analyste IA d'entreprise capable d'extraire des informations depuis des PDF financiers, de les indexer dans une base vectorielle, puis de repondre a des questions via une API.

## Architecture

1. Dataset Phase 1: 10 documents financiers texte dans `data/raw_txts/`.
2. Parsing `.txt` et `.pdf` avec extraction de metadata.
3. Nettoyage texte, normalisation et correction de mojibake courant.
4. Decoupage semantique par sections et paragraphes, pas par taille fixe brute.
5. Ingestion dans Qdrant avec embeddings Sentence Transformers `all-MiniLM-L6-v2`.
5. Reponse via outils SQL et vectoriels exposes a l'agent.
6. Evaluation optionnelle avec RAGAS.

## Phase 1 - Conformite

- Dataset: 10 documents complexes sur Alphabet, Amazon, Apple, ExxonMobil, Goldman Sachs, Meta, Microsoft, NVIDIA, Pfizer et Tesla.
- Nettoyage avant ingestion: `src/etl/clean_text.py`.
- Chunking semantique: `src/etl/chunking.py` detecte les sections et groupe les paragraphes.
- Embeddings locaux: `sentence-transformers/all-MiniLM-L6-v2`.
- Vector DB dockerisee: service Qdrant dans `docker-compose.yml`.
- Metadata JSON par vecteur: `company_name`, `document_year`, `document_period`, `document_type`, `section_title`, `page`, `source_file`.

## Prochaines etapes

- Ajouter un schema SQL metier dans `finance.db`.
- Connecter `src/agent/graph.py` a un LLM de production.
- Ajouter des tests automatises pour l'ETL et l'API.
- Ajouter une CI GitHub Actions.
