#!/usr/bin/env python3
"""
Lance LOO old + new + comparaison.

Usage :
  python pipeline_sim_v1/run_all.py
  python -m pipeline_sim_v1.run_all
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permet l'execution directe (python pipeline_sim_v1/run_all.py)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    from pipeline_sim_v1.compare import run as run_compare
    from pipeline_sim_v1.constants import EVAL_CODES, EXCLUDED_HOTELS
    from pipeline_sim_v1.run_pipeline import export_pipeline_excel, run_loo_pipeline
    from pipeline_sim_v1.sim_v1_old import run as run_old

    print(
        "=== sim_v1 LOO — 6 hotels (excl. {}) ===".format(
            ", ".join(sorted(EXCLUDED_HOTELS))
        )
    )
    print("Hotels :", ", ".join(EVAL_CODES))
    print()

    print("--- old (RevenueRules Python) ---")
    old = run_old()
    print(old["metrics"].to_string(index=False))
    print(f"→ {old['excel_path']}")
    print()

    print("--- new (ConnectionPipeline DuckDB + YAML) ---")
    pipe = run_loo_pipeline(rebuild=True)
    excel_new = export_pipeline_excel(pipe)
    print(pipe["metrics"].to_string(index=False))
    print(f"→ {excel_new}")
    print()

    print("--- comparaison old vs pipeline ---")
    cmp = run_compare(rerun=False)
    print(cmp["metrics_side_by_side"].to_string(index=False))
    print()
    if not cmp["delta_mae"].empty:
        print("Delta MAE (new − old) :")
        print(cmp["delta_mae"].to_string(index=False))
    print(f"→ {cmp['excel_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
