#!/usr/bin/env python3
"""
Holidays (calendrier) en parallèle (shards) pour les hôtels France.

* Filtre ``hotel_data.xlsx`` : pays FR
* Découpe en N shards disjoints (défaut 12 process)
* Chaque process écrit ``data/holidays_shards/holidays_fr_shardXX.xlsx``
* Merge final → ``data/hotel_holidays_data.xlsx`` (union avec l'existant)

Calcul local (pas d'API) : fériés FR, weekends, vacances scolaires A/B/C
pour les (année, mois) de ``geo_common.year_month_pairs`` (années ventes).

```bash
cd accord
python -m parallel_holidays --workers 12
# fusion seule :
python -m parallel_holidays --merge-only
```
"""

from __future__ import annotations

import argparse
import json
import math
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
HOTEL_XLSX = DATA / "hotel_data.xlsx"
OUT_XLSX = DATA / "hotel_holidays_data.xlsx"
SHARD_DIR = DATA / "holidays_shards"
STATE_DIR = DATA / "holidays_state"


def _chunk_list(items: list[Any], n: int) -> list[list[Any]]:
    if n <= 1 or len(items) <= 1:
        return [items] if items else []
    n = min(n, len(items))
    size = math.ceil(len(items) / n)
    return [items[i : i + size] for i in range(0, len(items), size)]


def load_france_hotels(path: Path | None = None) -> pd.DataFrame:
    """Tous les hôtels France (coords optionnelles — zone via CP)."""
    path = path or HOTEL_XLSX
    df = pd.read_excel(path, dtype={"hotel_code": str, "hotel_code_postal": str})
    if df.empty:
        return df
    country = (
        df.get("hotel_country", pd.Series([""] * len(df)))
        .astype(str)
        .str.upper()
        .str.strip()
    )
    fr = df[country.isin(["FR", "FRA", "FRANCE"])].copy()
    fr["hotel_code"] = fr["hotel_code"].astype(str).str.strip()
    fr = fr[fr["hotel_code"].ne("") & fr["hotel_code"].ne("nan")]
    fr = fr.drop_duplicates(subset=["hotel_code"], keep="first")
    return fr.reset_index(drop=True)


def _worker_shard(
    hotel_records: list[dict[str, Any]],
    shard_id: int,
    pairs: list[tuple[int, int]],
    meta: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Process worker : calendrier holidays pour un shard d'hôtels."""
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from geo_holidays import compute_holidays_rows

    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SHARD_DIR / f"holidays_fr_shard{shard_id:02d}.xlsx"
    prog_path = STATE_DIR / f"holidays_fr_shard{shard_id:02d}_progress.json"

    t0 = time.perf_counter()
    hotels = pd.DataFrame(hotel_records)
    print(
        f"[hol shard{shard_id:02d}] hotels={len(hotels)} pairs={len(pairs)}",
        flush=True,
    )

    # reprise : si shard déjà complet (n_hotels * n_pairs), skip
    expected = len(hotels) * len(pairs) if pairs else 0
    if out_path.exists() and expected > 0:
        try:
            prev = pd.read_excel(out_path, dtype={"hotel_code": str})
            if len(prev) >= expected:
                summary = {
                    "ok": True,
                    "shard_id": shard_id,
                    "path": str(out_path),
                    "n_rows": int(len(prev)),
                    "n_hotels": int(prev["hotel_code"].nunique())
                    if "hotel_code" in prev.columns
                    else 0,
                    "elapsed_s": 0.0,
                    "resumed": True,
                }
                (STATE_DIR / f"holidays_fr_shard{shard_id:02d}_summary.json").write_text(
                    json.dumps(summary, indent=2), encoding="utf-8"
                )
                print(f"[hol shard{shard_id:02d}] RESUME skip {summary}", flush=True)
                return summary
        except Exception:
            pass

    rows = compute_holidays_rows(hotels, pairs, meta=meta)
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values(["hotel_code", "annee", "mois"]).reset_index(drop=True)
    frame.to_excel(out_path, index=False, sheet_name="hotel_holidays")

    elapsed = time.perf_counter() - t0
    summary = {
        "ok": True,
        "shard_id": shard_id,
        "path": str(out_path),
        "n_rows": int(len(frame)),
        "n_hotels": int(frame["hotel_code"].nunique()) if not frame.empty else 0,
        "elapsed_s": round(elapsed, 1),
        "resumed": False,
    }
    prog_path.write_text(
        json.dumps(
            {
                "shard_id": shard_id,
                "n_rows": summary["n_rows"],
                "n_hotels": summary["n_hotels"],
                "pairs": pairs,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    (STATE_DIR / f"holidays_fr_shard{shard_id:02d}_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"[hol shard{shard_id:02d}] DONE {summary}", flush=True)
    return summary


def merge_shards(*, out_path: Path | None = None) -> dict[str, Any]:
    from geo_holidays import save_holidays_frame

    out_path = out_path or OUT_XLSX
    frames: list[pd.DataFrame] = []

    for p in sorted(SHARD_DIR.glob("holidays_fr_shard*.xlsx")):
        try:
            df = pd.read_excel(p, dtype={"hotel_code": str})
            if not df.empty:
                frames.append(df)
                print(f"[merge] {p.name}: {len(df)} rows / {df['hotel_code'].nunique()} hotels")
        except Exception as exc:
            print(f"[merge] skip {p.name}: {exc}")

    # conserver l'existant (pilotes hors FR ou déjà présents)
    if OUT_XLSX.exists():
        try:
            old = pd.read_excel(OUT_XLSX, dtype={"hotel_code": str})
            if not old.empty:
                frames.append(old)
                print(
                    f"[merge] existing main: {len(old)} rows / "
                    f"{old['hotel_code'].nunique()} hotels"
                )
        except Exception as exc:
            print(f"[merge] existing main skip: {exc}")

    if not frames:
        return {"ok": False, "error": "aucun shard / fichier"}

    all_df = pd.concat(frames, ignore_index=True, sort=False)
    all_df["hotel_code"] = all_df["hotel_code"].astype(str).str.strip()
    all_df["annee"] = pd.to_numeric(all_df["annee"], errors="coerce")
    all_df["mois"] = pd.to_numeric(all_df["mois"], errors="coerce")
    all_df = all_df.dropna(subset=["hotel_code", "annee", "mois"])
    all_df["annee"] = all_df["annee"].astype(int)
    all_df["mois"] = all_df["mois"].astype(int)

    # préférence : dernière version (shards d'abord dans frames → reverse keep first
    # en mettant shards après existing : on veut shards prioritaires sur FR)
    # Re-concat : existing first, then shards, keep last
    ordered: list[pd.DataFrame] = []
    if OUT_XLSX.exists():
        try:
            old = pd.read_excel(OUT_XLSX, dtype={"hotel_code": str})
            if not old.empty:
                ordered.append(old)
        except Exception:
            pass
    for p in sorted(SHARD_DIR.glob("holidays_fr_shard*.xlsx")):
        try:
            df = pd.read_excel(p, dtype={"hotel_code": str})
            if not df.empty:
                ordered.append(df)
        except Exception:
            pass
    if not ordered:
        ordered = frames

    all_df = pd.concat(ordered, ignore_index=True, sort=False)
    all_df["hotel_code"] = all_df["hotel_code"].astype(str).str.strip()
    all_df["annee"] = pd.to_numeric(all_df["annee"], errors="coerce")
    all_df["mois"] = pd.to_numeric(all_df["mois"], errors="coerce")
    all_df = all_df.dropna(subset=["hotel_code", "annee", "mois"])
    all_df["annee"] = all_df["annee"].astype(int)
    all_df["mois"] = all_df["mois"].astype(int)
    # shards (derniers) gagnent en cas de doublon (code, annee, mois)
    all_df = all_df.drop_duplicates(subset=["hotel_code", "annee", "mois"], keep="last")
    all_df = all_df.sort_values(["hotel_code", "annee", "mois"]).reset_index(drop=True)

    save_holidays_frame(all_df, out_path)
    summary = {
        "ok": True,
        "path": str(out_path),
        "n_rows": int(len(all_df)),
        "n_hotels": int(all_df["hotel_code"].nunique()),
        "n_shards_merged": len(list(SHARD_DIR.glob("holidays_fr_shard*.xlsx")))
        if SHARD_DIR.exists()
        else 0,
        "years": sorted(int(y) for y in all_df["annee"].unique()),
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "holidays_fr_merge_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return summary


def run_parallel(*, workers: int = 12, skip_existing: bool = True) -> dict[str, Any]:
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from geo_common import sales_years, year_month_pairs
    from geo_holidays import _hotel_meta_lookup, load_holidays_frame

    hotels = load_france_hotels()
    print(f"[hol] FR hotels: {len(hotels)}")

    years = sales_years()
    pairs = year_month_pairs(years)
    print(f"[hol] years={years} n_pairs={len(pairs)}")
    if not pairs:
        return {"ok": False, "error": "aucun mois à générer"}

    meta = _hotel_meta_lookup(load_holidays_frame())

    if skip_existing and OUT_XLSX.exists():
        try:
            done = pd.read_excel(OUT_XLSX, dtype={"hotel_code": str})
            if not done.empty and "hotel_code" in done.columns:
                # hôtel « complet » si a tous les pairs
                need = set(pairs)
                complete: set[str] = set()
                for code, g in done.groupby(done["hotel_code"].astype(str).str.strip()):
                    have = set(
                        zip(
                            pd.to_numeric(g["annee"], errors="coerce").dropna().astype(int),
                            pd.to_numeric(g["mois"], errors="coerce").dropna().astype(int),
                        )
                    )
                    if need.issubset(have):
                        complete.add(str(code))
                before = len(hotels)
                hotels = hotels[
                    ~hotels["hotel_code"].astype(str).str.strip().isin(complete)
                ]
                print(f"[hol] skip complete in main: {before} → {len(hotels)}")
        except Exception as exc:
            print(f"[hol] skip-existing main failed: {exc}")

    # skip déjà dans shards
    if SHARD_DIR.exists():
        done_shards: set[str] = set()
        need = set(pairs)
        for p in SHARD_DIR.glob("holidays_fr_shard*.xlsx"):
            try:
                d = pd.read_excel(p, dtype={"hotel_code": str})
                for code, g in d.groupby(d["hotel_code"].astype(str).str.strip()):
                    have = set(
                        zip(
                            pd.to_numeric(g["annee"], errors="coerce").dropna().astype(int),
                            pd.to_numeric(g["mois"], errors="coerce").dropna().astype(int),
                        )
                    )
                    if need.issubset(have):
                        done_shards.add(str(code))
            except Exception:
                pass
        if done_shards:
            before = len(hotels)
            hotels = hotels[
                ~hotels["hotel_code"].astype(str).str.strip().isin(done_shards)
            ]
            print(f"[hol] skip shard-done: {before} → {len(hotels)}")

    records = hotels.to_dict(orient="records")
    if not records:
        print("[hol] rien à calculer — merge")
        return merge_shards()

    shards = _chunk_list(records, workers)
    print(
        f"[hol] {len(records)} hotels → {len(shards)} shards "
        f"sizes={[len(s) for s in shards]}"
    )

    t0 = time.perf_counter()
    results = []
    with ProcessPoolExecutor(max_workers=len(shards)) as ex:
        futs = {}
        for i, shard in enumerate(shards):
            if not shard:
                continue
            futs[ex.submit(_worker_shard, shard, i, pairs, meta)] = i
        for fut in as_completed(futs):
            sid = futs[fut]
            try:
                res = fut.result()
            except Exception as exc:
                res = {"ok": False, "shard_id": sid, "error": str(exc)}
                print(f"[hol] shard {sid} FAILED: {exc}")
            results.append(res)

    merged = merge_shards()
    merged["elapsed_s"] = round(time.perf_counter() - t0, 1)
    merged["shard_results"] = results
    return merged


def main() -> None:
    p = argparse.ArgumentParser(description="Holidays FR parallèle (shards calendrier)")
    p.add_argument("--workers", type=int, default=12, help="Process agents (max 12)")
    p.add_argument("--merge-only", action="store_true")
    p.add_argument("--no-skip-existing", action="store_true")
    args = p.parse_args()

    workers = max(1, min(12, int(args.workers)))

    if args.merge_only:
        merge_shards()
        return

    result = run_parallel(
        workers=workers,
        skip_existing=not args.no_skip_existing,
    )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "shard_results"},
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
