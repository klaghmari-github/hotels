# hotels_renatus

Projet **consommateur** de l’outil [renatus](../renatus/) pour les flux
**hotels** (sim_v1, sim_v2, ml).

Le package `renatus` reste générique. Ici : zones + composants métier.

## Démarrage

```bash
cd ../renatus
source .venv/bin/activate
renatus-gui ../hotels_renatus/hotels_renatus.renatus.yaml
```

## Zones (sous main)

| Zone | Rôle |
|------|------|
| `sources` | Excel → tables communes |
| `build_sim_v1` | Datasets + LOO simulateur v1 |
| `build_sim_v2` | Datasets + simulation + LOO v2 |
| `build_ml` | Rich + training ML |
| `estimate_sim_v1` | Ligne leviers → CA / marge |
| `estimate_sim_v2` | Ligne leviers → pred v2 |
| `estimate_ml` | Ligne → score ML |

Build offline : Renatus `sources` puis `build_*`.  
Estimate : éditer `input_estimate/estimate_input_*.xlsx` puis Renatus `estimate_*`.

## Docs

Voir [PLAN_MIGRATION.md](PLAN_MIGRATION.md) (maîtrise renatus + plan détaillé).
