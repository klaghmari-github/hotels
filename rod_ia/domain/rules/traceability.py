"""Traçabilité règle Python ↔ cellule Excel."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class RuleTrace:
    """Lien explicite entre une règle Python et sa source Excel."""

    rule_id: str
    workbook: str
    sheet: str
    cells: list[str]
    business_description: str
    python_method: str
    status: str
    excel_formula: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)