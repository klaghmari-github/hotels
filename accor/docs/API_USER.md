# API User (port 5056)

Serveur : `accor.user.app` — `python run_user.py` ou `accor-user`.

Base URL : `http://127.0.0.1:5056`

Static servi depuis `PROJECT_ROOT/static` (user + shared).

---

## Pages

### `GET /`

Wizard directeur (`templates/user/index.html`).

### `GET /api/health`

```json
{
  "status": "ok",
  "app": "accord-rod-user",
  "concepts": ["SIMPLY", "LIBERTY", "CONNECTED"],
  "reference_loaded": true
}
```

---

## Méta UI

### `GET /api/meta`

Alimente le front : pivots par concept, besoins clients F&B / N-F&B
(labels + défauts), résumé des règles, défauts modèle.

### `GET /api/brands`

```json
{ "brands": [ { "Marque": "IBIS", … }, … ] }
```

Source : `hotel_brand_data.xlsx` via `AdminCatalog`.

### `GET /api/concept_pilote/brand/<path:brand>`

Moyennes d’exploitation pour une marque (étape 1 du wizard).

- Lit `concept_pilote.xlsx`
- Filtre la marque
- Exclut en général l’année la plus récente (hold-out type 2026)
- Renvoie aussi un bloc `rule1` (CA attendu par concept après impact TO + R1)

404 si marque sans données.

---

## Hôtels

### `GET /api/hotels`

Liste complète des fiches `hotel_data`. Peut être lourde — préférer
`/search` pour l’UI.

### `GET /api/hotels/search`

Autocomplete.

| Query | Défaut | Rôle |
|-------|--------|------|
| `q` / `query` | | code, nom, ville, marque |
| `limit` | 20 (max 50) | nombre de résultats |

```json
{ "ok": true, "q": "montmartre", "n": 3, "hotels": [ … ] }
```

### `GET /api/hotels/<hotel_code>`

Fiche brute. 404 si inconnu.

### `GET /api/hotels/<hotel_code>/context`

Contexte complet pour le wizard + payload simulation.

| Query | Défaut | Rôle |
|-------|--------|------|
| `fetch` | 1 | si `0`/`false`, ne scrape pas si absent |

Comportement :

1. Charge `hotel_data` + agrégats `model_data` si le code existe.
2. Sinon, si `fetch` actif : scrape
   `all.accor.com/hotel/{code}/`, upsert `hotel_data`, invalide le cache
   catalogue.

Réponse : identité, operating, sources, `payload` prêt pour `/api/simulate`,
flag `scraped`.

---

## Géocode & enrichissement

### `POST /api/geocode`

Localise lat/lon.

Body (tous optionnels, combiner ce qu’on a) :

```json
{
  "street": "…",
  "postal_code": "75018",
  "city": "Paris",
  "hotel_name": "…",
  "hotel_code": "0373",
  "accor_url": "https://all.accor.com/hotel/0373/…"
}
```

Ordre des sources : BAN (data.gouv) → fiche Accor → Nominatim.

HTTP 200 même en échec métier : lire `ok` dans le JSON.

### `POST /api/enrich`

Complète un `SimulationRequest` (proximity, weather, holidays, coords).

```json
{
  "identity": { … },
  "operating": { … },
  "light": false
}
```

`light: true` saute Overpass / Meteostat (plus rapide).

---

## Règle 1 (aperçu)

### `POST /api/rule1`

Aperçu impact TO + scaling clients pour les 3 concepts, sans lancer la
simu complète.

```json
{
  "nb_chambres": 100,
  "taux_occupation": 0.75,
  "guests_per_chambre": 1.7
}
```

`taux_occupation` : 0–1 ou pourcentage selon le helper backend.

---

## Simulation

### `POST /api/simulate`

Simulation multi-concepts (SIMPLY / LIBERTY / CONNECTED) + recommandation.

Query / body :

| Champ | Rôle |
|-------|------|
| `light` / `light_enrich` | saute enrichissement lourd |
| body = `SimulationRequest` | identity, operating, services, client_profile, corner… |
| `hotel_code` seul | hydrate 100 % depuis admin (context) |

Réponse (extrait) :

```json
{
  "ok": true,
  "by_concept": {
    "SIMPLY": { "revenue": {…}, "costs": {…}, "marge_nette_mensuelle": … },
    "LIBERTY": { … },
    "CONNECTED": { … }
  },
  "recommended_concept": "LIBERTY",
  "warnings": [ … ],
  "calc_summary": { … }
}
```

`calc_summary` détaille le concept recommandé (clients hôtel/pilote,
facteur, CA).

---

## Exemples curl

```bash
curl -s 'http://127.0.0.1:5056/api/hotels/search?q=H0373'

curl -s 'http://127.0.0.1:5056/api/hotels/H0373/context'

curl -s -X POST http://127.0.0.1:5056/api/simulate?light=1 \
  -H 'Content-Type: application/json' \
  -d '{"hotel_code":"H0373"}'
```
