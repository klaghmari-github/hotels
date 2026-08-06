#!/usr/bin/env python3
"""
Météo Meteostat en parallèle (shards) pour les hôtels France.

* Filtre ``hotel_data.xlsx`` : pays FR + coords valides
* Découpe en N shards disjoints (défaut 12 process)
* Chaque process écrit ``data/weather_shards/weather_fr_shardXX.xlsx``
* Merge final → ``data/hotel_weather_data.xlsx`` (union avec l'existant)

Années / mois = ``geo_common.year_month_pairs`` (années des ventes, mois terminés).

```bash
cd accord
python -m parallel_weather --workers 12 --pause 0.35
python -m parallel_weather --merge-only
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
OUT_XLSX = DATA / "hotel_weather_data.xlsx"
SHARD_DIR = DATA / "weather_shards"
STATE_DIR = DATA / "weather_state"
WEATHER_SHEET = "Sheet1"


def load_france_hotels(path: Path | None = None) -> pd.DataFrame:
    """Hotels France avec lat/lon valides (Meteostat)."""
    return _load_fr(path or HOTEL_XLSX, require_coords=True)


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    out["hotel_code"] = out["hotel_code"].astype(str).str.strip()
    out["annee"] = pd.to_numeric(out["annee"], errors="coerce")
    out["mois"] = pd.to_numeric(out["mois"], errors="coerce")
    out = out.dropna(subset=["hotel_code", "annee", "mois"])
    out["annee"] = out["annee"].astype(int)
    out["mois"] = out["mois"].astype(int)
    return out


def _hotel_has_all_pairs(frame: pd.DataFrame, code: str, pairs: set[tuple[int, int]]) -> bool:
    """True si l'hôtel a tous les (année, mois) avec météo réellement OK."""
    g = frame[frame["hotel_code"].astype(str).str.strip() == code]
    if g.empty:
        return False
    have = set(
        zip(
            pd.to_numeric(g["annee"], errors="coerce").dropna().astype(int),
            pd.to_numeric(g["mois"], errors="coerce").dropna().astype(int),
        )
    )
    if not pairs.issubset(have):
        return False
    # weather_ok explicite (échec Meteostat → False, ne pas skip)
    if "weather_ok" in g.columns:
        ok_series = g["weather_ok"].map(
            lambda v: v is True or v == 1 or str(v).lower() == "true"
        )
        if not bool(ok_series.any()):
            return False
    temp_col = "meteo_temperature_c_mean"
    if temp_col not in g.columns:
        return False
    vals = pd.to_numeric(g[temp_col], errors="coerce").fillna(0.0)
    # au moins ~50 % des mois avec une température non nulle
    nonzero = (vals.abs() > 1e-9).sum()
    return bool(nonzero >= max(1, int(len(pairs) * 0.5)))


def save_weather_frame(frame: pd.DataFrame, path: Path) -> Path:
    from archive.accor_1_0_5.accor_1_0_0.geo_weather import meteo_column_names

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = _normalize_frame(frame)
    id_cols = [
        c
        for c in (
            "hotel_code",
            "hotel_name",
            "annee",
            "mois",
            "hotel_lat",
            "hotel_lon",
            "weather_ok",
            "weather_error",
            "shard_id",
        )
        if c in frame.columns
    ]
    meteo_cols = [c for c in meteo_column_names() if c in frame.columns]
    for c in meteo_cols:
        frame[c] = pd.to_numeric(frame[c], errors="coerce").fillna(0.0)
    rest = [c for c in frame.columns if c not in id_cols and c not in meteo_cols]
    ordered = frame[id_cols + meteo_cols + rest]
    ordered = ordered.sort_values(["hotel_code", "annee", "mois"]).reset_index(drop=True)
    ordered.to_excel(path, index=False, sheet_name=WEATHER_SHEET)
    return path


def _worker_shard(
    hotel_records: list[dict[str, Any]],
    shard_id: int,
    years: list[int],
    pairs: list[tuple[int, int]],
    pause_s: float,
) -> dict[str, Any]:
    """Process worker : météo pour un shard d'hôtels."""
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from archive.accor_1_0_5.accor_1_0_0.geo_common import filter_frame_to_pairs
    from archive.accor_1_0_5.accor_1_0_0.geo_weather import WeatherFromGeo, meteo_column_names

    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SHARD_DIR / f"weather_fr_shard{shard_id:02d}.xlsx"
    prog_path = STATE_DIR / f"weather_fr_shard{shard_id:02d}_progress.json"

    pairs_set = set((int(y), int(m)) for y, m in pairs)
    expected_per_hotel = len(pairs_set)

    # reprise (uniquement hôtels avec météo vraiment OK)
    done_codes: set[str] = set()
    rows: list[dict[str, Any]] = []
    if out_path.exists():
        try:
            prev_df = pd.read_excel(out_path, dtype={"hotel_code": str})
            prev_df = _normalize_frame(prev_df)
            if not prev_df.empty:
                rows = prev_df.to_dict(orient="records")
                for code in prev_df["hotel_code"].unique():
                    if _hotel_has_all_pairs(prev_df, str(code), pairs_set):
                        done_codes.add(str(code))
        except Exception:
            rows, done_codes = [], set()

    pending = [
        h
        for h in hotel_records
        if str(h.get("hotel_code") or "").strip() not in done_codes
    ]
    engine = WeatherFromGeo(years=tuple(years))
    n_ok = 0
    n_err = 0
    # compte hotels déjà ok dans rows
    if rows:
        tmp = pd.DataFrame(rows)
        if "weather_ok" in tmp.columns:
            n_ok = int(
                tmp.drop_duplicates("hotel_code")["weather_ok"]
                .fillna(False)
                .astype(bool)
                .sum()
            )
        n_err = len(done_codes) - n_ok

    t0 = time.perf_counter()
    print(
        f"[wx shard{shard_id:02d}] pending={len(pending)} done={len(done_codes)} "
        f"years={years} pairs={len(pairs)}",
        flush=True,
    )

    for i, h in enumerate(pending):
        code = str(h.get("hotel_code") or "").strip()
        if pause_s > 0 and i > 0:
            time.sleep(pause_s)
        err = ""
        ok = False
        try:
            part = engine.for_point(h.get("hotel_lat"), h.get("hotel_lon"), impute=True)
            if part is None or part.empty:
                raise RuntimeError("empty weather frame")
            part = part.copy()
            part["hotel_code"] = code
            part["hotel_name"] = h.get("hotel_name")
            part = filter_frame_to_pairs(part, pairs)
            if part.empty:
                raise RuntimeError("no year-month pairs after filter")
            temp = pd.to_numeric(part.get("meteo_temperature_c_mean"), errors="coerce")
            ok = bool(temp.notna().any())
            part["weather_ok"] = ok
            part["weather_error"] = ""
            part["shard_id"] = shard_id
            # fill meteo nulls
            for c in meteo_column_names():
                if c in part.columns:
                    part[c] = pd.to_numeric(part[c], errors="coerce").fillna(0.0)
            # drop previous rows for this code (partial)
            rows = [r for r in rows if str(r.get("hotel_code") or "").strip() != code]
            rows.extend(part.to_dict(orient="records"))
        except Exception as exc:
            err = str(exc)
            ok = False
            # grille vide pour garder structure
            empty_rows = []
            for year, month in pairs:
                empty_rows.append(
                    {
                        "hotel_code": code,
                        "hotel_name": h.get("hotel_name"),
                        "annee": int(year),
                        "mois": int(month),
                        "hotel_lat": h.get("hotel_lat"),
                        "hotel_lon": h.get("hotel_lon"),
                        "weather_ok": False,
                        "weather_error": err,
                        "shard_id": shard_id,
                    }
                )
            rows = [r for r in rows if str(r.get("hotel_code") or "").strip() != code]
            rows.extend(empty_rows)

        if ok:
            n_ok += 1
        else:
            n_err += 1

        if (i + 1) % 5 == 0 or (i + 1) == len(pending):
            frame = pd.DataFrame(rows)
            save_weather_frame(frame, out_path)
            prog_path.write_text(
                json.dumps(
                    {
                        "shard_id": shard_id,
                        "n_rows": len(rows),
                        "n_ok": n_ok,
                        "n_err": n_err,
                        "last_code": code,
                        "done_hotels": len(done_codes) + i + 1,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                encoding="utf-8",
            )
            elapsed = time.perf_counter() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(pending) - i - 1) / rate if rate > 0 else 0
            print(
                f"[wx shard{shard_id:02d}] {i+1}/{len(pending)} "
                f"ok={n_ok} err={n_err} ({elapsed:.0f}s, {rate:.2f}/s, ETA {eta:.0f}s) "
                f"last={code}",
                flush=True,
            )

    frame = pd.DataFrame(rows)
    save_weather_frame(frame, out_path)
    elapsed = time.perf_counter() - t0
    n_hotels = int(frame["hotel_code"].nunique()) if not frame.empty else 0
    summary = {
        "ok": True,
        "shard_id": shard_id,
        "path": str(out_path),
        "n_rows": int(len(frame)),
        "n_hotels": n_hotels,
        "n_ok": n_ok,
        "n_err": n_err,
        "expected_rows_hint": n_hotels * expected_per_hotel,
        "elapsed_s": round(elapsed, 1),
    }
    (STATE_DIR / f"weather_fr_shard{shard_id:02d}_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"[wx shard{shard_id:02d}] DONE {summary}", flush=True)
    return summary


def merge_shards(*, out_path: Path | None = None) -> dict[str, Any]:
    out_path = out_path or OUT_XLSX
    ordered: list[pd.DataFrame] = []

    if OUT_XLSX.exists():
        try:
            old = pd.read_excel(OUT_XLSX, dtype={"hotel_code": str})
            if not old.empty:
                ordered.append(_normalize_frame(old))
                print(
                    f"[merge] existing main: {len(old)} rows / "
                    f"{old['hotel_code'].nunique()} hotels"
                )
        except Exception as exc:
            print(f"[merge] existing main skip: {exc}")

    n_shards = 0
    if SHARD_DIR.exists():
        for p in sorted(SHARD_DIR.glob("weather_fr_shard*.xlsx")):
            try:
                df = pd.read_excel(p, dtype={"hotel_code": str})
                if not df.empty:
                    ordered.append(_normalize_frame(df))
                    n_shards += 1
                    print(
                        f"[merge] {p.name}: {len(df)} rows / "
                        f"{df['hotel_code'].nunique()} hotels"
                    )
            except Exception as exc:
                print(f"[merge] skip {p.name}: {exc}")

    if not ordered:
        return {"ok": False, "error": "aucun shard / fichier"}

    all_df = pd.concat(ordered, ignore_index=True, sort=False)
    all_df = _normalize_frame(all_df)

    # priorité : weather_ok True, puis dernière occurrence (shards après existing)
    if "weather_ok" in all_df.columns:
        all_df["_rank"] = all_df["weather_ok"].map(
            lambda v: 0 if v is True or v == 1 or str(v).lower() == "true" else 1
        )
        all_df = all_df.sort_values(["hotel_code", "annee", "mois", "_rank"])
        all_df = all_df.drop_duplicates(
            subset=["hotel_code", "annee", "mois"], keep="first"
        )
        all_df = all_df.drop(columns=["_rank"], errors="ignore")
    else:
        all_df = all_df.drop_duplicates(
            subset=["hotel_code", "annee", "mois"], keep="last"
        )

    save_weather_frame(all_df, out_path)
    summary = {
        "ok": True,
        "path": str(out_path),
        "n_rows": int(len(all_df)),
        "n_hotels": int(all_df["hotel_code"].nunique()),
        "n_shards_merged": n_shards,
        "years": sorted(int(y) for y in all_df["annee"].unique()),
        "n_ok_hotels": int(
            all_df.groupby("hotel_code")["weather_ok"].any().sum()
        )
        if "weather_ok" in all_df.columns
        else None,
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "weather_fr_merge_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return summary


def run_parallel(
    *,
    workers: int = 12,
    pause_s: float = 0.35,
    skip_existing: bool = True,
) -> dict[str, Any]:
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from archive.accor_1_0_5.accor_1_0_0.geo_common import sales_years, year_month_pairs

    hotels = load_france_hotels()
    print(f"[wx] FR hotels with coords: {len(hotels)}")

    years = sales_years()
    pairs = year_month_pairs(years)
    print(f"[wx] years={years} n_pairs={len(pairs)}")
    if not pairs:
        return {"ok": False, "error": "aucun mois à générer"}

    pairs_set = set((int(y), int(m)) for y, m in pairs)

    if skip_existing and OUT_XLSX.exists():
        try:
            done = pd.read_excel(OUT_XLSX, dtype={"hotel_code": str})
            done = _normalize_frame(done)
            if not done.empty:
                complete = {
                    str(code)
                    for code in done["hotel_code"].unique()
                    if _hotel_has_all_pairs(done, str(code), pairs_set)
                }
                before = len(hotels)
                hotels = hotels[
                    ~hotels["hotel_code"].astype(str).str.strip().isin(complete)
                ]
                print(f"[wx] skip complete in main: {before} → {len(hotels)}")
        except Exception as exc:
            print(f"[wx] skip-existing main failed: {exc}")

    if SHARD_DIR.exists():
        done_shards: set[str] = set()
        for p in SHARD_DIR.glob("weather_fr_shard*.xlsx"):
            try:
                d = _normalize_frame(pd.read_excel(p, dtype={"hotel_code": str}))
                for code in d["hotel_code"].unique():
                    if _hotel_has_all_pairs(d, str(code), pairs_set):
                        done_shards.add(str(code))
            except Exception:
                pass
        if done_shards:
            before = len(hotels)
            hotels = hotels[
                ~hotels["hotel_code"].astype(str).str.strip().isin(done_shards)
            ]
            print(f"[wx] skip shard-done: {before} → {len(hotels)}")

    records = hotels.to_dict(orient="records")
    if not records:
        print("[wx] rien à calculer — merge")
        return merge_shards()

    shards = chunk_list(records, workers)
    print(
        f"[wx] {len(records)} hotels → {len(shards)} shards "
        f"sizes={[len(s) for s in shards]} pause={pause_s}s"
    )

    t0 = time.perf_counter()
    results = []
    with ProcessPoolExecutor(max_workers=len(shards)) as ex:
        futs = {}
        for i, shard in enumerate(shards):
            if not shard:
                continue
            futs[ex.submit(_worker_shard, shard, i, years, pairs, pause_s)] = i
        for fut in as_completed(futs):
            sid = futs[fut]
            try:
                res = fut.result()
            except Exception as exc:
                res = {"ok": False, "shard_id": sid, "error": str(exc)}
                print(f"[wx] shard {sid} FAILED: {exc}")
            results.append(res)

    merged = merge_shards()
    merged["elapsed_s"] = round(time.perf_counter() - t0, 1)
    merged["shard_results"] = results
    return merged


def main() -> None:
    p = argparse.ArgumentParser(description="Weather FR parallèle (Meteostat shards)")
    p.add_argument("--workers", type=int, default=12, help="Process agents (max 12)")
    p.add_argument("--pause", type=float, default=0.35, help="Pause entre hôtels / process")
    p.add_argument("--merge-only", action="store_true")
    p.add_argument("--no-skip-existing", action="store_true")
    args = p.parse_args()

    workers = max(1, min(12, int(args.workers)))

    if args.merge_only:
        merge_shards()
        return

    result = run_parallel(
        workers=workers,
        pause_s=args.pause,
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
