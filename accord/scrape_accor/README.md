# Scrape all.accor.com — marques & hôtels

## Marques

```bash
cd accord
python -m scrape_accor.brands              # scrape + logos par catégorie
python -m scrape_accor.brands --force      # retélécharge les logos
python -m scrape_accor.brands --reorganize-only  # réorganise un scrape existant
```

Sortie :

* `data/marques/marques.xlsx` — **`marque_nom` en MAJUSCULES** (jointures)
* `data/marques/{categorie_slug}/{slug}.png` — logos par sous-dossier catégorie  
  ex. `economy/ibis_budget.png`, `midscale/mercure.png`

Source : https://all.accor.com/a/fr/brands.html

## Hôtels (parallèle par plages)

Chaque worker traite une plage exclusive d’IDs et écrit son fichier :

`data/marques/hotels/hotels_1000_1099.xlsx`

```bash
cd accord

# Un seul range (test)
python -m scrape_accor.worker --start 1140 --end 1150 --worker-id test

# Orchestrateur (jusqu'à 12 workers, plages de 100, IDs 1000–8000)
python -m scrape_accor.orchestrator --max-workers 12 --range-size 100 \
  --id-min 1000 --id-max 8000 --target-hotels 4000 --pause 0.45

# Fusion de toutes les plages
python -m scrape_accor.orchestrator --merge-only
```

### Anti-collision

* Claim fichier `data/marques/hotels_state/claim_{start}_{end}.json`
* Progress partiel `progress_{start}_{end}.json` (reprise possible)
* Pas d’écriture partagée sur le même xlsx

### Respect du site

* Pause entre requêtes (`--pause`, défaut 0.45 s)
* Jusqu’à **12 agents** en parallèle (défaut actuel)
* User-Agent identifiable

## Schéma hôtel (feuille `hotels`)

| Colonne | Description |
|---------|-------------|
| hotel_code_accor | ID numérique Accor |
| hotel_name | Nom |
| hotel_brand | Marque |
| hotel_adresse / complement / code_postal / city / country | Adresse |
| hotel_lat / hotel_lon | GPS |
| services_f_b / services_n_f_b | Amenities classées |
| has_restaurant, has_bar, has_parking, … | Flags 0/1 |

## Liste loyalty opt-in (manquants)

Page : https://all.accor.com/loyalty-program/optin-htl/index.fr.shtml  
(API catalog `q=france`, ~18 pages × 100)

```bash
cd accord
python -m scrape_accor.loyalty_list
# option: --q france
```

Sorties dans `data/marques/hotels/` :

* `loyalty_optin_all.xlsx` — liste complète page/API
* `loyalty_optin_missing.xlsx` / `.csv` — absents de `hotels_all.xlsx`
* `loyalty_optin_matched.xlsx` — déjà présents

## Monde (70 pays — catalog + manquants + scrape)

Liste dans `scrape_accor/countries_config.py` (Europe, Afrique/ME, Asie, Océanie, Amériques).

```bash
cd accord
# Catalog seul → world_missing.xlsx
python -m scrape_accor.world_scrape --catalog-only

# Scrape des manquants (parallèle) + merge hotels_all
python -m scrape_accor.world_scrape --scrape-missing --workers 12 --threads 3

# Tout-en-un (12 agents max)
python -m scrape_accor.world_scrape --all --workers 12 --threads 3

# Une région
python -m scrape_accor.world_scrape --region asia --all
```

Sorties clés :
* `world_catalog_all.xlsx` — codes uniques multi-pays
* `world_missing.xlsx` — absents de `hotels_all` avant scrape
* `hotels_missing_world.xlsx` — fiches scrapées
* `{slug}_destination_*.xlsx` — détail par pays
* `world_catalog_summary.json`

## Destination pays (catalog + manquants)

Pays : config complète dans `countries_config.py` + legacy flags

```bash
cd accord
python -m scrape_accor.destination_country --all-targets --skip-html
python -m scrape_accor.destination_country --country italy
```

Sorties : `{slug}_destination_{all,missing,matched}.*` + `multi_countries_missing.xlsx`

## Hôtels France (destination + manquants)

Page : https://all.accor.com/a/fr/destination/country/hotels-france-pfr.html

* HTML SSR : `?pageIndex=1..50` (~6 hôtels/page, ~300 max)
* Liste complète : API catalog `q=france` (~1747)

```bash
cd accord
python -m scrape_accor.destination_france
# rapide (API seule) :
python -m scrape_accor.destination_france --skip-html
# HTML limité :
python -m scrape_accor.destination_france --max-html-pages 10
```

Sorties dans `data/marques/hotels/` :

* `france_destination_all.xlsx` — catalogue France (API + ratings HTML)
* `france_destination_missing.xlsx` / `.csv` — absents de `hotels_all.xlsx`
* `france_destination_matched.xlsx` — déjà scrapés
* `france_destination_summary.json`

## Scrape par liste de codes (alphanum + pad 4)

Les codes Accor sont souvent sur **4 caractères** (`0785`, `A7L5`, `B625`).
Le scrape par plage entière `785` sans zéro à gauche rate ces fiches.

```bash
cd accord

# Liste (ex. 748 manquants France)
python -m scrape_accor.scrape_codes \
  --from-xlsx data/marques/hotels/france_destination_missing.xlsx \
  --out hotels_missing_france.xlsx --workers 12

# Plage 0–999 forcée en 4 chiffres (0000..0999)
python -m scrape_accor.scrape_codes --pad4-range 0 999 \
  --out hotels_0000_0999.xlsx --workers 12

# Fusion
python -m scrape_accor.orchestrator --merge-only
```

Options utiles : `--codes A7L5,0785`, `--force` (ignore progress), `--no-skip-existing`.

### Parallèle multi-process (recommandé pour listes longues)

```bash
cd accord
# 12 process agents, shards auto, merge + hotels_all
python -m scrape_accor.parallel_codes \
  --from-xlsx data/marques/hotels/france_destination_missing.xlsx \
  --out hotels_missing_france.xlsx --workers 12 --pause 0.25
```

Jusqu’à **12 process agents** en parallèle (défaut). Chaque worker écrit `hotels_*_shardNN.xlsx`, le parent fusionne.

Colonnes utiles pour le scrape suivant : `hotel_code_accor`, `url_hotel`.
