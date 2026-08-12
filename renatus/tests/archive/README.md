# Archive des tests obsoletes

## Regle (F0028 / F0129)

Quand une feature change de design, de methode ou de preference UI, les
tests qui figent l ancien contrat doivent etre :

1. **Mis a jour** si la feature existe encore sous une autre forme, ou
2. **Deplaces ici** s ils ne correspondent plus a aucun comportement actif
   (renommer `test_*.py` → `archived_*.py` pour ne pas etre collectes).

Les tests actifs sous `tests/` decrivent uniquement l etat a jour du projet.

## Alignements majeurs (historique)

| Contrat obsolete | Remplacement actuel | Action |
|------------------|---------------------|--------|
| Multi-cles monofichier `foo.yaml` avec id `t_x` | F0101 monocomposant `t_x.yaml` | Tests mis a jour (helpers 1 fichier / id) |
| `list_tabs(open_ids)` seul | F0125 toutes zones disque | Tests F0052 close mis a jour |
| Vue `all` contient `main` | F0104 all = hors type zone | F0082 assert via `/gui/tabs` + `/gui/step/main` |
| Croix fermer zone UI | F0126 retiree ; navigation select | Assertions UI retirees |
| Dataframe sans `mode` | F0119 mode create_* | Tests F0119 |
| Preview sans pagination | F0123/F0124 limit+page | Tests F0123/F0124 |
| Import zones invisibles | F0125 list_tabs + sync objects | Tests F0125 |
| `sql` seul dans YAML | `script` unifie (legacy `sql` OK) | Doc + normalize_script_key |
| `showDirectoryPicker` prioritaire | F0120 webkitdirectory first | Tests F0120 |

## Contenu archive

Modules entiers archives (si presents) : `archived_*.py` — non collectes
par pytest (`testpaths = tests` + pattern `test_*.py`).

Pour l instant : **aucun module entier archive** ; les echecs F0101/F0104
ont ete **corriges** pour coller au contrat actuel plutot que archives
(features encore actives).

## Verification

```bash
pytest tests/ -q
# 694+ passed (apres F0129 alignements)
```
