from dataclasses import dataclass, asdict
from typing import Optional, List

@dataclass
class RuleTrace:
    rule_id: str
    workbook: str
    sheet: str
    cells: List[str]
    excel_formula: Optional[str]
    business_description: str
    python_method: str
    status: str = "implemented_or_pending_validation"

    def to_dict(self) -> dict:
        return asdict(self)
