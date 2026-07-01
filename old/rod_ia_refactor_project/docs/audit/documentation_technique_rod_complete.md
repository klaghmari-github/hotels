# Documentation technique et fonctionnelle — simulateur ROD, règles Excel, ventes et notebooks

> Rapport généré à partir des fichiers réellement présents dans `/mnt/data`. Les doublons `(1)` ont été détectés par hash et ne sont pas réanalysés deux fois. Quand une information vient uniquement des logs de conversation et non du fichier complet uploadé, c’est signalé.

## 1. Fichiers analysés et doublons

- Doublons exacts `4cf0960a` : `Fichier markdown(1).md collé`, `Fichier markdown.md collé`
- Doublons exacts `8f336d52` : `ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx`, `ROD - Paramètres & règles + projections nb. d'hôtels.xlsx`
- Doublons exacts `10f221a1` : `Analyse du poids des catégories de produit (2024-2025)(1).xlsm`, `Analyse du poids des catégories de produit (2024-2025).xlsm`
- Doublons exacts `a320b28c` : `ROD - Simulateurs + détail des coûts(1).xlsx`, `ROD - Simulateurs + détail des coûts.xlsx`
- Doublons exacts `791dc358` : `2026.02.Fevrier-ExportAccor(1).xlsx`, `2026.02.Fevrier-ExportAccor.xlsx`

Fichiers de travail principaux :

- `001.queryVentes.csv` — 16673.9 Ko
- `2026.02.Fevrier-ExportAccor(1).xlsx` — 304.4 Ko
- `2026.02.Fevrier-ExportAccor.xlsx` — 304.4 Ko
- `Analyse du poids des catégories de produit (2024-2025)(1).xlsm` — 18368.7 Ko
- `Analyse du poids des catégories de produit (2024-2025).xlsm` — 18368.7 Ko
- `Fichier markdown (2).md collé` — 336.6 Ko
- `Fichier markdown(1).md collé` — 346.2 Ko
- `Fichier markdown.md collé` — 346.2 Ko
- `ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx` — 395.4 Ko
- `ROD - Paramètres & règles + projections nb. d'hôtels.xlsx` — 395.4 Ko
- `ROD - Simulateurs + détail des coûts(1).xlsx` — 254.3 Ko
- `ROD - Simulateurs + détail des coûts.xlsx` — 254.3 Ko
- `Récapitulatif de l'ensemble des données ROD enrichies(2).xlsx` — 25.9 Ko
- `Récapitulatif de l'ensemble des données ROD(RECAP DATA ROD).csv` — 20.9 Ko
- `Récapitulatif de l'ensemble des données ROD.xlsx` — 33.6 Ko
- `Simulation-IA-ROD.png` — 594.5 Ko
- `association_gamme.ipynb` — 33.9 Ko
- `inspection_regles_formules_rod.md` — 9.6 Ko

## 2. Inventaire des feuilles Excel

|file|sheet|max_row|max_col|non_empty|formula_count|comment_count|note|
|---|---|---|---|---|---|---|---|
|2026.02.Fevrier-ExportAccor(1).xlsx|Result 1|3492|20|66245|0|0||
|2026.02.Fevrier-ExportAccor(1).xlsx|Query|1|1|1|0|0||
|Analyse du poids des catégories de produit (2024-2025)(1).xlsm|BASE|?|38|?|see xml|?|xlsm huge; formulas parsed from XML|
|Analyse du poids des catégories de produit (2024-2025)(1).xlsm|Détails1|?|?|?|see xml|?|xlsm huge; formulas parsed from XML|
|Analyse du poids des catégories de produit (2024-2025)(1).xlsm|Feuil1|?|721|?|see xml|?|xlsm huge; formulas parsed from XML|
|ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx|REGLES POUR RECO DU CONCEPT|62|21|203|76|0||
|ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx|NB CH 1|40|2|78|0|0||
|ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx|NB CH 2|62|4|171|56|0||
|ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx|RESTO 1|9|6|42|0|0||
|ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx|RESTO 2|8|13|67|26|0||
|ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx|BAR 1|9|6|39|0|0||
|ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx|BAR 2|8|13|63|25|0||
|ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx|CRITERES POUR PANEL|9|5|24|0|0||
|ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx|TESTS SIMPLY|33|28|269|4|0||
|ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx|TESTS LIBERTY|33|35|338|5|0||
|ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx|TESTS CONNECTED|35|35|292|5|0||
|ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx|CORRECTIONS ND|12|2|10|0|0||
|ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx|DATA|39|10|191|0|0||
|ROD - Paramètres & règles + projections nb. d'hôtels(1).xlsx|PROTOTYPE|170|28|233|0|0||
|ROD - Simulateurs + détail des coûts(1).xlsx|SIMULATEUR SIMPLY|187|20|401|135|1||
|ROD - Simulateurs + détail des coûts(1).xlsx|SIMULATEUR LIBERTY|187|20|401|135|1||
|ROD - Simulateurs + détail des coûts(1).xlsx|SIMULATEUR CONNECTED|187|22|406|133|1||
|ROD - Simulateurs + détail des coûts(1).xlsx|COUTS - TECHNOS|36|25|230|69|0||
|ROD - Simulateurs + détail des coûts(1).xlsx|COUTS - ANNEXES|24|18|166|51|0||
|ROD - Simulateurs + détail des coûts(1).xlsx|COUTS - AGENCEMENT|37|30|763|532|0||
|ROD - Simulateurs + détail des coûts(1).xlsx|REVENUS - MIX & MARGES|18|15|67|17|0||
|ROD - Simulateurs + détail des coûts(1).xlsx|REVENUS - IMPACT TO|13|27|95|21|0||
|Récapitulatif de l'ensemble des données ROD enrichies(2).xlsx|RECAP DATA ROD|145|17|1507|0|0||
|Récapitulatif de l'ensemble des données ROD.xlsx|RECAP DATA ROD|137|17|1605|14|0||
|Récapitulatif de l'ensemble des données ROD.xlsx|Feuille2|8|131|729|14|0||
|Récapitulatif de l'ensemble des données ROD.xlsx|Feuille3|9|131|759|14|0||

Inventaire complet des formules exporté ici : `inventaire_formules_excel.csv`. Inventaire des commentaires Excel exporté ici : `inventaire_commentaires_excel.csv`.


## 3. Vision fonctionnelle globale du simulateur ROD

Le simulateur ROD sert à comparer des solutions de corner retail pour un hôtel Accor. L’utilisateur renseigne ou valide des informations hôtel, choisit des paramètres de corner, puis obtient des revenus, coûts, marge nette et amortissement. Les fichiers Excel représentent une première logique de simulation déterministe. L’IA doit ensuite produire une estimation plus riche en exploitant les features hôtel, météo, POI, marque, contraintes et configuration produits.

Les trois concepts sont :
- **SIMPLY STORE** : coin de vente avec encaissement par opérateur/réception, scanner possible, pas de self-service complet.
- **LIBERTY STORE** : self-service sans frigo, avec caisse/borne et vitrine sèche.
- **CONNECTED STORE** : self-service avec frigo/connecté, plus coûteux.


## 4. Fichier `ROD - Simulateurs + détail des coûts.xlsx`

Ce classeur est la pièce centrale pour transformer les règles de revenus/coûts en Python. Il contient 8 feuilles : simulateurs par concept, coûts technos, coûts annexes, coûts d’agencement, mix/marges et impact du TO.

### 4.1. Feuille `SIMULATEUR SIMPLY`

**Rôle fonctionnel.** Cette feuille calcule pour un concept donné : paramètres hôtel, espace retail, mix F&B/N-F&B, revenus mensuels, marge produits, coûts mensuels, marge nette et amortissement. Elle est construite sur des résultats pilotes moyens, puis applique plusieurs règles de projection.

**Paramètres lus dans la feuille :**

|cellule|valeur/formule|
|---|---|
|C9|129|
|C10|1.7|
|C11|0.8|
|F9|6|
|I9|0.4|
|I10|0.6|
|J9|2.6|
|J10|1.45|
|C19|231|
|E34|533|
|E35|187|
|H34|587|
|H35|224|
|C147|1|
|C148|0|
|C149|1|
|C156|1|
|C166|=F9|

**Décomposition fonctionnelle des blocs :**

- **Paramètres hôtel** : nombre de chambres `C9`, guests/chambre `C10`, TO `C11`.

- **Espace retail** : mètres linéaires `F9`.

- **Mix et marge produits** : F&B `I9`, N-F&B `I10`, marges `J9/J10`, marge pondérée `J11 = SUMPRODUCT(marges, mix) / SUM(mix)`.

- **Clients hébergés** : chambres occupées `C15 = C9*C11`, clients/jour `C16 = C10*C9*C11`, clients/mois `C17 = C16*30.5`.

- **Règle 1** : revenus calculés à partir du nombre de clients acheteurs mensuels. Le taux d’acheteurs mensuels est `C21 = C19/C17`, puis le simulateur applique ce ratio au nombre de clients hébergés.

- **Règle 2** : chaque 10% de mix produit en plus ou en moins impacte le CA F&B et N-F&B. Les cellules `E51/H51` et `E52/H52` calculent l’impact de 10% de mix à partir des CA pilotes.

- **Règle 3** : influence des catégories cochées/non cochées. La feuille liste les catégories F&B et non-F&B avec des poids/impacts : boissons sans alcool, alcool, sucré sec/frais, salé sec/frais, épicerie fine; puis SOS, hygiène, cosmétiques, enfants, prêt-à-porter, accessoires, souvenirs.

- **Règle 4** : impact d’un mètre linéaire en plus ou en moins. Les cellules `E112/H112` et `E113/H113` divisent le CA pilote par le nombre de mètres linéaires de référence.

- **Marge produits mensuelle** : `E132 = E120 - (E120/E128)` et `E133 = E121 - (E121/E129)`. La marge utilise les coefficients de marge produits.

- **Coûts mensuels** : coûts technos, annexes et agencement, importés des feuilles de coûts.

- **Marge nette mensuelle** : `E176 = E134 - H168`.

- **Amortissement** : `E184 = E168/E176`, puis conversion en années avec `E185 = E184/12`.


**Extraits de lignes clés :**

- B7: PARAMETRES HOTEL ; E7: RETAIL SPACE ; H7: MIX + MARGE PDTS
- J8: Marge
- B9: Nb. de ch. ; C9: 129 ; E9: M. lin. ; F9: 6 ; H9: F&B ; I9: 0.4 ; J9: 2.6
- B10: Nb. gu / ch ; C10: 1.7 ; H10: N-F&B ; I10: 0.6 ; J10: 1.45
- B11: TO (YTD) ; C11: 0.8 ; H11: Marge pondérée ; J11: =SUMPRODUCT(J9:J10,I9:I10)/SUM(I9:I10)
- B13: MOYENNE
- B15: Ch. occ. ; C15: =C9*C11 ; D15: chambres occupées
- B16: Cl. héb. ; C16: =(C10*C9)*C11 ; D16: clients hébergés / jour
- B17: Cl. héb. ; C17: =C16*30.5 ; D17: clients hébergés / mois
- B19: Nb. ventes ; C19: 231 ; D19: ventes mensuelles (résultat pilotes)
- C21: =C19/C17 ; D21: de clients acheteurs / mois

**Formules fréquentes dans cette feuille :**


### 4.2. Feuille `SIMULATEUR LIBERTY`

**Rôle fonctionnel.** Cette feuille calcule pour un concept donné : paramètres hôtel, espace retail, mix F&B/N-F&B, revenus mensuels, marge produits, coûts mensuels, marge nette et amortissement. Elle est construite sur des résultats pilotes moyens, puis applique plusieurs règles de projection.

**Paramètres lus dans la feuille :**

|cellule|valeur/formule|
|---|---|
|C9|142|
|C10|2.2|
|C11|0.7|
|F9|8|
|I9|0.7|
|I10|0.3|
|J9|2.6|
|J10|2|
|C19|312|
|E34|1055|
|E35|424|
|H34|1174|
|H35|508|
|C147|1|
|C148|1|
|C149|1|
|C156|1|
|C166|=F9|

**Décomposition fonctionnelle des blocs :**

- **Paramètres hôtel** : nombre de chambres `C9`, guests/chambre `C10`, TO `C11`.

- **Espace retail** : mètres linéaires `F9`.

- **Mix et marge produits** : F&B `I9`, N-F&B `I10`, marges `J9/J10`, marge pondérée `J11 = SUMPRODUCT(marges, mix) / SUM(mix)`.

- **Clients hébergés** : chambres occupées `C15 = C9*C11`, clients/jour `C16 = C10*C9*C11`, clients/mois `C17 = C16*30.5`.

- **Règle 1** : revenus calculés à partir du nombre de clients acheteurs mensuels. Le taux d’acheteurs mensuels est `C21 = C19/C17`, puis le simulateur applique ce ratio au nombre de clients hébergés.

- **Règle 2** : chaque 10% de mix produit en plus ou en moins impacte le CA F&B et N-F&B. Les cellules `E51/H51` et `E52/H52` calculent l’impact de 10% de mix à partir des CA pilotes.

- **Règle 3** : influence des catégories cochées/non cochées. La feuille liste les catégories F&B et non-F&B avec des poids/impacts : boissons sans alcool, alcool, sucré sec/frais, salé sec/frais, épicerie fine; puis SOS, hygiène, cosmétiques, enfants, prêt-à-porter, accessoires, souvenirs.

- **Règle 4** : impact d’un mètre linéaire en plus ou en moins. Les cellules `E112/H112` et `E113/H113` divisent le CA pilote par le nombre de mètres linéaires de référence.

- **Marge produits mensuelle** : `E132 = E120 - (E120/E128)` et `E133 = E121 - (E121/E129)`. La marge utilise les coefficients de marge produits.

- **Coûts mensuels** : coûts technos, annexes et agencement, importés des feuilles de coûts.

- **Marge nette mensuelle** : `E176 = E134 - H168`.

- **Amortissement** : `E184 = E168/E176`, puis conversion en années avec `E185 = E184/12`.


**Extraits de lignes clés :**

- B7: PARAMETRES HOTEL ; E7: RETAIL SPACE ; H7: MIX + MARGE PDTS
- J8: Marge
- B9: Nb. de ch. ; C9: 142 ; E9: M. lin. ; F9: 8 ; H9: F&B ; I9: 0.7 ; J9: 2.6
- B10: Nb. gu / ch ; C10: 2.2 ; H10: N-F&B ; I10: 0.3 ; J10: 2
- B11: TO (YTD) ; C11: 0.7 ; H11: Marge pondérée ; J11: =SUMPRODUCT(J9:J10,I9:I10)/SUM(I9:I10)
- B13: MOYENNE
- B15: Ch. occ. ; C15: =C9*C11 ; D15: chambres occupées
- B16: Cl. héb. ; C16: =(C10*C9)*C11 ; D16: clients hébergés / jour
- B17: Cl. héb. ; C17: =C16*30.5 ; D17: clients hébergés / mois
- B19: Nb. ventes ; C19: 312 ; D19: ventes mensuelles (résultat pilotes)
- C21: =C19/C17 ; D21: de clients acheteurs / mois

**Formules fréquentes dans cette feuille :**


### 4.3. Feuille `SIMULATEUR CONNECTED`

**Rôle fonctionnel.** Cette feuille calcule pour un concept donné : paramètres hôtel, espace retail, mix F&B/N-F&B, revenus mensuels, marge produits, coûts mensuels, marge nette et amortissement. Elle est construite sur des résultats pilotes moyens, puis applique plusieurs règles de projection.

**Paramètres lus dans la feuille :**

|cellule|valeur/formule|
|---|---|
|C9|305|
|C10|1.8|
|C11|0.75|
|F9|7|
|I9|0.8|
|I10|0.2|
|J9|2.6|
|J10|1.8|
|C19|534|
|E34|3503|
|E35|131|
|H34|3696|
|H35|138|
|C147|3|
|C148|1|
|C149|inclus|
|C156||
|C166|=F9|

**Décomposition fonctionnelle des blocs :**

- **Paramètres hôtel** : nombre de chambres `C9`, guests/chambre `C10`, TO `C11`.

- **Espace retail** : mètres linéaires `F9`.

- **Mix et marge produits** : F&B `I9`, N-F&B `I10`, marges `J9/J10`, marge pondérée `J11 = SUMPRODUCT(marges, mix) / SUM(mix)`.

- **Clients hébergés** : chambres occupées `C15 = C9*C11`, clients/jour `C16 = C10*C9*C11`, clients/mois `C17 = C16*30.5`.

- **Règle 1** : revenus calculés à partir du nombre de clients acheteurs mensuels. Le taux d’acheteurs mensuels est `C21 = C19/C17`, puis le simulateur applique ce ratio au nombre de clients hébergés.

- **Règle 2** : chaque 10% de mix produit en plus ou en moins impacte le CA F&B et N-F&B. Les cellules `E51/H51` et `E52/H52` calculent l’impact de 10% de mix à partir des CA pilotes.

- **Règle 3** : influence des catégories cochées/non cochées. La feuille liste les catégories F&B et non-F&B avec des poids/impacts : boissons sans alcool, alcool, sucré sec/frais, salé sec/frais, épicerie fine; puis SOS, hygiène, cosmétiques, enfants, prêt-à-porter, accessoires, souvenirs.

- **Règle 4** : impact d’un mètre linéaire en plus ou en moins. Les cellules `E112/H112` et `E113/H113` divisent le CA pilote par le nombre de mètres linéaires de référence.

- **Marge produits mensuelle** : `E132 = E120 - (E120/E128)` et `E133 = E121 - (E121/E129)`. La marge utilise les coefficients de marge produits.

- **Coûts mensuels** : coûts technos, annexes et agencement, importés des feuilles de coûts.

- **Marge nette mensuelle** : `E176 = E134 - H168`.

- **Amortissement** : `E184 = E168/E176`, puis conversion en années avec `E185 = E184/12`.


**Extraits de lignes clés :**

- B7: PARAMETRES HOTEL ; E7: RETAIL SPACE ; H7: MIX + MARGE PDTS
- J8: Marge
- B9: Nb. de ch. ; C9: 305 ; E9: M. lin. ; F9: 7 ; H9: F&B ; I9: 0.8 ; J9: 2.6
- B10: Nb. gu / ch ; C10: 1.8 ; E10: Nb. FC ; F10: 3 ; H10: N-F&B ; I10: 0.2 ; J10: 1.8
- B11: TO (YTD) ; C11: 0.75 ; H11: Marge pondérée ; J11: =SUMPRODUCT(J9:J10,I9:I10)/SUM(I9:I10)
- B13: MOYENNE
- B15: Ch. occ. ; C15: =C9*C11 ; D15: chambres occupées
- B16: Cl. héb. ; C16: =(C10*C9)*C11 ; D16: clients hébergés / jour
- B17: Cl. héb. ; C17: =C16*30.5 ; D17: clients hébergés / mois
- B19: Nb. ventes ; C19: 534 ; D19: ventes mensuelles (résultat pilotes)
- C21: =C19/C17 ; D21: de clients acheteurs / mois

**Formules fréquentes dans cette feuille :**


### 4.4. Feuille `COUTS - TECHNOS`

Cette feuille paramètre les coûts technologiques : scanner pour Simply, caisse pour Liberty, frigo pour Connected, vitrine, licence logicielle, frais ad hoc. Les formules transforment des coûts totaux en coûts mensuels par durée d’amortissement ou de contrat. Exemples : `F8 = E8/$C$7` pour mensualiser un coût scanner Simply, `M8 = L8-(L8*$O$7)` pour appliquer une réduction/remise côté Liberty, et formules analogues côté Connected.

- B2: COÛTS  ► TECHNOS
- B4: SIMPLY STORE > BUY ONLY ; I4: LIBERTY STORE > BUY OU LEASE
- C6: SCANNER ; J6: CAISSE
- C7: 60 ; D7: mois ; E7: BUY ; F7: MENSUEL ; G7: Calcul du coût mensuel uniquement pour la mensualisation du résultat. ; J7: 60
- C8: 1 ; D8: scan ; E8: 500 ; F8: =E8/$C$7 ; J8: 1
- C9: 2 ; D9: scan ; E9: =$E$8*C9 ; F9: =E9/$C$7 ; J9: 2
- C10: 3 ; D10: scan ; E10: =$E$8*C10 ; F10: =E10/$C$7 ; J10: 3
- C11: 4 ; D11: scan ; E11: =$E$8*C11 ; F11: =E11/$C$7 ; J11: 4
- C13: VITRINE ; J13: VITRINE
- C14: 60 ; D14: mois ; E14: BUY ; F14: MENSUEL ; G14: Calcul du coût mensuel uniquement pour la mensualisation du résultat. ; J14: 60
- C15: 1 ; D15: vitr. ; E15: 800 ; F15: =E15/$C$14 ; J15: 1
- C16: 2 ; D16: vitr. ; E16: =$E$15*C16 ; F16: =E16/$C$14 ; J16: 2
- C17: 3 ; D17: vitr. ; E17: =$E$15*C17 ; F17: =E17/$C$14 ; J17: 3
- C18: 4 ; D18: vitr. ; E18: =$E$15*C18 ; F18: =E18/$C$14 ; J18: 4
- C20: LICENCE LOGICIELLE ; J20: LICENCE LOGICIELLE
- C21: 60 ; D21: mois ; E21: TOTAL ; F21: MENSUEL ; G21: Licence réglée de façon / mensuelle uniquement. ; J21: 60
- C22: 1 ; D22: licen. ; E22: =F22*$C$21 ; F22: 50 ; J22: 1
- C24: FRAIS AD HOC ; J24: FRAIS AD HOC
- C25: 60 ; D25: mois ; E25: TOTAL ; F25: MENSUEL ; G25: Frais ad hoc réglés de façon / one-shot uniquement. ; J25: 60
- C26: 1 ; D26: frais ; E26: 1000 ; F26: =E26/$C$25 ; J26: 1
- C28: TOTAL ; E28: =SUM(E8,E15,E22,E26) ; F28: =SUM(F8,F15,F22,F26) ; J28: TOTAL

### 4.5. Feuille `COUTS - ANNEXES`

Cette feuille ajoute les coûts annexes mensuels : électricité liée au scanner/caisse/vitrine/frigo et personnel/staff. Les coûts sont multipliés par le nombre d’équipements. Exemple : `E8 = F8*$C$7`, puis déclinaisons par nombre de scanners ou vitrines.

- B2: COÛTS  ► ANNEXES
- B4: SIMPLY STORE ; H4: LIBERTY STORE
- E6: ELECTRICITE ; K6: ELECTRICITE
- C7: 60 ; D7: mois ; E7: TOTAL ; F7: PAR MOIS ; I7: 60 ; J7: mois ; K7: TOTAL ; L7: PAR MOIS
- C8: 1 ; D8: scan ; E8: =F8*$C$7 ; F8: 2 ; I8: 1 ; J8: cai. ; K8: =L8*$I$7 ; L8: 10
- C9: 2 ; D9: scan ; E9: =F9*$C$7 ; F9: =$F$8*C9 ; I9: 2 ; J9: cai. ; K9: =L9*$I$7 ; L9: =$L$8*I9
- C10: 3 ; D10: scan ; E10: =F10*$C$7 ; F10: =$F$8*C10 ; I10: 3 ; J10: cai. ; K10: =L10*$I$7 ; L10: =$L$8*I10
- C11: 4 ; D11: scan ; E11: =F11*$C$7 ; F11: =$F$8*C11 ; I11: 4 ; J11: cai. ; K11: =L11*$I$7 ; L11: =$L$8*I11
- E13: ELECTRICITE ; K13: ELECTRICITE
- C14: 60 ; D14: mois ; E14: TOTAL ; F14: PAR MOIS ; I14: 60 ; J14: mois ; K14: TOTAL ; L14: PAR MOIS
- C15: 1 ; D15: vitr. ; E15: =F15*$C$14 ; F15: 10 ; I15: 1 ; J15: vitr. ; K15: =L15*$I$14 ; L15: 10
- C16: 2 ; D16: vitr. ; E16: =$E$15*C16 ; F16: =$F$15*C16 ; I16: 2 ; J16: vitr. ; K16: =L16*$I$14 ; L16: =$L$15*I16
- C17: 3 ; D17: vitr. ; E17: =$E$15*C17 ; F17: =$F$15*C17 ; I17: 3 ; J17: vitr. ; K17: =L17*$I$14 ; L17: =$L$15*I17
- C18: 4 ; D18: vitr. ; E18: =$E$15*C18 ; F18: =$F$15*C18 ; I18: 4 ; J18: vitr. ; K18: =L18*$I$14 ; L18: =$L$15*I18
- E20: PERSONNEL ; K20: PERSONNEL
- C21: 60 ; D21: mois ; E21: TOTAL ; F21: PAR MOIS ; I21: 60 ; J21: mois ; K21: TOTAL ; L21: PAR MOIS
- C22: 1 ; D22: staff ; E22: =F22*$C$21 ; F22: 3 ; I22: 1 ; J22: staff ; K22: =L22*$I$21 ; L22: 10
- C24: TOTAL ; E24: =SUM(E8,E15,E22) ; F24: =SUM(F8,F15,F22) ; I24: TOTAL ; K24: =SUM(K8,K15,K22) ; L24: =SUM(L8,L15,L22)

### 4.6. Feuille `COUTS - AGENCEMENT`

Cette feuille calcule l’agencement selon les mètres linéaires et le niveau de finition : Classic, Premium, Bespoke. La logique est principalement linéaire : coût total = coût unitaire par mètre × nombre de mètres, puis mensualisation sur une durée d’amortissement. Les concepts ont des durées et coûts unitaires distincts.

- B2: COÛTS  ► AGENCEMENT
- B4: SIMPLY STORE ; L4: LIBERTY STORE
- E6: CLASSIC ; G6: PREMIUM ; I6: BESPOKE ; O6: CLASSIC
- C7: 84 ; D7: mois ; E7: TOTAL ; F7: PAR MOIS ; G7: TOTAL ; H7: PAR MOIS ; I7: TOTAL ; J7: PAR MOIS ; M7: 84 ; N7: mois ; O7: TOTAL
- C8: 1 ; D8: m ; E8: 1000 ; F8: =E8/$C$7 ; G8: 1200 ; H8: =G8/$C$7 ; I8: 2200 ; J8: =I8/$C$7 ; M8: 1 ; N8: m ; O8: 1000
- C9: 2 ; D9: m ; E9: =$E$8*C9 ; F9: =E9/$C$7 ; G9: =$G$8*C9 ; H9: =G9/$C$7 ; I9: =$I$8*C9 ; J9: =I9/$C$7 ; M9: 2 ; N9: m ; O9: =$O$8*M9
- C10: 3 ; D10: m ; E10: =$E$8*C10 ; F10: =E10/$C$7 ; G10: =$G$8*C10 ; H10: =G10/$C$7 ; I10: =$I$8*C10 ; J10: =I10/$C$7 ; M10: 3 ; N10: m ; O10: =$O$8*M10
- C11: 4 ; D11: m ; E11: =$E$8*C11 ; F11: =E11/$C$7 ; G11: =$G$8*C11 ; H11: =G11/$C$7 ; I11: =$I$8*C11 ; J11: =I11/$C$7 ; M11: 4 ; N11: m ; O11: =$O$8*M11
- C12: 5 ; D12: m ; E12: =$E$8*C12 ; F12: =E12/$C$7 ; G12: =$G$8*C12 ; H12: =G12/$C$7 ; I12: =$I$8*C12 ; J12: =I12/$C$7 ; M12: 5 ; N12: m ; O12: =$O$8*M12
- B13: IBB NICE ; C13: 6 ; D13: m ; E13: =$E$8*C13 ; F13: =E13/$C$7 ; G13: =$G$8*C13 ; H13: =G13/$C$7 ; I13: =$I$8*C13 ; J13: =I13/$C$7 ; M13: 6 ; N13: m ; O13: =$O$8*M13
- B14: =I13/C13 ; C14: 7 ; D14: m ; E14: =$E$8*C14 ; F14: =E14/$C$7 ; G14: =$G$8*C14 ; H14: =G14/$C$7 ; I14: =$I$8*C14 ; J14: =I14/$C$7 ; L14: MER BOUL ; M14: 7 ; N14: m ; O14: =$O$8*M14
- C15: 8 ; D15: m ; E15: =$E$8*C15 ; F15: =E15/$C$7 ; G15: =$G$8*C15 ; H15: =G15/$C$7 ; I15: =$I$8*C15 ; J15: =I15/$C$7 ; M15: 8 ; N15: m ; O15: =$O$8*M15

### 4.7. Feuille `REVENUS - MIX & MARGES`

Cette feuille définit des mixes F&B/N-F&B et des marges par concept ou cas pilote. Elle calcule une marge pondérée avec `SUMPRODUCT(marges, mix)/SUM(mix)`. Elle sert à alimenter le simulateur quand l’utilisateur choisit une proportion F&B/N-F&B.

- B2: REVENUS  ► MIX PRODUITS
- B4: SIMPLY STORE ; G4: LIBERTY STORE ; L4: CONNECTED STORE
- C6: F&B ; D6: N-F&B ; E6: TOTAL ; H6: F&B ; I6: N-F&B ; J6: TOTAL ; M6: F&B ; N6: N-F&B ; O6: TOTAL
- B7: MIX ; C7: 0.7 ; D7: 0.3 ; E7: =SUM(C7:D7) ; G7: MIX ; H7: 1 ; I7: 0 ; J7: =SUM(H7:I7) ; L7: MIX ; M7: 0.9 ; N7: 0.1 ; O7: =SUM(M7:N7)
- B8: MARGE ; C8: 2.6 ; D8: 1.45 ; E8: 2.025 ; G8: MARGE ; H8: 2.6 ; I8:  -  ; J8: 2.6 ; L8: MARGE ; M8: 2.6 ; N8: 1.8 ; O8: 2.2
- B9: IBB NICE ; E9: =SUMPRODUCT(C8:D8,C7:D7)/SUM(C7:D7) ; G9: MER BOUL ; J9: =SUMPRODUCT(H8:I8,H7:I7)/SUM(H7:I7) ; L9: MER MONT ; O9: =SUMPRODUCT(M8:N8,M7:N7)/SUM(M7:N7)
- G11: MIX ; H11: 0.3 ; I11: 0.7 ; J11: =SUM(H11:I11)
- G12: MARGE ; H12: 2.6 ; I12: 2 ; J12: 2.3
- G13: NOV MEG ; J13: =SUMPRODUCT(H12:I12,H11:I11)/SUM(H11:I11)
- G15: MIX ; H15: =AVERAGE(H7,H11) ; I15: =AVERAGE(I7,I11) ; J15: =SUM(H15:I15)
- G16: MARGE ; H16: =AVERAGE(H8,H12) ; I16: =AVERAGE(I8,I12) ; J16: =AVERAGE(H16:I16)
- B18: MOYENNE ; E18: =SUMPRODUCT(C8:D8,C7:D7)/SUM(C7:D7) ; G18: MOYENNE ; J18: =SUMPRODUCT(H16:I16,H15:I15)/SUM(H15:I15) ; L18: MOYENNE ; O18: =SUMPRODUCT(M8:N8,M7:N7)/SUM(M7:N7)

### 4.8. Feuille `REVENUS - IMPACT TO`

Cette feuille donne une règle d’impact du taux d’occupation. Le principe visible est : pour un impact TO de 1 point (`C12 = 0.01`), le CA F&B/N-F&B est recalculé proportionnellement au TO moyen pilote. Exemple `D12 = ($C$12*D8)/$C$8`. Cette logique correspond à une règle de trois sur le TO.

- B2: REVENUS  ► TAUX D'OCCUPATION
- B4: SIMPLY STORE ; K4: LIBERTY STORE
- D6: CA HT ; G6: CA TTC ; M6: CA HT
- C7: TO MOYEN ; D7: F&B ; E7: N-F&B ; F7: TOTAL ; G7: F&B ; H7: N-F&B ; I7: TOTAL ; L7: TO MOYEN ; M7: F&B
- B8: IBB NICE ; C8: 0.78 ; D8: 533.25 ; E8: 187 ; F8: =SUM(D8:E8) ; G8: 587.083 ; H8: 224.417 ; I8: =SUM(G8:H8) ; K8: MER BOUL ; L8: 0.68 ; M8: 1718.67
- K9: NOV MEG ; L9: 0.67 ; M9: 391.709
- K10: MOYENNE ; L10: =AVERAGE(L8:L9) ; M10: 1055.19
- B12: IMPACT ; C12: 0.01 ; D12: =($C$12*D8)/$C$8 ; E12: =($C$12*E8)/$C$8 ; F12: =($C$12*F8)/$C$8 ; G12: =($C$12*G8)/$C$8 ; H12: =($C$12*H8)/$C$8 ; I12: =($C$12*I8)/$C$8 ; K12: IMPACT ; L12: 0.01 ; M12: =($L$12*M10)/$L$10

## 5. Fichier `ROD - Paramètres & règles + projections nb. d'hôtels.xlsx`

Ce classeur documente les règles de recommandation conceptuelle et les distributions globales du parc hôtelier par marque, nombre de chambres, restaurants et bars. Il sert à projeter les concepts sur le parc Accor, pas seulement à simuler un hôtel isolé.


### 5.1. Feuille `REGLES POUR RECO DU CONCEPT`

Cette feuille pose les règles de recommandation conceptuelle. Les règles visibles sont :

- **Règle #1** : nombre de chambres. Simply est associé aux hôtels entre 0 et 49 chambres; Liberty aux hôtels de plus de 50 chambres.

- **Règle #2** : si au moins une des 5 catégories non-F&B suivantes est sélectionnée/cochée — Cosmetics, Kids items, Ready-to-wear, Accessories, Souvenirs — le choix Liberty doit être possible, en particulier pour NOVOTEL et MERCURE.

- **Règle #3** : si l’hôtel souhaite plus de 4 mètres linéaires, alors orientation vers Liberty Store.

- **Règle #4** : possession d’une vitrine réfrigérée.

- **Règle #5** : dernier tri en fonction du TO moyen YTD, notamment TO < 70%.

- La feuille calcule un nombre total d’hôtels et un quality check `SUM(E60,K60,Q60)`.

- E2: SIMPLY ; K2: LIBERTY
- B4: REGLE #1 ; D4: Nb. de chambres ; E4: Entre 0 et 49 chambres ; K4:  + de 50 chambres
- F6: Nb. hôtels ; L6: Nb. hôtels
- E7: IBB ; F7: ='NB CH 2'!C3 ; K7: IBB ; L7: ='NB CH 2'!C2-'NB CH 2'!C3
- E8: IBS ; F8: ='NB CH 2'!C11 ; K8: IBS ; L8: ='NB CH 2'!C10-'NB CH 2'!C11
- E9: IBIS ; F9: ='NB CH 2'!C19 ; K9: IBIS ; L9: ='NB CH 2'!C18-'NB CH 2'!C19
- E10: NOV ; F10: 0 ; K10: NOV ; L10: ='NB CH 2'!C26-'NB CH 2'!C27
- E11: MER ; F11: ='NB CH 2'!C35 ; K11: MER ; L11: ='NB CH 2'!C34-'NB CH 2'!C35
- E12: TOTAL ; F12: =SUM(F7:F11) ; G12: =F12/H12 ; H12: 1343 ; K12: TOTAL ; L12: =SUM(L7:L11) ; M12: =L12/N12 ; N12: 1343
- B15: REGLE #2 ; D15: Min. 1 des 5 catégories :
- D16: Cosmetics et/ou Kids items et/ou Ready-to-wear et/ou Accessories et/ou Souvenirs ; K16: YES
- L18: Nb. hôtels
- K19: IBB ; L19: 0
- G20: Le choix doit être possible / pour les hôtels NOV et MER / ↔ ; K20: IBS ; L20: 0
- K21: IBIS ; L21: 0
- E22: NOV ; F22: =L22 ; K22: NOV ; L22: =L10
- E23: MER ; F23: =L23 ; K23: MER ; L23: =L11
- E24: TOTAL ; F24: =SUM(F19:F23) ; G24: =F24/H24 ; H24: 1343 ; K24: TOTAL ; L24: =SUM(L19:L23) ; M24: =L24/N24 ; N24: 1343
- B27: REGLE #3 ; D27: Nb. de mètres linéaires :
- D28: Si l'hôtel souhaite + de 4 mètres linéaires alors > LIBERTY STORE ; K28: > 4 METRES LINEAIRES
- L30: Nb. hôtels
- K31: IBB ; L31: =$R$19*M31 ; M31: 0.1
- K32: IBS ; L32: =$R$20*M32 ; M32: 0.3
- K33: IBIS ; L33: =$R$21*M33 ; M33: 0.2
- K34: TOTAL ; L34: =SUM(L31:L33) ; M34: =L34/N34 ; N34: 1343
- B36: Pour les hôtels répondant aux critères ci-après : ; G36:  - Plus de 50 chambres /  - Aucune des 5 catégories de produits sélectionnées/cochées /  - Entre 2 et 4 mètres linéaires accordés à leur future boutique (2 mètres étant le minimum dans ROD)
- B42: REGLE #4 ; D42: L'hôtel est-il déjà en possession d'une vitrine réfrigérée ? ; K42: YES
- L44: Nb. hôtels
- K45: IBB ; L45: =$R$31*M45 ; M45: 0.4
- K46: IBS ; L46: =$R$32*M46 ; M46: 0.5
- K47: IBIS ; L47: =$R$33*M47 ; M47: 0.6
- K48: TOTAL ; L48: =SUM(L45:L47) ; M48: =L48/N48 ; N48: 1343
- B52: REGLE #5 ; D52: Dernier tri en fonction du TO moyen (YTD) ; K52: TO < à 70%
- L54: Nb. hôtels
- K55: IBB ; L55: =$R$45*M55 ; M55: 0.4
- K56: IBS ; L56: =$R$46*M56 ; M56: 0.3
- K57: IBIS ; L57: =$R$47*M57 ; M57: 0.2
- K58: TOTAL ; L58: =SUM(L55:L57) ; M58: =L58/N58 ; N58: 1343
- B60: NB. HOTELS TOTAUX ; E60: =F12 ; K60: =SUM(L24,L34,L48,L58)
- B62: QUALITY CHECK ; E62: =SUM(E60,K60,Q60)

### 5.x. Feuille `NB CH 2`

Distribution du parc par marque et tranche de nombre de chambres. Les marques visibles sont IBIS BUDGET, IBIS STYLES, IBIS, NOVOTEL, MERCURE. Total visible : 1343 hôtels. Les formules calculent des proportions par marque et par tranche.

- B2: IBIS BUDGET ; C2: 342 ; D2: =C2/$C$2
- B3: Entre 0 et 49 ch. ; C3: 45 ; D3: =C3/$C$2
- B4: Entre 50 et 99 ch. ; C4: 252 ; D4: =C4/$C$2
- B5: Entre 100 et 149 ch. ; C5: 31 ; D5: =C5/$C$2
- B6: Entre 150 et 199 ch. ; C6: 7 ; D6: =C6/$C$2
- B7: Entre 200 et 249 ch. ; C7: 3 ; D7: =C7/$C$2
- B8: Entre 250 et 299 ch. ; C8: 3 ; D8: =C8/$C$2
- B9: Plus de 300 ch. ; C9: 1 ; D9: =C9/$C$2
- B10: IBIS STYLES ; C10: 267 ; D10: =C10/$C$10
- B11: Entre 0 et 49 ch. ; C11: 60 ; D11: =C11/$C$10
- B12: Entre 50 et 99 ch. ; C12: 174 ; D12: =C12/$C$10
- B13: Entre 100 et 149 ch. ; C13: 26 ; D13: =C13/$C$10
- B14: Entre 150 et 199 ch. ; C14: 3 ; D14: =C14/$C$10
- B15: Entre 200 et 249 ch. ; C15: 1 ; D15: =C15/$C$10
- B16: Entre 250 et 299 ch. ; C16: 0 ; D16: =C16/$C$10
- B17: Plus de 300 ch. ; C17: 3 ; D17: =C17/$C$10
- B18: IBIS ; C18: 362 ; D18: =C18/$C$18
- B19: Entre 0 et 49 ch. ; C19: 45 ; D19: =C19/$C$18
- B20: Entre 50 et 99 ch. ; C20: 247 ; D20: =C20/$C$18
- B21: Entre 100 et 149 ch. ; C21: 45 ; D21: =C21/$C$18
- B22: Entre 150 et 199 ch. ; C22: 11 ; D22: =C22/$C$18
- B23: Entre 200 et 249 ch. ; C23: 3 ; D23: =C23/$C$18
- B24: Entre 250 et 299 ch. ; C24: 4 ; D24: =C24/$C$18
- B25: Plus de 300 ch. ; C25: 7 ; D25: =C25/$C$18
- B26: NOVOTEL ; C26: 117 ; D26: =C26/$C$26
- B27: Entre 0 et 49 ch. ; C27: 0 ; D27: =C27/$C$26
- B28: Entre 50 et 99 ch. ; C28: 37 ; D28: =C28/$C$26
- B29: Entre 100 et 149 ch. ; C29: 57 ; D29: =C29/$C$26
- B30: Entre 150 et 199 ch. ; C30: 15 ; D30: =C30/$C$26
- B31: Entre 200 et 249 ch. ; C31: 2 ; D31: =C31/$C$26
- B32: Entre 250 et 299 ch. ; C32: 4 ; D32: =C32/$C$26
- B33: Plus de 300 ch. ; C33: 2 ; D33: =C33/$C$26
- B34: MERCURE ; C34: 255 ; D34: =C34/$C$34
- B35: Entre 0 et 49 ch. ; C35: 28 ; D35: =C35/$C$34
- B36: Entre 50 et 99 ch. ; C36: 155 ; D36: =C36/$C$34
- B37: Entre 100 et 149 ch. ; C37: 45 ; D37: =C37/$C$34
- B38: Entre 150 et 199 ch. ; C38: 15 ; D38: =C38/$C$34
- B39: Entre 200 et 249 ch. ; C39: 5 ; D39: =C39/$C$34
- B40: Entre 250 et 299 ch. ; C40: 0 ; D40: =C40/$C$34

### 5.x. Feuille `RESTO 2`

Distribution du nombre de restaurants par marque. Les formules calculent des ratios par marque et vérifient que les proportions somment à 1.

- B2: NB. DE RESTAURANT(S) ; C2: 0 ; E2: 1 ; G2: 2 ; I2: 3 ; L2: NB. HOTELS
- B3: IBIS BUDGET ; C3: 314 ; D3: =C3/$L$3 ; E3: 28 ; F3: =E3/$L$3 ; L3: 342
- B4: IBIS STYLES ; C4: 181 ; D4: =C4/$L$4 ; E4: 81 ; F4: =E4/$L$4 ; G4: 4 ; H4: =G4/$L$4 ; I4: 1 ; L4: 267
- B5: IBIS ; C5: 181 ; D5: =C5/$L$5 ; E5: 176 ; F5: =E5/$L$5 ; G5: 4 ; H5: =G5/$L$5 ; I5: 1 ; L5: 362
- B6: NOVOTEL ; C6: 5 ; D6: =C6/$L$6 ; E6: 102 ; F6: =E6/$L$6 ; G6: 7 ; H6: =G6/$L$6 ; I6: 3 ; J6: =I6/$L$6 ; L6: 117
- B7: MERCURE ; C7: 106 ; D7: =C7/$L$7 ; E7: 140 ; F7: =E7/$L$7 ; G7: 8 ; H7: =G7/$L$7 ; I7: 1 ; J7: =I7/$L$7 ; L7: 255
- B8: TOTAL ; C8: 787 ; D8: =C8/$L$8 ; E8: 527 ; F8: =E8/$L$8 ; G8: 23 ; H8: =G8/$L$8 ; I8: 6 ; J8: =I8/$L$8 ; L8: 1343

### 5.x. Feuille `BAR 2`

Distribution du nombre de bars par marque. Même logique que RESTO 2.

- B2: NB. DE BAR(S) ; C2: 0 ; E2: 1 ; G2: 2 ; I2: 3 ; L2: NB. HOTELS
- B3: IBIS BUDGET ; C3: 319 ; D3: =C3/$L$3 ; E3: 23 ; F3: =E3/$L$3 ; L3: 342
- B4: IBIS STYLES ; C4: 48 ; D4: =C4/$L$4 ; E4: 218 ; F4: =E4/$L$4 ; G4: 1 ; H4: =G4/$L$4 ; L4: 267
- B5: IBIS ; C5: 15 ; D5: =C5/$L$5 ; E5: 341 ; F5: =E5/$L$5 ; G5: 6 ; H5: =G5/$L$5 ; L5: 362
- B6: NOVOTEL ; C6: 1 ; D6: =C6/$L$6 ; E6: 107 ; F6: =E6/$L$6 ; G6: 9 ; H6: =G6/$L$6 ; L6: 117
- B7: MERCURE ; C7: 27 ; D7: =C7/$L$7 ; E7: 224 ; F7: =E7/$L$7 ; G7: 3 ; H7: =G7/$L$7 ; I7: 1 ; J7: =I7/$L$7 ; L7: 255
- B8: TOTAL ; C8: 410 ; D8: =C8/$L$8 ; E8: 913 ; F8: =E8/$L$8 ; G8: 19 ; H8: =G8/$L$8 ; I8: 1 ; J8: =I8/$L$8 ; L8: 1343

### 5.x. Feuille `CRITERES POUR PANEL`

Définit un panel représentatif pour tester le simulateur : tranches de chambres, nombre de restaurants et bars par marque.

- B2: CRITERES POUR PANEL REPRESENTATIF (TESTS SIMULATEUR)
- C4: NB. CH. ; D4: NB. RESTO ; E4: NB. BAR
- B5: IBIS BUDGET ; C5: Entre 50 et 99 ch. ; D5: 0 ; E5: 0
- B6: IBIS STYLES ; C6: Entre 50 et 99 ch. ; D6: 0 ; E6: 1
- B7: IBIS ; C7: Entre 50 et 99 ch. ; D7: 0 et 1 ; E7: 1
- B8: NOVOTEL ; C8: Entre 100 et 149 ch. ; D8: 1 ; E8: 1
- B9: MERCURE ; C9: Entre 50 et 99 ch. ; D9: 1 ; E9: 1

### 5.x. Feuille `DATA`

Cartographie des données : nom de la donnée, source actuelle, contact/référent, API possible, stockage/outils, équipe responsable et commentaires Thomas. Cette feuille est utile pour définir le futur feature store.

- B2: CATEGORIE ; C2: DATA ; D2: SOURCE ACTUELLE ; E2: CONTACT / REFERENT ; F2: N+1 CONTACT / REFERENT ; G2: API ? ; H2: STOCKAGE / OUTIL ; I2: EQUIPE RESPONSABLE ; J2: COMMENTAIRE THOMAS (INNOLAB)
- B3: HOTEL ; C3: CODE H ; D3: 360 Hotel Referential ; E3: Benoit SALMON ; F3: François-Xavier MILLE
- C4: NOM DE L'HOTEL ; D4: 360 Hotel Referential ; E4: Benoit SALMON ; F4: François-Xavier MILLE
- B5: GENERAL INFORMATION ; C5: MARQUE ; D5: 360 Hotel Referential ; E5: Benoit SALMON ; F5: François-Xavier MILLE ; G5: API Portfolio ; J5: Taki IDER + Delphine BAROUX + Jennifer WINSTON (WeMax)
- C6: BUILT ; D6: 360 Hotel Referential ; E6: Benoit SALMON ; F6: François-Xavier MILLE ; G6: API Portfolio ; J6: Taki IDER + Delphine BAROUX + Jennifer WINSTON (WeMax)
- C7: NB. DE CHAMBRES ; D7: 360 Hotel Referential ; E7: Benoit SALMON ; F7: François-Xavier MILLE ; G7: API Portfolio ; J7: Taki IDER + Delphine BAROUX + Jennifer WINSTON (WeMax)
- B8: LOCALISATION ; C8: ADRESSE POSTALE (1) ; D8: Parc Hôtel Southern Europe ; E8:  -  ; F8:  - 
- C9: ADRESSE POSTALE (2) ; D9: Parc Hôtel Southern Europe ; E9:  -  ; F9:  - 
- C10: ADRESSE POSTALE (3) ; D10: Parc Hôtel Southern Europe ; E10:  -  ; F10:  - 
- C11: CODE POSTAL ; D11: Parc Hôtel Southern Europe ; E11:  -  ; F11:  - 
- C12: VILLE ; D12: VILLE ; E12: Benoit SALMON
- C13: LONGITUDE ; D13: Export à la demande ; E13: Rémy LEROY ; F13: Arnaud THULLIEZ
- C14: LATITUDE ; D14: Export à la demande
- C15: LOCATION ; D15: Données fictives pour le moment ; E15:  -  ; F15:  - 
- B16: OTHER INFORMATION ; C16: HOTEL LAST RENOVATION ; D16: Données fictives pour le moment ; E16:  -  ; F16:  - 
- C17: LOBBY LAST RENOVATION ; D17: Données fictives pour le moment ; E17:  -  ; F17:  - 
- C18: CONTRAT ; D18: 360 Hotel Referential ; E18: Benoit SALMON ; F18: François-Xavier MILLE ; H18: MEGA ou WeMax ; J18: Taki IDER + Delphine BAROUX + Jennifer WINSTON (WeMax)
- C19: OWNER ; D19: 360 Hotel Referential ; E19: Benoit SALMON ; F19: François-Xavier MILLE ; H19: MEGA ou WeMax ; J19: Taki IDER + Delphine BAROUX + Jennifer WINSTON (WeMax)
- C20: DOM/DOF ; D20: 360 Hotel Referential ; E20: Benoit SALMON ; F20: François-Xavier MILLE ; H20: MEGA ou WeMax ; J20: Taki IDER + Delphine BAROUX + Jennifer WINSTON (WeMax)
- C21: PMS ; D21: 360 Hotel Referential ; E21: Benoit SALMON ; F21: François-Xavier MILLE ; G21: API Portfolio ; J21: Taki IDER + Delphine BAROUX + Jennifer WINSTON (WeMax)
- B22: BUSINESS INFORMATION ; C22: # GUESTS PER ROOM ; D22: Données fictives pour le moment ; E22:  -  ; F22:  -  ; J22: Elias TANNOURY + Sylvain SETRAKIAN + Geetanjali ROGBEER
- C23: YTD OCC. RATE ; D23: Données fictives pour le moment ; E23:  -  ; F23:  -  ; J23: Elias TANNOURY + Sylvain SETRAKIAN + Geetanjali ROGBEER
- C24: LOWEST (MONTH) ; D24: Données fictives pour le moment ; E24:  -  ; F24:  -  ; J24: Elias TANNOURY + Sylvain SETRAKIAN + Geetanjali ROGBEER
- C25: LOWEST (RATE) ; D25: Données fictives pour le moment ; E25:  -  ; F25:  -  ; J25: Elias TANNOURY + Sylvain SETRAKIAN + Geetanjali ROGBEER
- C26: HIGHEST (MONTH) ; D26: Données fictives pour le moment ; E26:  -  ; F26:  -  ; J26: Elias TANNOURY + Sylvain SETRAKIAN + Geetanjali ROGBEER
- C27: HIGHEST (RATE) ; D27: Données fictives pour le moment ; E27:  -  ; F27:  -  ; J27: Elias TANNOURY + Sylvain SETRAKIAN + Geetanjali ROGBEER
- B28: SERVICES ; C28: BAR ; D28: 360 Hotel Referential ; E28: Benoit SALMON ; F28: François-Xavier MILLE ; J28: Vanessa PACINI
- C29: RESTAURANT ; D29: 360 Hotel Referential ; E29: Benoit SALMON ; F29: François-Xavier MILLE ; J29: Vanessa PACINI
- C30: ROOM-SERVICE ; D30: Données fictives pour le moment ; E30:  -  ; F30:  - 
- C31: MINIBAR ; D31: Données fictives pour le moment ; E31:  -  ; F31:  - 
- C32: MEETING ROOMS ; D32: 360 Hotel Referential ; E32: Benoit SALMON ; F32: François-Xavier MILLE ; J32: Vanessa PACINI
- C33: FITNESS ; D33: 360 Hotel Referential ; E33: Benoit SALMON ; F33: François-Xavier MILLE ; J33: Vanessa PACINI
- C34: SPA ; D34: 360 Hotel Referential ; E34: Benoit SALMON ; F34: François-Xavier MILLE ; J34: Vanessa PACINI
- C35: POOL ; D35: 360 Hotel Referential ; E35: Benoit SALMON ; F35: François-Xavier MILLE ; J35: Vanessa PACINI
- B36: GUEST PROFILING ; C36: NATIONAL ; D36: Données fictives pour le moment ; E36:  -  ; F36:  -  ; J36: Elias TANNOURY + Sylvain SETRAKIAN + Geetanjali ROGBEER
- C37: INTERNATIONAL ; D37: Données fictives pour le moment ; E37:  -  ; F37:  -  ; J37: Elias TANNOURY + Sylvain SETRAKIAN + Geetanjali ROGBEER
- C38: LEISURE ; D38: Données fictives pour le moment ; E38:  -  ; F38:  -  ; J38: Elias TANNOURY + Sylvain SETRAKIAN + Geetanjali ROGBEER
- C39: BUSINESS ; D39: Données fictives pour le moment ; E39:  -  ; F39:  -  ; J39: Elias TANNOURY + Sylvain SETRAKIAN + Geetanjali ROGBEER

### 5.x. Feuille `PROTOTYPE`

Spécification fonctionnelle de l’interface du simulateur ROD : paramètres hôtel, espace retail, règles UI, solutions proposées, matériel, toggles, sélection, affichage. Elle est une base pour transformer le prototype Excel en application web.

- B2: PROTOTYPE - SIMULATEUR ROD + REGLES POUR RECO DU CONCEPT RETAIL
- B4: HOTEL PARAMETERS ; I4: RETAIL SPACE(S)
- D6: min. ; F6: max. ; K6: min.
- B7: Nb. of rooms ; D7: 1 ; E7: auto ; F7: 1000 ; I7: Name of the space ; K7: liste déroulante
- B8: Nb. of guests /room ; D8: 1 ; E8: incrément 0,5 ; F8: 6 ; I8: Wall linear meters ; K8: 2m ; L8: incrément 1
- B9: Average occ. rate ; D9: 0 ; E9: incrément 1 ; F9: 1 ; I9: Square meters ; K9:  -  ; L9: auto
- B17: REGLES CONCERNANT LES PARAMETRES CI-DESSUS
- B19: No specific rules ; I19: Wall linear meters /  / 1. En fonction du nom de l'espace sélectionné par l'hôtel dans la liste déroulante, les données correspondantes (mètres linéaires et m²) s'affichent automatiquement. /  / 2. Les m² se calculent automatiquement en fonction du n
- B35: PROPOSED AUTONOMOUS SOLUTIONS >> MATERIEL
- B37: Les trois solutions (types de boutique) s'affichent >> voir design proposé par Sylvain >> bouton "NEXT OPTIONS".
- B38: La solution (type de boutique) qui s'affichera en premier, sera la solution recommandée par l'Innovation Lab en fonction des paramètres qui seront indiqués/complétés par l'hôtel dans le simulateur.
- B39: Une seule solution à la fois peut-être sélectionnée par l'hôtel afin d'obtenir les résultats du simulateur (CA F&B, CA NON-F&B…).

### 5.x. Feuille `CORRECTIONS ND`

Liste de corrections produit/UX demandées : modifier marges et coûts dans back-office, afficher Not profitable si revenus négatifs, refresh auto, comportement slider F&B lorsque toggles off, logos, mise à jour selon machines/agencement, etc.

- B2: CORRECTIONS NET DEVICES - 30/10/2025
- B4:  - Modifier marges produits et coûts dans le back-office
- B5:  - Afficher plutôt "Not profitable" si revenus négatifs (F&B ou NON-F&B ou TOTAL)
- B6:  - Attention la somme de F&B et NON-F&B ne fait pas exactement le montant affiché
- B7:  - Si "refresh" ou si modification d'une des variables alors = l'écran doit automatiquement affiché de nouveau la solution recommandée
- B8:  - Le slider F&B doit être à 0% lorsque tous les toggles sont OFF (ou message d'erreur)
- B9:  - Logos hôtels pas tout le temps corrects
- B10:  - Mise à jour automatique en modifiant le nb. de machines et l'agencement
- B11:  - Modifier la couleur du ou des toggles + du curseur/slider (barre + rond) en rouge (#DC2C3E) dès lors que ROD a modifié des paramètres automatiquement pour faire en sorte que le résultat soit positif
- B12:  - Modifier le composant heure/minutes dans l'étape #2 (ou le fixer)

## 6. Fichiers ROD récapitulatifs des hôtels pivots

Les fichiers `Récapitulatif...` contiennent le questionnaire ROD : étapes, sous-étapes, données, sources, possibilité de modification par l’utilisateur, exploitation dans la simulation, commentaires, puis colonnes par hôtel pivot.

Sections ROD détectées : `ETAPE ROD`, `0 - PAGE DE CONNEXION`, `1 - INFORMATIONS
GENERALES`, `2 - SERVICES &
EQUIPEMENTS`, `3 - PROFIL DE VOS
CLIENTS`, `4 - INFORMATIONS
CORNER`, `5 - SIMULATEUR
DE REVENUS`.

Hôtels/colonnes détectés dans le récapitulatif :

|col|brand_header|city_header|hotel_name|
|---|---|---|---|
|10|IBIS BUDGET|NICE|IBIS BUDGET NICE CALIFORNIE|
|11||STRASBOURG|IBIS BUDGET STRASBOURG REPUBLIQUE|
|12|IBIS STYLES|PARIS CDG|IBIS STYLES ROISSY CDG|
|13|NOVOTEL|MEGEVE|NOVOTEL MEGEVE MONT BLANC|
|14||TOUR EIFFEL|NOVOTEL PARIS CENTRE TOUR EIFFEL|
|15|MERCURE|MONTMARTRE|MERCURE MONTMARTRE SACRE COEUR|
|16||BOULOGNE|MERCURE PARIS BOULOGNE|

Interprétation fonctionnelle : ces données décrivent l’hôtel pivot ou nouveau hôtel au niveau ROD : page connexion, informations générales, services/équipements, profil clients, informations corner, simulateur de revenus. Elles alimentent les features non transactionnelles.


## 7. Données de ventes transactionnelles

Fichier principal : `001.queryVentes.csv`. Il contient les ventes enrichies sur plusieurs hôtels, machines, catégories et dates.

- Nombre de lignes : 85674
- Colonnes : 20
- Période : 2023-08-10 → 2026-04-07
- Hôtels avec ventes : Ibis budget Nice, Ibis budget Strasbourg Centre République, Mercure Paris Montmartre Sacré-Cœur, Novotel Megève Mont-Blanc, Novotel Paris Tour Eiffel, Novotel Porte d’Italie


**Types :**

- `F&B` : 75241
- `NON-F&B` : 9679
- `nan` : 754

**Gammes / catégories :**

- `SANS ALCOOL` : 44249
- `FOOD SUCREE` : 15915
- `FOOD SALEE` : 13312
- `SOS` : 7414
- `ALCOOL` : 1727
- `nan` : 754
- `ACCESSOIRES` : 586
- `#REF!` : 444
- `JEUX / ENFANTS` : 420
- `COSMETIQUE` : 383
- `PAP` : 290
- `SOUVENIRS` : 180

**Opérateurs :**

- `DIGITIZME` : 58086
- `SELFLYSTORE` : 16696
- `ADIPOS` : 10892

**Machines principales :**

- `FRIGO TOUR EIFFEL` : 44160
- `ACCESSORIES (armoire sèche)` : 11802
- `SCANNER NICE` : 5903
- `FRIGO MONTMARTRE (GRAB & GO)` : 5155
- `BORNE MEGEVE` : 4989
- `FRIGO STRASBOURG` : 4665
- `FRIGO MONTMARTRE (APERO PREMIUM 2)` : 3247
- `FRIGO MONTMARTRE (APERO PREMIUM 1)` : 3009
- `FRIGO PORTE D’ITALIE` : 2124
- `FRIGO MONTMARTRE (SOUVENIRS)` : 355
- `Ibis Budget Strasbourg` : 265

### 7.1. Catalogue catégories, sous-catégories, produits exemples

Catalogue complet exporté dans `catalogue_ventes_categories_produits.csv`. Extrait :

|TYPE|GAMME|nb_lignes|nb_produits_distincts|top_produits|top_marques|
|---|---|---|---|---|---|
|F&B|ALCOOL|1727|28|Bière Heineken (25cl) (581) ; Grand vin Mercure (254) ; Bière Gallia (25cl) (246) ; Champagne demi bouteille (189) ; Heineken  (136) ; Gallia (49) ; Demi bouteille de vin (34) ; Mo|HEINEKEN (717) ; - (343) ; GALLIA (295) ; MERCURE (254) ; BACCHANTE (48) ;  -  (35) ; DUVEL (14) ; LA DEBAUCHE (13)|
|F&B|FOOD SALEE|13312|151|CHIPS NATURE SEL GUERANDE 90g (1628) ; CHIPS DE POULET ROTI 45g (1467) ; Chips (90g) (599) ; CLUB JAMBON BEURRE FLEUR DE SEL DE GUÉRANDE SALADE (582) ; BURGER BISTROT BŒUF CHAROLAI| -  (9872) ; - (1154) ; SODEBO (457) ; LAYS (357) ; BEENDI (312) ; MONOPRIX (245) ; BRETS (220) ; TUC (177)|
|F&B|FOOD SUCREE|15915|163|TWIX 50g (1182) ; KINDER BUENO 43g (1149) ; SNICKERS 50g (1072) ; LION 42g (1057) ; M&M'S 45g (1013) ; TOBLERON LAIT 50G (795) ; Barre chocolatée (ex : Mars, Twix, Lion...) (737) ;| -  (2137) ; - (1682) ; KINDER (1612) ; TWIX (1444) ; M&M'S (1360) ; SNICKERS (1280) ; LION (1154) ; HARIBO (894)|
|F&B|SANS ALCOOL|44249|130|VITTEL 50cl (7463) ; COCA COLA ZERO  33CL (3717) ; COCA COLA 33CL (3334) ; L'EAU NEUVE 50CL (1916) ; SAN PELLEGRINO  50cl (1895) ; L'Eau Neuve (50cl) (1750) ; SPRITE  33CL (1485) ;|COCA COLA (10511) ; VITTEL (9830) ; EAU NEUVE (4928) ; SAN PELLEGRINO (2872) ; PERRIER (2012) ; SPRITE (1786) ; ORANGINA (1521) ; FUZE TEA (1510)|
|F&B|SOUVENIRS|38|8|Peluche Chamois (12) ; Confiture Parisienne (7) ; La French Baguette (7) ; Glacons De Megeve (6) ; Miel de Fleurs Crémeux 140g (3) ; Miel de Sapin 140g (1) ; Grelots Aux Beaufort (|MONOPRIX (14) ; - (12) ; DIVERS (12)|
|NON-F&B|#REF!|444|53|Cable de recharge (67) ; serviette de plage bleue 145 x 85 cm (44) ; Trousse de toilette Femme (38) ; Peluche Ourson (32) ; Peluche Stitch (25) ; Echarpe Mickey / Scarf  (23) ; Tot|DECATHLON (212) ; - (90) ; DISNEY (79) ; MONOPRIX (41) ; KUMQUAT (22)|
|NON-F&B|ACCESSOIRES|586|56|TONGS HOMME TO 100 NOIR (56) ; TONGS FEMME 100 NOIR (54) ; Chaussette Mickey / Socks (44) ; Lunettes de natation (36) ; MF COMPACT XL TOWEL BLUE PETROL (26) ; Trousse de toilette H|DECATHLON (476) ; DISNEY (68) ; RAINS (40) ; KUMQUAT (2)|
|NON-F&B|COSMETIQUE|383|48|SPRAY FACIAL FACIAL BRUMISATEUR (64) ; Trousse de voyage (46) ; Baume à levre (39) ; Rituals Gel Douche Moussant (26) ; RitualsSmall Gift Set (19) ; Spray facial Brumisateur Evian |MONOPRIX (84) ; RITUALS (83) ;  -  (83) ; - (46) ; NUXE (34) ; RESPIRE (15) ; DECATHLON (14) ; NIVEA (13)|
|NON-F&B|JEUX / ENFANTS|420|62|Peluche Mickey Small (54) ; Mes coloriages avec stickers, Stitch (34) ; Ou ce cache Stitch (29) ; Mes coloriages avec stickers, Encanto la fantastique famille Madrigal (25) ; Mes c|DISNEY (299) ; MONOPRIX (74) ; LEGO (15) ; DECATHLON (14) ; UNO (5) ; MIKADO (5) ; RUBIKS CUBE (3) ; QUI EST CE (3)|
|NON-F&B|PAP|290|50|T-shirt Blanc Mickey / White T-shirt (64) ; BOARDSHORT HENDAIA ECO NT BLEU (60) ; Pull Blanc Mickey/ White Pullover (43) ; Pull Vert Mickey/ Green Pullover (34) ; MAILLOT DE BAIN D|DECATHLON (147) ; DISNEY (143)|
|NON-F&B|SOS|7414|61|GOURDE (1319) ; ADAPTATEUR UNIVERSEL (970) ; KIT DENTAIRE COLGATE (834) ; Gourde en verre Novotel (768) ; GOURDE EN VERRE NOVOTEL (704) ; Gourde (567) ; Kit Dentaire Colgate (447) | -  (3942) ; NOVOTEL (1659) ; COLGATE (1281) ; LOVE & GREEN (242) ; MONOPRIX (124) ; - (119) ; MERCURE (25) ; DECATHLON (12)|
|NON-F&B|SOUVENIRS|142|19|Carte Postale  (79) ; Bougie Fleurs d'alpage (7) ; Mug (7) ; Bougie Fruits d'altitude (6) ; Pochette en tissu "Paris mon amour" (6) ; Bougie Lac & Montagne (6) ; Tote-bag parisienn|- (118) ; MONOPRIX (23) ; DIVERS (1)|
|||754|73|SAN BENDETTO GAZEUSE (124) ; SAN BENDETTO  PLATE (98) ; Boites De Biscuits 240g (43) ; Porte clé - Novotel (38) ; Peluche porte Clés (28) ; Petite Boite De Biscuits 120g (24) ; Pel||

### 7.2. Export février 2026

Le fichier `2026.02.Fevrier-ExportAccor.xlsx` contient `3491` lignes pour la période `2026-02-01` → `2026-02-28`. Il a deux feuilles : `Result 1` et `Query`. Il sert de version courte/récente pour tester les notebooks d’association.

Hôtels dans cet export : Ibis budget Nice, Ibis budget Strasbourg Centre République, Mercure Paris Montmartre Sacré-Cœur, Novotel Megève Mont-Blanc, Novotel Paris Tour Eiffel, Novotel Porte d’Italie.


## 8. Fichier `Analyse du poids des catégories de produit (2024-2025).xlsm`

Ce fichier contient une base historique et des analyses de poids de catégories. Feuilles détectées : `BASE`, `Détails1`, `Feuil1`. La feuille `BASE` contient beaucoup de formules, notamment des colonnes calculées `Mois`, `Day`, clé composite et pondération par ticket. Des formules contiennent `#REF!`, donc certaines références Excel étaient cassées dans le fichier. Cela doit être traité comme une source à auditer avant reprise en Python.

Exemples de formules extraites de `BASE` :

|sheet|cell|formula|
|---|---|---|
|BASE|A1|=TEXT(D2,"mmmm"&" " &"aaaa")|
|BASE|F2|=IF(WEEKDAY(D2, 2) > 5, "Week-end", "Semaine")|
|BASE|G2|=A2 & "_" & TEXT(D2,"aaaammjj") & "_" & S2|
|BASE|U2|=1 / COUNTIF($T:$T, T2)|
|BASE|V2|=IFERROR(INDEX(#REF!, MATCH(E2,#REF!, 0), MATCH(A2,#REF!, 0)), 0)|
|BASE|X2|=TEXT(D3,"mmmm"&" " &"aaaa")|
|BASE|F3|=<v>Semaine</v></c><c r="G3" s="35" t="s"><v>1260</v></c><c r="H3" s="4" t="s"><v>827</v></c><c r="I3" s="12" t="s"><v>443</v></c><c r="J3" s="5" t="s"><v>444</v></c><c r="K3" s="1|
|BASE|U3|=<v>1</v></c><c r="V3" s="3" t="s"><v>4529</v></c><c r="W3" s="55"><f>IFERROR(INDEX(#REF!, MATCH(E3,#REF!, 0), MATCH(A3,#REF!, 0)), 0)|
|BASE|X3|=VLOOKUP(AI3,$AC$8:$AD$20,2,FALSE)|
|BASE|AL3|=IF(AJ3=TRUE,(VLOOKUP(AI3,$AC$8:$AE$20,3,FALSE)+1)*AK3,(1-VLOOKUP(AI3,$AC$8:$AE$20,3,FALSE))*AK3)|
|BASE|A4|=TEXT(D4,"mmmm"&" " &"aaaa")|
|BASE|F4|=<v>Semaine</v></c><c r="G4" s="35" t="s"><v>1261</v></c><c r="H4" s="4" t="s"><v>827</v></c><c r="I4" s="12" t="s"><v>665</v></c><c r="J4" s="5" t="s"><v>666</v></c><c r="K4" s="1|
|BASE|X4|=VLOOKUP(AI4,$AC$8:$AD$20,2,FALSE)|
|BASE|AL4|=IF(AJ4=TRUE,(VLOOKUP(AI4,$AC$8:$AE$20,3,FALSE)+1)*AK4,(1-VLOOKUP(AI4,$AC$8:$AE$20,3,FALSE))*AK4)|
|BASE|A5|=<v>août 2023</v></c><c r="F5" s="3" t="str"><f t="shared" si="0"/><v>Week-end</v></c><c r="G5" s="35" t="s"><v>1262</v></c><c r="H5" s="4" t="s"><v>827</v></c><c r="I5" s="12" t="|
|BASE|X5|=<v>43300.969207236238</v></c><c r="AL5" s="96"><f t="shared" ref="AL5:AL16" si="5">IF(AJ5=TRUE,(VLOOKUP(AI5,$AC$8:$AE$20,3,FALSE)+1)*AK5,(1-VLOOKUP(AI5,$AC$8:$AE$20,3,FALSE))*AK5)|
|BASE|A6|=<v>août 2023</v></c><c r="F6" s="3" t="str"><f t="shared" si="0"/><v>Week-end</v></c><c r="G6" s="35" t="s"><v>1263</v></c><c r="H6" s="4" t="s"><v>827</v></c><c r="I6" s="12" t="|
|BASE|X6|=<v>5532.8849073675565</v></c><c r="AL6" s="96"><f t="shared" si="5"/><v>5450.1197898730043</v></c></row><row r="7" spans="1:38" ht="13.95" customHeight="1" x14ac:dyDescent="0.3"><|
|BASE|X7|=<v>21089.88277021328</v></c><c r="AL7" s="96"><f t="shared" si="5"/><v>19887.362530699593</v></c></row><row r="8" spans="1:38" ht="13.95" customHeight="1" x14ac:dyDescent="0.3"><c|
|BASE|X8|=<v>51953.304661783906</v></c><c r="AL8" s="96"><f t="shared" si="5"/><v>44655.866586612312</v></c></row><row r="9" spans="1:38" ht="13.95" customHeight="1" x14ac:dyDescent="0.3"><|

## 9. Documentation technique des notebooks

Cette section transforme les notebooks/tentatives en documentation. Le fichier réellement uploadé ici est `association_gamme.ipynb`. Les autres notebooks sont documentés à partir des logs de lecture disponibles dans les fichiers markdown de conversation; il faudra réouvrir les `.ipynb` complets pour auditer ligne par ligne.


### `rod_data.ipynb`

Aplatissement Excel ROD hiérarchique en table 1 ligne par hôtel; contient HotelExcelFlattener et HotelDataPrep selon les logs. Génère/alimente rod_hotels_flattened, rod_hotels_ml_ready, rod_prepared_data, rod_prepared_base_data.


### `rod_data_v0.ipynb`

Ancienne version de la préparation ROD, plus simple, remplacée par la version principale.


### `rod_selection.ipynb`

Filtrage manuel de colonnes ROD via selection_rod.xlsx; nettoyage OUI/X→1, ?→moyenne, dummies selon les logs.


### `poi.ipynb`

Agrège les commerces/POI autour des hôtels par rayon; produit poi_prepared_data.xlsx selon les logs.


### `weather_data.ipynb`

Agrège la météo par mois et par géolocalisation; produit weather_prepared_data.xlsx selon les logs.


### `transaction_data.ipynb`

Agrège les ventes par hôtel/mois/TYPE/GAMME en format large; produit transaction_prepared_data.xlsx selon les logs.


### `merge_data.ipynb`

Joint les préparations ROD, POI, météo, transactions pour produire ml_data.xlsx selon les logs.


### `data_augmentation.ipynb`

Contient outils WeatherPrep/GeoPrep pour récupérer météo et POI avec cache selon les logs.


### `ml.ipynb`

Test ML basique Keras sur ml_data.xlsx; à considérer brouillon/prototype selon les logs.


### `ml_v0.ipynb`

Première tentative ML sur data.csv avec get_dummies; brouillon selon les logs.


### `rod_sim_cout.ipynb`

Modélise revenus/coûts via dataclasses et règles de simulation; base conceptuelle reliée aux fichiers ROD Simulateurs.


### `association_gamme.ipynb`

Notebook uploadé et inspecté complètement: règles d’association par GAMME avec apriori/lift sur export février 2026.

**Lecture cellule par cellule du fichier uploadé :**

- Cellule 0 (code) : Importe pandas et les fonctions `apriori` / `association_rules` de mlxtend.
```python
import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules
```
- Cellule 1 (code) : Charge l’export `2026.02.Fevrier-ExportAccor.xlsx`.
```python
df = pd.read_excel("2026.02.Fevrier-ExportAccor.xlsx")
```
- Cellule 2 (code) : 
```python
df.shape
```
- Cellule 3 (code) : 
```python
df.head(3)
```
- Cellule 4 (code) : Construit une date-heure et des features calendaires : année, mois, jour, semaine, week-end, heure, flags jour du mois >= i.
```python
from turtle import fd


dt_col = "DATE"
tm_col = "HEURE"
dttm_col = "DATETIME"

df[dttm_col] = pd.to_datetime(df[dt_col] + " " + df[tm_col])

df["ANNEE"] = df[dttm_col].dt.year
df["MOIS_D_ANNEE"] = df[dttm_col].dt.month
df["JOUR_DU_MOIS"] = df[dttm_col].dt.day
df["JOUR_DE_SEMAINE"] = df[dttm_col].dt.dayofweek
df["JOUR_D_ANNEE"] = df[dttm_col].dt.dayofyear
df["SEMAINE_D_ANNEE"] = df[dttm_col].dt.isocalendar().week.astype(int)
df["IS_WEEKEND"] = df["JOUR_DE_SEMAINE"].isin([5, 6]).astype(int)
df["HEURE_DU_JOUR"] = df[dttm_col].dt.hour
df.head(3)

df["JOUR_DU_MOIS"].nunique()

for i in range(2, 30):
    df[f"IS_JOUR_DU_MOIS_GEQ_{i}"] = (df["JOUR_DU_MOIS"] >= i).astype(int)

df.head(5)
```
- Cellule 5 (code) : Charge l’export `2026.02.Fevrier-ExportAccor.xlsx`.
```python
class Prep():
    def __init__(self, filepath : str):
        self.filepath = filepath

        self._df = None

    @property
    def df(self):
        if(self._df is None):
            self._df = pd.read_excel(self.filepath)
        return self._df
    

    
    


p = Prep("2026.02.Fevrier-ExportAccor.xlsx")
p.df["DATE"]
```
- Cellule 6 (code) : Filtre les ventes DONE, conserve ticket + GAMME, supprime valeurs nulles et doublons ticket/GAMME.
```python
ORDER_COL = "ORDER ID (TICKET DE CAISSE)"
PRODUCT_COL = "GAMME"
df = (
    df[df["STATUT"].str.upper() == "DONE"][[ORDER_COL, PRODUCT_COL]]
    .dropna()
    .drop_duplicates(subset = [ORDER_COL, PRODUCT_COL])
)
```
- Cellule 7 (code) : Filtre les ventes DONE, conserve ticket + GAMME, supprime valeurs nulles et doublons ticket/GAMME.
```python
basket = (
    df.assign(value=1)
    .pivot_table(
        index=ORDER_COL,
        columns=PRODUCT_COL,
        values="value",
        aggfunc="max",
        fill_value=0
    )          
    .astype(bool)
)
```
- Cellule 9 (code) : 
```python
basket
```
- Cellule 10 (code) : Calcule les itemsets fréquents avec support minimum 1%.
```python
frequent_itemsets = apriori(
    basket,
    min_support=0.01,   # à ajuster selon ton volume
    use_colnames=True
)
```
- Cellule 11 (code) : 
```python
frequent_itemsets.shape
```
- Cellule 12 (code) : Construit les règles d’association avec métrique lift et seuil minimal 1.
```python
rules = association_rules(
    frequent_itemsets,
    metric="lift",
    min_threshold=1.0
)
```
- Cellule 13 (code) : 
```python
rules.shape
```
- Cellule 14 (code) : 
```python
rules
```
- Cellule 15 (code) : Filtre les règles intéressantes : confidence >= 20% et lift >= 1.20, tri décroissant.
```python
rules[
    (rules["confidence"] >= 0.20) &
    (rules["lift"] >= 1.20)
].sort_values(
    by=["lift", "confidence", "support"],
    ascending=False
)
```

### `association_product.ipynb`

Même logique que association_gamme, mais au niveau NOM DU PRODUIT selon les logs.


## 10. Comment appliquer les calculs aux hôtels pivots puis aux nouveaux hôtels

### 10.1. Sur les hôtels pivots

1. Lire le ROD pivot : marque, chambres, TO, guests/chambre, services, équipements, corner, mètres linéaires, catégories autorisées.
2. Lire les ventes transactionnelles quand elles existent.
3. Construire les targets historiques : moyenne mensuelle globale, par catégorie et par sous-catégorie, en excluant 2026 pour test.
4. Calculer les features météo/POI si disponibles.
5. Appliquer les règles Excel ROD pour obtenir un résultat déterministe de référence : CA, marge produits, coûts, marge nette, amortissement.
6. Entraîner les modèles IA XGBoost sur les hôtels avec transactions.

### 10.2. Sur un nouvel hôtel du groupe Accor

1. L’utilisateur saisit nom/adresse et caractéristiques hôtel.
2. Le feature store récupère ou lit le cache : météo 12 mois, POI aux rayons 0.1/0.2/0.3/0.4/0.5 km, distance plage éventuellement.
3. L’utilisateur choisit ou fige des contraintes : concept, mètres linéaires, catégories interdites/autorisées, proportions.
4. Le moteur ROD calcule une simulation basée sur les règles Excel.
5. Le modèle IA prédit le nombre de ventes et le montant par mois, catégorie, sous-catégorie et globalement.
6. L’optimiseur teste les configurations non figées et conserve la meilleure selon l’objectif choisi : CA, marge ou ROI.


## 11. Points d’attention sans extrapolation

- Les fichiers Excel contiennent des règles explicites mais certaines zones sont prototypes ou à compléter, notamment `TESTS CONNECTED` où des lignes indiquent `>> à compléter`.
- Le fichier `.xlsm` d’analyse de poids contient des références cassées `#REF!`; il ne faut pas reprendre ces formules sans correction.
- Les commentaires Excel natifs détectés sont limités : essentiellement des commentaires thread en `M166` dans les simulateurs. Les vrais commentaires métier sont surtout des cellules textuelles comme `COMMENTAIRE THOMAS`.
- Les notebooks complets autres que `association_gamme.ipynb` ne sont pas tous uploadés ici : la documentation détaillée ligne par ligne devra être complétée quand les fichiers `.ipynb` complets seront disponibles.
