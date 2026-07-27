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
| [ROD_EXCEL_SIM.md](ROD_EXCEL_SIM.md) | **Simulateur Excel** — réf. par solution, dual-colonne, R1–R4, reco |
| [MODEL.md](MODEL.md) | Intermédiaires, final (stacking), explore, éval ML |

Les docstrings en tête de chaque module Python / fichier JS reprennent
l’essentiel ; en cas d’écart, le code fait foi.

### Sidebar admin (rappel)

```
All → Pilotes
  → Simulateur ROD          (réf. catégorie + écart 2026)
  → Simulateur Excel        (réf. solution · dual-colonne · voir ROD_EXCEL_SIM.md)
  → Modèles intermédiaires  (Build · Explore · Évaluation)
  → Modèle final            (Build · Explore · Évaluation)
```

### Vocabulaire ROD

* **Hôtel pilote** = ventes train → référence catégorie  
* **Hôtel cible** = hôtel pour lequel on simule le corner  

### run_dev (console Grok web)

```bash
python run_dev.py                 # :5500
python scripts/dev_watchdog.py    # keep-alive + README url + git push
```

La première ligne du [README](../README.md) est `run_dev url : …`
(URL tunnel HTTPS si `./scripts/expose_public.sh dev|all` a été lancé,
sinon IP LAN `http://192.168.x.x:5500`).

### Watchdog permanent

Agent indéfini (`scripts/dev_watchdog.py`) :

* garde **run_dev** (:5500), **run_admin** (:5055), **run_user** (:5056) UP
* maintient les tunnels Cloudflare (URL dans `data/dev_console/tunnel_*.url`)
* publie les URL publiques en tête du [README](../README.md) + push git
* chaque minute : `git fetch` du README distant et exécute les lignes `watchdog>`

Consignes (section **Watchdog inbox**) :

```
watchdog> status
watchdog> restart admin
watchdog> reexpose all
watchdog> note: message libre
```

### Accès Internet (hors LAN)

`192.168.x.x` n’est **pas** routable depuis Internet. Pour un accès externe :

```bash
./scripts/expose_public.sh all      # admin + user + run_dev
./scripts/expose_public.sh status
```

Binaire : `bin/cloudflared`. Détails : [README § Accès réseau](../README.md).

Cache-busting assets : `?dt=<mtime>` (templates `{{ asset(...) }}` + rewrite des imports JS).