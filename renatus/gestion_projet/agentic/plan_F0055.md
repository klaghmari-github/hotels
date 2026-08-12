# Plan F0055 — Execute Python

## Objectif
Composant pipeline/GUI **execute_python** (ou type voisin non collision avec `execute` SQL) :
- zone **script** (code Python)
- execution dans le **.venv par defaut** du projet, ou un **venv selectionne** en config
- integration core + GUI (palette, form, YAML, data-testid)

## Perimetre
1. Core: Step + factory + process (subprocess dans venv, isolation)
2. GUI: type registry, config (script + venv path), pictogramme
3. Tests unit/integration; AC documentes
4. Docs ARCHITECTURE/README si besoin

## Contraintes
- Ne pas casser le type `execute` SQL existant
- Separation: rien dans gestion; code produit sous `src/renatus/`
- Branche `F0055` depuis main a jour; merge FF only apres notes_test PASS + pytest OK
- Anti-respawn F0001-F0011

## Livrables
- code + tests
- notes_dev_F0055.md / notes_test_F0055.md
