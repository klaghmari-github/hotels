from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List

@dataclass
class CategoryMix:
    fb_share: float = 0.7
    non_fb_share: float = 0.3
    category_shares: Dict[str, float] = field(default_factory=dict)
    subcategory_shares: Dict[str, float] = field(default_factory=dict)

    def normalize(self) -> "CategoryMix":
        total = self.fb_share + self.non_fb_share
        if total > 0:
            self.fb_share /= total
            self.non_fb_share /= total
        return self

@dataclass
class StoreConfiguration:
    concept: str = "SIMPLY"
    m_lin: float = 2.0
    mix: CategoryMix = field(default_factory=CategoryMix)
    allowed_categories: List[str] = field(default_factory=list)
    excluded_categories: List[str] = field(default_factory=list)
    locked_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StoreConfiguration":
        data = data or {}
        mix_data = data.get("mix") or {}
        if "fb_share" in data or "non_fb_share" in data:
            mix_data = {
                **mix_data,
                "fb_share": data.get("fb_share", mix_data.get("fb_share", 0.7)),
                "non_fb_share": data.get("non_fb_share", mix_data.get("non_fb_share", 0.3)),
            }
        return cls(
            concept=data.get("concept", "SIMPLY"),
            m_lin=float(data.get("m_lin", 2.0)),
            mix=CategoryMix(**mix_data).normalize(),
            allowed_categories=data.get("allowed_categories", []) or [],
            excluded_categories=data.get("excluded_categories", []) or [],
            locked_fields=data.get("locked_fields", []) or [],
        )
