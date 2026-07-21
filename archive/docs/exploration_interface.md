# Interface d’exploration des données et du modèle

Page réservée à l’administration technique. Elle décrit le parcours des fichiers sources jusqu’aux prédictions, et permet d’inspecter le modèle XGBoost.

## Accès

| Élément | Valeur |
|---------|--------|
| Lancement | `python run_admin.py` |
| URL | http://127.0.0.1:5001/exploration |
| Prérequis | `./init.sh` |

L’interface utilisateur (directeurs d’hôtel) ne propose pas cette page. Elle est accessible uniquement via le serveur d’administration.

## Onglets

1. **Données** — parcours du dataset d’entraînement
2. **Modèle** — arbres de régression et prédiction manuelle

## Onglet Données

Chaque étape du pipeline est présentée dans un bloc repliable. Un filtre permet de choisir un hôtel pivot ou d’afficher tous les hôtels. Les tableaux montrent un échantillon de lignes et de colonnes.

### Étape 1 — Données source ventes

Extrait de `001.queryVentes.csv` : boutique, date, type, gamme, montant.

### Étape 2 — Saisie utilisateur et registre

Chambres, taux d’occupation, guests, marque, ville. Valeurs issues du registre identité et des saisies enregistrées dans le feature store.

### Étape 3 — Enrichissement ROD et marques

Nombre d’hôtels par marque et par tranche de taille (fichier projections Excel), plus un échantillon des champs récap ROD.

### Étape 4 — Météo et commerces de proximité

Coordonnées, comptage de commerces par rayon, indicateurs météo mensuels lorsque le cache géographique existe. Sinon, seules les coordonnées du registre sont affichées.

### Étape 5 — Format numérique nettoyé

Contenu de `X_descriptive.csv` après imputation et sélection des variables. Les champs textuels ne sont pas injectés dans le modèle.

### Étape 6 — Variables cibles

Dataset complet : features descriptives et cibles mensuelles (`t_m01_ca_total`, ventes par type et gamme, etc.).

### Étape 7 — Conversion en pourcentages

Répartitions mensuelles F&B / non-F&B et par gamme, issues de `train_percentages_long.csv`.

## Onglet Modèle

Le modèle est un XGBoost multi-sorties : 120 arbres par sortie, 24 sorties globales (CA et ventes totales pour chaque mois).

### Visualiser un arbre

1. Choisir la sortie (par exemple avril — CA)
2. Indiquer le numéro d’arbre (1 à 120)
3. Cliquer sur « Afficher l’arbre »

Les seuils et feuilles sont affichés. Les identifiants `f0`, `f1` sont traduits en libellés `d_...` lorsque c’est possible.

### Prédiction interactive

1. Choisir un hôtel de référence (ou laisser la moyenne des pivots)
2. Modifier des variables : chambres, TO, guests, parts F&B, etc.
3. Lancer le calcul

Résultats : totaux annuels et mensuels, tableau mois par mois, ventilation estimée par type et gamme (répartition selon les pourcentages historiques de l’hôtel).

## Routes HTTP

| Route | Rôle |
|-------|------|
| `GET /api/data-exploration?hotel_id=` | Échantillons des sept étapes |
| `GET /api/model-exploration/meta` | Liste des sorties et des arbres |
| `GET /api/model-exploration/tree?target_index=&tree_number=` | Structure JSON d’un arbre |
| `POST /api/model-exploration/predict` | Prédiction avec surcharge de variables |

## Fichiers source

| Fichier | Rôle |
|---------|------|
| `rod_ia/domain/services/data_exploration_service.py` | Construction des échantillons |
| `rod_ia/domain/services/model_exploration_service.py` | Arbres et prédictions |
| `rod_ia/api/routes/exploration.py` | Routes HTTP |
| `rod_ia/web/exploration.html` | Page |
| `rod_ia/web/exploration.js` | Logique interface |

## Modèle et artefacts

| Situation | Commande |
|-----------|----------|
| Première installation | `./init.sh` |
| Dataset présent, modèle absent | `python -m rod_ia.pipelines.train_model` |
| Réentraînement forcé | `python -m rod_ia.pipelines.train_model --force` |
| Reconstruction dataset + entraînement | `python -m rod_ia.pipelines.train_model --rebuild-dataset` |

Vérification : `GET /api/model/status` (disponible sur le serveur d’administration).

Sans modèle chargé, l’onglet Modèle affiche un avertissement. Dans le simulateur, les prédictions retombent alors sur les règles ROD.