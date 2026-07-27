# Simulateur Excel ROD

Nouvelle vue admin calquée sur
`archive/sources/raw/ROD - Simulateurs + détail des coûts.xlsx`.

**Ne remplace pas** le [Simulateur ROD](ROD_ADMIN.md) (référence par catégorie
de marque + écart temporel 2026). Les deux coexistent.

---

## Différence clé

| | Simulateur ROD (existant) | **Simulateur Excel** (nouveau) |
|--|---------------------------|--------------------------------|
| Référence | Pilotes de la **même catégorie** de marque | Pilotes de la **même solution** |
| Onglets | CA / marge / écart / batch | **SIMPLY · LIBERTY · CONNECTED** |
| Layout | Formulaire + résultats | **2 colonnes** type Excel |
| Commentaires | Courtes formules | Textes Excel (R1–R4, coûts, amort) |

### Mapping pilotes → solution

Fichier : `data/rod_pilot_concepts.json` (issu des feuilles
`REVENUS - MIX & MARGES` et `REVENUS - IMPACT TO`).

| Solution | Pilotes | Codes |
|----------|---------|-------|
| SIMPLY | IBB NICE | `H2075` |
| LIBERTY | MER BOUL + NOV MEG (moyenne) | `H6188`, `HB5I0` |
| CONNECTED | MER MONT | `H0373` |

Si plusieurs hôtels pour une solution → **moyenne** des paramètres ;
CA F&B / N-F&B de base = pivots Excel (`rod_reference.json`).

---

## Layout UI

```
┌──────────────────────────┬──────────────────────────┐
│ MOYENNE RESULTATS        │ SIMULATEUR               │
│ PILOTES {SOLUTION}       │ Hôtel désigné            │
│ (params + CA base)       │ (règles 1→4 + coûts)     │
└──────────────────────────┴──────────────────────────┘
```

Colonne **gauche** : référence pilote (comme E120 = E34 dans l’Excel —
CA base, sans rejouer R2–R4).  
Colonne **droite** : projection avec le moteur `RevenueRules` / `CostRules`
et la référence de **cette** solution.

---

## API

| Route | Rôle |
|-------|------|
| `GET /api/rod/excel/meta` | Commentaires, besoins, mapping, défauts |
| `GET /api/rod/excel/pilots` | Moyennes par solution |
| `POST /api/rod/excel/simulate` | Dual-colonne pour les 3 solutions |

Body simulate : `hotel_code`, `m_lin`, `mix_fb`, `client_needs`,
`nb_chambres`, `taux_occupation`, `guests_per_chambre`.

---

## Code

* Backend : `src/accor/rod_excel_sim.py`
* Front : `static/js/admin/rod-excel-panel.js`
* Template : `#view-rod-excel` dans `templates/index.html`
