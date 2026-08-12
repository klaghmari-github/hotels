# Notes dev F0008 — CLI renatus

Date: 2026-08-07  
Role: agent DEVELOPPEUR  
Branche: F0008 (base main `a21fdc3`)  
Temps passe: **~50 minutes** (implementation + verification smoke/pytest)

## Perimetre

- CLI oneshot et REPL pour piloter `ConnectionPipeline`
- Commandes : `p_table_view`, `table_view` (sans lineage), cle pipeline
  (`process_with_requires`), `help`, `quit` / `exit` / EOF
- Pas de modification `engine.py`
- Pas de merge develop/main, pas de force push
- Pas de modification `features.csv` status (gestionnaire)
- Zone `tests/` laissee au testeur (fichiers presents en parallele)

## Livrables

| Fichier | Action |
|---------|--------|
| `src/renatus/cli.py` | Classes `ResultPrinter`, `CommandRunner`, `CommandResult`, `RenatusCli`, `main()` |
| `src/renatus/__main__.py` | `python -m renatus` |
| `renatus.py` | Lanceur racine + shim package (evite l'ombre du package src/) |
| `pyproject.toml` | entry point `[project.scripts] renatus` + pytest `pythonpath=src` |
| `gestion_projet/notes_dev_F0008.md` | Ce fichier |
| `gestion_projet/agentic/plan_F0008.md` | Etapes dev cochees |

## Decisions

1. **Architecture POO** : `ResultPrinter` (affichage), `CommandRunner`
   (tokens -> engine), `RenatusCli` (orchestration oneshot/REPL).
2. **Lazy connection** : properties `connection` / `runner` sur `RenatusCli`.
3. **read_only=False par defaut** — les etapes `execute` peuvent ecrire
   (`--read-only` disponible).
4. **Un seul token = cle pipeline** — `process_with_requires`
   (ex: `x_drop_rows`).
5. **table_view** — controle `relation_exists` avant SQL ; `LookupError`
   explicite si absent (pas de lineage).
6. **Affichage** — tableau texte simple, max 200 lignes + mention si tronque.
7. **REPL** — prompt `renatus> `, split simple, EOF = quit, erreurs non fatales.
8. **renatus.py shim** — le fichier racine porte le meme nom que le package ;
   on fixe `__path__` vers `src/renatus` et on charge `__init__` pour ne pas
   casser les imports (`import renatus` / pytest).
9. **pytest pythonpath** — `src` en tete pour preferer le package source.
10. **Injection I/O** — `printer` / `stdin` injectables pour tests unitaires.

## Commandes CLI

```text
python renatus.py <db> <pipeline_dir> p_table_view v_sales
python -m renatus <db> <pipeline_dir>
python renatus.py <db> <pipeline_dir>          # REPL
renatus <db> <pipeline_dir> table_view v_achats  # si entrypoint installe
```

REPL / oneshot:
- `p_table_view NAME` — lineage + SELECT *
- `table_view NAME` — SELECT * sans lineage (erreur si absent)
- `x_drop_rows` / `process_with_requires NAME` — etape + requires
- `process NAME`, `p_iteration NAME`, `help`, `quit` / `exit`

## Validation

```text
pytest tests/test_f0008_cli.py -q   # 21 passed (apres complements testeur)
pytest tests/ -q                    # 68 passed

# Smoke manuel tmp
python renatus.py <tmp.db> <tmp/pipelines> p_table_view v_sales   # exit 0
python renatus.py <tmp.db> <tmp/pipelines> table_view no_such     # exit 1
printf 'help\nquit\n' | python renatus.py <tmp.db> <tmp/pipelines>
```

## Commits / push

Branche : `F0008` → `origin/F0008` (tracking OK)

| hash | message |
|------|---------|
| `3d0f2b6` | F0008: CLI oneshot + REPL renatus |
| `1a82464` | F0008: notes_dev hash commit et push origin/F0008 |
| `7583bfd` | F0008: tests CLI complements multi-yaml et notes test (testeur) |
| `249a1f6` | F0008: plan dev coche + notes finalisation |

Tip : `249a1f6` = `origin/F0008`. Push sans force. Pas de merge develop/main.

## Non fait (volontaire / hors scope)

- Quotes / parsing avance des arguments REPL
- Pagination interactive
- Export CLI dans `__init__.py` (non obligatoire)
- Merge develop/main (gestionnaire)
- Status features.csv (gestionnaire)
