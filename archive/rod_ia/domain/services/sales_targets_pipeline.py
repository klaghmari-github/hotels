"""Pipeline OOP des targets IA — entraînement (< année test) vs test/évaluation (holdout)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from rod_ia.domain.repositories.feature_store_repository import FeatureStoreRepository
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.services.feature_imputer import FeatureImputer
from rod_ia.domain.services.feature_selector import FeatureSelector
from rod_ia.domain.services.ml_column_naming import MLColumnNaming
from rod_ia.domain.services.rod_recap_extractor import RodRecapExtractor
from rod_ia.domain.services.sales_mix_extractor import SalesMixExtractor
from rod_ia.domain.services.sales_percentage_service import SalesPercentageService


@dataclass
class SalesTargetsPipelineConfig:
    """Configuration du pipeline targets."""

    evaluation_year: int = 2026
    sales_path: Path | None = None
    output_dir: Path | None = None
    recap_path: Path | None = None
    recap_output_dir: Path | None = None
    reference_repository: ReferenceRepository | None = None


class SalesTargetsPipeline:
    """Construit les données d'entraînement et le jeu de test/évaluation pour l'IA.

    Stratégie (holdout strict — l'année ``evaluation_year`` n'entre jamais dans le fit) :
    1. **Entraînement** : moyenne mensuelle sur années < ``evaluation_year``
       par hôtel / mois / TYPE / GAMME + répartitions % (3 niveaux).
    2. **Test / évaluation** : agrégats réels de ``evaluation_year`` uniquement
       pour comparer ROD vs IA au terrain (jamais vus à l'entraînement).
    3. **Feature store** : persiste les targets d'entraînement par ``hotel_id``.
    """

    def __init__(
        self,
        sales_path: str | Path,
        identity_registry: HotelIdentityRegistry,
        output_dir: str | Path,
        feature_store: FeatureStoreRepository | None = None,
        evaluation_year: int = 2026,
        recap_path: str | Path | None = None,
        recap_output_dir: str | Path | None = None,
        reference_repository: ReferenceRepository | None = None,
    ) -> None:
        self.sales_path = Path(sales_path)
        self.identity_registry = identity_registry
        self.output_dir = Path(output_dir)
        self.feature_store = feature_store
        self.evaluation_year = evaluation_year
        self.recap_path = Path(recap_path) if recap_path else None
        self.recap_output_dir = Path(recap_output_dir) if recap_output_dir else None
        self.reference_repository = reference_repository
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._extractor = SalesMixExtractor(self.sales_path, self.identity_registry)
        self._recap_wide: pd.DataFrame | None = None
        self._recap_schema_path: Path | None = None

    def assert_training_holdout(self) -> None:
        """Vérifie que ``evaluation_year`` est exclue des données d'entraînement."""
        raw = self._extractor.prepare(exclude_year=self.evaluation_year)
        if raw.empty:
            return
        leaked = raw.loc[raw["year"] >= self.evaluation_year, "year"].unique()
        if len(leaked):
            raise ValueError(
                f"Fuite holdout : années {sorted(int(y) for y in leaked)} "
                f"présentes dans le jeu d'entraînement (evaluation_year={self.evaluation_year})."
            )

    def build_training_monthly_avg(self) -> pd.DataFrame:
        """Moyennes mensuelles d'entraînement (années < evaluation_year)."""
        self.assert_training_holdout()
        return self._extractor.monthly_average_targets(exclude_year=self.evaluation_year)

    def build_evaluation_actuals(self) -> pd.DataFrame:
        """CA et ventes réels par hôtel/mois sur l'année de test/évaluation (holdout)."""
        frame = self._extractor.prepare(exclude_year=None)
        frame = frame[frame["year"] == self.evaluation_year]
        if frame.empty:
            return pd.DataFrame(
                columns=["hotel_id", "month", "TYPE", "GAMME", "montant", "nbr_ventes"]
            )
        keys = ["hotel_id", "month", "TYPE", "GAMME"]
        return (
            frame.groupby(keys, dropna=False)
            .agg(
                montant=("montant", "sum"),
                nbr_ventes=("ticket_id", "nunique"),
            )
            .reset_index()
        )

    def evaluation_coverage_by_hotel(self) -> pd.DataFrame:
        """Couverture test/évaluation (ex. 2026) : mois présents et CA sur la période réelle.

        Jeu actuel : janvier–avril (mois 1–4) pour les hôtels pivots ayant des ventes
        sur ``evaluation_year``. Les années < ``evaluation_year`` servent
        uniquement à l'entraînement (``build_training_monthly_avg``).
        """
        actuals = self.build_evaluation_actuals()
        if actuals.empty:
            return pd.DataFrame(
                columns=[
                    "hotel_id",
                    "n_months_present",
                    "months_present",
                    "actual_ca_period",
                    "actual_ca_annualized",
                    "actual_ventes_period",
                ]
            )
        monthly = (
            actuals.groupby(["hotel_id", "month"], dropna=False)
            .agg(
                ca=("montant", "sum"),
                ventes=("nbr_ventes", "sum"),
            )
            .reset_index()
        )
        rows: list[dict] = []
        for hotel_id, grp in monthly.groupby("hotel_id"):
            n_months = int(grp["month"].nunique())
            months = sorted(int(m) for m in grp["month"].unique())
            ca_period = float(grp["ca"].sum())
            ventes_period = float(grp["ventes"].sum())
            rows.append(
                {
                    "hotel_id": str(hotel_id),
                    "n_months_present": n_months,
                    "months_present": months,
                    "actual_ca_period": ca_period,
                    "actual_ca_annualized": ca_period * 12.0 / n_months if n_months else 0.0,
                    "actual_ventes_period": ventes_period,
                    "actual_ca_mensuel_moyen_period": ca_period / n_months if n_months else 0.0,
                }
            )
        return pd.DataFrame(rows)

    def evaluation_annual_by_hotel(self) -> pd.DataFrame:
        """Alias — utilise la règle de 3 sur les mois effectivement présents."""
        coverage = self.evaluation_coverage_by_hotel()
        if coverage.empty:
            return pd.DataFrame(columns=["hotel_id", "actual_ca_annuel", "actual_ventes_annuel"])
        out = coverage.rename(
            columns={
                "actual_ca_period": "actual_ca_raw_period",
                "actual_ca_annualized": "actual_ca_annuel",
                "actual_ventes_period": "actual_ventes_raw_period",
            }
        )
        out["actual_ca_mensuel_moyen"] = out["actual_ca_mensuel_moyen_period"]
        return out

    def _global_monthly_targets(self, monthly_avg: pd.DataFrame) -> pd.DataFrame:
        """Targets globales mensuelles t_m{mm}_ca_total / t_m{mm}_ventes_total."""
        if monthly_avg.empty:
            return pd.DataFrame(columns=["hotel_id"])
        totals = (
            monthly_avg.groupby(["hotel_id", "month"], dropna=False)
            .agg(
                ca_total=("avg_montant", "sum"),
                ventes_total=("avg_nbr_ventes", "sum"),
            )
            .reset_index()
        )
        buckets: dict[str, dict[str, Any]] = {}
        for _, row in totals.iterrows():
            hotel_id = str(row["hotel_id"])
            month = int(row["month"])
            entry = buckets.setdefault(hotel_id, {"hotel_id": hotel_id})
            entry[MLColumnNaming.target(f"m{month:02d}_ca_total")] = float(row["ca_total"])
            entry[MLColumnNaming.target(f"m{month:02d}_ventes_total")] = float(row["ventes_total"])
        return pd.DataFrame(buckets.values()).fillna(0.0)

    def _granular_targets_wide(self, monthly_avg: pd.DataFrame) -> pd.DataFrame:
        buckets: dict[str, dict[str, Any]] = {}
        for _, row in monthly_avg.iterrows():
            hotel_id = str(row["hotel_id"])
            month = int(row["month"])
            type_label = str(row["TYPE"])
            gamme = str(row["GAMME"])
            entry = buckets.setdefault(hotel_id, {"hotel_id": hotel_id})
            entry[
                MLColumnNaming.target_month_type_gamme(month, type_label, gamme, "montant")
            ] = float(row["avg_montant"])
            entry[
                MLColumnNaming.target_month_type_gamme(month, type_label, gamme, "nbr_ventes")
            ] = float(row["avg_nbr_ventes"])
        if not buckets:
            return pd.DataFrame(columns=["hotel_id"])
        return pd.DataFrame(buckets.values()).fillna(0.0)

    def extract_recap_features(self) -> pd.DataFrame:
        """Extrait le récap ROD wide (``d_recap_*``) si le fichier est configuré."""
        if self._recap_wide is not None:
            return self._recap_wide
        if not self.recap_path or not self.recap_path.exists():
            self._recap_wide = pd.DataFrame(columns=["hotel_id"])
            return self._recap_wide

        out_dir = self.recap_output_dir or (self.output_dir / "rod_recap")
        out_stem = out_dir / "rod_recap"
        extractor = RodRecapExtractor(self.recap_path, self.identity_registry, out_stem)
        self._recap_wide = extractor.extract_wide()
        self._recap_schema_path = out_stem.with_suffix(".schema.json")
        return self._recap_wide

    def build_training_dataset(self) -> pd.DataFrame:
        """Dataset ML complet (entraînement uniquement) avec d_* et t_*."""
        self.assert_training_holdout()
        monthly_avg = self.build_training_monthly_avg()
        pct_service = SalesPercentageService(monthly_avg)
        pct_wide, pct_long = pct_service.compute_all()
        global_targets = self._global_monthly_targets(monthly_avg)
        granular_targets = self._granular_targets_wide(monthly_avg)

        dataset = global_targets
        for part in (granular_targets, pct_wide):
            if not part.empty:
                dataset = dataset.merge(part, on="hotel_id", how="outer")

        recap_wide = self.extract_recap_features()
        if not recap_wide.empty and len(recap_wide.columns) > 1:
            dataset = dataset.merge(recap_wide, on="hotel_id", how="left")

        dataset = self._attach_registry_descriptives(dataset)
        dataset = self._attach_info_columns(dataset)

        imputer = FeatureImputer(
            self.identity_registry,
            reference=self.reference_repository,
            schema_path=self._recap_schema_path,
        )
        dataset, imputation_report = imputer.impute(dataset, monthly_avg=monthly_avg)
        (self.output_dir / "imputation_report.json").write_text(
            json.dumps(imputation_report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        dataset = dataset.fillna(0.0)
        all_feature_cols = MLColumnNaming.feature_columns(dataset.columns)
        selector = FeatureSelector()
        dataset, feature_cols, selection_report = selector.select(dataset, all_feature_cols)
        selection_report.save(self.output_dir / "feature_selection_report.json")

        target_cols = MLColumnNaming.target_columns(dataset.columns)
        MLColumnNaming.assert_no_target_leakage(feature_cols)

        manifest = MLColumnNaming.build_manifest(dataset.columns, source="sales_targets_pipeline")
        (self.output_dir / "column_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        dataset.to_csv(self.output_dir / "ml_dataset_full.csv", index=False)
        dataset[feature_cols].to_csv(self.output_dir / "X_descriptive.csv", index=False)
        dataset[target_cols].to_csv(self.output_dir / "y_targets.csv", index=False)

        recap_feature_cols = [c for c in feature_cols if c.startswith("d_recap_")]
        meta = {
            "evaluation_year": self.evaluation_year,
            "train_years": f"< {self.evaluation_year}",
            "holdout_policy": "evaluation_year excluded from training targets and model fit",
            "n_rows": len(dataset),
            "n_features": len(feature_cols),
            "n_recap_features": len(recap_feature_cols),
            "n_targets": len(target_cols),
            "feature_cols": feature_cols,
            "target_cols": target_cols,
            "global_target_cols": [
                c for c in target_cols if "ca_total" in c or "ventes_total" in c
            ],
            "recap_source": str(self.recap_path) if self.recap_path else None,
            "imputation_count": imputation_report.to_dict()["count"],
            "features_removed_constant": selection_report.to_dict()["n_removed_constant"],
            "features_removed_duplicate": selection_report.to_dict()["n_removed_duplicate"],
        }
        (self.output_dir / "dataset_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (self.output_dir / "evaluation_actuals_annual.csv").write_text(
            self.evaluation_annual_by_hotel().to_csv(index=False), encoding="utf-8"
        )
        pct_long.to_csv(self.output_dir / "train_percentages_long.csv", index=False)
        monthly_avg.to_csv(self.output_dir / "train_monthly_avg_long.csv", index=False)
        return dataset

    def persist_hotel_targets(self) -> int:
        """Écrit les targets train dans le feature store de chaque hôtel pivot."""
        if not self.feature_store:
            return 0
        monthly_avg = self.build_training_monthly_avg()
        pct_service = SalesPercentageService(monthly_avg)
        _, pct_long = pct_service.compute_all()
        count = 0
        for hotel_id in monthly_avg["hotel_id"].unique():
            rows = monthly_avg[monthly_avg["hotel_id"] == hotel_id]
            pct_rows = pct_long[pct_long["hotel_id"] == hotel_id] if not pct_long.empty else pct_long
            self.feature_store.save_sales_targets(
                str(hotel_id),
                monthly_avg=rows.to_dict(orient="records"),
                monthly_pct=pct_rows.to_dict(orient="records") if not pct_rows.empty else [],
            )
            count += 1
        return count

    def _attach_registry_descriptives(self, dataset: pd.DataFrame) -> pd.DataFrame:
        """Injecte ``d_nb_chambres`` depuis le registre identité (avant imputation)."""
        rows: list[dict] = []
        for hotel_id in dataset["hotel_id"].unique():
            record = self.identity_registry.get(str(hotel_id))
            if not record:
                continue
            rows.append(
                {
                    "hotel_id": hotel_id,
                    MLColumnNaming.descriptive("nb_chambres"): float(record.nb_chambres or 0),
                }
            )
        if not rows:
            return dataset
        registry_df = pd.DataFrame(rows)
        if MLColumnNaming.descriptive("nb_chambres") in dataset.columns:
            dataset = dataset.drop(columns=[MLColumnNaming.descriptive("nb_chambres")])
        return dataset.merge(registry_df, on="hotel_id", how="left")

    def _attach_info_columns(self, dataset: pd.DataFrame) -> pd.DataFrame:
        info_rows = []
        for hotel_id in dataset["hotel_id"].unique():
            record = self.identity_registry.get(str(hotel_id))
            if not record:
                continue
            info_rows.append(
                {
                    "hotel_id": hotel_id,
                    "name_display": record.name_display,
                    "name_ventes": record.name_ventes,
                    "name_rod": record.name_rod,
                    "city": record.city,
                    "brand": record.brand,
                    "lat": record.lat_canonical,
                    "lon": record.lon_canonical,
                    "geo_source": record.geo_source,
                }
            )
        if not info_rows:
            return dataset
        return dataset.merge(pd.DataFrame(info_rows), on="hotel_id", how="left")