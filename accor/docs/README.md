# Documentation Accor ROD

Index des docs détaillées. Le point d’entrée reste le
[README racine](../README.md) (install, lancement, vue d’ensemble).

| Document | Contenu |
|----------|---------|
| [API_ADMIN.md](API_ADMIN.md) | Routes Flask admin (:5055) — datasets, modèles, **ROD** |
| [API_USER.md](API_USER.md) | Routes Flask user (:5056) |
| [MODULES.md](MODULES.md) | Catalogue des modules Python |
| [FRONT.md](FRONT.md) | JS/CSS admin, user, shared |
| [DATA.md](DATA.md) | Fichiers Excel/JSON, grains, rôles colonnes |
| [ROD_RULES.md](ROD_RULES.md) | Revenus, coûts, recommandation concept |
| [ROD_ADMIN.md](ROD_ADMIN.md) | **Simulateur ROD** admin/user (hôtel cible, éval temporelle) |
| [MODEL.md](MODEL.md) | Intermédiaires, final (stacking), explore, éval ML |

Les docstrings en tête de chaque module Python / fichier JS reprennent
l’essentiel ; en cas d’écart, le code fait foi.

### Sidebar admin (rappel)

```
All → Pilotes
  → Simulateur ROD
  → Modèles intermédiaires  (Build · Explore · Évaluation)
  → Modèle final            (Build · Explore · Évaluation)
```

### Vocabulaire ROD

* **Hôtel pilote** = ventes train → référence catégorie  
* **Hôtel cible** = hôtel pour lequel on simule le corner  
