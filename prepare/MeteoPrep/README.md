# MeteoPrep — Étape 2

Récupération et structuration des données météo mensuelles par hôtel, avec libellés lisibles et imputation des valeurs manquantes.

## Objectif

Produire une table `hotel_code × annee × mois` avec des indicateurs météo renommés (température, humidité, précipitations…).

**Années cibles :** si non fournies → **année en cours**. Les mois manquants d'une année sont complétés par le **même mois de l'année précédente** (jamais d'imputation à 0).

## Fichiers

| Dossier | Contenu |
|---------|---------|
| `Input/` | `hotels.parquet` / `hotels.csv` (champs d'identité issus de RodPrep) |
| `Output/` | `meteo_monthly.parquet`, `meteo_monthly.csv` |
| `Explore/` | `explore.ipynb` — exploration pas-à-pas ; remplit `Output/` |
| `Src/meteo_prep/prep.py` | Classe `MeteoPrep` |

## Entrées (identité hôtel)

| Champ | Origine | Rôle |
|-------|---------|------|
| `hotel_code` | RodPrep | Identifiant hôtel (code Accor) |
| `hotel_name` | RodPrep | Nom affiché |
| `hotel_brand` | RodPrep | Marque |
| `hotel_city` | RodPrep | Ville |
| `hotel_lat` | RodPrep | **Latitude** — point météo |
| `hotel_lon` | RodPrep | **Longitude** — point météo |
| `hotel_adresse` | Optionnel | Fallback uniquement si lat/lon absentes |

Les coordonnées sont renseignées par RodPrep (récap, registre ou géocodage). La météo s'appuie sur `hotel_lat` / `hotel_lon` (stations Meteostat les plus proches du point).

## Source météo

Données horaires Meteostat au point `(hotel_lat, hotel_lon)` (stations les plus proches), agrégées par mois via `EnrichHotelService._fetch_weather_12_months`. Seule la météo est demandée (pas de POI / plage).

| Préfixe brut | Exemple |
|--------------|---------|
| `d_m{MM}_{metric}_{stat}` | `d_m03_temp_mean` |

Métriques brutes : `temp`, `dwpt`, `rhum`, `prcp`, `snow`, `wspd`, `pres`, `tsun`.  
Statistiques : `mean`, `min`, `max`.

## Traitement

1. `fill_input_from_rod` : copie les champs d'identité depuis `RodPrep/Output/hotel_lookup` (sans `hotel_code` null).
2. Pour chaque hôtel : météo au point `(hotel_lat, hotel_lon)` agrégée par `(année, mois)` ; si coords manquantes, géocodage nom/ville/adresse.
3. Génération d'une grille `hotel_code × annee × mois` (années cibles + année N-1 pour imputation).
4. Imputation des mois manquants : même mois de l'année précédente (pas de fill à 0).
5. Filtrage sur les années cibles puis écriture `Output/`.

## Sorties calculées

| Champ | Méthode |
|-------|---------|
| `hotel_code` | Reprise entrée |
| `hotel_name` | Reprise entrée |
| `annee` | Années cibles (`target_years`, défaut = année en cours) |
| `mois` | 1 à 12 |
| `meteo_temperature_c_mean` | Renommage de `d_m{MM}_temp_mean` |
| `meteo_temperature_c_min` | Renommage de `d_m{MM}_temp_min` |
| `meteo_temperature_c_max` | Renommage de `d_m{MM}_temp_max` |
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

**Année absente dans les observations API :** rattachée à l'année en cours.

**Note :** `run_prepare.py` passe explicitement une plage d'années (N-3 … N) pour couvrir la jointure ventes.

## Exécution

```bash
python run_prepare.py   # sans --skip-meteo
```

Ou notebook : `prepare/MeteoPrep/Explore/explore.ipynb`.
