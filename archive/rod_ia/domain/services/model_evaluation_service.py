"""Évaluation ROD vs IA — période réelle 2026 + règle de 3."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from rod_ia.domain.models.director_inputs import HotelGeneralInfo
from rod_ia.domain.models.hotel import HotelIdentity, HotelOperatingState
from rod_ia.domain.models.identity import HotelRecord
from rod_ia.domain.models.simulation import (
    PerformanceComparisonRow,
    PerformanceReport,
    RodSimulationRequest,
    SimulationResult,
)
from rod_ia.domain.repositories.feature_store_repository import FeatureStoreRepository
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.rules.excel_category_coeffs import BRAND_TO_CODE
from rod_ia.domain.services.feature_imputer import BRAND_GUESTS_DEFAULT, BRAND_TO_DEFAULT
from rod_ia.domain.services.sales_targets_pipeline import SalesTargetsPipeline
from rod_ia.domain.services.simulation_orchestrator import SimulationOrchestrator


class ModelEvaluationService:
    """Compare ROD et IA au CA réel sur le jeu de test/évaluation (holdout)."""

    VALIDATION_MONTHS_2026 = (1, 2, 3, 4)

    def __init__(
        self,
        sales_pipeline: SalesTargetsPipeline,
        orchestrator: SimulationOrchestrator,
        identity_registry: HotelIdentityRegistry,
        reference: ReferenceRepository,
        feature_store: FeatureStoreRepository | None = None,
        output_path: Path | None = None,
        evaluation_year: int = 2026,
    ) -> None:
        self._pipeline = sales_pipeline
        self._orchestrator = orchestrator
        self._registry = identity_registry
        self._reference = reference
        self._feature_store = feature_store
        self._output_path = Path(output_path) if output_path else None
        self._evaluation_year = evaluation_year

    @staticmethod
    def _error_pct(predicted: float, actual: float) -> float:
        if actual == 0:
            return 0.0 if predicted == 0 else 100.0
        return (predicted - actual) / actual * 100.0

    @staticmethod
    def _brand_key(record: HotelRecord) -> str:
        return (record.brand or "").upper().replace("_", " ").strip()

    @staticmethod
    def _period_label(months: list[int], year: int) -> str:
        if months == list(ModelEvaluationService.VALIDATION_MONTHS_2026):
            return f"janvier–avril {year} (4 mois)"
        if len(months) == 1:
            return f"mois {months[0]} {year}"
        return f"{len(months)} mois en {year} (mois {months})"

    @staticmethod
    def _normalize_to_rate(value: float) -> float:
        val = float(value)
        return val / 100.0 if val > 1.0 else val

    @staticmethod
    def _to_from_recap(recap: dict[str, float]) -> float | None:
        """TO recap : ``to_annuel`` (paramètre simulateur ROD), sinon moyenne haut/bas."""
        annuel: float | None = None
        haut: float | None = None
        bas: float | None = None

        for key, value in recap.items():
            lower = key.lower()
            if "to_le_plus_bas_mois" in lower:
                continue
            try:
                val = float(value)
            except (TypeError, ValueError):
                continue
            if not 0 < val <= 100:
                continue
            if "to_annuel" in lower:
                annuel = val
            elif "to_le_plus_haut_taux" in lower:
                haut = val
            elif "to_le_plus_bas_taux" in lower:
                bas = val

        if annuel is not None:
            return ModelEvaluationService._normalize_to_rate(annuel)
        if haut is not None and bas is not None:
            return ModelEvaluationService._normalize_to_rate((haut + bas) / 2.0)
        if haut is not None:
            return ModelEvaluationService._normalize_to_rate(haut)
        if bas is not None:
            return ModelEvaluationService._normalize_to_rate(bas)
        return None

    @staticmethod
    def _guests_from_recap(recap: dict[str, float]) -> float | None:
        for key, value in recap.items():
            lower = key.lower()
            if "guests" in lower and "chambre" in lower:
                return float(value)
        return None

    def _operating_for_hotel(
        self, hotel_id: str, record: HotelRecord, nb_chambres: int
    ) -> HotelOperatingState:
        """Paramètres hôtel : director_inputs > récap ROD > défauts marque > pilote SIMPLY."""
        brand = self._brand_key(record)
        to = BRAND_TO_DEFAULT.get(brand, 0.75)
        guests = BRAND_GUESTS_DEFAULT.get(brand, 1.7)

        if self._feature_store:
            recap = self._feature_store.load_recap_features(hotel_id)
            recap_to = self._to_from_recap(recap)
            if recap_to is not None:
                to = recap_to

            saved = self._feature_store.load_director_inputs(hotel_id)
            if saved:
                op = saved.get("operating") or saved
                if op.get("taux_occupation") is not None:
                    to = float(op["taux_occupation"])
                if op.get("guests_per_chambre") is not None:
                    guests = float(op["guests_per_chambre"])
                if op.get("nb_chambres") is not None:
                    nb_chambres = int(op["nb_chambres"])
            elif brand not in BRAND_GUESTS_DEFAULT:
                recap_guests = self._guests_from_recap(recap)
                if recap_guests is not None:
                    guests = recap_guests

        return HotelOperatingState(
            nb_chambres=nb_chambres,
            taux_occupation=to,
            guests_per_chambre=guests,
        )

    @staticmethod
    def _ca_period_from_monthly(monthly: list, months_present: list[int], mensuel_moyen: float) -> float:
        if not months_present:
            return 0.0
        by_month = {m.month: m.ca for m in monthly}
        if any(by_month.get(m, 0) > 0 for m in months_present):
            return sum(by_month.get(m, mensuel_moyen) for m in months_present)
        return mensuel_moyen * len(months_present)

    @staticmethod
    def _candidate_concepts(record: HotelRecord, nb_chambres: int) -> list[str]:
        """Restreint le best-fit aux concepts plausibles selon marque et taille."""
        code = BRAND_TO_CODE.get(ModelEvaluationService._brand_key(record), "")
        if code == "IBB":
            return ["SIMPLY", "LIBERTY"]
        if nb_chambres >= 500:
            return ["CONNECTED", "LIBERTY"]
        if nb_chambres >= 150:
            return ["LIBERTY", "CONNECTED", "SIMPLY"]
        return ["SIMPLY", "LIBERTY", "CONNECTED"]

    @staticmethod
    def _select_best_fit_concept(
        rod_by_concept: dict[str, SimulationResult],
        actual_period: float,
        n_months: int,
        candidates: list[str] | None = None,
    ) -> str:
        """Concept dont le CA ROD sur la période est le plus proche du réel."""
        pool = candidates or list(rod_by_concept.keys())
        best_concept = pool[0]
        best_abs_err = float("inf")
        for concept in pool:
            rod = rod_by_concept.get(concept)
            if not rod:
                continue
            rod_period = float(rod.ca_mensuel_moyen) * n_months
            abs_err = abs(rod_period - actual_period)
            if abs_err < best_abs_err:
                best_abs_err = abs_err
                best_concept = concept
        return best_concept

    def evaluate(self) -> PerformanceReport:
        coverage = self._pipeline.evaluation_coverage_by_hotel()
        warnings: list[str] = []
        rows: list[PerformanceComparisonRow] = []

        if coverage.empty:
            warnings.append(
                f"Aucune vente {self._evaluation_year} (test/évaluation) — comparaison impossible."
            )
            return PerformanceReport(
                self._evaluation_year, rows, {}, warnings, "period_with_rule_of_three"
            )

        sample_months = sorted(
            {
                int(m)
                for _, cov in coverage.iterrows()
                for m in cov.get("months_present") or []
            }
        )
        period = self._period_label(sample_months, self._evaluation_year)
        warnings.append(
            f"Test/évaluation {self._evaluation_year} : comparaison sur {period} "
            "(holdout — jamais vu à l'entraînement ; réel annualisé par règle de 3)."
        )
        warnings.append(
            "Concept retenu pour ROD : meilleur ajustement CA sur la période "
            "(best-fit), pas uniquement la recommandation marge."
        )

        for _, cov in coverage.iterrows():
            hotel_id = str(cov["hotel_id"])
            record = self._registry.get(hotel_id)
            if not record or not record.has_rod:
                continue

            nb_ch = int(record.nb_chambres or 100)
            operating = self._operating_for_hotel(hotel_id, record, nb_ch)
            request = RodSimulationRequest(
                identity=HotelIdentity(
                    hotel_id=hotel_id,
                    hotel_name=record.name_display,
                    city=record.city,
                    brand=record.brand,
                ),
                operating=operating,
                general=HotelGeneralInfo(
                    adults_per_room=operating.guests_per_chambre,
                    children_per_room=0.0,
                ),
            )
            full = self._orchestrator.simulate_all(request)

            n_months = int(cov["n_months_present"])
            actual_period = float(cov["actual_ca_period"])
            candidates = self._candidate_concepts(record, nb_ch)
            concept = self._select_best_fit_concept(
                full.rod_by_concept, actual_period, n_months, candidates
            )
            recommended = full.recommended_concept

            rod = full.rod_by_concept.get(concept)
            ai = full.ai_by_concept.get(concept)
            if not rod or not ai:
                continue

            months = list(cov["months_present"])
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
                    evaluation_year=self._evaluation_year,
                    n_months_present=n_months,
                    months_present=months,
                    nb_chambres=nb_ch,
                    taux_occupation=float(operating.taux_occupation),
                    guests_per_chambre=float(operating.guests_per_chambre),
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
                    recommended_concept=recommended,
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
            self._evaluation_year, rows, summary, warnings, "period_with_rule_of_three"
        )
        if self._output_path:
            self._output_path.parent.mkdir(parents=True, exist_ok=True)
            import json

            self._output_path.write_text(
                json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return report