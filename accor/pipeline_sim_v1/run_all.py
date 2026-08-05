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
    from pipeline_sim_v1.sim_v1_new import run as run_new
    from pipeline_sim_v1.sim_v1_old import run as run_old

    print("=== sim_v1 LOO — 6 hotels (excl. {}) ===".format(", ".join(sorted(EXCLUDED_HOTELS))))
    print("Hotels :", ", ".join(EVAL_CODES))
    print()

    print("--- old (RevenueRules) ---")
    old = run_old()
    print(old["metrics"].to_string(index=False))
    print(f"→ {old['excel_path']}")
    print()

    print("--- new (formules R1-R4) ---")
    new = run_new()
    print(new["metrics"].to_string(index=False))
    print(f"→ {new['excel_path']}")
    print()

    print("--- comparaison ---")
    # Excel deja ecrits ; compare sans double recalcul des predict
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
