#!/usr/bin/env python3
"""
Serveur Flask de l interface admin Accor Data and Model Studio.

Ce module expose la page unique et les routes API. La logique metier
est dans store, join_data, geo_*, sales_prep, model_*, concept_pilote.

Routes principales:
  pages HTML via templates/index.html
  CRUD datasets Excel via store.py
  rebuild all_data, model_data, sales, weather, proximity, holidays, concept
  build, list, explore et deploy des modeles XGBoost

Lancer: python run_admin.py  (http://127.0.0.1:5055)
Simulateur directeur: python run_user.py (port 5056)
Documentation: README.md
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

# Schémas des onglets (colonnes saisissables) et couche Excel
from archive.accor_1_0_6.accor_1_0_0.schemas import list_datasets
from archive.accor_1_0_6.accor_1_0_0.store import (
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


def _resolve_marque_logo(relpath: str) -> Path | None:
    """
    Résout un ``logo_path`` Excel vers un fichier sous ``accord/data/marques/``.

    Chemin ancré sur ``ROOT`` (= dossier de ``app.py`` / ``run_admin.py``),
    **indépendant du cwd** au lancement.

    Accepte :
    * ``economy/ibis.png``  (forme stockée dans hotel_brand_data)
    * ``marques/economy/ibis.png``
    * ``data/marques/economy/ibis.png``
    * chemin absolu déjà sous ``data/marques/``
    """
    base = (ROOT / "data" / "marques").resolve()
    if not relpath:
        return None
    raw = str(relpath).strip().replace("\\", "/")
    if not raw or raw.lower() in {"nan", "none", "null"}:
        return None

    p = Path(raw)
    if p.is_absolute():
        try:
            target = p.resolve()
            target.relative_to(base)
            return target if target.is_file() else None
        except (ValueError, OSError):
            return None

    clean = raw.lstrip("/")
    # strip préfixes redondants
    for prefix in (
        "data/marques/",
        "marques/",
        "./data/marques/",
        "./marques/",
    ):
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix) :]
            break
    if ".." in clean.split("/"):
        return None
    target = (base / clean).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return None
    return target if target.is_file() else None


def _logo_mimetype(path: Path) -> str:
    """
    Détecte le vrai type des logos Accor.

    Beaucoup de fichiers ``*.png`` du scrape sont en fait du **SVG**
    (logos monochrome Accor) — un Content-Type image/png fait échouer
    l'affichage navigateur (→ tiret « — » dans l'UI).
    """
    try:
        head = path.read_bytes()[:512]
    except OSError:
        return "application/octet-stream"
    low = head.lstrip().lower()
    if low.startswith(b"<svg") or b"<svg" in low or low.startswith(b"<?xml"):
        return "image/svg+xml"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    # fallback extension
    ext = path.suffix.lower()
    return {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")


@app.get("/api/marques/logos/<path:relpath>")
def api_marque_logo(relpath: str):
    """
    Sert un logo marque depuis ``accord/data/marques/``.

    URL : ``/api/marques/logos/economy/ibis_budget.png``
    Fichier : ``{ROOT}/data/marques/economy/ibis_budget.png``
    avec ``ROOT`` = répertoire de ``run_admin.py`` / ``app.py``.

    Le Content-Type est déduit du **contenu** (SVG vs PNG réel), pas
    seulement de l'extension.
    """
    target = _resolve_marque_logo(relpath)
    if target is None:
        return jsonify({
            "error": "logo introuvable",
            "path": relpath,
            "expected_under": str((ROOT / "data" / "marques").resolve()),
        }), 404
    mime = _logo_mimetype(target)
    # max-age court pour pouvoir recharger après re-scrape
    resp = send_file(
        target,
        mimetype=mime,
        conditional=True,
        download_name=target.name,
        max_age=300,
    )
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


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
@app.post("/api/datasets/data/rebuild")  # alias retro-compat
def api_rebuild_join():
    """
    Bouton Reconstruire de l onglet All Data.

    Construit data/all_data.xlsx :
      base = hotel_sales_data (hotels avec au moins une vente, mois de vente)
      left join holidays, weather, hotel_data, proximity, brand

    Body JSON optionnel:
      fill_weather, fill_proximity (defaut false depuis l UI)
    """
    body = request.get_json(force=True, silent=True) or {}
    try:
        result = rebuild_joined_data(
            fill_weather=bool(body.get("fill_weather", False)),
            fill_proximity=bool(body.get("fill_proximity", False)),
        )
        # invalide aussi model_data (dérivé)
        try:
            from archive.accor_1_0_6.accor_1_0_0.store import _cache

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
        from archive.accor_1_0_6.accor_1_0_0.model_data import rebuild_model_data
        from archive.accor_1_0_6.accor_1_0_0.store import _cache

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
        from archive.accor_1_0_6.accor_1_0_0.sales_prep import ensure_raw_sales_from_archive, rebuild_hotel_sales_data
        from archive.accor_1_0_6.accor_1_0_0.store import _cache

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
        from archive.accor_1_0_6.accor_1_0_0.geo_weather import rebuild_hotel_weather_data
        from archive.accor_1_0_6.accor_1_0_0.store import _cache

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
        from archive.accor_1_0_6.accor_1_0_0.geo_proximity import rebuild_hotel_proximity_data
        from archive.accor_1_0_6.accor_1_0_0.store import _cache

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
        from archive.accor_1_0_6.accor_1_0_0.geo_holidays import rebuild_hotel_holidays_data
        from archive.accor_1_0_6.accor_1_0_0.store import _cache

        result = rebuild_hotel_holidays_data()
        _cache.pop("holidays", None)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/datasets/concept_pilote/rebuild")
def api_rebuild_concept_pilote():
    """
    Recalcule ``concept_pilote.xlsx`` (hôtel × année).

    * clients = chambres × TO × guests (hotel_data + défauts marque)
    * CA mensuel moyen depuis hotel_sales_data
    * mix F_B / N_F_B = produits distincts (sales_raw prioritaire)
    """
    try:
        from archive.accor_1_0_6.accor_1_0_0.concept_pilote import rebuild_concept_pilote
        from archive.accor_1_0_6.accor_1_0_0.store import _cache

        result = rebuild_concept_pilote()
        _cache.pop("concept_pilote", None)
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
        from archive.accor_1_0_6.accor_1_0_0.model_train import get_config_payload

        return jsonify(get_config_payload())
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/list")
def api_model_list():
    """Liste des modèles design, triés par performance."""
    try:
        from archive.accor_1_0_6.accor_1_0_0.model_train import get_last_trained, get_top_model, list_design_models

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
    Build manuel + grid search (batch asynchrone).

    Body JSON:
      model_name, xgb_params (manuel),
      grid_search: { param: [valeurs], ... }  (optionnel),
      main_target: cible principale pour le ranking (defaut montant_ventes),
      rank_metric: r2 | rmse | mae,
      async: true (defaut) lance en arriere-plan et retourne tout de suite

    Suivre l avancement: GET /api/model/build/progress
    """
    body = request.get_json(force=True, silent=True) or {}
    try:
        from archive.accor_1_0_6.accor_1_0_0.model_train import (
            build_and_save,
            count_grid_jobs,
            start_build_batch,
        )

        use_async = body.get("async", True)
        grid = body.get("grid_search") or body.get("grid") or {}
        # normaliser listes
        if isinstance(grid, dict):
            grid_norm = {
                k: (v if isinstance(v, list) else [v])
                for k, v in grid.items()
                if v is not None and v != ""
            }
        else:
            grid_norm = {}

        if use_async:
            result = start_build_batch(
                model_name=body.get("model_name"),
                xgb_params=body.get("xgb_params"),
                grid_search=grid_norm or None,
                main_target=body.get("main_target"),
                rank_metric=body.get("rank_metric") or "r2",
            )
            counts = count_grid_jobs(body.get("xgb_params"), grid_norm or None)
            result["counts"] = counts
            return jsonify(result)

        # mode sync simple (un seul modele, sans grid)
        if grid_norm:
            return jsonify(
                {
                    "error": "Utilisez async=true pour un build avec grid search",
                }
            ), 400
        result = build_and_save(
            xgb_params=body.get("xgb_params"),
            model_name=body.get("model_name"),
            main_target=body.get("main_target"),
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


@app.get("/api/model/build/progress")
def api_model_build_progress():
    """Progression du build batch (manuel + grid search)."""
    try:
        from archive.accor_1_0_6.accor_1_0_0.model_train import get_build_progress

        return jsonify(get_build_progress())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/model/build/count")
def api_model_build_count():
    """Compte le nombre de modeles (manuel + grid) sans lancer l entrainement."""
    body = request.get_json(force=True, silent=True) or {}
    try:
        from archive.accor_1_0_6.accor_1_0_0.model_train import count_grid_jobs

        grid = body.get("grid_search") or body.get("grid") or {}
        if isinstance(grid, dict):
            grid_norm = {
                k: (v if isinstance(v, list) else [v])
                for k, v in grid.items()
                if v is not None and v != ""
            }
        else:
            grid_norm = {}
        return jsonify(count_grid_jobs(body.get("xgb_params"), grid_norm or None))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/model/deploy")
def api_model_deploy():
    """
    Copie le modèle design sélectionné vers ``models/deploy/model.pkl``
    + ``model.json`` (un seul modèle déployé).
    """
    body = request.get_json(force=True, silent=True) or {}
    try:
        from archive.accor_1_0_6.accor_1_0_0.model_train import deploy_model

        return jsonify(deploy_model(body.get("model_name") or body.get("id")))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/<model_id>")
def api_model_detail(model_id: str):
    """Métadonnées d'un modèle design."""
    try:
        from archive.accor_1_0_6.accor_1_0_0.model_train import DESIGN_DIR
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
        from archive.accor_1_0_6.accor_1_0_0.model_explore import explore_overview

        return jsonify(explore_overview(model_id))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/<model_id>/tree")
def api_model_tree(model_id: str):
    """Structure d'un arbre (cible principale par défaut)."""
    try:
        from archive.accor_1_0_6.accor_1_0_0.model_explore import get_tree

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
        from archive.accor_1_0_6.accor_1_0_0.model_explore import trees_table

        return jsonify(trees_table(model_id))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/<model_id>/tree-metrics")
def api_model_tree_metrics(model_id: str):
    """Alias → table des arbres."""
    try:
        from archive.accor_1_0_6.accor_1_0_0.model_explore import trees_table

        return jsonify(trees_table(model_id))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/<model_id>/importance")
def api_model_importance(model_id: str):
    """Feature importance (cible principale)."""
    try:
        from archive.accor_1_0_6.accor_1_0_0.model_explore import feature_importance_payload

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

    parser = argparse.ArgumentParser(description="Accor · Data & Model Studio")
    parser.add_argument("--host", default="127.0.0.1", help="Adresse d'écoute")
    parser.add_argument("--port", type=int, default=5055, help="Port HTTP")
    parser.add_argument("--debug", action="store_true", help="Mode debug Flask")
    args = parser.parse_args()
    print(f"Accor · Data & Model Studio → http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
