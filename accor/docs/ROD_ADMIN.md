# Simulateur ROD (admin)

Zone **Simulateur ROD** dans l’admin (`:5055`), entre les datasets (All / Pilotes)
et la section **Modèle**.

Objectif : rejouer les **mêmes règles Excel** que le parcours directeur
(`user.rules.*`), avec le détail des étapes et des chiffres, sur les
**hôtels pilotes** (ceux qui ont des ventes sur l’année choisie, souvent 2026).

Code : `src/accor/rod_admin.py`  
UI : `static/js/admin/rod-sim-panel.js` + vue `#view-rod-sim`  
API : `/api/rod/*` (voir [API_ADMIN.md](API_ADMIN.md))

---

## Sidebar

```
All
Pilotes
────────────
Simulateur ROD
  · Simulateur ROD     (vue unique, 3 onglets internes)
────────────
Modèle                 ← singulier
  · Model Build
  · Model Explore
  · Éval. modèle ML    ← XGBoost (pas ROD)
```

Ne pas confondre :

| Zone | Rôle |
|------|------|
| **Simulateur ROD** | Règles déterministes Excel : CA, coûts, marge, écart vs réel |
| **Éval. modèle ML** | Perf XGBoost (moyenne mensuelle Σ/12 sur hold-out) |

---

## Onglets internes

### 1 · Prédiction ventes

Pour un hôtel pilote + un concept (SIMPLY / LIBERTY / CONNECTED) :

Enchaînement affiché étape par étape (formule + valeurs + CA F&B / N-F&B) :

1. **Entrées hôtel** — n, TO, guests, clients jour/mois, m_lin, mix  
2. **Référence pilote concept** — pivots `rod_reference.json`  
3. **Impact TO** — ΔTO × ~9,23 € HT / point  
4. **R1 clients** — CA × (clients_hôtel / clients_pilote)  
5. **R2 mix** — pas de 10 % vs mix pilote  
6. **R3 catégories** — besoins clients vs baseline coefs  
7. **R4 m_lin** — écart mètres linéaires  
8. **Marge produit** — CA − CA/coef (F&B et N-F&B)

KPI : CA HT / mois, marge produit, coûts, marge nette.

### 2 · Marge & coûts

Tableau des 3 concepts :

- CA HT mensuel  
- Marge produit  
- Techno / annexes / agencement  
- Coût total mensuel  
- Marge nette  
- Capex  

+ détail des **lignes de coûts** du concept sélectionné  
(`cost_lines` techno / annexes / agencement).

Formule : `marge_nette = marge_produit − coûts_mensuels`.

### 3 · Évaluation (sim vs réel)

Sur **tous** les pilotes de l’année :

- réel : `avg_monthly_true = somme(montant_ventes mois dispo) / 12`  
- simulé : CA mensuel ROD par concept  
- écart = simulé − réel (€ et %)  
- colonnes SIMPLY / LIBERTY / CONNECTED + concept **recommandé**  
- métriques globales sur le concept reco : MAE, RMSE, biais, MAPE  

---

## Pilotes

Hôtels présents dans `hotel_sales_data` pour l’année (ex. 2026, mois 1–4).

Liste via `GET /api/rod/pilots?year=2026`.

Contexte hôtel : `HotelContextBuilder` (hotel_data + model_data), même
hydratation que le user.

---

## API (résumé)

| Méthode | Chemin | Rôle |
|---------|--------|------|
| GET | `/api/rod/pilots?year=` | liste pilotes + Σ ventes /12 |
| GET | `/api/rod/hotel/<code>/trace?year=` | étapes ventes + coûts + marge (3 concepts) |
| GET | `/api/rod/eval?year=` | batch écart sim vs réel |

---

## Moteurs réutilisés

- `user.rules.revenue.RevenueRules`  
- `user.rules.costs.CostRules`  
- `user.services.orchestrator.SimulationOrchestrator`  
- `user.services.hotel_context.HotelContextBuilder`  
- `user.reference.RodReference` (`data/rod_reference.json`)

Le traçage des étapes ventes rejoue la chaîne dans `rod_admin._sales_steps`
pour exposer chaque intermédiaire (pas seulement le résultat final).

Voir aussi [ROD_RULES.md](ROD_RULES.md) pour le détail métier des formules.
