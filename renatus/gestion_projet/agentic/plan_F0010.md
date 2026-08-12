# Plan de resolution — F0010

## Identite

| champ | valeur |
|-------|--------|
| id | F0010 |
| titre | gui renatus gui |
| branche | F0010 |
| status | en_cours |
| base main | 4ab50fe |

## Objectif

Interface web (gui renatus) : connexion db + pipelines, graphe de
dependances requires, edition config step, build et visualisation tabulaire.
S'appuie sur l'API F0009 (`RenatusService`).

## Spec fonctionnelle

1. **Demarrage** : `renatus-gui <db> <pipeline_dir>`
2. **UI** : static vanilla (`index.html` / `app.js` / `style.css`)
3. **Routes** : connect, graph, step get/put, build, result
4. **Package** : `src/renatus/gui/` 100% POO
5. **Tests** : `tests/test_f0010_gui.py` (TestClient, tmp_path)
6. **Contraintes** : TDD, push reguliers F0010, pas de merge dev/main

## Etapes

- [x] 1. Lire regles + F0009 API (reutiliser RenatusService)
- [x] 2. Check git branche F0010 base main
- [x] 3. Dev : package renatus.gui + static + entrypoint
- [x] 4. Tests TDD test_f0010_gui.py
- [x] 5. Commit + push `F0010: ...`
- [x] 6. notes_dev_F0010.md + plan
- [ ] 7. Revue gestionnaire + merge FF

## Decisions

| date | decision | motif |
|------|----------|-------|
| 2026-08-07 | Package renatus.gui + composition RenatusService | ne pas casser F0009 |
| 2026-08-07 | Layout graphe hierarchique JS pur | zero deps frontend |
| 2026-08-07 | Config JSON client / YAML serveur | round-trip PyYAML simple |

## Risques

- Conflits git dev/test : dev -> src/ + tests TDD ; testeur peut enrichir
- Reload pipeline apres save YAML (validation requires)

## Temps

| role | minutes |
|------|---------|
| developpeur | ~45 |
| testeur | |

## Reprise

1. plan + session + etat.json
2. git status F0010
3. premiere etape non cochee
