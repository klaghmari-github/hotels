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
    app = Flask(__name__)
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
                    "error": "Excel introuvable. Lancer : python run.py ml --rebuild",
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
            return jsonify({"ok": True, "model": "catboost", "prediction": pred})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 400

    return app
