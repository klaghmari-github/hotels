# Simulateur ROD — admin vs user

## Deux applications, deux usages

| App | Entrée | Public | Données de ventes |
|-----|--------|--------|-------------------|
| **User** | `run_user.py` / `accor-user` (:5056) | Directeur d’hôtel | Souvent **aucune** → on estime, sans écart |
| **Admin** | `run_admin.py` / `accor-admin` (:5055) | Data / métier | **Hôtels pilotes** (ventes connues) → on estime **et** on évalue |

Le moteur de règles (revenus, coûts, reco) est le **même**
(`rod_admin.simulate_hotel_trace`). Seul le contexte change : validation
chiffrée côté admin grâce aux ventes historiques.

---

## Vocabulaire

| Terme | Sens |
|-------|------|
| **Hôtel pilote** | A des ventes sur des années **train** → entre dans la **référence** catégorie |
| **Hôtel cible** (ou **à cibler**) | Hôtel pour lequel on **simule** le corner (estimation CA / coûts / reco) |
| **Référence catégorie** | Moyennes des pilotes de la même catégorie de marque, années train uniquement |

On ne parle plus d’« hôtel client » ni de « traité comme nouveau » dans l’UI.

---

## Hôtel pilote

Un **hôtel pilote** a des **ventes sur des années précédentes**. Ces séries
servent de **référence** pour :

1. estimer les ventes d’un **hôtel cible** (même catégorie de marque) ;
2. estimer le « futur » et, quand ce futur est disponible (hold-out),
   **comparer** estimation et réel (écart admin uniquement).

Sans ventes passées, l’hôtel n’est pas pilote : l’app user peut quand même
simuler (scrape / défauts), sans score d’écart.

---

## Découpage **temporel** (pas par hôtel)

| Période | Années | Rôle |
|---------|--------|------|
| **Apprentissage / ref** | 2023, 2024, 2025 | Seules années pour la **référence** catégorie |
| **Évaluation** | 2026 (ex. mois 1–4) | Futur non vu → on estime puis on compare au réel |

Points clés :

* Exclusion / inclusion **temporelle** : 2026 hors ref, **pas** d’exclusion
  d’hôtel (pas de leave-one-out).
* Tous les pilotes de la catégorie avec ventes train entrent dans la moyenne.
* Peu d’hôtels en apprentissage = normal avec les données actuelles.
* Réel 2026 : `avg_true = somme(montant_ventes mois) / 12`.

Même esprit que le split ML (`_is_eval`) ; ici le moteur est **déterministe**
(règles Excel), pas XGBoost.

---

## Flux admin (onglet Simulateur ROD)

1. Choisir un **hôtel cible** (liste des codes avec ventes train).
2. Lire sa **catégorie de marque**.
3. **Référence** = moyennes de **tous** les pilotes de la catégorie sur
   2023–2025 (**pas 2026**) :
   - par année : avg mensuelle = Σ mois / 12 ;
   - moyenne multi-années par hôtel ;
   - moyenne entre hôtels de la catégorie.
4. Paramètres **corner** (m_lin, mix, sous-cat., chambres, TO, guests).
5. Règles ROD → CA, coûts, marge (SIMPLY / LIBERTY / CONNECTED) + reco.
6. **Écart** vs réel 2026 (Σ/12) si réel présent. Batch → MAE / MAPE / biais.

**Recalcul auto** (debounce) à chaque changement — pas de bouton Simuler.  
**Barre de progression** visible (style build modèle) pendant le calcul.

### Onglets résultats

| Onglet | Contenu |
|--------|---------|
| **CA (règles)** | Étapes ROD (hôtel cible → ref catégorie → R1–R4…) |
| **Coûts & marge** | Table marge + lignes de coûts (sans écart) |
| **Écart réel / sim** | CA simulé vs réel Σ/12 (séparé de l’étude CA/marge) |
| **Batch** | Tous les pilotes, métriques d’écart |

---

## Flux user (`run_user`)

* **Même moteur** : `simulate_hotel_trace` (ref catégorie train, corner,
  3 concepts + reco).
* N’importe quel code hôtel (scrape Accor si fiche absente).
* **Pas d’écart** hold-out (`include_gaps=False`).
* UI directeur : grands chiffres, onglets Résultat / Détail CA / Coûts & marge,
  recalcul auto.
* API : `POST /api/rod/simulate` (port 5056).

---

## API admin

| Méthode | Chemin | Rôle |
|---------|--------|------|
| GET | `/api/rod/meta` | labels sous-cat., défauts corner |
| GET | `/api/rod/pilots?year=` | pilotes train + `has_holdout` / réel éval |
| **GET\|POST** | `/api/rod/hotel/<code>/trace` | simu hôtel cible (UI = **POST**) + gaps si réel |
| GET | `/api/rod/eval?year=` | batch ; MAE / MAPE si réel hold-out |

Module : `src/accor/rod_admin.py`  
UI : `static/js/admin/rod-sim-panel.js`

Détail HTTP : [API_ADMIN.md](API_ADMIN.md) § Simulateur ROD.

---

## Formules

```
# référence (train uniquement, ex. 2023–2025)
avg_year(h, y) = sum(montant_ventes mois de y) / 12
ref_hotel(h)   = mean_y avg_year(h, y)
ref_cat(c)     = mean_h ref_hotel(h)   # tous les pilotes catégorie c

# réel hold-out (ex. 2026)
avg_true = sum(montant_ventes mois hold-out) / 12

# écart règles ROD
gap_rod = CA_sim_ROD_mensuel − avg_true

# R1 (hôtel cible)
facteur = clients_mois_cible / clients_mois_catégorie
```

---

## Roadmap — comparer règles ROD et modèle ML (même hold-out)

**Objectif plus tard** : pour le **même hôtel** et la **même année 2026** :

| Source | Sortie |
|--------|--------|
| **Simulateur ROD** | CA estimé mensuel |
| **Modèle ML** (intermédiaire ou final) | CA prédit mensuel (`model_eval` / Σ/12) |
| **Réel 2026** | `avg_true` = Σ mois / 12 |

Puis métriques **ROD vs ML** côte à côte. Aujourd’hui les deux évals restent
séparées (Simulateur ROD vs onglets Évaluation ML).
