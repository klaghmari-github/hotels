#!/usr/bin/env python3
"""
Serveur Flask — interface admin Accor Data & Model Studio.

Page unique (templates/index.html) + API JSON. La logique métier est
ailleurs : store (Excel), join_data / sales_prep / geo_* / model_* /
concept_pilote.

Routes regroupées :
  /api/datasets/*     CRUD + pagination + rebuilds
  /api/model/*        build, list, explore, deploy, eval
  /api/marques/logos  logos PNG sous data/marques/

Lancer :
  python run_admin.py          → http://127.0.0.1:5055
  accor-admin

Simulateur directeur (autre process) : python run_user.py → :5056

Doc :
  README.md           vue d'ensemble
  docs/API_ADMIN.md   contrat HTTP (datasets, modèle, /api/rod/*)
  docs/ROD_ADMIN.md   Simulateur ROD admin (trace pilotes)
  docs/MODULES.md     carte des modules
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

# Schémas des onglets (colonnes saisissables) et couche Excel
from accor.schemas import list_datasets
from accor.store import (
    add_row,
    delete_rows,
    page_payload,
    rebuild_joined_data,
    reload_dataset,
    update_rows,
)

from accor.cache_bust import register_cache_bust
from accor.data_io import PROJECT_ROOT, STATIC_DIR, TEMPLATES_DIR

ROOT = PROJECT_ROOT

app = Flask(
    __name__,
    template_folder=str(TEMPLATES_DIR),
    static_folder=None,  # servi via cache_bust (?dt=mtime)
)
# Garde les accents / unicode dans les réponses JSON (noms d'hôtels, etc.)
app.config["JSON_AS_ASCII"] = False
register_cache_bust(app, STATIC_DIR)


# ---------------------------------------------------------------------------
# Pages HTML
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    """
    Page unique admin (SPA légère).

    Le HTML charge ``static/js/admin/app.js`` (modules ES) : datasets,
    Model Build, Model Explore, Evaluation — le tout via ``/api/...``.
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
            from accor.store import _cache

            _cache.pop("model_data", None)
        except Exception:
            pass
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/datasets/model_data/rebuild")
def api_rebuild_model_data():
    """
    Reconstruit model_data.xlsx (+ meta JSON) depuis all_data.

    Filtre hôtels sans ventes, rôles colonnes, _is_eval, imputation ML.
    """
    try:
        from accor.model_data import rebuild_model_data
        from accor.store import _cache

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
        from accor.sales_prep import ensure_raw_sales_from_archive, rebuild_hotel_sales_data
        from accor.store import _cache

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
        from accor.geo_weather import rebuild_hotel_weather_data
        from accor.store import _cache

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
        from accor.geo_proximity import rebuild_hotel_proximity_data
        from accor.store import _cache

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
        from accor.geo_holidays import rebuild_hotel_holidays_data
        from accor.store import _cache

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
        from accor.concept_pilote import rebuild_concept_pilote
        from accor.store import _cache

        result = rebuild_concept_pilote()
        _cache.pop("concept_pilote", None)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/datasets/simulateur_data/rebuild")
def api_rebuild_simulateur_data():
    """
    Recalcule ``simulateur_data.xlsx`` depuis ``hotel_sales_raw_data.xlsx``.

    Mesures ventes des pilotes regroupés par solution SIMPLY / LIBERTY /
    CONNECTED (CA HT/TTC F&B·N-F&B, mix, nb ventes, impact TO…).
    Feuilles : simulateur_data, mensuel, moyennes_solution, meta.

    Synchronise aussi ``hotel_solution_simply|liberty|connected`` (0/1)
    sur hotel_data pour les joints all_data / model_data.
    """
    try:
        from accor.simulator_data import rebuild_simulateur_data
        from accor.store import _cache

        result = rebuild_simulateur_data()
        _cache.pop("simulateur_data", None)
        _cache.pop("hotel", None)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/datasets/hotel/sync_solution_flags")
def api_sync_hotel_solution_flags():
    """Pose hotel_solution_simply|liberty|connected (0/1) depuis rod_pilot_concepts."""
    try:
        from accor.hotel_solutions import sync_hotel_data_solution_flags
        from accor.store import _cache

        result = sync_hotel_data_solution_flags()
        _cache.pop("hotel", None)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


# ---------------------------------------------------------------------------
# API — modèle XGBoost (build design + explore + deploy)
# ---------------------------------------------------------------------------

@app.get("/api/model/config")
def api_model_config():
    """
    Config Model Build : hyperparams par défaut, grilles, cible principale,
    dernier modèle. Features issues de model_data.
    """
    try:
        from accor.model_train import get_config_payload

        return jsonify(get_config_payload())
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/list")
def api_model_list():
    """Liste models/design, last_trained et top_model (ranking cible principale)."""
    try:
        from accor.model_train import get_last_trained, get_top_model, list_design_models

        return jsonify(
            {
                "models": list_design_models(),
                "last_trained": get_last_trained(),
                "top_model": get_top_model(),
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/eval/meta")
def api_model_eval_meta():
    """
    Prépare l'onglet Evaluation.

    Query ``tier`` = intermediate (défaut) | final.
    """
    try:
        from accor.model_eval import eval_meta

        tier = request.args.get("tier") or "intermediate"
        return jsonify(eval_meta(tier=tier))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.get("/api/model/eval")
@app.post("/api/model/eval")
def api_model_eval():
    """
    Évalue un modèle (intermédiaire ou final) sur l'année incomplete.

    Body/query : model_id, target, year, tier (intermediate|final).
    """
    try:
        from accor.model_eval import evaluate_model

        if request.method == "POST":
            body = request.get_json(force=True, silent=True) or {}
        else:
            body = {}
        model_id = (
            body.get("model_id")
            or request.args.get("model_id")
            or request.args.get("model")
        )
        target = body.get("target") or request.args.get("target")
        year_raw = body.get("year") if "year" in body else request.args.get("year")
        year = int(year_raw) if year_raw not in (None, "") else None
        tier = body.get("tier") or request.args.get("tier") or "intermediate"
        result = evaluate_model(model_id, target=target, year=year, tier=tier)
        status = 200 if result.get("ok") else 400
        return jsonify(result), status
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


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
        from accor.model_train import (
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
        from accor.model_train import get_build_progress

        return jsonify(get_build_progress())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/model/build/count")
def api_model_build_count():
    """Compte le nombre de modeles (manuel + grid) sans lancer l entrainement."""
    body = request.get_json(force=True, silent=True) or {}
    try:
        from accor.model_train import count_grid_jobs

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
        from accor.model_train import deploy_model

        return jsonify(deploy_model(body.get("model_name") or body.get("id")))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/<model_id>")
def api_model_detail(model_id: str):
    """Métadonnées d'un modèle design."""
    try:
        from accor.model_train import DESIGN_DIR
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
        from accor.model_explore import explore_overview

        return jsonify(explore_overview(model_id))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/<model_id>/tree")
def api_model_tree(model_id: str):
    """Structure d'un arbre (cible principale par défaut)."""
    try:
        from accor.model_explore import get_tree

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
        from accor.model_explore import trees_table

        return jsonify(trees_table(model_id))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/<model_id>/tree-metrics")
def api_model_tree_metrics(model_id: str):
    """Alias → table des arbres."""
    try:
        from accor.model_explore import trees_table

        return jsonify(trees_table(model_id))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/<model_id>/importance")
def api_model_importance(model_id: str):
    """Feature importance (cible principale)."""
    try:
        from accor.model_explore import feature_importance_payload

        return jsonify(feature_importance_payload(model_id))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


# ---------------------------------------------------------------------------
# API — modèle FINAL (stacking enrichi : descriptives + pred_*)
# ---------------------------------------------------------------------------

@app.get("/api/model/final/config")
def api_final_config():
    """Config build final + liste des intermédiaires disponibles."""
    try:
        from accor.model_final import get_final_config_payload

        return jsonify(get_final_config_payload())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/final/list")
def api_final_list():
    try:
        from accor.model_final import (
            get_final_last_trained,
            get_final_top_model,
            list_final_models,
        )

        return jsonify(
            {
                "models": list_final_models(),
                "last_trained": get_final_last_trained(),
                "top_model": get_final_top_model(),
                "tier": "final",
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/model/final/build")
def api_final_build():
    """
    Build modèle final : preds intermédiaires + descriptives → XGB montant_ventes.

    Body : intermediate_model_id, model_name, xgb_params, grid_search, main_target.
    """
    body = request.get_json(force=True, silent=True) or {}
    try:
        from accor.model_final import start_final_build
        from accor.model_train import count_grid_jobs

        grid = body.get("grid_search") or body.get("grid") or {}
        if isinstance(grid, dict):
            grid_norm = {
                k: (v if isinstance(v, list) else [v])
                for k, v in grid.items()
                if v is not None and v != ""
            }
        else:
            grid_norm = {}
        result = start_final_build(
            intermediate_model_id=body.get("intermediate_model_id"),
            model_name=body.get("model_name") or "xgb_final",
            xgb_params=body.get("xgb_params"),
            main_target=body.get("main_target"),
            grid_search=grid_norm or None,
        )
        result["counts"] = count_grid_jobs(body.get("xgb_params"), grid_norm or None)
        return jsonify(result)
    except FileNotFoundError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.get("/api/model/final/build/progress")
def api_final_build_progress():
    try:
        from accor.model_final import get_final_build_progress

        return jsonify(get_final_build_progress())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/model/final/deploy")
def api_final_deploy():
    body = request.get_json(force=True, silent=True) or {}
    try:
        from accor.model_final import deploy_final_model

        return jsonify(deploy_final_model(body.get("model_name") or body.get("id")))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/final/<model_id>/explore")
def api_final_explore(model_id: str):
    try:
        from accor.model_explore import explore_overview

        return jsonify(explore_overview(model_id, tier="final"))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/final/<model_id>/trees")
def api_final_trees(model_id: str):
    try:
        from accor.model_explore import trees_table

        return jsonify(trees_table(model_id, tier="final"))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/final/<model_id>/tree")
def api_final_tree(model_id: str):
    try:
        from accor.model_explore import get_tree

        tree = int(request.args.get("tree", 0))
        return jsonify(get_tree(model_id, tree_index=tree, tier="final"))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/model/final/<model_id>/importance")
def api_final_importance(model_id: str):
    try:
        from accor.model_explore import feature_importance_payload

        return jsonify(feature_importance_payload(model_id, tier="final"))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


# ---------------------------------------------------------------------------
# API — Simulateur ROD (admin : trace pilotes)
# ---------------------------------------------------------------------------

@app.get("/api/rod/pilots")
def api_rod_pilots():
    """
    Pilotes = ventes sur années **train** (avant ``year``).
    ``year`` = année d'éval (hold-out temporel, exclue de la ref).
    """
    try:
        from accor.rod_admin import list_pilot_hotels

        year = int(request.args.get("year") or 2026)
        return jsonify(list_pilot_hotels(year))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.get("/api/rod/meta")
def api_rod_meta():
    """Labels sous-catégories F&B / N-F&B et défauts corner (mix, m_lin)."""
    try:
        from accor.rod_admin import rod_ui_meta

        return jsonify(rod_ui_meta())
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/rod/hotel/<hotel_code>/trace", methods=["GET", "POST"])
def api_rod_hotel_trace(hotel_code: str):
    """
    Simu ROD : ref catégorie train (hors year), corner, 3 concepts + reco.
    Écart vs réel hold-out si dispo. UI admin = POST JSON.

    Body (POST) / query (GET) :
      year, m_lin, mix_fb (0–1 ou %), client_needs {id: bool},
      nb_chambres, taux_occupation, guests_per_chambre
    """
    try:
        from accor.rod_admin import simulate_hotel_trace

        body = {}
        if request.method == "POST":
            body = request.get_json(force=True, silent=True) or {}
        year_raw = body.get("year", request.args.get("year") or 2026)
        year = int(year_raw) if year_raw not in (None, "") else 2026

        def _opt_float(key):
            v = body.get(key, request.args.get(key))
            if v is None or v == "":
                return None
            return float(v)

        needs = body.get("client_needs")
        result = simulate_hotel_trace(
            hotel_code,
            year=year,
            m_lin=_opt_float("m_lin"),
            mix_fb=_opt_float("mix_fb"),
            client_needs=needs if isinstance(needs, dict) else None,
            nb_chambres=_opt_float("nb_chambres"),
            taux_occupation=_opt_float("taux_occupation"),
            guests_per_chambre=_opt_float("guests_per_chambre"),
        )
        status = 200 if result.get("ok") else 400
        return jsonify(result), status
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.get("/api/rod/eval")
def api_rod_eval():
    """
    Batch éval **temporelle** : ref train, vérité = year (ex. 2026).
    MAE / MAPE sur les pilotes qui ont du réel cette année.
    """
    try:
        from accor.rod_admin import evaluate_pilots_year

        year = int(request.args.get("year") or 2026)
        result = evaluate_pilots_year(year)
        status = 200 if result.get("ok") else 400
        return jsonify(result), status
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


# ---------------------------------------------------------------------------
# API — Simulateur Excel (réf. par solution SIMPLY/LIBERTY/CONNECTED)
# ---------------------------------------------------------------------------

@app.get("/api/rod/excel/meta")
def api_rod_excel_meta():
    """Meta UI Excel : commentaires, mapping pilotes, besoins, défauts."""
    try:
        from accor.rod_excel_sim import excel_ui_meta

        return jsonify(excel_ui_meta())
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.get("/api/rod/excel/pilots")
def api_rod_excel_pilots():
    """Pilotes par solution + moyennes (live train + pivots Excel)."""
    try:
        from accor.rod_excel_sim import list_excel_pilots

        year_raw = request.args.get("year")
        year = int(year_raw) if year_raw not in (None, "") else None
        return jsonify(list_excel_pilots(year))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/rod/excel/simulate", methods=["GET", "POST"])
def api_rod_excel_simulate():
    """
    Dual-colonne Excel pour les 3 solutions.

    Body / query :
      hotel_code (requis), year, m_lin, mix_fb, client_needs,
      nb_chambres, taux_occupation, guests_per_chambre,
      pilot_overrides (dict par concept ou plat — colonne pilote éditable)
    """
    try:
        from accor.rod_excel_sim import simulate_excel_dual

        body = {}
        if request.method == "POST":
            body = request.get_json(force=True, silent=True) or {}

        hotel_code = (
            body.get("hotel_code")
            or request.args.get("hotel_code")
            or ""
        )

        def _opt_float(key):
            v = body.get(key, request.args.get(key))
            if v is None or v == "":
                return None
            return float(v)

        needs = body.get("client_needs")
        year_raw = body.get("year", request.args.get("year"))
        year = int(year_raw) if year_raw not in (None, "") else None
        pilot_ov = body.get("pilot_overrides")
        if pilot_ov is not None and not isinstance(pilot_ov, dict):
            pilot_ov = None

        result = simulate_excel_dual(
            str(hotel_code),
            year=year,
            m_lin=_opt_float("m_lin"),
            mix_fb=_opt_float("mix_fb"),
            client_needs=needs if isinstance(needs, dict) else None,
            nb_chambres=_opt_float("nb_chambres"),
            taux_occupation=_opt_float("taux_occupation"),
            guests_per_chambre=_opt_float("guests_per_chambre"),
            pilot_overrides=pilot_ov,
        )
        status = 200 if result.get("ok") else 400
        return jsonify(result), status
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


# ---------------------------------------------------------------------------
# Entrée CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    """
    Point d'entrée serveur Flask admin.

    Par défaut écoute sur ``0.0.0.0`` (LAN + exposable publiquement).
    Override : ``--host 127.0.0.1`` ou env ``ACCOR_HOST`` / ``ACCOR_PORT``.
    """
    import argparse

    from accor.serve_utils import (
        default_host,
        default_port,
        print_listen_banner,
        run_flask_app,
    )

    parser = argparse.ArgumentParser(description="Accor · Data & Model Studio")
    parser.add_argument(
        "--host",
        default=default_host(),
        help="Adresse d'écoute (défaut 0.0.0.0 = toutes interfaces / réseau)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=default_port(5055),
        help="Port HTTP (défaut 5055, ou ACCOR_PORT)",
    )
    parser.add_argument("--debug", action="store_true", help="Mode debug Flask")
    args = parser.parse_args(argv)
    print_listen_banner("Accor · Data & Model Studio (admin)", args.host, args.port)
    run_flask_app(app, host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
