# Front (JS / CSS)

Pas de bundler : modules ES natifs (`type="module"`).

---

## Shared (`static/shared/`)

Utilisé par admin **et** user.

| Fichier | Rôle |
|---------|------|
| `js/api.js` | `ApiClient` — fetch JSON, throw si non 2xx (`body.error`) |
| `js/dom.js` | `$`, `$$`, `on`, `escapeHtml`, `debounce`, helpers champs |
| `js/format.js` | `Format.euro`, pourcentages, nombres FR |
| `js/toast.js` | toasts |
| `js/loading.js` | overlay chargement (compteur d’appels imbriqués) |
| `css/tokens.css` | variables couleur / spacing partagées |

---

## Admin (`static/js/admin/` + `static/css/app.css`)

Entrée : `templates/index.html` → `app.js`

### Sidebar (ordre)

```
All / Pilotes
  → Simulateur ROD
  → Modèles intermédiaires  (Build · Explore · Évaluation)
  → Modèle final            (Build · Explore · Évaluation)
```

| Fichier | Classe / rôle |
|---------|----------------|
| `app.js` | `AdminApp` — compose tout, `window.AccorAdmin` |
| `state.js` | `AdminState` |
| `nav-controller.js` | sidebar datasets + ROD + intermédiaires + final |
| `table-renderer.js` | table éditable |
| `dataset-controller.js` | fetch page, save, rebuilds |
| `rod-sim-panel.js` | **Simulateur ROD** : hôtel cible, corner, onglets, barre progression |
| `model-build-panel.js` | Build **intermédiaires** multi-cibles |
| `model-explore-panel.js` | Explore intermédiaires (arbres, importances) |
| `model-eval-panel.js` | Éval ML (instance `intermediate` ou `final`, vues séparées) |
| `final-model-build-panel.js` | Build **modèle final** (stacking) |
| `final-model-explore-panel.js` | Explore modèle final |
| `tree-svg.js` | SVG arbre XGBoost |
| `constants.js` | icônes, datasets pinés |

### Panels / vues HTML

| Id | Contenu |
|----|---------|
| `#view-table` | datasets |
| `#view-rod-sim` | Simulateur ROD |
| `#view-model-build` / `#view-model-explore` / `#view-model-eval` | Intermédiaires |
| `#view-final-build` / `#view-final-explore` / `#view-final-eval` | Final |

Navigation : `#nav-rod-sim`, `#nav-model-build|explore|eval`,
`#nav-final-build|explore|eval`.

### Flux Simulateur ROD

Split **temporel** (apprend hors 2026, évalue 2026) — pas d’exclusion d’hôtel.  
**Pas de bouton Simuler** : recalcul auto (debounce).  
**Barre de progression** (`#rod-progress-card`, style build) pendant le calcul.

1. open → GET `/api/rod/meta` puis GET `/api/rod/pilots?year=`
2. **Hôtel cible** / corner / sous-cat. → **POST** `/api/rod/hotel/<code>/trace`
3. Onglets :
   - **CA (règles)** — étapes (dont « Hôtel cible »)
   - **Coûts & marge**
   - **Écart réel / sim** (séparé)
   - **Batch** — GET `/api/rod/eval`

Vocabulaire : **hôtel cible** / **à cibler** (pas « client »).  
Détail métier : [ROD_ADMIN.md](ROD_ADMIN.md).

### Flux modèles ML

**Intermédiaires**

- Build → POST `/api/model/build` + poll progress  
- Explore → `/api/model/list`, `…/explore`, arbres  
- Évaluation → `#view-model-eval` · `tier=intermediate` · listes `models/design`

**Final (stacking)**

- Build → POST `/api/model/final/build` + poll  
- Explore → `/api/model/final/*`  
- Évaluation → `#view-final-eval` · `tier=final` · listes `models/final/design`  

Les deux évaluations sont **des vues et états séparés** (pas le même écran).

---

## User (`static/user/`) — directeur

Entrée : `templates/user/index.html` → `modules/app.js` (`DirectorApp`).

**Même moteur** que l’admin (`POST /api/rod/simulate` → `simulate_hotel_trace`,
`include_gaps=False`, scrape si besoin). UX orientée **résultat** :

| Zone | Contenu |
|------|---------|
| Sidebar | hôtel, exploitation, corner, sous-cat. |
| Hero | solution recommandée (très grand) |
| Big metrics | CA / marge nette / coûts / marge produit |
| Onglets | **Résultat** · **Détail CA** · **Coûts & marge** |

Recalcul **auto** — pas de bouton Simuler.

---

## CSS admin (`static/css/app.css`)

Layout sidebar + main, table, chips, cards model, metrics-grid,
`.build-progress` (build + ROD), `.rod-progress-card`, overlay loading, toasts.

Tokens : `shared/css/tokens.css`.

---

## Debug navigateur

```js
window.AccorAdmin  // admin
window.RODUser     // user
```
