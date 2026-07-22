# Accord Data Studio

Interface web de **saisie WYSIWYG** des fichiers Excel `accord/data/`.

## Onglets

| Onglet | Fichier | Colonnes affichées |
|--------|---------|-------------------|
| Hotel Brand Data | `hotel_brand_data.xlsx` | Effectifs `Nb_*` (pas les `Pct_*` calculés) |
| Hotel Data | `hotel_data.xlsx` | Identité, équipements, corner (pas les one-hot brand) |
| Hotel Weather Data | `hotel_weather_data.xlsx` | Identité + métriques météo |
| Hotel Sales Data | `hotel_sales_data.xlsx` | Base ventes mensuelles (pas cat_/heure_ calculés) |
| Hotel Holidays Data | `hotel_holidays_data.xlsx` | Fériés / vacances + arrays de jours |
| **All Data** | `data.xlsx` | Grille hotel × année × mois + fill auto météo / proximité |

### Onglet All Data

- Fichier : `accord/data/data.xlsx`
- Grille **parfaite** : chaque hôtel (`hotel_data`) × chaque année × 12 mois
- Identité (`hotel_name`, brand, lat/lon) toujours remplie depuis `hotel_data`
- **Météo** : trous comblés via `WeatherFromGeo(lat, lon)` (Meteostat)
- **Proximité** : trous comblés via `ProximityFromGeo(lat, lon)` (Overpass)
- **Ventes** : seules colonnes autorisées à rester vides
- Bouton **Rebuild All Data** (ou `POST /api/datasets/data/rebuild`)
- Pas de colonnes en double

## Lancer

```bash
cd accord
python run.py
# → http://127.0.0.1:5055
```

Options : `python run.py --port 8080 --debug`

## Fonctions UI

- Tables éditables page par page (pagination)
- Filtre / recherche
- Enregistrement Excel (Ctrl+S)
- Ajout / suppression de lignes
- Rechargement depuis le disque
- Design sombre premium (navy + or)

## API

| Méthode | Route |
|---------|-------|
| GET | `/api/datasets` |
| GET | `/api/datasets/<id>?page=1&page_size=25&q=` |
| PUT | `/api/datasets/<id>/rows` body `{ "rows": [{ "_index": 0, ... }] }` |
| POST | `/api/datasets/<id>/rows` |
| DELETE | `/api/datasets/<id>/rows` body `{ "indices": [0,1] }` |
| POST | `/api/datasets/<id>/reload` |
