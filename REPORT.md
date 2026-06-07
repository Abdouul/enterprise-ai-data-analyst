# Rapport Projet

## Objectif

Construire un analyste IA d'entreprise capable d'extraire des informations depuis des PDF financiers, de les indexer dans une base vectorielle, puis de repondre a des questions via une API.

## Architecture

1. Extraction PDF avec `pypdf`.
2. Nettoyage texte et normalisation.
3. Decoupage en chunks avec chevauchement.
4. Ingestion dans Qdrant avec embeddings Sentence Transformers.
5. Reponse via outils SQL et vectoriels exposes a l'agent.
6. Evaluation optionnelle avec RAGAS.

## Prochaines etapes

- Ajouter un schema SQL metier dans `finance.db`.
- Connecter `src/agent/graph.py` a un LLM de production.
- Ajouter des tests automatises pour l'ETL et l'API.
- Ajouter une CI GitHub Actions.
