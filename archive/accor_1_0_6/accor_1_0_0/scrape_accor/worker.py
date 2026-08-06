#!/usr/bin/env python3
"""
Worker de plage : scrape hotels ``start``..``end`` inclus → Excel dédié.

Fichier de sortie unique par plage (pas d'écriture concurrente) :
``accord/data/marques/hotels/hotels_{start:04d}_{end:04d}.xlsx``
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from archive.accor_1_0_6.accor_1_0_0.scrape_accor.hotels import code_for_url, fetch_hotel, write_hotels_xlsx

ROOT = Path(__file__).resolve().parent.parent
HOTELS_DIR = ROOT / "data" / "marques" / "hotels"
STATE_DIR = ROOT / "data" / "marques" / "hotels_state"


def range_paths(start: int, end: int) -> tuple[Path, Path, Path]:
    """xlsx, progress json, claim lock file."""
    HOTELS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tag = f"{start:04d}_{end:04d}"
    return (
        HOTELS_DIR / f"hotels_{tag}.xlsx",
        STATE_DIR / f"progress_{tag}.json",
        STATE_DIR / f"claim_{tag}.json",
    )


def claim_range(
    start: int,
    end: int,
    worker_id: str,
    *,
    force: bool = False,
) -> bool:
    """
    Réserve une plage (create exclusive claim file).

    Returns True si claim OK.
    """
    _, _, claim = range_paths(start, end)
    xlsx, _, _ = range_paths(start, end)
    if xlsx.exists() and not force:
        # déjà terminé
        return False
    if claim.exists() and not force:
        try:
            data = json.loads(claim.read_text(encoding="utf-8"))
            if data.get("status") == "done":
                return False
            if data.get("status") == "running":
                # claim trop vieux (> 2 h) → récupérable
                started = float(data.get("started_at") or 0)
                if time.time() - started < 7200:
                    return False
        except Exception:
            pass
    claim.write_text(
        json.dumps(
            {
                "start": start,
                "end": end,
                "worker_id": worker_id,
                "status": "running",
                "started_at": time.time(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return True


def release_range(start: int, end: int, *, status: str = "done", **extra: Any) -> None:
    _, _, claim = range_paths(start, end)
    data = {
        "start": start,
        "end": end,
        "status": status,
        "finished_at": time.time(),
        **extra,
    }
    claim.write_text(json.dumps(data, indent=2), encoding="utf-8")


def process_range(
    start: int,
    end: int,
    *,
    worker_id: str = "worker",
    pause_s: float = 0.45,
    save_every: int = 20,
    force: bool = False,
) -> dict[str, Any]:
    """
    Scrape [start, end] et écrit l'Excel de plage.

    Reprend depuis le progress si partiel.
    """
    xlsx, progress, _ = range_paths(start, end)
    if not claim_range(start, end, worker_id, force=force):
        return {
            "ok": False,
            "skipped": True,
            "start": start,
            "end": end,
            "reason": "range already claimed or done",
        }

    done_codes: set[int] = set()
    rows: list[dict[str, Any]] = []
    if progress.exists() and not force:
        try:
            prev = json.loads(progress.read_text(encoding="utf-8"))
            rows = list(prev.get("rows") or [])
            done_codes = {int(r["hotel_code_accor"]) for r in rows if r.get("hotel_code_accor")}
        except Exception:
            rows, done_codes = [], set()

    n_ok = sum(1 for r in rows if r.get("status") == "ok")
    n_missing = sum(1 for r in rows if r.get("status") == "missing")
    n_error = sum(1 for r in rows if r.get("status") == "error")

    try:
        for code in range(start, end + 1):
            if code in done_codes:
                continue
            # <1000 → URL 0785 (pas 785) — sinon page vide
            rec = fetch_hotel(code_for_url(code), pause_s=pause_s)
            rows.append(rec)
            done_codes.add(code)
            st = rec.get("status")
            if st == "ok":
                n_ok += 1
            elif st == "missing":
                n_missing += 1
            else:
                n_error += 1

            if len(done_codes) % save_every == 0:
                progress.write_text(
                    json.dumps(
                        {
                            "start": start,
                            "end": end,
                            "worker_id": worker_id,
                            "n_ok": n_ok,
                            "n_missing": n_missing,
                            "n_error": n_error,
                            "last_code": code,
                            "rows": rows,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

        # Excel final : uniquement status=ok + log (codes en texte → garde 0785)
        ok_rows = [r for r in rows if r.get("status") == "ok"]
        log_rows = [
            {
                "hotel_code_accor": r.get("hotel_code_accor"),
                "status": r.get("status"),
                "http_status": r.get("http_status"),
                "error": r.get("error") or r.get("note") or "",
                "url": r.get("url"),
            }
            for r in rows
        ]
        write_hotels_xlsx(xlsx, ok_rows, log_rows)

        progress.write_text(
            json.dumps(
                {
                    "start": start,
                    "end": end,
                    "worker_id": worker_id,
                    "n_ok": n_ok,
                    "n_missing": n_missing,
                    "n_error": n_error,
                    "done": True,
                    "xlsx": str(xlsx),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        release_range(
            start,
            end,
            status="done",
            worker_id=worker_id,
            n_ok=n_ok,
            n_missing=n_missing,
            n_error=n_error,
            xlsx=str(xlsx),
        )
        return {
            "ok": True,
            "start": start,
            "end": end,
            "xlsx": str(xlsx),
            "n_ok": n_ok,
            "n_missing": n_missing,
            "n_error": n_error,
        }
    except Exception as exc:  # noqa: BLE001
        release_range(
            start, end, status="error", worker_id=worker_id, error=str(exc)
        )
        # garder progress
        progress.write_text(
            json.dumps(
                {
                    "start": start,
                    "end": end,
                    "worker_id": worker_id,
                    "n_ok": n_ok,
                    "error": str(exc),
                    "rows": rows,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return {"ok": False, "start": start, "end": end, "error": str(exc)}


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Worker scrape hôtels Accor (une plage)")
    p.add_argument("--start", type=int, required=True)
    p.add_argument("--end", type=int, required=True)
    p.add_argument("--worker-id", default="manual")
    p.add_argument("--pause", type=float, default=0.45)
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    result = process_range(
        args.start,
        args.end,
        worker_id=args.worker_id,
        pause_s=args.pause,
        force=args.force,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
