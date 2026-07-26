# Règles ROD (simulateur)

Moteur déterministe calqué sur l’Excel simulateur. Code sous
`src/accor/user/rules/` + orchestration `services/`.

Séparation volontaire :

- **revenus** (`RevenueRules`) — peut un jour être remplacé par un modèle  
- **coûts** (`CostRules`) — barèmes stables  
- **reco** (`RecommendationRules`) — filtre + meilleur net  

---

## Indicateurs d’entrée

Produits par `HotelContextBuilder` / saisie wizard :

| Indicateur | Formule / source |
|------------|------------------|
| clients/jour | nb_chambres × TO × guests_per_chambre |
| clients/mois | clients/jour × 30.5 |
| mix F&B / N-F&B | historique model_data ou saisie |
| m_lin | corner hôtel ou pivot concept |
| client_needs | booléens catégories (règle 3) |
| CA pilote | rod_reference par concept |

---

## Chaîne revenus

Ordre dans `RevenueRules.compute` :

1. **Impact TO** — delta occupation → ajustement CA F&B / N-F&B  
2. **R1 clients** — facteur = clients_hotel / clients_pilote  
3. **R2 mix** — rééquilibrage selon mix cible (pas à pas `MIX_STEP`)  
4. **R3 catégories** — coefficients `RULE3_FB_COEFFS` / `RULE3_NFB_COEFFS`
   selon besoins activés vs baseline  
5. **R4 m_lin** — scaling mètres linéaires vs pivot concept  
6. **Marge produit** — `CA - CA/coef` (coefs type Excel J9/J10)

Aperçu UI sans simu complète : `POST /api/rule1` (impact TO + R1 seulement).

---

## Coûts

`CostRules.compute(request, concept)` :

- lit `concepts.{CONCEPT}.cost_lines` dans `rod_reference.json`
- par ligne :  
  - si `monthly_unit` > 0 → opex = monthly_unit × qty  
  - sinon si capex + amort → opex = capex/amort  
- groupes typiques : techno, annexes, agencement (souvent ∝ m_lin)

Piège connu (corrigé) : ne pas double-compter une qty CONNECTED déjà
portée dans un forfait (ex. frigo).

Sortie : monthly_cost, annual_cost, capex, détail lignes.

---

## Recommandation

`RecommendationRules` :

1. **Taille**  
   - n &lt; 50 → SIMPLY (chemin restreint)  
   - n ≥ 50 → LIBERTY / CONNECTED (et cas IBB particuliers)  
2. **N-F&B lifestyle** — si au moins un besoin de `LIBERTY_NFB_NEEDS`
   actif → ouvre LIBERTY  
3. **Choix final** — parmi les concepts autorisés, maximise la marge nette
   (après coûts)

Warnings renvoyés dans la réponse simu (transparence UI).

---

## Orchestration

`SimulationOrchestrator.simulate_all` :

1. `prepare_request` — hydrate hotel_code depuis admin si besoin  
2. enrichissement optionnel (`light_enrich` saute Overpass/Meteostat)  
3. pour chaque concept ∈ {SIMPLY, LIBERTY, CONNECTED} : `RodSimulator`  
4. reco + assemblage `FullSimulation`

---

## Validation

```bash
accor-validate-rod
```

Couvre clients jour/mois, R1 API vs engine, R2–R4 neutres au pivot,
reco &lt;50 / LIBERTY N-F&B, coûts ∝ m_lin, cohérence simulate.

---

## Coefficients (`coeffs.py`)

- `RULE3_FB_COEFFS` / `RULE3_NFB_COEFFS` — poids catégories  
- `RULE3_BASELINE_*` — sommes de référence  
- `LIBERTY_NFB_NEEDS` — set lifestyle pour reco  
- `CLIENT_NEED_LABELS` — libellés UI  
- `BRAND_TO_CODE` / `BRANDS_REQUIRING_LIBERTY_PATH` — mapping marques  
