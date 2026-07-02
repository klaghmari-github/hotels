"""Évaluation ROD vs IA — période réelle 2026 + règle de 3."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from rod_ia.domain.models.hotel import HotelIdentity, HotelOperatingState
from rod_ia.domain.models.simulation import (
    PerformanceComparisonRow,
    PerformanceReport,
    RodSimulationRequest,
)
from rod_ia.domain.repositories.feature_store_repository import FeatureStoreRepository
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.services.sales_targets_pipeline import SalesTargetsPipeline
from rod_ia.domain.services.simulation_orchestrator import SimulationOrchestrator


class ModelEvaluationService:
    """Compare ROD et IA au CA réel sur les mois présents en validation."""

    def __init__(
        self,
        sales_pipeline: SalesTargetsPipeline,
        orchestrator: SimulationOrchestrator,
        identity_registry: HotelIdentityRegistry,
        reference: ReferenceRepository,
        feature_store: FeatureStoreRepository | None = None,
        output_path: Path | None = None,
        validation_year: int = 2026,
    ) -> None:
        self._pipeline = sales_pipeline
        self._orchestrator = orchestrator
        self._registry = identity_registry
        self._reference = reference
        self._feature_store = feature_store
        self._output_path = Path(output_path) if output_path else None
        self._validation_year = validation_year

    @staticmethod
    def _error_pct(predicted: float, actual: float) -> float:
        if actual == 0:
            return 0.0 if predicted == 0 else 100.0
        return (predicted - actual) / actual * 100.0

    def _operating_for_hotel(self, hotel_id: str, concept: str, nb_chambres: int) -> HotelOperatingState:
        """Paramètres hôtel : feature store > registre > pilote concept."""
        key = f"concepts.{concept}"
        guests = float(self._reference.get(f"{key}.pivot_guests_per_chambre", 1.7) or 1.7)
        to = float(self._reference.get(f"{key}.pivot_to", 0.75) or 0.75)

        if self._feature_store:
            saved = self._feature_store.load_director_inputs(hotel_id)
            if saved:
                op = saved.get("operating") or saved
                if op.get("taux_occupation") is not None:
                    to = float(op["taux_occupation"])
                if op.get("guests_per_chambre") is not None:
                    guests = float(op["guests_per_chambre"])
                if op.get("nb_chambres") is not None:
                    nb_chambres = int(op["nb_chambres"])

        return HotelOperatingState(nb_chambres=nb_chambres, taux_occupation=to, guests_per_chambre=guests)

    @staticmethod
    def _ca_period_from_monthly(monthly: list, months_present: list[int], mensuel_moyen: float) -> float:
        if not months_present:
            return 0.0
        by_month = {m.month: m.ca for m in monthly}
        if any(by_month.get(m, 0) > 0 for m in months_present):
            return sum(by_month.get(m, mensuel_moyen) for m in months_present)
        return mensuel_moyen * len(months_present)

    def evaluate(self) -> PerformanceReport:
        coverage = self._pipeline.validation_coverage_by_hotel()
        warnings: list[str] = []
        rows: list[PerformanceComparisonRow] = []

        if coverage.empty:
            warnings.append(f"Aucune vente {self._validation_year} — comparaison impossible.")
            return PerformanceReport(
                self._validation_year, rows, {}, warnings, "period_with_rule_of_three"
            )

        warnings.append(
            f"Comparaison sur les mois présents en {self._validation_year} "
            "(prédictions ramenées à la période, réel annualisé par règle de 3)."
        )

        for _, cov in coverage.iterrows():
            hotel_id = str(cov["hotel_id"])
            record = self._registry.get(hotel_id)
            if not record or not record.has_rod:
                continue

            nb_ch = int(record.nb_chambres or 100)
            request = RodSimulationRequest(
                identity=HotelIdentity(
                    hotel_id=hotel_id,
                    hotel_name=record.name_display,
                    city=record.city,
                    brand=record.brand,
                ),
                operating=self._operating_for_hotel(hotel_id, "SIMPLY", nb_ch),
            )
            full = self._orchestrator.simulate_all(request)
            concept = full.recommended_concept
            request.operating = self._operating_for_hotel(hotel_id, concept, nb_ch)
            full = self._orchestrator.simulate_all(request)

            rod = full.rod_by_concept.get(concept)
            ai = full.ai_by_concept.get(concept)
            if not rod or not ai:
                continue

            months = list(cov["months_present"])
            n_months = int(cov["n_months_present"])
            actual_period = float(cov["actual_ca_period"])
            actual_annualized = float(cov["actual_ca_annualized"])

            rod_period = float(rod.ca_mensuel_moyen) * n_months
            ai_period = self._ca_period_from_monthly(
                ai.monthly, months, float(ai.ca_mensuel_moyen)
            )
            rod_annualized = float(rod.ca_mensuel_moyen) * 12.0
            ai_annualized = float(ai.ca_annuel)

            rows.append(
                PerformanceComparisonRow(
                    hotel_id=hotel_id,
                    hotel_name=record.name_display,
                    brand=record.brand,
                    concept=concept,
                    validation_year=self._validation_year,
                    n_months_present=n_months,
                    months_present=months,
                    nb_chambres=nb_ch,
                    taux_occupation=float(request.operating.taux_occupation),
                    guests_per_chambre=float(request.operating.guests_per_chambre),
                    actual_ca_period=actual_period,
                    actual_ca_annualized=actual_annualized,
                    rod_ca_period=rod_period,
                    ai_ca_period=ai_period,
                    rod_ca_annualized=rod_annualized,
                    ai_ca_annualized=ai_annualized,
                    rod_error_pct=self._error_pct(rod_period, actual_period),
                    ai_error_pct=self._error_pct(ai_period, actual_period),
                    rod_ca_mensuel_moyen=float(rod.ca_mensuel_moyen),
                    ai_ca_mensuel_moyen=float(ai.ca_mensuel_moyen),
                    actual_ca_mensuel_moyen=float(cov["actual_ca_mensuel_moyen_period"]),
                )
            )

        summary = {}
        if rows:
            df = pd.DataFrame([r.to_dict() for r in rows])
            summary = {
                "n_hotels": len(rows),
                "mean_months_present": float(df["n_months_present"].mean()),
                "mean_abs_rod_error_pct": float(df["rod_error_pct"].abs().mean()),
                "mean_abs_ai_error_pct": float(df["ai_error_pct"].abs().mean()),
                "ai_better_count": int(
                    (df["ai_error_pct"].abs() < df["rod_error_pct"].abs()).sum()
                ),
            }

        report = PerformanceReport(
            self._validation_year, rows, summary, warnings, "period_with_rule_of_three"
        )
        if self._output_path:
            self._output_path.parent.mkdir(parents=True, exist_ok=True)
            import json

            self._output_path.write_text(
                json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return report