# Audit & plan UX GUI (F0044)

## Zones auditées

| Zone | Constats | Ameliorations appliquees |
|------|----------|---------------------------|
| **Topbar** | Chips + boutons a plat, peu de hierarchie | Groupes d actions, chips plus lisibles, status plus fort |
| **Outils** | Cartes correctes, hover OK | Accent lateral par type, icone plus presente, densite |
| **Graphe** | Grille dense, empty basique | Empty state plus clair, tabs plus marquees, canvas adouci |
| **Config** | Formulaire long, labels uppercase | Champs groupes, focus renforce, actions config plus stables |
| **Requires / Utilise par** | Deja riches (F0040/41) | Alignement chips, espacement |
| **Data preview / Changelogs** | Tabs bas OK | Tabs plus proeminents, table plus lisible |
| **Dialogs** | Solides (F0036/38) | Cohesion ombres / rayon / boutons |
| **Boutons** | Multiples densites | Echelle unifiee (sm / default / primary / icon) |

## Principes design

1. **Hierarchie** : surface (bg) → panel → controles
2. **Accent unique** : bleu renatus + couleurs type (df/table/view/…)
3. **Feedback** : hover leger, focus visible, selected marque
4. **Densite** : pro data-tool (compact) sans ecraser les cibles cliquables
5. **Consistance** : meme rayon, meme gap, meme mono pour chemins/ids

## Hors scope (suite possible)

- Dark/light toggle
- Drag redimension panels
- Zoom graphe
- Theming par projet
