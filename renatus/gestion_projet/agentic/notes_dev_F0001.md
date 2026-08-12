# Notes dev F0001 — initialisation package renatus

## Temps consomme
- Environ 20 minutes (exploration source + structure + adaptation + install editable + smoke)

## Fichiers crees / modifies
- `pyproject.toml` — package renatus 0.1.0, setuptools, src layout, python>=3.10
- `requirements.txt` — duckdb, pandas, numpy, pyyaml
- `src/renatus/__init__.py` — reexport API publique pipeline
- `src/renatus/pipeline/__init__.py`
- `src/renatus/pipeline/connection.py` — PipelineFactory (depuis release)
- `src/renatus/pipeline/engine.py` — moteur (depuis release)
- `src/renatus/pipeline/paths.py` — root configurable
- `src/renatus/pipeline/scope.py` — domaine hotels (copie + note F0006)
- `pipeline/` (vide + .gitkeep), `data/files/input/` (vide + .gitkeep)
- arborescence data/duckdb creee pour le dev local

## Decisions
1. **Root configurable** : `Paths(root=...)` et `release_root(root=...)` ; par defaut `find_project_root()` cherche un dossier avec `data/` + `pipeline/` (cwd, parents, emplacement package), sinon cwd.
2. **Parametre `root`** au lieu de `release_root` sur `Paths.__init__` (plus clair pour renatus) ; la fonction `release_root()` reste pour compat API.
3. **ParallelismConfig** : ajout de `@dataclass` (present dans l'import source mais decorateur manquant — necessaire pour instancier).
4. **scope.py** : copie tel quel + commentaire "domaine-specifique, F0006 reorganisera".
5. **Deps** : pas de flask/ml/catboost ; openpyxl en optional `excel` seulement (lecture xlsx dans engine si besoin).
6. **Pas de YAML metier** ni sim_v1/sim_v2/ml copies.
7. **Install** : `.venv` local + `pip install -e .` — imports verifies :
   - `from renatus import ConnectionPipeline`
   - `from renatus.pipeline import ConnectionPipeline`
   - smoke ConnectionPipeline sur YAML minimal temporaire.

## Non fait (hors scope dev)
- Tests unitaires detailles (agent testeur)
- Commit / push / merge (gestionnaire)
- features.csv / anomalies.csv (gestionnaire)
