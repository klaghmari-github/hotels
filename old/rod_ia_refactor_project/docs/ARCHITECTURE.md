# Architecture fonctionnelle et technique proposée

## Objectif

Construire une application web ROD maintenable qui relie :

1. les informations saisies par le directeur d'hôtel ;
2. les enrichissements automatiques météo / POI ;
3. les règles Excel ROD ;
4. les constantes recalculables depuis les ventes pivots ;
5. la prédiction IA ;
6. l'optimisation sous contraintes.

## Flux web

```text
index.html / script.js
  -> JSON typé
  -> Flask /api/simulate
  -> RodSimulationRequest
  -> RodSimulator + AIRodRevenuePredictor
  -> JSON résultat
  -> affichage KPI + graphique mensuel
```

## Flux enrichissement

```text
Nom hôtel + adresse + ville
  -> geocode_hotel
  -> lat/lon
  -> fetch_weather_12_months
  -> fetch_poi 0.1-0.5 km
  -> compute_poi_features + nearest competitors
  -> feature_store/hotels/<hotel_id>/enriched.json
```

## Dataclasses principales

- `HotelIdentity` : nom, ville, adresse, marque.
- `HotelOperatingState` : variables dépendantes avec getters/setters.
- `StoreConfiguration` : concept, mètres linéaires, mix, contraintes.
- `RodSimulationRequest` : objet complet envoyé au simulateur.
- `SimulationResult` : résultat mensuel/annuel, coûts, marge, ROI, warnings, trace.

## Règles et traçabilité

Chaque règle doit progressivement recevoir :

- id de règle ;
- classe/méthode Python ;
- workbook Excel ;
- feuille ;
- cellules ;
- formule Excel ;
- description métier ;
- statut de validation.

La classe `RuleTrace` est prévue pour ça.

## Ce qui est volontairement laissé à zéro

`rod_reference_demo.json` ne contient pas de vrais chiffres. C'est volontaire :
aucune constante métier ne doit être inventée. Les chiffres doivent venir :

1. de l'Excel ;
2. ou du recalcul depuis les ventes pivots ;
3. ou d'une hypothèse explicitement validée.

## Prochaines étapes

1. Copier les Excel dans `app/data/raw/`.
2. Lancer `scripts/extract_excel_rules.py`.
3. Mapper les formules Excel vers `revenue_rules.py`, `cost_rules.py`, `recommendation_rules.py`.
4. Recalculer les références avec `scripts/recompute_sales_references.py`.
5. Brancher le modèle XGBoost réel dans `app/artifacts/`.
6. Ajouter des tests unitaires qui comparent Python vs Excel sur quelques scénarios pivots.
