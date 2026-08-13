"""
Évaluation full-train (in-sample) — sans leave-one-out.

Stratégie
---------
  - Apprentissage / coefficients sur **tous** les hôtels de la solution
    (sim_v1 : pilotes observés ; sim_v2 & ml : observés + scénarios simulés).
  - Test uniquement sur les **observations** pilotes (scénario vide).
  - Aucun hôtel n'est exclu du train, même si n_hotels(solution) > 1.

Exports (même schéma web que LOO pour l'admin) :
  data/files/output/sim_v1/eval_sim_v1_full.xlsx
  data/files/output/sim_v2/eval_sim_v2_full.xlsx
  data/files/output/ml/eval_ml_full.xlsx
  data/files/output/common/eval_full_compare.xlsx
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from src.ml.common import TARGETS, metrics_frame
from src.ml.super_model import SuperModelService
from src.pipeline.connection import PipelineFactory
from src.pipeline.paths import Paths
from src.sim_v1.service import (
    SOLUTIONS_V1,
    SimV1Service,
    load_pilot_defaults,
    mix_fb_from_type_mix,
    run_rules_r1_r4,
)
from src.sim_v2.service import SimV2Service

logger = logging.getLogger(__name__)


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def _norm_sol(s: Any) -> str:
    return str(s or "").strip().lower().replace("_", " ")


class FullTrainEvalService:
    """Évaluation in-sample des trois moteurs sur les pilotes observés."""

    def __init__(
        self,
        paths: Paths | None = None,
        factory: PipelineFactory | None = None,
    ):
        self.paths = (paths or Paths()).ensure()
        self.factory = factory or PipelineFactory(self.paths)

    # ------------------------------------------------------------------ sim_v1
    def eval_sim_v1(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Référence = moyenne de **tous** les pilotes de la solution (y compris
        l'hôtel testé). Puis R1–R4 sur les leviers observés.
        """
        svc = SimV1Service(self.paths, factory=self.factory)
        defaults = load_pilot_defaults(str(self.paths.root))
        cp = svc.open(read_only=False)
        try:
            cp.process_with_requires("v_hotel_params")
            hotels = cp.con.execute(
                """
                SELECT *
                FROM v_hotel_params
                WHERE CAST(hotel_code AS VARCHAR) NOT IN ('H5586', 'H6188')
                ORDER BY solution, hotel_code
                """
            ).df()
            # ventes / marge réelles mensuelles
            try:
                reels = cp.con.execute(
                    """
                    SELECT
                      CAST(hotel_code AS VARCHAR) AS hotel_code,
                      ca_reel_mensuel,
                      marge_reelle_mensuelle
                    FROM v_hotel_params
                    """
                ).df()
            except Exception:  # noqa: BLE001
                reels = hotels
        finally:
            cp.close()

        if hotels.empty:
            raise ValueError("Aucun hôtel pilote pour eval full sim_v1")

        hotels = hotels.copy()
        hotels["hotel_code"] = hotels["hotel_code"].astype(str)
        hotels["solution"] = hotels["solution"].astype(str).str.upper()

        # moyennes par solution (tous les hôtels = train full)
        peer_cols = [
            c
            for c in (
                "ca_fb_mensuel",
                "ca_nf_mensuel",
                "nb_ventes_mensuel",
                "clients_mois",
                "mix_fb",
                "m_lin",
            )
            if c in hotels.columns
        ]
        # fallback column names
        alt = {
            "ca_fb_mensuel": ["ca_fb", "ca_fb_mensuel"],
            "ca_nf_mensuel": ["ca_nfb", "ca_nf_mensuel", "ca_nf"],
            "nb_ventes_mensuel": ["nb_ventes_mensuel", "ventes"],
            "clients_mois": ["clients_mois", "clients"],
            "mix_fb": ["mix_fb"],
            "m_lin": ["m_lin", "metres_lineaires"],
        }
        # build peer averages from available numeric cols
        rows: list[dict[str, Any]] = []
        for sol in hotels["solution"].unique():
            sub = hotels.loc[hotels["solution"] == sol]
            for _, h in sub.iterrows():
                code = str(h["hotel_code"])
                # reference = moyenne solution (tous)
                ref = dict(defaults.get(sol) or {})
                # inject peer means when columns exist
                for col in sub.columns:
                    if col in ("hotel_code", "solution", "label", "name"):
                        continue
                    if pd.api.types.is_numeric_dtype(sub[col]):
                        med = pd.to_numeric(sub[col], errors="coerce").mean()
                        if pd.notna(med):
                            # map to ref keys used by run_rules
                            key = str(col)
                            if "ca_fb" in key and "mensuel" in key:
                                ref["ca_fb"] = float(med)
                            elif "ca_nf" in key or "ca_nfb" in key:
                                ref["ca_nfb"] = float(med)
                            elif "vente" in key:
                                ref["ventes"] = float(med)
                            elif "client" in key:
                                ref["clients_heb"] = float(med)
                            elif key == "mix_fb":
                                ref["mix_fb"] = float(med)
                            elif key in ("m_lin", "metres_lineaires"):
                                ref["ml_ref"] = float(med)

                clients = _f(
                    h.get("clients_mois"),
                    _f(h.get("nb_chambres"), 100)
                    * _f(h.get("taux_occupation"), _f(h.get("hotel_to_annuel"), 0.7))
                    * _f(h.get("guests_per_chambre"), _f(h.get("hotel_guests_per_chambre"), 1.7))
                    * 30.5,
                )
                mix_fb = _f(h.get("mix_fb"), 0.7)
                m_lin = _f(h.get("m_lin"), _f(h.get("metres_lineaires"), 6.0))
                frigos = _f(h.get("nb_frigos_froid"), 3.0)

                pred = run_rules_r1_r4(
                    solution=sol,
                    clients_mois=clients,
                    mix_fb=mix_fb,
                    m_lin=m_lin,
                    nb_frigos_froid=frigos,
                    ref=ref,
                )
                ca_pred = _f(pred.get("ca_ht_predit"))
                marge_pred = _f(pred.get("marge_produit_predite"))
                ca_reel = _f(
                    h.get("ca_reel_mensuel"),
                    h.get("ca_total") if "ca_total" in h.index else 0.0,
                )
                marge_reel = _f(
                    h.get("marge_reelle_mensuelle"),
                    h.get("marge_selon_coef_mensuelle")
                    if "marge_selon_coef_mensuelle" in h.index
                    else 0.0,
                )
                rows.append(
                    {
                        "hotel_code": code,
                        "solution": sol,
                        "eval_mode": "full_train",
                        "eval_biased": True,  # toujours in-sample
                        "n_solution_hotels": int(sub["hotel_code"].nunique()),
                        "ca_reel": ca_reel,
                        "ca_pred": ca_pred,
                        "ca_err_abs": abs(ca_pred - ca_reel),
                        "marge_reel": marge_reel,
                        "marge_pred": marge_pred,
                        "marge_err_abs": abs(marge_pred - marge_reel),
                        "metres_lineaires": m_lin,
                    }
                )

        predictions = pd.DataFrame(rows)
        metrics = self._metrics_from_web(predictions)
        return predictions, metrics

    # ------------------------------------------------------------------ sim_v2
    def eval_sim_v2(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Coefficients globaux (obs + sim de tous les hôtels) appliqués sur
        chaque observation pilote.
        """
        svc = SimV2Service(self.paths, factory=self.factory)
        cp = svc.open(rebuild=False)
        try:
            # observations pivot
            obs = cp.con.execute(
                """
                SELECT *
                FROM t_dataset_pivot
                WHERE COALESCE(LEN(scenario_removed_natures), 0) = 0
                  AND CAST(hotel_code AS VARCHAR) NOT IN ('H5586', 'H6188')
                """
            ).df()
            # force materialize global coeffs
            for name in (
                "v_restitution_simulation_long",
                "v_restitution_training_source",
                "v_restitution_solution_coefficients",
            ):
                try:
                    cp.p_table_view(name)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("%s: %s", name, exc)
        finally:
            cp.close()

        if obs.empty:
            raise ValueError("Aucune observation pivot pour eval full sim_v2")

        rows: list[dict[str, Any]] = []
        for _, o in obs.iterrows():
            code = str(o.get("hotel_code") or "")
            sol = _norm_sol(o.get("solution"))
            nb = _f(o.get("hotel_nb_chambres"), 100)
            # guests from pivot
            guests_mois = _f(o.get("nombre_guests_par_mois"), 0)
            to = 0.7
            gpc = 1.7
            if guests_mois > 0 and nb > 0:
                # reverse approx if needed
                pass
            # extract type/gamme mix
            type_mix: dict[str, float] = {}
            gamme_mix: dict[str, float] = {}
            for c, v in o.items():
                cs = str(c)
                if cs.startswith("type_") and cs.endswith("_part_natures"):
                    key = cs[len("type_") : -len("_part_natures")].replace("_", " ")
                    if "non" in key.lower():
                        key = "NON F&B"
                    elif "f" in key.lower() and "b" in key.lower():
                        key = "F&B"
                    type_mix[key] = _f(v)
                if cs.startswith("gamme_") and cs.endswith("_part_natures"):
                    key = cs[len("gamme_") : -len("_part_natures")].replace("_", " ")
                    gamme_mix[key] = _f(v)

            m_lin = _f(o.get("metres_lineaires"), 6.0)
            try:
                cp2 = self.factory.open(read_only=True)
                try:
                    ctx = cp2.con.execute(
                        """
                        SELECT
                          MAX(HOTEL_NB_CHAMBRES) AS nb,
                          MAX(HOTEL_TO_ANNUEL) AS to_a,
                          MAX(HOTEL_GUESTS_PER_CHAMBRE) AS gpc
                        FROM t_sales
                        WHERE CAST(HOTEL_CODE AS VARCHAR) = ?
                        """,
                        [code],
                    ).df()
                    if not ctx.empty:
                        nb = _f(ctx.iloc[0]["nb"], nb) or nb
                        to = _f(ctx.iloc[0]["to_a"], to) or to
                        gpc = _f(ctx.iloc[0]["gpc"], gpc) or gpc
                finally:
                    cp2.close()
            except Exception:  # noqa: BLE001
                pass

            # renormaliser mix (somme exacte 1 pour restitution)
            def _renorm(d: dict[str, float]) -> dict[str, float]:
                if not d:
                    return d
                s = sum(max(0.0, float(v or 0)) for v in d.values())
                if s <= 1e-12:
                    n = len(d)
                    return {k: 1.0 / n for k in d}
                return {k: max(0.0, float(v or 0)) / s for k, v in d.items()}

            type_mix = _renorm(type_mix) or {"F&B": 0.7, "NON F&B": 0.3}
            gamme_mix = _renorm(gamme_mix) if gamme_mix else None

            pred_df = svc.predict(
                hotel_nb_chambres=nb,
                hotel_to_annuel=to,
                hotel_guests_per_chambre=gpc,
                metres_lineaires=m_lin,
                type_mix=type_mix,
                gamme_mix=gamme_mix,
            )
            if pred_df is None or pred_df.empty:
                ca_pred = marge_pred = 0.0
            else:
                hit = pred_df
                if "solution" in pred_df.columns:
                    m = pred_df["solution"].astype(str).str.lower() == sol
                    if m.any():
                        hit = pred_df.loc[m]
                r0 = hit.iloc[0]
                ca_pred = _f(
                    r0.get("montant_ventes_par_mois_predit"),
                    r0.get("montant_ventes_par_mois"),
                )
                marge_pred = _f(
                    r0.get("montant_marge_selon_coef_par_mois_predite"),
                    r0.get("montant_marge_selon_coef_par_mois"),
                )

            ca_reel = _f(o.get("montant_ventes_par_mois"))
            marge_reel = _f(o.get("montant_marge_selon_coef_par_mois"))
            rows.append(
                {
                    "hotel_code": code,
                    "solution": sol,
                    "methode": "sim_v2",
                    "eval_mode": "full_train",
                    "eval_biased": True,
                    "metres_lineaires": m_lin,
                    "montant_ventes_par_mois_reel": ca_reel,
                    "montant_ventes_par_mois_predit": ca_pred,
                    "montant_ventes_erreur_absolue": abs(ca_pred - ca_reel),
                    "montant_marge_selon_coef_par_mois_reel": marge_reel,
                    "montant_marge_selon_coef_par_mois_predite": marge_pred,
                    "montant_marge_selon_coef_erreur_absolue": abs(
                        marge_pred - marge_reel
                    ),
                    # alias web
                    "ca_reel": ca_reel,
                    "ca_pred": ca_pred,
                    "ca_err_abs": abs(ca_pred - ca_reel),
                    "marge_reel": marge_reel,
                    "marge_pred": marge_pred,
                    "marge_err_abs": abs(marge_pred - marge_reel),
                }
            )

        predictions = pd.DataFrame(rows)
        metrics = self._metrics_from_web(predictions)
        return predictions, metrics

    # ------------------------------------------------------------------ ml
    def eval_ml(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Modèles globaux (train sur obs+sim) appliqués aux observations —
        sans exclusion d'hôtel.
        """
        svc = SuperModelService(self.paths, factory=self.factory)
        df = svc.load_dataset(rebuild_rich=False)
        # s'assurer que les modèles globaux existent
        try:
            svc.train_final(df)
        except Exception as exc:  # noqa: BLE001
            logger.warning("train_final skip/err: %s", exc)

        obs = df.loc[df["is_observation"].astype(bool)].copy()
        rows: list[dict[str, Any]] = []
        for _, source in obs.iterrows():
            code = str(source.get("hotel_code") or "")
            sol = _norm_sol(source.get("solution"))
            feat_row = {
                c: float(source[c])
                for c in source.index
                if pd.api.types.is_numeric_dtype(type(source[c]))
                or isinstance(source[c], (int, float, np.floating))
            }
            # also force numeric coercion
            for c in source.index:
                if c in (
                    "scenario_id",
                    "hotel_code",
                    "solution",
                    "is_observation",
                    "scenario_removed_natures",
                ):
                    continue
                try:
                    feat_row[str(c)] = float(source[c]) if pd.notna(source[c]) else 0.0
                except (TypeError, ValueError):
                    continue

            type_mix: dict[str, float] = {}
            gamme_mix: dict[str, float] = {}
            for c, v in source.items():
                cs = str(c)
                if cs.startswith("type_") and cs.endswith("_part_natures"):
                    key = cs[len("type_") : -len("_part_natures")].replace("_", " ")
                    type_mix[key] = _f(v)
                if cs.startswith("gamme_") and cs.endswith("_part_natures"):
                    key = cs[len("gamme_") : -len("_part_natures")].replace("_", " ")
                    gamme_mix[key] = _f(v)

            try:
                pred = svc.predict_row(
                    feat_row,
                    sol,
                    hotel_code=code,
                    type_mix=type_mix or None,
                    gamme_mix=gamme_mix or None,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("ml full pred %s: %s", code, exc)
                pred = {}

            ca_pred = _f(pred.get("montant_ventes_par_mois"))
            marge_pred = _f(
                pred.get("montant_marge_selon_coef_par_mois"),
                pred.get("montant_marge_par_mois"),
            )
            ca_reel = _f(source.get("montant_ventes_par_mois"))
            marge_reel = _f(source.get("montant_marge_selon_coef_par_mois"))
            m_lin = _f(source.get("metres_lineaires"), 6.0)
            rows.append(
                {
                    "hotel_code": code,
                    "solution": sol,
                    "eval_mode": "full_train",
                    "eval_biased": True,
                    "chain": pred.get("chain") or "ml",
                    "montant_ventes_par_mois_reel": ca_reel,
                    "montant_ventes_par_mois_predit": ca_pred,
                    "montant_ventes_par_mois_erreur_absolue": abs(ca_pred - ca_reel),
                    "montant_marge_selon_coef_par_mois_reel": marge_reel,
                    "montant_marge_selon_coef_par_mois_predit": marge_pred,
                    "montant_marge_selon_coef_par_mois_erreur_absolue": abs(
                        marge_pred - marge_reel
                    ),
                    "ca_reel": ca_reel,
                    "ca_pred": ca_pred,
                    "ca_err_abs": abs(ca_pred - ca_reel),
                    "marge_reel": marge_reel,
                    "marge_pred": marge_pred,
                    "marge_err_abs": abs(marge_pred - marge_reel),
                    "metres_lineaires": m_lin,
                }
            )

        predictions = pd.DataFrame(rows)
        # metrics multi-target if columns present
        try:
            metrics = metrics_frame(predictions, TARGETS)
            if metrics.empty:
                metrics = self._metrics_from_web(predictions)
        except Exception:  # noqa: BLE001
            metrics = self._metrics_from_web(predictions)
        return predictions, metrics

    @staticmethod
    def _metrics_from_web(predictions: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for scope, sub in [("ALL", predictions)] + [
            (str(s), predictions.loc[predictions["solution"].astype(str).str.lower() == str(s).lower()])
            for s in predictions["solution"].dropna().unique()
        ]:
            if sub.empty:
                continue
            ca_r = pd.to_numeric(sub.get("ca_reel"), errors="coerce")
            ca_p = pd.to_numeric(sub.get("ca_pred"), errors="coerce")
            m_r = pd.to_numeric(sub.get("marge_reel"), errors="coerce")
            m_p = pd.to_numeric(sub.get("marge_pred"), errors="coerce")
            mask = ca_r.notna() & ca_p.notna()
            if not mask.any():
                continue
            err_ca = (ca_p - ca_r).abs()
            err_m = (m_p - m_r).abs()
            rows.append(
                {
                    "scope": scope if scope == "ALL" else str(scope).upper(),
                    "solution": None if scope == "ALL" else str(scope).lower(),
                    "n_hotels": int(mask.sum()),
                    "mae_ca": float(err_ca[mask].mean()),
                    "rmse_ca": float(math.sqrt(((ca_p - ca_r)[mask] ** 2).mean())),
                    "mae_marge": float(err_m[m_r.notna() & m_p.notna()].mean())
                    if m_r.notna().any()
                    else float("nan"),
                    "methode": "full_train",
                }
            )
        return pd.DataFrame(rows)

    def export_all(self) -> dict[str, Path]:
        """Lance les 3 évaluations full-train + compare + sauvegarde Excel."""
        out: dict[str, Path] = {}

        logger.info("full-train sim_v1 …")
        p1, m1 = self.eval_sim_v1()
        path1 = self.paths.out_sim_v1("eval_sim_v1_full.xlsx")
        path1.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(path1, engine="openpyxl") as w:
            p1.to_excel(w, sheet_name="predictions", index=False)
            m1.to_excel(w, sheet_name="metrics", index=False)
        out["sim_v1"] = path1
        logger.info("→ %s", path1)

        logger.info("full-train sim_v2 …")
        p2, m2 = self.eval_sim_v2()
        path2 = self.paths.out_sim_v2("eval_sim_v2_full.xlsx")
        with pd.ExcelWriter(path2, engine="openpyxl") as w:
            p2.to_excel(w, sheet_name="predictions", index=False)
            m2.to_excel(w, sheet_name="metrics", index=False)
        out["sim_v2"] = path2
        logger.info("→ %s", path2)

        logger.info("full-train ml …")
        pml, mml = self.eval_ml()
        pathm = self.paths.out_ml("eval_ml_full.xlsx")
        with pd.ExcelWriter(pathm, engine="openpyxl") as w:
            pml.to_excel(w, sheet_name="predictions", index=False)
            mml.to_excel(w, sheet_name="metrics", index=False)
        out["ml"] = pathm
        logger.info("→ %s", pathm)

        # compare by hotel
        compare = self._build_compare(p1, p2, pml)
        pathc = self.paths.output_common / "eval_full_compare.xlsx"
        pathc.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(pathc, engine="openpyxl") as w:
            compare.to_excel(w, sheet_name="compare", index=False)
            m1.assign(engine="sim_v1").to_excel(w, sheet_name="metrics_v1", index=False)
            m2.assign(engine="sim_v2").to_excel(w, sheet_name="metrics_v2", index=False)
            mml.assign(engine="ml").to_excel(w, sheet_name="metrics_ml", index=False)
        out["compare"] = pathc
        logger.info("→ %s", pathc)
        return out

    @staticmethod
    def _build_compare(
        p1: pd.DataFrame, p2: pd.DataFrame, pml: pd.DataFrame
    ) -> pd.DataFrame:
        def _idx(df: pd.DataFrame) -> pd.DataFrame:
            d = df.copy()
            d["hotel_code"] = d["hotel_code"].astype(str)
            return d.set_index("hotel_code", drop=False)

        a, b, c = _idx(p1), _idx(p2), _idx(pml)
        codes = sorted(set(a.index) | set(b.index) | set(c.index))
        rows = []
        for code in codes:
            r1 = a.loc[code] if code in a.index else None
            r2 = b.loc[code] if code in b.index else None
            rm = c.loc[code] if code in c.index else None
            if isinstance(r1, pd.DataFrame):
                r1 = r1.iloc[0]
            if isinstance(r2, pd.DataFrame):
                r2 = r2.iloc[0]
            if isinstance(rm, pd.DataFrame):
                rm = rm.iloc[0]

            def g(r, k, default=None):
                if r is None:
                    return default
                return r.get(k, default) if hasattr(r, "get") else r[k] if k in r.index else default

            sol = g(r1, "solution") or g(r2, "solution") or g(rm, "solution")
            ca_reel = g(r1, "ca_reel") or g(r2, "ca_reel") or g(rm, "ca_reel")
            m_reel = g(r1, "marge_reel") or g(r2, "marge_reel") or g(rm, "marge_reel")
            row = {
                "hotel_code": code,
                "solution": sol,
                "eval_mode": "full_train",
                "ca_reel": ca_reel,
                "marge_reel": m_reel,
                "ca_pred_sim_v1": g(r1, "ca_pred"),
                "ca_err_sim_v1": g(r1, "ca_err_abs"),
                "ca_pred_sim_v2": g(r2, "ca_pred"),
                "ca_err_sim_v2": g(r2, "ca_err_abs"),
                "ca_pred_ml": g(rm, "ca_pred"),
                "ca_err_ml": g(rm, "ca_err_abs"),
                "marge_pred_sim_v1": g(r1, "marge_pred"),
                "marge_err_sim_v1": g(r1, "marge_err_abs"),
                "marge_pred_sim_v2": g(r2, "marge_pred"),
                "marge_err_sim_v2": g(r2, "marge_err_abs"),
                "marge_pred_ml": g(rm, "marge_pred"),
                "marge_err_ml": g(rm, "marge_err_abs"),
            }
            # best engine by |err| CA
            best, best_e = None, None
            for eng in ("sim_v1", "sim_v2", "ml"):
                e = row.get(f"ca_err_{eng}")
                if e is None or (isinstance(e, float) and math.isnan(e)):
                    continue
                if best_e is None or float(e) < best_e:
                    best_e = float(e)
                    best = eng
            row["best_ca_engine"] = best
            rows.append(row)
        return pd.DataFrame(rows)
