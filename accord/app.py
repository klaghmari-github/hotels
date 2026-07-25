#!/usr/bin/env python3
"""
Accord · Data & Model Studio — API HTTP + page unique.

Rôle
----
Serveur Flask de l'application :

* **Pages** : shell UI (``templates/index.html`` + static JS/CSS).
* **API datasets** : CRUD paginé sur les Excel de ``data/`` (via ``store.py``).
* **API jointure** : rebuild ``all_data.xlsx`` / ``model_data.xlsx``.
* **API modèles** : build XGBoost (design/), explore, deploy.

La logique métier ne vit **pas** ici : ce module route uniquement vers
``store``, ``join_data``, ``model_*``.

Lancer
------
    python run_admin.py
    # → http://127.0.0.1:5055

Interface directeur / simulateur ROD : ``python run_user.py`` (port 5056).

Voir ``README.md`` pour le détail des routes et de l'architecture.
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template, request

# Schémas des onglets (colonnes saisissables) et couche Excel
from schemas import list_datasets
from store import (
    add_row,
    delete_rows,
    page_payload,
    rebuild_joined_data,
    reload_dataset,
    update_rows,
)

# Racine du package accord/ (templates + static à côté de ce fichier)
ROOT = Path(__file__).resolve().parent

app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(ROOT / "static"),
)
# Garde les accents / unicode dans les réponses JSON (noms d'hôtels, etc.)
app.config["JSON_AS_ASCII"] = False


# ---------------------------------------------------------------------------
# Pages HTML
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    """
    Page unique de l'application (SPA légère).

    Le HTML charge ``static/js/app.js`` qui pilote les onglets datasets,
    Model Build et Model Explore via les routes ``/api/...``.
    """
    return render_template("index.html")


@app.get("/favicon.ico")
def favicon():
    """Évite un 404 bruyant dans la console navigateur."""
    return ("", 204)


# ---------------------------------------------------------------------------
# API — lecture des datasets (tables Excel)
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    """Sonde simple pour vérifier que le serveur tourne."""
    return jsonify({"status": "ok", "app": "accord-data-model-studio"})


@app.get("/api/datasets")
def api_datasets():
    """
    Liste les jeux de données (onglets) avec métadonnées UI.

    Chaque entrée contient id, label, description, colonnes éditables, etc.
    """
    return jsonify({"datasets": list_datasets()})


@app.get("/api/datasets/<dataset_id>")
def api_get_page(dataset_id: str):
    """
    Retourne une **page** de lignes éditables pour un dataset.

    Query params
    ------------
    page : int (défaut 1)
    page_size : int (optionnel, sinon défaut du schéma)
    q : str — filtre texte sur toutes les colonnes affichées
    """
    try:
        page = int(request.args.get("page", 1))
        page_size = request.args.get("page_size")
        q = request.args.get("q", "").strip()
        payload = page_payload(
            dataset_id,
            page=page,
            page_size=int(page_size) if page_size else None,
            q=q,
        )
        return jsonify(payload)
    except KeyError as exc:
        # dataset_id inconnu
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


# ---------------------------------------------------------------------------
# API — écriture (persistance Excel)
# ---------------------------------------------------------------------------

@app.put("/api/datasets/<dataset_id>/rows")
def api_update_rows(dataset_id: str):
    """
    Met à jour une ou plusieurs lignes puis réécrit le fichier Excel.

    Body JSON
    ---------
    {
      "rows": [
        { "_index": 0, "hotel_code": "H2075", "nombre_ventes": 12, ... },
        ...
      ]
    }

    ``_index`` = index pandas de la ligne dans le DataFrame chargé en mémoire.
    Seules les colonnes déclarées éditables dans le schéma sont prises en compte.
    """
    body = request.get_json(force=True, silent=True) or {}
    rows = body.get("rows") or []
    try:
        result = update_rows(dataset_id, rows)
        return jsonify(result)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/datasets/<dataset_id>/rows")
def api_add_row(dataset_id: str):
    """
    Ajoute une ligne vide (ou préremplie) en bas du tableau.

    Body optionnel : ``{ "values": { "hotel_code": "...", ... } }``
    """
    body = request.get_json(force=True, silent=True) or {}
    try:
        result = add_row(dataset_id, body.get("values") or {})
        return jsonify(result)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.delete("/api/datasets/<dataset_id>/rows")
def api_delete_rows(dataset_id: str):
    """
    Supprime des lignes par index DataFrame.

    Body : ``{ "indices": [0, 3, 12] }``
    """
    body = request.get_json(force=True, silent=True) or {}
    indices = body.get("indices") or []
    try:
        result = delete_rows(dataset_id, [int(i) for i in indices])
        return jsonify(result)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/datasets/<dataset_id>/reload")
def api_reload(dataset_id: str):
    """
    Recharge le fichier Excel depuis le disque (invalide le cache mémoire).

    Utile si le fichier a été modifié hors de l'application.
    """
    try:
        return jsonify(reload_dataset(dataset_id))
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404


@app.post("/api/datasets/all_data/rebuild")
@app.post("/api/datasets/data/rebuild")  # alias rétro-compat
def api_rebuild_join():
    """
    **Reconstruire** : jointure de tous les onglets → ``data/all_data.xlsx``,
    puis le fichier est rechargé en cache pour l'UI.

    Body optionnel JSON : ``{ "fill_weather": false, "fill_proximity": false }``
    """
    body = request.get_json(force=True, silent=True) or {}
    try:
        result = rebuild_joined_data(
            fill_weather=bool(body.get("fill_weather", False)),
            fill_proximity=bool(body.get("fill_proximity", False)),
        )
        # invalide aussi model_data (dérivé)
        try:
            from store import _cache

            _cache.pop("model_data", None)
        except Exception:
            pass
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/datasets/model_data/rebuild")
def api_rebuild_model_data():
    """Reconstruit model_data.xlsx depuis all_data."""
    try:
        from model_data import rebuild_model_data
        from store import _cache

        result = rebuild_model_data()
        _cache.pop("model_data", None)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/datasets/sales/rebuild")
def api_rebuild_sales():
    """
    Reconstruit ``hotel_sales_data.xlsx`` depuis ``hotel_sales_raw_data.xlsx``.

    Normalise TYPE/GAMME, mappe les boutiques → hotel_code (hotel_data),
    agrège mensuellement + indicateurs %.
    """
    try:
        from sales_prep import ensure_raw_sales_from_archive, rebuild_hotel_sales_data
        from store import _cache

        ensure_raw_sales_from_archive()
        result = rebuild_hotel_sales_data(drop_unmatched=True)
        _cache.pop("sales", None)
        _cache.pop("sales_raw", None)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/datasets/weather/rebuild")
def api_rebuild_weather():
    """
    Recalcule ``hotel_weather_data.xlsx``.

    Hôtels = hotel_data ; années = hotel_sales ; mois terminés uniquement
    (mois en cours exclu). Meteostat via lat/lon.
    """
    try:
        from geo_weather import rebuild_hotel_weather_data
        from store import _cache

        result = rebuild_hotel_weather_data()
        _cache.pop("weather", None)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/datasets/proximity/rebuild")
def api_rebuild_proximity():
    """
    Recalcule ``hotel_proximity_data.xlsx`` via Overpass pour chaque hôtel
    de hotel_data (commerces 100–500 m, plage 1–5 km).
    """
    try:
        from geo_proximity import rebuild_hotel_proximity_data
        from store import _cache

        result = rebuild_hotel_proximity_data(pause_s=1.0)
        _cache.pop("proximity", None)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/datasets/holidays/rebuild")
def api_rebuild_holidays():
    """
    Recalcule ``hotel_holidays_data.xlsx``.

    Hôtels = hotel_data ; années = hotel_sales ; mois terminés uniquement.
    Jours fériés FR + vacances scolaires par zone.
    """
    try:
        from geo_holidays import rebuild_hotel_holidays_data
        from store import _cache

        result = rebuild_hotel_holidays_data()
        _cache.pop("holidays", None)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


# ---------------------------------------------------------------------------
# API — modèle XGBoost (build design + explore + deploy)
# ---------------------------------------------------------------------------

@app.get("/api/model/config")
def api_model_config():
    """Config Model Build : hyperparams + dernier modèle (source = model_data)."""
    try:
        from model_train import get_config_payload

        return jsonify(get_config_payload())
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/list")
def api_model_list():
    """Liste des modèles design, triés par performance."""
    try:
        from model_train import get_last_trained, get_top_model, list_design_models

        return jsonify(
            {
                "models": list_design_models(),
                "last_trained": get_last_trained(),
                "top_model": get_top_model(),
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/model/build")
def api_model_build():
    """
    Entraîne + sauvegarde dans ``models/design/<name>/``
    (model.pkl + config.json). Écrase si même nom.
    """
    body = request.get_json(force=True, silent=True) or {}
    try:
        from model_train import build_and_save

        result = build_and_save(
            xgb_params=body.get("xgb_params"),
            model_name=body.get("model_name"),
        )
        return jsonify(result)
    except ImportError as exc:
        return jsonify({"error": str(exc)}), 500
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/model/deploy")
def api_model_deploy():
    """
    Copie le modèle design sélectionné vers ``models/deploy/model.pkl``
    + ``model.json`` (un seul modèle déployé).
    """
    body = request.get_json(force=True, silent=True) or {}
    try:
        from model_train import deploy_model

        return jsonify(deploy_model(body.get("model_name") or body.get("id")))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/<model_id>")
def api_model_detail(model_id: str):
    """Métadonnées d'un modèle design."""
    try:
        from model_train import DESIGN_DIR
        import json as _json

        meta_path = DESIGN_DIR / model_id / "config.json"
        if not meta_path.exists():
            return jsonify({"error": f"Modèle inconnu : {model_id}"}), 404
        meta = _json.loads(meta_path.read_text(encoding="utf-8"))
        meta["id"] = model_id
        meta["path"] = str(meta_path.parent)
        return jsonify(meta)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/<model_id>/explore")
def api_model_explore(model_id: str):
    """Vue d'ensemble Model Explore."""
    try:
        from model_explore import explore_overview

        return jsonify(explore_overview(model_id))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/<model_id>/tree")
def api_model_tree(model_id: str):
    """Structure d'un arbre (cible principale par défaut)."""
    try:
        from model_explore import get_tree

        target = request.args.get("target")
        tree = int(request.args.get("tree", 0))
        t_idx = int(target) if target not in (None, "") else None
        return jsonify(get_tree(model_id, target_index=t_idx, tree_index=tree))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/<model_id>/trees")
def api_model_trees_table(model_id: str):
    """Table des arbres (profondeur, n features, perf cumulative)."""
    try:
        from model_explore import trees_table

        return jsonify(trees_table(model_id))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/<model_id>/tree-metrics")
def api_model_tree_metrics(model_id: str):
    """Alias → table des arbres."""
    try:
        from model_explore import trees_table

        return jsonify(trees_table(model_id))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/<model_id>/importance")
def api_model_importance(model_id: str):
    """Feature importance (cible principale)."""
    try:
        from model_explore import feature_importance_payload

        return jsonify(feature_importance_payload(model_id))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


# ---------------------------------------------------------------------------
# Entrée CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """Point d'entrée serveur de développement Flask."""
    import argparse

    parser = argparse.ArgumentParser(description="Accord · Data & Model Studio")
    parser.add_argument("--host", default="127.0.0.1", help="Adresse d'écoute")
    parser.add_argument("--port", type=int, default=5055, help="Port HTTP")
    parser.add_argument("--debug", action="store_true", help="Mode debug Flask")
    args = parser.parse_args()
    print(f"Accord · Data & Model Studio → http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
