# Notes correctif A0001

Date: 2026-08-07
Role: correctif packaging

## Probleme

`pip install -e .` n installait pas fastapi/uvicorn (extra `[api]` seulement),
alors que `renatus-gui` et `renatus-api` sont des entrypoints toujours declares.

## Correctif

- `pyproject.toml` : fastapi + uvicorn dans `dependencies` principales
- `requirements.txt` : miroir
- extras `[api]` / `[gui]` vides (alias historiques)
- README : install simple `pip install -e .`
- Tests `tests/test_a0001_packaging_deps.py`

## Temps

~20 min
