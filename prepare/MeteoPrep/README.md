# MeteoPrep — Étape 2

Récupération et structuration des données météo mensuelles par hôtel, avec libellés lisibles et imputation des valeurs manquantes.

## Objectif

Produire une table `hotel_code × annee × mois` avec des indicateurs météo renommés (température, humidité, précipitations…).

**Années cibles :** si non fournies → **année en cours**. Les mois manquants d'une année sont complétés par le **même mois de l'année précédente** (jamais d'imputation à 0).

## Architecture

| Module | Classe | Rôle |
|--------|--------|------|
| `Src/meteo_prep/weather.py` | `MonthlyWeather` | **Indépendant du domaine hôtel** : coordonnées + années → indicateurs par année × mois × point |
| `Src/meteo_prep/prep.py` | `MeteoPrep` | Orchestration pipeline : I/O hôtels, délégation météo, imputation, écriture `Output/` |

`MonthlyWeather` ne fait **pas** de géocodage d'adresse. Les coordonnées doivent être fournies ; leur résolution (adresse → lat/lon) est le rôle d'une autre étape (ex. RodPrep).

## Fichiers

| Dossier | Contenu |
|---------|---------|
| `Input/` | `hotels.parquet` / `hotels.csv` (champs d'identité issus de RodPrep) |
| `Output/` | `meteo_monthly.parquet`, `meteo_monthly.csv` |
| `Explore/` | `explore.ipynb` — exploration pas-à-pas ; remplit `Output/` |
| `Src/meteo_prep/weather.py` | `MonthlyWeather`, imputation générique |
| `Src/meteo_prep/prep.py` | Classe `MeteoPrep` |

## Entrées (identité hôtel)

| Champ | Origine | Rôle |
|-------|---------|------|
| `hotel_code` | RodPrep | Identifiant hôtel (code Accor) |
| `hotel_name` | RodPrep | Nom affiché |
| `hotel_brand` | RodPrep | Marque |
| `hotel_city` | RodPrep | Ville |
| `hotel_lat` | RodPrep | **Latitude** — point météo (obligatoire) |
| `hotel_lon` | RodPrep | **Longitude** — point météo (obligatoire) |

Sans `hotel_lat` / `hotel_lon` exploitables, la ligne hôtel est émise avec une grille année×mois vide (NaN), **sans** fallback adresse.

## `MonthlyWeather` (API pure)

```python
from meteo_prep import MonthlyWeather

# --- Tout-en-un : geo + années → meteo_final (grille + imputation + filtre) ---
meteo_final = MonthlyWeather.compute_meteo_final(
    geo_df,                          # colonnes lat / lon (+ ids optionnels)
    years=(2024, 2025, 2026),
    lat_col="lat",
    lon_col="lon",
    id_cols=("point_id",),           # optionnel
)

# Étapes bas niveau (exploration)
mw = MonthlyWeather(years=(2024, 2025, 2026))
df = mw.for_point(lat=43.69, lon=7.24)
df = mw.for_points(locations_df, lat_col="lat", lon_col="lon", id_cols=("point_id",))
```

Équivalent côté pipeline hôtel :

```python
meteo_final = prep.compute_meteo_final(geo=hotels, years=(2024, 2025, 2026))
```

| Entrée | Sortie |
|--------|--------|
| geo + liste d'années | `meteo_final` : grille `annee × mois` par point, imputée, filtrée |
| Observations absentes | Cellules NaN puis imputation N←N-1 (jamais fill à 0) |

## Source météo

Données horaires Meteostat au point `(lat, lon)` (stations les plus proches), agrégées par `(année, mois)`.

| Préfixe brut | Exemple |
|--------------|---------|
| colonnes Meteostat | `temp`, `dwpt`, `rhum`, … |

Métriques brutes : `temp`, `dwpt`, `rhum`, `prcp`, `snow`, `wspd`, `pres`, `tsun`.  
Statistiques : `mean`, `min`, `max`.

## Traitement (`MeteoPrep.run`)

1. `fill_input_from_rod` : copie les champs d'identité depuis `RodPrep/Output/hotel_lookup` (sans `hotel_code` null).
2. Pour chaque hôtel : météo au point `(hotel_lat, hotel_lon)` via `MonthlyWeather` (années cibles + N-1 pour imputation).
3. Génération d'une grille `hotel_code × annee × mois`.
4. Imputation des mois manquants : même mois de l'année précédente (pas de fill à 0).
5. Filtrage sur les années cibles puis écriture `Output/`.

## Sorties calculées

| Champ | Méthode |
|-------|---------|
| `hotel_code` | Reprise entrée |
| `hotel_name` | Reprise entrée |
| `annee` | Années cibles (`target_years`, défaut = année en cours) |
| `mois` | 1 à 12 |
| `meteo_temperature_c_mean` | Renommage de `temp` mean |
| `meteo_temperature_c_min` | Renommage de `temp` min |
| `meteo_temperature_c_max` | Renommage de `temp` max |
| `meteo_point_rosee_c_{stat}` | `dwpt` → point de rosée (°C) |
| `meteo_humidite_pct_{stat}` | `rhum` → humidité relative (%) |
| `meteo_precipitations_mm_{stat}` | `prcp` → précipitations (mm) |
| `meteo_neige_mm_{stat}` | `snow` → neige (mm) |
| `meteo_vent_kmh_{stat}` | `wspd` → vent (km/h) |
| `meteo_pression_hpa_{stat}` | `pres` → pression (hPa) |
| `meteo_ensoleillement_min_{stat}` | `tsun` → ensoleillement (minutes) |

`{stat}` ∈ {`mean`, `min`, `max`}.

## Formules et règles

**Renommage :**

```
meteo_{READABLE_MAP[metric]}_{stat}
```

avec `READABLE_MAP = {temp: temperature_c, dwpt: point_rosee_c, rhum: humidite_pct, …}`.

**Imputation (par `hotel_code`, colonne `meteo_*`) :**

1. Si valeur manquante pour `(annee=Y, mois=M)` → reprendre `(Y-1, M)`, puis `(Y-2, M)`, …
2. **Jamais** d'imputation à `0.0` : si aucune année antérieure n'a la valeur, le NaN est conservé.

**Note :** `run_prepare.py` passe explicitement une plage d'années (N-3 … N) pour couvrir la jointure ventes.

## Exécution

```bash
python run_prepare.py   # sans --skip-meteo
```

Ou notebook : `prepare/MeteoPrep/Explore/explore.ipynb`.
