#!/usr/bin/env python3
"""
Accord Data Studio — API HTTP + page unique de saisie.

Rôle
----
Expose une interface web pour éditer les Excel de ``accord/data/`` en WYSIWYG
(page par page). Le front (HTML/JS) appelle les routes ``/api/datasets/...`` ;
la logique métier (lecture/écriture Excel, pagination) vit dans ``store.py``.

Lancer
------
    python run.py
    # → http://127.0.0.1:5055
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
# Pages
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    """Page principale : shell UI (onglets + table éditable)."""
    return render_template("index.html")


@app.get("/favicon.ico")
def favicon():
    """Évite un 404 bruyant dans la console navigateur."""
    return ("", 204)


# ---------------------------------------------------------------------------
# API — lecture
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    """Sonde simple pour vérifier que le serveur tourne."""
    return jsonify({"status": "ok", "app": "accord-data-studio"})


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
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


# ---------------------------------------------------------------------------
# API — modèle XGBoost (config + build + liste)
# ---------------------------------------------------------------------------

@app.get("/api/model/config")
def api_model_config():
    """
    Schéma de configuration pour l'écran d'apprentissage.

    Query : ``source`` = ``data`` (All Data) ou ``sales``.
    """
    try:
        from model_train import get_config_payload

        source = request.args.get("source", "data").strip() or "data"
        return jsonify(get_config_payload(source=source))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/list")
def api_model_list():
    """Liste des modèles sauvegardés dans ``models/``."""
    try:
        from model_train import list_models

        return jsonify({"models": list_models()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/model/build")
def api_model_build():
    """
    Lance l'apprentissage XGBoost et sauvegarde le modèle.

    Body JSON
    ---------
    {
      "source": "data",
      "feature_groups": { "pct_mix": true, "pct_sous_cat": true, ... },
      "targets": ["nombre_ventes", "montant_ventes"],
      "xgb_params": { "n_estimators": 200, "max_depth": 6, ... },
      "test_size": 0.2,
      "model_name": "xgb_sales"
    }
    """
    body = request.get_json(force=True, silent=True) or {}
    try:
        from model_train import train_model

        result = train_model(
            source=str(body.get("source") or "data"),
            feature_groups=body.get("feature_groups"),
            targets=body.get("targets"),
            xgb_params=body.get("xgb_params"),
            test_size=float(body.get("test_size") or 0.2),
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


@app.get("/api/model/<model_id>")
def api_model_detail(model_id: str):
    """Métadonnées d'un modèle sauvegardé."""
    try:
        from model_train import MODELS_DIR
        import json as _json

        meta_path = MODELS_DIR / model_id / "meta.json"
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
    """Vue d'ensemble pour Model Explore (targets, n arbres, importances)."""
    try:
        from model_explore import explore_overview

        return jsonify(explore_overview(model_id))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/<model_id>/tree")
def api_model_tree(model_id: str):
    """
    Structure d'un arbre de décision.

    Query : ``target`` (index), ``tree`` (index 0-based).
    """
    try:
        from model_explore import get_tree

        target = int(request.args.get("target", 0))
        tree = int(request.args.get("tree", 0))
        return jsonify(get_tree(model_id, target_index=target, tree_index=tree))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/<model_id>/tree-metrics")
def api_model_tree_metrics(model_id: str):
    """
    Performance cumulative de chaque arbre vs performance globale.

    Query : ``target`` (index de la cible).
    """
    try:
        from model_explore import tree_performances

        target = int(request.args.get("target", 0))
        return jsonify(tree_performances(model_id, target_index=target))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/<model_id>/importance")
def api_model_importance(model_id: str):
    """Feature importance globale ou par target (``?target=0``)."""
    try:
        from model_explore import feature_importance_payload

        t = request.args.get("target")
        target_index = int(t) if t is not None and t != "" else None
        return jsonify(feature_importance_payload(model_id, target_index=target_index))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


# ---------------------------------------------------------------------------
# Entrée CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """Point d'entrée serveur de développement Flask."""
    import argparse

    parser = argparse.ArgumentParser(description="Accord Data Studio")
    parser.add_argument("--host", default="127.0.0.1", help="Adresse d'écoute")
    parser.add_argument("--port", type=int, default=5055, help="Port HTTP")
    parser.add_argument("--debug", action="store_true", help="Mode debug Flask")
    args = parser.parse_args()
    print(f"Accord Data Studio → http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
