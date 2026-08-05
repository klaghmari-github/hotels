# Plan de migration sim_v1 — moteur Excel ROD vers pipelines déclaratifs

Document de planification. Dossier : `pipeline_sim_v1/`.  
Références : `plan_v1.html`, `config/` (style sim_v2), `pipelines/src/accor/user/rules/`.

---

## 1. Objectif

Migrer le moteur de règles Excel ROD (simulateur v1, R1 à R4 + marge produit) d’une
implémentation Python impérative (`RevenueRules` + Flask / `run_eval_sim_v1`) vers une
chaîne de **stages déclaratifs** (YAML + tables DuckDB + formules pures).

| Ancien | Nouveau |
|--------|---------|
| `RevenueRules.compute` en boucle Python | Vues SQL / tables intermédiaires enchaînées |
| Référence LOO construite dans `eval_sim_v1.py` | Stage `2_reference` + itération LOO |
| Dépendances app user / Flask pour l’évaluation | Runner pipeline autonome, sans `run_user` |
| Un seul export `eval_sim_v1_loo.xlsx` | Trois exports : old / new / old_vs_new |

**Phase A (ce plan)** : revenus R1–R4 + marge produit + LOO + parité.  
**Phase B (hors scope immédiat)** : coûts, marge nette, amortissement, arbre de reco.

---

## 2. Périmètre hôtels

| Solution   | Codes retenus     | Exclu                          |
|------------|-------------------|--------------------------------|
| SIMPLY     | H2075, HB6A3      | —                              |
| LIBERTY    | H6188, HB5I0      | —                              |
| CONNECTED  | H0373, H3546      | **H5586** (données faibles)    |

- **6 hôtels** uniquement (`INCLUDED_HOTELS` dans `constants.py`).
- **H5586** (Novotel Porte d’Italie) est exclu : Connected avec données insuffisantes.
- Aucune agrégation ne mélange les solutions (même discipline que sim_v2 restitution).

---

## 3. Différence ancien vs nouveau

### 3.1 Ancien (baseline « old »)

- Source de vérité actuelle : `pipelines/src/accor/eval_sim_v1.py` + `RevenueRules`.
- Pour chaque hôtel H : exclusion de H des pairs de sa solution, reconstruction de la
  référence (moyenne pilotes pairs ou pivots), appel `RevenueRules.compute` avec les
  paramètres d’exploitation de H.
- Sortie de référence pour la parité : `data/eval_sim_v1_old_loo.xlsx`.

### 3.2 Nouveau (pipeline « new »)

- Stages YAML sous `pipeline_sim_v1/config/` (documentation + contrat pour un runner Python).
- Tables stables + vues de calcul ; formules R1–R4 en SQL (ou moteur de formules pur)
  **sans** dépendance Flask / services user.
- Constantes pilote et coeffs R3 centralisés dans `pipeline_sim_v1/constants.py`
  (copie fidèle de `pilot_table.py`).
- Sortie : `data/eval_sim_v1_new_loo.xlsx`.
- Comparaison : `data/eval_sim_v1_old_vs_new.xlsx` (écarts CA / marge par hôtel).

### 3.3 Ce qui ne change pas (métier)

- Ordre des règles : R1 → R2 → R3 → R4 → marge produit.
- Formules Excel (voir §6).
- LOO = exclusion de H dans la **référence pilote**, pas le LOO coefficients de sim_v2.
- Cibles LOO phase A : CA HT mensuel et marge produit (coef 2,6 / 1,45).

---

## 4. Stages pipeline

```
0_src → 1_hotel_features → 2_reference_loo → 3_rules_r1_r4 → 4_metrics
```

| Stage | Fichier config | Rôle |
|-------|----------------|------|
| **0_src** | `config/0_src_pipeline.yaml` | Chargement Excel/JSON → dataframes et tables brutes ; filtre 6 hôtels ; exclusion H5586 |
| **1_hotel_features** | `config/1_hotel_features_pipeline.yaml` | Indicateurs d’exploitation par hôtel (clients/mois, mix, m_lin, CA/marge réels) |
| **2_reference_loo** | `config/2_reference_pipeline.yaml` | Table pilote Excel ; référence solution complète ; référence LOO (pairs hors H) |
| **3_rules_r1_r4** | `config/3_rules_pipeline.yaml` | Chaîne R1–R4 + marge produit pour (hôtel H, référence active) |
| **4_metrics** | `config/4_loo_metrics_pipeline.yaml` | Itération LOO, résultats prédits vs réels, MAE/MAPE, export Excel |

Base DuckDB dédiée (à créer au premier run) :

```
duckdb/pilotes/sim_v1/sim_v1.duckdb
```

Ne pas mélanger avec `duckdb/pilotes/sim_v2/`.

---

## 5. Sources de données

| Fichier | Obligatoire | Usage |
|---------|-------------|--------|
| `data/hotel_sales_data.xlsx` | Oui | CA, marge, volumes mensuels (vérité LOO, mix observé) |
| `data/hotel_data.xlsx` | Oui | Chambres, TO, marque, m_lin corner |
| `data/rod_pilot_concepts.json` | Oui | Mapping hôtel → solution (SIMPLY / LIBERTY / CONNECTED) |
| `data/simulateur_data.xlsx` | Optionnel | Enrichissement paramètres si présent |
| Table pilote (`constants.PILOT`) | Oui | Sensibilités R2/R4, clients hébergés de référence Excel |

Notes :

- Les JSON imbriqués ne sont pas lus nativement comme Excel par le type `dataframe`
  du manager v2 : le runner sim_v1 aplatit `rod_pilot_concepts.json` en table
  `t_pilot_concepts` avant ou dans le stage 0.
- `rod_reference.json` peut compléter les pivots en phase ultérieure ; la phase A
  s’appuie sur `PILOT` + agrégats pairs LOO.

---

## 6. Formules (phase A)

```
clients_mois_h = nb_chambres × TO × guests × 30.5

# R1 — clients acheteurs
taux_acheteur  = nb_ventes_ref / clients_mois_ref
nb_acheteurs   = clients_mois_h × taux_acheteur
ca_fb_r1       = (ca_fb_ref / nb_ventes_ref) × nb_acheteurs
ca_nf_r1       = (ca_nf_ref / nb_ventes_ref) × nb_acheteurs

# R2 — impact mix ±10 %
steps          = (mix_fb_h − mix_fb_ref) × 10
ca_fb_r2       = ca_fb_r1 + ca_10_fb × steps
ca_nf_r2       = ca_nf_r1 + ca_10_nfb × (−steps)

# R3 — catégories (en eval : tous besoins ON, ou table t_client_needs)
mult_fb        = 1 + Σ(±coeff_fb)
mult_nfb       = 1 + Σ(±coeff_nfb)
ca_fb_r3       = ca_fb_r2 × mult_fb
ca_nf_r3       = ca_nf_r2 × mult_nfb

# R4 — Simply/Liberty : m_lin ; Connected : frigos froid
ca_*_r4        = ca_*_r3 ± ca_1ml_* × |m_lin_h − m_lin_ref|
               ou ± ca_1frigo_* × |frigos_h − frigo_ref|

# Marge produit
marge          = (ca_fb − ca_fb/coef_fb) + (ca_nf − ca_nf/coef_nf)
```

Coefficients R3 et table `PILOT` : voir `constants.py`.

---

## 7. Sorties

| Fichier | Contenu |
|---------|---------|
| `data/eval_sim_v1_old_loo.xlsx` | LOO via `RevenueRules` (baseline) |
| `data/eval_sim_v1_new_loo.xlsx` | LOO via pipeline tables + formules |
| `data/eval_sim_v1_old_vs_new.xlsx` | Jointure old/new : Δ CA, Δ marge, flags de parité |

Onglets cibles (alignés sur l’existant) : `data`, `eval_<code>` par hôtel, `eval` (synthèse).

---

## 8. Flux LOO

```
v_loo_step (hôtel H)
  → référence solution S sans H
  → R1–R4 sur paramètres d’exploitation de H
  → pred CA / marge
  → vs réel mensuel de H
  → t_v1_loo_results
  → v_v1_loo_metrics (MAE, MAPE)
```

Itération **séquentielle** (6 hôtels) — parallélisme inutile.

---

## 9. Critères de réussite

1. Le runner pipeline produit `t_v1_loo_results` **sans** appeler `RevenueRules` en boucle.
2. Écart absolu max CA et marge produit **&lt; 0,05 EUR** vs old sur les 6 hôtels.
3. Un hôtel exclu n’apparaît jamais dans sa propre référence solution.
4. H5586 absent de toute table filtrée et de tout export.
5. Les trois fichiers Excel de sortie sont générés et documentés.

---

## 10. Recommandations opérationnelles

**Faire**

- Isoler config et DuckDB sous `pipeline_sim_v1/` / `duckdb/pilotes/sim_v1/`.
- Valider d’abord la parité R1–R4 avant phase B (coûts).
- Réutiliser le pattern `ConnectionPipeline` de `main.py` si/quand le runner est branché
  (les YAML actuels sont le contrat ; le branchement n’est pas requis pour ce livrable).

**Ne pas faire**

- Mélanger scenarios d’assortiment sim_v2 et règles Excel v1.
- Forcer le LOO coefficients v2 sur la v1.
- Réintroduire H5586 sans décision métier explicite.
- Dupliquer un second manager de pipelines.

---

## 11. Livrables de ce dossier

| Chemin | Description |
|--------|-------------|
| `pipeline_sim_v1/PLAN.md` | Ce plan |
| `pipeline_sim_v1/constants.py` | Hôtels, chemins, PILOT, CAT_FB/NFB, JOURS_MOIS |
| `pipeline_sim_v1/config/0_src_pipeline.yaml` | Sources |
| `pipeline_sim_v1/config/1_hotel_features_pipeline.yaml` | Features hôtel |
| `pipeline_sim_v1/config/2_reference_pipeline.yaml` | Référence + LOO |
| `pipeline_sim_v1/config/3_rules_pipeline.yaml` | R1–R4 + marge |
| `pipeline_sim_v1/config/4_loo_metrics_pipeline.yaml` | Métriques + exports |

Prochaine étape d’implémentation (hors ce livrable) : runner Python qui interprète ces
YAML, exécute old vs new, et écrit les trois Excel de comparaison.
