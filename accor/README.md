# Simulateur Accor et modeles XGBoost

## Contenu

- `main.py` : generation parallele des simulations de modelisation et restitution V2.
- `ml_xgboost.py` : construction du dataset ML, optimisation Optuna, entrainement XGBoost et evaluation Leave-One-Hotel-Out.
- `config/8_ml_dataset_pipeline.yaml` : vue d'apprentissage limitee aux variables de la restitution V2.
- `main.ipynb` : sequence d'execution complete.

## Variables descriptives

- `solution`
- `hotel_nb_chambres`
- `hotel_to_annuel`
- `hotel_guests_per_chambre`
- `metres_lineaires`
- toutes les colonnes `type_*_part_natures`
- toutes les colonnes `gamme_*_part_natures`

`hotel_code` et `scenario_id` ne sont pas utilises comme variables d'apprentissage.

## Cibles

- `montant_ventes_par_mois`
- `montant_marge_par_mois`
- `montant_marge_selon_coef_par_mois`

Un modele XGBoost distinct est entraine pour chaque cible.

## Validation

Pendant l'optimisation, `GroupKFold` maintient toutes les simulations d'un hotel dans le meme fold. Seule la ligne d'observation des hotels de validation est utilisee pour calculer le score.

Pendant l'evaluation Leave-One-Hotel-Out :

1. toutes les simulations de l'hotel evalue sont retirees de l'apprentissage ;
2. le modele est entraine sur les autres hotels ;
3. seule l'observation initiale de l'hotel exclu est predite ;
4. la prediction est comparee a la valeur mensuelle observee.

## Installation

```bash
pip install -r requirements_ml.txt
```

## Execution

```python
from main import main
from ml_xgboost import MLConfig, XGBoostWorkflow

simulation = main()
cp = simulation["cp"]

workflow = XGBoostWorkflow(
    cp,
    MLConfig(
        optuna_trials=80,
        cv_splits=5,
    ),
)
result = workflow.run()
```

## Artefacts

- `models/xgboost/*.json` : modeles finaux.
- `models/xgboost/*_metadata.json` : variables, parametres et score CV.
- `reports/xgboost/optuna/` : etudes et essais Optuna.
- `reports/xgboost/leave_one_hotel_out.xlsx` : predictions et metriques ML.
- `reports/xgboost/feature_importance.xlsx` : importance par gain.
- `reports/xgboost/ml_vs_sim_v2.xlsx` : comparaison avec les methodes A et B si `t_loo_results` existe.
