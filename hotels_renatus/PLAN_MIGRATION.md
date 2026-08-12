# Plan de migration hotels → renatus

## 1. Compréhension renatus (maîtrise)

**renatus** = outil générique de flux de données (package `src/renatus/`), **sans**
métier hotels. Le métier vit dans un **projet consommateur** (ce dossier).

### Surfaces

| Surface | Rôle |
|---------|------|
| **core** | `ConnectionPipeline` + steps YAML → DuckDB |
| **cli** | `renatus` / `renatus-cli` |
| **api** | `renatus-api` |
| **gui** | `renatus-gui` (graphe Flux, Config, View/Track) |

### Composants (types)

| Famille | Types | Usage hotels |
|---------|-------|--------------|
| Datasets | `dataframe`, `table`, `view` | **prioritaire** (90 %+ des flux) |
| Execute | `execute_sql`, `execute_python`, `execute_shell` | INSERT LOO, scoring ML |
| Flow | `iterate`, `zone` | LOO, scénarios sim_v2, organisation |
| Auto | `flatzone`, `backzone`, … | vues d’organisation (optionnel) |

### Concepts clés

- **id** = stem fichier YAML (`t_sales.yaml` → id `t_sales`), immutable, dans `requires`
- **label** = libellé UI
- **name** = nom relation SQL (FROM …)
- **requires** = graphe de dépendances (ids)
- **mode** : `create_if_not_exists` | `create_or_replace`
- **Renatus (build)** d’un nœud ou d’une **zone** : part des feuilles, remonte le lineage selon besoin
- **zone** : dossier `flow/<zone>/` + membership `objects` ; modes `required_for_leaves` / `root_to_leaves`
- **iterate** : table scenarios → `step_view` 1 ligne → rejoue `target` (LOO, scénarios)

### Layout projet consommateur

```
projet/
  *.renatus.yaml     # db_path + flow_path
  flow/              # versionné (git)
    main.yaml        # zone principale
    main/
    sources.yaml + sources/
    build_sim_v1/ …
  input/             # sources (références ; ici symlink → release_1_0_0)
  data/              # duckdb runtime (gitignore)
```

**Règle** : le dépôt `renatus/` reste générique. Hotels = projet à part.

---

## 2. Architecture cible hotels (zones)

```
main  (zone principale = default)
├── sources              # Excel → tables communes
├── build_sim_v1         # params, refs, R1–R4, LOO v1
├── build_sim_v2          # sales, ranks, dataset, sim, restitution, LOO v2
├── build_ml             # rich features + training dataset
├── estimate_sim_v1      # 1 ligne leviers → CA / marge (règles Excel)
├── estimate_sim_v2       # 1 ligne leviers → pred restitution
└── estimate_ml          # 1 ligne features → score modèle
```

### Deux temps d’usage

| Temps | Zones | Action |
|-------|-------|--------|
| **Build offline** | `sources`, `build_*` | `Renatus` zone → matérialise datasets / coeffs / LOO |
| **Estimate online** | `estimate_*` | Input row (fichier ou table 1 ligne) → sortie prédiction |

Build une fois (ou quand les données changent). Estimate à chaque hôtel / scénario UI.

---

## 2.bis Estimation sim_v2 vs ML (logique métier)

Référence : même **solution** (SIMPLY / LIBERTY / CONNECTED).  
Entrée cible : leviers hôtel (chambres, TO, guests/chambre → clients/mois, m_lin) + **mix F&B (type)** + **mix gammes**.

### Taux de conversion

```
taux_conversion = nombre_ventes_par_mois / nombre_guests_par_mois
```

C’est le levier central qui relie **trafic clients** et **volume de ventes**.

### Rôle du modèle XGBoost (ML)

Apprend / prédit le **taux de conversion** à partir de :

- variables descriptives hôtel : proximité commerces / concurrence, plage, météo,  
  nb chambres, TO, guests/chambre, bars, salles de réunion, sport, etc.
- **brand**
- **mix F&B** et **mix gammes**

Sortie ML pure = **taux de conversion prédit** pour l’hôtel cible (dans son contexte).

### Chaîne estimate_sim_v2 (sans remplacer la conversion par le ML)

1. Prendre les lignes **observées + simulées** du **même solution**  
   (hôtels de modélisation / `t_dataset_pivot` + scénarios).
2. **Adapter** chaque ligne au **mix F&B + gammes** et **m_lin** de l’hôtel cible  
   (mêmes distributions cibles pour tous).
3. Pour chaque hôtel de modélisation, garder **son propre taux de conversion**  
   (issu de ses ventes / guests).
4. Estimer un **CA** par ligne (ventes × coefficients / panier moyen selon le modèle  
   de restitution — en pratique aujourd’hui : coeffs × guests_cible × m_lin × parts mix).
5. **Moyenne des CA** sur toutes ces lignes → **sortie estimation sim_v2**.

En une phrase :  
**sim_v2 estimate = moyenne des CA des hôtels de modélisation reconfigurés au mix + m_lin cibles, chacun avec son taux de conversion.**

### Chaîne estimate_ml

1. Même socle que sim_v2 (lignes solution, adaptation mix / m_lin).
2. Le ML fournit le **taux de conversion de l’hôtel cible**.
3. On **applique ce taux** (recalage) sur le CA de **chaque** hôtel de modélisation  
   **avant** la moyenne  
   (typiquement : `CA_i' = CA_i * (taux_cible_ML / taux_i)` ou équivalent ventes→CA).
4. **Moyenne des CA recalés** → **sortie estimation ML**.

En une phrase :  
**ML estimate = même moyenne sim_v2, mais conversion de chaque ligne ramenée au taux prédit pour la cible.**

### Lien avec le code release actuel

| Bloc | Fichiers / vues |
|------|-----------------|
| Lignes long mix + coeffs | `v_restitution_simulation_long`, `v_restitution_solution_coefficients` |
| Conversion par solution | `v_solution_conversion_rate` (moyen / pondéré) |
| Pred sim_v2 | `v_restitution_prediction_*` : `coeff × guests × m_lin × target_part` puis AVG |
| ML | XGB / super sur features rich + mix ; cibles ventes/marge (à aligner explicitement sur **taux_conversion** si pas déjà) |

La forme **coefficient moyenne** du SQL actuel est une **agrégation** de l’idée  
« reconfigurer chaque hôtel puis moyenner » ; la migration renatus doit  
**documenter et, si besoin, expliciter** l’étape conversion (sim_v2 = conversion  
source ; ML = conversion prédite cible) pour coller au métier ci-dessus.

### Zones renatus

| Zone | Entrée | Sortie |
|------|--------|--------|
| `build_sim_v2` | sales, scénarios | pivot, coeffs, lignes sim/obs |
| `build_ml` | rich + pivot | dataset train + modèle (artefacts) |
| `estimate_sim_v2` | 1 row hôtel + mix | CA moyen (conversion des peers) |
| `estimate_ml` | 1 row hôtel + features + mix | CA moyen (conversion ML cible) |

---

## 3. Mapping release_1_0_0 → zones

| Ancien chemin | Zone renatus | Contenu |
|---------------|--------------|---------|
| `pipeline/common/0_all_sources*` | `sources` | df/t hotel_*, clients, proximity, weather, holidays |
| `pipeline/common/1_web_views*` | `sources` | v_web_* |
| `pipeline/sim_v1/*` | `build_sim_v1` | pilots, hotel_params, R1–R4, LOO |
| `pipeline/sim_v2/*` | `build_sim_v2` | sales → ranks → dataset → sim → restitution → LOO |
| `pipeline/ml/*` | `build_ml` | rich + v_ml_training |
| *(nouveau)* | `estimate_sim_v1` | input + vue estimate R1–R4 |
| *(nouveau)* | `estimate_sim_v2` | input + restitution (phase B) |
| *(nouveau)* | `estimate_ml` | input + features + execute_python score (phase C) |

Services Python actuels (`SimV1Service`, `SuperModelService`, …) :
- **build** : remplacé par Renatus des zones `build_*`
- **estimate** : remplacé par Renatus `estimate_*` (+ python seulement pour ML inference)

---

## 4. Phases de migration

### Phase A — Squelette (fait dans ce dossier)

- [x] Projet `hotels_renatus/` hors package renatus
- [x] Zone `main` + 7 sous-zones
- [x] Conversion monocomposant YAML (`sql`→`script`, `iteration`→`iterate`)
- [x] Symlink `input/` → `release_1_0_0/data/files/input`
- [x] `estimate_sim_v1` SQL complet (R1–R4 aligné Excel)
- [x] Stubs `estimate_sim_v2` / `estimate_ml`

### Phase B — Build parity

1. Ouvrir `hotels_renatus.renatus.yaml` dans `renatus-gui`
2. `Renatus` zone **sources** puis **build_sim_v1** ; comparer LOO à `eval_sim_v1_loo.xlsx`
3. Idem **build_sim_v2** (itération scénarios + LOO)
4. Idem **build_ml** (`t_rich_data`, `v_ml_training_dataset`)
5. Corriger requires croisés (ex. `t_sales` utilisé par web/ml)

### Phase C — Estimate parity

1. **sim_v1** : brancher UI sur `v_estimate_sim_v1` (déjà SQL) ; valider vs `run_rules_r1_r4`
2. **sim_v2** : porter `v_restitution_prediction_*` sur `df_estimate_input_v2`
3. **ml** : `execute_python` charge modèles `release_1_0_0/models/super/` et écrit table résultats

### Phase D — Coupure services legacy

1. API hotels appelle renatus core (`process_with_requires`) au lieu de `src/sim_v1/service.py`
2. Garder `release_1_0_0` en lecture data/models jusqu’à stabilisation
3. Docs + tests renatus côté projet hotels (petits fixtures, pas full parc)

---

## 5. Comment « Renatus » une zone

```bash
# depuis le repo renatus (venv)
cd /path/to/renatus
source .venv/bin/activate
renatus-gui /path/to/hotels_renatus/hotels_renatus.renatus.yaml
```

Dans le GUI :

1. Select zone **sources** → Renatus (View)
2. Select **build_sim_v1** → Renatus
3. Select **estimate_sim_v1** → Renatus → View `v_estimate_sim_v1`

CLI :

```bash
renatus data/main.duckdb flow/ --project hotels_renatus.renatus.yaml
# puis p_table_view / process sur un id
```

Python :

```python
from renatus.pipeline import ConnectionPipeline
cp = ConnectionPipeline("data/main.duckdb", "flow/")
cp.process_with_requires("v_estimate_sim_v1")  # remonte t_pilot_defaults, etc.
print(cp.table_view("v_estimate_sim_v1").df())
cp.close()
```

---

## 6. Principes d’implémentation (datasets d’abord)

| Besoin | Composant |
|--------|-----------|
| Lire Excel/CSV | `dataframe` |
| Matérialiser | `table` mode `create_if_not_exists` ou `create_or_replace` |
| Transformer / règles | `view` (chaîne SQL) |
| LOO / scénarios | `iterate` + `execute_sql` INSERT résultats |
| Scoring ML | `execute_python` (session notebook si besoin) |
| Organisation | `zone` |

Éviter Python pour R1–R4 et restitution purement SQL.

---

## 7. Inventaire généré

Voir dossiers `flow/<zone>/` : **133 composants** au moment de la génération.

| Zone | ~nb | Rôle |
|------|-----|------|
| sources | 22 | données communes |
| build_sim_v1 | 24 | simulateur v1 offline |
| build_sim_v2 | 71 | simulateur v2 offline |
| build_ml | 8 | datasets ML |
| estimate_sim_v1 | 3 | inference v1 |
| estimate_sim_v2 | 2 | inference v2 (stub) |
| estimate_ml | 3 | inference ml (stub + python placeholder) |

---

## 8. Risques / points d’attention

1. **Requires croisés zones** : supportés (id global) ; le build estimate remonte `t_pilot_defaults` dans `build_sim_v1`.
2. **`v_loo_step`** : vue dynamique iterate, pas un YAML — ne pas la mettre en requires.
3. **Chemins `file`** : relative au project_dir ; `input/` symlink.
4. **Parity LOO** : revalider ca_10 / R3 (correctifs Excel déjà dans release).
5. **ML** : dernier à migrer (artefacts `.json`/`.cbm` hors DuckDB).
6. **Ne pas polluer le repo renatus** avec data hotels (règle F0011 / package générique).

---

## 9. Critères de fin de migration

- [ ] Zone `build_sim_v1` produit les mêmes LOO metrics que release
- [ ] Zone `build_sim_v2` produit pivot + LOO alignés
- [ ] Zone `build_ml` produit `v_ml_training_dataset` / `t_rich_data`
- [ ] `estimate_sim_v1` = `predict_from_levers` (écarts < 1 c€)
- [ ] `estimate_sim_v2` / `estimate_ml` branchés UI user
- [ ] Plus d’appel obligatoire à `src/sim_v1|sim_v2|ml` pour le chemin nominal
