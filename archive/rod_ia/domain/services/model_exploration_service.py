"""Exploration du modele multi sorties : arbres XGBoost et predictions interactives."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from rod_ia.domain.services.ai_predictor import AIRodRevenuePredictor
from rod_ia.domain.services.ml_column_naming import MLColumnNaming


class ModelExplorationService:
    """Inspecte les arbres appris et produit des predictions avec surcharge de variables."""

    MONTH_LABELS = (
        "Janvier",
        "Fevrier",
        "Mars",
        "Avril",
        "Mai",
        "Juin",
        "Juillet",
        "Aout",
        "Septembre",
        "Octobre",
        "Novembre",
        "Decembre",
    )

    def __init__(
        self,
        predictor: AIRodRevenuePredictor,
        processed_dir: Path,
    ) -> None:
        self._predictor = predictor
        self._processed_dir = Path(processed_dir)

    def _feature_labels(self) -> list[str]:
        return list(self._predictor.feature_cols)

    def _target_labels(self) -> list[str]:
        return list(self._predictor.target_cols)

    def _load_training_meta(self) -> dict[str, Any]:
        meta_path = self._predictor.artifacts_dir / "meta.json"
        if not meta_path.exists():
            return {}
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def _align_to_feature_cols(self, row: pd.Series) -> pd.Series:
        """Aligne une ligne sur les colonnes du modele (0.0 si absentes)."""
        cols = self._feature_labels()
        if not cols:
            return pd.Series(dtype=float)
        return row.reindex(cols).fillna(0.0).astype(float)

    def _default_feature_row(self, hotel_id: str | None) -> pd.Series:
        cols = self._feature_labels()
        if not cols:
            return pd.Series(dtype=float)

        source_path = self._processed_dir / "ml_dataset_full.csv"
        if not source_path.exists():
            source_path = self._processed_dir / "X_descriptive.csv"
        if not source_path.exists():
            return pd.Series(0.0, index=cols)

        frame = pd.read_csv(source_path).fillna(0.0)
        if hotel_id and "hotel_id" in frame.columns:
            match = frame[frame["hotel_id"].astype(str) == str(hotel_id)]
            if not match.empty:
                return self._align_to_feature_cols(match.iloc[0])

        present = [c for c in cols if c in frame.columns]
        if present:
            return self._align_to_feature_cols(frame[present].mean())
        return pd.Series(0.0, index=cols)

    @staticmethod
    def _human_target(name: str) -> str:
        m = re.search(r"m(\d{2})_(ca_total|ventes_total)", name)
        if not m:
            return name.replace("t_", "").replace("_", " ")
        month = int(m.group(1))
        kind = "CA" if "ca" in m.group(2) else "ventes"
        label = ModelExplorationService.MONTH_LABELS[month - 1]
        return f"{label} — {kind}"

    def meta(self) -> dict[str, Any]:
        model = self._predictor.model
        warnings = list(self._predictor.load_warnings)
        n_trees = 0
        if model is not None and getattr(model, "estimators_", None):
            n_trees = int(getattr(model.estimators_[0], "n_estimators", 0))
        targets = [
            {"index": i, "name": name, "label": self._human_target(name)}
            for i, name in enumerate(self._target_labels())
        ]
        dataset_warnings: list[str] = []
        meta_path = self._processed_dir / "dataset_meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            dataset_cols = meta.get("feature_cols", [])
            model_cols = self._feature_labels()
            missing = [c for c in model_cols if c not in dataset_cols]
            if missing:
                dataset_warnings.append(
                    f"{len(missing)} variable(s) du modele absentes du dataset courant "
                    "(valeur 0 a la prediction). Re-executer ./init.sh pour re-aligner."
                )
        warnings = warnings + dataset_warnings
        training_meta = self._load_training_meta()

        return {
            "model_available": model is not None,
            "warnings": warnings,
            "n_outputs": len(targets),
            "n_trees_per_output": n_trees,
            "tree_range": {"min": 1, "max": max(n_trees, 1)},
            "production_model": training_meta.get("production_model", "xgboost"),
            "model_comparison": training_meta.get("model_comparison"),
            "neural_network": training_meta.get("neural_network"),
            "features": [
                {"name": c, "label": c.replace("d_", "").replace("_", " ")[:60]}
                for c in self._feature_labels()
            ],
            "targets": targets,
        }

    def tree(self, target_index: int, tree_number: int) -> dict[str, Any]:
        model = self._predictor.model
        if model is None:
            raise ValueError("Modele absent. Executer ./init.sh.")
        estimators = getattr(model, "estimators_", None)
        if not estimators:
            raise ValueError("Structure de modele non supportee.")
        if target_index < 0 or target_index >= len(estimators):
            raise ValueError(f"Sortie invalide (0-{len(estimators) - 1}).")
        n_trees = int(estimators[target_index].n_estimators)
        if tree_number < 1 or tree_number > n_trees:
            raise ValueError(f"Arbre invalide (1-{n_trees}).")
        dump = estimators[target_index].get_booster().get_dump(dump_format="json")
        node = json.loads(dump[tree_number - 1])
        feature_cols = self._feature_labels()
        return {
            "target_index": target_index,
            "target_name": self._target_labels()[target_index],
            "target_label": self._human_target(self._target_labels()[target_index]),
            "tree_number": tree_number,
            "n_trees_total": n_trees,
            "feature_cols": feature_cols,
            "tree": node,
        }

    def _breakdown_by_category(
        self, features: pd.Series, monthly_ca: list[float], monthly_ventes: list[float]
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for month in range(1, 13):
            ca_total = monthly_ca[month - 1]
            ventes_total = monthly_ventes[month - 1]
            prefix = f"d_pct_mois_m{month:02d}"
            type_cols = [c for c in features.index if c.startswith(prefix) and "gamme" in c]
            for col in type_cols:
                pct = float(features.get(col, 0.0) or 0.0)
                if pct <= 0:
                    continue
                parts = col.replace(prefix + "_", "").split("_gamme_")
                type_label = parts[0].replace("type_", "") if parts else "autre"
                gamme = parts[1] if len(parts) > 1 else ""
                rows.append(
                    {
                        "month": month,
                        "month_label": self.MONTH_LABELS[month - 1],
                        "type": type_label,
                        "gamme": gamme.replace("_", " "),
                        "pct": round(pct * 100, 2),
                        "ca_estime": round(ca_total * pct, 2),
                        "ventes_estimees": round(ventes_total * pct, 2),
                    }
                )
        return rows

    def predict(
        self,
        hotel_id: str | None = None,
        feature_overrides: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        model = self._predictor.model
        if model is None:
            raise ValueError("Modele absent. Executer ./init.sh.")
        cols = self._feature_labels()
        row = self._default_feature_row(hotel_id)
        overrides = feature_overrides or {}
        for key, val in overrides.items():
            if key in row.index:
                row[key] = float(val)
        frame = pd.DataFrame([self._align_to_feature_cols(row)])
        raw = model.predict(frame.values)
        values = raw[0] if hasattr(raw, "__len__") else [float(raw)]
        target_cols = self._target_labels()

        monthly_ca = [0.0] * 12
        monthly_ventes = [0.0] * 12
        per_target: list[dict[str, Any]] = []
        for col, val in zip(target_cols, values):
            v = max(float(val), 0.0)
            m = re.search(r"m(\d{2})_(ca_total|ventes_total)", col)
            if m:
                idx = int(m.group(1)) - 1
                if "ca_total" in col:
                    monthly_ca[idx] = v
                else:
                    monthly_ventes[idx] = v
            per_target.append(
                {
                    "target": col,
                    "label": self._human_target(col),
                    "value": round(v, 2),
                }
            )

        breakdown = self._breakdown_by_category(row, monthly_ca, monthly_ventes)
        return {
            "hotel_id": hotel_id,
            "features_used": {c: round(float(row.get(c, 0.0)), 4) for c in cols[:30]},
            "feature_overrides": overrides,
            "per_target": per_target,
            "monthly_global": [
                {
                    "month": m + 1,
                    "month_label": self.MONTH_LABELS[m],
                    "ca_total": round(monthly_ca[m], 2),
                    "ventes_total": round(monthly_ventes[m], 2),
                }
                for m in range(12)
            ],
            "annual_totals": {
                "ca_annuel": round(sum(monthly_ca), 2),
                "ventes_annuelles": round(sum(monthly_ventes), 2),
                "ca_mensuel_moyen": round(sum(monthly_ca) / 12.0, 2),
            },
            "breakdown_by_category": breakdown[:48],
            "breakdown_note": (
                "Ventilation type et gamme calculee a partir des repartitions historiques "
                "et des totaux mensuels predits par le modele."
            ),
        }