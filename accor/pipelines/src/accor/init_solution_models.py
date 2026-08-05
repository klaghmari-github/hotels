#!/usr/bin/env python3
"""
Assure un modèle intermédiaire + final par solution ROD (SIMPLY / LIBERTY / CONNECTED).

Si un modèle manque pour une solution, il est créé et entraîné sur les lignes
``hotel_solution_* = 1`` de model_data.

Usage
-----
  python -m accor.init_solution_models
  python -m accor.init_solution_models --force
  python -m accor.init_solution_models --dry-run
  python -m accor.init_solution_models --solutions simply liberty
  accor-init-models

Appelé aussi au démarrage admin (thread daemon) si des modèles manquent
(désactiver : ``ACCOR_SKIP_INIT_MODELS=1``).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from accor.data_io import MODELS_DIR
from accor.hotel_solutions import SOLUTIONS, normalize_solution

_INIT_LOCK = threading.Lock()
_INIT_STATE: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "last_result": None,
    "error": None,
}

STATUS_FILE = MODELS_DIR / "init_solution_models.json"


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[init_models {ts}] {msg}", flush=True)


def _write_status(payload: dict[str, Any]) -> None:
    try:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def status_snapshot() -> dict[str, Any]:
    """État des modèles par solution (intermédiaire + final)."""
    from accor.model_final import list_final_models
    from accor.model_train import list_design_models

    by_sol: dict[str, Any] = {}
    any_missing = False
    for sol in SOLUTIONS:
        inter = list_design_models(solution=sol)
        finals = list_final_models(solution=sol)
        missing_inter = len(inter) == 0
        missing_final = len(finals) == 0
        if missing_inter or missing_final:
            any_missing = True
        top_i = inter[0] if inter else None
        top_f = finals[0] if finals else None
        by_sol[sol] = {
            "intermediate_count": len(inter),
            "final_count": len(finals),
            "missing_intermediate": missing_inter,
            "missing_final": missing_final,
            "top_intermediate_id": (top_i or {}).get("id"),
            "top_final_id": (top_f or {}).get("id"),
            "ready": not missing_inter and not missing_final,
        }
    return {
        "any_missing": any_missing,
        "all_ready": not any_missing,
        "solutions": by_sol,
        "init_running": bool(_INIT_STATE.get("running")),
        "init_error": _INIT_STATE.get("error"),
        "last_result": _INIT_STATE.get("last_result"),
    }


def any_missing(solutions: list[str] | None = None) -> bool:
    snap = status_snapshot()
    sols = solutions or list(SOLUTIONS)
    for s in sols:
        su = normalize_solution(s) or str(s).upper()
        info = (snap.get("solutions") or {}).get(su) or {}
        if info.get("missing_intermediate") or info.get("missing_final"):
            return True
    return False


def ensure_solution_models(
    *,
    solutions: list[str] | None = None,
    force: bool = False,
    rebuild_data_once: bool = True,
    xgb_params: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Pour chaque solution : entraîne l'intermédiaire s'il manque, puis le final.

    ``force=True`` ré-entraîne même si un modèle existe déjà.
    ``rebuild_data_once`` : un seul ``rebuild_model_data`` au début.
    """
    from accor.model_data import rebuild_model_data
    from accor.model_final import list_final_models, train_final_model
    from accor.model_train import (
        DEFAULT_XGB_PARAMS,
        get_top_model,
        list_design_models,
        train_model,
    )

    if not _INIT_LOCK.acquire(blocking=False):
        return {
            "ok": False,
            "skipped": True,
            "error": "Un init modèles est déjà en cours.",
            "status": status_snapshot(),
        }

    started = time.time()
    _INIT_STATE.update(
        {
            "running": True,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "error": None,
            "last_result": None,
        }
    )
    sols_in = solutions or list(SOLUTIONS)
    sols: list[str] = []
    for s in sols_in:
        n = normalize_solution(s)
        if n and n not in sols:
            sols.append(n)
    if not sols:
        sols = list(SOLUTIONS)

    result: dict[str, Any] = {
        "ok": True,
        "force": force,
        "dry_run": dry_run,
        "solutions": {},
        "trained": [],
        "skipped": [],
        "errors": [],
        "started_at": _INIT_STATE["started_at"],
    }
    _write_status({**result, "running": True})

    try:
        _log(
            f"ensure solutions={','.join(sols)} force={force} dry_run={dry_run}"
        )

        if rebuild_data_once and not dry_run:
            _log("rebuild model_data (une fois)…")
            try:
                rebuild_model_data()
                _log("model_data OK")
            except Exception as exc:
                _log(f"rebuild model_data: {exc} (on continue avec l'existant)")

        params = {**DEFAULT_XGB_PARAMS, **(xgb_params or {})}
        # n_jobs limité pour ne pas saturer le VPS pendant l'init
        if params.get("n_jobs") in (-1, None):
            params["n_jobs"] = max(1, min(4, (os.cpu_count() or 2)))

        for sol in sols:
            entry: dict[str, Any] = {
                "solution": sol,
                "intermediate": None,
                "final": None,
                "actions": [],
            }
            try:
                inter_list = list_design_models(solution=sol)
                final_list = list_final_models(solution=sol)
                need_inter = force or len(inter_list) == 0
                need_final = force or len(final_list) == 0

                if not need_inter and not need_final:
                    entry["actions"].append("skip_all_ready")
                    result["skipped"].append(sol)
                    top_i = get_top_model(solution=sol) or (inter_list[0] if inter_list else None)
                    top_f = final_list[0] if final_list else None
                    entry["intermediate"] = {
                        "id": (top_i or {}).get("id"),
                        "status": "exists",
                    }
                    entry["final"] = {
                        "id": (top_f or {}).get("id"),
                        "status": "exists",
                    }
                    result["solutions"][sol] = entry
                    _log(f"{sol}: déjà prêt (inter + final)")
                    continue

                inter_id: str | None = None
                if need_inter:
                    name = f"xgb_sales_{sol.lower()}"
                    entry["actions"].append(
                        "train_intermediate" if not dry_run else "would_train_intermediate"
                    )
                    _log(f"{sol}: entraînement intermédiaire → {name}")
                    if dry_run:
                        entry["intermediate"] = {
                            "id": f"{sol.lower()}/{name}",
                            "status": "dry_run",
                        }
                        inter_id = f"{sol.lower()}/{name}"
                    else:
                        res_i = train_model(
                            xgb_params=params,
                            model_name=name,
                            save=True,
                            rebuild_data=False,
                            solution=sol,
                        )
                        inter_id = str(res_i.get("id") or f"{sol.lower()}/{name}")
                        r2 = None
                        try:
                            me = res_i.get("metrics_eval") or {}
                            per = me.get("per_target") or {}
                            mt = res_i.get("main_target")
                            if mt and mt in per:
                                r2 = per[mt].get("r2")
                            else:
                                r2 = me.get("mean_r2")
                        except Exception:
                            r2 = None
                        entry["intermediate"] = {
                            "id": inter_id,
                            "status": "trained",
                            "n_train": res_i.get("n_train"),
                            "n_eval": res_i.get("n_eval"),
                            "r2": r2,
                        }
                        result["trained"].append(f"inter:{inter_id}")
                        _log(
                            f"{sol}: intermédiaire OK id={inter_id} "
                            f"n_train={res_i.get('n_train')} r2={r2}"
                        )
                else:
                    top = get_top_model(solution=sol) or inter_list[0]
                    inter_id = str(top.get("id"))
                    entry["intermediate"] = {
                        "id": inter_id,
                        "status": "exists",
                    }
                    entry["actions"].append("reuse_intermediate")
                    _log(f"{sol}: intermédiaire existant id={inter_id}")

                if need_final:
                    fname = f"xgb_final_{sol.lower()}"
                    entry["actions"].append(
                        "train_final" if not dry_run else "would_train_final"
                    )
                    _log(
                        f"{sol}: entraînement final → {fname} "
                        f"(inter={inter_id})"
                    )
                    if dry_run:
                        entry["final"] = {
                            "id": f"{sol.lower()}/{fname}",
                            "status": "dry_run",
                            "intermediate_model_id": inter_id,
                        }
                    else:
                        res_f = train_final_model(
                            intermediate_model_id=inter_id,
                            model_name=fname,
                            xgb_params=params,
                            rebuild_data=False,
                            solution=sol,
                        )
                        fid = str(res_f.get("id") or f"{sol.lower()}/{fname}")
                        r2f = None
                        try:
                            me = res_f.get("metrics_eval") or {}
                            per = me.get("per_target") or {}
                            mt = res_f.get("main_target")
                            if mt and mt in per:
                                r2f = per[mt].get("r2")
                            else:
                                r2f = me.get("mean_r2")
                        except Exception:
                            r2f = None
                        entry["final"] = {
                            "id": fid,
                            "status": "trained",
                            "intermediate_model_id": inter_id,
                            "n_train": res_f.get("n_train"),
                            "n_eval": res_f.get("n_eval"),
                            "r2": r2f,
                        }
                        result["trained"].append(f"final:{fid}")
                        _log(
                            f"{sol}: final OK id={fid} "
                            f"n_train={res_f.get('n_train')} r2={r2f}"
                        )
                else:
                    top_f = final_list[0]
                    entry["final"] = {
                        "id": top_f.get("id"),
                        "status": "exists",
                    }
                    entry["actions"].append("reuse_final")
                    _log(f"{sol}: final existant id={top_f.get('id')}")

            except Exception as exc:
                result["ok"] = False
                err = f"{sol}: {exc}"
                result["errors"].append(err)
                entry["error"] = str(exc)
                entry["traceback"] = traceback.format_exc()
                _log(f"ERREUR {err}")
            result["solutions"][sol] = entry

        result["elapsed_s"] = round(time.time() - started, 1)
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        result["status_after"] = status_snapshot()
        if result["errors"]:
            result["ok"] = False
        _INIT_STATE["last_result"] = {
            k: v
            for k, v in result.items()
            if k not in ("status_after",)
        }
        _INIT_STATE["error"] = "; ".join(result["errors"]) if result["errors"] else None
        _write_status({**result, "running": False})
        _log(
            f"terminé ok={result['ok']} trained={len(result['trained'])} "
            f"skipped={len(result['skipped'])} errors={len(result['errors'])} "
            f"en {result['elapsed_s']}s"
        )
        return result
    except Exception as exc:
        result["ok"] = False
        result["errors"].append(str(exc))
        result["elapsed_s"] = round(time.time() - started, 1)
        _INIT_STATE["error"] = str(exc)
        _INIT_STATE["last_result"] = result
        _write_status({**result, "running": False, "fatal": str(exc)})
        _log(f"fatal: {exc}")
        raise
    finally:
        _INIT_STATE["running"] = False
        _INIT_STATE["finished_at"] = datetime.now(timezone.utc).isoformat()
        _INIT_LOCK.release()


def spawn_ensure_if_missing(*, force: bool = False) -> bool:
    """
    Lance ``ensure_solution_models`` en thread daemon si modèles manquants.

    Returns True si un thread a été démarré.
    """
    if os.environ.get("ACCOR_SKIP_INIT_MODELS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        _log("skip (ACCOR_SKIP_INIT_MODELS)")
        return False
    if _INIT_STATE.get("running"):
        return False
    try:
        if not force and not any_missing():
            _log("tous les modèles solution sont présents — rien à faire")
            return False
    except Exception as exc:
        _log(f"status check failed, on tente quand même: {exc}")

    def _run() -> None:
        try:
            # laisse Flask démarrer avant un rebuild lourd
            time.sleep(2.0)
            ensure_solution_models(force=force, rebuild_data_once=True)
        except Exception as exc:
            _log(f"background ensure failed: {exc}")
            traceback.print_exc()

    t = threading.Thread(
        target=_run,
        name="init-solution-models",
        daemon=True,
    )
    t.start()
    _log("thread background démarré (ensure modèles manquants)")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Crée et entraîne les modèles intermédiaire+final manquants par solution ROD."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ré-entraîne même si un modèle existe déjà",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche ce qui serait fait sans entraîner",
    )
    parser.add_argument(
        "--solutions",
        nargs="+",
        default=None,
        help="Sous-ensemble (simply liberty connected)",
    )
    parser.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Ne pas reconstruire model_data au début",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Affiche seulement l'état des modèles et quitte",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Sortie JSON (status ou résultat)",
    )
    args = parser.parse_args(argv)

    if args.status:
        snap = status_snapshot()
        if args.json:
            print(json.dumps(snap, ensure_ascii=False, indent=2))
        else:
            print("Modèles par solution ROD")
            print("-" * 48)
            for sol, info in (snap.get("solutions") or {}).items():
                flag = "OK" if info.get("ready") else "MANQUANT"
                print(
                    f"  {sol:10} [{flag}]  "
                    f"inter={info.get('intermediate_count')} "
                    f"({info.get('top_intermediate_id') or '—'})  "
                    f"final={info.get('final_count')} "
                    f"({info.get('top_final_id') or '—'})"
                )
            print(
                f"\nany_missing={snap.get('any_missing')} "
                f"all_ready={snap.get('all_ready')}"
            )
        return 0 if snap.get("all_ready") else 1

    try:
        res = ensure_solution_models(
            solutions=args.solutions,
            force=args.force,
            rebuild_data_once=not args.no_rebuild,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        # pas de traceback massif dans le dump
        clean = {
            k: v
            for k, v in res.items()
            if k != "solutions"
            or True
        }
        sols_clean = {}
        for sol, e in (res.get("solutions") or {}).items():
            sols_clean[sol] = {k: v for k, v in e.items() if k != "traceback"}
        clean["solutions"] = sols_clean
        print(json.dumps(clean, ensure_ascii=False, indent=2, default=str))
    else:
        print()
        print("Résumé init modèles solution")
        print("-" * 48)
        print(f"  ok       : {res.get('ok')}")
        print(f"  trained  : {res.get('trained')}")
        print(f"  skipped  : {res.get('skipped')}")
        print(f"  errors   : {res.get('errors')}")
        print(f"  elapsed  : {res.get('elapsed_s')}s")
        for sol, e in (res.get("solutions") or {}).items():
            inter = e.get("intermediate") or {}
            fin = e.get("final") or {}
            print(
                f"  {sol}: inter[{inter.get('status')}]={inter.get('id')}  "
                f"final[{fin.get('status')}]={fin.get('id')}"
                + (f"  ERR={e.get('error')}" if e.get("error") else "")
            )
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
