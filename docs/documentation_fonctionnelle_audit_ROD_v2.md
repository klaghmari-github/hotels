# Documentation fonctionnelle détaillée et audit consolidé — ROD / Accor Store Simulator / IA

> Version générée le 2026-07-01 06:28 à partir des fichiers fournis dans `/mnt/data`, du ZIP d’audit, du fichier `consigne ROD.odt`, des classeurs Excel, des notebooks Jupyter et des scripts Python/Flask.  
> Hiérarchie retenue pour l’audit : **1) Excel ROD = source de vérité n°1**, **2) `consigne ROD.odt` = source de vérité fonctionnelle n°2**, **3) données de ventes = vérité observationnelle**, **4) notebooks/scripts = implémentations à auditer, pas vérité métier**.

## 0. Résumé exécutif

Le projet vise à construire un simulateur web ROD pour les hôtels Accor. Les directeurs d’hôtel saisissent ou valident des informations concernant leur hôtel, leurs contraintes et le coin de vente souhaité. Le système doit produire deux résultats comparables :

1. une **simulation ROD déterministe**, issue des règles et formules Excel ;
2. une **simulation IA**, plus riche, exploitant les caractéristiques hôtel, météo, POI, marque, concept, mètres linéaires et mix produit.

L’audit confirme que beaucoup de briques existent déjà : préparation ROD, préparation ventes, POI, météo, XGBoost, prototype Flask, enrichissement géographique, simulateurs. Mais l’implémentation n’est pas encore conforme à 100% à la stratégie décrite dans `consigne ROD.odt`. Les écarts les plus importants sont :

- Les targets de ventes sont actuellement plutôt **sommées par mois** sur les années historiques dans certains scripts, alors que la stratégie demande une **moyenne mensuelle historique par mois saisonnier**, peu importe la durée d’historique disponible par hôtel.
- `enrich_hotel.py` utilise des rayons POI **1 à 5 km**, alors que la stratégie demande **0.1 à 0.5 km**.
- Il manque encore un vrai **feature store persistant par hôtel**.
- Le simulateur Python `rod_simulator.py` est un prototype simplifié : il ne doit pas être considéré comme une reproduction fidèle des Excel tant qu’on n’a pas de tests cellule-à-cellule.
- L’application web Flask est utile pour la démonstration mais elle utilise encore un **vecteur de base issu d’un pivot** et des mocks/profils simplifiés ; elle doit être refactorée pour production.

## 1. Sources analysées

### 1.1. Source de vérité n°1 : classeurs Excel ROD

Les classeurs les plus importants sont :

- `ROD - Simulateurs + détail des coûts.xlsx` : simulateurs Simply / Liberty / Connected, revenus, coûts, marges, amortissement.
- `ROD - Paramètres & règles + projections nb. d'hôtels.xlsx` : règles de recommandation de concept, volumes par marque, règles de panel, prototype d’interface.
- `Récapitulatif de l'ensemble des données ROD.xlsx` et version enrichie : données ROD des hôtels pivots.
- `Analyse du poids des catégories de produit (2024-2025).xlsm` : historique/poids des catégories, avec formules et quelques références `#REF!` à traiter prudemment.

### 1.2. Source de vérité n°2 : consigne fonctionnelle

`consigne ROD.odt` décrit la stratégie fonctionnelle : simulateur web, feature store par hôtel, séparation ROD vs IA, XGBoost, stacking, moyenne mensuelle historique, test 2026, contraintes figées et optimisation.

Sections du fichier consigne :

```text
1. Contexte métier général
2. Rôle du simulateur ROD
3. Mètre linéaire
4. Règles ROD vs IA
5. Contraintes utilisateur et optimisation
6. Feature store par hôtel
7. Features météo, POI et Accor
8. Problème des ventes passées
9. Hôtels disponibles
10. Préparation des targets avec historiques de durée différente
11. Données 2026 comme test
12. Première couche de modèles XGBoost
13. Deuxième couche : stacking
14. Différence avec le simulateur “bête”
15. Ce qu’il ne faut pas faire
16. Vision produit finale
```

### 1.3. Données de ventes

Le fichier `001.queryVentes.csv` contient les colonnes de ventes : boutique, opérateur, machine, date/heure, statut, produit, quantité, prix, type F&B/non-F&B, gamme, marque, fournisseur, ticket, météo du jour/mois. Les catégories observées dans l’audit sont listées plus bas.

### 1.4. Code et notebooks

Les notebooks et scripts sont considérés comme des tentatives de production technique : certains sont utiles, d’autres sont des brouillons, et certains doivent être corrigés ou refondus.

## 2. Inventaire des feuilles et formules Excel

L’inventaire du ZIP montre les feuilles suivantes :

| file                                                           | sheet                       | max_row   | max_col   | non_empty   | formula_count   | comment_count   | note                                |
|:---------------------------------------------------------------|:----------------------------|:----------|:----------|:------------|:----------------|:----------------|:------------------------------------|
| 2026.02.Fevrier-ExportAccor(1).xlsx                            | Result 1                    | 3492      | 20        | 66245       | 0               | 0               | nan                                 |
| 2026.02.Fevrier-ExportAccor(1).xlsx                            | Query                       | 1         | 1         | 1           | 0               | 0               | nan                                 |
| Analyse du poids des catégories de produit (2024-2025)(1).xlsm | BASE                        | ?         | 38        | ?           | see xml         | ?               | xlsm huge; formulas parsed from XML |
| Analyse du poids des catégories de produit (2024-2025)(1).xlsm | Détails1                    | ?         | ?         | ?           | see xml         | ?               | xlsm huge; formulas parsed from XML |
| Analyse du poids des catégories de produit (2024-2025)(1).xlsm | Feuil1                      | ?         | 721       | ?           | see xml         | ?               | xlsm huge; formulas parsed from XML |
| ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx   | REGLES POUR RECO DU CONCEPT | 62        | 21        | 203         | 76              | 0               | nan                                 |
| ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx   | NB CH 1                     | 40        | 2         | 78          | 0               | 0               | nan                                 |
| ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx   | NB CH 2                     | 62        | 4         | 171         | 56              | 0               | nan                                 |
| ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx   | RESTO 1                     | 9         | 6         | 42          | 0               | 0               | nan                                 |
| ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx   | RESTO 2                     | 8         | 13        | 67          | 26              | 0               | nan                                 |
| ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx   | BAR 1                       | 9         | 6         | 39          | 0               | 0               | nan                                 |
| ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx   | BAR 2                       | 8         | 13        | 63          | 25              | 0               | nan                                 |
| ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx   | CRITERES POUR PANEL         | 9         | 5         | 24          | 0               | 0               | nan                                 |
| ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx   | TESTS SIMPLY                | 33        | 28        | 269         | 4               | 0               | nan                                 |
| ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx   | TESTS LIBERTY               | 33        | 35        | 338         | 5               | 0               | nan                                 |
| ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx   | TESTS CONNECTED             | 35        | 35        | 292         | 5               | 0               | nan                                 |
| ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx   | CORRECTIONS ND              | 12        | 2         | 10          | 0               | 0               | nan                                 |
| ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx   | DATA                        | 39        | 10        | 191         | 0               | 0               | nan                                 |
| ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx   | PROTOTYPE                   | 170       | 28        | 233         | 0               | 0               | nan                                 |
| ROD - Simulateurs + détail des coûts(1).xlsx                   | SIMULATEUR SIMPLY           | 187       | 20        | 401         | 135             | 1               | nan                                 |
| ROD - Simulateurs + détail des coûts(1).xlsx                   | SIMULATEUR LIBERTY          | 187       | 20        | 401         | 135             | 1               | nan                                 |
| ROD - Simulateurs + détail des coûts(1).xlsx                   | SIMULATEUR CONNECTED        | 187       | 22        | 406         | 133             | 1               | nan                                 |
| ROD - Simulateurs + détail des coûts(1).xlsx                   | COUTS - TECHNOS             | 36        | 25        | 230         | 69              | 0               | nan                                 |
| ROD - Simulateurs + détail des coûts(1).xlsx                   | COUTS - ANNEXES             | 24        | 18        | 166         | 51              | 0               | nan                                 |
| ROD - Simulateurs + détail des coûts(1).xlsx                   | COUTS - AGENCEMENT          | 37        | 30        | 763         | 532             | 0               | nan                                 |
| ROD - Simulateurs + détail des coûts(1).xlsx                   | REVENUS - MIX & MARGES      | 18        | 15        | 67          | 17              | 0               | nan                                 |
| ROD - Simulateurs + détail des coûts(1).xlsx                   | REVENUS - IMPACT TO         | 13        | 27        | 95          | 21              | 0               | nan                                 |
| Récapitulatif de l'ensemble des données ROD enrichies(2).xlsx  | RECAP DATA ROD              | 145       | 17        | 1507        | 0               | 0               | nan                                 |
| Récapitulatif de l'ensemble des données ROD.xlsx               | RECAP DATA ROD              | 137       | 17        | 1605        | 14              | 0               | nan                                 |
| Récapitulatif de l'ensemble des données ROD.xlsx               | Feuille2                    | 8         | 131       | 729         | 14              | 0               | nan                                 |
| Récapitulatif de l'ensemble des données ROD.xlsx               | Feuille3                    | 9         | 131       | 759         | 14              | 0               | nan                                 |

Commentaires Excel trouvés :

| file                                         | sheet                | cell   | author                                    | comment                                                                                                                                                                                                                                                                |
|:---------------------------------------------|:---------------------|:-------|:------------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| ROD - Simulateurs + détail des coûts(1).xlsx | SIMULATEUR SIMPLY    | M166   | tc={1A7A519E-6296-4FE5-93DC-CB380AD8A795} | [Commentaire à thread]                                                                                                                                                                                                                                                 |
|                                              |                      |        |                                           |                                                                                                                                                                                                                                                                        |
|                                              |                      |        |                                           | Votre version d’Excel vous permet de lire ce commentaire à thread. Toutefois, les modifications qui y sont apportées seront supprimées si le fichier est ouvert dans une version plus récente d’Excel. En savoir plus : https://go.microsoft.com/fwlink/?linkid=870924 |
|                                              |                      |        |                                           |                                                                                                                                                                                                                                                                        |
|                                              |                      |        |                                           | Commentaire :                                                                                                                                                                                                                                                          |
|                                              |                      |        |                                           |     Ne pas modifier                                                                                                                                                                                                                                                    |
| ROD - Simulateurs + détail des coûts(1).xlsx | SIMULATEUR LIBERTY   | M166   | tc={14AFF51F-3663-4FA2-BED3-71A7C993A5AE} | [Commentaire à thread]                                                                                                                                                                                                                                                 |
|                                              |                      |        |                                           |                                                                                                                                                                                                                                                                        |
|                                              |                      |        |                                           | Votre version d’Excel vous permet de lire ce commentaire à thread. Toutefois, les modifications qui y sont apportées seront supprimées si le fichier est ouvert dans une version plus récente d’Excel. En savoir plus : https://go.microsoft.com/fwlink/?linkid=870924 |
|                                              |                      |        |                                           |                                                                                                                                                                                                                                                                        |
|                                              |                      |        |                                           | Commentaire :                                                                                                                                                                                                                                                          |
|                                              |                      |        |                                           |     Ne pas modifier                                                                                                                                                                                                                                                    |
| ROD - Simulateurs + détail des coûts(1).xlsx | SIMULATEUR CONNECTED | M166   | tc={32C93C77-C608-4381-A13C-C796F940A9A3} | [Commentaire à thread]                                                                                                                                                                                                                                                 |
|                                              |                      |        |                                           |                                                                                                                                                                                                                                                                        |
|                                              |                      |        |                                           | Votre version d’Excel vous permet de lire ce commentaire à thread. Toutefois, les modifications qui y sont apportées seront supprimées si le fichier est ouvert dans une version plus récente d’Excel. En savoir plus : https://go.microsoft.com/fwlink/?linkid=870924 |
|                                              |                      |        |                                           |                                                                                                                                                                                                                                                                        |
|                                              |                      |        |                                           | Commentaire :                                                                                                                                                                                                                                                          |
|                                              |                      |        |                                           |     Ne pas modifier                                                                                                                                                                                                                                                    |

Point important : il y a seulement 3 commentaires Excel inventoriés dans `ROD - Simulateurs + détail des coûts.xlsx`, tous en cellule `M166` des simulateurs Simply/Liberty/Connected, avec l’indication **“Ne pas modifier”**. Cela signale que la zone concernée doit être protégée lors de la transcription Python.

## 3. Description fonctionnelle des classeurs Excel

### 3.1. `ROD - Simulateurs + détail des coûts.xlsx`

Ce fichier est la base du simulateur ROD déterministe. Il contient 8 feuilles : `SIMULATEUR SIMPLY`, `SIMULATEUR LIBERTY`, `SIMULATEUR CONNECTED`, `COUTS - TECHNOS`, `COUTS - ANNEXES`, `COUTS - AGENCEMENT`, `REVENUS - MIX & MARGES`, `REVENUS - IMPACT TO`.

#### 3.1.1. Feuilles simulateurs par concept

Ces trois feuilles calculent pour un concept donné : paramètres hôtel, espace retail, mix F&B/non-F&B, nombre de clients, nombre de ventes, CA, marges, coûts, marge nette et amortissement.

| concept | nb chambres ref | guests/ch | TO ref | m lin ref | mix F&B | mix N-F&B | marge F&B | marge N-F&B | ventes mensuelles ref | CA HT F&B ref | CA HT N-F&B ref |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SIMPLY | 129 | 1.7 | 0.80 | 6 | 0.40 | 0.60 | 2.6 | 1.45 | 231 | 533 | 187 |
| LIBERTY | 142 | 2.2 | 0.70 | 8 | 0.70 | 0.30 | 2.6 | 2.0 | 312 | 1055 | 424 |
| CONNECTED | 305 | 1.8 | 0.75 | 7 | 0.80 | 0.20 | 2.6 | 1.8 | 534 | 3503 | 131 |

Formules principales observées :

```text
Chambres occupées = nb_chambres × TO
Clients hébergés / jour = nb_chambres × TO × guests_per_chambre
Clients hébergés / mois = clients hébergés / jour × 30.5
Taux acheteurs mensuels = nb_ventes_ref / clients_hébergés_mois_ref
Marge pondérée = SUMPRODUCT(marges, mix) / SUM(mix)
Impact mètre linéaire = CA pilote / m_lin_ref
Marge nette mensuelle = marge produits - coûts mensuels
Amortissement mois = coûts initiaux / marge nette mensuelle
Amortissement années = amortissement mois / 12
```

Lecture fonctionnelle : les feuilles simulent l’effet du nombre de chambres, du TO, des mètres linéaires et du mix produit sur les ventes et la rentabilité. Elles intègrent ensuite les coûts techno, annexes et agencement.

#### 3.1.2. `REVENUS - IMPACT TO`

Cette feuille mesure l’effet du taux d’occupation sur les revenus et calcule un impact pour `0.01` de TO. Elle sert à relier les revenus aux pilotes plutôt qu’à faire une règle de trois brute.

#### 3.1.3. `REVENUS - MIX & MARGES`

Cette feuille définit ou récapitule les mix F&B/non-F&B et les marges par concept/pilote. Elle utilise `SUMPRODUCT` pour calculer une marge pondérée. Les scripts Python doivent vérifier l’unité métier de ces coefficients avant d’en faire des pourcentages.

#### 3.1.4. `COUTS - TECHNOS`

Cette feuille donne les coûts des équipements technologiques : scanner, caisse, vitrine, frigo froid, frigo ambiant, licence logicielle. Elle distingue achat et location pour certains concepts et amortit des coûts sur environ 60 mois.

#### 3.1.5. `COUTS - ANNEXES`

Cette feuille calcule des coûts annexes, notamment électricité, personnel et coûts récurrents associés aux équipements. Les scripts actuels qui utilisent des coûts simplifiés par mètre linéaire ne reproduisent pas encore cette feuille.

#### 3.1.6. `COUTS - AGENCEMENT`

Cette feuille calcule les coûts d’agencement par mètre linéaire et par niveau : Classic, Premium, Bespoke. L’amortissement observé est sur 84 mois.

```text
Classic : environ 1000 €/m
Premium : environ 1200 €/m
Bespoke : environ 2200 €/m
mensualisation : coût total / 84
```

### 3.2. `ROD - Paramètres & règles + projections nb. d'hôtels.xlsx`

Ce fichier définit les règles de recommandation et les projections par typologie d’hôtel.

#### 3.2.1. `REGLES POUR RECO DU CONCEPT`

Règles observées :

```text
Règle #1 : nombre de chambres
- Simply : entre 0 et 49 chambres
- Liberty / Connected : plus de 50 chambres selon les autres règles

Règle #2 : catégories non-F&B
- min. 1 des catégories : Cosmetics, Kids items, Ready-to-wear, Accessories, Souvenirs

Règle #3 : mètres linéaires
- si l’hôtel souhaite plus de 4 mètres linéaires : Liberty Store
- si <= 4 mètres linéaires : autre orientation selon critères

Règle #4 : vitrine réfrigérée existante
- question : l’hôtel possède-t-il déjà une vitrine réfrigérée ?

Règle #5 : TO moyen YTD
- dernier tri selon TO < 70% ou TO >= 70%
```

Audit : `rod_rules.py` reprend plusieurs de ces règles, mais contient aussi une “politique high-end” qui n’est pas clairement confirmée dans les sources. Elle doit être validée ou retirée.

#### 3.2.2. `NB CH 1` / `NB CH 2`

Ces feuilles donnent la distribution des hôtels par marque et tranche de chambres : IBIS BUDGET 342, IBIS STYLES 267, IBIS 362, MERCURE 255, NOVOTEL 117, total général 1343. Elles servent à projeter le potentiel de déploiement par marque.

#### 3.2.3. `RESTO 1/2` et `BAR 1/2`

Ces feuilles résument la présence de restaurants et bars par marque. Elles enrichissent le profil hôtel, car le potentiel corner dépend probablement de l’offre F&B déjà présente.

#### 3.2.4. `CRITERES POUR PANEL`

Cette feuille donne les critères pour construire un panel représentatif de tests simulateur par marque : tranche de chambres, nombre de restaurants, nombre de bars.

#### 3.2.5. `TESTS SIMPLY`, `TESTS LIBERTY`, `TESTS CONNECTED`

Ces feuilles comparent des revenus “THOMAS” et “ROD”, marge nette et amortissement. Elles doivent devenir les jeux de tests unitaires du simulateur Python.

#### 3.2.6. `DATA`

Cette feuille documente les sources de données : 360 Hotel Referential, Parc Hôtel Southern Europe, exports lat/lon, ville, marque, nombre de chambres. Elle est utile pour construire le feature store.

#### 3.2.7. `PROTOTYPE`

Cette feuille décrit l’interface cible : paramètres hôtel, retail spaces, concepts proposés, équipements, agencement, règles d’affichage et messages d’erreur. Éléments observés : scanner minimum pour Simply, caisse minimum pour Liberty, frigo froid/ambiant pour Connected, une seule solution sélectionnable à la fois.

## 4. Données de ventes : catégories, gammes, produits

Le fichier de ventes contient `TYPE`, `GAMME`, `NOM DU PRODUIT`, `MARQUE`. Le catalogue extrait est :

| TYPE    | GAMME          |   nb_lignes |   nb_produits_distincts | top_produits                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | top_marques                                                                                                                                       |
|:--------|:---------------|------------:|------------------------:|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------|
| F&B     | ALCOOL         |        1727 |                      28 | Bière Heineken (25cl) (581) ; Grand vin Mercure (254) ; Bière Gallia (25cl) (246) ; Champagne demi bouteille (189) ; Heineken  (136) ; Gallia (49) ; Demi bouteille de vin (34) ; Moulin à vent demi bouteille  (27) ; Vin Demi Blanc (23) ; Bouteille de vin (18) ; BIERE BACCHANTE BLANCHE ETERNELLE (17) ; BIERE BACCHANTE MEGEVANNE DOREE (16)                                                                                                                                                                                                                                                                           | HEINEKEN (717) ; - (343) ; GALLIA (295) ; MERCURE (254) ; BACCHANTE (48) ;  -  (35) ; DUVEL (14) ; LA DEBAUCHE (13)                               |
| F&B     | FOOD SALEE     |       13312 |                     151 | CHIPS NATURE SEL GUERANDE 90g (1628) ; CHIPS DE POULET ROTI 45g (1467) ; Chips (90g) (599) ; CLUB JAMBON BEURRE FLEUR DE SEL DE GUÉRANDE SALADE (582) ; BURGER BISTROT BŒUF CHAROLAIS (565) ; CLUB POULET MAYONNAISE (560) ; SPAGHETTI ALLA BOLOGNESE (502) ; WRAP VEGGIE ŒUF PARMESAN TOMATES (469) ; CLUB THON A LA NICOISE (378) ; CHIPS DE POMME NATURE (358) ; RAVIOLI RICOTTA EPINARD A LA FIORENTINA (347) ; GNOCHI CACIO E PEPE (305)                                                                                                                                                                                | -  (9872) ; - (1154) ; SODEBO (457) ; LAYS (357) ; BEENDI (312) ; MONOPRIX (245) ; BRETS (220) ; TUC (177)                                        |
| F&B     | FOOD SUCREE    |       15915 |                     163 | TWIX 50g (1182) ; KINDER BUENO 43g (1149) ; SNICKERS 50g (1072) ; LION 42g (1057) ; M&M'S 45g (1013) ; TOBLERON LAIT 50G (795) ; Barre chocolatée (ex : Mars, Twix, Lion...) (737) ; MARS 51g (623) ; BOUNTY 57g (595) ; YAOURT FRAISE FRAMBOISE (413) ; YAOURT NATURE 125G (295) ; MOUSSE AU CHOCOLAT A L'ANCIENNE (291)                                                                                                                                                                                                                                                                                                    | -  (2137) ; - (1682) ; KINDER (1612) ; TWIX (1444) ; M&M'S (1360) ; SNICKERS (1280) ; LION (1154) ; HARIBO (894)                                  |
| F&B     | SANS ALCOOL    |       44249 |                     130 | VITTEL 50cl (7463) ; COCA COLA ZERO  33CL (3717) ; COCA COLA 33CL (3334) ; L'EAU NEUVE 50CL (1916) ; SAN PELLEGRINO  50cl (1895) ; L'Eau Neuve (50cl) (1750) ; SPRITE  33CL (1485) ; Vittel en verre (50cl) (1419) ; ORANGINA   33CL (1146) ; FUZE TEA 33cl (1013) ; EVIAN 33 CL (1007) ; FANTA ORANGE  33CL (967)                                                                                                                                                                                                                                                                                                           | COCA COLA (10511) ; VITTEL (9830) ; EAU NEUVE (4928) ; SAN PELLEGRINO (2872) ; PERRIER (2012) ; SPRITE (1786) ; ORANGINA (1521) ; FUZE TEA (1510) |
| F&B     | SOUVENIRS      |          38 |                       8 | Peluche Chamois (12) ; Confiture Parisienne (7) ; La French Baguette (7) ; Glacons De Megeve (6) ; Miel de Fleurs Crémeux 140g (3) ; Miel de Sapin 140g (1) ; Grelots Aux Beaufort (1) ; Crozet de Savoie au Sarrasin 320g (1)                                                                                                                                                                                                                                                                                                                                                                                               | MONOPRIX (14) ; - (12) ; DIVERS (12)                                                                                                              |
| NON-F&B | #REF!          |         444 |                      53 | Cable de recharge (67) ; serviette de plage bleue 145 x 85 cm (44) ; Trousse de toilette Femme (38) ; Peluche Ourson (32) ; Peluche Stitch (25) ; Echarpe Mickey / Scarf  (23) ; Tot Bag Mickey  (22) ; Trousse de toilette Homme (13) ; GRAND PARAPLUIE NOIR ET GRIS (12) ; Casquette Adulte Grise (11) ; Gel Hydroalcoolique (11) ; CHAUSSURES AQUATIQUES ADULTE - AQUASHOES 100 GRI 44-45  UK 9.5-10.5 (10)                                                                                                                                                                                                               | DECATHLON (212) ; - (90) ; DISNEY (79) ; MONOPRIX (41) ; KUMQUAT (22)                                                                             |
| NON-F&B | ACCESSOIRES    |         586 |                      56 | TONGS HOMME TO 100 NOIR (56) ; TONGS FEMME 100 NOIR (54) ; Chaussette Mickey / Socks (44) ; Lunettes de natation (36) ; MF COMPACT XL TOWEL BLUE PETROL (26) ; Trousse de toilette Homme (25) ; Bonnet Mickey / Cap (24) ; SERVIETTE DE PLAGE VERTE XL (20) ; CHAUSSURES AQUATIQUES ADULTE - AQUASHOES 100 GRI 38-39   UK 5-5.5 (18) ; Rains Hillo Week End Bag Medium  (18) ; Rains Hillo Week End Small  (17) ; SERVIETTE DE BAIN MICROFIBRE ORANGE TAILLE XL 110 X 175 CM (15)                                                                                                                                            | DECATHLON (476) ; DISNEY (68) ; RAINS (40) ; KUMQUAT (2)                                                                                          |
| NON-F&B | COSMETIQUE     |         383 |                      48 | SPRAY FACIAL FACIAL BRUMISATEUR (64) ; Trousse de voyage (46) ; Baume à levre (39) ; Rituals Gel Douche Moussant (26) ; RitualsSmall Gift Set (19) ; Spray facial Brumisateur Evian (19) ; Baume Lévres karité BIO (13) ; SPRAY PROTECTION SOLAIRE ACTIVE SPF 30 50 ML (12) ; Rituals Body Cream (12) ; Rituals Gift Set L (11) ; Parfum Mercure (9) ; Crème solaire Corinne de Farme 50  (9)                                                                                                                                                                                                                                | MONOPRIX (84) ; RITUALS (83) ;  -  (83) ; - (46) ; NUXE (34) ; RESPIRE (15) ; DECATHLON (14) ; NIVEA (13)                                         |
| NON-F&B | JEUX / ENFANTS |         420 |                      62 | Peluche Mickey Small (54) ; Mes coloriages avec stickers, Stitch (34) ; Ou ce cache Stitch (29) ; Mes coloriages avec stickers, Encanto la fantastique famille Madrigal (25) ; Mes coloriages avec stickers (22) ; Le roi Lion, ou ce cache Simba ? (20) ; Les deux font la paire (17) ; Héros et Vilains, qui suis-je (16) ; Mes coloriages avec stickers - Vice-Versa 2 (16) ; Peluche Mini (14) ; Bouée piscine gonflable imprimée grande taille 92 cm avec poignées (14) ; Peluche Mickey (13)                                                                                                                           | DISNEY (299) ; MONOPRIX (74) ; LEGO (15) ; DECATHLON (14) ; UNO (5) ; MIKADO (5) ; RUBIKS CUBE (3) ; QUI EST CE (3)                               |
| NON-F&B | PAP            |         290 |                      50 | T-shirt Blanc Mickey / White T-shirt (64) ; BOARDSHORT HENDAIA ECO NT BLEU (60) ; Pull Blanc Mickey/ White Pullover (43) ; Pull Vert Mickey/ Green Pullover (34) ; MAILLOT DE BAIN DE NATATION 1 PIÈCE FEMME HEVA U NOIR (9) ; MAILLOT DE BAIN NATATION GARÇON - BOXER 100 BASIC - BLEU (5) ; MAILLOT DE BAIN NATATION GARÇON - SWIMSHORT 100 BASIC - MARINE (4) ; Boxer de bain natation garçon speedo imprime bleu - 12 ans (4) ; SHORT BLEU MARINE L (4) ; MAILLOT DE BAIN DE NATATION 1 PIÈCE FILLE BASIC VIOLET (3) ; Boxer de bain natation garçon speedo imprime bleu - 8 ans (3) ; polaire grise Homme taille XL (3) | DECATHLON (147) ; DISNEY (143)                                                                                                                    |
| NON-F&B | SOS            |        7414 |                      61 | GOURDE (1319) ; ADAPTATEUR UNIVERSEL (970) ; KIT DENTAIRE COLGATE (834) ; Gourde en verre Novotel (768) ; GOURDE EN VERRE NOVOTEL (704) ; Gourde (567) ; Kit Dentaire Colgate (447) ; Adaptateur Universel (373) ; KIT RASAGE (340) ; SERVIETTES LOVE & GREEN BIO X 2 (164) ; PARAPLUIE POCKET (151) ; Kit Rasage (117)                                                                                                                                                                                                                                                                                                      | -  (3942) ; NOVOTEL (1659) ; COLGATE (1281) ; LOVE & GREEN (242) ; MONOPRIX (124) ; - (119) ; MERCURE (25) ; DECATHLON (12)                       |
| NON-F&B | SOUVENIRS      |         142 |                      19 | Carte Postale  (79) ; Bougie Fleurs d'alpage (7) ; Mug (7) ; Bougie Fruits d'altitude (6) ; Pochette en tissu "Paris mon amour" (6) ; Bougie Lac & Montagne (6) ; Tote-bag parisienne (6) ; Bougie Feu de bois  (5) ; Bougie Cascade (4) ; Le Béret Français - BLEU ROYAL (extensible tour de tête 55 à 62 cm) (3) ; Le Béret Français - ECRU (extensible tour de tête 55 à 62 cm) (3) ; Le Béret Français - ROUGE (extensible tour de tête 55 à 62 cm) (2)                                                                                                                                                                  | - (118) ; MONOPRIX (23) ; DIVERS (1)                                                                                                              |
| nan     | nan            |         754 |                      73 | SAN BENDETTO GAZEUSE (124) ; SAN BENDETTO  PLATE (98) ; Boites De Biscuits 240g (43) ; Porte clé - Novotel (38) ; Peluche porte Clés (28) ; Petite Boite De Biscuits 120g (24) ; Peluche Marmotte (21) ; Minute Maid Pomme (20) ; Chips du Crétin (19) ; Peluche ECUREUIL (19) ; Sachets de Bonbons - Colliers (18) ; Mini Tarte à la Myrtille 300g (15)                                                                                                                                                                                                                                                                     | nan                                                                                                                                               |

Audit sur catégorie/sous-catégorie : dans les ventes, le niveau réellement disponible est `TYPE` → `GAMME` → produit. La notion de sous-catégorie de l’interface ROD doit donc être définie par mapping métier si elle ne correspond pas directement à `GAMME`.

## 5. Audit de conformité à la consigne

### 5.1. Ce qui est conforme

- Séparation ROD vs IA.
- Usage pandas, pas Spark.
- Anti-fuite des cibles dans `prepare_X_y_clean.py`.
- 2026 identifiée comme période test.
- Prototype Flask avec enrichissement et prédiction.
- Apprentissage sur hôtels pivots et projection vers hôtels sans transactions.

### 5.2. Écarts critiques

| exigence                                                      | etat_actuel                                                                                       | statut         | action                                                                                               | priorite   |
|:--------------------------------------------------------------|:--------------------------------------------------------------------------------------------------|:---------------|:-----------------------------------------------------------------------------------------------------|:-----------|
| Feature store par hôtel avec cache                            | enrich_hotel calcule mais ne crée pas un stockage par hotel_id structuré.                         | Non terminé    | Créer dossiers data/feature_store/hotels/{hotel_id}/geo, poi, weather, profile, inputs, simulations. | Haute      |
| Rayons POI 0.1 à 0.5 km                                       | enrich_hotel utilise 1 à 5 km; anciens poi_prepared ont 0.1-0.5 km selon logs.                    | Ecart          | Corriger enrich_hotel et harmoniser noms de colonnes.                                                | Haute      |
| Distance plage la plus proche                                 | Mentionnée dans consigne; pas observée dans code.                                                 | Manquant       | Ajouter source géographique et cache distance_beach_km.                                              | Haute      |
| Targets moyennes mensuelles par mois/catégorie/sous-catégorie | prepare_ml_dataset et transaction_data agrègent par somme sur années.                             | Ecart critique | Passer à moyenne par mois saisonnier et ajouter colonnes de fiabilité.                               | Haute      |
| Sous-catégories produit                                       | Ventes contiennent TYPE, GAMME, produit; pas de colonne sous-catégorie officielle.                | A définir      | Créer mapping produit→sous-catégorie à partir de l’UI ROD / Excel / métier.                          | Haute      |
| Simulation ROD fidèle cellule-à-cellule                       | rod_simulator hardcode et simplifie.                                                              | Partiel        | Exporter paramètres Excel et tests unitaires.                                                        | Haute      |
| Simulation IA plus précise                                    | XGBoost baseline et app POC existent mais N=5, features très larges.                              | Partiel        | Construire V1 avec agrégats + LOHO + calibration ROD.                                                | Haute      |
| Optimisation sous contraintes verrouillées                    | business_logic et server reallocate existent, mais pas un vrai solveur complet avec champs figés. | Partiel        | Créer StoreConfiguration + LockedConstraints + grid search/pruning.                                  | Haute      |
| Comparer sortie ROD vs sortie IA                              | Endpoints /api/rod_simulate et /api/predict existent mais pas cadrage produit complet.            | Partiel        | Standardiser un objet SimulationResult commun.                                                       | Haute      |
| Pas de Spark, pandas only                                     | Tous scripts sont pandas, conforme.                                                               | Conforme       | Conserver pandas + parquet/csv local.                                                                | Haute      |

## 6. Quoi garder / modifier / jeter

| composant                                    | etat                                         | decision                      | raison                                                                                                                                                                         | action                                                                                                                                  | priorite   |
|:---------------------------------------------|:---------------------------------------------|:------------------------------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------|:-----------|
| Excels ROD règles + simulateurs              | Source de vérité                             | GARDER                        | C’est la source de vérité n°1 demandée : règles concept, coûts, revenus, marges, amortissement.                                                                                | Reproduire les feuilles en Python via tables de paramètres + tests unitaires cellule-à-cellule.                                         | Haute      |
| consigne ROD.odt                             | Source de vérité fonctionnelle               | GARDER                        | C’est la source de vérité n°2 : objectifs produit, feature store, stratégie ML, contraintes et stacking.                                                                       | Transformer en backlog fonctionnel et critères d’acceptation.                                                                           | Haute      |
| rod_data(1).ipynb                            | Production technique utile                   | GARDER / INDUSTRIALISER       | Aplatissement ROD hiérarchique propre, utile pour passer du questionnaire Excel à une table hôtel.                                                                             | Extraire en module Python versionné avec tests et dictionnaire de colonnes.                                                             | Haute      |
| rod_data_v0.ipynb                            | Ancienne tentative                           | ARCHIVER                      | Version antérieure remplacée par rod_data plus complet.                                                                                                                        | Conserver comme historique, ne pas maintenir.                                                                                           | Basse      |
| transaction_data.ipynb                       | Utile mais à corriger                        | MODIFIER                      | Prépare les ventes par mois/type/gamme, mais l’approche actuelle agrège/somme les années au lieu de produire la moyenne mensuelle historique voulue.                           | Calculer mean par mois saisonnier avec nb_observations, années_count, total_tickets_count.                                              | Haute      |
| prepare_ml_dataset.py                        | Utile mais non conforme à 100%               | MODIFIER                      | Script formalise le pipeline ML mais pivote avec somme sur les années <2026; la consigne demande moyenne mensuelle indépendamment de la durée d’historique.                    | Réécrire prepare_sales_monthly_wide en version moyenne mensuelle + fiabilité.                                                           | Haute      |
| prepare_X_y_clean.py                         | Conforme au principe anti-leakage            | GARDER / RENFORCER            | Identifie les cibles montant/nbr_ventes et les enlève des features.                                                                                                            | Garder, ajouter whitelist/blacklist de colonnes et tests de fuite.                                                                      | Haute      |
| ml_xgboost_baseline.py / ml.ipynb            | Base de modèle utile mais fragile            | MODIFIER                      | XGBoost est cohérent, mais N=5 et p très grand; risque de surapprentissage.                                                                                                    | Réduire la granularité d’abord : global mensuel, catégorie, sous-catégorie; validation leave-one-hotel-out; OOF pour stacking.          | Haute      |
| Stacking                                     | Stratégie définie, pas encore industrialisée | A DEVELOPPER                  | La couche 2 avec prédictions L1 comme features est dans la stratégie, pas encore un pipeline validé.                                                                           | Implémenter OOF predictions L1 puis L2, sans utiliser les vraies cibles 2026.                                                           | Haute      |
| poi.ipynb / weather_data.ipynb               | Préparation utile                            | GARDER / ADAPTER              | Agrège POI et météo déjà dans l’esprit feature store.                                                                                                                          | Mettre en fonctions réutilisables, aligner formats mensuels et rayons 0.1 à 0.5 km.                                                     | Haute      |
| enrich_hotel.py                              | Très utile mais écart majeur                 | MODIFIER                      | Le module enrichit géocodage/POI/météo, mais les rayons par défaut sont 1-5 km alors que la consigne demande 0.1-0.5 km. Pas de cache feature store robuste ni distance plage. | Corriger DEFAULT_RADII=[0.1,0.2,0.3,0.4,0.5], ajouter persistance par hotel_id, adresse, date d’enrichissement, distance plage.         | Haute      |
| server.py + index.html/script.js/style.css   | Prototype web utile                          | GARDER COMME POC / REFACTORER | L’application Flask existe avec écrans ROD, enrichissement et prédiction, mais utilise un vecteur base pivot et des mocks.                                                     | Séparer API de production, service feature_store, service simulation_excel, service simulation_ia; éviter le template pivot par défaut. | Haute      |
| rod_simulator.py                             | Prototype non suffisant comme source vérité  | MODIFIER FORTEMENT            | Le fichier dit “fidèle”, mais il hardcode des valeurs et simplifie plusieurs formules/coûts; il ne couvre pas toutes les catégories/sous-catégories.                           | Re-générer à partir des tables Excel, avec tests comparant sorties Python vs cellules Excel.                                            | Haute      |
| rod_rules.py                                 | Prototype utile mais à vérifier              | MODIFIER                      | Il encode des règles du classeur, mais contient aussi des éléments stratégiques non clairement confirmés comme politique high-end; à valider.                                  | Reprendre uniquement les règles présentes dans Excel et consigne; documenter toute règle ajoutée comme hypothèse.                       | Haute      |
| business_logic.py                            | Prototype métier intéressant mais hypothèses | MODIFIER                      | Contient funnel, reallocation, P&L, optimiser simple; mais buyer rate 0.35 et coûts simplifiés doivent être remplacés par Excel ou données.                                    | Paramétrer depuis Excel; rendre les hypothèses visibles; séparer naturel vs contraint.                                                  | Haute      |
| rod_full_simulator.py                        | Architecture cible intéressante              | MODIFIER                      | Regroupe revenus/coûts/optimisation, mais coûts simplifiés et potentiellement non conformes.                                                                                   | En faire l’orchestrateur après extraction fidèle des règles Excel.                                                                      | Moyenne    |
| hotel_ca_projector.py / simulateur_corner.py | Anciennes approches hybrides                 | ARCHIVER / REUTILISER IDEES   | Utile pour comprendre la projection pivot et la saisonnalité, mais moins aligné avec la nouvelle stratégie feature store + XGBoost + stacking.                                 | Réutiliser idées de saisonnalité et mix; ne pas l’utiliser comme moteur final.                                                          | Moyenne    |
| association_gamme/product notebooks          | Exploration utile                            | ARCHIVER / REUTILISER         | Analyse de panier par gamme/produit utile pour assortiment, mais pas coeur de prédiction CA V1.                                                                                | Conserver pour moteur d’assortiment / exemples produits; nettoyer doublons small vs enrichi.                                            | Moyenne    |
| ml_v0.ipynb / rod_selection.ipynb            | Brouillons / anciennes pistes                | ARCHIVER                      | Contiennent essais de dummies/keras/sélection manuelle; utiles historiquement, mais pas moteur cible.                                                                          | Conserver hors pipeline prod.                                                                                                           | Basse      |

## 7. Audit des notebooks et scripts

| fichier                        | description fonctionnelle                             | décision                      | commentaire                                                                                |
|:-------------------------------|:------------------------------------------------------|:------------------------------|:-------------------------------------------------------------------------------------------|
| rod_data(1).ipynb              | Aplatissement ROD Excel hiérarchique vers table hôtel | Garder/industrialiser         | Base solide pour feature hotel_profile et ROD inputs.                                      |
| transaction_data.ipynb         | Agrégation ventes par hôtel/mois/type/gamme           | Modifier                      | Remplacer somme annuelle cumulée par moyenne mensuelle historique.                         |
| poi.ipynb                      | Agrégation POI F&B/non-F&B par rayons                 | Garder/adapter                | Aligner avec feature store.                                                                |
| weather_data.ipynb             | Agrégats météo mensuels                               | Garder/adapter                | Réutiliser pour features weather_monthly.                                                  |
| merge_data.ipynb               | Fusion ROD+POI+weather+transactions                   | Modifier                      | Ne pas créer un seul monolithe final trop large; garder tables séparées puis scoring view. |
| ml.ipynb                       | XGBoost multi-output sur 5 pivots                     | Modifier                      | POC; limiter dimensions, mieux valider.                                                    |
| ml_v0.ipynb                    | Essai ancien dummies/ML                               | Archiver                      | Brouillon remplacé.                                                                        |
| rod_selection.ipynb            | Sélection manuelle de colonnes ROD                    | Archiver/extraire idées       | Peut servir au dictionnaire de features.                                                   |
| association_gamme.ipynb        | Règles association par GAMME                          | Archiver utile                | Assortiment et cross-sell, pas prédiction centrale.                                        |
| association_product.ipynb      | Règles association produit                            | Archiver utile                | Exemples produits / panier.                                                                |
| data_augmentation.ipynb        | Collecte météo/POI via APIs                           | Garder/refactorer             | Base de enrich_hotel.                                                                      |
| rod_sim_cout(3).ipynb          | Classes RevenusData/SimRevenusData                    | Garder comme brouillon métier | Ancêtre des formules Excel revenus/coûts.                                                  |
| server.py                      | Backend Flask POC                                     | Garder/refactorer             | POC web; ne doit pas rester lié à un pivot template.                                       |
| index.html/script.js/style.css | Interface ROD IA POC                                  | Garder/refactorer             | Écrans utiles pour démonstration.                                                          |
| enrich_hotel.py                | Géo+POI+météo                                         | Modifier                      | Rayons à corriger, cache à ajouter.                                                        |
| rod_simulator.py               | Simulation ROD simplifiée                             | Refaire selon Excel           | Ne pas considérer fidèle sans tests cellule-à-cellule.                                     |
| rod_rules.py                   | Règles concept                                        | Vérifier/refaire              | Extraire automatiquement ou manuellement depuis Excel.                                     |
| business_logic.py              | Funnel, mix, P&L, optimiser                           | Refactorer                    | Remplacer hypothèses par paramètres Excel.                                                 |
| prepare_X_y_clean.py           | Séparation X/y anti-fuite                             | Garder                        | Bon principe.                                                                              |
| prepare_ml_dataset.py          | Dataset ML large                                      | Modifier critique             | Moyennes mensuelles + fiabilité.                                                           |
| ml_xgboost_baseline.py         | XGBoost baseline                                      | Garder comme baseline         | Ajouter validation robuste et agrégats.                                                    |
| rod_full_simulator.py          | Orchestrateur revenus/coûts/optimisation              | Garder/refaire formules       | Bonne cible architecture, calculs à fiabiliser.                                            |
| hotel_ca_projector.py          | Projection CA pivot/hôtel                             | Archiver ou réutiliser idées  | Ancien moteur hybride.                                                                     |
| simulateur_corner.py           | Simulateur CA par m_lin/catégorie                     | Archiver ou réutiliser idées  | Utile pour démo ancienne, pas moteur cible.                                                |

### Détails importants

#### `transaction_data.ipynb` et `prepare_ml_dataset.py`

Ils calculent `montant = PRIX TTC × QUANTITE` et créent des colonnes mensuelles par type/gamme. Mais ils doivent être corrigés pour produire une moyenne mensuelle historique, pas un cumul sur toutes les années disponibles.

```python
# cible attendue
avg_montant_mois_gamme = mean(montant_annuel_mois_gamme)
avg_nbr_ventes_mois_gamme = mean(nbr_ventes_annuel_mois_gamme)
nb_years_observed = nunique(annee)
```

#### `enrich_hotel.py`

Le concept est bon : géocodage, météo, POI. Mais les rayons doivent être corrigés :

```python
# actuel observé
DEFAULT_RADII = [1.0, 2.0, 3.0, 4.0, 5.0]

# attendu selon consigne
DEFAULT_RADII = [0.1, 0.2, 0.3, 0.4, 0.5]
```

Il faut aussi ajouter le cache feature store par hôtel et la distance plage.

#### `server.py`

Le backend est un POC utile. Mais `get_base_row()` part de la première ligne pivot et applique des overrides. Pour un vrai nouvel hôtel, il faut construire le vecteur depuis son feature store, pas depuis un pivot.

#### `rod_simulator.py`

Prototype utile mais pas encore fidèle. Il simplifie les feuilles Excel et ne doit pas être la source métier finale. La bonne approche : extraire tables Excel + tests Python vs Excel.

#### `rod_rules.py`

À vérifier contre `REGLES POUR RECO DU CONCEPT`. Toute politique non présente dans l’Excel ou la consigne doit être marquée comme hypothèse.

#### `business_logic.py` et `rod_full_simulator.py`

Ils esquissent bien la logique : funnel, reallocation, P&L, optimiser. Mais les valeurs hardcodées doivent être remplacées par les paramètres Excel et les données observées.

## 8. Architecture cible recommandée

### 8.1. Feature store local pandas

```text
data/
  accord/
    global/
      brand_distribution.parquet
      concept_rules.parquet
      concept_costs.parquet
      rod_excel_parameters.parquet

  feature_store/
    hotels/
      {hotel_id}/
        identity/hotel_profile.parquet
        geo/geocoding.parquet
        geo/beach_distance.parquet
        poi/poi_radius.parquet
        weather/weather_monthly_12m.parquet
        rod_input/director_inputs.parquet
        simulations/simulation_history.parquet
```

### 8.2. Tables pandas séparées

```text
df_hotel_profile
df_accord_global
df_weather_monthly
df_poi_radius
df_director_input
df_store_config
df_sales_targets_monthly_avg
df_model_input
```

### 8.3. Targets IA

```text
1 ligne = hôtel × mois × catégorie/sous-catégorie

avg_montant_vente
avg_nbr_ventes
nb_observations
nb_years_observed
```

### 8.4. Modélisation IA

Couche 1 : modèles XGBoost indépendants par granularité : global mensuel, catégorie, gamme/sous-catégorie.  
Couche 2 : stacking avec prédictions out-of-fold de couche 1 comme features pour rendre les prédictions cohérentes entre mois et catégories.

### 8.5. Optimisation

L’optimiseur doit utiliser les prédictions IA comme objectif, respecter les contraintes figées, et comparer les configurations autorisées.

```python
StoreConfiguration(
    concept='LIBERTY',
    m_lin=4,
    fb_ratio=0.7,
    non_fb_ratio=0.3,
    allowed_categories=[...],
    locked_fields=['m_lin', 'alcool']
)
```

## 9. Roadmap de correction

### Priorité 1

1. Extraire les paramètres Excel en tables propres.
2. Créer tests Python vs Excel sur `TESTS SIMPLY/LIBERTY/CONNECTED`.
3. Corriger les POI à 0.1-0.5 km.
4. Créer feature store par hôtel.
5. Corriger les targets : moyenne mensuelle historique.

### Priorité 2

1. Construire dataset train jusqu’à 2025.
2. Garder 2026 en test.
3. Entraîner modèle global mensuel.
4. Entraîner modèle par catégorie.
5. Entraîner modèle par gamme/sous-catégorie si mapping validé.
6. Ajouter colonnes de fiabilité historique.

### Priorité 3

1. API `/hotel/enrich` persistante.
2. API `/simulation/rod` fidèle Excel.
3. API `/simulation/ia` XGBoost.
4. API `/simulation/optimize` sous contraintes.
5. Interface de comparaison ROD vs IA.

## 10. Conclusion

Le projet est bien avancé en exploration : les données, les Excel, les notebooks et une première web app existent. Mais la prochaine étape n’est pas d’ajouter encore un modèle ; c’est de stabiliser la vérité fonctionnelle : Excel ROD en Python, consigne en backlog, feature store, targets moyennes mensuelles, puis seulement le XGBoost et le stacking.

Trajectoire recommandée :

```text
Excel ROD fidèle → feature store hôtel → targets moyennes mensuelles → XGBoost V1 → stacking → optimisation sous contraintes → web app propre
```
