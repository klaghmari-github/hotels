# ROD-IA — architecture refactorisée Flask + règles Excel + feature store

Base propre pour poursuivre le simulateur ROD avec une architecture maintenable.

Principes :

1. Source de vérité n°1 : les fichiers Excel ROD.
2. Source de vérité n°2 : consigne ROD / documentation fonctionnelle.
3. Les anciens scripts sont conservés en `legacy_original/`, mais ils ne sont pas considérés comme source de vérité.
4. Les constantes métier doivent être injectées depuis un référentiel Excel/recalculé, pas cachées dans le code.
5. Les POI doivent être calculés à 0.1, 0.2, 0.3, 0.4 et 0.5 km, pas 1–5 km.

## Structure

```text
app/
  server.py
  routes/
  domain/
    models/          dataclasses métier + état interdépendant hôtel
    rules/           règles revenus/coûts/recommandation traçables Excel
    services/        simulation, IA, optimisation, enrichissement, sales mix
    repositories/    lecture Excel + référentiels
  web/               interface HTML/CSS/JS à onglets
  data/raw/          déposer les Excel/CSV source
  data/reference/    référentiels constants versionnés/recalculés
  feature_store/     cache par hôtel
scripts/             extraction Excel + recalcul ventes
legacy_original/     anciens fichiers fournis, pour audit seulement
```

## Lancement

```bash
cd rod_ia_refactor_project
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.server
```

Puis ouvrir `http://127.0.0.1:5000`.

## Données à copier dans `app/data/raw/`

- `ROD - Simulateurs + détail des coûts.xlsx`
- `ROD - Paramètres & règles + projections nb. d'hôtels.xlsx`
- `001.queryVentes.csv` ou fichier de transactions enrichi
- récapitulatif ROD si utile

## Important

Le fichier `rod_reference_demo.json` met les références à zéro par défaut pour ne pas inventer de chiffres. Les formules/références doivent être chargées depuis Excel ou recalculées depuis les ventes pivots avant usage métier.
