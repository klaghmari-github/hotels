#!/usr/bin/env python3
"""
Orchestrateur multi-workers pour le scrape hôtels Accor.

* Plages de ``range_size`` (défaut 100) entre ``id_min`` et ``id_max``
* Au plus ``max_workers`` processus en parallèle
* Chaque worker écrit son propre ``hotels_{start}_{end}.xlsx``
* Arrêt global quand ``target_hotels`` hôtels OK cumulés (défaut 4000)
  ou toutes les plages traitées

Usage
-----
    cd accord
    python -m scrape_accor.orchestrator --max-workers 4 --range-size 100
    python -m scrape_accor.orchestrator --id-min 1000 --id-max 2000 --max-workers 2
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from scrape_accor.worker import HOTELS_DIR, STATE_DIR, process_range, range_paths

ROOT = Path(__file__).resolve().parent.parent
COUNTER_FILE = STATE_DIR / "global_counter.json"


def build_ranges(id_min: int, id_max: int, range_size: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start = id_min
    while start <= id_max:
        end = min(start + range_size - 1, id_max)
        ranges.append((start, end))
        start = end + 1
    return ranges


def count_hotels_ok() -> int:
    """
    Compte les hôtels **uniques** (hotel_code_accor) dans tous les xlsx de plage.

    Évite de double-compter les plages qui se chevauchent (ex. smoke 1140–1155
    + 1100–1199).
    """
    import pandas as pd

    HOTELS_DIR.mkdir(parents=True, exist_ok=True)
    codes: set[str] = set()
    for path in sorted(HOTELS_DIR.glob("hotels_*.xlsx")):
        if path.name == "hotels_all.xlsx":
            continue
        try:
            df = pd.read_excel(path, sheet_name="hotels")
        except Exception:
            continue
        if df.empty:
            continue
        col = "hotel_code_accor" if "hotel_code_accor" in df.columns else None
        if col:
            for v in df[col].dropna().astype(str):
                codes.add(v.strip())
        else:
            # fallback sans clé : ne pas sur-compter
            codes.update(f"{path.stem}:{i}" for i in range(len(df)))
    return len(codes)


def range_is_done(start: int, end: int) -> bool:
    xlsx, _, claim = range_paths(start, end)
    if xlsx.exists():
        return True
    if claim.exists():
        try:
            data = json.loads(claim.read_text(encoding="utf-8"))
            return data.get("status") == "done"
        except Exception:
            return False
    return False


def pending_ranges(
    id_min: int, id_max: int, range_size: int
) -> list[tuple[int, int]]:
    return [
        r
        for r in build_ranges(id_min, id_max, range_size)
        if not range_is_done(*r)
    ]


def _worker_entry(args: tuple[int, int, str, float, bool]) -> dict[str, Any]:
    start, end, worker_id, pause_s, force = args
    return process_range(
        start, end, worker_id=worker_id, pause_s=pause_s, force=force
    )


def run_orchestrator(
    *,
    id_min: int = 1000,
    id_max: int = 8000,
    range_size: int = 100,
    max_workers: int = 4,
    target_hotels: int = 4000,
    pause_s: float = 0.45,
    force: bool = False,
) -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    HOTELS_DIR.mkdir(parents=True, exist_ok=True)

    pending = pending_ranges(id_min, id_max, range_size)
    print(
        f"[orchestrator] plages en attente: {len(pending)} "
        f"({id_min}–{id_max}, size={range_size}), workers={max_workers}"
    )
    already = count_hotels_ok()
    print(f"[orchestrator] hôtels déjà extraits: {already} / cible {target_hotels}")
    if already >= target_hotels and not force:
        return {
            "ok": True,
            "stopped": "target_reached",
            "n_hotels": already,
            "target": target_hotels,
        }

    results: list[dict[str, Any]] = []
    # Nourrir le pool au fur et à mesure
    idx = 0
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        # seed
        while idx < len(pending) and len(futures) < max_workers:
            if count_hotels_ok() >= target_hotels:
                break
            start, end = pending[idx]
            wid = f"w{idx:03d}_{start}_{end}"
            fut = pool.submit(_worker_entry, (start, end, wid, pause_s, force))
            futures[fut] = (start, end, wid)
            idx += 1
            print(f"[orchestrator] démarré {wid}")

        while futures:
            for fut in as_completed(list(futures.keys()), timeout=None):
                start, end, wid = futures.pop(fut)
                try:
                    res = fut.result()
                except Exception as exc:  # noqa: BLE001
                    res = {"ok": False, "error": str(exc), "start": start, "end": end}
                results.append(res)
                n_ok = count_hotels_ok()
                print(
                    f"[orchestrator] terminé {wid} → {res.get('n_ok')} ok "
                    f"(global {n_ok}/{target_hotels})"
                )
                # lancer la suivante
                if n_ok >= target_hotels:
                    print("[orchestrator] cible atteinte — plus de nouvelles plages")
                    # laisser finir les futures en cours
                    continue
                if idx < len(pending):
                    start2, end2 = pending[idx]
                    wid2 = f"w{idx:03d}_{start2}_{end2}"
                    fut2 = pool.submit(
                        _worker_entry, (start2, end2, wid2, pause_s, force)
                    )
                    futures[fut2] = (start2, end2, wid2)
                    idx += 1
                    print(f"[orchestrator] démarré {wid2}")
                break  # as_completed iterator refresh

    final = count_hotels_ok()
    summary = {
        "ok": True,
        "n_hotels": final,
        "target": target_hotels,
        "ranges_done": len(results),
        "results": results,
    }
    COUNTER_FILE.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    # merge optionnel
    try:
        merge_all_hotels()
    except Exception as exc:  # noqa: BLE001
        summary["merge_error"] = str(exc)
    return summary


def merge_all_hotels() -> Path:
    """Concatène tous les hotels_*.xlsx → hotels_all.xlsx (dédup par code)."""
    import pandas as pd

    from scrape_accor.hotels import code_for_url, write_hotels_xlsx

    frames = []
    for path in sorted(HOTELS_DIR.glob("hotels_*.xlsx")):
        if path.name == "hotels_all.xlsx":
            continue
        try:
            df = pd.read_excel(path, sheet_name="hotels", dtype={"hotel_code_accor": str})
            if not df.empty:
                frames.append(df)
        except Exception:
            try:
                df = pd.read_excel(path, sheet_name="hotels")
                if not df.empty:
                    frames.append(df)
            except Exception:
                continue
    out = HOTELS_DIR / "hotels_all.xlsx"
    if not frames:
        pd.DataFrame().to_excel(out, index=False)
        return out
    all_df = pd.concat(frames, ignore_index=True)
    if "hotel_code_accor" in all_df.columns:
        # Restaure 0785 si Excel a stocké 785 / 785.0
        all_df["hotel_code_accor"] = all_df["hotel_code_accor"].map(
            lambda x: code_for_url(x) if pd.notna(x) and str(x).strip() not in {"", "nan"} else x
        )
        all_df = all_df.drop_duplicates(subset=["hotel_code_accor"], keep="first")
    # write with text format
    write_hotels_xlsx(out, all_df.to_dict(orient="records"), None)
    print(f"[orchestrator] merge → {out} ({len(all_df)} hôtels)")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Orchestrateur scrape hôtels Accor")
    p.add_argument("--id-min", type=int, default=1000)
    p.add_argument("--id-max", type=int, default=8000)
    p.add_argument("--range-size", type=int, default=100)
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--target-hotels", type=int, default=4000)
    p.add_argument("--pause", type=float, default=0.45)
    p.add_argument("--force", action="store_true")
    p.add_argument("--merge-only", action="store_true")
    args = p.parse_args()

    if args.merge_only:
        path = merge_all_hotels()
        print(path)
        return

    summary = run_orchestrator(
        id_min=args.id_min,
        id_max=args.id_max,
        range_size=args.range_size,
        max_workers=args.max_workers,
        target_hotels=args.target_hotels,
        pause_s=args.pause,
        force=args.force,
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))


if __name__ == "__main__":
    main()
