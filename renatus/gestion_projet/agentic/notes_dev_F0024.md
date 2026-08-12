# Notes F0024 — tests composant iteration

## Architecture du scenario

```
df_sales (xlsx) → t_sales
t_scenarios (regions)
t_results (sink create_if_not_exists)
x_agg (execute: INSERT filtre v_step.region)
i_run (iteration sequential, order_by region)
v_final (view sur t_results)  ← preuve de fin
```

## Attributs iteration verifies

- type, execution=sequential
- scenarios, step_view, target, order_by
- requires (sans step_view dans requires)

## Regle

`step_view` (v_step) est TEMP VIEW dynamique — jamais dans le YAML requires.
