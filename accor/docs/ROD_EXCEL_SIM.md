# Simulateur Excel ROD

Vue admin calquée sur le classeur Excel métier, avec **référence par solution**
(SIMPLY / LIBERTY / CONNECTED) et affichage **dual-colonne** type Excel.

**Ne remplace pas** le [Simulateur ROD](ROD_ADMIN.md) (référence par **catégorie
de marque** + écart temporel 2026). Les deux coexistent dans la sidebar admin.

---

## Sources de vérité

| Source | Rôle |
|--------|------|
| `archive/sources/raw/ROD_Audit_Complet_Regles_Simulateurs.html` | Audit métier croisé : mapping pilotes, 4 règles CA, coûts, marge nette, arbre de reco, « Not profitable », années 2023–2025 / 2026 |
| `archive/sources/raw/ROD - Simulateurs + détail des coûts.xlsx` | 3 simulateurs (feuilles SIMULATEUR \*), barèmes COUTS - TECHNOS / ANNEXES / AGENCEMENT, REVENUS - MIX & MARGES, REVENUS - IMPACT TO |
| `archive/sources/raw/ROD - Paramètres & règles + projections nb. d'hôtels.xlsx` | Arbre de décision de recommandation + projections de parc |
| `archive/sources/raw/Analyse du poids des catégories de produit (2024-2025).xlsm` | Ventes réelles / poids catégories (validation R3, pas leviers de simu) |
| `data/rod_reference.json` | Pivots runtime extraits de l’Excel (CA base, mix, marges, cost_lines) |
| `data/rod_pilot_concepts.json` | Mapping **pilote → solution** utilisé par le code |

Runtime : `src/accor/rod_excel_sim.py` + moteur commun
`user/rules/{revenue,costs,recommendation,coeffs}.py`.

### Colonne pilote éditable (cascade)

Les 3 simulateurs Excel (Simply / Liberty / Connected) exposent la **colonne
gauche** (moyenne pilotes) en **saisie** :

| Champ | Impact |
|-------|--------|
| Nb. chambres, TO, guests | Clients pilote / mois → facteur R1 |
| M. lin. | Réf. R4 (CA / m) |
| Mix F&B, marges F&B / N-F&B | Réf. R2 + marge produit |
| CA HT F&B / N-F&B, nb. ventes | Base R1 et revenus pilote |

Toute modification est renvoyée en `pilot_overrides` dans
`POST /api/rod/excel/simulate` et recalcule **gauche + droite** (R1→R4,
coûts, marge nette, amortissement). Bouton **Réinitialiser** = pivots Excel.

---

## Différence clé vs Simulateur ROD (catégorie)

| | **Simulateur ROD** ([ROD_ADMIN.md](ROD_ADMIN.md)) | **Simulateur Excel** (ce doc) |
|--|---------------------------------------------------|-------------------------------|
| Référence | Pilotes de la **même catégorie** de marque | Pilotes de la **même solution** |
| Onglets UI | CA / coûts & marge / écart / batch | **SIMPLY · LIBERTY · CONNECTED** |
| Layout | Formulaire + résultats | **2 colonnes** type Excel |
| Commentaires | Formules courtes | Textes Excel (R1–R4, coûts, amort) |
| Écart hold-out 2026 | Oui (batch MAE/MAPE) | Non (fidélité Excel / P&L solution) |
| API | `/api/rod/*` | `/api/rod/excel/*` |

---

## Mapping pilotes → solution

Fichier runtime : [`data/rod_pilot_concepts.json`](../data/rod_pilot_concepts.json)
(issu des feuilles Excel `REVENUS - MIX & MARGES`, `REVENUS - IMPACT TO`,
`COUTS - AGENCEMENT` — confirmé par l’audit HTML).

| Solution | Pilote(s) | Codes hôtel | Rôle |
|----------|-----------|-------------|------|
| **SIMPLY** | IBB NICE + IBB STRA | `H2075`, `HB6A3` | Principal + secondaire (agencement) |
| **LIBERTY** | MER BOUL + NOV MEG | `H6188`, `HB5I0` | Moyenne des 2 pilotes Liberty |
| **CONNECTED** | MER MONT | `H0373` | Pilote Connected |

Règles d’agrégation :

* **plusieurs hôtels pour une solution** → **moyenne** des paramètres live
  (chambres, TO, guests) sur les années train ;
* **CA F&B / N-F&B / nb ventes / mix / marges / m_lin** de base =
  pivots Excel dans `rod_reference.json` (moyennes multi-pilotes déjà
  extraites — intègrent des ventes réception hors bornes seules) ;
* si params live indisponibles → fallback pivots Excel.

> Non mappés (audit) : Novotel Tour Eiffel (volume élevé, non taggé),
> Novotel Porte d’Italie (petit volume). Seuls les codes de
> `rod_pilot_concepts.json` alimentent le simulateur Excel.

---

## Années de référence / évaluation

Même découpage temporel que le Simulateur ROD et l’audit :

| Période | Années | Rôle |
|---------|--------|------|
| **Référence / modélisation** | **2023, 2024, 2025** | Moyennes pilotes solution (params live) ; pivots Excel calibrés sur cette fenêtre |
| **Évaluation** | **2026** | **Exclue** des calculs de référence ; réservée au back-test / écart (Simulateur ROD) |

Dans le code : `_years_split(sales)` → `eval_year = max(années)` (ex. 2026),
`train_years = années < eval_year` (ex. 2023–2025). Paramètre optionnel
`year` sur les API Excel pour forcer l’année d’éval.

---

## Feuilles annexe Excel (MIX PRODUITS + IMPACT TO)

Fichier runtime : `data/rod_excel_sheets.json`  
Affichées en tête de chaque onglet (sections repliables).

### REVENUS ► MIX PRODUITS

| Solution | Pilotes (mix F&B/N-F&B · marges) | Marge moyenne |
|----------|----------------------------------|---------------|
| SIMPLY | IBB NICE 70/30 · 2,60/1,45 | **2,26** |
| LIBERTY | MER BOUL 100/0 · 2,60 + NOV MEG 30/70 · 2,60/2,00 | **2,39** |
| CONNECTED | MER MONT 90/10 · 2,60/1,80 | **2,52** |

> Mix **Règle 2** du SIMULATEUR peut différer (SIMPLY **40/60** dans la
> feuille SIMULATEUR vs **70/30** dans MIX PRODUITS).

### REVENUS ► TAUX D'OCCUPATION (IMPACT TO)

| Solution | TO moyen | CA HT total | Impact +1 % TO (HT) |
|----------|----------|-------------|---------------------|
| SIMPLY | 78 % | 720 € | **9 €** (F&B 7 + N-F&B 2) |
| LIBERTY | 68 % | 1 479 € | **22 €** |
| CONNECTED | 75 % | 3 634 € | **48 €** |

---

## Layout UI dual-colonne (type Excel)

Dans la **sidebar admin**, 3 entrées séparées (même design, chiffres différents) :

* **Simulateur Simply**
* **Simulateur Liberty**
* **Simulateur Connected**

Chaque entrée ouvre la même vue dual-colonne, pré-positionnée sur la solution :

```
┌────────────────────────────────┬────────────────────────────────┐
│ MOYENNE RESULTATS PILOTES      │ SIMULATEUR                     │
│ {SOLUTION}                     │ Hôtel désigné                  │
│ (params + CA base solution)    │ (R1→R4 + coûts + marge nette)  │
└────────────────────────────────┴────────────────────────────────┘
```

| Colonne | Contenu | Comportement moteur |
|---------|---------|---------------------|
| **Gauche** | Moyenne pilotes de la **solution** | CA base Excel **sans** rejouer R2–R4 (équivalent `E120 = E34` dans l’Excel) ; coûts au pivot solution |
| **Droite** | Projection sur l’**hôtel désigné** | Chaîne complète Impact TO + R1→R4 + coûts + amort, avec **référence de cette solution** |

Étapes affichées (ids communs left/right pour l’UI) :

1. `params` — PARAMETRES HOTEL  
2. `derived` — ch. occ., clients/jour, clients/mois, nb ventes, taux acheteurs  
3. `r1` … `r4` — les 4 règles de revenus  
4. `revenus` — CA HT F&B + N-F&B + total  
5. `marge_produit` — marge produits mensuelle  
6. `couts` — techno / annexes / agencement / capex  
7. `marge_nette` — marge nette + taux  
8. `amort` — amortissement mois / ans  

Commentaires métier Excel : constante `EXCEL_COMMENTS` dans `rod_excel_sim.py`
(textes R1–R4, coûts, amort repris de l’audit / Excel).

Front : `static/js/admin/rod-excel-panel.js` · template `#view-rod-excel`.

---

## Chaîne de calcul (ordre strict — audit §3 / §11)

Lorsqu’un hôtel est saisi :

1. **Collecte des paramètres** — nb chambres, guests/chambre, TO (YTD),
   m_lin, mix F&B, catégories cochées (besoins client).
2. **Arbre de recommandation** — détermine quelle solution s’affiche
   **en premier** (voir ci-dessous). Les 3 solutions restent calculées.
3. **Pour chaque solution** — P&L complet (4 règles + coûts + marge nette).
4. **Affichage** — CA, marge produits, coûts, marge nette, amortissement ;
   reco structurante même si une autre solution a un meilleur CA brut.

---

## Les 4 règles de revenus

Appliquées **dans l’ordre**, en partant des chiffres de référence pilote
(colonne gauche). Moteur : `RevenueRules` (`user/rules/revenue.py`).

### Règle 1 — Clients acheteurs

```
Clients_hébergés_mois = Nb_chambres × Guests_per_room × TO × 30,5
Taux_acheteurs        = Nb_ventes_pilote / Clients_hébergés_pilote
Facteur_clients       = Clients_hôtel / Clients_pilote

CA_F&B  ∝ facteur   (base = CA_F&B_pilote solution)
CA_NFB  ∝ facteur
```

Références pilotes mensuelles (pivots Excel / audit) :

| | SIMPLY | LIBERTY | CONNECTED |
|--|--------|---------|-----------|
| Nb ventes / mois | 231 | 312 | 534 |
| CA F&B HT | 533 € | 1 055 € | 3 503 € |
| CA N-F&B HT | 187 € | 424 € | 131 € |

### Règle 2 — Mix produits (±10 %)

Chaque pas de **10 %** de mix F&B (ou N-F&B) par rapport au mix de
référence du concept impacte le CA (bonus ou malus).

Mix de référence concept :

| | SIMPLY | LIBERTY | CONNECTED |
|--|--------|---------|-----------|
| F&B | 0,40 | 0,70 | 0,80 |
| N-F&B | 0,60 | 0,30 | 0,20 |

### Règle 3 — Catégories sélectionnées

```
SI catégorie cochée     → + coeff × CA
SI catégorie non cochée → − coeff × CA
```

Appliqué séparément sur CA F&B et CA N-F&B **après R2**. Si le CA précédent
est négatif, la sélection de catégories « réduit la perte ».

Coefficients (leviers de simulation, **pas** les poids historiques) :
`RULE3_FB_COEFFS` / `RULE3_NFB_COEFFS` dans `coeffs.py`
(cumul max F&B ≈ 0,48 · N-F&B ≈ 0,19 — audit §5).

### Règle 4 — Surface / équipement

* **SIMPLY & LIBERTY** : chaque mètre linéaire en plus/moins vs pivot
  (6 ML Simply / 8 ML Liberty).
* **CONNECTED** (logique Excel métier) : chaque frigo connecté vs réf.
  (3 frigos) — le runtime Python aligne surtout le scaling sur `m_lin`
  pivot (voir `rod_reference` / `RevenueRules`).

```
Diff = ML_simulé − ML_réf
CA_unit = CA_réf / ML_réf
CA = CA_après_R3 + CA_unit × Diff
```

### Marge produits

```
Marge = CA − CA / coef_marge
```

| Concept | Coef F&B | Coef N-F&B |
|---------|----------|------------|
| SIMPLY | 2,6 | 1,45 |
| LIBERTY | 2,6 | 2,0 (pilote) / ~1,45 (simu selon pivot) |
| CONNECTED | 2,6 | ~1,8 (pilote) / ~1,45 (simu) |

---

## Coûts mensuels

`CostRules` lit `concepts.{CONCEPT}.cost_lines` dans `rod_reference.json`.

```
Coût total mensuel = Techno + Annexes + Agencement
```

| Groupe | Contenu typique | Amort |
|--------|-----------------|-------|
| **Techno** | Scanner (Simply) / Caisse (Liberty) / Frigo froid (Connected) + vitrine + licence + frais OS | souvent / 60 mois ; licence 50 €/mois |
| **Annexes** | Électricité équipements + staff | mensuel direct |
| **Agencement** | Classic / Premium / Bespoke × m_lin | / 84 mois |

Si `monthly_unit` > 0 → opex = monthly_unit × qty ;  
sinon si capex + amort → opex = capex / amort_months.

---

## Marge nette, amortissement, « Not profitable »

```
Marge_nette_mensuelle = Marge_produits − Coûts_mensuels
Taux_marge            = Marge_nette / CA_HT_total
Amortissement_mois    = Capex_total / Marge_nette_mensuelle   (si marge > 0)
Amortissement_ans     = Amortissement_mois / 12
```

**Règle d’affichage (audit §8 — corrections ND)** :

* si marge nette &lt; 0 → taux = **N/A** / **Not profitable** ;
* si revenus F&B, N-F&B ou total **négatifs** → afficher **« Not profitable »**
  plutôt qu’un chiffre négatif trompeur ;
* amortissement non calculé (ou vide) si marge nette ≤ 0.

---

## Arbre de recommandation (ordre d’affichage ≠ max CA)

Point critique de l’audit : la solution **recommandée / affichée en premier**
n’est **pas** purement le max de CA (ni même toujours le max de marge).

Arbre métier (Fichier C — Paramètres & règles) :

```
SI nb_chambres ≤ 49
    → SIMPLY en premier

SINON SI au moins 1 catégorie parmi
         {Cosmetics, Kids items, Ready-to-wear, Accessories, Souvenirs}
    → LIBERTY en premier

SINON SI mètres_linéaires > 4
    → LIBERTY en premier

SINON SI l’hôtel possède déjà une vitrine réfrigérée
    → LIBERTY en premier

SINON SI TO moyen < 70 %
    → LIBERTY en premier

SINON
    → CONNECTED en premier
```

Conséquences :

* on peut recommander la **2ᵉ meilleure** solution en CA si les règles
  structurelles (taille, catégories, ML, vitrine, TO) l’imposent ;
* c’est **volontaire** : adéquation opérationnelle / conceptuelle avant
  optimisation pure du CA brut ;
* les **3 solutions restent calculées et accessibles** ; la reco oriente
  l’ordre d’affichage, pas un exclusif.

Implémentation runtime actuelle (`RecommendationRules`) :

1. filtre d’admissibilité (n &lt; 50 → SIMPLY seul ; N-F&B lifestyle → ouvre LIBERTY) ;
2. parmi les concepts autorisés, sélection par **meilleure marge nette**.

L’arbre complet Excel (ML, vitrine, TO) reste la **spec métier** de
l’audit ; le code admin Excel expose les 3 onglets + le moteur commun.

Projections de parc (audit, parc 1 343) : SIMPLY ~13 % · LIBERTY ~70 % ·
CONNECTED ~17 %.

---

## API admin (`run_admin` :5055)

| Méthode | Chemin | Rôle |
|---------|--------|------|
| `GET` | `/api/rod/excel/meta` | Commentaires Excel, mapping pilotes, besoins F&B/N-F&B + coefs, défauts (`mix_fb`, `m_lin`, `client_needs`), labels layout |
| `GET` | `/api/rod/excel/pilots` | Moyennes par solution (`build_concept_reference`) + `map` ; query `year` optionnel |
| `GET\|POST` | `/api/rod/excel/simulate` | Dual-colonne pour les **3** solutions |

### Body / query `simulate`

| Champ | Rôle |
|-------|------|
| `hotel_code` | **requis** — hôtel désigné (colonne droite) |
| `m_lin` | mètres linéaires corner |
| `mix_fb` | mix F&B (0–1 ou %) |
| `client_needs` | dict booléen catégories R3 |
| `nb_chambres`, `taux_occupation`, `guests_per_chambre` | exploitation (sinon contexte hôtel) |
| `year` | année d’éval (défaut max des ventes → 2026) |

### Réponse `simulate` (schéma simplifié)

```json
{
  "ok": true,
  "hotel_code": "H0373",
  "eval_year": 2026,
  "train_years": [2023, 2024, 2025],
  "params": { "nb_chambres": 120, "m_lin": 6, "mix_fb": 0.7, "client_needs": {} },
  "concept_order": ["SIMPLY", "LIBERTY", "CONNECTED"],
  "concepts": {
    "SIMPLY": {
      "pilots": [...],
      "left":  { "ca_ht": ..., "marge_nette": ..., "steps": [...] },
      "right": { "ca_ht": ..., "marge_nette": ..., "steps": [...] },
      "steps": [ { "id": "r1", "left_rows": [], "right_rows": [], "comment": "..." } ],
      "kpi": { "left_ca_ht": ..., "right_ca_ht": ..., "right_marge_nette": ... }
    }
  },
  "comments": { "r1": "...", "r2": "..." }
}
```

### Exemples curl

```bash
curl -s 'http://127.0.0.1:5055/api/rod/excel/meta'
curl -s 'http://127.0.0.1:5055/api/rod/excel/pilots?year=2026'
curl -s -X POST 'http://127.0.0.1:5055/api/rod/excel/simulate' \
  -H 'Content-Type: application/json' \
  -d '{
    "hotel_code": "H0373",
    "year": 2026,
    "m_lin": 6,
    "mix_fb": 0.7,
    "nb_chambres": 120,
    "taux_occupation": 0.75,
    "guests_per_chambre": 1.7
  }'
```

---

## Code & fichiers

| Pièce | Chemin |
|-------|--------|
| Backend | `src/accor/rod_excel_sim.py` |
| Routes Flask | `src/accor/app.py` (`/api/rod/excel/*`) |
| Front panel | `static/js/admin/rod-excel-panel.js` |
| Template | `#view-rod-excel` dans `templates/index.html` |
| Mapping pilotes | `data/rod_pilot_concepts.json` |
| Pivots / coûts | `data/rod_reference.json` |
| Règles partagées | `src/accor/user/rules/{revenue,costs,recommendation,coeffs}.py` |
| Audit HTML | `archive/sources/raw/ROD_Audit_Complet_Regles_Simulateurs.html` |
| Excel source | `archive/sources/raw/ROD - Simulateurs + détail des coûts.xlsx` |

---

## Coexistence avec le Simulateur ROD (catégorie)

Les deux modules vivent **côte à côte** dans l’admin :

```
Sidebar admin
  → Simulateur ROD          # catégorie de marque + écart 2026
  → Simulateur Excel        # solution SIMPLY/LIBERTY/CONNECTED + dual-colonne
```

| Question métier | Outil |
|-----------------|-------|
| « Pour un hôtel d’une catégorie donnée, l’estimation règles tient-elle face au réel 2026 ? » | **Simulateur ROD** |
| « Que donne le P&L Excel pour chaque solution, avec la moyenne des pilotes de cette solution ? » | **Simulateur Excel** |

Moteur de revenus / coûts partagé ; seules la **construction de la
référence** (catégorie vs solution) et l’**UI** diffèrent. Détail des
formules communes : [ROD_RULES.md](ROD_RULES.md). Validation catégorie
+ hold-out : [ROD_ADMIN.md](ROD_ADMIN.md).
