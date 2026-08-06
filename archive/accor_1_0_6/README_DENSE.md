# Reseau dense de regression

Ce module teste un reseau dense residuel sur le meme dataset et avec les memes entrees que XGBoost et la restitution V2.

## Lancement

```python
from main import main
from ml_dense import DenseConfig, DenseWorkflow

simulation = main()
cp = simulation["cp"]

workflow = DenseWorkflow(
    cp=cp,
    config=DenseConfig(
        optuna_trials=50,
        cv_splits=5,
    ),
)

result = workflow.run()

display(result["training_summary"])
display(result["loo_predictions"])
display(result["loo_metrics"])
```

## Principe de validation

Toutes les simulations de l'hotel laisse de cote sont exclues de l'apprentissage. Seule son observation initiale est predite pour l'evaluation.
