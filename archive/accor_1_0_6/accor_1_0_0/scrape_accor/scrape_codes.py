#!/usr/bin/env python3
"""
Scrape une liste de codes hôtels Accor (alphanumériques OK).

Usages
------
# 748 manquants France
python -m scrape_accor.scrape_codes \\
  --from-xlsx data/marques/hotels/france_destination_missing.xlsx \\
  --out hotels_missing_france.xlsx --workers 12

# Plage 0–999 avec zéros à gauche (4 caractères)
python -m scrape_accor.scrape_codes --pad4-range 0 999 --out hotels_0000_0999.xlsx

# Codes explicites
python -m scrape_accor.scrape_codes --codes A7L5,0785,B625 --out hotels_test.xlsx
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd

from archive.accor_1_0_6.accor_1_0_0.scrape_accor.hotels import (
    code_for_url,
    fetch_hotel,
    normalize_hotel_code,
    write_hotels_xlsx,
)

ROOT = Path(__file__).resolve().parent.parent
HOTELS_DIR = ROOT / "data" / "marques" / "hotels"
STATE_DIR = ROOT / "data" / "marques" / "hotels_state"


def _load_codes_from_xlsx(path: Path, col: str = "hotel_code_accor") -> list[str]:
    df = pd.read_excel(path)
    if col not in df.columns:
        # fallback first column
        col = df.columns[0]
    codes = []
    for v in df[col].dropna().astype(str):
        c = v.strip()
        if c and c.lower() != "nan":
            codes.append(c)
    # preserve order, unique
    seen: set[str] = set()
    out: list[str] = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _existing_codes(hotels_all: Path | None = None) -> set[str]:
    """Codes déjà connus (forme brute + normalisée sans zéros)."""
    path = hotels_all or (HOTELS_DIR / "hotels_all.xlsx")
    if not path.exists():
        return set()
    try:
        df = pd.read_excel(path, sheet_name="hotels")
    except ValueError:
        df = pd.read_excel(path, sheet_name=0)
    if df.empty or "hotel_code_accor" not in df.columns:
        return set()
    codes: set[str] = set()
    for v in df["hotel_code_accor"].dropna().astype(str):
        s = v.strip().upper()
        codes.add(s)
        if s.isdigit():
            codes.add(str(int(s)))  # 0785 ↔ 785
            codes.add(s.zfill(4))
    return codes


def _progress_path(tag: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"codes_{tag}_progress.json"


def scrape_code_list(
    codes: list[str],
    *,
    out_name: str = "hotels_codes.xlsx",
    workers: int = 12,
    pause_s: float = 0.35,
    pad4: bool = False,
    skip_existing: bool = True,
    force: bool = False,
    tag: str | None = None,
) -> dict[str, Any]:
    """Scrape une liste de codes en parallèle (threads I/O)."""
    HOTELS_DIR.mkdir(parents=True, exist_ok=True)
    tag = tag or Path(out_name).stem
    out_path = HOTELS_DIR / out_name
    prog_path = _progress_path(tag)

    # normalize codes (pad4 auto pour <1000 via code_for_url)
    codes = [
        normalize_hotel_code(c, pad4=True) if pad4 else code_for_url(c) for c in codes
    ]
    # unique preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    codes = uniq

    existing = _existing_codes() if skip_existing else set()
    if skip_existing and existing:
        before = len(codes)
        codes = [
            c
            for c in codes
            if c not in existing
            and (not c.isdigit() or str(int(c)) not in existing)
            and c.zfill(4) not in existing
        ]
        print(f"[codes] skip existing: {before} → {len(codes)} à scraper")

    rows: list[dict[str, Any]] = []
    done: set[str] = set()
    if prog_path.exists() and not force:
        try:
            prev = json.loads(prog_path.read_text(encoding="utf-8"))
            rows = list(prev.get("rows") or [])
            done = {
                str(r.get("hotel_code_accor") or "").strip().upper()
                for r in rows
                if r.get("hotel_code_accor")
            }
            print(f"[codes] reprise progress: {len(done)} déjà traités")
        except Exception:
            rows, done = [], set()

    pending = [c for c in codes if c.upper() not in done]
    print(
        f"[codes] total={len(codes)} pending={len(pending)} "
        f"workers={workers} pause={pause_s}s → {out_path.name}"
    )

    n_ok = sum(1 for r in rows if r.get("status") == "ok")
    n_missing = sum(1 for r in rows if r.get("status") == "missing")
    n_error = sum(1 for r in rows if r.get("status") == "error")
    t0 = time.perf_counter()
    lock_rows: list[dict[str, Any]] = list(rows)

    def _one(code: str) -> dict[str, Any]:
        return fetch_hotel(code, pause_s=pause_s, pad4=False)

    save_every = max(10, workers * 2)
    completed = 0

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {ex.submit(_one, c): c for c in pending}
        for fut in as_completed(futs):
            code = futs[fut]
            try:
                rec = fut.result()
            except Exception as exc:  # noqa: BLE001
                rec = {
                    "hotel_code_accor": code,
                    "status": "error",
                    "error": str(exc),
                    "url": f"https://all.accor.com/hotel/{code}/index.fr.shtml",
                }
            lock_rows.append(rec)
            st = rec.get("status")
            if st == "ok":
                n_ok += 1
            elif st == "missing":
                n_missing += 1
            else:
                n_error += 1
            completed += 1

            if completed % save_every == 0 or completed == len(pending):
                prog_path.write_text(
                    json.dumps(
                        {
                            "tag": tag,
                            "n_ok": n_ok,
                            "n_missing": n_missing,
                            "n_error": n_error,
                            "completed": completed,
                            "pending_total": len(pending),
                            "rows": lock_rows,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                elapsed = time.perf_counter() - t0
                rate = completed / elapsed if elapsed > 0 else 0
                eta = (len(pending) - completed) / rate if rate > 0 else 0
                print(
                    f"[codes] {completed}/{len(pending)} "
                    f"ok={n_ok} miss={n_missing} err={n_error} "
                    f"({elapsed:.0f}s, {rate:.1f}/s, ETA {eta:.0f}s)"
                )

    ok_rows = [r for r in lock_rows if r.get("status") == "ok"]
    log_rows = [
        {
            "hotel_code_accor": r.get("hotel_code_accor"),
            "status": r.get("status"),
            "http_status": r.get("http_status"),
            "error": r.get("error") or r.get("note") or "",
            "url": r.get("url"),
        }
        for r in lock_rows
    ]
    # Texte forcé pour garder 0785 / 0339 (sinon Excel → int 785)
    write_hotels_xlsx(out_path, ok_rows, log_rows)

    elapsed = time.perf_counter() - t0
    summary = {
        "ok": True,
        "out": str(out_path),
        "n_requested": len(codes),
        "n_pending_at_start": len(pending),
        "n_ok": n_ok,
        "n_missing": n_missing,
        "n_error": n_error,
        "elapsed_s": round(elapsed, 1),
        "rate_per_s": round(len(pending) / elapsed, 2) if elapsed > 0 else 0,
    }
    (STATE_DIR / f"codes_{tag}_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="Scrape liste de codes hôtels Accor")
    p.add_argument("--from-xlsx", type=str, default="", help="Excel avec hotel_code_accor")
    p.add_argument("--codes", type=str, default="", help="Codes séparés par virgule")
    p.add_argument(
        "--pad4-range",
        nargs=2,
        type=int,
        metavar=("START", "END"),
        help="Génère codes numériques zero-pad 4 (ex: 0 999 → 0000..0999)",
    )
    p.add_argument("--out", type=str, default="hotels_codes.xlsx")
    p.add_argument(
        "--workers",
        type=int,
        default=12,
        help="Threads I/O (ou process via parallel_codes, max 12 agents)",
    )
    p.add_argument("--pause", type=float, default=0.35)
    p.add_argument("--pad4", action="store_true", help="Force zfill(4) sur codes numériques")
    p.add_argument("--no-skip-existing", action="store_true")
    p.add_argument("--force", action="store_true", help="Ignore progress partiel")
    p.add_argument("--tag", type=str, default="", help="Tag progress (défaut = stem out)")
    args = p.parse_args()

    codes: list[str] = []
    if args.from_xlsx:
        path = Path(args.from_xlsx)
        if not path.is_absolute():
            # try relative to cwd then to ROOT
            if not path.exists():
                alt = ROOT / path
                path = alt if alt.exists() else path
        codes.extend(_load_codes_from_xlsx(path))
    if args.codes:
        codes.extend(c.strip() for c in args.codes.split(",") if c.strip())
    if args.pad4_range:
        start, end = args.pad4_range
        codes.extend(f"{i:04d}" for i in range(start, end + 1))
        args.pad4 = True

    if not codes:
        p.error("Fournir --from-xlsx et/ou --codes et/ou --pad4-range")

    scrape_code_list(
        codes,
        out_name=args.out,
        workers=args.workers,
        pause_s=args.pause,
        pad4=args.pad4,
        skip_existing=not args.no_skip_existing,
        force=args.force,
        tag=args.tag or None,
    )


if __name__ == "__main__":
    main()
