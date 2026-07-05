#!/usr/bin/env python3
"""Compare les cellules Excel ROD avec ``rod_reference.json`` — rapport d'audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rod_ia.config.settings import get_settings
from rod_ia.domain.services.rod_excel_extractor import RodExcelExtractor

# Mapping audit : clé JSON → (feuille, cellule) ou fonction d'extraction
AUDIT_CELLS: dict[str, tuple[str, str]] = {
    "concepts.SIMPLY.pivot_nb_chambres": ("SIMULATEUR SIMPLY", "C9"),
    "concepts.SIMPLY.pivot_to": ("SIMULATEUR SIMPLY", "C11"),
    "concepts.SIMPLY.pivot_m_lin": ("SIMULATEUR SIMPLY", "F9"),
    "concepts.SIMPLY.base_monthly_ca_fb": ("SIMULATEUR SIMPLY", "E34"),
    "concepts.SIMPLY.base_monthly_ca_nf": ("SIMULATEUR SIMPLY", "E35"),
    "concepts.SIMPLY.base_monthly_sales": ("SIMULATEUR SIMPLY", "C19"),
    "concepts.SIMPLY.margin_fb_pct": ("SIMULATEUR SIMPLY", "J9"),
    "concepts.SIMPLY.monthly_cost_total": ("SIMULATEUR SIMPLY", "H168"),
    "concepts.LIBERTY.pivot_nb_chambres": ("SIMULATEUR LIBERTY", "C9"),
    "concepts.LIBERTY.base_monthly_ca": ("SIMULATEUR LIBERTY", "E122"),
    "concepts.CONNECTED.pivot_nb_chambres": ("SIMULATEUR CONNECTED", "C9"),
    "concepts.CONNECTED.base_monthly_ca": ("SIMULATEUR CONNECTED", "E122"),
    "impact_to.ht_per_0_01_to": ("REVENUS - IMPACT TO", "F12"),
}


def _flatten(data: dict, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in data.items():
        if key.startswith("_"):
            continue
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_flatten(value, path))
        else:
            out[path] = value
    return out


def _get_nested(data: dict, dotted: str) -> object:
    node: object = data
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> None:
    settings = get_settings()
    simulator_xlsx = next(settings.sources_raw_dir.glob("ROD - Simulateurs*.xlsx"), None)
    if not simulator_xlsx:
        raise SystemExit(f"Fichier simulateur absent dans {settings.sources_raw_dir}")

    ref_path = settings.data_reference_dir / "rod_reference.json"
    extractor = RodExcelExtractor(simulator_xlsx, ref_path)
    extracted = extractor.extract()

    import openpyxl

    wb = openpyxl.load_workbook(simulator_xlsx, data_only=True, read_only=True)
    rows: list[dict] = []
    for key, (sheet, cell) in AUDIT_CELLS.items():
        excel_val = None
        if sheet in wb.sheetnames:
            excel_val = _to_float(wb[sheet][cell].value)
        json_val = _to_float(_get_nested(extracted, key))
        if key.endswith("base_monthly_ca"):
            fb_key = key.replace("base_monthly_ca", "base_monthly_ca_fb")
            nf_key = key.replace("base_monthly_ca", "base_monthly_ca_nf")
            json_val = (_to_float(_get_nested(extracted, fb_key)) or 0) + (
                _to_float(_get_nested(extracted, nf_key)) or 0
            )
        delta = None
        status = "ok"
        if excel_val is not None and json_val is not None:
            delta = json_val - excel_val
            status = "ok" if abs(delta) < 0.05 else "mismatch"
        elif excel_val is None:
            status = "excel_missing"
        else:
            status = "json_missing"
        rows.append(
            {
                "key": key,
                "sheet": sheet,
                "cell": cell,
                "excel": excel_val,
                "json": json_val,
                "delta": delta,
                "status": status,
            }
        )
    wb.close()

    mismatches = [r for r in rows if r["status"] == "mismatch"]
    report = {
        "source_file": simulator_xlsx.name,
        "reference_file": str(ref_path),
        "n_checks": len(rows),
        "n_mismatches": len(mismatches),
        "n_ok": sum(1 for r in rows if r["status"] == "ok"),
        "rows": rows,
        "cost_lines_present": {
            concept: "cost_lines" in (extracted.get("concepts", {}).get(concept) or {})
            for concept in ("SIMPLY", "LIBERTY", "CONNECTED")
        },
    }

    out_path = settings.data_reference_dir / "rod_reference_extracted.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Audit écrit: {out_path}")
    print(f"Vérifications: {report['n_ok']}/{report['n_checks']} OK, {report['n_mismatches']} écarts")
    if mismatches:
        for row in mismatches:
            print(f"  ÉCART {row['key']}: excel={row['excel']} json={row['json']}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()