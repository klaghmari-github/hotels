"""
Utilitaires communs pour les rebuilds France en shards (weather / holidays / proximity).

API
---
* chunk_list — decoupe une liste en N sous-listes
* load_france_hotels — hotel_data filtre FR (option coords)
* read_shard_frames / merge_shard_excels — fusion des xlsx shardNN
* write_json — progression et resumes sous data/*_state/

Les workers specifiques (Overpass, calendrier, Meteostat) restent dans
parallel_weather / parallel_holidays / parallel_proximity.
Voir aussi data_io.filter_france_hotels et geo_common pour les annees de ventes.
"""

from __future__ import annotations

import json
import math
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from archive.accor_1_0_6.accor_1_0_0.data_io import DATA_DIR, filter_france_hotels, read_excel

ROOT = Path(__file__).resolve().parent
HOTEL_XLSX = DATA_DIR / "hotel_data.xlsx"


def chunk_list(items: list[Any], n: int) -> list[list[Any]]:
    """Decoupe items en au plus n sous-listes de tailles proches."""
    if n <= 1 or len(items) <= 1:
        return [items] if items else []
    n = min(n, len(items))
    size = math.ceil(len(items) / n)
    return [items[i : i + size] for i in range(0, len(items), size)]


def load_france_hotels(
    path: Path | None = None,
    *,
    require_coords: bool = False,
    extra_dtypes: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Hotels France depuis hotel_data.xlsx.

    require_coords : True pour meteo / proximite (lat/lon obligatoires).
    """
    path = path or HOTEL_XLSX
    dtype = {"hotel_code": str}
    if extra_dtypes:
        dtype.update(extra_dtypes)
    df = read_excel(path, sheet=0, dtype=dtype)
    return filter_france_hotels(df, require_coords=require_coords)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def read_shard_frames(
    shard_dir: Path,
    pattern: str,
    *,
    dtype: dict[str, Any] | None = None,
) -> list[tuple[Path, pd.DataFrame]]:
    """Charge tous les xlsx matchant pattern sous shard_dir."""
    out: list[tuple[Path, pd.DataFrame]] = []
    if not shard_dir.exists():
        return out
    for p in sorted(shard_dir.glob(pattern)):
        try:
            df = read_excel(p, sheet=0, dtype=dtype)
            if df is not None and not df.empty:
                out.append((p, df))
        except Exception as exc:
            print(f"[merge] skip {p.name}: {exc}")
    return out


def merge_frames_prefer_last(
    frames: list[pd.DataFrame],
    *,
    key_cols: list[str],
) -> pd.DataFrame:
    """
    Concat + dedupe : la derniere occurrence gagne (shards apres existant).
    """
    if not frames:
        return pd.DataFrame()
    all_df = pd.concat(frames, ignore_index=True, sort=False)
    for c in key_cols:
        if c not in all_df.columns:
            continue
        if c == "hotel_code":
            all_df[c] = all_df[c].astype(str).str.strip()
        elif c in ("annee", "mois"):
            all_df[c] = pd.to_numeric(all_df[c], errors="coerce")
    present = [c for c in key_cols if c in all_df.columns]
    if not present:
        return all_df
    all_df = all_df.dropna(subset=present)
    if "annee" in present:
        all_df["annee"] = all_df["annee"].astype(int)
    if "mois" in present:
        all_df["mois"] = all_df["mois"].astype(int)
    all_df = all_df.drop_duplicates(subset=present, keep="last")
    sort_cols = [c for c in present if c in all_df.columns]
    if sort_cols:
        all_df = all_df.sort_values(sort_cols).reset_index(drop=True)
    else:
        all_df = all_df.reset_index(drop=True)
    return all_df


def run_process_pool(
    shards: list[list[Any]],
    worker: Callable[..., dict[str, Any]],
    worker_args_for_shard: Callable[[list[Any], int], tuple],
    *,
    label: str = "shard",
) -> list[dict[str, Any]]:
    """
    Execute worker(shard, i, ...) en ProcessPoolExecutor.

    worker_args_for_shard(shard, index) → args positionnels du worker.
    """
    results: list[dict[str, Any]] = []
    active = [(i, s) for i, s in enumerate(shards) if s]
    if not active:
        return results
    with ProcessPoolExecutor(max_workers=len(active)) as ex:
        futs = {}
        for i, shard in active:
            args = worker_args_for_shard(shard, i)
            futs[ex.submit(worker, *args)] = i
        for fut in as_completed(futs):
            sid = futs[fut]
            try:
                res = fut.result()
            except Exception as exc:
                res = {"ok": False, "shard_id": sid, "error": str(exc)}
                print(f"[{label}] shard {sid} FAILED: {exc}")
            results.append(res)
    return results
