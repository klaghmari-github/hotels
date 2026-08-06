#!/usr/bin/env python3
"""
Pipeline mondial : catalog pays → manquants vs hotels_all → scrape parallèle → merge.

```bash
cd accord
# 1) Catalog tous les pays + liste manquants
python -m scrape_accor.world_scrape --catalog-only

# 2) Scrape des manquants (ou tout-en-un)
python -m scrape_accor.world_scrape --scrape-missing --workers 12 --threads 3

# 3) Tout
python -m scrape_accor.world_scrape --all --workers 12 --threads 3
```
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from archive.accor_1_0_6.accor_1_0_0.scrape_accor.countries_config import COUNTRIES, WORLD_SLUGS
from archive.accor_1_0_6.accor_1_0_0.scrape_accor.destination_country import (
    HOTELS_DIR,
    fetch_catalog,
    find_missing,
    load_existing_hotels,
)

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "data" / "marques" / "hotels_state"


def run_catalog_all(
    *,
    slugs: list[str] | None = None,
    pause_s: float = 0.15,
) -> dict[str, Any]:
    """Télécharge le catalog de chaque pays, produit missing combiné."""
    slugs = slugs or list(WORLD_SLUGS)
    HOTELS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    existing = load_existing_hotels()
    per_country: dict[str, Any] = {}
    all_frames: list[pd.DataFrame] = []
    missing_frames: list[pd.DataFrame] = []

    t0 = time.perf_counter()
    for i, slug in enumerate(slugs, 1):
        cfg = COUNTRIES[slug]
        q = cfg["query"]
        label = cfg["label"]
        dest_url = cfg.get("dest_url") or "https://all.accor.com/"
        print(f"\n[{i}/{len(slugs)}] {label} ({slug}) q={q!r}")
        try:
            api = fetch_catalog(q, referer=dest_url, pause_s=pause_s)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR catalog: {exc}")
            per_country[slug] = {
                "label": label,
                "query": q,
                "n_catalog": 0,
                "n_missing": 0,
                "n_matched": 0,
                "error": str(exc),
            }
            continue

        if api.empty:
            print(f"  empty catalog")
            per_country[slug] = {
                "label": label,
                "query": q,
                "n_catalog": 0,
                "n_missing": 0,
                "n_matched": 0,
            }
            # still write empty all
            api.to_excel(
                HOTELS_DIR / f"{slug}_destination_all.xlsx",
                index=False,
                sheet_name="hotels",
            )
            continue

        api = api.copy()
        api["country_slug"] = slug
        api["country_label"] = label
        api["region"] = cfg.get("region", "")

        missing, matched = find_missing(api, existing)
        if not missing.empty:
            missing = missing.copy()
            missing["country_slug"] = slug
            missing["country_label"] = label
            missing["region"] = cfg.get("region", "")
            missing_frames.append(missing)
        all_frames.append(api)

        # per-country files
        api.to_excel(
            HOTELS_DIR / f"{slug}_destination_all.xlsx",
            index=False,
            sheet_name="hotels",
        )
        missing.to_excel(
            HOTELS_DIR / f"{slug}_destination_missing.xlsx",
            index=False,
            sheet_name="missing",
        )
        missing.to_csv(
            HOTELS_DIR / f"{slug}_destination_missing.csv", index=False
        )
        matched.to_excel(
            HOTELS_DIR / f"{slug}_destination_matched.xlsx",
            index=False,
            sheet_name="matched",
        )

        per_country[slug] = {
            "label": label,
            "query": q,
            "region": cfg.get("region", ""),
            "n_catalog": int(len(api)),
            "n_missing": int(len(missing)),
            "n_matched": int(len(matched)),
        }
        print(
            f"  catalog={len(api)} matched={len(matched)} missing={len(missing)}"
        )

    # World catalog (unique codes)
    world_path = HOTELS_DIR / "world_catalog_all.xlsx"
    if all_frames:
        world = pd.concat(all_frames, ignore_index=True)
        world = world.drop_duplicates(subset=["hotel_code_accor"], keep="first")
        world.to_excel(world_path, index=False, sheet_name="hotels")
        n_world = len(world)
    else:
        n_world = 0
        pd.DataFrame().to_excel(world_path, index=False)

    # Combined missing
    miss_path = HOTELS_DIR / "world_missing.xlsx"
    miss_csv = HOTELS_DIR / "world_missing.csv"
    if missing_frames:
        miss = pd.concat(missing_frames, ignore_index=True)
        miss = miss.drop_duplicates(subset=["hotel_code_accor"], keep="first")
        miss.to_excel(miss_path, index=False, sheet_name="missing")
        miss.to_csv(miss_csv, index=False)
        n_missing = len(miss)
    else:
        n_missing = 0
        pd.DataFrame().to_excel(miss_path, index=False)
        pd.DataFrame().to_csv(miss_csv, index=False)

    elapsed = time.perf_counter() - t0
    summary = {
        "ok": True,
        "n_countries": len(slugs),
        "n_world_unique": n_world,
        "n_missing_unique": n_missing,
        "n_existing": int(existing["hotel_code_norm"].nunique())
        if not existing.empty and "hotel_code_norm" in existing.columns
        else len(existing),
        "elapsed_s": round(elapsed, 1),
        "world_catalog": str(world_path),
        "world_missing": str(miss_path),
        "world_missing_csv": str(miss_csv),
        "per_country": per_country,
        "zero_catalog": [
            s for s, v in per_country.items() if v.get("n_catalog", 0) == 0
        ],
    }
    (HOTELS_DIR / "world_catalog_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\n======== CATALOG SUMMARY ========")
    print(
        f"countries={len(slugs)} world_unique={n_world} "
        f"missing={n_missing} existing={summary['n_existing']} "
        f"in {elapsed:.0f}s"
    )
    print(f"zero catalog: {summary['zero_catalog']}")
    return summary


def run_scrape_missing(
    *,
    workers: int = 12,
    threads: int = 3,
    pause_s: float = 0.22,
    missing_xlsx: Path | None = None,
) -> dict[str, Any]:
    from archive.accor_1_0_6.accor_1_0_0.scrape_accor.parallel_codes import run_parallel

    missing_xlsx = missing_xlsx or (HOTELS_DIR / "world_missing.xlsx")
    if not missing_xlsx.exists():
        return {"ok": False, "error": f"missing file not found: {missing_xlsx}"}

    return run_parallel(
        from_xlsx=str(missing_xlsx),
        out_name="hotels_missing_world.xlsx",
        workers=workers,
        threads_per_worker=threads,
        pause_s=pause_s,
        skip_existing=True,
        merge_all=True,
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Scrape mondial Accor par pays")
    p.add_argument("--catalog-only", action="store_true")
    p.add_argument("--scrape-missing", action="store_true")
    p.add_argument("--all", action="store_true", help="catalog + scrape + merge")
    p.add_argument(
        "--workers",
        type=int,
        default=12,
        help="Process agents en parallèle (max recommandé 12)",
    )
    p.add_argument("--threads", type=int, default=3)
    p.add_argument("--pause", type=float, default=0.2)
    p.add_argument(
        "--region",
        choices=["europe", "africa_me", "asia", "oceania", "americas"],
        help="Limiter à une région",
    )
    p.add_argument(
        "--countries",
        type=str,
        default="",
        help="Slugs séparés par virgule (sinon tous)",
    )
    args = p.parse_args()

    if args.countries:
        slugs = [s.strip() for s in args.countries.split(",") if s.strip()]
    elif args.region:
        slugs = [
            s
            for s, c in COUNTRIES.items()
            if c.get("region") == args.region
        ]
    else:
        slugs = list(WORLD_SLUGS)

    unknown = [s for s in slugs if s not in COUNTRIES]
    if unknown:
        p.error(f"Slugs inconnus: {unknown}")

    do_catalog = args.catalog_only or args.all or (
        not args.scrape_missing and not args.catalog_only and not args.all
    )
    # default if no flag: --all behavior for convenience when only region given
    if not args.catalog_only and not args.scrape_missing and not args.all:
        args.all = True
        do_catalog = True

    if do_catalog or args.all:
        cat = run_catalog_all(slugs=slugs, pause_s=args.pause)
        print(json.dumps({k: v for k, v in cat.items() if k != "per_country"}, indent=2))

    if args.scrape_missing or args.all:
        # refresh existing after catalog
        scrape = run_scrape_missing(
            workers=args.workers,
            threads=args.threads,
            pause_s=args.pause,
        )
        print(json.dumps(scrape, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
