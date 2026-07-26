# Accor ROD — package Python

Application **prod** : Data & Model Studio (admin) + simulateur directeur (user).

Le code est un **package installable** `accor` (layout `src/`).  
Les donnees et assets restent a la racine du projet.

## Structure

```
accor/                          # racine projet
  pyproject.toml                # metadata + dependances
  requirements.txt              # miroir pour pip -r
  .venv/                        # environnement virtuel (local)
  run_admin.py                  # entrees fines
  run_user.py
  data/                         # Excel + rod_reference (runtime)
  models/                       # design + deploy
  static/                       # JS/CSS admin + user
  templates/                    # HTML
  src/
    accor/                      # PACKAGE Python
      __init__.py               # PROJECT_ROOT, DATA_DIR, MODELS_DIR
      app.py                    # Flask admin
      data_io.py, store.py, schemas.py, …
      brand_category.py, impute_model.py, …
      user/                     # simulateur ROD
      scrape_accor/             # scrape fiche hotel unitaire
```

Imports : `from accor.store import get_frame`, `from accor.user.app import app`, etc.

Chemins runtime (independants de l endroit d ou on lance) :

| Constante | Emplacement |
|-----------|-------------|
| `accor.PROJECT_ROOT` | racine projet (`…/hotels/accor`) |
| `accor.DATA_DIR` | `PROJECT_ROOT/data` |
| `accor.MODELS_DIR` | `PROJECT_ROOT/models` |
| `accor.STATIC_DIR` | `PROJECT_ROOT/static` |
| `accor.TEMPLATES_DIR` | `PROJECT_ROOT/templates` |

## Environnement virtuel

```bash
cd accor

# creer le venv (une fois)
python3 -m venv .venv
source .venv/bin/activate

# installer le package en editable + dependances
pip install -U pip setuptools wheel
pip install -e .

# verifier
python -c "import accor; print(accor.__version__, accor.DATA_DIR)"
accor-validate-rod
```

Desactiver : `deactivate`.

## Lancer les apps

```bash
source .venv/bin/activate

# Admin  :5055
python run_admin.py
# ou
accor-admin

# User   :5056
python run_user.py
# ou
accor-user
```

## Commandes utiles

| Commande | Role |
|----------|------|
| `pip install -e .` | (re)installe le package en dev |
| `accor-admin` | Flask admin |
| `accor-user` | Flask user / simulateur |
| `accor-validate-rod` | tests regles revenus / couts / reco |
| `python -m accor.user.validate_rod` | idem |

## Contenu prod (rappel)

- Donnees preconstruites sous `data/` (pas de rebuilds massifs UI)
- Ventes raw + `sales_prep`
- Scrape hotel a la demande (`scrape_accor` + `user.services.hotel_fetch`)
- Imputation prediction par categorie de marque (`brand_category` + `impute_model`)
- Simulateur ROD (`user.rules.*`)
- Admin **Evaluation** : perf modele sur l annee incomplete (defaut 2026) ;
  cible selectionnable (defaut principale) ;
  metrique = moyenne mensuelle hotel = somme(mois disponibles) / 12, pred vs reel
  (`model_eval.py`, API `/api/model/eval`, onglet Evaluation)

Archive complete (pipelines bulk) : `../accor_1_0_0/`.
