"""Sélection des variables ML — variance nulle, doublons exacts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class FeatureSelectionReport:
    """Trace les colonnes retirées et la justification."""

    removed_constant: list[dict[str, Any]] = field(default_factory=list)
    removed_duplicate: list[dict[str, Any]] = field(default_factory=list)
    kept_features: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "removed_constant": self.removed_constant,
            "removed_duplicate": self.removed_duplicate,
            "kept_features": self.kept_features,
            "n_removed_constant": len(self.removed_constant),
            "n_removed_duplicate": len(self.removed_duplicate),
            "n_kept": len(self.kept_features),
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


class FeatureSelector:
    """Retire les ``d_*`` non informatives (constantes ou redondantes)."""

    def select(
        self,
        dataset: pd.DataFrame,
        feature_cols: list[str] | None = None,
    ) -> tuple[pd.DataFrame, list[str], FeatureSelectionReport]:
        frame = dataset.copy()
        cols = feature_cols or [c for c in frame.columns if c.startswith("d_")]
        report = FeatureSelectionReport()
        kept = list(cols)

        for col in list(kept):
            if col not in frame.columns:
                kept.remove(col)
                continue
            series = pd.to_numeric(frame[col], errors="coerce")
            if int(series.isna().sum()) > 0:
                report.removed_constant.append(
                    {
                        "column": col,
                        "reason": "non_numerique",
                        "value": None,
                        "justification": "Valeurs texte ou non convertibles — exclue de X.",
                    }
                )
                frame = frame.drop(columns=[col])
                kept.remove(col)
                continue
            nunique = int(series.nunique(dropna=True))
            if nunique <= 1:
                constant_val = float(series.dropna().iloc[0]) if series.notna().any() else 0.0
                report.removed_constant.append(
                    {
                        "column": col,
                        "reason": "variance_nulle",
                        "value": constant_val,
                        "justification": "Même valeur sur toutes les lignes — non exploitable pour le ML.",
                    }
                )
                frame = frame.drop(columns=[col])
                kept.remove(col)

        seen_hashes: dict[str, str] = {}
        for col in list(kept):
            if col not in frame.columns:
                continue
            fingerprint = tuple(pd.to_numeric(frame[col], errors="coerce").fillna(-9999.0).tolist())
            if fingerprint in seen_hashes:
                twin = seen_hashes[fingerprint]
                report.removed_duplicate.append(
                    {
                        "column": col,
                        "duplicate_of": twin,
                        "reason": "colonnes_identiques",
                        "justification": f"Valeurs identiques à {twin} sur tous les hôtels.",
                    }
                )
                frame = frame.drop(columns=[col])
                kept.remove(col)
            else:
                seen_hashes[fingerprint] = col

        report.kept_features = kept
        return frame, kept, report