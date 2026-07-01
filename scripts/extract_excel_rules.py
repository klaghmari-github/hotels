#!/usr/bin/env python3
"""Extrait les constantes des classeurs Excel ROD (stub — à compléter cellule par cellule)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rod_ia.config.settings import get_settings


def main() -> None:
    settings = get_settings()
    simulator_xlsx = settings.sources_raw_dir / "ROD - Simulateurs + détail des coûts.xlsx"
    if not simulator_xlsx.exists():
        raise SystemExit(f"Fichier manquant: {simulator_xlsx}")

    # TODO: parser openpyxl et mapper vers rod_reference.json
    payload = {
        "_status": "stub",
        "_message": (
            "Extraction Excel non encore implémentée. "
            "Les formules doivent être mappées vers data/reference/rod_reference.json "
            "avec traçabilité RuleTrace."
        ),
        "source_file": str(simulator_xlsx.name),
    }
    out_path = settings.data_reference_dir / "rod_reference_extracted.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Stub écrit: {out_path}")


if __name__ == "__main__":
    main()