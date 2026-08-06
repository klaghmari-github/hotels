"""
Modèle final (stacking enrichi).

Pipeline
--------
1. Charger un **modèle intermédiaire** multi-output (models/design/).
2. Prédire **toutes** les cibles sur model_data (train + eval).
3. Features finales = features descriptives d'origine
   **+** pred_<cible> pour chaque cible intermédiaire.
4. Entraîner un XGB **mono-cible** sur la cible principale (montant_ventes)
   avec ce set enrichi.
5. Sauver dans models/final/design/<slug>/

Ce n'est pas un stacking « meta-model sur preds seules » : les variables
descriptives restent dans X, aux côtés des prédictions intermédiaires.

UI admin : zone **Modèle final** (Build + Explore), distincte des
**Modèles intermédiaires**.
"""

from __future__ import annotations

import json
import pickle
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from archive.accor_1_0_6.pipelines.src.accor.data_io import MODELS_DIR
from archive.accor_1_0_6.pipelines.src.accor.model_data import MAIN_TARGET, rebuild_model_data
from archive.accor_1_0_6.pipelines.src.accor.model_train import (
    DESIGN_DIR,
    BuildProgress,
    _coerce_params,
    _load_model_frame,
    _metrics,
    _slug,
    get_top_model,
    list_design_models,
    load_design_model,
)

FINAL_DESIGN_DIR = MODELS_DIR / "final" / "design"
FINAL_DEPLOY_DIR = MODELS_DIR / "final" / "deploy"
FINAL_LAST_FILE = MODELS_DIR / "final" / "last_trained.json"
FINAL_PROGRESS_FILE = MODELS_DIR / "final" / "build_progress.json"

_final_lock = threading.Lock()
_final_thread: threading.Thread | None = None


class FinalBuildProgress(BuildProgress):
    """Même état que BuildProgress, fichier dédié models/final/build_progress.json."""

    def _persist_unlocked(self) -> None:  # type: ignore[override]
        try:
            FINAL_PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
            slim = []
            for r in self._state.get("results") or []:
                slim.append(
                    {
                        "name": r.get("name"),
                        "id": r.get("id"),
                        "kind": r.get("kind"),
                        "rank": r.get("rank"),
                        "main_target": r.get("main_target"),
                        "metrics_eval": r.get("metrics_eval"),
                        "n_features": r.get("n_features"),
                        "n_pred_features": r.get("n_pred_features"),
                        "intermediate_model_id": r.get("intermediate_model_id"),
                        "xgb_params": r.get("xgb_params"),
                        "error": r.get("error"),
                        "ok": r.get("ok"),
                    }
                )
            payload = {
                **self._state,
                "results": slim,
                "pct": self._compute_pct_unlocked(),
                "tier": "final",
            }
            FINAL_PROGRESS_FILE.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            pass


_final_progress = FinalBuildProgress()


def pred_col_name(target: str) -> str:
    """Nom de feature pour une prédiction intermédiaire."""
    safe = re.sub(r"[^0-9a-zA-Z_]+", "_", str(target)).strip("_")
    return f"pred_{safe}"


def _norm_sol(solution: str | None) -> str | None:
    from archive.accor_1_0_6.pipelines.src.accor.hotel_solutions import normalize_solution

    return normalize_solution(solution)


def final_design_dir(solution: str | None = None) -> Path:
    sol = _norm_sol(solution)
    if sol:
        return FINAL_DESIGN_DIR / sol.lower()
    return FINAL_DESIGN_DIR


def get_final_config_payload(solution: str | None = None) -> dict[str, Any]:
    """Config UI modèle final : intermédiaires dispos + hyperparams défaut."""
    from archive.accor_1_0_6.pipelines.src.accor.model_train import get_config_payload

    sol = _norm_sol(solution)
    base = get_config_payload()
    inter = list_design_models(solution=sol)
    top = get_top_model(solution=sol)
    return {
        **base,
        "tier": "final",
        "solution": sol,
        "intermediate_models": inter,
        "top_intermediate": top,
        "default_intermediate_id": (top or {}).get("id") or (inter[0]["id"] if inter else None),
        "design_dir": str(final_design_dir(sol)),
        "model_name": f"xgb_final_{sol.lower()}" if sol else "xgb_final",
        "pipeline": {
            "steps": [
                f"Filtrer model_data sur solution {sol or 'GLOBAL'}",
                "Charger intermédiaire multi-output (même spécialité)",
                "Prédire cibles → pred_*",
                f"Fit XGB mono-cible sur {MAIN_TARGET}",
            ],
            "note": "Un modèle final par solution (Simply / Liberty / Connected).",
        },
    }


def list_final_models(solution: str | None = None) -> list[dict[str, Any]]:
    FINAL_DESIGN_DIR.mkdir(parents=True, exist_ok=True)
    sol = _norm_sol(solution)
    out: list[dict[str, Any]] = []
    roots: list[Path] = []
    if sol:
        roots = [final_design_dir(sol)]
    else:
        roots = [FINAL_DESIGN_DIR]
        from archive.accor_1_0_6.pipelines.src.accor.hotel_solutions import SOLUTIONS

        for s in SOLUTIONS:
            roots.append(final_design_dir(s))
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for conf_path in sorted(root.glob("*/config.json")):
            try:
                conf = json.loads(conf_path.read_text(encoding="utf-8"))
                mid = conf_path.parent.name
                if conf_path.parent.parent.resolve() != FINAL_DESIGN_DIR.resolve():
                    mid = f"{conf_path.parent.parent.name}/{conf_path.parent.name}"
                if mid in seen:
                    continue
                seen.add(mid)
                conf["id"] = mid
                conf.setdefault("name", conf_path.parent.name)
                conf["tier"] = "final"
                conf.setdefault(
                    "solution",
                    conf.get("solution_filter")
                    or (
                        conf_path.parent.parent.name.upper()
                        if conf_path.parent.parent.name
                        in ("simply", "liberty", "connected")
                        else None
                    ),
                )
                out.append(conf)
            except Exception:
                continue

    def sort_key(m: dict[str, Any]) -> tuple:
        me = m.get("metrics_eval") or m.get("metrics_test") or {}
        main = m.get("main_target") or MAIN_TARGET
        per = (me.get("per_target") or {}).get(main) or me
        r2 = per.get("r2")
        try:
            r2f = float(r2) if r2 is not None else float("-inf")
        except (TypeError, ValueError):
            r2f = float("-inf")
        return (-r2f, m.get("name") or "")

    out.sort(key=sort_key)
    for i, m in enumerate(out, 1):
        m["rank"] = i
    return out


def get_final_last_trained() -> dict[str, Any] | None:
    if not FINAL_LAST_FILE.exists():
        return None
    try:
        return json.loads(FINAL_LAST_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_final_top_model(solution: str | None = None) -> dict[str, Any] | None:
    models = list_final_models(solution=solution)
    return models[0] if models else None


def load_final_model(
    model_id: str, *, solution: str | None = None
) -> dict[str, Any]:
    mid = str(model_id or "").strip().replace("\\", "/")
    candidates: list[Path] = []
    if "/" in mid:
        candidates.append(FINAL_DESIGN_DIR / mid)
    sol = _norm_sol(solution)
    slug = _slug(mid.split("/")[-1])
    if sol:
        candidates.append(final_design_dir(sol) / slug)
    candidates.append(FINAL_DESIGN_DIR / slug)
    from archive.accor_1_0_6.pipelines.src.accor.hotel_solutions import SOLUTIONS

    for s in SOLUTIONS:
        candidates.append(final_design_dir(s) / slug)
    path = conf_path = None
    for parent in candidates:
        p = parent / "model.pkl"
        c = parent / "config.json"
        if p.exists():
            path, conf_path = p, c
            break
    if path is None:
        raise FileNotFoundError(f"Modèle final introuvable : {model_id}")
    with path.open("rb") as f:
        bundle = pickle.load(f)
    meta = {}
    if conf_path and conf_path.exists():
        meta = json.loads(conf_path.read_text(encoding="utf-8"))
    return {"bundle": bundle, "meta": meta}


def get_final_build_progress() -> dict[str, Any]:
    if FINAL_PROGRESS_FILE.exists():
        try:
            disk = json.loads(FINAL_PROGRESS_FILE.read_text(encoding="utf-8"))
            live = _final_progress.snapshot()
            if live.get("status") == "running":
                return live
            if disk.get("status") in {"done", "error", "running"}:
                return disk
        except Exception:
            pass
    return _final_progress.snapshot()


def _resolve_intermediate_id(
    intermediate_model_id: str | None, *, solution: str | None = None
) -> str:
    mid = (intermediate_model_id or "").strip().replace("\\", "/")
    if mid:
        # conserver simply/slug
        if "/" in mid:
            return mid
        return _slug(mid)
    sol = _norm_sol(solution)
    top = get_top_model(solution=sol)
    if top and top.get("id"):
        return str(top["id"])
    models = list_design_models(solution=sol)
    if not models:
        raise FileNotFoundError(
            f"Aucun modèle intermédiaire pour {sol or 'GLOBAL'} dans models/design/ — "
            "entraînez d'abord un intermédiaire de cette spécialité."
        )
    return str(models[0]["id"])


def build_stacked_features(
    frame: pd.DataFrame,
    meta: dict[str, Any],
    intermediate_bundle: dict[str, Any],
) -> tuple[pd.DataFrame, list[str], list[str], list[str]]:
    """
    Retourne (work_df, feature_cols_final, base_feature_cols, pred_cols).

    work_df contient les pred_* en colonnes numériques.
    """
    base_feats = [
        c
        for c in (intermediate_bundle.get("feature_cols") or meta.get("descriptive_columns") or [])
        if c in frame.columns
    ]
    target_cols = list(intermediate_bundle.get("target_cols") or meta.get("target_columns") or [])
    if not base_feats:
        raise ValueError("Aucune feature descriptive pour le stacking.")
    if not target_cols:
        raise ValueError("Aucune cible dans le modèle intermédiaire.")

    model = intermediate_bundle["model"]
    work = frame.copy()
    for c in base_feats:
        work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0.0)

    X = work[base_feats].to_numpy(dtype=float)
    preds = model.predict(X)
    if preds.ndim == 1:
        preds = preds.reshape(-1, 1)

    pred_cols: list[str] = []
    for i, t in enumerate(target_cols):
        col = pred_col_name(t)
        pred_cols.append(col)
        if i < preds.shape[1]:
            work[col] = preds[:, i]
        else:
            work[col] = 0.0

    feature_cols_final = base_feats + pred_cols
    return work, feature_cols_final, base_feats, pred_cols


def train_final_model(
    *,
    intermediate_model_id: str | None = None,
    model_name: str = "xgb_final",
    xgb_params: dict[str, Any] | None = None,
    main_target: str | None = None,
    rebuild_data: bool = True,
    progress_hook: Any | None = None,
    solution: str | None = None,
) -> dict[str, Any]:
    """Entraîne le modèle final stacking (optionnellement spécialisé solution)."""
    try:
        from xgboost import XGBRegressor
    except ImportError as exc:
        raise ImportError(
            "xgboost requis : pip install xgboost scikit-learn"
        ) from exc

    from archive.accor_1_0_6.pipelines.src.accor.hotel_solutions import SOLUTION_FLAG_COLS, filter_frame_by_solution
    from archive.accor_1_0_6.pipelines.src.accor.model_train import MIN_EVAL_ROWS, MIN_TRAIN_ROWS, _apply_solution_filter

    sol = _norm_sol(solution)
    mid = _resolve_intermediate_id(intermediate_model_id, solution=sol)
    if progress_hook:
        progress_hook(0.02, f"Chargement intermédiaire {mid}…", "")

    loaded = load_design_model(mid, solution=sol)
    inter_bundle = loaded["bundle"]
    inter_meta = loaded.get("meta") or {}
    # force alignement solution intermédiaire
    inter_sol = _norm_sol(inter_meta.get("solution") or inter_bundle.get("solution"))
    if sol and inter_sol and inter_sol != sol:
        raise ValueError(
            f"Intermédiaire {mid} est {inter_sol}, attendu {sol}."
        )
    if not sol and inter_sol:
        sol = inter_sol

    if rebuild_data:
        if progress_hook:
            progress_hook(0.05, "Reconstruction model_data…", "")
        rebuild_model_data()
    frame, meta = _load_model_frame()
    frame, meta, _ = _apply_solution_filter(frame, meta, sol)

    main_t = (main_target or meta.get("main_target") or MAIN_TARGET).strip()
    if main_t not in frame.columns:
        main_t = MAIN_TARGET if MAIN_TARGET in frame.columns else main_t

    if progress_hook:
        progress_hook(0.15, "Prédictions intermédiaires (enrichissement)…", "")

    work, feature_cols, base_feats, pred_cols = build_stacked_features(
        frame, meta, inter_bundle
    )
    # drop residual solution flags if any
    feature_cols = [c for c in feature_cols if c not in SOLUTION_FLAG_COLS]
    if main_t not in work.columns:
        raise ValueError(f"Cible principale absente : {main_t}")

    work[main_t] = pd.to_numeric(work[main_t], errors="coerce").fillna(0.0)

    # split temporel
    if "_is_eval" in work.columns:
        is_eval = work["_is_eval"].astype(int) == 1
    elif "annee" in work.columns and meta.get("eval_year") is not None:
        is_eval = pd.to_numeric(work["annee"], errors="coerce") == int(meta["eval_year"])
    else:
        is_eval = pd.Series(False, index=work.index)
        n = len(work)
        is_eval.iloc[int(n * 0.8) :] = True

    train_df = work.loc[~is_eval]
    eval_df = work.loc[is_eval]
    if len(train_df) < MIN_TRAIN_ROWS:
        raise ValueError(
            f"Trop peu de lignes train ({len(train_df)}) pour {sol or 'GLOBAL'}."
        )
    if len(eval_df) < MIN_EVAL_ROWS:
        if len(work) >= MIN_TRAIN_ROWS + 1:
            eval_df = work.tail(max(1, len(work) // 5))
            train_df = work.drop(index=eval_df.index)
        else:
            raise ValueError("Aucune ligne d'évaluation.")

    X_train = train_df[feature_cols].to_numpy(dtype=float)
    y_train = train_df[main_t].to_numpy(dtype=float)
    X_eval = eval_df[feature_cols].to_numpy(dtype=float)
    y_eval = eval_df[main_t].to_numpy(dtype=float)

    params = _coerce_params(xgb_params)
    # mono-cible
    params = {**params}

    if progress_hook:
        progress_hook(0.35, f"Fit XGB final sur {main_t}…", main_t)

    model = XGBRegressor(**params)
    model.fit(X_train, y_train)

    if progress_hook:
        progress_hook(0.85, "Métriques…", main_t)

    y_pred_train = model.predict(X_train)
    y_pred_eval = model.predict(X_eval)
    metrics_train = _metrics(
        y_train.reshape(-1, 1), y_pred_train.reshape(-1, 1), [main_t]
    )
    metrics_eval = _metrics(
        y_eval.reshape(-1, 1), y_pred_eval.reshape(-1, 1), [main_t]
    )

    importance: dict[str, float] = {}
    if hasattr(model, "feature_importances_"):
        for f, v in zip(feature_cols, model.feature_importances_):
            importance[f] = float(v)
    top_imp = sorted(importance.items(), key=lambda x: -x[1])[:40]

    name = _slug(
        model_name or (f"xgb_final_{sol.lower()}" if sol else "xgb_final")
    )
    public_id = f"{sol.lower()}/{name}" if sol else name
    bundle = {
        "model": model,
        "feature_cols": feature_cols,
        "target_cols": [main_t],
        "base_feature_cols": base_feats,
        "pred_feature_cols": pred_cols,
        "intermediate_model_id": mid,
        "tier": "final",
        "kind": "stacked_final",
        "solution": sol,
    }
    config: dict[str, Any] = {
        "name": name,
        "id": public_id,
        "tier": "final",
        "kind": "stacked_final",
        "solution": sol,
        "solution_filter": sol,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "model_data + intermediate preds",
        "intermediate_model_id": mid,
        "intermediate_model_name": inter_meta.get("name") or mid,
        "eval_year": meta.get("eval_year"),
        "n_rows_used": int(len(work)),
        "n_train": int(len(train_df)),
        "n_eval": int(len(eval_df)),
        "feature_cols": feature_cols,
        "base_feature_cols": base_feats,
        "pred_feature_cols": pred_cols,
        "n_features": len(feature_cols),
        "n_base_features": len(base_feats),
        "n_pred_features": len(pred_cols),
        "target_cols": [main_t],
        "n_targets": 1,
        "main_target": main_t,
        "xgb_params": params,
        "metrics_train": metrics_train,
        "metrics_eval": metrics_eval,
        "metrics_test": metrics_eval,
        "top_feature_importance": [{"feature": k, "importance": v} for k, v in top_imp],
        "feature_importance": importance,
        "pipeline": "descriptive + pred_* stacking (per solution)",
        "model_file": "model.pkl",
        "config_file": "config.json",
    }

    root = final_design_dir(sol)
    root.mkdir(parents=True, exist_ok=True)
    out_dir = root / name
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "model.pkl").open("wb") as f:
        pickle.dump(bundle, f)
    config["path"] = str(out_dir)
    config["id"] = public_id
    (out_dir / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    last_payload = {
        "name": name,
        "id": public_id,
        "solution": sol,
        "created_at": config["created_at"],
        "tier": "final",
    }
    FINAL_LAST_FILE.parent.mkdir(parents=True, exist_ok=True)
    FINAL_LAST_FILE.write_text(json.dumps(last_payload, indent=2), encoding="utf-8")
    if sol:
        (root / "last_trained.json").write_text(
            json.dumps(last_payload, indent=2), encoding="utf-8"
        )

    if progress_hook:
        progress_hook(1.0, "Terminé", main_t)

    return {
        "ok": True,
        "id": public_id,
        "name": name,
        "solution": sol,
        "tier": "final",
        "path": str(out_dir),
        "intermediate_model_id": mid,
        "main_target": main_t,
        "n_train": int(len(train_df)),
        "n_eval": int(len(eval_df)),
        "n_features": len(feature_cols),
        "n_base_features": len(base_feats),
        "n_pred_features": len(pred_cols),
        "feature_cols": feature_cols,
        "pred_feature_cols": pred_cols,
        "metrics_train": metrics_train,
        "metrics_eval": metrics_eval,
        "metrics_test": metrics_eval,
        "xgb_params": params,
        "top_feature_importance": config["top_feature_importance"],
        "config": config,
    }


def start_final_build(
    *,
    intermediate_model_id: str | None = None,
    model_name: str = "xgb_final",
    xgb_params: dict[str, Any] | None = None,
    main_target: str | None = None,
    grid_search: dict[str, list[Any]] | None = None,
    solution: str | None = None,
) -> dict[str, Any]:
    """
    Lance le build final en thread (spécialité solution optionnelle).

    Si grid_search non vide : un modèle par combinaison + manuel
    (même logique simplifiée que intermédiaire).
    """
    global _final_thread
    from archive.accor_1_0_6.pipelines.src.accor.model_train import GridSearchPlanner

    sol = _norm_sol(solution)
    base = model_name or (f"xgb_final_{sol.lower()}" if sol else "xgb_final")
    planner = GridSearchPlanner(
        base_name=_slug(base),
        manual_params=xgb_params or {},
        grid=grid_search,
    )
    # (name, kind, params)
    jobs = planner.jobs()
    counts = planner.counts()

    with _final_lock:
        live = _final_progress.snapshot()
        if live.get("status") == "running":
            return {"ok": False, "error": "Un build final est déjà en cours.", **live}

    def hook_factory(job_index: int, n_jobs: int, job_name: str):
        def hook(frac: float, message: str, target: str) -> None:
            _final_progress.update(
                status="running",
                phase="train",
                done=job_index,
                total=n_jobs,
                job_fraction=min(max(frac, 0.0), 1.0),
                current_name=job_name,
                current_target=target or "",
                message=message,
                stage_label=f"Job {job_index + 1}/{n_jobs}",
            )

        return hook

    def worker() -> None:
        results: list[dict[str, Any]] = []
        try:
            _final_progress.reset_running(
                total=len(jobs),
                main_target=main_target or MAIN_TARGET,
                rank_metric="r2",
            )
            _final_progress.update(
                message="Démarrage modèle final…",
                n_manual=counts.get("n_manual", 1),
                n_grid=counts.get("n_grid", 0),
                tier="final",
            )
            rebuild_model_data()
            for i, (jname, jkind, jparams) in enumerate(jobs):
                try:
                    res = train_final_model(
                        intermediate_model_id=intermediate_model_id,
                        model_name=jname,
                        xgb_params=jparams,
                        main_target=main_target,
                        rebuild_data=False,
                        progress_hook=hook_factory(i, len(jobs), jname),
                        solution=sol,
                    )
                    results.append(
                        {
                            "ok": True,
                            "id": res["id"],
                            "name": res["name"],
                            "solution": res.get("solution") or sol,
                            "kind": jkind,
                            "main_target": res["main_target"],
                            "metrics_eval": res["metrics_eval"],
                            "metrics_train": res["metrics_train"],
                            "n_features": res["n_features"],
                            "n_pred_features": res["n_pred_features"],
                            "intermediate_model_id": res["intermediate_model_id"],
                            "xgb_params": res["xgb_params"],
                        }
                    )
                except Exception as exc:
                    results.append(
                        {
                            "ok": False,
                            "name": jname,
                            "error": str(exc),
                            "kind": jkind,
                        }
                    )
                _final_progress.update(
                    done=i + 1,
                    job_fraction=0.0,
                    results=list(results),
                )

            ok_res = [r for r in results if r.get("ok")]
            main_t = main_target or MAIN_TARGET

            def r2_of(r: dict) -> float:
                me = r.get("metrics_eval") or {}
                per = (me.get("per_target") or {}).get(main_t) or {}
                try:
                    return float(per.get("r2", float("-inf")))
                except (TypeError, ValueError):
                    return float("-inf")

            ok_res.sort(key=r2_of, reverse=True)
            for rank, r in enumerate(ok_res, 1):
                r["rank"] = rank
            ordered = list(ok_res) + [r for r in results if not r.get("ok")]

            _final_progress.update(
                status="done",
                phase="done",
                done=len(jobs),
                total=len(jobs),
                job_fraction=1.0,
                message=f"Terminé · {len(ok_res)}/{len(jobs)} modèle(s) final(aux)",
                results=ordered,
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as exc:
            _final_progress.update(
                status="error",
                phase="error",
                error=str(exc),
                message=str(exc),
                results=results,
            )

    t = threading.Thread(target=worker, daemon=True, name="final-model-build")
    _final_thread = t
    t.start()
    return {
        "ok": True,
        "async": True,
        "total": len(jobs),
        "counts": counts,
        "message": f"Build final lancé · {len(jobs)} modèle(s)",
    }


def deploy_final_model(model_name: str | None = None) -> dict[str, Any]:
    name = _slug(model_name or "")
    if not name:
        top = get_final_top_model() or get_final_last_trained()
        if not top:
            raise FileNotFoundError("Aucun modèle final à déployer.")
        name = _slug(top.get("name") or top.get("id") or "")
    src = FINAL_DESIGN_DIR / name
    if not src.exists():
        raise FileNotFoundError(f"Modèle final introuvable : {name}")
    FINAL_DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
    for p in FINAL_DEPLOY_DIR.iterdir():
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)
    shutil.copy2(src / "model.pkl", FINAL_DEPLOY_DIR / "model.pkl")
    conf = {}
    if (src / "config.json").exists():
        conf = json.loads((src / "config.json").read_text(encoding="utf-8"))
    conf["deployed_at"] = datetime.now(timezone.utc).isoformat()
    conf["deployed_from"] = name
    conf["tier"] = "final"
    (FINAL_DEPLOY_DIR / "model.json").write_text(
        json.dumps(conf, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"ok": True, "deployed_from": name, "tier": "final"}
