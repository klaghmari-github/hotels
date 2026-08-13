# Accor ROD — release 1.0.0

Simulateurs **sim_v1** / **sim_v2**, moteur **ml** (XGBoost conversion + CA), API et interfaces user / admin.

## Structure

```
release_1_0_0/
  data/files/input/     # ventes, hôtels, proximité, météo, référentiels
  data/files/output/    # eval LOO, full, extracts
  data/duckdb/main/     # main.duckdb (partagée)
  pipeline/             # YAML sim_v1, sim_v2, ml
  src/
    sim_v1/ sim_v2/ ml/ # services
    eval/               # évaluation full (in-sample)
    api/ web/ user/     # API, GUI, coûts/ROI
  models/super/         # modèles ml par solution
  doc/                  # documentation HTML + analyse
  run.py
```

## Commandes

```bash
cd release_1_0_0
.venv/bin/python run.py serve --port 5080
.venv/bin/python run.py sim-v1 --rebuild    # LOO + export
.venv/bin/python run.py sim-v2 --rebuild
.venv/bin/python run.py ml --rebuild        # chaîne ml_tc → ml_ca + LOO
.venv/bin/python run.py eval-full           # in-sample (pas de leave-out)
```

| URL | Rôle |
|-----|------|
| http://127.0.0.1:5080/ | Accueil |
| http://127.0.0.1:5080/user | Parcours estimation |
| http://127.0.0.1:5080/user/doc | Doc parcours |
| http://127.0.0.1:5080/admin | Studio (auth) |

## Moteurs

| Moteur | Principe |
|--------|----------|
| **sim_v1** | Règles Excel R1–R4 + marge ventes par coefficients F&B/Non F&B |
| **sim_v2** | Coefficients d’intensité sur obs+sim pilotes, restitution mix |
| **ml** | XGBoost : taux de conversion puis CA (par solution), features hôtel/proximité/météo/marque |

**ROI** = marge ventes (PV − PA) − coûts solution. Recommandation = meilleur ROI annuel.

## Évaluations

| Mode | Train | Test | Fichiers |
|------|-------|------|----------|
| **LOO** | Sans l’hôtel si ≥2 / solution | Observation | `eval_*_loo.xlsx` |
| **full** | Tous les pilotes (v2/ml : + sim) | Observations | `eval_*_full.xlsx`, `common/eval_full_compare.xlsx` |

Admin : onglets **LOO · comparaison** et **full · comparaison**.

## Documentation

| Doc | Contenu |
|-----|---------|
| [doc/index.html](doc/index.html) | Vue d’ensemble |
| [doc/sim_v1.html](doc/sim_v1.html) | Règles Excel R1–R4, lab interactif (pilote → cible) |
| [doc/sim_v2.html](doc/sim_v2.html) | Pipeline scénarios → dataset → coeffs → CA (lab live) |
| [doc/ml.html](doc/ml.html) | Chaîne ml_tc → pont → ml_ca (sans détail d’algo) |
| [doc/roi.html](doc/roi.html) | Marge, coûts solution, amortissement, ROI |
| [doc/reco.html](doc/reco.html) | Arbre de décision concept (éditable) |
| [doc/analyse.html](doc/analyse.html) | Interprétation LOO / full |
| [doc/sim_v2_scientific.html](doc/sim_v2_scientific.html) | Méthode sim_v2 |
| [doc/ARCHITECTURE.md](doc/ARCHITECTURE.md) | Couches package |

## Déploiement Adixon

| | |
|--|--|
| Script | [`scripts/deploy_to_adixon.sh`](scripts/deploy_to_adixon.sh) |
| Doc | [`doc/SYNC_ADIXON.md`](doc/SYNC_ADIXON.md) |
| Cible | `adixon@178.62.220.14:/var/www/rod-ia` → https://rod-ia.adixon-dev.fr |
| PM2 | `ecosystem.config.js` (`rod-ia-user` :8000 + redirect `/studio` :8001) |

```bash
# code + reload PM2 (usage courant)
./scripts/deploy_to_adixon.sh

# premier install / full sync
./scripts/deploy_to_adixon.sh --all

# simulation
./scripts/deploy_to_adixon.sh --dry-run
```

**Règle :** push GitHub libre ; **déploiement Adixon uniquement** sur consigne explicite (« déploie sur Adixon »). Les évolutions locales / GitHub n’impliquent **pas** de déploiement hébergement.
