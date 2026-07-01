# Documentation détaillée du ZIP `rod_ia_refactor_project.zip`

## 1. Objectif du ZIP

Ce ZIP est une **base de refactorisation propre** pour le projet ROD-IA. Il ne remplace pas encore totalement les fichiers Excel ROD, mais il donne une architecture maintenable pour progressivement transformer les règles Excel, les anciens notebooks, les scripts Python et la web app Flask en application structurée.

L’objectif est de relier dans un même projet :

1. l’interface web du simulateur ROD ;
2. les données saisies par les directeurs d’hôtel ;
3. l’enrichissement automatique par géolocalisation, météo et POI ;
4. les règles déterministes issues des Excel ROD ;
5. les constantes/references recalculables depuis les ventes pivots ;
6. la prédiction IA ;
7. l’optimiseur sous contraintes ;
8. l’audit et la traçabilité des règles.

Le principe important est le suivant :

```text
Excel ROD = source de vérité n°1
Consigne ROD / documentation fonctionnelle = source de vérité n°2
Code legacy = matériau d’audit, pas source de vérité
```

Le ZIP a donc été construit comme une **architecture cible de travail**, pas comme une version finale validée contre Excel cellule par cellule. Les modules sont volontairement séparés pour faciliter la maintenance, les tests et l’extension.

---

## 2. Vue globale de l’arborescence

```text
rod_ia_refactor_project/
├── README.md
├── requirements.txt
├── app/
│   ├── server.py
│   ├── config/
│   ├── routes/
│   ├── domain/
│   │   ├── models/
│   │   ├── rules/
│   │   ├── services/
│   │   └── repositories/
│   ├── web/
│   ├── artifacts/
│   ├── data/
│   │   ├── raw/
│   │   └── reference/
│   ├── feature_store/
│   └── tests/
├── docs/
│   ├── ARCHITECTURE.md
│   └── audit/
├── scripts/
└── legacy_original/
```

Cette arborescence sépare les responsabilités :

- `app/domain/models/` contient les objets métier et dataclasses.
- `app/domain/rules/` contient les règles de calcul ou de recommandation.
- `app/domain/services/` contient les services de simulation, IA, optimisation, enrichissement et extraction des ventes.
- `app/domain/repositories/` contient les accès aux référentiels et fichiers Excel.
- `app/routes/` expose les API Flask.
- `app/web/` contient l’interface HTML/CSS/JS.
- `app/data/raw/` reçoit les Excel et CSV sources.
- `app/data/reference/` contient les constantes/references versionnées ou recalculées.
- `app/feature_store/` stocke le cache par hôtel.
- `scripts/` contient les outils d’extraction et de recalcul.
- `legacy_original/` conserve les anciens scripts pour audit.

---

## 3. Philosophie technique retenue

### 3.1. Ne pas coder les règles au hasard

Les règles doivent être traçables : chaque formule ou constante doit venir :

```text
1. d’un Excel ROD ;
2. ou d’un recalcul depuis les ventes pivots ;
3. ou d’une hypothèse explicitement validée.
```

Dans le ZIP, les fichiers `revenue_rules.py`, `cost_rules.py` et `recommendation_rules.py` contiennent déjà une structure traçable avec des objets `RuleTrace`, mais plusieurs règles sont encore marquées comme :

```text
requires_excel_validation
```

Cela veut dire que la structure est prête, mais que la formule exacte doit encore être reliée aux cellules Excel précises.

### 3.2. Séparer données, règles et services

Le simulateur ne doit pas mélanger :

- les inputs saisis par l’hôtel ;
- les données enrichies météo/POI ;
- les constantes Excel ;
- les règles de calcul ;
- la prédiction IA ;
- l’optimisation.

Chaque bloc est isolé pour pouvoir être testé et remplacé.

### 3.3. Ne pas dépendre de Spark

Tout est pensé pour fonctionner avec :

```text
Flask + pandas + JSON/parquet/csv + joblib
```

Cela correspond à ta décision : pas de Spark, car les volumes sont raisonnables pour une V1.

### 3.4. POI à 0.1–0.5 km

La correction métier est intégrée dans la configuration :

```python
DEFAULT_POI_RADII_KM = [0.1, 0.2, 0.3, 0.4, 0.5]
```

C’est cohérent avec ton objectif : mesurer la concurrence immédiatement accessible à pied, et non la densité commerciale d’un quartier à 1–5 km.

---

## 4. Flux fonctionnel complet

### 4.1. Flux utilisateur web

```text
Directeur hôtel
  ↓
Saisit nom, adresse, ville, marque
  ↓
Clique “Enrichir automatiquement POI + météo”
  ↓
Backend géocode l’hôtel
  ↓
Backend récupère météo + POI 0.1–0.5 km
  ↓
Features sauvegardées dans feature_store
  ↓
Directeur saisit TO, chambres, guests/chambre, concept, mètres linéaires, mix, contraintes
  ↓
/api/simulate
  ↓
Résultat ROD déterministe + résultat IA
  ↓
Affichage KPI + graphique mensuel
  ↓
Optionnel : /api/optimize pour proposer la meilleure configuration sous contraintes
```

### 4.2. Flux côté backend

```text
Payload JSON typé
  ↓
RodSimulationRequest.from_dict()
  ↓
HotelIdentity + HotelOperatingState + StoreConfiguration + EnrichedHotelFeatures
  ↓
RodSimulator.simulate()
  ↓
RodRevenueRules.compute()
RodCostRules.compute()
  ↓
SimulationResult
  ↓
AIRodRevenuePredictor.predict()
  ↓
JSON retourné au front
```

### 4.3. Flux enrichissement hôtel

```text
Nom + adresse + ville
  ↓
EnrichHotelService.make_hotel_id()
  ↓
Vérification cache feature_store/hotels/<hotel_id>/enriched.json
  ↓
Si absent ou force_refresh=True :
    géocodage via Nominatim
    météo via meteostat
    POI via Overpass/OSM
    calcul counts par rayon 0.1–0.5 km
    calcul distances au commerce le plus proche par type
  ↓
Sauvegarde JSON
```

### 4.4. Flux références commerciales

```text
Excel ROD / ventes pivots
  ↓
extract_excel_rules.py ou recompute_sales_references.py
  ↓
JSON / CSV d’audit / références recalculées
  ↓
ReferenceRepository
  ↓
RodRevenueRules / RodCostRules
```

---

## 5. Documentation fichier par fichier

## 5.1. `README.md`

### Rôle

Fichier d’entrée du projet. Il explique :

- le but général du projet ;
- les principes de vérité métier ;
- la structure des dossiers ;
- comment lancer l’application ;
- quels fichiers déposer dans `app/data/raw/` ;
- pourquoi les constantes démo sont à zéro.

### Points importants

Le README rappelle explicitement que :

```text
rod_reference_demo.json met les références à zéro par défaut pour ne pas inventer de chiffres.
```

Cela est volontaire : le système ne doit pas produire des résultats métier crédibles sans avoir chargé les vraies constantes Excel ou recalculé les références à partir des ventes.

### Statut

À garder. C’est un bon fichier d’accueil, mais il faudra l’enrichir lorsque les vraies règles Excel seront intégrées.

---

## 5.2. `requirements.txt`

### Rôle

Liste les dépendances nécessaires au projet.

Dépendances attendues :

```text
flask
pandas
numpy
requests
meteostat
joblib
openpyxl
scikit-learn
```

### Statut

À garder. À compléter si on ajoute XGBoost réel, par exemple :

```text
xgboost
```

---

# 6. Dossier `app/`

Le dossier `app/` contient l’application Flask et toute la logique métier.

---

## 6.1. `app/server.py`

### Rôle

Point d’entrée Flask.

Il :

1. crée l’application Flask ;
2. sert les fichiers statiques de `app/web/` ;
3. enregistre les blueprints API ;
4. expose `/` pour afficher l’interface ;
5. expose `/health` pour tester que le serveur répond.

### Fonctionnement

```python
app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path='/static')
app.register_blueprint(enrich_bp)
app.register_blueprint(simulate_bp)
```

Les routes sont donc séparées dans :

```text
app/routes/enrich.py
app/routes/simulate.py
```

### Endpoints

```text
GET /
→ renvoie index.html

GET /health
→ renvoie {"status": "ok"}
```

### Statut

À garder. C’est propre et beaucoup mieux que l’ancien `server.py` qui mélangeait chargement modèle, routes, logique métier et static files dans un même fichier.

---

## 6.2. `app/config/settings.py`

### Rôle

Centralise les chemins et constantes de configuration.

### Variables importantes

```python
APP_DIR
PROJECT_DIR
DATA_DIR
RAW_DATA_DIR
REFERENCE_DIR
FEATURE_STORE_DIR
ARTIFACTS_DIR
WEB_DIR
```

Elles permettent d’éviter les chemins codés en dur partout.

### POI

```python
DEFAULT_POI_RADII_KM = [0.1, 0.2, 0.3, 0.4, 0.5]
```

C’est la correction métier majeure : on veut mesurer la concurrence accessible à pied immédiatement.

### APIs externes

```python
NOMINATIM_URL
OVERPASS_URL
USER_AGENT
```

Ces constantes sont utilisées par le service d’enrichissement.

### Statut

À garder. C’est un bon point central pour modifier les paramètres globaux.

---

# 7. Dossier `app/domain/models/`

Ce dossier contient les objets métier. C’est la base de l’architecture orientée objet.

---

## 7.1. `app/domain/models/hotel.py`

### Classes

```python
HotelIdentity
HotelOperatingState
```

---

### 7.1.1. `HotelIdentity`

#### Rôle

Représente l’identité de l’hôtel.

Champs :

```python
hotel_name: str
city: str
address: str
brand: str
hotel_id: Optional[str]
```

#### Pourquoi c’est utile

On évite d’envoyer partout des dictionnaires non contrôlés. L’hôtel devient un objet métier clair.

#### Méthodes

```python
to_dict()
from_dict()
```

Elles facilitent le lien entre JSON Flask et dataclass Python.

---

### 7.1.2. `HotelOperatingState`

#### Rôle

C’est une des classes les plus importantes du ZIP. Elle représente les variables opérationnelles interdépendantes de l’hôtel.

Variables internes :

```python
_nb_chambres
_taux_occupation
_guests_per_chambre
_jours_mois
_chambres_occupees
_clients_jour
_clients_mois
```

#### Logique métier

Tu avais expliqué que les variables du simulateur sont dépendantes. Exemple :

```text
chambres occupées = nombre de chambres × taux d’occupation
clients/jour = chambres occupées × guests/chambre
clients/mois = clients/jour × nombre moyen de jours/mois
```

Donc si une variable est modifiée, les autres doivent être recalculées automatiquement.

Cette classe implémente cette logique avec des getters/setters.

#### Exemple 1 : modification du TO

```python
s = HotelOperatingState(nb_chambres=100, taux_occupation=0.5, guests_per_chambre=2)
s.taux_occupation = 0.8
```

Résultat :

```text
chambres_occupees = 80
clients_jour = 160
clients_mois = 160 × 30.5
```

#### Exemple 2 : modification des clients/jour

```python
s.clients_jour = 120
```

Le système recalcule :

```text
taux_occupation = clients_jour / (nb_chambres × guests_per_chambre)
```

Avec 100 chambres et 2 guests/chambre :

```text
taux_occupation = 120 / 200 = 0.6
```

#### Gestion des pourcentages

La méthode `_clip_rate()` accepte aussi bien :

```text
0.8
80
```

Si la valeur dépasse 1, elle est divisée par 100.

#### Statut

À garder absolument. C’est exactement la logique orientée objet dont tu parlais : aucune variable n’est vraiment figée, et modifier une variable recale les autres.

À améliorer plus tard :

- ajouter des tests pour `chambres_occupees` ;
- ajouter des tests pour `clients_mois` ;
- gérer explicitement les cas de contradiction forte entre plusieurs variables saisies.

---

## 7.2. `app/domain/models/store.py`

### Classes

```python
CategoryMix
StoreConfiguration
```

---

### 7.2.1. `CategoryMix`

#### Rôle

Représente le mix commercial du store.

Champs :

```python
fb_share
non_fb_share
category_shares
subcategory_shares
```

#### Exemple

```python
CategoryMix(
    fb_share=0.7,
    non_fb_share=0.3,
    category_shares={"ALCOOL": 0.1, "SANS_ALCOOL": 0.3},
    subcategory_shares={"boissons_froides": 0.2}
)
```

#### Méthode `normalize()`

Si l’utilisateur met :

```text
F&B = 80
Non-F&B = 40
```

le total vaut 120. La méthode normalise les deux valeurs pour que le total fasse 1.

Cela protège contre les incohérences simples.

---

### 7.2.2. `StoreConfiguration`

#### Rôle

Représente une configuration de solution store.

Champs :

```python
concept
m_lin
mix
allowed_categories
excluded_categories
locked_fields
```

#### Concepts attendus

```text
SIMPLY
LIBERTY
CONNECTED
```

#### Contraintes utilisateur

- `excluded_categories` : catégories sorties du périmètre, par exemple `ALCOOL`.
- `locked_fields` : champs que l’optimiseur ne doit pas modifier.

Exemple :

```python
StoreConfiguration(
    concept="LIBERTY",
    m_lin=4,
    excluded_categories=["ALCOOL"],
    locked_fields=["m_lin", "excluded_categories"]
)
```

Ici, l’optimiseur ne doit pas changer les mètres linéaires et doit respecter l’exclusion alcool.

#### Statut

À garder. C’est la bonne structure pour connecter l’interface web, le simulateur ROD, l’IA et l’optimiseur.

À améliorer :

- valider que `concept` appartient bien à la liste officielle ;
- normaliser les noms de catégories ;
- ajouter les sous-catégories détaillées ;
- ajouter la notion de `forced_categories` ou `locked_category_shares`.

---

## 7.3. `app/domain/models/simulation.py`

### Classes

```python
EnrichedHotelFeatures
RodSimulationRequest
MonthlyProjection
SimulationResult
```

---

### 7.3.1. `EnrichedHotelFeatures`

#### Rôle

Contient les données automatiques récupérées pour l’hôtel.

Champs :

```python
lat
lon
address_resolved
poi
weather_monthly
nearest
```

#### Exemple

```python
EnrichedHotelFeatures(
    lat=48.85,
    lon=2.35,
    poi={"fb_0_0_1km": 2, "not_fb_0_0_5km": 4},
    weather_monthly={"m07_temp_mean": 25.1},
    nearest={"nearest_supermarket_m": 120}
)
```

#### Pourquoi c’est important

Ces features ne doivent pas être saisies par le directeur. Elles sont calculées automatiquement puis injectées dans la simulation IA.

---

### 7.3.2. `RodSimulationRequest`

#### Rôle

Objet complet représentant une demande de simulation.

Champs :

```python
identity: HotelIdentity
operating: HotelOperatingState
store: StoreConfiguration
enriched: EnrichedHotelFeatures
```

C’est le pont propre entre :

```text
JSON web
→ dataclasses
→ simulateur
```

#### Méthode `from_dict()`

Elle convertit le JSON envoyé par le front en objets métier.

Exemple JSON attendu :

```json
{
  "identity": {"hotel_name": "Ibis budget Nice", "city": "Nice", "brand": "IBIS_BUDGET"},
  "operating": {"nb_chambres": 129, "taux_occupation": 0.8, "guests_per_chambre": 1.7},
  "store": {"concept": "SIMPLY", "m_lin": 2, "mix": {"fb_share": 0.7, "non_fb_share": 0.3}},
  "enriched": {"poi": {}, "weather_monthly": {}, "nearest": {}}
}
```

---

### 7.3.3. `MonthlyProjection`

#### Rôle

Représente une sortie mensuelle.

Champs :

```python
month
ca
nbr_ventes
margin
cost
```

Un résultat annuel est composé de 12 `MonthlyProjection`.

---

### 7.3.4. `SimulationResult`

#### Rôle

Représente le résultat complet d’une simulation.

Champs :

```python
source
concept
m_lin
ca_annuel
nbr_ventes_annuel
marge_annuelle
cout_annuel
roi_months
monthly
breakdown
warnings
trace
```

#### Sources possibles

```text
ROD_EXCEL_RULES
AI_MODEL
```

#### Point important

La marge peut être négative. C’est volontaire et important : si les coûts dépassent les revenus, le résultat doit le montrer.

#### Statut

À garder. C’est un format clair pour renvoyer les résultats au front.

---

# 8. Dossier `app/domain/rules/`

Ce dossier contient les règles métier.

---

## 8.1. `traceability.py`

### Rôle

Définit la classe `RuleTrace`.

### Utilité

Chaque règle doit pouvoir être liée à sa source Excel :

```python
rule_id
workbook
sheet
cells
excel_formula
business_description
python_method
status
```

### Exemple

```python
RuleTrace(
    rule_id="REV_CLIENTS_MONTH",
    workbook="ROD - Simulateurs + détail des coûts.xlsx",
    sheet="SIMULATEUR *",
    cells=["à valider"],
    excel_formula="clients_mois = nb_chambres * TO * guests_per_chambre * 30.5",
    business_description="Calcul des clients mensuels",
    python_method="HotelOperatingState",
    status="implemented_formula_to_validate"
)
```

### Statut

À garder absolument. C’est la base de l’audit et de la maintenance.

---

## 8.2. `revenue_rules.py`

### Rôle

Calcule les revenus ROD déterministes.

### Classe principale

```python
RodRevenueRules
```

### Méthode principale

```python
compute(req: RodSimulationRequest) -> RevenueComputation
```

### Données utilisées

Le module lit des constantes via `ReferenceRepository` :

```python
concepts.<concept>.base_monthly_ca
concepts.<concept>.base_monthly_sales
concepts.<concept>.pivot_m_lin
concepts.<concept>.pivot_clients_mois
seasonality.monthly
```

### Calcul actuellement codé

Le calcul actuel suit cette structure :

```text
mlin_factor = m_lin choisi / m_lin pivot
client_factor = clients_mois hôtel simulé / clients_mois pivot
ca_mensuel = base_monthly_ca × mlin_factor × client_factor × saisonnalité
ventes_mensuelles = base_monthly_sales × mlin_factor × client_factor × saisonnalité
```

### Exemple

Si :

```text
base_monthly_ca = 5000
m_lin choisi = 4
m_lin pivot = 2
clients_mois hôtel = 8000
clients_mois pivot = 4000
saisonnalité = 1.1
```

Alors :

```text
mlin_factor = 4 / 2 = 2
client_factor = 8000 / 4000 = 2
ca_mensuel = 5000 × 2 × 2 × 1.1 = 22000
```

### Warnings

Si la référence `base_monthly_ca` est absente ou vaut zéro, le module ajoute un warning :

```text
Référence base_monthly_ca absente: résultat revenu à zéro tant que les constantes Excel/recalculées ne sont pas chargées.
```

C’est volontaire pour éviter l’hallucination de chiffres.

### Traçabilité

Deux règles sont tracées :

```text
REV_MLIN_SCALE
REV_CLIENTS_MONTH
```

### Statut

À garder comme structure, mais **pas encore validé comme reproduction fidèle Excel**.

À faire :

1. mapper exactement les cellules Excel des simulateurs Simply/Liberty/Connected ;
2. intégrer le mix F&B/Non-F&B plus finement ;
3. intégrer les catégories et sous-catégories ;
4. intégrer les règles d’impact TO Excel ;
5. tester Python vs Excel sur les scénarios pivots.

---

## 8.3. `cost_rules.py`

### Rôle

Calcule les coûts : agencement, techno, capex, opex, amortissement.

### Classe principale

```python
RodCostRules
```

### Méthode principale

```python
compute(req: RodSimulationRequest) -> CostComputation
```

### Références attendues

```python
concepts.<concept>.cost_per_m
concepts.<concept>.fixed_capex
concepts.<concept>.opex_monthly
concepts.<concept>.amort_months
```

### Calcul actuellement codé

```text
capex = fixed_capex + cost_per_m × m_lin
monthly_cost = capex / amort_months + opex_monthly
annual_cost = monthly_cost × 12
```

### Exemple

Si :

```text
fixed_capex = 5000
cost_per_m = 1000
m_lin = 4
opex_monthly = 300
amort_months = 84
```

Alors :

```text
capex = 5000 + 1000 × 4 = 9000
monthly_cost = 9000 / 84 + 300 = 407.14
annual_cost = 4885.68
```

### Warnings

Si toutes les références coût sont absentes, le module prévient que les coûts Excel doivent être chargés.

### Statut

À garder comme squelette. À compléter avec les vrais coûts des feuilles :

```text
COUTS - TECHNOS
COUTS - ANNEXES
COUTS - AGENCEMENT
```

---

## 8.4. `recommendation_rules.py`

### Rôle

Filtre les concepts autorisés/recommandés selon les règles ROD.

### Classe principale

```python
RodRecommendationRules
```

### Méthode

```python
allowed_concepts(req)
```

### Logique temporaire actuellement codée

```text
si nb_chambres < 50 → SIMPLY
sinon si m_lin > 4 → LIBERTY ou CONNECTED
sinon → SIMPLY, LIBERTY, CONNECTED
```

### Statut

À garder comme emplacement, mais la logique actuelle est **temporaire**.

Elle doit être remplacée par la consommation fidèle de :

```text
ROD - Paramètres & règles + projections nb. d'hôtels.xlsx
Feuille : REGLES POUR RECO DU CONCEPT
```

À faire :

- implémenter toutes les règles de recommandation ;
- tracer chaque règle ;
- gérer les cas de stratégie haut de gamme si validés par la consigne ;
- ne pas confondre règle de calcul et règle de recommandation.

---

# 9. Dossier `app/domain/repositories/`

Ce dossier gère l’accès aux références et aux Excel.

---

## 9.1. `reference_repository.py`

### Rôle

Charge un fichier JSON de références et permet de lire une valeur avec un chemin pointé.

Exemple :

```python
reference.get("concepts.SIMPLY.base_monthly_ca", 0)
```

### Pourquoi c’est important

Les constantes ne doivent pas être cachées dans le code. Elles doivent venir de fichiers de référence.

### Sources possibles futures

```text
rod_reference_demo.json
recomputed_sales_reference.json
excel_reference.json
```

### Statut

À garder. À faire évoluer pour gérer plusieurs sources :

```text
source="excel"
source="recomputed_sales"
source="manual_validated"
```

---

## 9.2. `excel_repository.py`

### Rôle

Lit les fichiers Excel et extrait :

- les formules ;
- les commentaires.

### Utilité

C’est un outil d’audit et de traçabilité. Il sert à consommer progressivement le contenu Excel.

### Méthodes attendues

```python
extract_formulas()
extract_comments()
```

### Statut

À garder. C’est utile pour construire une table de correspondance :

```text
cellule Excel → règle Python → test associé
```

---

# 10. Dossier `app/domain/services/`

Ce dossier contient les services applicatifs.

---

## 10.1. `rod_simulator.py`

### Rôle

Service principal de simulation ROD déterministe.

### Classe

```python
RodSimulator
```

### Dépendances injectées

```python
RodRevenueRules
RodCostRules
RodRecommendationRules
```

Cela rend le code maintenable : le simulateur orchestre les règles, mais ne contient pas directement toutes les formules.

### Méthode principale

```python
simulate(req: RodSimulationRequest) -> SimulationResult
```

### Calculs faits

1. Calcule les revenus via `revenue_rules.compute()`.
2. Calcule les coûts via `cost_rules.compute()`.
3. Calcule le CA annuel.
4. Calcule le nombre de ventes annuel.
5. Calcule la marge annuelle :

```text
marge_annuelle = ca_annuel - cout_annuel
```

6. Calcule le ROI en mois si la marge est positive :

```text
roi_months = capex / (marge_annuelle / 12)
```

7. Calcule les marges mensuelles :

```text
margin_mois = ca_mois - cost_mois
```

### Point important

La marge peut être négative. Le code l’accepte.

### Statut

Très bonne base. À garder.

À améliorer :

- intégrer la recommandation dans le flux si un concept est interdit ;
- ajouter les règles de mix catégories/sous-catégories ;
- ajouter le détail des coûts par poste ;
- ajouter le détail de marge brute vs marge nette.

---

## 10.2. `ai_predictor.py`

### Rôle

Service de prédiction IA.

### Classe

```python
AIRodRevenuePredictor
```

### Fonctionnement

Au démarrage, il cherche dans `app/artifacts/` :

```text
model.joblib
feature_cols.json
target_cols.json
```

Si `model.joblib` est absent, il ne plante pas. Il renvoie un résultat IA à zéro avec warning.

### Construction des features

La méthode `request_to_features()` transforme `RodSimulationRequest` en DataFrame pandas.

Features actuellement créées :

```python
nb_chambres
taux_occupation
guests_per_chambre
m_lin
fb_share
non_fb_share
poi_*
weather_*
nearest_*
```

### Prédiction

Si un modèle existe :

1. il prédit les target columns ;
2. il regroupe les colonnes par mois via regex `mXX` ;
3. il additionne les colonnes contenant `montant` ou `ca` pour le CA ;
4. il additionne les colonnes contenant `nbr_ventes` ou `ventes` pour les ventes.

### Exemple cible attendue

```text
m07__FB__SANS_ALCOOL__montant
m07__FB__SANS_ALCOOL__nbr_ventes
```

### Statut

Bonne base. À garder.

À améliorer :

- ajouter le préprocessing complet du modèle XGBoost ;
- gérer les colonnes catégorielles comme la marque ;
- intégrer le stacking plus tard ;
- gérer la prédiction catégorie/sous-catégorie ;
- intégrer les contraintes d’exclusion catégorie.

---

## 10.3. `optimizer.py`

### Rôle

Optimiseur sous contraintes.

### Classe

```python
RodOptimizer
```

### Fonctionnement

Il teste plusieurs configurations :

```python
concepts = SIMPLY, LIBERTY, CONNECTED
m_lins = 1, 2, 3, 4, 5, 6
fb_shares = 0.5, 0.6, 0.7, 0.8, 0.9
```

Pour chaque combinaison, il respecte `locked_fields`.

Exemple :

```text
si m_lin est figé → il ne change pas m_lin
si concept est figé → il ne change pas concept
si fb_share est figé → il ne change pas le mix F&B
```

Il garde la configuration qui maximise :

```text
marge_annuelle
```

### Statut

Bonne première version simple.

À améliorer :

- intégrer les `allowed_concepts` des règles ROD ;
- respecter `excluded_categories` dans le score ;
- optimiser aussi les sous-catégories ;
- permettre l’optimisation sur CA, marge ou ROI selon objectif ;
- remplacer grid search par optimisation plus fine si nécessaire.

---

## 10.4. `sales_mix_extractor.py`

### Rôle

Recalcule les métriques de référence depuis les ventes pivots.

C’est une pièce très importante parce que les constantes Excel peuvent venir d’un historique plus ancien. Maintenant que tu as plus de données, on veut pouvoir recalculer.

### Classe

```python
SalesMixExtractor
```

### Méthodes

```python
load_sales()
prepare()
monthly_average_targets()
mix_by_type_and_gamme()
```

### Logique métier

La méthode `monthly_average_targets()` :

1. charge les ventes ;
2. exclut 2026 si demandé ;
3. calcule l’année et le mois ;
4. calcule le montant ;
5. groupe par hôtel, mois, type et gamme ;
6. somme par année ;
7. moyenne les mois disponibles sans tronquer l’historique.

C’est exactement ta stratégie :

```text
ne pas s’aligner sur la plus petite période historique
moyenner chaque mois disponible
conserver toute la donnée disponible
```

### Exemple

Si un hôtel a :

```text
Janvier 2023, janvier 2024, janvier 2025
```

la moyenne de janvier utilise 3 valeurs.

Si un autre hôtel a seulement :

```text
Janvier 2024, janvier 2025
```

la moyenne de janvier utilise 2 valeurs.

La colonne `nb_years_used` indique la profondeur de calcul.

### Statut

Très utile. À garder.

À améliorer :

- nettoyer `GAMME` (`#REF!`, espaces, accents, slashs) ;
- ajouter catégorie/sous-catégorie si disponible ;
- générer directement un format target large compatible IA ;
- exporter aussi les mesures de fiabilité (`nb_months_used`, `nb_orders`, etc.).

---

## 10.5. `enrich_hotel.py`

### Rôle

Service d’enrichissement automatique hôtel.

### Classe

```python
EnrichHotelService
```

### Responsabilités

1. créer un `hotel_id` stable ;
2. gérer un cache par hôtel ;
3. géocoder l’hôtel ;
4. récupérer la météo 12 mois ;
5. récupérer les POI à 0.1–0.5 km ;
6. calculer les counts POI ;
7. calculer les distances aux commerces les plus proches ;
8. sauvegarder le résultat dans le feature store.

---

### `make_hotel_id()`

Transforme nom + ville en identifiant propre.

Exemple :

```text
Ibis budget Nice + Nice
→ ibis_budget_nice_nice
```

Cela sert à créer :

```text
app/feature_store/hotels/ibis_budget_nice_nice/enriched.json
```

---

### Cache feature store

Méthodes :

```python
load_cached()
save_cached()
hotel_dir()
```

Si l’hôtel a déjà été enrichi, on relit `enriched.json` au lieu de refaire les appels API.

---

### Géocodage

Méthode :

```python
geocode_hotel()
```

Elle appelle Nominatim à partir de :

```text
nom hôtel + adresse + ville + pays
```

Elle retourne :

```python
lat
lon
address_resolved
```

---

### Météo 12 mois

Méthode :

```python
fetch_weather_12_months()
```

Elle utilise `meteostat` si disponible.

Elle calcule des agrégats mensuels :

```text
temp_mean, temp_min, temp_max
dwpt_mean, dwpt_min, dwpt_max
rhum_mean, rhum_min, rhum_max
prcp_mean, prcp_min, prcp_max
snow_mean, snow_min, snow_max
wspd_mean, wspd_min, wspd_max
pres_mean, pres_min, pres_max
tsun_mean, tsun_min, tsun_max
```

préfixés par mois :

```text
m01_temp_mean
m07_temp_max
...
```

---

### POI à 0.1–0.5 km

Méthode :

```python
fetch_poi()
```

Elle interroge Overpass/OSM.

Rayons utilisés :

```python
[0.1, 0.2, 0.3, 0.4, 0.5]
```

Le service récupère les commerces dont le tag `shop` appartient aux listes :

```python
FB_TYPES = [
  "convenience", "bakery", "supermarket", "alcohol", "confectionery",
  "beverages", "grocery", "ice_cream", "fast_food"
]
```

```python
NOT_FB_TYPES = [
  "cosmetics", "gift", "tobacco", "kiosk", "pharmacy", "chemist"
]
```

### Pourquoi c’est métier

Ce n’est pas une mesure de densité commerciale générale. C’est une mesure de **substitution immédiate à pied** :

```text
Est-ce que le client peut sortir de l’hôtel et trouver le même produit moins cher tout près ?
```

---

### Features POI calculées

Méthode :

```python
compute_poi_features()
```

Produit par exemple :

```text
fb_0_0_1km
fb_0_0_2km
fb_0_0_3km
fb_0_0_4km
fb_0_0_5km
not_fb_0_0_1km
not_fb_0_0_2km
...
```

Le nom `fb_0_0_1km` vient du remplacement du point dans `0.1` par `_`. C’est fonctionnel, mais pas très lisible.

### Amélioration recommandée

Renommer plus clairement :

```text
fb_100m
fb_200m
fb_300m
fb_400m
fb_500m
not_fb_100m
...
```

---

### Distances au plus proche commerce

Le service calcule aussi :

```text
nearest_supermarket_m
nearest_bakery_m
nearest_pharmacy_m
nearest_alcohol_m
...
```

C’est très utile parce qu’un seul commerce à 50m peut être plus important que plusieurs commerces à 450m.

---

### Statut

Très important. À garder.

À améliorer :

- renommer les colonnes POI ;
- ajouter éventuellement distance plage ;
- ajouter gestion quotas / erreurs API ;
- enrichir `amenity` en plus de `shop` si nécessaire ;
- intégrer sauvegarde séparée météo/poi/geo dans des sous-fichiers si le feature store devient plus structuré.

---

# 11. Dossier `app/routes/`

Ce dossier contient les endpoints Flask.

---

## 11.1. `routes/enrich.py`

### Endpoint

```text
POST /api/enrich
```

### Rôle

Reçoit les informations de l’hôtel, lance l’enrichissement automatique et retourne les features.

### Payload attendu

```json
{
  "identity": {
    "hotel_name": "Ibis budget Nice",
    "address": "",
    "city": "Nice"
  },
  "force_refresh": false
}
```

### Réponse

```json
{
  "hotel_id": "ibis_budget_nice_nice",
  "features": {
    "lat": 43.7,
    "lon": 7.2,
    "poi": {},
    "weather_monthly": {},
    "nearest": {}
  }
}
```

### Statut

À garder.

---

## 11.2. `routes/simulate.py`

### Endpoints

```text
POST /api/simulate
POST /api/optimize
```

---

### `/api/simulate`

#### Rôle

Lance deux simulations :

```text
ROD déterministe
IA
```

#### Flux

```python
payload → RodSimulationRequest.from_dict(payload)
req → rod_simulator.simulate(req)
req → ai_predictor.predict(req)
```

#### Réponse

```json
{
  "rod": {...},
  "ai": {...}
}
```

---

### `/api/optimize`

#### Rôle

Teste plusieurs configurations et retourne la meilleure selon marge annuelle.

#### Réponse

```json
{
  "request": {...configuration retenue...},
  "result": {...résultat simulation...}
}
```

### Statut

À garder. À améliorer : ajouter validation des payloads et gestion d’erreurs plus explicite.

---

# 12. Dossier `app/web/`

Ce dossier contient la web app légère.

---

## 12.1. `index.html`

### Rôle

Interface web du simulateur.

### Structure

La page est organisée en 4 onglets :

```text
1. Infos générales
2. Configuration store
3. Contraintes
4. Résultats
```

### Bloc identification hôtel

Champs :

```text
Nom hôtel
Adresse
Ville
Marque
```

Bouton :

```text
Enrichir automatiquement POI + météo
```

### Onglet infos générales

Champs :

```text
Nombre de chambres
TO annuel
Guests / chambre
```

### Onglet configuration store

Champs :

```text
Concept
Mètres linéaires
Part F&B
Part Non-F&B
```

### Onglet contraintes

Cases à cocher :

```text
Exclure alcool
Exclure prêt-à-porter
Exclure souvenirs
Concept figé
Mètres linéaires figés
Mix F&B figé
```

### Onglet résultats

Affiche :

```text
CA ROD annuel
Marge ROD
CA IA annuel
graphique mensuel
JSON brut
```

### Statut

Bonne base. À garder.

À améliorer :

- ajouter détail catégories/sous-catégories ;
- ajouter affichage coûts, ROI, marge négative ;
- afficher warnings et trace des règles ;
- mieux séparer résultat ROD vs IA ;
- afficher les features enrichies récupérées.

---

## 12.2. `script.js`

### Rôle

Gère l’interaction front.

### Fonctions importantes

#### `collectRodInputs()`

Construit le JSON typé envoyé au backend.

C’est une amélioration importante par rapport à l’ancien front, qui envoyait directement des noms de colonnes ML techniques.

Structure retournée :

```json
{
  "identity": {...},
  "operating": {...},
  "store": {...},
  "enriched": {...}
}
```

#### `enrichHotel()`

Appelle :

```text
POST /api/enrich
```

Puis stocke :

```javascript
enrichedFeatures = data.features
```

Ensuite relance automatiquement la simulation.

#### `runSimulation()`

Appelle :

```text
POST /api/simulate
```

Puis appelle `renderResults()`.

#### `runOptimize()`

Appelle :

```text
POST /api/optimize
```

Puis met à jour les champs `concept`, `m_lin`, `fb_share`, `non_fb_share` avec la configuration proposée.

#### `renderResults()`

Met à jour :

```text
rod_ca
rod_margin
ai_ca
raw_output
monthly_chart
```

Le graphique utilise Chart.js avec deux séries :

```text
ROD
IA
```

#### `setupTabs()`

Gère la navigation entre onglets.

#### Auto-refresh

Au chargement :

```javascript
document.querySelectorAll('input, select').forEach(el => el.addEventListener('change', auto));
```

Donc toute modification relance une simulation après debounce.

### Statut

Bonne base.

À améliorer :

- éviter l’appel initial `runSimulation()` avant enrichissement si les références valent zéro ;
- afficher clairement les warnings ;
- ajouter un état loading ;
- empêcher optimisation si les références sont à zéro ;
- gérer erreurs réseau/API plus proprement.

---

## 12.3. `style.css`

### Rôle

Style simple dark mode.

### Éléments stylés

```text
container
cards
grids
inputs
buttons
tabs
panels
KPI
raw JSON
```

### Statut

À garder. Simple, lisible, suffisant pour une V1.

---

# 13. Dossier `app/data/`

---

## 13.1. `app/data/raw/`

### Rôle

Dossier où déposer les fichiers source.

Fichiers attendus :

```text
ROD - Simulateurs + détail des coûts.xlsx
ROD - Paramètres & règles + projections nb. d'hôtels.xlsx
001.queryVentes.csv
Récapitulatif ROD si nécessaire
```

### Statut

Dossier vide dans le ZIP, avec un README. Normal : les fichiers sources sont lourds et séparés.

---

## 13.2. `app/data/reference/rod_reference_demo.json`

### Rôle

Fichier de références démo.

Il contient la structure attendue pour les constantes, mais avec des valeurs à zéro ou neutres.

### Pourquoi à zéro

Pour ne pas inventer de chiffres.

### Statut

À garder comme template.

À remplacer ou compléter avec :

```text
excel_reference.json
recomputed_sales_reference.json
```

---

# 14. Dossier `app/feature_store/`

### Rôle

Stocker les enrichissements par hôtel.

Exemple futur :

```text
app/feature_store/hotels/ibis_budget_nice_nice/enriched.json
```

### Contenu de `enriched.json`

```json
{
  "lat": ...,
  "lon": ...,
  "address_resolved": "...",
  "poi": {...},
  "weather_monthly": {...},
  "nearest": {...}
}
```

### Statut

À garder. À améliorer si besoin en séparant :

```text
geo.json
poi.json
weather.json
nearest.json
```

---

# 15. Dossier `app/artifacts/`

### Rôle

Recevoir les artefacts IA.

Fichiers attendus :

```text
model.joblib
feature_cols.json
target_cols.json
scaler.joblib si nécessaire
meta.json si nécessaire
```

### Statut

Vide dans le ZIP. Normal.

Le service IA sait gérer l’absence du modèle sans planter.

---

# 16. Dossier `scripts/`

---

## 16.1. `extract_excel_rules.py`

### Rôle

Extrait les formules et commentaires des fichiers Excel déposés dans `app/data/raw/`.

### Fonctionnement

Pour chaque fichier Excel :

```text
extract_formulas()
→ docs/audit/<nom_fichier>_formulas.csv

extract_comments()
→ docs/audit/<nom_fichier>_comments.csv
```

### Utilité

C’est la base de la consommation complète des Excel.

On peut ensuite créer une table :

```text
formule Excel → règle Python → test
```

### Statut

À garder.

---

## 16.2. `recompute_sales_references.py`

### Rôle

Recalcule les références depuis les ventes pivots.

### Fichier attendu

```text
app/data/raw/001.queryVentes.csv
```

### Sortie

```text
app/data/reference/recomputed_sales_reference.json
```

### Logique métier

Le script utilise `SalesMixExtractor` et exclut 2026 par défaut.

Il ajoute une note :

```text
Calculé en moyennant les mois disponibles par hôtel/mois/type/gamme,
sans tronquer au plus petit historique.
```

### Statut

À garder. Très utile pour recalculer les constantes Excel avec les historiques enrichis.

---

# 17. Dossier `docs/`

---

## 17.1. `docs/ARCHITECTURE.md`

### Rôle

Documentation courte de l’architecture.

Elle explique :

- le flux web ;
- le flux enrichissement ;
- les dataclasses ;
- la traçabilité des règles ;
- pourquoi les références sont à zéro ;
- les prochaines étapes.

### Statut

À garder. La présente documentation est une version beaucoup plus détaillée.

---

## 17.2. `docs/audit/`

### Rôle

Contient les documents d’audit générés précédemment.

Fichiers présents :

```text
documentation_fonctionnelle_audit_ROD_v2.md
documentation_technique_rod_complete.md
audit_gap_analysis_rod.csv
audit_decisions_keep_modify_drop.csv
catalogue_ventes_categories_produits.csv
inventaire_fichiers_feuilles.csv
inventaire_commentaires_excel.csv
```

### Utilité

Ces fichiers sont là pour garder l’historique de l’audit :

- ce qui a été inspecté ;
- les écarts identifiés ;
- les décisions keep/modify/drop ;
- le catalogue des ventes/catégories/produits ;
- les inventaires Excel.

### Statut

À garder comme documentation de référence.

---

# 18. Dossier `legacy_original/`

### Rôle

Conserve les anciens scripts fournis.

Fichiers principaux :

```text
server.py
business_logic.py
enrich_hotel.py
rod_simulator.py
rod_rules.py
rod_full_simulator.py
hotel_ca_projector.py
simulateur_corner.py
index.html
script.js
style.css
prepare_ml_dataset.py
prepare_X_y_clean.py
ml_xgboost_baseline.py
```

### Pourquoi les garder

Ils contiennent des idées utiles :

- première web app Flask ;
- première logique business ;
- premier enrichissement ;
- premières règles ROD ;
- premier simulateur ;
- premiers scripts ML.

### Pourquoi ne pas les utiliser comme source de vérité

Ils peuvent contenir :

- des constantes codées en dur ;
- des approximations ;
- des rayons POI incorrects ;
- des références à des fichiers absents ;
- des mélanges entre logique web, ML et règles métier ;
- des hypothèses non tracées aux Excel.

### Statut

À garder uniquement pour audit et récupération d’idées.

---

# 19. Tests

## `app/tests/test_operating_state.py`

### Rôle

Teste la classe `HotelOperatingState`.

### Tests présents

#### `test_to_updates_clients()`

Vérifie que modifier le TO modifie automatiquement :

```text
chambres occupées
clients/jour
```

#### `test_clients_updates_to()`

Vérifie que modifier `clients_jour` recalcule le TO.

### Statut

Très bon début. À compléter fortement.

Tests à ajouter :

```text
modification nb_chambres
modification guests_per_chambre
modification clients_mois
TO saisi en 80 au lieu de 0.8
cas nb_chambres = 0
cas marge négative
cas références absentes
cas locked_fields optimizer
cas POI radii 0.1–0.5 km
```

---

# 20. Ce qui est déjà bien développé

## 20.1. Architecture propre

Le projet est maintenant séparé en couches :

```text
web
routes
models
rules
services
repositories
data
feature_store
scripts
legacy
```

C’est beaucoup plus maintenable.

## 20.2. Dataclasses métier

Les objets suivants structurent bien les données :

```text
HotelIdentity
HotelOperatingState
CategoryMix
StoreConfiguration
RodSimulationRequest
EnrichedHotelFeatures
SimulationResult
```

## 20.3. Getters/setters interdépendants

`HotelOperatingState` répond à ton besoin de variables interdépendantes.

## 20.4. POI corrigé à 0.1–0.5 km

Le mauvais rayon 1–5 km a été corrigé dans la nouvelle architecture.

## 20.5. Feature store local

Le cache par hôtel est prévu et fonctionnel conceptuellement.

## 20.6. Simulation ROD traçable

Le simulateur renvoie une trace des règles, ce qui est essentiel pour auditer Excel vs Python.

## 20.7. IA branchable

Le module IA ne bloque pas si aucun modèle n’est présent, mais il est prêt à charger un `model.joblib`.

## 20.8. Optimiseur sous contraintes

Un premier grid search respecte `locked_fields`.

## 20.9. Recalcul ventes

Le script `recompute_sales_references.py` suit la stratégie de moyenne mensuelle sur historique disponible.

---

# 21. Ce qui reste incomplet ou à auditer

## 21.1. Les règles Excel ne sont pas encore entièrement consommées

Les fichiers Python sont structurés, mais les formules exactes doivent être intégrées cellule par cellule.

Priorité :

```text
ROD - Simulateurs + détail des coûts.xlsx
ROD - Paramètres & règles + projections nb. d'hôtels.xlsx
```

## 21.2. Les constantes sont à zéro

C’est volontaire, mais cela signifie que le simulateur donnera zéro tant que les références ne sont pas chargées.

## 21.3. Mix catégories/sous-catégories incomplet

La structure existe, mais le calcul détaillé par :

```text
F&B
Non-F&B
catégorie
sous-catégorie
```

n’est pas encore complètement branché.

## 21.4. IA non entraînée dans le ZIP

Le ZIP prépare le chargement du modèle, mais ne contient pas le modèle entraîné.

## 21.5. Recommandation ROD temporaire

`recommendation_rules.py` contient une logique temporaire à remplacer par les règles Excel.

## 21.6. Optimiseur encore simple

Il teste seulement concept, m_lin et fb_share. Il ne traite pas encore toutes les catégories et sous-catégories.

## 21.7. Front encore minimal

L’interface est propre, mais pas encore complète par rapport au vrai simulateur ROD.

Il manque notamment :

```text
détail sous-catégories
coûts détaillés
marges détaillées
ROI clair
trace des règles
warnings visibles
comparaison ROD vs IA plus riche
configuration optimale complète
```

---

# 22. Ordre recommandé des prochaines étapes

## Étape 1 — Charger les Excel dans `app/data/raw/`

Copier :

```text
ROD - Simulateurs + détail des coûts.xlsx
ROD - Paramètres & règles + projections nb. d'hôtels.xlsx
001.queryVentes.csv
```

## Étape 2 — Extraire les formules

Lancer :

```bash
python scripts/extract_excel_rules.py
```

Objectif : produire des CSV de formules/commentaires.

## Étape 3 — Créer un mapping Excel → Python

Pour chaque règle :

```text
id règle
feuille
cellule
formule Excel
description métier
méthode Python
test associé
```

## Étape 4 — Compléter `revenue_rules.py`

Intégrer :

```text
clients hébergés
clients acheteurs
CA F&B
CA Non-F&B
mix catégories
impact TO
impact mètres linéaires
saisonnalité
```

## Étape 5 — Compléter `cost_rules.py`

Intégrer :

```text
coûts technos
coûts annexes
coûts agencement
maintenance
licences
amortissement
```

## Étape 6 — Compléter `recommendation_rules.py`

Implémenter toutes les règles de :

```text
REGLES POUR RECO DU CONCEPT
```

## Étape 7 — Recalculer les références ventes

Lancer :

```bash
python scripts/recompute_sales_references.py
```

Puis comparer :

```text
constantes Excel historiques
vs
références recalculées sur ventes enrichies
```

## Étape 8 — Tester Python vs Excel

Créer des tests sur les hôtels pivots :

```text
mêmes inputs
résultat Excel
résultat Python
écart toléré
```

## Étape 9 — Brancher XGBoost

Mettre dans `app/artifacts/` :

```text
model.joblib
feature_cols.json
target_cols.json
```

## Étape 10 — Enrichir l’interface

Ajouter :

```text
catégories/sous-catégories
warnings
trace règles
coûts détaillés
marges
ROI
comparaison ROD vs IA
```

---

# 23. Décisions keep / modify / drop sur le ZIP

## À garder

```text
app/server.py
app/config/settings.py
app/domain/models/*
app/domain/rules/traceability.py
app/domain/services/enrich_hotel.py
app/domain/services/rod_simulator.py
app/domain/services/sales_mix_extractor.py
app/routes/*
app/web/*
scripts/*
docs/audit/*
legacy_original/* pour audit uniquement
```

## À modifier

```text
revenue_rules.py
cost_rules.py
recommendation_rules.py
ai_predictor.py
optimizer.py
index.html
script.js
rod_reference_demo.json
```

## À ne pas utiliser comme production

```text
legacy_original/server.py
legacy_original/business_logic.py
legacy_original/rod_full_simulator.py
legacy_original/hotel_ca_projector.py
legacy_original/simulateur_corner.py
```

Ils restent utiles pour comprendre les tentatives précédentes, mais la nouvelle architecture doit prendre le relais.

---

# 24. Conclusion

Le ZIP construit une bonne fondation : il transforme ton projet en une architecture maintenable, orientée objet, avec séparation claire entre web, dataclasses, règles, services, référentiels, feature store et legacy.

Le point le plus important est que le projet ne prétend pas encore reproduire parfaitement Excel. Il met en place le cadre pour le faire correctement :

```text
règle Excel → règle Python traçable → test unitaire → validation métier
```

La prochaine vraie étape n’est pas de coder davantage au hasard. C’est de remplir progressivement les règles avec la source de vérité Excel, puis de brancher les références recalculées depuis les ventes pivots enrichies.

