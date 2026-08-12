# Feature — Redistribution proportionnelle du mix (type & gammes)

## Objectif

Dans l’interface utilisateur (Configuration / leviers), quand on **augmente** ou
**réduit** la part d’**une** entrée de mix (type F&B / Non F&B, ou une gamme),
l’écart n’est **pas** réparti à parts égales sur le reste : il est répercuté
**proportionnellement aux parts actuelles** des autres entrées libres.

Même règle pour :

- le mix **type** (F&B vs Non F&B) ;
- les mix **gammes F&B** ;
- les mix **gammes Non F&B**.

## Règle métier

Soit un groupe de parts qui somment à 1 (hors items **verrouillés**).

1. L’utilisateur fixe la part de la clé `K` à une nouvelle valeur `v`
   (bornée pour que la somme reste réalisable avec les locks).
2. Masse restante pour les **autres libres** :
   `rem = 1 − somme(locked) − v`
3. Chaque autre libre `i` reçoit :
   ```
   part_i = rem × (part_i_avant / somme(parts_autres_libres_avant))
   ```
4. Si tous les autres libres sont à 0 % : répartition **égale**
   (seul cas non proportionnel, indéterminé sinon).

### Exemple numérique

| | Avant | A → 60 % | A → 40 % |
|--|------:|---------:|---------:|
| A | 50 % | **60 %** | **40 %** |
| B | 30 % | **24 %** | **36 %** |
| C | 20 % | **16 %** | **24 %** |

- A +10 % : on retire 10 % de B+C au prorata 30:20 → B −6 %, C −4 %.
- A −10 % : on rend 10 % au même prorata → B +6 %, C +4 %.

## UI

Deux modes (`memory.mixMode`) :

| Mode | Quand | Comportement |
|------|--------|--------------|
| **`select`** | avant estimation | switch **ON/OFF** types & gammes uniquement (pas de sliders) |
| **`edit`** | après reco mix | sliders de proportions + redistribution proportionnelle |

- Composant **`MixPanel`** (`src/web/pages_user.py`)
  - mode `edit` : curseur → `setValue(key, pct)` (prorata)
  - switch : en `select` = activer/désactiver ; en `edit` = libre/verrouillé
- Les items désactivés ou verrouillés ne participent pas à la redistribution

## Backend (cohérence optimisation grid)

La fonction `vary_one` dans `src/user/optimize.py` (mode `method=grid` du
balayage 10 %) utilise **la même** redistribution proportionnelle, pour que
les scénarios d’optimisation ne déforment pas le mix de façon artificielle
(égale).

## Code

| Fichier | Élément |
|---------|---------|
| `src/web/pages_user.py` | `MixPanel.setValue` — prorata UI |
| `src/user/optimize.py` | `vary_one` — prorata grid |

## Lien avec l’assortiment optimal

Voir [FEATURE_OPTIMAL_MIX.md](FEATURE_OPTIMAL_MIX.md) : la reco calcule un
mix initial (top produits / m_lin) ; l’utilisateur peut ensuite **ajuster**
les parts avec cette redistribution proportionnelle avant une nouvelle
simulation.
