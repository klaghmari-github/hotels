# Feature — Assortiment optimal (m_lin × rangs de marge)

## Objectif

Pour un hôtel cible et un **mètre linéaire** choisi, proposer :

1. le **nombre de produits** exposables (densité moyenne solution) ;
2. le **top N produits** qui ramènent le plus de marge (rangs croisés hotels) ;
3. le **mix F&B / gammes** déduit de ce top N ;
4. le **CA attendu** (sim_v1 / sim_v2 / ml) avec ce mix.

## Données ajoutées (vues DuckDB)

| Vue | Contenu |
|-----|---------|
| `v_hotel_product_exposure` | par hotel : `nombre_produits_distincts`, `metres_lineaires`, **`produits_par_m_lin`** |
| `v_solution_produits_par_m_lin` | moyenne densite par solution |
| `v_product_margin_by_hotel` | marge + **`rang_marge`** par `nom_produit` × hotel |
| `v_product_mean_rank_by_solution` | **`rang_moyen`** (hotels sans le produit exclus) |

Source : `t_sales.NOM_PRODUIT` + `MARGE_SELON_COEF` + `t_hotel_params.m_lin`.

## Algorithme

```
produits_par_m_lin = AVG(n_produits_distincts / m_lin)  [meme solution]
N = round(m_lin_cible * produits_par_m_lin)

pour chaque produit :
  rang_h = RANK(marge) dans hotel h
  rang_moyen = AVG(rang_h) sur hotels de la solution qui ont le produit

top N = ORDER BY rang_moyen ASC  (filtres type / gammes utilisateur)

type_mix   = parts de produits F&B vs NON F&B dans le top N
gamme_mix  = parts de gammes dans le top N (global et par famille)
```

## API

| Endpoint | Role |
|----------|------|
| `GET /api/user/product_exposure` | table exposition hotels |
| `POST /api/user/recommend_mix` | assortiment seul (`solution`, `metres_lineaires`, filtres) |
| `POST /api/user/optimize` | `method=product_rank` (defaut) : assortiment + CA moteurs |

Body optimize : leviers hotel + `type_mix` / gammes (servent de **filtres** actifs si part > 2 %).

Reponse : `apply_mix` pour recharger l’UI Configuration ; `assortments` + top produits.

## UI

Etape Optimisation → **Lancer l’optimisation** :

1. calcule assortiment product_rank pour chaque solution ;
2. evalue CA sim_v1 / sim_v2 / ml ;
3. pre-charge les mix reco dans Configuration (modifiables ensuite).

Les ajustements manuels de mix (type / gammes) après la reco suivent la
**redistribution proportionnelle** (pas d’éclatement égal) — voir
[FEATURE_MIX_REDISTRIBUTION.md](FEATURE_MIX_REDISTRIBUTION.md).

Fallback historique : `method=grid` (balayage 10 %, même règle de prorata
dans `vary_one`).

## Code

- `pipeline/sim_v2/8_optimal_mix_pipeline.yaml`
- `src/sim_v2/optimal_mix.py`
- `src/user/optimize.py` → `run_product_rank_optimization`
- `src/web/pages_user.py` → `applyRecommendedMix`
