"""
API REST unifiee : tables pipeline, LOO, predictions sim_v1 / sim_v2 / CatBoost.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from flask import Flask, jsonify, request

from src.ml.catboost_model import CatBoostService
from src.pipeline.connection import PipelineFactory
from src.pipeline.paths import Paths
from src.sim_v1.service import SimV1Service
from src.sim_v2.service import SimV2Service


def _clean_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    records = []
    for rec in df.to_dict(orient="records"):
        cleaned = {}
        for key, value in rec.items():
            if value is None or (isinstance(value, float) and pd.isna(value)):
                cleaned[key] = None
            else:
                cleaned[key] = value
        records.append(cleaned)
    return records


def create_api_app(paths: Paths | None = None) -> Flask:
    paths = (paths or Paths()).ensure()
    static_dir = paths.root / "static"
    app = Flask(
        __name__,
        static_folder=str(static_dir) if static_dir.is_dir() else None,
        static_url_path="/static",
    )
    app.config["JSON_AS_ASCII"] = False
    app.config["PATHS"] = paths

    factory = PipelineFactory(paths)
    sim_v1 = SimV1Service(paths, factory)
    sim_v2 = SimV2Service(paths, factory)
    ml = CatBoostService(paths, factory=factory)

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "service": "release_1_0_0",
                "db": str(paths.main_db),
                "db_exists": paths.main_db.exists(),
            }
        )

    @app.get("/api/tables/<name>")
    def table_view(name: str):
        """Expose une table/vue deja materialisee (SELECT *)."""
        cp = factory.open(read_only=False)
        try:
            if not cp.relation_exists(name):
                return jsonify({"ok": False, "error": f"Relation absente : {name}"}), 404
            df = cp.table_view(name).df()
            limit = int(request.args.get("limit", 200))
            return jsonify(
                {
                    "ok": True,
                    "name": name,
                    "rows": _clean_records(df.head(limit)),
                    "total": len(df),
                }
            )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 400
        finally:
            cp.close()

    @app.get("/api/p_tables/<name>")
    def p_table_view(name: str):
        """Construit la relation via process_with_requires puis renvoie le contenu."""
        cp = factory.open(read_only=False)
        try:
            df = cp.p_table_view(name).df()
            limit = int(request.args.get("limit", 200))
            return jsonify(
                {
                    "ok": True,
                    "name": name,
                    "rows": _clean_records(df.head(limit)),
                    "total": len(df),
                }
            )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 400
        finally:
            cp.close()

    @app.get("/api/hotels")
    def hotels():
        try:
            v2 = sim_v2.list_pilot_hotels()
            if v2 is not None and not v2.empty:
                return jsonify({"ok": True, "source": "t_sales", "hotels": _clean_records(v2)})
            v1 = sim_v1.list_hotels()
            return jsonify({"ok": True, "source": "v_hotel_params", "hotels": _clean_records(v1)})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.get("/api/eval/sim_v1")
    def eval_v1():
        path = paths.out_sim_v1("eval_sim_v1_loo.xlsx")
        if not path.exists():
            return jsonify(
                {
                    "ok": False,
                    "error": "Excel introuvable. Lancer : python run.py sim-v1 --rebuild",
                }
            ), 404
        pred = pd.read_excel(path, sheet_name="predictions")
        metrics = pd.read_excel(path, sheet_name="metrics")
        return jsonify(
            {
                "ok": True,
                "source": path.name,
                "predictions": _clean_records(pred),
                "metrics": _clean_records(metrics),
            }
        )

    @app.get("/api/eval/sim_v2")
    def eval_v2():
        path = paths.out_sim_v2("eval_sim_v2_loo.xlsx")
        if not path.exists():
            return jsonify(
                {
                    "ok": False,
                    "error": "Excel introuvable. Lancer : python run.py sim-v2 --rebuild",
                }
            ), 404
        pred = pd.read_excel(path, sheet_name="predictions")
        metrics = pd.read_excel(path, sheet_name="metrics")
        return jsonify(
            {
                "ok": True,
                "source": path.name,
                "predictions": _clean_records(pred),
                "metrics": _clean_records(metrics),
            }
        )

    @app.get("/api/eval/ml")
    def eval_ml():
        path = paths.out_ml("eval_catboost_loo.xlsx")
        if not path.exists():
            return jsonify(
                {
                    "ok": False,
                    "error": "Evaluation ml introuvable. Lancer : python run.py ml --rebuild",
                }
            ), 404
        pred = pd.read_excel(path, sheet_name="predictions")
        metrics = pd.read_excel(path, sheet_name="metrics")
        return jsonify(
            {
                "ok": True,
                "source": "ml",
                "predictions": _clean_records(pred),
                "metrics": _clean_records(metrics),
            }
        )

    @app.post("/api/predict/sim_v1")
    def predict_v1():
        body = request.get_json(force=True) or {}
        code = str(body.get("hotel_code") or "").strip()
        if not code:
            return jsonify({"ok": False, "error": "hotel_code requis"}), 400
        try:
            return jsonify(sim_v1.predict_hotel(code))
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/predict/sim_v2")
    def predict_v2():
        body = request.get_json(force=True) or {}
        try:
            df = sim_v2.predict(
                hotel_nb_chambres=float(body.get("hotel_nb_chambres", 100)),
                hotel_to_annuel=float(body.get("hotel_to_annuel", 0.70)),
                hotel_guests_per_chambre=float(
                    body.get("hotel_guests_per_chambre", 1.7)
                ),
                metres_lineaires=float(body.get("metres_lineaires", 6)),
                type_mix=body.get("type_mix"),
                gamme_mix=body.get("gamme_mix"),
            )
            return jsonify({"ok": True, "model": "sim_v2", "predictions": _clean_records(df)})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/predict/ml")
    def predict_ml():
        body = request.get_json(force=True) or {}
        try:
            solution = str(body.get("solution") or "simply").lower()
            features = {
                "hotel_nb_chambres": float(body.get("hotel_nb_chambres", 100)),
                "hotel_to_annuel": float(body.get("hotel_to_annuel", 0.70)),
                "hotel_guests_per_chambre": float(
                    body.get("hotel_guests_per_chambre", 1.7)
                ),
                "metres_lineaires": float(body.get("metres_lineaires", 6)),
            }
            # mix optionnel : cles deja normalisees type_xxx_part_natures
            for key, value in (body.get("features") or {}).items():
                features[str(key)] = float(value)
            for family, mix in (
                ("type", body.get("type_mix") or {}),
                ("gamme", body.get("gamme_mix") or {}),
            ):
                from src.sim_v2.restitution import normalized_mix_name

                for label, part in mix.items():
                    features[normalized_mix_name(family, str(label))] = float(part)

            pred = ml.predict_row(features, solution)
            return jsonify({"ok": True, "model": "ml", "prediction": pred})
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            # Ne pas exposer le type de modele ML dans l'UI
            for secret in ("CatBoost", "catboost", "XGBoost", "xgboost"):
                msg = msg.replace(secret, "ml")
            return jsonify({"ok": False, "error": msg}), 400

    # ------------------------------------------------------------------ admin datasets
    DATASET_CATALOG = [
        {
            "id": "hotel_brand_data",
            "table": "t_hotel_brand_data",
            "group": "ALL",
            "label": "hotel_brand_data",
            "description": "Marques Accor + logos",
        },
        {
            "id": "hotel_data",
            "table": "t_hotel_data",
            "group": "ALL",
            "label": "hotel_data",
            "description": "Referentiel hotels",
        },
        {
            "id": "hotel_proximity_data",
            "table": "t_hotel_proximity_data",
            "group": "ALL",
            "label": "hotel_proximity_data",
            "description": "Proximite Overpass",
        },
        {
            "id": "hotel_holidays_data",
            "table": "t_hotel_holidays_data",
            "group": "ALL",
            "label": "hotel_holidays_data",
            "description": "Calendriers / feries",
        },
        {
            "id": "hotel_weather_data",
            "table": "t_hotel_weather_data",
            "group": "ALL",
            "label": "hotel_weather_data",
            "description": "Series meteo",
        },
        {
            "id": "sales_raw",
            "table": "t_sales",
            "group": "PILOTE",
            "label": "sales_raw",
            "description": "Ventes pilotes (t_sales)",
        },
    ]

    @app.get("/api/admin/datasets")
    def admin_datasets():
        return jsonify({"ok": True, "datasets": DATASET_CATALOG})

    @app.get("/api/admin/datasets/<dataset_id>")
    def admin_dataset_page(dataset_id: str):
        meta = next((d for d in DATASET_CATALOG if d["id"] == dataset_id), None)
        if not meta:
            return jsonify({"ok": False, "error": f"Dataset inconnu : {dataset_id}"}), 404
        page = max(int(request.args.get("page", 1)), 1)
        page_size = min(max(int(request.args.get("page_size", 50)), 1), 500)
        q = (request.args.get("q") or "").strip().lower()
        cp = factory.open(read_only=False)
        try:
            df = cp.p_table_view(meta["table"]).df()
            total_all = len(df)
            if q and not df.empty:
                mask = pd.Series(False, index=df.index)
                for col in df.columns:
                    mask = mask | df[col].astype(str).str.lower().str.contains(
                        q, na=False, regex=False
                    )
                df = df.loc[mask]
            total = len(df)
            start = (page - 1) * page_size
            chunk = df.iloc[start : start + page_size]
            cols = [str(c) for c in df.columns.tolist()] if total_all else []
            return jsonify(
                {
                    "ok": True,
                    "dataset": meta,
                    "columns": cols,
                    "rows": _clean_records(chunk),
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_all": total_all,
                }
            )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 400
        finally:
            cp.close()

    # ------------------------------------------------------------------ user hotels
    @app.get("/api/user/hotels/search")
    def user_hotel_search():
        """Recherche multi-tokens : ville, marque, code, nom (AND)."""
        q = (request.args.get("q") or "").strip()
        limit = min(max(int(request.args.get("limit", 30)), 1), 100)
        if not q:
            return jsonify({"ok": True, "hotels": [], "q": q})
        tokens = [t for t in q.lower().replace(",", " ").split() if t]
        cp = factory.open(read_only=False)
        try:
            df = cp.p_table_view("t_hotel_data").df()
            if df.empty:
                return jsonify({"ok": True, "hotels": [], "q": q})
            # colonnes de recherche
            for col in (
                "hotel_code",
                "hotel_name",
                "hotel_brand",
                "hotel_city",
                "hotel_country",
            ):
                if col not in df.columns:
                    df[col] = ""
            blob = (
                df["hotel_code"].astype(str)
                + " "
                + df["hotel_name"].astype(str)
                + " "
                + df["hotel_brand"].astype(str)
                + " "
                + df["hotel_city"].astype(str)
                + " "
                + df["hotel_country"].astype(str)
            ).str.lower()
            mask = pd.Series(True, index=df.index)
            for tok in tokens:
                mask = mask & blob.str.contains(tok, na=False, regex=False)
            hit = df.loc[mask].head(limit)
            cols = [
                c
                for c in (
                    "hotel_code",
                    "hotel_name",
                    "hotel_brand",
                    "hotel_city",
                    "hotel_country",
                    "hotel_nb_chambres",
                    "hotel_to_annuel",
                    "hotel_metres_lineaires_dedies_corner",
                )
                if c in hit.columns
            ]
            return jsonify(
                {
                    "ok": True,
                    "q": q,
                    "tokens": tokens,
                    "hotels": _clean_records(hit[cols] if cols else hit),
                }
            )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 400
        finally:
            cp.close()

    @app.get("/api/user/hotels/<hotel_code>")
    def user_hotel_get(hotel_code: str):
        code = str(hotel_code or "").strip()
        cp = factory.open(read_only=False)
        try:
            df = cp.p_table_view("t_hotel_data").df()
            row = df.loc[df["hotel_code"].astype(str) == code]
            if row.empty:
                return jsonify({"ok": False, "error": f"Hotel inconnu : {code}"}), 404
            hotel = _clean_records(row)[0]
            # enrich brand logo if possible
            try:
                brands = cp.p_table_view("t_hotel_brand_data").df()
                brand = str(hotel.get("hotel_brand") or "")
                if not brands.empty and "Marque" in brands.columns:
                    b = brands.loc[
                        brands["Marque"].astype(str).str.upper() == brand.upper()
                    ]
                    if not b.empty:
                        hotel["brand_meta"] = _clean_records(b)[0]
            except Exception:
                pass
            # guests default
            if hotel.get("hotel_guests_per_chambre") is None:
                hotel["hotel_guests_per_chambre"] = 1.7
            if hotel.get("hotel_metres_lineaires_dedies_corner") is None:
                hotel["hotel_metres_lineaires_dedies_corner"] = 6.0
            return jsonify({"ok": True, "hotel": hotel})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 400
        finally:
            cp.close()

    @app.post("/api/user/simulate")
    def user_simulate():
        """
        Simulation multi-moteurs pour un etat hotel en memoire (payload client).

        Body: hotel fields + type_mix + gamme_mix + solutions[] optionnel
        """
        from src.user.business import enrich_prediction_with_costs, recommend

        body = request.get_json(force=True) or {}
        hotel_code = str(body.get("hotel_code") or "").strip()
        nb = float(body.get("hotel_nb_chambres") or 100)
        to = float(body.get("hotel_to_annuel") or 0.7)
        guests = float(body.get("hotel_guests_per_chambre") or 1.7)
        m_lin = float(
            body.get("metres_lineaires")
            or body.get("hotel_metres_lineaires_dedies_corner")
            or 6
        )
        type_mix = body.get("type_mix") or {"F&B": 0.7, "NON F&B": 0.3}
        gamme_mix = body.get("gamme_mix") or {
            "sans alcool": 0.35,
            "food salee": 0.25,
            "food sucree": 0.15,
            "accessoires": 0.15,
            "sos": 0.10,
        }
        solutions = body.get("solutions") or ["simply", "liberty", "connected"]
        solutions = [str(s).lower() for s in solutions]

        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []

        # --- sim_v2 : une restitution multi-solutions ---
        try:
            df = sim_v2.predict(
                hotel_nb_chambres=nb,
                hotel_to_annuel=to,
                hotel_guests_per_chambre=guests,
                metres_lineaires=m_lin,
                type_mix=type_mix,
                gamme_mix=gamme_mix,
            )
            for rec in _clean_records(df):
                sol = str(rec.get("solution") or "").lower()
                if solutions and sol not in solutions:
                    continue
                results.append(
                    enrich_prediction_with_costs(
                        solution=sol,
                        ca_monthly=rec.get("montant_ventes_par_mois_predit"),
                        marge_monthly=rec.get("montant_marge_par_mois_predite"),
                        metres_lineaires=m_lin,
                        engine="sim_v2",
                        extra=rec,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            errors.append({"engine": "sim_v2", "error": str(exc)})

        # --- ml : une prediction par solution ---
        for sol in solutions:
            try:
                features = {
                    "hotel_nb_chambres": nb,
                    "hotel_to_annuel": to,
                    "hotel_guests_per_chambre": guests,
                    "metres_lineaires": m_lin,
                }
                from src.sim_v2.restitution import normalized_mix_name

                for family, mix in (("type", type_mix), ("gamme", gamme_mix)):
                    for label, part in (mix or {}).items():
                        features[normalized_mix_name(family, str(label))] = float(part)
                pred = ml.predict_row(features, sol)
                results.append(
                    enrich_prediction_with_costs(
                        solution=sol,
                        ca_monthly=pred.get("montant_ventes_par_mois"),
                        marge_monthly=pred.get("montant_marge_par_mois"),
                        metres_lineaires=m_lin,
                        engine="ml",
                        extra=pred,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                for secret in ("CatBoost", "catboost"):
                    msg = msg.replace(secret, "ml")
                errors.append({"engine": "ml", "solution": sol, "error": msg})

        # --- sim_v1 : LOO hotel_code (pilotes uniquement) ---
        if hotel_code:
            try:
                pred = sim_v1.predict_hotel(hotel_code)
                if pred.get("ok"):
                    results.append(
                        enrich_prediction_with_costs(
                            solution=str(pred.get("solution") or "simply"),
                            ca_monthly=pred.get("montant_ventes_par_mois"),
                            marge_monthly=pred.get("montant_marge_par_mois"),
                            metres_lineaires=m_lin,
                            engine="sim_v1",
                            extra=pred.get("detail") or pred,
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                errors.append({"engine": "sim_v1", "error": str(exc)})

        reco = recommend(results, nb_chambres=nb)
        return jsonify(
            {
                "ok": True,
                "hotel_code": hotel_code,
                "params": {
                    "hotel_nb_chambres": nb,
                    "hotel_to_annuel": to,
                    "hotel_guests_per_chambre": guests,
                    "metres_lineaires": m_lin,
                    "type_mix": type_mix,
                    "gamme_mix": gamme_mix,
                },
                "results": results,
                "recommendation": reco,
                "errors": errors,
            }
        )

    return app
