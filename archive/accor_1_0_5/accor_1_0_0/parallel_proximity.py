#!/usr/bin/env python3
"""
Proximité Overpass en parallèle (shards) pour les hôtels France.

* Filtre ``hotel_data.xlsx`` : pays FR + coords valides
* Découpe en N shards disjoints (défaut 12 process)
* Chaque process écrit ``data/proximity_shards/proximity_fr_shardXX.xlsx``
* Merge final → ``data/hotel_proximity_data.xlsx``

```bash
cd accord
python -m parallel_proximity --workers 12 --pause 0.9
# fusion seule :
python -m parallel_proximity --merge-only
```
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd

from archive.accor_1_0_5.accor_1_0_0.parallel_common import chunk_list, load_france_hotels as _load_fr

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
HOTEL_XLSX = DATA / "hotel_data.xlsx"
OUT_XLSX = DATA / "hotel_proximity_data.xlsx"
SHARD_DIR = DATA / "proximity_shards"
STATE_DIR = DATA / "proximity_state"

# Mirrors Overpass (FR en tete — souvent le plus fiable depuis la France)
OVERPASS_ENDPOINTS = [
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def load_france_hotels(path: Path | None = None) -> pd.DataFrame:
    """Hotels France avec coords valides (Overpass)."""
    return _load_fr(path or HOTEL_XLSX, require_coords=True)


def _worker_shard(
    hotel_records: list[dict[str, Any]],
    shard_id: int,
    pause_s: float,
    overpass_url: str,
) -> dict[str, Any]:
    """Process worker : calcule proximité pour un shard d'hôtels."""
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from archive.accor_1_0_5.accor_1_0_0.geo_proximity import ProximityFromGeo, ProximityFromGeo as _  # noqa: F401
    from archive.accor_1_0_5.accor_1_0_0.geo_proximity import empty_proximity_features, id_and_feature_columns

    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SHARD_DIR / f"proximity_fr_shard{shard_id:02d}.xlsx"
    prog_path = STATE_DIR / f"proximity_fr_shard{shard_id:02d}_progress.json"

    # reprise
    done_codes: set[str] = set()
    rows: list[dict[str, Any]] = []
    if prog_path.exists():
        try:
            prev = json.loads(prog_path.read_text(encoding="utf-8"))
            rows = list(prev.get("rows") or [])
            done_codes = {
                str(r.get("hotel_code") or "").strip()
                for r in rows
                if r.get("hotel_code")
            }
        except Exception:
            rows, done_codes = [], set()

    # aussi si xlsx partiel existe
    if out_path.exists() and not rows:
        try:
            prev_df = pd.read_excel(out_path, dtype={"hotel_code": str})
            rows = prev_df.to_dict(orient="records")
            done_codes = {
                str(r.get("hotel_code") or "").strip() for r in rows if r.get("hotel_code")
            }
        except Exception:
            pass

    engine = ProximityFromGeo(overpass_url=overpass_url)
    pending = [
        h
        for h in hotel_records
        if str(h.get("hotel_code") or "").strip() not in done_codes
    ]
    n_ok = sum(1 for r in rows if r.get("proximity_ok"))
    n_err = sum(1 for r in rows if r.get("proximity_ok") is False)
    t0 = time.perf_counter()
    print(
        f"[prox shard{shard_id:02d}] pending={len(pending)} "
        f"done={len(done_codes)} endpoint={overpass_url}",
        flush=True,
    )

    for i, h in enumerate(pending):
        code = str(h.get("hotel_code") or "").strip()
        if pause_s > 0 and i > 0:
            time.sleep(pause_s)
        try:
            feats = engine.for_point(h.get("hotel_lat"), h.get("hotel_lon"))
            ok = True
            # empty features after exception are all 0 / nan — still "ok" attempt
        except Exception as exc:
            feats = empty_proximity_features()
            ok = False
            err = str(exc)
        else:
            err = ""

        row = {
            "hotel_code": code,
            "hotel_name": h.get("hotel_name"),
            "hotel_lat": h.get("hotel_lat"),
            "hotel_lon": h.get("hotel_lon"),
            "hotel_city": h.get("hotel_city"),
            "hotel_country": h.get("hotel_country") or "FR",
            **feats,
            "proximity_ok": ok,
            "proximity_error": err,
            "shard_id": shard_id,
        }
        rows.append(row)
        if ok:
            n_ok += 1
        else:
            n_err += 1

        if (i + 1) % 5 == 0 or (i + 1) == len(pending):
            prog_path.write_text(
                json.dumps(
                    {
                        "shard_id": shard_id,
                        "n_rows": len(rows),
                        "n_ok": n_ok,
                        "n_err": n_err,
                        "last_code": code,
                        "rows": rows,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                encoding="utf-8",
            )
            pd.DataFrame(rows).to_excel(out_path, index=False, sheet_name="hotel_proximity")
            elapsed = time.perf_counter() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(pending) - i - 1) / rate if rate > 0 else 0
            print(
                f"[prox shard{shard_id:02d}] {i+1}/{len(pending)} "
                f"ok={n_ok} err={n_err} ({elapsed:.0f}s, {rate:.2f}/s, ETA {eta:.0f}s) "
                f"via={engine.overpass_url.split('/')[2]}",
                flush=True,
            )

    frame = pd.DataFrame(rows)
    frame.to_excel(out_path, index=False, sheet_name="hotel_proximity")
    elapsed = time.perf_counter() - t0
    summary = {
        "ok": True,
        "shard_id": shard_id,
        "path": str(out_path),
        "n_rows": len(frame),
        "n_ok": n_ok,
        "n_err": n_err,
        "elapsed_s": round(elapsed, 1),
        "endpoint": overpass_url,
    }
    (STATE_DIR / f"proximity_fr_shard{shard_id:02d}_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"[prox shard{shard_id:02d}] DONE {summary}", flush=True)
    return summary


def merge_shards(*, out_path: Path | None = None) -> dict[str, Any]:
    from archive.accor_1_0_5.accor_1_0_0.geo_proximity import save_proximity_frame

    out_path = out_path or OUT_XLSX
    frames = []
    for p in sorted(SHARD_DIR.glob("proximity_fr_shard*.xlsx")):
        try:
            df = pd.read_excel(p, dtype={"hotel_code": str})
            if not df.empty:
                frames.append(df)
                print(f"[merge] {p.name}: {len(df)}")
        except Exception as exc:
            print(f"[merge] skip {p.name}: {exc}")

    # garder aussi l'ancien fichier si partiel
    if OUT_XLSX.exists():
        try:
            old = pd.read_excel(OUT_XLSX, dtype={"hotel_code": str})
            if not old.empty:
                frames.append(old)
                print(f"[merge] existing main: {len(old)}")
        except Exception:
            pass

    if not frames:
        return {"ok": False, "error": "aucun shard"}

    all_df = pd.concat(frames, ignore_index=True, sort=False)
    all_df["hotel_code"] = all_df["hotel_code"].astype(str).str.strip()
    # préférence : ligne avec proximity_ok True, sinon dernière
    if "proximity_ok" in all_df.columns:
        all_df["_rank"] = all_df["proximity_ok"].map(
            lambda v: 0 if v is True or v == 1 or str(v).lower() == "true" else 1
        )
        all_df = all_df.sort_values(["hotel_code", "_rank"])
        all_df = all_df.drop_duplicates(subset=["hotel_code"], keep="first")
        all_df = all_df.drop(columns=["_rank"], errors="ignore")
    else:
        all_df = all_df.drop_duplicates(subset=["hotel_code"], keep="last")

    save_proximity_frame(all_df, out_path)
    summary = {
        "ok": True,
        "path": str(out_path),
        "n_hotels": int(len(all_df)),
        "n_shards_merged": len(frames),
        "n_ok": int(all_df["proximity_ok"].sum())
        if "proximity_ok" in all_df.columns
        else None,
    }
    (STATE_DIR / "proximity_fr_merge_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return summary


def run_parallel(
    *,
    workers: int = 12,
    pause_s: float = 0.9,
    skip_existing: bool = True,
) -> dict[str, Any]:
    hotels = load_france_hotels()
    print(f"[prox] FR hotels with coords: {len(hotels)}")

    if skip_existing and OUT_XLSX.exists():
        try:
            done = pd.read_excel(OUT_XLSX, dtype={"hotel_code": str})
            if not done.empty and "hotel_code" in done.columns:
                done_set = set(done["hotel_code"].astype(str).str.strip())
                # only skip if has real commerce columns filled (any non-zero)
                from archive.accor_1_0_5.accor_1_0_0.geo_proximity import ProximityFromGeo

                feat_cols = [
                    c
                    for c in ProximityFromGeo.proximity_columns()
                    if c in done.columns and c.startswith("commerce_")
                ]
                if feat_cols:
                    has_data = done[feat_cols].fillna(0).sum(axis=1) > 0
                    # also keep rows with proximity_ok
                    if "proximity_ok" in done.columns:
                        has_data = has_data | done["proximity_ok"].fillna(False).astype(bool)
                    done_set = set(
                        done.loc[has_data, "hotel_code"].astype(str).str.strip()
                    )
                before = len(hotels)
                hotels = hotels[~hotels["hotel_code"].astype(str).str.strip().isin(done_set)]
                print(f"[prox] skip existing with data: {before} → {len(hotels)}")
        except Exception as exc:
            print(f"[prox] skip-existing failed: {exc}")

    # also skip codes already in any shard progress
    if SHARD_DIR.exists():
        done_shards: set[str] = set()
        for p in SHARD_DIR.glob("proximity_fr_shard*.xlsx"):
            try:
                d = pd.read_excel(p, dtype={"hotel_code": str})
                done_shards |= set(d["hotel_code"].astype(str).str.strip())
            except Exception:
                pass
        if done_shards:
            before = len(hotels)
            hotels = hotels[~hotels["hotel_code"].astype(str).str.strip().isin(done_shards)]
            print(f"[prox] skip shard-done: {before} → {len(hotels)}")

    records = hotels.to_dict(orient="records")
    if not records:
        print("[prox] rien à calculer — merge")
        return merge_shards()

    shards = chunk_list(records, workers)
    print(
        f"[prox] {len(records)} hotels → {len(shards)} shards "
        f"sizes={[len(s) for s in shards]} pause={pause_s}s"
    )

    t0 = time.perf_counter()
    results = []
    with ProcessPoolExecutor(max_workers=len(shards)) as ex:
        futs = {}
        for i, shard in enumerate(shards):
            if not shard:
                continue
            url = OVERPASS_ENDPOINTS[i % len(OVERPASS_ENDPOINTS)]
            futs[ex.submit(_worker_shard, shard, i, pause_s, url)] = i
        for fut in as_completed(futs):
            sid = futs[fut]
            try:
                res = fut.result()
            except Exception as exc:
                res = {"ok": False, "shard_id": sid, "error": str(exc)}
                print(f"[prox] shard {sid} FAILED: {exc}")
            results.append(res)

    merged = merge_shards()
    merged["elapsed_s"] = round(time.perf_counter() - t0, 1)
    merged["shard_results"] = results
    return merged


def main() -> None:
    p = argparse.ArgumentParser(description="Proximité FR parallèle (Overpass shards)")
    p.add_argument("--workers", type=int, default=12, help="Process agents (max 12)")
    p.add_argument("--pause", type=float, default=0.9, help="Pause entre hôtels / process")
    p.add_argument("--merge-only", action="store_true")
    p.add_argument("--no-skip-existing", action="store_true")
    args = p.parse_args()

    if args.merge_only:
        merge_shards()
        return

    result = run_parallel(
        workers=args.workers,
        pause_s=args.pause,
        skip_existing=not args.no_skip_existing,
    )
    print(json.dumps({k: v for k, v in result.items() if k != "shard_results"}, indent=2))


if __name__ == "__main__":
    main()
