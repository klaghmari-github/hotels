# Notes test F0019

## Couverture

`tests/test_f0019_requires_dataview.py`

| Test | AC |
|------|-----|
| html requires picker | multi-select UI + testids |
| js renderRequiresPicker / previewRequireSource | branchement → DataView |
| css requires-picker | styles presents |
| put requires → YAML + edges | sync backend |
| preview prereq apres build | lignes limit 3 |
| graph candidates | toutes steps listables |
| tools fields | table/view/execute/iteration ont requires |

## Resultat

50 tests (F0019 + regression gui/pipeline) : PASS

## Notes

- Dataframes DuckDB (`con.register`) sont dans le catalogue `temp` : `relation_exists` mis a jour pour les voir (sinon DataView prerequis vide).
- Preview dataframe re-process leger si register session perdu.
