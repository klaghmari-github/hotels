# Hotels / Accor ROD

| Dossier | Role |
|---------|------|
| **`accor/`** | **Package production** — interfaces admin + user, donnees propres, scrape hotel a la demande |
| `accor_1_0_0/` | Archive version complete (rebuilds massifs weather/geo/holidays, scrapes bulk, shards) |
| `archive/` | Anciens pipelines et sources brutes |

## Prod (`accor/`)

Package Python installable + venv :

```bash
cd accor
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

python run_admin.py    # :5055  (ou accor-admin)
python run_user.py     # :5056  (ou accor-user)
accor-validate-rod
```

Code package : `accor/src/accor/`.  
Doc detaillee : `accor/README.md`.
