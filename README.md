# Hotels / Accor ROD

| Dossier | Role |
|---------|------|
| **`accor/`** | **Package production** — interfaces admin + user, donnees propres, scrape hotel a la demande |
| `accor_1_0_0/` | Archive version complete (rebuilds massifs weather/geo/holidays, scrapes bulk, shards) |
| `archive/` | Anciens pipelines et sources brutes |

## Prod

```bash
cd accor
pip install -r requirements.txt
python run_admin.py   # :5055
python run_user.py    # :5056
```

Doc detaillee : `accor/README.md`.
