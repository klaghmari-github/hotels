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
| `js/toast.js` | toasts (host multi admin ou élément unique user) |
| `js/loading.js` | overlay chargement avec compteur d’appels imbriqués |
| `css/tokens.css` | variables couleur / spacing partagées |

---

## Admin (`static/js/admin/` + `static/css/app.css`)

Entrée : `templates/index.html` → `app.js?v=…`

### Sidebar (ordre)

1. **All** / **Pilotes** — datasets Excel  
2. **Simulateur ROD** — règles Excel, trace pilotes  
3. **Modèle** (singulier) — Build / Explore / Éval. ML  

| Fichier | Classe / rôle |
|---------|----------------|
| `app.js` | `AdminApp` — compose tout, `window.AccorAdmin` |
| `state.js` | `AdminState` — dataset courant, page, dirty, panel |
| `nav-controller.js` | sidebar datasets + ROD + Model Build / Explore / Eval |
| `table-renderer.js` | table éditable, sélection, dirty cells |
| `dataset-controller.js` | fetch page, save, add/delete, rebuilds |
| `rod-sim-panel.js` | **Simulateur ROD** : corner, ventes, marge, batch éval temporelle |
| `model-build-panel.js` | params XGB, grille, barre progression réelle |
| `model-explore-panel.js` | structure modèle (importances, arbres) — pas de scores métier |
| `model-eval-panel.js` | **éval ML** XGBoost (Σ/12) |
| `tree-svg.js` | layout + SVG arbre XGBoost |
| `constants.js` | icônes, datasets pinés, map rebuilds |

### Panels / vues HTML

Ids principaux dans `index.html` :

- `#view-table` — datasets  
- `#view-rod-sim` — Simulateur ROD (onglets ventes / marge / eval)  
- `#view-model-build`  
- `#view-model-explore`  
- `#view-model-eval` — Éval. modèle ML  

Navigation : `#nav-rod-sim`, `#nav-model-build`, `#nav-model-explore`,
`#nav-model-eval`.

### Flux dataset

1. `loadDatasets` → GET `/api/datasets`
2. clic onglet → GET `/api/datasets/<id>?page&q`
3. édition cellule → dirty map dans state
4. Sauvegarder → PUT `/api/datasets/<id>/rows`
5. Rebuild (si dispo) → POST `/api/datasets/.../rebuild`

### Flux Simulateur ROD

Split **temporel** (apprend hors 2026, évalue 2026) — pas d’exclusion d’hôtel.
**Pas de bouton Simuler** : recalcul auto (debounce) dès qu’un paramètre change.

1. open → GET `/api/rod/meta` puis GET `/api/rod/pilots?year=`
2. hôtel / corner / sous-cat. → **POST** `/api/rod/hotel/<code>/trace` (auto)
3. Onglets séparés :
   - **CA (règles)** — étapes ROD uniquement
   - **Coûts & marge** — étude économique (sans écart)
   - **Écart réel / sim** — validation vs ventes réelles (Σ/12)
   - **Batch** — GET `/api/rod/eval` au premier affichage de l’onglet

Détail métier : [ROD_ADMIN.md](ROD_ADMIN.md).

### Flux modèles ML

- Build : POST build → poll `/api/model/build/progress` (manuel puis grid)
- Explore : list + explore + tree/importance (structure uniquement)
- Éval ML : meta → POST `/api/model/eval` → métriques Σ/12

---

## User (`static/user/`) — directeur

Entrée : `templates/user/index.html` → `modules/app.js` (`DirectorApp`).

**Même moteur** que l’admin (`POST /api/rod/simulate` → `simulate_hotel_trace`,
`include_gaps=False`, scrape si besoin). UX orientée **résultat** :

| Zone | Contenu |
|------|---------|
| Sidebar | hôtel (search), exploitation, corner (m_lin / mix), sous-cat. |
| Hero | solution recommandée (très grand) |
| Big metrics | CA / marge nette / coûts / marge produit |
| Onglets | **Résultat** (3 cartes) · **Détail CA** · **Coûts & marge** |

Recalcul **auto** (debounce) — pas de bouton Simuler.  
Legacy wizard modules (`stepper.js`, `simulation-panel.js`…) plus utilisés par
l’entrée principale.

---

## CSS admin (`static/css/app.css`)

Layout sidebar + main, table, chips, cards model, metrics-grid,
couleurs pos/neg pour tables eval, overlay loading, toasts.

Tokens : importer / s’appuyer sur `shared/css/tokens.css` quand présent.

---

## Debug navigateur

```js
// admin
window.AccorAdmin.state
window.AccorAdmin.modelEval.lastResult

// user
window.RODUser
```
