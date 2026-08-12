# Notes dev F0003 — README architecture dossiers

Date: 2026-08-07  
Role: agent DEVELOPPEUR  
Branche: F0003  
Temps passe: **~12 minutes** (exploration arborescence + lecture README/pyproject/notes F0001-F0002 + redaction README + notes)

## Perimetre

Documentation courte de l'architecture du projet dans `README.md` : role de chaque sous-dossier / fichier cle.  
Pas de code production. Pas de commit / push / merge.  
Pas de modification de `features.csv` / `anomalies.csv`.

## Fichiers modifies / crees

| Fichier | Action |
|---------|--------|
| `README.md` | Reecrit (propre, intention conserve + section Arborescence + install dev) |
| `gestion_projet/notes_dev_F0003.md` | Cree (ce fichier) |

## Contenu README

1. **Intention conserve** : data lineage, creation recursive des ancetres, types t_/v_/x_/iteration, modes `create_if_not_exists` vs `create_or_replace`, package core local (PyPI au tag release), tests sur bases de test, gestion_projet.
2. **Nettoyage** : orthographe, structure en sections, formulation concise, pas de caracteres bizarres (regles_de_gestion).
3. **Section Arborescence** : tableau des chemins demandes :
   - `src/renatus/`, `src/renatus/pipeline/`
   - `pipeline/`, `data/` (+ input/output, duckdb main/workers)
   - `tests/`, `models/`, `gestion_projet/`
   - `pyproject.toml`, `requirements.txt`, `.gitignore`
4. **Optionnel** : installation dev (`pip install -e ".[dev]"` + `pytest`) et extra `excel`.

## Auto-verification

- Chemins de l'arborescence alignes avec le repo (list_dir + find).
- `pipeline/` et `data/files/input/` presentes (gitkeep) ; duckdb/models prets pour le runtime.
- Descriptions coherentes avec F0001 (package src, moteur pipeline) et F0002 (types etape, modes create).
- Aucun fichier CSV de gestion touche.

## Decisions

1. Tableau markdown pour l'arborescence (lisible, court).
2. Details `data/files/*` et `data/duckdb/*` explicites pour coller a la structure reelle.
3. Pas de duplication longue de l'API Python (hors scope README architecture dossiers).

## Anomalies

Aucune.

## Fin de mission dev F0003

- `README.md` a jour.
- Notes dev redigees.
- Commit / merge / status features.csv : **gestionnaire**.
