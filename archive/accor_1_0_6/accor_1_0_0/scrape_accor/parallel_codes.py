#!/usr/bin/env python3
"""
Scrape parallèle multi-process d'une liste de codes (style « agents »).

Chaque worker = 1 process isolé sur un shard de codes → son propre xlsx.
Le parent fusionne à la fin.

Beaucoup plus efficace que des sous-agents LLM pour du HTTP pur :
vrai parallélisme process, pas de surcharge de raisonnement.

Usage
-----
    cd accord
    python -m scrape_accor.parallel_codes \\
      --from-xlsx data/marques/hotels/france_destination_missing.xlsx \\
      --out hotels_missing_france.xlsx \\
      --workers 12

    python -m scrape_accor.parallel_codes --pad4-range 0 999 --workers 12 \\
      --out hotels_0000_0999.xlsx
"""

from __future__ import annotations

import argparse
import json
import math
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
HOTELS_DIR = ROOT / "data" / "marques" / "hotels"
STATE_DIR = ROOT / "data" / "marques" / "hotels_state"


def _chunk_list(items: list[str], n: int) -> list[list[str]]:
    if n <= 1 or len(items) <= 1:
        return [items] if items else []
    n = min(n, len(items))
    size = math.ceil(len(items) / n)
    return [items[i : i + size] for i in range(0, len(items), size)]


def _worker_shard(
    codes: list[str],
    shard_id: int,
    out_name: str,
    pause_s: float,
    tag: str,
    threads_per_worker: int = 3,
) -> dict[str, Any]:
    """
    Process worker : scrape un shard de codes.

    Import local pour compatibilité ProcessPool (spawn).
    """
    import sys

    # assure import scrape_accor depuis accord/
    accord = str(ROOT)
    if accord not in sys.path:
        sys.path.insert(0, accord)

    from archive.accor_1_0_6.accor_1_0_0.scrape_accor.scrape_codes import scrape_code_list

    shard_out = f"{Path(out_name).stem}_shard{shard_id:02d}.xlsx"
    return scrape_code_list(
        codes,
        out_name=shard_out,
        # threads I/O *dans* le process + multi-process entre shards
        workers=max(1, threads_per_worker),
        pause_s=pause_s,
        pad4=False,  # codes déjà normalisés par le parent
        skip_existing=False,  # parent a déjà filtré
        force=True,
        tag=f"{tag}_shard{shard_id:02d}",
    )


def _load_codes(
    *,
    from_xlsx: str,
    codes_csv: str,
    pad4_range: tuple[int, int] | None,
) -> list[str]:
    from archive.accor_1_0_6.accor_1_0_0.scrape_accor.hotels import code_for_url
    from archive.accor_1_0_6.accor_1_0_0.scrape_accor.scrape_codes import _load_codes_from_xlsx

    codes: list[str] = []
    if from_xlsx:
        path = Path(from_xlsx)
        if not path.is_absolute() and not path.exists():
            alt = ROOT / path
            if alt.exists():
                path = alt
        codes.extend(_load_codes_from_xlsx(path))
    if codes_csv:
        codes.extend(c.strip() for c in codes_csv.split(",") if c.strip())
    if pad4_range:
        start, end = pad4_range
        codes.extend(f"{i:04d}" for i in range(start, end + 1))

    # normalize + unique
    seen: set[str] = set()
    out: list[str] = []
    for c in codes:
        n = code_for_url(c)
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _filter_existing(codes: list[str]) -> list[str]:
    from archive.accor_1_0_6.accor_1_0_0.scrape_accor.scrape_codes import _existing_codes

    existing = _existing_codes()
    if not existing:
        return codes
    kept = []
    for c in codes:
        if c in existing:
            continue
        if c.isdigit() and str(int(c)) in existing:
            continue
        if c.zfill(4) in existing:
            continue
        kept.append(c)
    return kept


def _merge_shards(shard_paths: list[Path], out_path: Path) -> int:
    import pandas as pd

    from archive.accor_1_0_6.accor_1_0_0.scrape_accor.hotels import code_for_url, write_hotels_xlsx

    ok_frames = []
    log_frames = []
    for p in shard_paths:
        if not p.exists():
            continue
        try:
            ok = pd.read_excel(p, sheet_name="hotels", dtype={"hotel_code_accor": str})
            if not ok.empty:
                ok_frames.append(ok)
        except Exception:
            pass
        try:
            log = pd.read_excel(p, sheet_name="log", dtype={"hotel_code_accor": str})
            if not log.empty:
                log_frames.append(log)
        except Exception:
            pass

    if not ok_frames:
        write_hotels_xlsx(out_path, [], [])
        return 0

    ok_df = pd.concat(ok_frames, ignore_index=True)
    ok_df["hotel_code_accor"] = ok_df["hotel_code_accor"].map(
        lambda x: code_for_url(x) if str(x).strip() not in {"", "nan"} else x
    )
    ok_df = ok_df.drop_duplicates(subset=["hotel_code_accor"], keep="first")

    log_rows = None
    if log_frames:
        log_df = pd.concat(log_frames, ignore_index=True)
        log_rows = log_df.to_dict(orient="records")

    write_hotels_xlsx(out_path, ok_df.to_dict(orient="records"), log_rows)
    return len(ok_df)


def run_parallel(
    *,
    from_xlsx: str = "",
    codes_csv: str = "",
    pad4_range: tuple[int, int] | None = None,
    out_name: str = "hotels_codes_parallel.xlsx",
    workers: int = 12,
    threads_per_worker: int = 3,
    pause_s: float = 0.25,
    skip_existing: bool = True,
    merge_all: bool = True,
) -> dict[str, Any]:
    HOTELS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    codes = _load_codes(
        from_xlsx=from_xlsx, codes_csv=codes_csv, pad4_range=pad4_range
    )
    n_loaded = len(codes)
    if skip_existing:
        codes = _filter_existing(codes)
    print(
        f"[parallel] loaded={n_loaded} to_scrape={len(codes)} "
        f"processes={workers} threads/proc={threads_per_worker} "
        f"(~{workers * threads_per_worker} requêtes //)"
    )

    out_path = HOTELS_DIR / out_name
    tag = Path(out_name).stem
    t0 = time.perf_counter()

    if not codes:
        summary = {
            "ok": True,
            "n_loaded": n_loaded,
            "n_to_scrape": 0,
            "n_ok": 0,
            "elapsed_s": 0,
            "note": "rien à scraper (déjà dans hotels_all ou liste vide)",
            "out": str(out_path),
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return summary

    shards = _chunk_list(codes, workers)
    print(f"[parallel] {len(shards)} shards sizes={[len(s) for s in shards]}")

    results: list[dict[str, Any]] = []
    shard_paths: list[Path] = []

    with ProcessPoolExecutor(max_workers=len(shards)) as ex:
        futs = {
            ex.submit(
                _worker_shard,
                shard,
                i,
                out_name,
                pause_s,
                tag,
                threads_per_worker,
            ): i
            for i, shard in enumerate(shards)
            if shard
        }
        for fut in as_completed(futs):
            sid = futs[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                res = {"ok": False, "shard": sid, "error": str(exc), "n_ok": 0}
                print(f"[parallel] shard {sid} FAILED: {exc}")
            else:
                print(
                    f"[parallel] shard {sid} done ok={res.get('n_ok')} "
                    f"miss={res.get('n_missing')} err={res.get('n_error')} "
                    f"in {res.get('elapsed_s')}s"
                )
            results.append(res)
            shard_paths.append(
                HOTELS_DIR / f"{Path(out_name).stem}_shard{sid:02d}.xlsx"
            )

    n_merged = _merge_shards(shard_paths, out_path)
    elapsed = time.perf_counter() - t0

    if merge_all:
        from archive.accor_1_0_6.accor_1_0_0.scrape_accor.orchestrator import merge_all_hotels

        merge_all_hotels()

    summary = {
        "ok": True,
        "n_loaded": n_loaded,
        "n_to_scrape": len(codes),
        "n_shards": len(shards),
        "n_ok_merged": n_merged,
        "shard_ok_sum": sum(int(r.get("n_ok") or 0) for r in results),
        "shard_missing_sum": sum(int(r.get("n_missing") or 0) for r in results),
        "shard_error_sum": sum(int(r.get("n_error") or 0) for r in results),
        "elapsed_s": round(elapsed, 1),
        "rate_per_s": round(len(codes) / elapsed, 2) if elapsed > 0 else 0,
        "out": str(out_path),
        "workers": workers,
        "threads_per_worker": threads_per_worker,
        "effective_concurrency": workers * threads_per_worker,
    }
    (STATE_DIR / f"parallel_{tag}_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> None:
    p = argparse.ArgumentParser(
        description="Scrape parallèle multi-process d'une liste de codes Accor"
    )
    p.add_argument("--from-xlsx", default="")
    p.add_argument("--codes", default="")
    p.add_argument("--pad4-range", nargs=2, type=int, metavar=("START", "END"))
    p.add_argument("--out", default="hotels_codes_parallel.xlsx")
    p.add_argument(
        "--workers",
        type=int,
        default=12,
        help="Nb process agents (max recommandé 12)",
    )
    p.add_argument(
        "--threads",
        type=int,
        default=3,
        help="Threads I/O par process (défaut 3 → 12×3=36 //)",
    )
    p.add_argument("--pause", type=float, default=0.25)
    p.add_argument("--no-skip-existing", action="store_true")
    p.add_argument("--no-merge-all", action="store_true")
    args = p.parse_args()

    if not args.from_xlsx and not args.codes and not args.pad4_range:
        p.error("Fournir --from-xlsx et/ou --codes et/ou --pad4-range")

    run_parallel(
        from_xlsx=args.from_xlsx,
        codes_csv=args.codes,
        pad4_range=tuple(args.pad4_range) if args.pad4_range else None,
        out_name=args.out,
        workers=args.workers,
        threads_per_worker=args.threads,
        pause_s=args.pause,
        skip_existing=not args.no_skip_existing,
        merge_all=not args.no_merge_all,
    )


if __name__ == "__main__":
    main()
