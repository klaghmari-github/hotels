"""
Service sim_v1 — LOO R1–R4 via pipeline SQL + prediction ponctuelle.

Prediction user : regles Excel (v1_pilot_defaults) + leviers hotel
(chambres, TO, guests/chambre, m_lin, mix F&B, frigos Connected).
"""

from __future__ import annotations

import json
import logging
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from src.pipeline.connection import PipelineFactory
from src.pipeline.engine import ConnectionPipeline
from src.pipeline.paths import Paths

logger = logging.getLogger(__name__)

SOLUTIONS_V1 = ("SIMPLY", "LIBERTY", "CONNECTED")

# Multiplicateurs R3 (categories ON) — regles revenue v1
MULT_FB = 1.48
MULT_NFB = 1.33


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def mix_fb_from_type_mix(type_mix: dict[str, Any] | None) -> float:
    """Part F&B dans [0,1] depuis type_mix UI (F&B / NON F&B)."""
    if not type_mix:
        return 0.7
    w_fb = 0.0
    w_nfb = 0.0
    for k, v in type_mix.items():
        key = str(k).lower().replace("&", "").replace("_", " ").strip()
        val = _f(v)
        if "non" in key:
            w_nfb += val
        elif "f" in key and "b" in key:
            w_fb += val
        elif key in {"fb", "f b"}:
            w_fb += val
    total = w_fb + w_nfb
    if total <= 1e-12:
        return 0.7
    return max(0.0, min(1.0, w_fb / total))


@lru_cache(maxsize=1)
def load_pilot_defaults(root: str) -> dict[str, dict[str, float]]:
    """
    Coefficients fixes par solution (Excel ou JSON input).
    Cles UPPER : SIMPLY / LIBERTY / CONNECTED.
    """
    paths = Paths(root).ensure()
    json_path = paths.input / "sim_v1_pilot_defaults.json"
    xlsx_path = paths.input / "v1_pilot_defaults.xlsx"
    out: dict[str, dict[str, float]] = {}

    def _row_to_ref(row: dict[str, Any], key: str) -> dict[str, Any]:
        rec: dict[str, Any] = {"solution": key}
        for k, v in row.items():
            if k in {"solution"} or str(k).startswith("_"):
                continue
            # frigo_ref : None si absent (Simply/Liberty) ; float sinon
            if k == "frigo_ref":
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    rec[k] = None
                else:
                    try:
                        rec[k] = float(v)
                    except (TypeError, ValueError):
                        rec[k] = None
                continue
            rec[k] = _f(v)
        return rec

    if json_path.exists():
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        by = raw.get("by_solution") or raw
        for sol, row in by.items():
            if not isinstance(row, dict):
                continue
            key = str(sol).strip().upper()
            out[key] = _row_to_ref(row, key)

    if not out and xlsx_path.exists():
        df = pd.read_excel(xlsx_path)
        for _, row in df.iterrows():
            key = str(row.get("solution") or "").strip().upper()
            if not key:
                continue
            raw_row = {str(c): row[c] for c in df.columns}
            out[key] = _row_to_ref(raw_row, key)

    if not out:
        raise FileNotFoundError(
            "Coefficients sim_v1 introuvables "
            "(v1_pilot_defaults.xlsx ou sim_v1_pilot_defaults.json)."
        )
    return out


def run_rules_r1_r4(
    *,
    solution: str,
    clients_mois: float,
    mix_fb: float,
    m_lin: float,
    nb_frigos_froid: float = 3.0,
    ref: dict[str, Any],
) -> dict[str, Any]:
    """
    Chaine R1→R4 + marge produit (meme logique que pipeline/sim_v1/3_rules).

    ref = ligne pilot defaults (ou moyenne pairs LOO).
    """
    sol = str(solution).strip().upper()
    ventes_ref = _f(ref.get("ventes"), _f(ref.get("ventes_ref")))
    clients_ref = _f(ref.get("clients_heb"), _f(ref.get("clients_ref")))
    ca_fb_ref = _f(ref.get("ca_fb"), _f(ref.get("ca_fb_ref")))
    ca_nfb_ref = _f(ref.get("ca_nfb"), _f(ref.get("ca_nfb_ref")))
    mix_fb_ref = _f(ref.get("mix_fb"), _f(ref.get("mix_fb_ref"), 0.7))
    ml_ref = _f(ref.get("ml_ref"), 6.0) or 6.0
    frigo_ref = ref.get("frigo_ref")
    frigo_ref_f = None if frigo_ref is None or (
        isinstance(frigo_ref, float) and math.isnan(frigo_ref)
    ) else _f(frigo_ref)

    ca_10_fb = _f(ref.get("ca_10_fb"), ca_fb_ref / 10.0 if ca_fb_ref else 0.0)
    ca_10_nfb = _f(ref.get("ca_10_nfb"), ca_nfb_ref / 10.0 if ca_nfb_ref else 0.0)
    ca_1ml_fb = _f(
        ref.get("ca_1ml_fb"),
        ca_fb_ref / ml_ref if ml_ref else 0.0,
    )
    ca_1ml_nfb = _f(
        ref.get("ca_1ml_nfb"),
        ca_nfb_ref / ml_ref if ml_ref else 0.0,
    )
    ca_1frigo_fb = _f(ref.get("ca_1frigo_fb"), ca_fb_ref / 3.0 if ca_fb_ref else 0.0)
    ca_1frigo_nfb = _f(
        ref.get("ca_1frigo_nfb"), ca_nfb_ref / 3.0 if ca_nfb_ref else 0.0
    )
    coeff_fb = _f(ref.get("coeff_fb"), 2.6) or 2.6
    coeff_nfb = _f(ref.get("coeff_nfb"), 1.45) or 1.45

    # R1 — clients acheteurs
    taux_acheteurs = (ventes_ref / clients_ref) if clients_ref > 0 else 0.0
    nb_acheteurs = clients_mois * taux_acheteurs if clients_ref > 0 else 0.0
    if ventes_ref > 0 and clients_ref > 0:
        ca_fb_r1 = (ca_fb_ref / ventes_ref) * nb_acheteurs
        ca_nfb_r1 = (ca_nfb_ref / ventes_ref) * nb_acheteurs
    else:
        ca_fb_r1 = ca_nfb_r1 = 0.0

    # R2 — mix ±10 %
    mix_steps = (mix_fb - mix_fb_ref) * 10.0
    ca_fb_r2 = ca_fb_r1 + ca_10_fb * mix_steps
    ca_nfb_r2 = ca_nfb_r1 + ca_10_nfb * (-mix_steps)

    # R3 — categories ON
    ca_fb_r3 = ca_fb_r2 * MULT_FB
    ca_nfb_r3 = ca_nfb_r2 * MULT_NFB

    # R4 — surface m_lin ou frigos Connected
    use_frigo = sol == "CONNECTED" and frigo_ref_f is not None
    if use_frigo:
        r4_diff = nb_frigos_froid - float(frigo_ref_f)
        r4_mode = "frigos_froid"
        sign = 1.0 if r4_diff > 0 else (-1.0 if r4_diff < 0 else 0.0)
        ca_fb_r4 = ca_fb_r3 + sign * ca_1frigo_fb * abs(r4_diff)
        ca_nfb_r4 = ca_nfb_r3 + sign * ca_1frigo_nfb * abs(r4_diff)
    else:
        r4_diff = m_lin - ml_ref
        r4_mode = "m_lin"
        sign = 1.0 if r4_diff > 0 else (-1.0 if r4_diff < 0 else 0.0)
        ca_fb_r4 = ca_fb_r3 + sign * ca_1ml_fb * abs(r4_diff)
        ca_nfb_r4 = ca_nfb_r3 + sign * ca_1ml_nfb * abs(r4_diff)

    ca_ht = ca_fb_r4 + ca_nfb_r4
    marge = 0.0
    if coeff_fb > 0:
        marge += ca_fb_r4 - (ca_fb_r4 / coeff_fb)
    if coeff_nfb > 0:
        marge += ca_nfb_r4 - (ca_nfb_r4 / coeff_nfb)

    return {
        "solution": sol,
        "clients_hotel": clients_mois,
        "taux_acheteurs": taux_acheteurs,
        "nb_acheteurs": nb_acheteurs,
        "mix_fb_hotel": mix_fb,
        "mix_fb_ref": mix_fb_ref,
        "mix_steps": mix_steps,
        "mult_fb": MULT_FB,
        "mult_nfb": MULT_NFB,
        "r4_mode": r4_mode,
        "r4_diff": r4_diff,
        "ca_fb_r4": ca_fb_r4,
        "ca_nfb_r4": ca_nfb_r4,
        "ca_ht_predit": ca_ht,
        "marge_produit_predite": marge,
        "montant_ventes_par_mois": max(ca_ht, 0.0),
        "montant_marge_par_mois": max(marge, 0.0),
    }


class SimV1Service:
    def __init__(
        self,
        paths: Paths | None = None,
        factory: PipelineFactory | None = None,
    ):
        self.paths = (paths or Paths()).ensure()
        self.factory = factory or PipelineFactory(self.paths)

    def open(
        self,
        *,
        rebuild: bool = False,
        read_only: bool = False,
    ) -> ConnectionPipeline:
        return self.factory.open(rebuild=rebuild, read_only=read_only)

    def pilot_defaults(self) -> dict[str, dict[str, float]]:
        return load_pilot_defaults(str(self.paths.root))

    def run_loo(self, *, rebuild: bool = True) -> dict[str, pd.DataFrame]:
        """Leave-one-out sur les 6 hotels pilotes (hors H5586)."""
        cp = self.open(rebuild=False)
        try:
            if rebuild:
                try:
                    cp.con.execute("DROP TABLE IF EXISTS t_v1_loo_results")
                except Exception:
                    pass

            cp.process_with_requires("t_v1_loo_hotels")
            cp.process_with_requires("t_v1_loo_results")
            cp.process_with_requires("i_v1_loo_evaluation")

            predictions = cp.con.execute(
                """
                SELECT
                  hotel_code,
                  solution,
                  ca_reel_mensuel AS ca_reel,
                  ca_ht_predit AS ca_pred,
                  abs_erreur_ca AS ca_err_abs,
                  marge_reelle_mensuelle AS marge_reel,
                  marge_produit_predite AS marge_pred,
                  abs_erreur_marge AS marge_err_abs,
                  n_mois
                FROM t_v1_loo_results
                WHERE hotel_code IS NOT NULL
                ORDER BY solution, hotel_code
                """
            ).df()
            metrics = cp.p_table_view("v_v1_loo_metrics").df()
            data = cp.con.execute(
                "SELECT * FROM v_hotel_params ORDER BY solution, hotel_code"
            ).df()
            return {
                "predictions": predictions,
                "metrics": metrics,
                "data": data,
            }
        finally:
            cp.close()

    def export_loo(self, result: dict[str, pd.DataFrame] | None = None) -> Path:
        result = result or self.run_loo(rebuild=True)
        path = self.paths.out_sim_v1("eval_sim_v1_loo.xlsx")
        path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            result["data"].to_excel(writer, sheet_name="data", index=False)
            result["predictions"].to_excel(
                writer, sheet_name="predictions", index=False
            )
            result["metrics"].to_excel(writer, sheet_name="metrics", index=False)
        logging.info("Export sim_v1 LOO : %s", path)
        return path

    def list_hotels(self) -> pd.DataFrame:
        cp = self.open(read_only=False)
        try:
            cp.process_with_requires("v_hotel_params")
            return cp.con.execute(
                "SELECT * FROM v_hotel_params ORDER BY solution, hotel_code"
            ).df()
        finally:
            cp.close()

    def predict_hotel(self, hotel_code: str) -> dict[str, Any]:
        """
        Prediction LOO-style pour un hotel pilote : reference = pairs, R1-R4.
        Utilise la vue SQL avec v_loo_step force sur l hotel.
        """
        cp = self.open(read_only=False)
        try:
            cp.process_with_requires("t_hotel_params")
            row = cp.con.execute(
                """
                SELECT hotel_code, solution
                FROM t_hotel_params
                WHERE hotel_code = ?
                """,
                [hotel_code],
            ).df()
            if row.empty:
                raise ValueError(f"Hotel inconnu dans le perimetre v1 : {hotel_code}")

            step = row.iloc[0].to_dict()
            cp.replace_step_view("v_loo_step", step)
            cp.process_with_requires("v_v1_prediction", processed=set())
            pred = cp.table_view("v_v1_prediction").df()
            if pred.empty:
                raise ValueError(f"Aucune prediction pour {hotel_code}")
            rec = pred.iloc[0].to_dict()
            return {
                "ok": True,
                "model": "sim_v1",
                "hotel_code": hotel_code,
                "solution": rec.get("solution"),
                "montant_ventes_par_mois": float(rec.get("ca_ht_predit") or 0),
                "montant_marge_par_mois": float(
                    rec.get("marge_produit_predite") or 0
                ),
                "detail": {
                    k: (None if pd.isna(v) else v)
                    for k, v in rec.items()
                },
            }
        finally:
            cp.close()

    def predict_from_levers(
        self,
        *,
        hotel_nb_chambres: float = 100.0,
        hotel_to_annuel: float = 0.70,
        hotel_guests_per_chambre: float = 1.7,
        metres_lineaires: float = 6.0,
        type_mix: dict[str, Any] | None = None,
        gamme_mix: dict[str, Any] | None = None,
        nb_frigos_froid: float = 3.0,
        solutions: list[str] | None = None,
        hotel_code: str | None = None,
        mix_fb: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Simulation user : regles Excel pilote + leviers (pas besoin d'etre pilote).

        - clients_mois = chambres × TO × guests/chambre × 30.5
        - mix_fb depuis type_mix (ou mix_fb explicite)
        - gamme_mix stocke en detail (v1 n'a pas de regle gamme fine, seulement mix F&B)
        - une estimation par solution (simply / liberty / connected)
        """
        defaults = self.pilot_defaults()
        nb = max(_f(hotel_nb_chambres, 100.0), 1.0)
        to = _f(hotel_to_annuel, 0.70)
        if to > 1.5:  # UI parfois en %
            to = to / 100.0
        to = max(0.01, min(to, 1.5))
        guests = max(_f(hotel_guests_per_chambre, 1.7), 0.1)
        m_lin = max(_f(metres_lineaires, 6.0), 0.1)
        frigos = max(_f(nb_frigos_froid, 3.0), 0.0)
        clients_mois = nb * to * guests * 30.5
        fb = _f(mix_fb) if mix_fb is not None else mix_fb_from_type_mix(type_mix)

        want = [
            str(s).strip().upper()
            for s in (solutions or list(SOLUTIONS_V1))
        ]
        want = [s for s in want if s in SOLUTIONS_V1] or list(SOLUTIONS_V1)

        rows: list[dict[str, Any]] = []
        for sol in want:
            ref = defaults.get(sol)
            if not ref:
                logger.warning("Pas de defaults pilote pour %s", sol)
                continue
            detail = run_rules_r1_r4(
                solution=sol,
                clients_mois=clients_mois,
                mix_fb=fb,
                m_lin=m_lin,
                nb_frigos_froid=frigos,
                ref=ref,
            )
            rows.append(
                {
                    "ok": True,
                    "model": "sim_v1",
                    "engine": "sim_v1",
                    "hotel_code": hotel_code,
                    "solution": sol.lower(),
                    "montant_ventes_par_mois": detail["montant_ventes_par_mois"],
                    "montant_marge_par_mois": detail["montant_marge_par_mois"],
                    "detail": {
                        **detail,
                        "hotel_nb_chambres": nb,
                        "hotel_to_annuel": to,
                        "hotel_guests_per_chambre": guests,
                        "metres_lineaires": m_lin,
                        "nb_frigos_froid": frigos,
                        "type_mix": type_mix or {},
                        "gamme_mix": gamme_mix or {},
                        "reference": "pilot_defaults",
                    },
                }
            )
        if not rows:
            raise ValueError("sim_v1 : aucune solution predite (defaults manquants).")
        return rows
