# Interface d exploration des donnees et du modele

Cette page decrit les onglets accessibles depuis le menu Exploration du simulateur ROD. Elle s adresse aux equipes qui veulent comprendre comment les fichiers sources deviennent des predictions, sans passer par la ligne de commande.

## Acces

Adresse : `/exploration` depuis l application web (apres `./init.sh` ou `./run.sh`).

Deux onglets :

1. Donnees — parcours du dataset
2. Modele — arbres de regression et prediction manuelle

## Onglet Donnees

L objectif est de montrer, etape par etape, comment les ventes brutes et les saisies hotelieres sont transformees avant l entrainement du modele.

Vous pouvez filtrer sur un hotel pivot ou afficher tous les hotels. Chaque bloc est repliable. Les tableaux montrent un echantillon de lignes et de colonnes pour rester lisible a l ecran.

### Etape 1 — Donnees source ventes

Extrait du fichier `001.queryVentes.csv` : boutique, date, type, gamme, montant. C est la matiere premiere avant toute moyenne mensuelle.

### Etape 2 — Saisie utilisateur et registre

Chambres, taux d occupation, guests, marque, ville. Ces valeurs viennent du registre identite et des saisies directeur enregistrees dans le feature store.

### Etape 3 — Enrichissement ROD et marques

Nombre d hotels par marque et par tranche de taille (fichier projections Excel), plus un echantillon des champs recap ROD (TO, chambres, equipements).

### Etape 4 — Meteo et geolocalisation commerce

Latitude, longitude, comptage de commerces de proximite par rayon, indicateurs meteo mensuels lorsque le cache geo existe pour l hotel. Sinon seules les coordonnees registre sont affichees.

### Etape 5 — Format numerique nettoye

Contenu de `X_descriptive.csv` : variables retenues apres imputation, suppression des champs constants et des doublons. Les colonnes categorielles textuelles ne sont pas injectees dans le modele.

### Etape 6 — Ajout des variables cibles

Vue du dataset complet : features descriptives plus cibles mensuelles `t_m01_ca_total`, ventes par type et gamme, etc.

### Etape 7 — Conversion en pourcentages

Repartitions mensuelles type F&B / NON-F&B et par gamme, issues de l historique d entrainement (fichier `train_percentages_long.csv`).

## Onglet Modele

Le modele actuel est un XGBoost multi sorties : une serie de 120 arbres par sortie predite, soit 24 sorties globales (CA et ventes totales pour chaque mois).

### Visualiser un arbre

1. Choisir la sortie (par exemple Avril CA)
2. Indiquer le numero d arbre entre 1 et 120
3. Cliquer sur Afficher l arbre

L arbre montre les seuils sur les variables d entree et les valeurs des feuilles. Les noms de colonnes `f0`, `f1` sont traduits en libelles `d_...` lorsque possible.

### Prediction interactive

1. Choisir un hotel de reference (ou laisser la moyenne des pivots)
2. Modifier quelques variables cles : chambres, TO, guests, parts F&B, etc.
3. Lancer Calculer la prediction

Resultats affiches :

- Totaux annuels et mensuels de CA et de ventes (sorties directes du modele)
- Tableau mois par mois
- Ventilation estimee par type et gamme : les totaux mensuels sont repartis selon les pourcentages historiques de l hotel. Cette ventilation aide a lire le detail metier ; seules les lignes globales mensuelles sont predites nativement par le modele.

## APIs utilisees

| Route | Role |
|-------|------|
| GET `/api/data-exploration?hotel_id=` | Echantillons des sept etapes |
| GET `/api/model-exploration/meta` | Liste des sorties et des arbres |
| GET `/api/model-exploration/tree?target_index=&tree_number=` | Structure JSON d un arbre |
| POST `/api/model-exploration/predict` | Prediction avec surcharge de variables |

## Fichiers code

| Fichier | Role |
|---------|------|
| `rod_ia/domain/services/data_exploration_service.py` | Construction des echantillons |
| `rod_ia/domain/services/model_exploration_service.py` | Arbres et predictions |
| `rod_ia/api/routes/exploration.py` | Routes HTTP |
| `rod_ia/web/exploration.html` | Page |
| `rod_ia/web/exploration.js` | Logique interface |

## Prerequis et entrainement du modele

Le code d apprentissage est dans `model_trainer.py`. Les artefacts sont generes a l execution :

| Situation | Action |
|-----------|--------|
| Rien n a ete initialise | `./init.sh` |
| Dataset present, modele absent | `./run.sh` entraine automatiquement, ou `python -m rod_ia.pipelines.train_model` |
| Forcer un reentrainement | `python -m rod_ia.pipelines.train_model --force` |
| Regenerer dataset puis entrainer | `python -m rod_ia.pipelines.train_model --rebuild-dataset` |

Verification : `GET /api/model/status` (dataset_ready, model_present).

Sans modele charge, l onglet Modele affiche un avertissement et les predictions IA retombent sur le fallback ROD dans le simulateur.