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

Corps JSON principal :

| Champ | Rôle |
|-------|------|
| `hotel_code` | obligatoire |
| `nb_chambres`, `taux_occupation`, `guests_per_chambre` | exploitation (modifiable à l'écran) |
| `m_lin`, `mix_fb` | taille du corner et part F&B |
| `has_vitrine` | true si vitrine déjà en place |
| `client_needs` | catégories autorisées / non autorisées |

Réponse simplifiée :

- `recommended_solution` et les motifs
- `by_solution` pour Simply, Liberty, Connected : CA simulé, CA modèle (si dispo), coûts, marge
- `hotel` : synthèse des paramètres utilisés
- `disclaimer` : rappel que ce sont des estimations

```bash
curl -s -X POST http://127.0.0.1:5056/api/rod/simulate \
  -H 'Content-Type: application/json' \
  -d '{"hotel_code":"H0373","m_lin":6,"mix_fb":0.7,"has_vitrine":false}'
```

---

## Hôtels

### `GET /api/hotels/search?q=…`

Suggestions pour l'auto-complétion (code, nom, ville, marque).

### `GET /api/hotels/<code>/context`

Fiche et exploitation pour préremplir l'écran. Si la fiche manque, tentative
de récupération Accor (sans modifier durablement les tables métier hors upsert
ponctuel déjà prévu par le service).

---

## Notes

- Pas d'évaluation « vrai CA 2026 » côté user : beaucoup d'hôtels n'ont pas
  encore de ventes ; ils explorent une solution avant d'investir.
- Seul l'admin enregistre des données de façon permanente.
