# scrape_accor (prod)

Scrape unitaire d’une fiche hôtel Accor. Sert surtout quand le directeur
saisit un code encore absent de `hotel_data.xlsx`.

## Modules

| Fichier | Rôle |
|---------|------|
| `hotels.py` | parse `https://all.accor.com/hotel/{code}/index.fr.shtml` |
| `http_util.py` | GET HTTP, User-Agent, erreurs basiques |

## Via le parcours user (recommandé)

```python
from accor.user.services.hotel_fetch import fetch_and_upsert_hotel

result = fetch_and_upsert_hotel("H0338")
# scrape si besoin, upsert data/hotel_data.xlsx, invalide les caches
```

L’API `GET /api/hotels/<code>/context` déclenche ce flux quand le code
n’est pas en base.

## Bas niveau

```python
from accor.scrape_accor.hotels import fetch_hotel, parse_hotel_html

row = fetch_hotel("0338")  # dict brut fiche Accor
```

Mapping vers le schéma `hotel_data` : `scrape_to_hotel_row` dans
`user.services.hotel_fetch`.

Pas de boucle massive ici. Pour reconstituer un parc (plages d’IDs,
multi-pays…), utiliser l’archive `../accor_1_0_0/`.
