# Simulation parallele Accor

## Structure

- `main.py` : moteur de pipeline, generation des scenarios et orchestration parallele.
- `main.ipynb` : notebook de lancement.
- `config/` : pipelines YAML.
- `data/` : placer `hotel_sales_raw_extended_data.xlsx`.
- `duckdb/workers/` : bases DuckDB persistantes des buckets.

## Lancement

```python
from main import main

simulation = main()
```

Par defaut, le nombre de buckets et de workers simultanes est calcule avec :

```text
max(1, nombre de vCPU - 2)
```

Pour imposer un nombre fixe de buckets, modifier `tasks` dans
`config/4_simulation_pipeline.yaml`.

Les resultats deja calcules dans la base partagee ou dans les bases workers
sont conserves et repris lors d'une nouvelle execution.


## Metres lineaires simules

Les metres lineaires ne sont plus figes pendant les scenarios. Pour chaque hotel, le moteur calcule d abord la place moyenne occupee par une nature dans la configuration observee :

```text
metres_lineaires_par_nature = metres_lineaires_observes / nombre_natures_observees
```

Puis, pour chaque scenario :

```text
metres_lineaires = metres_lineaires_par_nature * nombre_natures_restantes
```

La valeur peut donc differer d un hotel a l autre pour une meme nature. Si toutes les natures sont retirees, les metres lineaires simules valent 0.


## Restitution et evaluation Leave-One-Out

```python
from main import main, run_restitution, run_leave_one_out

simulation = main()
cp = simulation["cp"]

predictions = run_restitution(
    cp,
    hotel_nb_chambres=100,
    hotel_to_annuel=0.5,
    hotel_guests_per_chambre=1.0,
    metres_lineaires=10.0,
    type_mix={"F&B": 0.7, "NON F&B": 0.3},
    gamme_mix={"G1": 0.3, "G2": 0.2, "G3": 0.2, "G8": 0.1, "G9": 0.1, "G10": 0.05, "G15": 0.05},
)

loo = run_leave_one_out(cp, rebuild=True)
```

La methode A moyenne toutes les predictions de variables. La methode B moyenne d'abord les predictions par famille (type et gamme), puis moyenne les familles.
