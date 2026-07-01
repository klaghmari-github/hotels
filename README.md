# ROD-IA — Simulateur retail Accor

Application web de simulation ROD (règles Excel) comparée à une prédiction IA,
avec feature store par hôtel, registre d'identité pour les jointures, et
convention de nommage ML ``d_`` (descriptives) / ``t_`` (targets).

## Architecture

```text
rod_ia/
  config/           Configuration (chemins, POI 0.1–0.5 km)
  domain/
    models/         Dataclasses métier (HotelIdentity, StoreConfiguration…)
    rules/          Règles revenus / coûts / recommandation (traçables Excel)
    repositories/   Registre identité, feature store, références
    services/       Simulateur, enrichissement, ML, optimiseur
  pipelines/        ETL (dataset ML, moyennes mensuelles, %)
  api/              Flask (routes + injection de dépendances)
  web/              Interface HTML/CSS/JS
data/
  reference/        hotel_identity_registry.json, constantes ROD
  processed/        Datasets ML générés (X_descriptive.csv, y_targets.csv)
sources/raw/        Fichiers sources immuables (Excel, CSV ventes)
```

## Principes

1. **Excel ROD** = source de vérité n°1
2. **Jointures** uniquement via `hotel_id` (registre d'identité) — jamais sur le nom brut
3. **Targets ventes** = moyenne mensuelle historique + répartitions % (3 niveaux)
4. **ML** : colonnes `d_*` en entrée, `t_*` en sortie ; champs informatifs exclus du fit
5. **POI** aux rayons 0.1, 0.2, 0.3, 0.4, 0.5 km

## Installation

```bash
cd /chemin/vers/hotels
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Lancement

```bash
python run_server.py
# → http://127.0.0.1:5000
```

## Pipelines données

```bash
# Recalculer références ventes (moyennes + %)
python scripts/recompute_sales_references.py

# Construire dataset ML (d_* / t_* + manifeste)
python -m rod_ia.pipelines.build_ml_dataset

# Stub extraction Excel (à compléter)
python scripts/extract_excel_rules.py
```

## Artefacts ML

Copier les modèles entraînés depuis le prototype legacy :

```bash
cp old/artifacts/* rod_ia/artifacts/
```

## Tests

```bash
pytest tests/ -q
```

## Documentation

- Analyse architecture : `docs/analyse_architecture_cible_rod_ia.md`
- Audit fonctionnel : `docs/documentation_fonctionnelle_audit_ROD_v2.md`
- Spec ZIP refactor : `docs/documentation_zip_architecture_rod_ia.md`

## API

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/health` | Santé service |
| GET | `/api/registry` | Liste hôtels canoniques |
| POST | `/api/enrich` | Géocode + POI + météo → feature store |
| POST | `/api/simulate` | ROD + IA en parallèle |
| POST | `/api/optimize` | Meilleure config sous contraintes |
| GET | `/api/hotel/<hotel_id>` | Profil + enrichissement + saisies |
| POST | `/api/hotel/<hotel_id>/inputs` | Sauvegarder saisies directeur |