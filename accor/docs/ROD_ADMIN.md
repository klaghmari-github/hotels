# Simulateur ROD — admin vs user

## Deux applications, deux usages

| App | Entrée | Public | Données de ventes |
|-----|--------|--------|-------------------|
| **User** | `run_user.py` / `accor-user` (:5056) | Directeur d’hôtel | Souvent **aucune** → on estime, on ne peut pas juger l’écart |
| **Admin** | `run_admin.py` / `accor-admin` (:5055) | Data / métier | **Hôtels pilotes** (ventes connues) → on estime **et** on évalue |

Le moteur de règles (revenus, coûts, reco) est le **même**. Seul le
contexte change : validation chiffrée côté admin grâce aux ventes historiques.

---

## Hôtel pilote

Un **hôtel pilote** est un hôtel pour lequel on a des **ventes sur des
années précédentes**. Ces séries servent de **modèle** pour :

1. estimer les ventes d’**autres** hôtels (même logique que le user, avec
   une référence issue des pilotes de même catégorie de marque) ;
2. estimer les ventes **futures du même hôtel** et, quand le « futur »
   devient disponible, **comparer** estimation et réel pour mesurer la
   fiabilité (écart).

Sans ventes passées, l’hôtel n’est pas un pilote : l’app user peut quand
même simuler (paramètres corner + défauts / scrape), mais sans score d’écart.

---

## Découpage **temporel** (pas par hôtel)

| Période | Années | Rôle |
|---------|--------|------|
| **Apprentissage / ref** | 2023, 2024, 2025 | Seules années pour construire la **référence** catégorie |
| **Évaluation** | 2026 (ex. mois 1–4) | Futur non vu à la modélisation → on estime puis on compare |

Points clés :

* L’**exclusion / inclusion est temporelle** : on exclut l’année 2026 de la
  ref, **pas** un sous-ensemble d’hôtels.
* **Tous** les hôtels avec ventes train entrent dans la moyenne de leur
  catégorie (pas de leave-one-out).
* On a **peu d’hôtels** en apprentissage : c’est normal avec les données
  actuelles ; le hold-out reste l’année 2026.
* Réel 2026 : `avg_true = somme(montant_ventes mois) / 12` → écart, MAE, etc.

Même esprit que le split ML (`_is_eval` / dernière année) ; ici le moteur
est **déterministe** (règles Excel), pas XGBoost.

---

## Flux admin (onglet Simulateur ROD)

1. Lister les pilotes (ventes sur les années **train**).
2. Catégorie de marque de l’hôtel.
3. **Référence** = moyennes de **tous** les pilotes de la catégorie sur
   2023–2025 (**pas 2026** ; **pas d’exclusion d’hôtel**) :
   - par année : avg mensuelle = Σ mois / 12 ;
   - moyenne multi-années par hôtel ;
   - moyenne entre hôtels de la catégorie.
4. Traiter l’hôtel comme **client corner** (m_lin, mix, sous-cat., chambres…).
5. Règles ROD → CA, coûts, marge (SIMPLY / LIBERTY / CONNECTED) + reco.
6. **Évaluer sur 2026** : écart vs réel (Σ/12). Batch → MAE / MAPE / biais.

---

## Flux user (`run_user`)

* **Même moteur** que l’admin : `simulate_hotel_trace` (ref catégorie train,
  corner, 3 concepts + reco).
* N’importe quel code hôtel (scrape Accor si fiche absente).
* **Pas d’écart** hold-out (`include_gaps=False`) — le directeur regarde le
  **résultat** (CA, marge, reco), pas la validation data.
* UI : grands chiffres, onglets Résultat / Détail CA / Coûts & marge,
  recalcul auto (pas de bouton Simuler).
* API : `POST /api/rod/simulate` (port 5056).

---

## API admin

| Méthode | Chemin | Rôle |
|---------|--------|------|
| GET | `/api/rod/meta` | labels sous-cat., défauts corner |
| GET | `/api/rod/pilots?year=` | pilotes train + `has_holdout` / réel éval |
| **GET\|POST** | `/api/rod/hotel/<code>/trace` | simu (UI = **POST** JSON corner) + gaps si réel |
| GET | `/api/rod/eval?year=` | batch ; MAE / MAPE si réel hold-out |

Module : `src/accor/rod_admin.py`  
UI : `static/js/admin/rod-sim-panel.js` — recalcul auto, onglets  
**CA** / **Coûts & marge** / **Écart réel·sim** / **Batch** (séparés).

Détail HTTP : [API_ADMIN.md](API_ADMIN.md) § Simulateur ROD.

---

## Formules

```
# référence (train uniquement, ex. 2023–2025)
avg_year(h, y) = sum(montant_ventes mois de y) / 12
ref_hotel(h)   = mean_y avg_year(h, y)
ref_cat(c)     = mean_h ref_hotel(h)   # tous les pilotes catégorie c (pas d'exclusion)

# réel hold-out (ex. 2026)
avg_true = sum(montant_ventes mois hold-out) / 12

# écart règles ROD
gap_rod = CA_sim_ROD_mensuel − avg_true
```

---

## Roadmap — comparer règles ROD et modèle ML (même hold-out)

**Objectif plus tard** : pour le **même hôtel pilote** et la **même année 2026**
(mois disponibles) :

| Source | Sortie |
|--------|--------|
| **Simulateur ROD** (règles fixes Excel) | CA estimé mensuel (déjà en place) |
| **Modèle ML** (XGBoost, entraîné hors 2026) | CA prédit mensuel (`model_eval` / Σ mois pred / 12) |
| **Réel 2026** | `avg_true` = Σ mois / 12 |

Puis afficher côte à côte :

```
gap_rod = sim_ROD − réel
gap_ml  = pred_ML − réel
```

et des métriques globales (MAE, MAPE, biais) **ROD vs ML** sur les pilotes
hold-out. L’hypothèse métier : le modèle IA devrait faire mieux (ou au moins
être comparé objectivement aux règles fixes).

### Points d’accroche déjà dans le code

| Brique | Rôle aujourd’hui |
|--------|------------------|
| `rod_admin.simulate_hotel_trace` | sim ROD + gap vs réel 2026 |
| `model_eval.evaluate_model` | pred ML + gap vs réel (Σ/12, cible au choix) |
| Années train / eval | même esprit : 2023–25 train, 2026 hold-out |

### À brancher (futur)

1. Pour chaque pilote hold-out : appeler **les deux** moteurs avec les mêmes
   features d’entrée quand c’est possible (hôtel, mois 2026).
2. UI admin : onglet ou colonne **« ROD vs ML vs réel »** (pas seulement
   ROD vs réel ou ML vs réel séparément).
3. Garder les paramètres corner (mix, m_lin, sous-cat.) pour le bras ROD ;
   le bras ML utilise les features `model_data` (dont mix directeur si
   renseigné).

Jusque-là, les deux évaluations restent **séparées** (Simulateur ROD vs
Éval. modèle ML) — la fusion est le prochain jalon de validation.
