# Données (`data/`)

Tous les chemins sont sous `PROJECT_ROOT/data` (`accor.DATA_DIR`).

---

## Fichiers sources

| Fichier | Grain | Description |
|---------|-------|-------------|
| `hotel_brand_data.xlsx` | marque | stats réseau, dummies `cat_*`, `logo_path`, effectifs |
| `hotel_data.xlsx` | hôtel | fiche complète (GPS, chambres, TO, équipements, corner, contrat…) |
| `hotel_sales_raw_data.xlsx` | ligne ticket | export caisse / boutique |
| `hotel_weather_data.xlsx` | hôtel × an × mois | agrégats météo |
| `hotel_proximity_data.xlsx` | hôtel | commerces OSM par rayon, plage |
| `hotel_holidays_data.xlsx` | hôtel × an × mois | fériés, weekends, vacances scolaires |
| `couts.xlsx` | ref | barèmes coûts (complété par rod_reference) |
| `rod_reference.json` | ref | concepts, cost_lines, impact TO, pivots Excel |
| `marques/` | assets | PNG par catégorie + éventuellement `marques.xlsx` |

---

## Fichiers dérivés

| Fichier | Source | Grain |
|---------|--------|-------|
| `hotel_sales_data.xlsx` | sales_prep | hôtel × an × mois + mix % |
| `all_data.xlsx` | join_data | large jointure mois |
| `model_data.xlsx` | model_data | filtré, rôles, imputé ML |
| `model_data_meta.json` | model_data | listes colonnes, n_train/n_eval, eval_year |
| `concept_pilote.xlsx` | concept_pilote | hôtel × année |

---

## Onglets admin (`schemas.DATASETS`)

| id | Fichier | Editable | Notes |
|----|---------|----------|-------|
| brand | hotel_brand_data | oui | dummies cat_*, logo |
| hotel | hotel_data | oui | large schéma booléens |
| proximity | hotel_proximity_data | limité | rebuild Overpass |
| holidays | hotel_holidays_data | limité | rebuild calendrier |
| weather | hotel_weather_data | limité | rebuild Meteostat |
| sales_raw | hotel_sales_raw_data | oui | lignes tickets |
| sales | hotel_sales_data | dérivé | rebuild depuis raw |
| all_data | all_data | large | rebuild join |
| model_data | model_data | **readonly** | rebuild only |
| concept_pilote | concept_pilote | dérivé | rebuild |

---

## Rôles model_data

Définis dans `model_data_meta.json` :

- **id_detail** — identité / temps / géo descriptive non feature pure  
- **descriptive** — features X du modèle  
- **target** — Y multi-output  

Flag `_is_eval` : 1 = dernière année (hold-out), 0 = train.

Cible principale ranking : `montant_ventes`.

---

## Codes hôtel

Formes rencontrées : `H0373`, `0373`, `373`, parfois alphanum.

Normalisation :

- admin / data_io : `normalize_hotel_code_value` / series  
- user fetch : `code_variants` (pad 4, préfixe H, …)  
- scrape URL : souvent 4 caractères  

---

## rod_reference.json

Structure attendue (simplifiée) :

```json
{
  "concepts": {
    "SIMPLY": {
      "pivot_nb_chambres": …,
      "pivot_to": …,
      "pivot_m_lin": …,
      "mix_fb": …,
      "base_monthly_ca": …,
      "cost_lines": [ { "id", "qty_default", "monthly_unit", "capex_unit", "amort_months", … } ]
    },
    "LIBERTY": { … },
    "CONNECTED": { … }
  },
  "impact_to": { … }
}
```

Lu par `user.reference.RodReference`.

---

## models/

| Chemin | Rôle |
|--------|------|
| `design/<slug>/model.pkl` | pickle MultiOutputRegressor + bundle features |
| `design/<slug>/config.json` | hyperparams, métriques, target_cols… |
| `deploy/model.pkl` + `model.json` | modèle « en prod » simu |
| `last_trained.json` | pointeur dernier build |
| `build_progress.json` | état batch (si présent) |
