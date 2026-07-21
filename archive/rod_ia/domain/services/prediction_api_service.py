"""API REST — enrichissement feature store + simulation + prédiction par concept."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from rod_ia.domain.models.prediction_api import (
    ConceptPrediction,
    MonthlyPrediction,
    PredictionApiResponse,
)
from rod_ia.domain.models.simulation import RodSimulationRequest, SimulationResult
from rod_ia.domain.repositories.feature_store_repository import FeatureStoreRepository
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.services.enrich_hotel import EnrichHotelService
from rod_ia.domain.services.simulation_orchestrator import SimulationOrchestrator


class PredictionApiService:
    """Reçoit les saisies directeur, enrichit via le feature store, simule et prédit."""

    CONCEPTS = ("SIMPLY", "LIBERTY", "CONNECTED")

    def __init__(
        self,
        enrich_service: EnrichHotelService,
        feature_store: FeatureStoreRepository,
        identity_registry: HotelIdentityRegistry,
        reference: ReferenceRepository,
        orchestrator: SimulationOrchestrator,
    ) -> None:
        self._enrich = enrich_service
        self._feature_store = feature_store
        self._identity = identity_registry
        self._reference = reference
        self._orchestrator = orchestrator

    def predict(self, payload: dict) -> PredictionApiResponse:
        original = deepcopy(payload or {})
        request = RodSimulationRequest.from_dict(original)
        request.analyze_with_ai = True

        identity = request.identity
        enrich_result = self._enrich.enrich(
            hotel_name=identity.hotel_name or "",
            address=identity.address or "",
            city=identity.city or "",
            force_refresh=bool(original.get("force_refresh", False)),
            hotel_id=identity.hotel_id,
        )

        hotel_id = enrich_result.hotel_id
        request.identity.hotel_id = hotel_id
        request.enriched = enrich_result.features

        self._feature_store.save_director_inputs(hotel_id, original)
        recap_features = self._feature_store.load_recap_features(hotel_id)
        meta = self._feature_store.load_meta(hotel_id) or {}

        full = self._orchestrator.simulate_all(request)
        warnings = list(enrich_result.warnings) + list(full.warnings)

        input_echo = self._build_input_echo(original, request, hotel_id)
        context = self._build_context(
            hotel_id=hotel_id,
            enrich_source=enrich_result.source,
            enriched=request.enriched,
            recap_features=recap_features,
            meta=meta,
        )
        predictions = {
            concept: self._concept_prediction(full.ai_by_concept[concept])
            for concept in self.CONCEPTS
        }
        recommendation = {
            "concept": full.recommended_concept,
            "best_margin_concept": full.best_margin_concept,
            "reason": full.recommendation_reason,
        }

        return PredictionApiResponse(
            input=input_echo,
            context=context,
            predictions=predictions,
            recommendation=recommendation,
            warnings=warnings,
        )

    def _build_input_echo(
        self, original: dict, request: RodSimulationRequest, hotel_id: str
    ) -> dict:
        echo = deepcopy(original)
        echo.setdefault("identity", {})
        echo["identity"]["hotel_id"] = hotel_id
        echo["identity"].setdefault("hotel_name", request.identity.hotel_name)
        echo["identity"].setdefault("city", request.identity.city)
        echo["identity"].setdefault("brand", request.identity.brand)
        echo["enriched"] = request.enriched.to_dict()
        echo["analyze_with_ai"] = True
        return echo

    def _build_context(
        self,
        *,
        hotel_id: str,
        enrich_source: str,
        enriched,
        recap_features: dict[str, float],
        meta: dict,
    ) -> dict:
        poi = enriched.poi or {}
        nearest = enriched.nearest or {}
        beach_km = nearest.get("d_nearest_beach_km") or nearest.get("nearest_beach_km")

        return {
            "hotel_id": hotel_id,
            "enrichment_source": enrich_source,
            "registry_hotels_count": len(self._identity.all_records()),
            "proximity": {
                "beach_km": beach_km,
                "commerce_fb": {
                    "at_100m": poi.get("d_poi_fb_0_0_1km", 0.0),
                    "at_500m": poi.get("d_poi_fb_0_0_5km", 0.0),
                },
                "commerce_non_fb": {
                    "at_100m": poi.get("d_poi_not_fb_0_0_1km", 0.0),
                    "at_500m": poi.get("d_poi_not_fb_0_0_5km", 0.0),
                },
                "nearest_m": {
                    k.replace("d_nearest_", "").replace("_m", ""): v
                    for k, v in nearest.items()
                    if k.endswith("_m") and not k.endswith("_km")
                },
            },
            "weather": {
                "monthly_features_loaded": bool(enriched.weather_monthly),
                "feature_count": len(enriched.weather_monthly or {}),
            },
            "feature_store": {
                "meta": meta,
                "recap_features_count": len(recap_features),
            },
            "rod_rules": self._rod_rules_summary(),
        }

    def _rod_rules_summary(self) -> dict[str, Any]:
        concepts: dict[str, Any] = {}
        for concept in self.CONCEPTS:
            key = f"concepts.{concept}"
            concepts[concept] = {
                "pivot_nb_chambres": self._reference.get(f"{key}.pivot_nb_chambres"),
                "pivot_to": self._reference.get(f"{key}.pivot_to"),
                "pivot_m_lin": self._reference.get(f"{key}.pivot_m_lin"),
                "mix_fb": self._reference.get(f"{key}.mix_fb"),
                "mix_nf": self._reference.get(f"{key}.mix_nf"),
                "monthly_cost_total": self._reference.get(f"{key}.monthly_cost_total"),
                "margin_fb_pct": self._reference.get(f"{key}.margin_fb_pct"),
                "margin_nf_pct": self._reference.get(f"{key}.margin_nf_pct"),
            }
        return {
            "source": self._reference.reference_path.name if self._reference.reference_path else None,
            "impact_to": self._reference.get("impact_to"),
            "concepts": concepts,
        }

    @staticmethod
    def _concept_prediction(result: SimulationResult) -> ConceptPrediction:
        monthly = [
            MonthlyPrediction(
                month=m.month,
                ca=m.ca,
                nbr_ventes=m.nbr_ventes,
                marge_nette=m.marge_nette,
                cout=m.cost,
                marge_produit=m.marge_produit,
            )
            for m in result.monthly
        ]
        return ConceptPrediction(
            concept=result.concept,
            source=result.source,
            ca_annuel=result.ca_annuel,
            nbr_ventes_annuel=result.nbr_ventes_annuel,
            marge_annuelle=result.marge_annuelle,
            cout_annuel=result.cout_annuel,
            ca_mensuel_moyen=result.ca_mensuel_moyen,
            nbr_ventes_mensuel_moyen=result.nbr_ventes_mensuel_moyen,
            roi_months=result.roi_months,
            monthly=monthly,
            costs_breakdown=dict(result.breakdown),
        )