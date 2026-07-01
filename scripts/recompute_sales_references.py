#!/usr/bin/env python3
"""Recalcule les références ventes (mix et moyennes mensuelles)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rod_ia.config.settings import get_settings
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.services.sales_mix_extractor import SalesMixExtractor
from rod_ia.domain.services.sales_percentage_service import SalesPercentageService


def main() -> None:
    settings = get_settings()
    registry = HotelIdentityRegistry(settings.identity_registry_path)
    extractor = SalesMixExtractor(settings.sales_csv_path, registry)
    monthly_avg = extractor.monthly_average_targets(exclude_year=2026)
    pct_service = SalesPercentageService(monthly_avg)
    pct_wide, pct_long = pct_service.compute_all()

    output = {
        "monthly_average_note": (
            "Moyenne mensuelle par hotel_id/mois/type/gamme — pas somme des années."
        ),
        "monthly_average_rows": monthly_avg.to_dict(orient="records"),
        "percentage_wide_columns": list(pct_wide.columns) if not pct_wide.empty else [],
        "percentage_long_rows": pct_long.to_dict(orient="records") if not pct_long.empty else [],
    }
    out_path = settings.data_reference_dir / "recomputed_sales_reference.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Écrit: {out_path}")


if __name__ == "__main__":
    main()