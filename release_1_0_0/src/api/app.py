"""
API REST unifiee : tables pipeline, LOO / full-train, predictions sim_v1 / sim_v2 / ml.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from flask import Flask, jsonify, request, send_file

from src.ml.super_model import SuperModelService
from src.pipeline.connection import PipelineFactory
from src.pipeline.paths import Paths
from src.sim_v1.service import SimV1Service
from src.sim_v2.service import SimV2Service


def _marque_bases(paths: Paths) -> list[Path]:
    """Dossiers candidats pour les logos (data/marques puis static/marques)."""
    return [
        (paths.root / "data" / "marques").resolve(),
        (paths.root / "static" / "marques").resolve(),
        (paths.input / "marques").resolve(),
    ]


def resolve_marque_logo(paths: Paths, relpath: str) -> Path | None:
    """
    Resout logo_path Excel vers un fichier image.

    Accepte : economy/ibis.png, marques/..., data/marques/..., chemin absolu sous base.
    """
    if not relpath:
        return None
    raw = str(relpath).strip().replace("\\", "/")
    if not raw or raw.lower() in {"nan", "none", "null"}:
        return None

    bases = [b for b in _marque_bases(paths) if b.is_dir()]
    if not bases:
        return None

    p = Path(raw)
    if p.is_absolute():
        try:
            target = p.resolve()
            for base in bases:
                try:
                    target.relative_to(base)
                    return target if target.is_file() else None
                except ValueError:
                    continue
        except OSError:
            return None
        return None

    clean = raw.lstrip("/")
    for prefix in (
        "data/marques/",
        "static/marques/",
        "marques/",
        "./data/marques/",
        "./static/marques/",
        "./marques/",
    ):
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix) :]
            break
    if ".." in clean.split("/"):
        return None

    for base in bases:
        target = (base / clean).resolve()
        try:
            target.relative_to(base)
        except ValueError:
            continue
        if target.is_file():
            return target
    return None


def logo_mimetype(path: Path) -> str:
    """
    Content-Type selon le contenu reel.

    Beaucoup de fichiers *.png Accor sont en fait du SVG — image/png casse l'affichage.
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
    ext = path.suffix.lower()
    return {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")


def _clean_value(value: Any) -> Any:
    """Normalise valeurs pandas/numpy pour JSON (pas de NaN / Timestamps bizarres)."""
    if value is None:
        return None
    # listes / arrays (ex. scenario_removed_natures DuckDB LIST)
    if isinstance(value, (list, tuple)):
        return [_clean_value(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_clean_value(v) for v in value.tolist()]
    try:
        # pd.isna sur array renvoie un array → ne pas l'utiliser comme bool
        if not isinstance(value, (list, tuple, dict, np.ndarray)) and pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    # numpy / pandas scalaires
    if hasattr(value, "item") and not isinstance(value, (bytes, str, dict, list)):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float) and pd.isna(value):
        return None
    # dates
    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return value


def _clean_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    # colonnes en str stables (evite cles non-string)
    df = df.copy()
    df.columns = [str(c) for c in df.columns]
    records = []
    for rec in df.to_dict(orient="records"):
        cleaned = {str(key): _clean_value(value) for key, value in rec.items()}
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
    # « ml » = chaîne ml_tc → ml_tc_sim_v2 → ml_ca (SuperModelService)
    ml_super = SuperModelService(paths, factory=factory)
    ml = ml_super  # alias UI / predict

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

    @app.get("/api/marques/logos/<path:relpath>")
    def marque_logo(relpath: str):
        """
        Sert un logo marque.

        URL : /api/marques/logos/economy/ibis_budget.png
        logo_path Excel : economy/ibis_budget.png

        Content-Type detecte sur le contenu (SVG souvent stocke en .png).
        """
        target = resolve_marque_logo(paths, relpath)
        if target is None:
            return jsonify(
                {
                    "ok": False,
                    "error": "logo introuvable",
                    "path": relpath,
                }
            ), 404
        mime = logo_mimetype(target)
        return send_file(target, mimetype=mime, conditional=True, max_age=86400)

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

    def _pilot_m_lin_map() -> dict[str, float]:
        """m_lin pilotes (v_hotel_params) pour couts / amortissement LOO."""
        try:
            cp = factory.open(read_only=True)
            try:
                df = cp.con.execute(
                    """
                    SELECT CAST(hotel_code AS VARCHAR) AS hotel_code,
                           TRY_CAST(m_lin AS DOUBLE) AS m_lin
                    FROM v_hotel_params
                    """
                ).df()
            finally:
                cp.close()
            out: dict[str, float] = {}
            for _, r in df.iterrows():
                code = str(r.get("hotel_code") or "").strip()
                if not code:
                    continue
                try:
                    v = float(r.get("m_lin"))
                except (TypeError, ValueError):
                    v = 6.0
                if not (v > 0):
                    v = 6.0
                out[code] = v
            return out
        except Exception:  # noqa: BLE001
            return {}

    def _eval_economics(
        solution: str,
        marge_monthly: Any,
        metres_lineaires: float,
    ) -> dict[str, Any]:
        """Cout mensuel, ROI (marge ventes − couts), payback."""
        from src.user.business import enrich_prediction_with_costs

        enr = enrich_prediction_with_costs(
            solution=str(solution or "simply"),
            ca_monthly=0.0,
            marge_monthly=(
                float(marge_monthly)
                if marge_monthly is not None and pd.notna(marge_monthly)
                else 0.0
            ),
            metres_lineaires=float(metres_lineaires or 6.0),
        )
        roi_m = enr.get("roi_monthly", enr.get("marge_nette_monthly"))
        return {
            "cout_monthly": enr.get("cout_monthly"),
            "capex": (enr.get("costs") or {}).get("capex"),
            "marge_nette_monthly": roi_m,
            "roi_monthly": roi_m,
            "payback_months": enr.get("payback_months"),
            "payback_years": enr.get("payback_years"),
            "metres_lineaires": float(metres_lineaires or 6.0),
        }

    def _eval_web_payload(engine: str, pred: pd.DataFrame, metrics: pd.DataFrame) -> dict:
        """
        Projection web unifiee (v_web_*) pour l'UI.

        - CA reel / estime / err
        - Marge selon coef (+ err)
        - Cout, ROI (marge ventes − couts), amortissement (mois)
        """
        p = pred.copy()
        web_rows: list[dict[str, Any]] = []
        m_lin_map = _pilot_m_lin_map()

        def _f(row, *keys, default=None):
            for k in keys:
                if k in row and pd.notna(row[k]):
                    return row[k]
            return default

        def _num(v):
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        for _, row in p.iterrows():
            r = row.to_dict()
            if engine == "sim_v1":
                ca_r = _f(r, "ca_reel")
                ca_p = _f(r, "ca_pred")
                ca_e = _f(r, "ca_err_abs")
                m_r = _f(r, "marge_reel")
                m_p = _f(r, "marge_pred")
                m_e = _f(r, "marge_err_abs")
            elif engine == "sim_v2":
                ca_r = _f(r, "montant_ventes_par_mois_reel", "ca_reel")
                ca_p = _f(r, "montant_ventes_par_mois_predit", "ca_pred")
                ca_e = _f(r, "montant_ventes_erreur_absolue", "ca_err_abs")
                m_r = _f(r, "montant_marge_selon_coef_par_mois_reel", "marge_reel")
                m_p = _f(
                    r,
                    "montant_marge_selon_coef_par_mois_predite",
                    "marge_pred",
                )
                m_e = _f(
                    r,
                    "montant_marge_selon_coef_erreur_absolue",
                    "marge_err_abs",
                )
            else:
                ca_r = _f(r, "montant_ventes_par_mois_reel", "ca_reel")
                ca_p = _f(r, "montant_ventes_par_mois_predit", "ca_pred")
                ca_e = _f(
                    r,
                    "montant_ventes_par_mois_erreur_absolue",
                    "ca_err_abs",
                )
                m_r = _f(r, "montant_marge_selon_coef_par_mois_reel", "marge_reel")
                m_p = _f(
                    r,
                    "montant_marge_selon_coef_par_mois_predit",
                    "montant_marge_selon_coef_par_mois_predite",
                    "marge_pred",
                )
                m_e = _f(
                    r,
                    "montant_marge_selon_coef_par_mois_erreur_absolue",
                    "marge_err_abs",
                )
                if m_e is None and m_r is not None and m_p is not None:
                    m_e = abs(float(m_p) - float(m_r))
                if ca_e is None and ca_r is not None and ca_p is not None:
                    ca_e = abs(float(ca_p) - float(ca_r))

            code = str(_f(r, "hotel_code") or "").strip()
            sol = _f(r, "solution")
            m_lin_raw = _f(r, "metres_lineaires", "m_lin")
            try:
                m_lin = float(m_lin_raw) if m_lin_raw is not None else m_lin_map.get(code, 6.0)
            except (TypeError, ValueError):
                m_lin = m_lin_map.get(code, 6.0)
            if not (m_lin > 0):
                m_lin = 6.0

            eco_r = _eval_economics(sol, m_r, m_lin)
            eco_p = _eval_economics(sol, m_p, m_lin)

            web_rows.append(
                {
                    "hotel_code": code,
                    "solution": sol,
                    "metres_lineaires": m_lin,
                    "ca_reel": _num(ca_r),
                    "ca_pred": _num(ca_p),
                    "ca_err_abs": _num(ca_e),
                    "marge_reel": _num(m_r),
                    "marge_pred": _num(m_p),
                    "marge_err_abs": _num(m_e),
                    "cout_monthly": eco_r.get("cout_monthly"),
                    "capex": eco_r.get("capex"),
                    "marge_nette_reel": eco_r.get("roi_monthly"),
                    "marge_nette_pred": eco_p.get("roi_monthly"),
                    "roi_reel": eco_r.get("roi_monthly"),
                    "roi_pred": eco_p.get("roi_monthly"),
                    "payback_months_reel": eco_r.get("payback_months"),
                    "payback_months_pred": eco_p.get("payback_months"),
                    "payback_years_reel": eco_r.get("payback_years"),
                    "payback_years_pred": eco_p.get("payback_years"),
                }
            )

        web_pred = pd.DataFrame(web_rows)
        metric_rows: list[dict[str, Any]] = []
        if engine == "sim_v1":
            for _, m in metrics.iterrows():
                metric_rows.append(
                    {
                        "scope": m.get("scope")
                        or m.get("perimetre")
                        or m.get("solution")
                        or "ALL",
                        "n_hotels": m.get("n_hotels"),
                        "mae_ca": m.get("mae_ca"),
                        "mae_marge": m.get("mae_marge"),
                    }
                )
        elif engine == "sim_v2":
            for _, m in metrics.iterrows():
                # LOO : montant_ventes_mae ; full-train : mae_ca
                scope = m.get("scope")
                if scope is None or (isinstance(scope, float) and pd.isna(scope)):
                    scope = (
                        m.get("solution")
                        if pd.notna(m.get("solution"))
                        else "ALL"
                    )
                metric_rows.append(
                    {
                        "scope": scope if pd.notna(scope) else "ALL",
                        "n_hotels": m.get("nombre_hotels", m.get("n_hotels")),
                        "mae_ca": m.get("montant_ventes_mae", m.get("mae_ca")),
                        "mae_marge": m.get(
                            "marge_selon_coef_mae", m.get("mae_marge")
                        ),
                    }
                )
        else:
            # ml LOO multi-target OU full-train avec mae_ca
            if "mae_ca" in metrics.columns or "montant_ventes_mae" in metrics.columns:
                for _, m in metrics.iterrows():
                    metric_rows.append(
                        {
                            "scope": m.get("scope")
                            if pd.notna(m.get("scope"))
                            else "ALL",
                            "n_hotels": m.get("n_hotels", m.get("nombre_hotels")),
                            "mae_ca": m.get("mae_ca", m.get("montant_ventes_mae")),
                            "mae_marge": m.get("mae_marge", m.get("marge_selon_coef_mae")),
                        }
                    )
            else:
                mae_ca = mae_m = n_h = None
                for _, m in metrics.iterrows():
                    t = str(m.get("target") or "")
                    if t == "montant_ventes_par_mois":
                        mae_ca = m.get("mae")
                        n_h = m.get("nombre_hotels")
                    elif t == "montant_marge_selon_coef_par_mois":
                        mae_m = m.get("mae")
                        n_h = m.get("nombre_hotels")
                metric_rows.append(
                    {
                        "scope": "ALL",
                        "n_hotels": n_h,
                        "mae_ca": mae_ca,
                        "mae_marge": mae_m,
                    }
                )
        # sim_v1 full-train may already use mae_ca
        if engine == "sim_v1" and not metric_rows and not metrics.empty:
            for _, m in metrics.iterrows():
                metric_rows.append(
                    {
                        "scope": m.get("scope")
                        if pd.notna(m.get("scope"))
                        else (m.get("perimetre") or "ALL"),
                        "n_hotels": m.get("n_hotels"),
                        "mae_ca": m.get("mae_ca"),
                        "mae_marge": m.get("mae_marge"),
                    }
                )

        return {
            "predictions": _clean_records(web_pred),
            "metrics": metric_rows,
            "columns": [
                "hotel_code",
                "solution",
                "metres_lineaires",
                "ca_reel",
                "ca_pred",
                "ca_err_abs",
                "marge_reel",
                "marge_pred",
                "marge_err_abs",
                "cout_monthly",
                "capex",
                "marge_nette_reel",
                "marge_nette_pred",
                "roi_reel",
                "roi_pred",
                "payback_months_reel",
                "payback_months_pred",
            ],
            "margin_kind": "selon_coef_reel"
            if engine == "sim_v1"
            else "selon_coef",
            "estimate_kind": (
                "simulation"
                if engine in ("sim_v1", "sim_v2")
                else "prediction"
            ),
            "period": "monthly",
            "period_label": "€ / mois",
        }

    def _eval_file_response(
        engine: str,
        path: Path,
        *,
        mode: str = "loo",
        rebuild_hint: str = "",
    ):
        if not path.exists():
            return jsonify(
                {
                    "ok": False,
                    "error": (
                        f"Excel introuvable ({path.name}). "
                        f"{rebuild_hint or 'Relancer l evaluation.'}"
                    ),
                }
            ), 404
        pred = pd.read_excel(path, sheet_name="predictions")
        try:
            metrics = pd.read_excel(path, sheet_name="metrics")
        except Exception:  # noqa: BLE001
            metrics = pd.DataFrame()
        web = _eval_web_payload(engine, pred, metrics)
        return jsonify(
            {
                "ok": True,
                "source": engine,
                "engine": engine,
                "eval_mode": mode,
                **web,
                "raw_predictions": _clean_records(pred),
                "raw_metrics": _clean_records(metrics),
            }
        )

    @app.get("/api/eval/sim_v1")
    def eval_v1():
        mode = (request.args.get("mode") or "loo").strip().lower()
        if mode in {"full", "full_train", "in_sample"}:
            return _eval_file_response(
                "sim_v1",
                paths.out_sim_v1("eval_sim_v1_full.xlsx"),
                mode="full_train",
                rebuild_hint="python run.py eval-full",
            )
        return _eval_file_response(
            "sim_v1",
            paths.out_sim_v1("eval_sim_v1_loo.xlsx"),
            mode="loo",
            rebuild_hint="python run.py sim-v1 --rebuild",
        )

    @app.get("/api/eval/sim_v2")
    def eval_v2():
        mode = (request.args.get("mode") or "loo").strip().lower()
        if mode in {"full", "full_train", "in_sample"}:
            return _eval_file_response(
                "sim_v2",
                paths.out_sim_v2("eval_sim_v2_full.xlsx"),
                mode="full_train",
                rebuild_hint="python run.py eval-full",
            )
        return _eval_file_response(
            "sim_v2",
            paths.out_sim_v2("eval_sim_v2_loo.xlsx"),
            mode="loo",
            rebuild_hint="python run.py sim-v2 --rebuild",
        )

    def _eval_ml_file(engine: str, filename: str, rebuild_hint: str):
        path = paths.out_ml(filename)
        if not path.exists():
            return jsonify(
                {
                    "ok": False,
                    "error": f"Evaluation {engine} introuvable. Lancer : {rebuild_hint}",
                }
            ), 404
        pred = pd.read_excel(path, sheet_name="predictions")
        metrics = pd.read_excel(path, sheet_name="metrics")
        web = _eval_web_payload(engine, pred, metrics)
        return jsonify(
            {
                "ok": True,
                "source": engine,
                "engine": engine,
                **web,
                "raw_predictions": _clean_records(pred),
                "raw_metrics": _clean_records(metrics),
            }
        )

    @app.get("/api/eval/ml")
    def eval_ml():
        """Éval ML (LOO par défaut, full-train si ?mode=full)."""
        mode = (request.args.get("mode") or "loo").strip().lower()
        if mode in {"full", "full_train", "in_sample"}:
            return _eval_file_response(
                "ml",
                paths.out_ml("eval_ml_full.xlsx"),
                mode="full_train",
                rebuild_hint="python run.py eval-full",
            )
        for name in ("eval_ml_loo.xlsx", "eval_super_loo.xlsx", "eval_catboost_loo.xlsx"):
            path = paths.out_ml(name)
            if path.exists():
                return _eval_ml_file(
                    "ml", name, "python run.py ml --rebuild"
                )
        return _eval_ml_file(
            "ml", "eval_ml_loo.xlsx", "python run.py ml --rebuild"
        )

    def _load_eval_web_engine(
        engine: str, *, mode: str = "loo"
    ) -> dict[str, Any] | None:
        """Charge predictions web normalisees (LOO ou full-train)."""
        full = mode in {"full", "full_train", "in_sample"}
        if engine == "sim_v1":
            path = paths.out_sim_v1(
                "eval_sim_v1_full.xlsx" if full else "eval_sim_v1_loo.xlsx"
            )
            if not path.exists():
                return None
            pred = pd.read_excel(path, sheet_name="predictions")
            try:
                metrics = pd.read_excel(path, sheet_name="metrics")
            except Exception:  # noqa: BLE001
                metrics = pd.DataFrame()
            return {
                "engine": "sim_v1",
                **_eval_web_payload("sim_v1", pred, metrics),
            }
        if engine == "sim_v2":
            path = paths.out_sim_v2(
                "eval_sim_v2_full.xlsx" if full else "eval_sim_v2_loo.xlsx"
            )
            if not path.exists():
                return None
            pred = pd.read_excel(path, sheet_name="predictions")
            try:
                metrics = pd.read_excel(path, sheet_name="metrics")
            except Exception:  # noqa: BLE001
                metrics = pd.DataFrame()
            return {
                "engine": "sim_v2",
                **_eval_web_payload("sim_v2", pred, metrics),
            }
        if full:
            path = paths.out_ml("eval_ml_full.xlsx")
            if path.exists():
                pred = pd.read_excel(path, sheet_name="predictions")
                try:
                    metrics = pd.read_excel(path, sheet_name="metrics")
                except Exception:  # noqa: BLE001
                    metrics = pd.DataFrame()
                return {
                    "engine": "ml",
                    **_eval_web_payload("ml", pred, metrics),
                }
            return None
        for name in ("eval_ml_loo.xlsx", "eval_super_loo.xlsx", "eval_catboost_loo.xlsx"):
            path = paths.out_ml(name)
            if path.exists():
                pred = pd.read_excel(path, sheet_name="predictions")
                metrics = pd.read_excel(path, sheet_name="metrics")
                return {
                    "engine": "ml",
                    **_eval_web_payload("ml", pred, metrics),
                }
        return None

    @app.get("/api/eval/compare")
    def eval_compare():
        """
        Comparaison par hotel : sim_v1 vs sim_v2 vs ml.
        ?mode=loo (defaut) ou ?mode=full (in-sample).
        """
        mode = (request.args.get("mode") or "loo").strip().lower()
        engines = ("sim_v1", "sim_v2", "ml")
        by_hotel: dict[str, dict[str, Any]] = {}
        missing: list[str] = []
        global_metrics: dict[str, Any] = {}

        for eng in engines:
            payload = _load_eval_web_engine(eng, mode=mode)
            if not payload:
                missing.append(eng)
                continue
            # metrics ALL
            mrows = payload.get("metrics") or []
            mae_ca = mae_m = n_h = None
            for m in mrows:
                scope = str(m.get("scope") or "").upper()
                if scope in ("ALL", "NAN", "") or m.get("scope") is None:
                    if m.get("mae_ca") is not None:
                        mae_ca = m.get("mae_ca")
                        n_h = m.get("n_hotels")
                    if m.get("mae_marge") is not None:
                        mae_m = m.get("mae_marge")
            if mae_ca is None and mrows:
                mae_ca = mrows[0].get("mae_ca")
                mae_m = mrows[0].get("mae_marge")
                n_h = mrows[0].get("n_hotels")
            global_metrics[eng] = {
                "mae_ca": mae_ca,
                "mae_marge": mae_m,
                "n_hotels": n_h,
            }
            for rec in payload.get("predictions") or []:
                code = str(rec.get("hotel_code") or "").strip()
                if not code:
                    continue
                row = by_hotel.setdefault(
                    code,
                    {
                        "hotel_code": code,
                        "solution": rec.get("solution"),
                        "ca_reel": rec.get("ca_reel"),
                        "marge_reel": rec.get("marge_reel"),
                        "metres_lineaires": rec.get("metres_lineaires"),
                        "cout_monthly": rec.get("cout_monthly"),
                        "capex": rec.get("capex"),
                        "marge_nette_reel": rec.get("roi_reel", rec.get("marge_nette_reel")),
                        "roi_reel": rec.get("roi_reel", rec.get("marge_nette_reel")),
                        "payback_months_reel": rec.get("payback_months_reel"),
                    },
                )
                if not row.get("solution") and rec.get("solution"):
                    row["solution"] = rec.get("solution")
                if row.get("ca_reel") is None and rec.get("ca_reel") is not None:
                    row["ca_reel"] = rec.get("ca_reel")
                if row.get("marge_reel") is None and rec.get("marge_reel") is not None:
                    row["marge_reel"] = rec.get("marge_reel")
                for k in (
                    "metres_lineaires",
                    "cout_monthly",
                    "capex",
                    "marge_nette_reel",
                    "roi_reel",
                    "payback_months_reel",
                ):
                    if row.get(k) is None and rec.get(k) is not None:
                        row[k] = rec.get(k)
                    if k == "roi_reel" and row.get(k) is None:
                        row[k] = rec.get("marge_nette_reel")
                ca_p = rec.get("ca_pred")
                ca_e = rec.get("ca_err_abs")
                if ca_e is None and ca_p is not None and row.get("ca_reel") is not None:
                    try:
                        ca_e = abs(float(ca_p) - float(row["ca_reel"]))
                    except (TypeError, ValueError):
                        ca_e = None
                m_p = rec.get("marge_pred")
                m_e = rec.get("marge_err_abs")
                if m_e is None and m_p is not None and row.get("marge_reel") is not None:
                    try:
                        m_e = abs(float(m_p) - float(row["marge_reel"]))
                    except (TypeError, ValueError):
                        m_e = None
                row[f"ca_pred_{eng}"] = ca_p
                row[f"ca_err_{eng}"] = ca_e
                row[f"marge_pred_{eng}"] = m_p
                row[f"marge_err_{eng}"] = m_e
                roi_p = rec.get("roi_pred", rec.get("marge_nette_pred"))
                row[f"marge_nette_pred_{eng}"] = roi_p
                row[f"roi_pred_{eng}"] = roi_p
                row[f"payback_months_pred_{eng}"] = rec.get("payback_months_pred")

        # Meilleur moteur par hotel = plus faible |err| CA vs reel
        # (PAS le plus grand CA predit : une surestimation est une mauvaise eval)
        rows_out: list[dict[str, Any]] = []
        for code in sorted(by_hotel.keys()):
            row = by_hotel[code]
            best_eng = None
            best_err = None
            for eng in engines:
                err = row.get(f"ca_err_{eng}")
                if err is None:
                    # recalcule |err| si pred + reel dispo
                    ca_p = row.get(f"ca_pred_{eng}")
                    ca_r = row.get("ca_reel")
                    if ca_p is not None and ca_r is not None:
                        try:
                            err = abs(float(ca_p) - float(ca_r))
                            row[f"ca_err_{eng}"] = err
                        except (TypeError, ValueError):
                            err = None
                if err is None:
                    continue
                try:
                    e = abs(float(err))
                except (TypeError, ValueError):
                    continue
                if best_err is None or e < best_err:
                    best_err = e
                    best_eng = eng
            row["best_ca_engine"] = best_eng
            row["best_ca_err"] = best_err
            rows_out.append(row)

        # ---------- Metriques + meilleur moteur PAR SOLUTION ----------
        # Meilleur = MAE (erreur moyenne abs.) minimale, pas CA predit max.
        def _norm_sol(s: Any) -> str:
            return str(s or "").strip().lower().replace("_", " ")

        def _mean_abs(vals: list[float]) -> float | None:
            if not vals:
                return None
            return float(sum(vals) / len(vals))

        by_solution: dict[str, Any] = {}
        from src.user.business import SOLUTION_DISPLAY_ORDER

        sol_order = SOLUTION_DISPLAY_ORDER  # connected → liberty → simply
        # regrouper les hotels par solution
        hotels_by_sol: dict[str, list[dict[str, Any]]] = {}
        for row in rows_out:
            sol = _norm_sol(row.get("solution"))
            if not sol:
                continue
            hotels_by_sol.setdefault(sol, []).append(row)

        for sol in list(sol_order) + sorted(
            s for s in hotels_by_sol if s not in sol_order
        ):
            hrows = hotels_by_sol.get(sol) or []
            if not hrows:
                continue
            eng_stats: dict[str, Any] = {}
            for eng in engines:
                ca_errs: list[float] = []
                m_errs: list[float] = []
                for r in hrows:
                    ce = r.get(f"ca_err_{eng}")
                    me = r.get(f"marge_err_{eng}")
                    try:
                        if ce is not None:
                            ca_errs.append(float(ce))
                    except (TypeError, ValueError):
                        pass
                    try:
                        if me is not None:
                            m_errs.append(float(me))
                    except (TypeError, ValueError):
                        pass
                eng_stats[eng] = {
                    "mae_ca": _mean_abs(ca_errs),
                    "mae_marge": _mean_abs(m_errs),
                    "n_hotels": len(ca_errs) if ca_errs else len(hrows),
                }

            def _best_key(metric: str) -> str | None:
                best_e = None
                best_v = None
                for eng, st in eng_stats.items():
                    v = st.get(metric)
                    if v is None:
                        continue
                    try:
                        fv = float(v)
                    except (TypeError, ValueError):
                        continue
                    if best_v is None or fv < best_v:
                        best_v = fv
                        best_e = eng
                return best_e

            by_solution[sol] = {
                "solution": sol,
                "n_hotels": len(hrows),
                "hotels": [r.get("hotel_code") for r in hrows],
                "engines": eng_stats,
                "best_ca_engine": _best_key("mae_ca"),
                "best_marge_engine": _best_key("mae_marge"),
            }

        if not rows_out and missing == list(engines):
            return jsonify(
                {
                    "ok": False,
                    "error": (
                        "Aucune eval trouvee. "
                        + (
                            "Lancer : python run.py eval-full"
                            if mode in {"full", "full_train", "in_sample"}
                            else "Lancer sim-v1, sim-v2 et ml (LOO)."
                        )
                    ),
                    "missing": missing,
                    "eval_mode": mode,
                }
            ), 404

        from src.user.business import sort_rows_by_solution

        # Detail par hotel : Connected → Liberty → Simply, puis code hotel
        rows_sorted = sort_rows_by_solution(rows_out)

        return jsonify(
            {
                "ok": True,
                "source": "compare",
                "eval_mode": (
                    "full_train"
                    if mode in {"full", "full_train", "in_sample"}
                    else "loo"
                ),
                "engines": list(engines),
                "missing": missing,
                "period": "monthly",
                "period_label": "€ / mois",
                "global_metrics": global_metrics,
                "by_solution": by_solution,
                "rows": _clean_records(pd.DataFrame(rows_sorted))
                if rows_sorted
                else [],
                "n_hotels": len(rows_sorted),
            }
        )

    @app.get("/api/eval/ml-xgb")
    def eval_ml_xgb():
        """Legacy — alias de /api/eval/ml."""
        return eval_ml()

    @app.get("/api/eval/ml-super")
    def eval_ml_super():
        """Alias de /api/eval/ml."""
        return eval_ml()

    @app.post("/api/predict/sim_v1")
    def predict_v1():
        """
        sim_v1 :
        - avec leviers (chambres/TO/guests/m_lin/mix) → regles Excel pour 1..3 solutions
        - sinon hotel_code pilote → LOO SQL historique
        """
        body = request.get_json(force=True) or {}
        code = str(body.get("hotel_code") or "").strip()
        has_levers = any(
            k in body
            for k in (
                "hotel_nb_chambres",
                "hotel_to_annuel",
                "hotel_guests_per_chambre",
                "metres_lineaires",
                "type_mix",
                "mix_fb",
            )
        )
        try:
            if has_levers or not code:
                sols = body.get("solutions") or body.get("solution")
                if isinstance(sols, str):
                    sols = [sols]
                from src.user.business import sort_rows_by_solution

                rows = sort_rows_by_solution(
                    sim_v1.predict_from_levers(
                        hotel_nb_chambres=float(
                            body.get("hotel_nb_chambres") or 200
                        ),
                        hotel_to_annuel=float(body.get("hotel_to_annuel") or 0.70),
                        hotel_guests_per_chambre=float(
                            body.get("hotel_guests_per_chambre") or 1.7
                        ),
                        metres_lineaires=float(
                            body.get("metres_lineaires") or 6
                        ),
                        type_mix=body.get("type_mix"),
                        gamme_mix=body.get("gamme_mix"),
                        nb_frigos_froid=float(
                            body.get("nb_frigos_froid")
                            or body.get("nb_frigos")
                            or 3
                        ),
                        solutions=sols,
                        hotel_code=code or None,
                        mix_fb=body.get("mix_fb"),
                    )
                )
                return jsonify(
                    {
                        "ok": True,
                        "model": "sim_v1",
                        "predictions": rows,
                        "prediction": rows[0] if len(rows) == 1 else None,
                    }
                )
            return jsonify(sim_v1.predict_hotel(code))
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/predict/sim_v2")
    def predict_v2():
        body = request.get_json(force=True) or {}
        try:
            from src.user.business import sort_rows_by_solution

            df = sim_v2.predict(
                hotel_nb_chambres=float(body.get("hotel_nb_chambres", 200)),
                hotel_to_annuel=float(body.get("hotel_to_annuel", 0.70)),
                hotel_guests_per_chambre=float(
                    body.get("hotel_guests_per_chambre", 1.7)
                ),
                metres_lineaires=float(body.get("metres_lineaires", 6)),
                type_mix=body.get("type_mix"),
                gamme_mix=body.get("gamme_mix"),
            )
            preds = sort_rows_by_solution(_clean_records(df))
            return jsonify({"ok": True, "model": "sim_v2", "predictions": preds})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 400

    def _features_from_body(body: dict) -> tuple[str, dict[str, float]]:
        solution = str(body.get("solution") or "simply").lower()
        features = {
            "hotel_nb_chambres": float(body.get("hotel_nb_chambres", 200)),
            "hotel_to_annuel": float(body.get("hotel_to_annuel", 0.70)),
            "hotel_guests_per_chambre": float(
                body.get("hotel_guests_per_chambre", 1.7)
            ),
            "metres_lineaires": float(body.get("metres_lineaires", 6)),
        }
        for key, value in (body.get("features") or {}).items():
            features[str(key)] = float(value)
        from src.sim_v2.restitution import normalized_mix_name

        for family, mix in (
            ("type", body.get("type_mix") or {}),
            ("gamme", body.get("gamme_mix") or {}),
        ):
            for label, part in (mix or {}).items():
                features[normalized_mix_name(family, str(label))] = float(part)
        return solution, features

    @app.post("/api/predict/ml")
    def predict_ml():
        """Prediction = super-modele (sim_v2 + xgb base)."""
        body = request.get_json(force=True) or {}
        try:
            solution, features = _features_from_body(body)
            pred = ml_super.predict_row(
                features,
                solution,
                hotel_code=str(body.get("hotel_code") or "").strip() or None,
                type_mix=body.get("type_mix"),
                gamme_mix=body.get("gamme_mix"),
            )
            return jsonify({"ok": True, "model": "ml", "prediction": pred})
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            for secret in ("CatBoost", "catboost", "XGBoost", "xgboost", "super"):
                msg = msg.replace(secret, "ml")
            return jsonify({"ok": False, "error": msg}), 400

    @app.post("/api/predict/ml-xgb")
    def predict_ml_xgb():
        """Legacy — alias de /api/predict/ml."""
        return predict_ml()

    @app.post("/api/predict/ml-super")
    def predict_ml_super():
        """Alias de /api/predict/ml."""
        return predict_ml()

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
            "description": "Ventes pilotes tickets (t_sales)",
        },
        {
            "id": "sales_obs",
            "table": "v_web_sales_obs",
            "group": "PILOTE",
            "label": "sales_obs",
            "description": "Observation sim_v2 — CA/marge mensuels (baseline)",
        },
        {
            "id": "sim_scenarios",
            "table": "v_web_sales_sim_scenarios",
            "group": "PILOTE",
            "label": "sim_scenarios",
            "description": "Definitions scenarios retrait (~1780)",
        },
        {
            "id": "sales_sim",
            "table": "v_web_sales_sim",
            "group": "PILOTE",
            "label": "sales_sim",
            "description": "Simulations sim_v2 — CA/marge mensuels (scenarios)",
        },
    ]

    # Catalogue restreint pour la doc user (popups schema) — lecture seule publique
    DOC_DATASET_CATALOG = [
        {
            "id": "t_sales",
            "table": "t_sales",
            "label": "t_sales",
            "description": "Tickets pilotes",
        },
        {
            "id": "t_scenarios",
            "table": "t_scenarios",
            "label": "t_scenarios",
            "description": "Definitions des scenarios (retraits de natures)",
        },
        {
            "id": "sim_scenarios",
            "table": "v_web_sales_sim_scenarios",
            "label": "sim_scenarios",
            "description": "Scenarios (vue web)",
        },
        {
            "id": "t_dataset_pivot",
            "table": "t_dataset_pivot",
            "label": "t_dataset_pivot",
            "description": "Scenarios × hotels pilotes (obs + sim)",
        },
        {
            "id": "sales_sim",
            "table": "v_web_sales_sim",
            "label": "sales_sim",
            "description": "Simulations (vue legere scenario × hotel)",
        },
        {
            "id": "sales_obs",
            "table": "v_web_sales_obs",
            "label": "sales_obs",
            "description": "Observations baseline par hotel pilote",
        },
        {
            "id": "coeffs",
            "table": "v_restitution_solution_coefficients",
            "label": "coeffs",
            "description": "Coefficients unitaires par solution",
        },
        {
            "id": "conversion",
            "table": "v_solution_conversion_rate",
            "label": "conversion",
            "description": "Taux de conversion moyen par solution",
        },
        {
            "id": "pilot_concepts",
            "table": "t_pilot_concepts",
            "label": "t_pilot_concepts",
            "description": "Mapping hotel ↔ solution pilote",
        },
    ]

    def _dataset_page_response(catalog: list[dict], dataset_id: str):
        """Pagination SQL partagee admin / doc."""
        meta = next((d for d in catalog if d["id"] == dataset_id), None)
        if not meta:
            return jsonify({"ok": False, "error": f"Dataset inconnu : {dataset_id}"}), 404
        page = max(int(request.args.get("page", 1)), 1)
        page_size = min(max(int(request.args.get("page_size", 50)), 1), 200)
        q = (request.args.get("q") or "").strip()
        table = str(meta["table"])

        cp = None
        last_err: Exception | None = None
        for read_only in (True, False):
            try:
                cp = factory.open(read_only=read_only)
                break
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                cp = None
        if cp is None:
            return jsonify(
                {
                    "ok": False,
                    "error": f"Connexion DuckDB impossible : {last_err}",
                }
            ), 503

        try:
            try:
                cp.p_table_view(table)
            except Exception:
                pass

            try:
                desc = cp.con.execute(f'DESCRIBE "{table}"').fetchall()
                cols = [str(r[0]) for r in desc]
            except Exception:
                cols = [
                    str(r[0])
                    for r in cp.con.execute(
                        """
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name = ?
                        ORDER BY ordinal_position
                        """,
                        [table],
                    ).fetchall()
                ]
            if not cols:
                return jsonify(
                    {"ok": False, "error": f"Relation introuvable : {table}"}
                ), 404

            total_all = int(
                cp.con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            )

            where_sql = ""
            params: list[Any] = []
            if q:
                clauses = []
                for c in cols[:40]:
                    clauses.append(f'CAST("{c}" AS VARCHAR) ILIKE ?')
                    params.append(f"%{q}%")
                where_sql = " WHERE (" + " OR ".join(clauses) + ")"

            count_sql = f'SELECT COUNT(*) FROM "{table}"{where_sql}'
            total = int(cp.con.execute(count_sql, params).fetchone()[0])

            offset = (page - 1) * page_size
            order_col = cols[0]
            data_sql = (
                f'SELECT * FROM "{table}"{where_sql} '
                f'ORDER BY "{order_col}" '
                f"LIMIT ? OFFSET ?"
            )
            chunk = cp.con.execute(
                data_sql, [*params, page_size, offset]
            ).df()
            chunk.columns = [str(c) for c in chunk.columns]
            rows = _clean_records(chunk)
            for rec in rows:
                for c in cols:
                    rec.setdefault(c, None)

            return jsonify(
                {
                    "ok": True,
                    "dataset": meta,
                    "columns": cols,
                    "rows": rows,
                    "page": page,
                    "page_size": page_size,
                    "total": int(total),
                    "total_all": int(total_all),
                }
            )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 400
        finally:
            try:
                cp.close()
            except Exception:
                pass

    @app.get("/api/admin/datasets")
    def admin_datasets():
        return jsonify({"ok": True, "datasets": DATASET_CATALOG})

    @app.get("/api/admin/datasets/<dataset_id>")
    def admin_dataset_page(dataset_id: str):
        """
        Page de dataset admin — pagination SQL (evite de charger toute la table
        en RAM, source frequente de timeouts / Failed to fetch).
        """
        return _dataset_page_response(DATASET_CATALOG, dataset_id)

    @app.get("/api/doc/datasets")
    def doc_datasets():
        """Catalogue des tables exposees dans la documentation (popups schema)."""
        return jsonify({"ok": True, "datasets": DOC_DATASET_CATALOG})

    @app.get("/api/doc/datasets/<dataset_id>")
    def doc_dataset_page(dataset_id: str):
        """Lecture paginee publique pour popups de la doc user."""
        return _dataset_page_response(DOC_DATASET_CATALOG, dataset_id)

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

    def _as_float(v: Any, default: float | None = None) -> float | None:
        if v is None:
            return default
        try:
            if isinstance(v, float) and pd.isna(v):
                return default
            x = float(v)
            if pd.isna(x):
                return default
            return x
        except (TypeError, ValueError):
            return default

    def _normalize_to(v: Any, default: float = 0.70) -> float:
        """TO annuel en ratio 0-1 (accepte aussi % 1-100)."""
        x = _as_float(v, default)
        if x is None:
            return default
        if x > 1.5:  # stocke en pourcentage
            x = x / 100.0
        return max(0.01, min(1.0, x))

    @app.get("/api/user/hotels/<hotel_code>")
    def user_hotel_get(hotel_code: str):
        """Hotel enrichi (brand + proximity) + leviers pre-remplis (defaults si manquants)."""
        code = str(hotel_code or "").strip()
        cp = factory.open(read_only=False)
        try:
            df = cp.p_table_view("t_hotel_data").df()
            row = df.loc[df["hotel_code"].astype(str) == code]
            if row.empty:
                return jsonify({"ok": False, "error": f"Hotel inconnu : {code}"}), 404
            hotel = _clean_records(row)[0]

            # brand
            brand_meta = None
            try:
                brands = cp.p_table_view("t_hotel_brand_data").df()
                brand = str(hotel.get("hotel_brand") or "")
                if not brands.empty and "Marque" in brands.columns and brand:
                    b = brands.loc[
                        brands["Marque"].astype(str).str.upper() == brand.upper()
                    ]
                    if b.empty:
                        b = brands.loc[
                            brands["Marque"]
                            .astype(str)
                            .str.upper()
                            .str.contains(brand.upper()[:8], na=False)
                        ]
                    if not b.empty:
                        brand_meta = _clean_records(b)[0]
                        hotel["brand_meta"] = brand_meta
            except Exception:
                pass

            # proximity (resume utile)
            proximity = None
            try:
                px = cp.p_table_view("t_hotel_proximity_data").df()
                if "hotel_code" in px.columns:
                    p = px.loc[px["hotel_code"].astype(str) == code]
                    if not p.empty:
                        proximity = _clean_records(p)[0]
                        hotel["proximity"] = proximity
            except Exception:
                pass

            # leviers simulation (defaults si NaN en base — cas frequent hors pilotes)
            nb = _as_float(hotel.get("hotel_nb_chambres"), 200.0) or 200.0
            to = _normalize_to(hotel.get("hotel_to_annuel"), 0.70)
            guests = _as_float(hotel.get("hotel_guests_per_chambre"), 1.7) or 1.7
            m_lin = (
                _as_float(hotel.get("hotel_metres_lineaires_dedies_corner"), 6.0) or 6.0
            )
            defaults_used = {
                "hotel_nb_chambres": hotel.get("hotel_nb_chambres") is None,
                "hotel_to_annuel": hotel.get("hotel_to_annuel") is None,
                "hotel_guests_per_chambre": hotel.get("hotel_guests_per_chambre")
                is None,
                "metres_lineaires": hotel.get("hotel_metres_lineaires_dedies_corner")
                is None,
            }
            hotel["hotel_nb_chambres"] = nb
            hotel["hotel_to_annuel"] = to
            hotel["hotel_guests_per_chambre"] = guests
            hotel["hotel_metres_lineaires_dedies_corner"] = m_lin
            hotel["metres_lineaires"] = m_lin

            # sections pour l'UI (lecture / edition legere)
            identity = {
                "hotel_code": hotel.get("hotel_code"),
                "hotel_name": hotel.get("hotel_name"),
                "hotel_brand": hotel.get("hotel_brand"),
                "hotel_adresse_postale_1": hotel.get("hotel_adresse_postale_1"),
                "hotel_adresse_postale_2": hotel.get("hotel_adresse_postale_2"),
                "hotel_code_postal": hotel.get("hotel_code_postal"),
                "hotel_city": hotel.get("hotel_city"),
                "hotel_country": hotel.get("hotel_country"),
                "hotel_lat": hotel.get("hotel_lat"),
                "hotel_lon": hotel.get("hotel_lon"),
                "logo_path": (brand_meta or {}).get("logo_path"),
            }
            exploitation = {
                "hotel_nb_chambres": nb,
                "hotel_to_annuel": to,
                "hotel_guests_per_chambre": guests,
                "hotel_to_le_plus_bas_taux": _as_float(
                    hotel.get("hotel_to_le_plus_bas_taux")
                ),
                "hotel_to_le_plus_haut_taux": _as_float(
                    hotel.get("hotel_to_le_plus_haut_taux")
                ),
                "hotel_contrat_signe_annee": hotel.get("hotel_contrat_signe_annee"),
                "hotel_derniere_reno": hotel.get("hotel_derniere_reno"),
            }
            services = {
                "hotel_f_b_restaurant": hotel.get("hotel_f_b_restaurant"),
                "hotel_f_b_bar": hotel.get("hotel_f_b_bar"),
                "hotel_f_b_minibar": hotel.get("hotel_f_b_minibar"),
                "hotel_f_b_room_service": hotel.get("hotel_f_b_room_service"),
                "hotel_non_f_b_piscine": hotel.get("hotel_non_f_b_piscine"),
                "hotel_non_f_b_salle_de_sport": hotel.get(
                    "hotel_non_f_b_salle_de_sport"
                ),
                "hotel_non_f_b_salles_de_reunion": hotel.get(
                    "hotel_non_f_b_salles_de_reunion"
                ),
                "hotel_non_f_b_spa": hotel.get("hotel_non_f_b_spa"),
                "hotel_has_parking": hotel.get("hotel_has_parking"),
                "hotel_has_wifi": hotel.get("hotel_has_wifi"),
                "hotel_has_clim": hotel.get("hotel_has_clim"),
                "hotel_has_petit_dejeuner": hotel.get("hotel_has_petit_dejeuner"),
            }
            # resume prox editable (compteurs 500m + plage 500m)
            prox_summary: dict[str, Any] = {
                "commerce_supermarket_500m": 0,
                "commerce_bakery_500m": 0,
                "commerce_fast_food_500m": 0,
                "plage_500m": 0,
            }
            if proximity:
                for k in (
                    "commerce_supermarket_500m",
                    "commerce_bakery_500m",
                    "commerce_fast_food_500m",
                ):
                    if k in proximity and proximity[k] is not None:
                        try:
                            prox_summary[k] = max(0, int(float(proximity[k])))
                        except (TypeError, ValueError):
                            prox_summary[k] = 0
                dist = proximity.get("plage_distance_km")
                plage_500 = 0
                try:
                    if dist is not None and float(dist) <= 0.5:
                        # 0 km ou <= 500 m = plage a proximite
                        plage_500 = 1
                except (TypeError, ValueError):
                    plage_500 = 0
                prox_summary["plage_500m"] = plage_500
                if dist is not None:
                    try:
                        prox_summary["plage_distance_km"] = float(dist)
                    except (TypeError, ValueError):
                        pass

            # Mix hierarchique : type F&B/Non F&B + gammes par famille (UI user)
            gamme_mix_fb = {
                "sans alcool": 0.40,
                "food salee": 0.28,
                "food sucree": 0.18,
                "alcool": 0.10,
                "formule": 0.04,
            }
            gamme_mix_nfb = {
                "accessoires": 0.35,
                "sos": 0.30,
                "cosmetique": 0.12,
                "pap": 0.10,
                "jeux enfants": 0.08,
                "souvenirs": 0.05,
            }
            type_mix = {"F&B": 0.7, "NON F&B": 0.3}
            # plat pour moteurs (somme ~1) : poids type x mix famille
            gamme_mix = {
                **{k: 0.7 * v for k, v in gamme_mix_fb.items()},
                **{k: 0.3 * v for k, v in gamme_mix_nfb.items()},
            }
            levers = {
                "hotel_nb_chambres": nb,
                "hotel_to_annuel": to,
                "hotel_guests_per_chambre": guests,
                "metres_lineaires": m_lin,
                "type_mix": type_mix,
                "gamme_mix_fb": gamme_mix_fb,
                "gamme_mix_nfb": gamme_mix_nfb,
                "gamme_mix": gamme_mix,
            }

            return jsonify(
                {
                    "ok": True,
                    "hotel": hotel,
                    "identity": identity,
                    "exploitation": exploitation,
                    "services": services,
                    "proximity_summary": prox_summary,
                    "levers": levers,
                    "defaults_used": defaults_used,
                }
            )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 400
        finally:
            cp.close()

    def _ram_feature_overrides(
        services: dict[str, Any] | None,
        proximity: dict[str, Any] | None,
    ) -> dict[str, float]:
        """
        Mappe services / proximite UI → features modeles (hd_ / px_).
        Modifications RAM uniquement (jamais ecrites en base).
        """
        out: dict[str, float] = {}
        for k, v in (services or {}).items():
            key = str(k)
            try:
                val = 1.0 if v in (True, 1, "1") or (
                    isinstance(v, (int, float)) and float(v) > 0
                ) else 0.0
            except (TypeError, ValueError):
                val = 0.0
            out[key] = val
            out[f"hd_{key}"] = val
        for k, v in (proximity or {}).items():
            key = str(k)
            try:
                val = float(v)
            except (TypeError, ValueError):
                continue
            out[key] = val
            if key.startswith("commerce_"):
                out[f"px_{key}"] = val
            if key == "plage_500m":
                # pas de colonne native 500m : oriente plage_1km / distance
                out["px_plage_1km"] = 1.0 if val > 0 else 0.0
                if val > 0:
                    out["px_plage_distance_km"] = min(
                        float(out.get("px_plage_distance_km") or 0.5), 0.5
                    )
            if key == "plage_distance_km":
                out["px_plage_distance_km"] = val
        return out

    def _evaluate_engines(
        *,
        nb: float,
        to: float,
        guests: float,
        m_lin: float,
        type_mix: dict[str, Any],
        gamme_mix: dict[str, Any],
        solutions: list[str],
        hotel_code: str | None = None,
        frigos: float = 3.0,
        services: dict[str, Any] | None = None,
        proximity: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        """Evalue sim_v1 + sim_v2 + ml pour un jeu de leviers / mix (+ overrides RAM)."""
        from src.user.business import enrich_prediction_with_costs
        from src.sim_v2.restitution import normalized_mix_name
        from src.user.optimize import normalize_mix_exact

        # Garde-fou : type / gamme toujours somme exacte 1 (jamais d'alerte sim_v2
        # pour un residu float ou un mix UI non renorme).
        type_mix = normalize_mix_exact(
            type_mix, {"F&B": 0.7, "NON F&B": 0.3}
        )
        gamme_mix = normalize_mix_exact(
            gamme_mix,
            {
                "sans alcool": 0.28,
                "food salee": 0.20,
                "food sucree": 0.12,
                "alcool": 0.07,
                "formule": 0.03,
                "accessoires": 0.10,
                "sos": 0.09,
                "cosmetique": 0.04,
                "pap": 0.03,
                "jeux enfants": 0.02,
                "souvenirs": 0.02,
            },
        )

        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        ram_overrides = _ram_feature_overrides(services, proximity)

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
                        marge_monthly=rec.get(
                            "montant_marge_selon_coef_par_mois_predite"
                        )
                        or rec.get("montant_marge_par_mois_predite"),
                        metres_lineaires=m_lin,
                        engine="sim_v2",
                        extra=rec,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            errors.append({"engine": "sim_v2", "error": str(exc)})

        def _mix_features() -> dict[str, float]:
            features: dict[str, float] = {
                "hotel_nb_chambres": nb,
                "hotel_to_annuel": to,
                "hotel_guests_per_chambre": guests,
                "metres_lineaires": m_lin,
            }
            for family, mix in (("type", type_mix), ("gamme", gamme_mix)):
                for label, part in (mix or {}).items():
                    features[normalized_mix_name(family, str(label))] = float(part)
            # overrides services / prox (RAM) — prioritaires sur defaults
            features.update(ram_overrides)
            return features

        # ml = chaîne ml_tc → ml_tc_sim_v2 → ml_ca — pas ml1/ml2 en UI
        for sol in solutions:
            try:
                pred = ml_super.predict_row(
                    _mix_features(),
                    sol,
                    hotel_code=hotel_code,
                    type_mix=type_mix,
                    gamme_mix=gamme_mix,
                )
                results.append(
                    enrich_prediction_with_costs(
                        solution=sol,
                        ca_monthly=pred.get("montant_ventes_par_mois"),
                        marge_monthly=pred.get("montant_marge_selon_coef_par_mois")
                        or pred.get("montant_marge_par_mois"),
                        metres_lineaires=m_lin,
                        engine="ml",
                        extra=pred,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                for secret in ("CatBoost", "catboost", "XGBoost", "xgboost", "super"):
                    msg = msg.replace(secret, "ml")
                errors.append({"engine": "ml", "solution": sol, "error": msg})

        try:
            v1_rows = sim_v1.predict_from_levers(
                hotel_nb_chambres=nb,
                hotel_to_annuel=to,
                hotel_guests_per_chambre=guests,
                metres_lineaires=m_lin,
                type_mix=type_mix,
                gamme_mix=gamme_mix,
                nb_frigos_froid=frigos,
                solutions=solutions,
                hotel_code=hotel_code or None,
            )
            for pred in v1_rows:
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

        return results, errors

    @app.post("/api/user/simulate")
    def user_simulate():
        """
        Estimation multi-moteurs pour un etat hotel en memoire (payload client).

        Body: hotel fields + type_mix + gamme_mix + solutions[] optionnel
        """
        from src.user.business import recommend

        body = request.get_json(force=True) or {}
        hotel_code = str(body.get("hotel_code") or "").strip()
        nb = float(body.get("hotel_nb_chambres") or 200)
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
        from src.user.business import SOLUTION_DISPLAY_ORDER

        solutions = body.get("solutions") or list(SOLUTION_DISPLAY_ORDER)
        solutions = [str(s).lower() for s in solutions]
        frigos = float(body.get("nb_frigos_froid") or body.get("nb_frigos") or 3)
        services = body.get("services") if isinstance(body.get("services"), dict) else {}
        proximity = (
            body.get("proximity") if isinstance(body.get("proximity"), dict) else {}
        )

        results, errors = _evaluate_engines(
            nb=nb,
            to=to,
            guests=guests,
            m_lin=m_lin,
            type_mix=type_mix,
            gamme_mix=gamme_mix,
            solutions=solutions,
            hotel_code=hotel_code or None,
            frigos=frigos,
            services=services,
            proximity=proximity,
        )

        from src.user.business import sort_rows_by_solution

        results = sort_rows_by_solution(results)
        by_engine: dict[str, Any] = {}
        for eng in ("sim_v1", "sim_v2", "ml"):
            eng_rows = sort_rows_by_solution(
                [r for r in results if r.get("engine") == eng]
            )
            by_engine[eng] = {
                "results": eng_rows,
                "recommendation": recommend(eng_rows, nb_chambres=nb)
                if eng_rows
                else {
                    "recommended": None,
                    "reason": "Pas de prediction pour ce moteur.",
                    "warnings": [],
                },
            }

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
                "by_engine": by_engine,
                "errors": errors,
            }
        )

    @app.post("/api/user/recommend_mix")
    def user_recommend_mix():
        """
        Assortiment optimal : densite produits/m_lin × top N par rang de marge.
        Ne calcule pas le CA (voir /api/user/optimize method=product_rank).
        """
        body = request.get_json(force=True) or {}
        solution = str(body.get("solution") or "SIMPLY").strip().upper()
        m_lin = float(body.get("metres_lineaires") or 6)
        allowed_types = body.get("allowed_types")
        allowed_gammes = body.get("allowed_gammes")
        try:
            out = sim_v2.recommend_optimal_mix(
                solution=solution,
                metres_lineaires=m_lin,
                allowed_types=allowed_types,
                allowed_gammes=allowed_gammes,
            )
            return jsonify(out)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.get("/api/user/product_exposure")
    def user_product_exposure():
        """nombre_produits_distincts et produits_par_m_lin par hotel pilote."""
        try:
            df = sim_v2.product_exposure()
            return jsonify(
                {
                    "ok": True,
                    "rows": _clean_records(df),
                }
            )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 400

    def _parse_optimize_body(body: dict) -> dict:
        hotel_code = str(body.get("hotel_code") or "").strip()
        nb = float(body.get("hotel_nb_chambres") or 200)
        to = float(body.get("hotel_to_annuel") or 0.7)
        guests = float(body.get("hotel_guests_per_chambre") or 1.7)
        m_lin = float(body.get("metres_lineaires") or 6)
        type_mix = body.get("type_mix") or {"F&B": 0.7, "NON F&B": 0.3}
        gamme_mix_fb = body.get("gamme_mix_fb") or {
            "sans alcool": 0.40,
            "food salee": 0.28,
            "food sucree": 0.18,
            "alcool": 0.10,
            "formule": 0.04,
        }
        gamme_mix_nfb = body.get("gamme_mix_nfb") or {
            "accessoires": 0.35,
            "sos": 0.30,
            "cosmetique": 0.12,
            "pap": 0.10,
            "jeux enfants": 0.08,
            "souvenirs": 0.05,
        }
        from src.user.business import SOLUTION_DISPLAY_ORDER

        solutions = body.get("solutions") or list(SOLUTION_DISPLAY_ORDER)
        solutions = [str(s).lower() for s in solutions]
        frigos = float(body.get("nb_frigos_froid") or body.get("nb_frigos") or 3)
        step = float(body.get("step") or 0.1)
        services = body.get("services") if isinstance(body.get("services"), dict) else {}
        proximity = (
            body.get("proximity") if isinstance(body.get("proximity"), dict) else {}
        )
        method = str(body.get("method") or "product_rank").strip().lower()
        return {
            "hotel_code": hotel_code,
            "nb": nb,
            "to": to,
            "guests": guests,
            "m_lin": m_lin,
            "type_mix": type_mix,
            "gamme_mix_fb": gamme_mix_fb,
            "gamme_mix_nfb": gamme_mix_nfb,
            "solutions": solutions,
            "frigos": frigos,
            "step": step,
            "services": services,
            "proximity": proximity,
            "method": method,
        }

    def _run_optimize_core(p: dict, progress_cb=None) -> dict:
        from src.user.optimize import (
            run_mix_optimization,
            run_product_rank_optimization,
        )

        def evaluate_fn(**kw):
            rows, _errs = _evaluate_engines(
                nb=p["nb"],
                to=p["to"],
                guests=p["guests"],
                m_lin=p["m_lin"],
                type_mix=kw["type_mix"],
                gamme_mix=kw["gamme_mix"],
                solutions=p["solutions"],
                hotel_code=p["hotel_code"] or None,
                frigos=p["frigos"],
                services=p["services"],
                proximity=p["proximity"],
            )
            return rows

        if p["method"] == "grid":
            return run_mix_optimization(
                hotel_nb_chambres=p["nb"],
                hotel_to_annuel=p["to"],
                hotel_guests_per_chambre=p["guests"],
                metres_lineaires=p["m_lin"],
                type_mix=p["type_mix"],
                gamme_mix_fb=p["gamme_mix_fb"],
                gamme_mix_nfb=p["gamme_mix_nfb"],
                hotel_code=p["hotel_code"] or None,
                solutions=p["solutions"],
                evaluate_fn=evaluate_fn,
                step=p["step"],
                progress_cb=progress_cb,
            )
        return run_product_rank_optimization(
            hotel_nb_chambres=p["nb"],
            hotel_to_annuel=p["to"],
            hotel_guests_per_chambre=p["guests"],
            metres_lineaires=p["m_lin"],
            type_mix=p["type_mix"],
            gamme_mix_fb=p["gamme_mix_fb"],
            gamme_mix_nfb=p["gamme_mix_nfb"],
            hotel_code=p["hotel_code"] or None,
            solutions=[s.upper() for s in p["solutions"]],
            evaluate_fn=evaluate_fn,
            recommend_fn=lambda **kw: sim_v2.recommend_optimal_mix(**kw),
            progress_cb=progress_cb,
        )

    @app.post("/api/user/optimize")
    def user_optimize():
        """
        Optimisation mix (synchrone, compat).

        method=product_rank (defaut) : top produits par marge / m_lin puis CA.
        method=grid : balayage 10 % type + gammes (historique).

        Preferez POST /api/user/jobs/optimize + GET /api/user/jobs/<id>
        pour une barre de progression reelle.
        """
        body = request.get_json(force=True) or {}
        try:
            p = _parse_optimize_body(body)
            out = _run_optimize_core(p)
            return jsonify(out)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/user/jobs/optimize")
    def user_jobs_optimize_start():
        """
        Demarre l'estimation/optimisation en tache de fond.
        Retourne job_id ; poller GET /api/user/jobs/<job_id>.
        """
        import threading

        from src.user.jobs import JOB_STORE

        body = request.get_json(force=True) or {}
        try:
            p = _parse_optimize_body(body)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 400

        n_sol = max(len(p["solutions"]), 1)
        # estimation product_rank : 1 + n_sol reco + n_sol eval
        total_guess = (
            1 + 2 * n_sol if p["method"] != "grid" else max(int(1.0 / p["step"]) * 15, 10)
        )
        job = JOB_STORE.create(
            kind="optimize",
            total=total_guess,
            message="Demarrage…",
        )
        job_id = job.job_id
        cb = JOB_STORE.progress_callback(job_id)

        def _worker() -> None:
            try:
                JOB_STORE.update(
                    job_id, status="running", message="Calcul en cours…"
                )
                out = _run_optimize_core(p, progress_cb=cb)
                JOB_STORE.complete(job_id, out)
            except Exception as exc:  # noqa: BLE001
                JOB_STORE.fail(job_id, str(exc))

        threading.Thread(target=_worker, daemon=True).start()
        return jsonify(job.to_public())

    @app.get("/api/user/jobs/<job_id>")
    def user_jobs_status(job_id: str):
        """Etat + progression d'un job (estimation, optim, …)."""
        from src.user.jobs import JOB_STORE

        job = JOB_STORE.get(job_id)
        if not job:
            return jsonify({"ok": False, "error": "Job inconnu"}), 404
        return jsonify(job.to_public())

    return app
