# API REST de prédiction

Serveur HTTP autonome, distinct des interfaces web. Il reçoit les paramètres hôtel saisis dans le simulateur, enrichit les données via le feature store, applique les règles ROD et le modèle de prédiction, puis renvoie les estimations par concept.

## Démarrage

```bash
python run_api.py
```

| Élément | Valeur |
|---------|--------|
| URL de base | http://127.0.0.1:5002 |
| Santé | `GET /health` |
| Informations | `GET /api/v1` |
| Prédiction | `POST /api/v1/predict` |

Prérequis : `./init.sh` exécuté au moins une fois (dataset, modèle, feature store).

## Endpoint principal

### `POST /api/v1/predict`

Corps de requête en JSON. La structure reprend celle du simulateur web (`POST /api/simulate` sur l’interface utilisateur).

#### Champs principaux

| Bloc | Rôle |
|------|------|
| `identity` | Nom, ville, adresse, marque, `hotel_id` optionnel |
| `operating` | Chambres, taux d’occupation, guests par chambre |
| `general` | Contrat, rénovations, PMS, panier moyen (informatif) |
| `services` | Bar, restaurant, minibar, équipements lobby |
| `client_profile` | Répartition clients, besoins assortiment |
| `corner` | Corner existant, mètres linéaires, emplacement |
| `constraints` | Catégories exclues, champs verrouillés |
| `store` | Mix F&B et mètres linéaires (surcharge optionnelle) |
| `force_refresh` | `true` pour recalculer POI et météo (ignorer le cache) |

#### Exemple minimal

```bash
curl -X POST http://127.0.0.1:5002/api/v1/predict \
  -H "Content-Type: application/json" \
  -d '{
    "identity": {
      "hotel_name": "Ibis budget Nice",
      "city": "Nice",
      "brand": "IBIS_BUDGET"
    },
    "operating": {
      "nb_chambres": 129,
      "taux_occupation": 0.80,
      "guests_per_chambre": 1.7
    },
    "corner": { "m_lin": 6 }
  }'
```

#### Exemple complet (équivalent interface simulateur)

```json
{
  "identity": {
    "hotel_name": "IBIS ALES CENTRE VILLE",
    "address": "",
    "city": "Alès",
    "brand": "IBIS"
  },
  "operating": {
    "nb_chambres": 78,
    "taux_occupation": 0.65,
    "guests_per_chambre": 1.7
  },
  "general": {
    "adults_per_room": 1.5,
    "children_per_room": 0.2
  },
  "client_profile": {
    "client_needs": {
      "fb_soft_drinks": 80,
      "nfb_sos": 60
    }
  },
  "corner": {
    "has_existing_corner": false,
    "m_lin": 5
  },
  "constraints": {
    "excluded_categories": []
  },
  "store": {
    "m_lin": 5,
    "mix": { "fb_share": 0.8, "non_fb_share": 0.2 }
  }
}
```

## Structure de la réponse

La réponse est un objet JSON. Les données d’entrée sont renvoyées dans `input`, complétées par `hotel_id` et les features enrichies.

| Section | Contenu |
|---------|---------|
| `input` | Requête reçue, enrichie (`hotel_id`, `enriched`) |
| `context` | Données contextuelles : proximité, météo, règles ROD, feature store |
| `predictions` | Résultats pour SIMPLY, LIBERTY, CONNECTED |
| `recommendation` | Concept retenu et justification |
| `warnings` | Messages d’avertissement éventuels |

### `context`

| Sous-bloc | Description |
|-----------|-------------|
| `hotel_id` | Identifiant canonique (registre identité) |
| `enrichment_source` | `cache` ou `computed` |
| `registry_hotels_count` | Nombre d’hôtels dans le registre |
| `proximity` | Distance plage, commerces F&B et non-F&B (100 m et 500 m) |
| `weather` | Indicateurs météo mensuels chargés depuis le feature store |
| `feature_store` | Métadonnées et nombre de features récap |
| `rod_rules` | Paramètres pilotes et coûts par concept (référence Excel) |

### `predictions.{CONCEPT}`

Pour chaque concept (SIMPLY, LIBERTY, CONNECTED) :

| Champ | Description |
|-------|-------------|
| `ca_annuel` | Chiffre d’affaires annuel estimé |
| `nbr_ventes_annuel` | Nombre de ventes annuel |
| `marge_annuelle` | Marge nette annuelle |
| `cout_annuel` | Coûts annuels (technos, annexes, agencement…) |
| `ca_mensuel_moyen` | CA mensuel moyen |
| `monthly` | Tableau de 12 mois : `ca`, `nbr_ventes`, `marge_nette`, `cout` |
| `costs_breakdown` | Détail des postes de coût |
| `source` | Origine du calcul (`AI_MODEL` ou fallback ROD) |

### `recommendation`

| Champ | Description |
|-------|-------------|
| `concept` | Concept recommandé (meilleure marge nette ROD parmi les concepts autorisés) |
| `best_margin_concept` | Concept à la marge la plus élevée |
| `reason` | Texte explicatif |

## Traitement interne

1. Résolution de l’hôtel dans `hotel_identity_registry.json`
2. Lecture ou calcul des données géographiques (`feature_store/hotels/{hotel_id}/geo/enriched.json`)
3. Persistance des saisies directeur dans le feature store
4. Construction de la configuration store par concept
5. Simulation ROD (règles Excel) et prédiction modèle (profil mensuel sur 12 mois)
6. Calcul du P&L : marge produit, coûts, marge nette
7. Recommandation selon les règles métier

## Codes d’erreur

| Code | Cas |
|------|-----|
| 400 | Corps JSON absent ou champ `identity` manquant |
| 500 | Erreur de traitement (détail dans `error`) |

## Fichiers concernés

| Fichier | Rôle |
|---------|------|
| `run_api.py` | Point d’entrée |
| `rod_ia/api/api_factory.py` | Application Flask API |
| `rod_ia/api/routes/prediction.py` | Route HTTP |
| `rod_ia/domain/services/prediction_api_service.py` | Orchestration métier |
| `tests/test_prediction_api.py` | Tests unitaires |