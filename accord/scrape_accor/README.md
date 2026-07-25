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

# Orchestrateur (4 workers, plages de 100, IDs 1000–8000, stop à 4000 hôtels)
python -m scrape_accor.orchestrator --max-workers 4 --range-size 100 \
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
* Nombre de workers raisonnable (3–5 recommandé)
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
