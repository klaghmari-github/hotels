# Notes F0023 — tests graphe dependances + Excel

## Fixture

`tests/fixtures/f0023/sales_mini.xlsx`
Colonnes: id, region, product, qty, price
8 lignes, regions EU / US / ASIA

## Scenarios (test_f0023_graph_dependencies_xlsx.py)

| Id | Chaine | Focus |
|----|--------|--------|
| A | df → table | edges + build limit 3 |
| B | df → view select | colonnes reduites |
| C | df → table filtre EU | WHERE |
| D | df → table group by | SUM qty |
| E | df → t → v → t | chaine 4 noeuds / 3 edges |
| F | df → t_eu, t_us → v_union | multi-requires |
| G | PUT requires | edge dynamique |

Iteration: non couverte (feature dediee).
