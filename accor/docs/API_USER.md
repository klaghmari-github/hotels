# API User (port 5056)

Serveur : `python run_user.py` (ou `accor-user`).

Adresse locale : `http://127.0.0.1:5056`

Interface destinée au directeur d'hôtel : choisir un établissement, ajuster
le corner, obtenir une estimation. Aucune écriture en base depuis cette app.

---

## Page

### `GET /`

Parcours en quatre étapes (hôtel → établissement → offre → résultats).

### `GET /api/health`

État du service et liste des solutions connues.

---

## Simulation

### `GET /api/rod/meta`

Catégories de produits, valeurs par défaut (mix, mètres linéaires), repères
par solution.

### `POST /api/rod/simulate`

Tous les champs sont collectés **avant** le calcul (le client UI ne distingue
pas « champs simulateur » vs « champs IA »).

| Champ | Rôle |
|-------|------|
| `hotel_code` | obligatoire |
| `nb_chambres`, `taux_occupation`, `guests_per_chambre` | exploitation |
| `derniere_reno` | année de dernière rénovation (feature modèle) |
| `nb_restaurants`, `nb_bars` | compteurs F&B (feature modèle) |
| `has_pool` | piscine |
| `has_vitrine` | vitrine / frigo lobby déjà en place |
| `m_lin`, `mix_fb` | taille du corner et part F&B |
| `client_needs` | catégories autorisées / non autorisées |

Réponse :

- `recommended_solution` et motifs (arbre de reco métier)
- **`simulator.by_solution`** : pour chaque solution → `ca_mensuel`, `cout_mensuel`,
  `capex`, `marge_produit_mensuelle`, `marge_nette_mensuelle` / annuelle
- **`ai.by_solution`** : même structure ; CA issu du modèle ; coûts = sim ;
  marge produit proportionnelle au ratio sim
- `ai.available`, `ai.note`
- `hotel` : synthèse des paramètres utilisés
- `by_solution` : forme legacy (`ca_simule_mensuel` + `ca_predit_mensuel`)
- `disclaimer`

```bash
curl -s -X POST http://127.0.0.1:5056/api/rod/simulate \
  -H 'Content-Type: application/json' \
  -d '{"hotel_code":"H0373","m_lin":6,"mix_fb":0.7,"has_vitrine":false,"has_pool":false,"nb_restaurants":1,"nb_bars":0,"derniere_reno":2019}'
```

---

## Hôtels

### `GET /api/hotels/index`

Index léger (code, nom, marque, ville) pour filtrage **côté navigateur**.
Chargé une fois au démarrage du wizard (~tous les hôtels de `hotel_data`).

### `GET /api/hotels/search?q=…`

Suggestions serveur (code, nom, ville, marque). `q` vide = aperçu de la base.
Utilisé en secours ; le wizard filtre surtout en local sur l'index.

### `GET /api/hotels/<code>/context`

Fiche et exploitation pour préremplir l'écran.

- Si le code existe dans `hotel_data` / `model_data` : lecture seule.
- Sinon scrape Accor **en session uniquement** (`persist=0` par défaut) :
  aucune écriture dans `hotel_data.xlsx`. L'hôtel n'existe que le temps de
  la session navigateur (mémoire JS + réponse API).
- `persist=1` : upsert Excel (outils / admin uniquement, pas l'UI user).

---

## Notes

- Pas d'évaluation « vrai CA 2026 » côté user : beaucoup d'hôtels n'ont pas
  encore de ventes ; ils explorent une solution avant d'investir.
- Seul l'admin enregistre des données de façon permanente.
