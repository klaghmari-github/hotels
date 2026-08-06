"""
Orchestrateur multi-concepts.

Enchaînement pour POST /api/simulate :
  1. prepare_request — hydrate depuis hotel_data / model_data si code connu
  2. enrichissement optionnel des features manquantes
  3. simulation SIMPLY / LIBERTY / CONNECTED (RodSimulator)
  4. RecommendationRules — filtre + meilleure marge nette

Retourne un FullSimulation (détail par concept + reco + warnings).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from archive.accor_1_0_6.pipelines.src.accor.user.models import (
    ClientProfile,
    FullSimulation,
    HotelOperating,
    SimulationRequest,
    StoreConfig,
)
from archive.accor_1_0_6.pipelines.src.accor.user.reference import RodReference
from archive.accor_1_0_6.pipelines.src.accor.user.rules.costs import CostRules
from archive.accor_1_0_6.pipelines.src.accor.user.rules.recommendation import RecommendationRules
from archive.accor_1_0_6.pipelines.src.accor.user.rules.revenue import RevenueRules
from archive.accor_1_0_6.pipelines.src.accor.user.services.enrich import FeatureEnricher
from archive.accor_1_0_6.pipelines.src.accor.user.services.hotel_context import HotelContextBuilder
from archive.accor_1_0_6.pipelines.src.accor.user.services.simulator import RodSimulator


class SimulationOrchestrator:
    """Compare SIMPLY / LIBERTY / CONNECTED (règles ROD) et recommande."""

    CONCEPTS = ("SIMPLY", "LIBERTY", "CONNECTED")

    def __init__(
        self,
        reference: RodReference | None = None,
        enricher: FeatureEnricher | None = None,
        *,
        auto_enrich: bool = True,
    ) -> None:
        self.reference = reference or RodReference()
        self.enricher = enricher or FeatureEnricher()
        self.context_builder = HotelContextBuilder()
        self.auto_enrich = auto_enrich
        self.revenue = RevenueRules(self.reference)
        self.costs = CostRules(self.reference)
        self.reco = RecommendationRules()
        self.simulator = RodSimulator(self.revenue, self.costs)

    def prepare_request(
        self,
        request: SimulationRequest,
        *,
        hydrate_from_admin: bool = True,
    ) -> tuple[SimulationRequest, dict[str, Any]]:
        """
        Impute / complète les indicateurs manquants.

        Si un ``hotel_code`` est fourni et que des champs d'exploitation
        manquent, charge le contexte admin (hotel_data + model_data).
        """
        prepared = deepcopy(request)
        meta: dict[str, Any] = {"indicators": {}, "sources": {}, "warnings": []}

        code = (prepared.identity.hotel_code or "").strip()
        needs_hydrate = (
            hydrate_from_admin
            and code
            and (
                prepared.operating.nb_chambres <= 0
                or prepared.operating.taux_occupation <= 0
                or prepared.corner.m_lin is None
                or prepared.corner.mix_fb is None
            )
        )

        if hydrate_from_admin and code:
            try:
                ctx = self.context_builder.build(code)
                meta["indicators"] = ctx.indicators
                meta["sources"] = ctx.sources
                meta["warnings"] = list(ctx.warnings)

                # Identité : complète les trous uniquement
                for field in (
                    "hotel_name",
                    "hotel_brand",
                    "hotel_lat",
                    "hotel_lon",
                    "hotel_adresse_postale_1",
                    "hotel_adresse_postale_2",
                    "hotel_code_postal",
                    "hotel_city",
                ):
                    cur = getattr(prepared.identity, field, None)
                    if cur in (None, "") and ctx.identity.get(field) not in (None, ""):
                        setattr(prepared.identity, field, ctx.identity[field])

                # Operating : priorise saisie user si déjà renseignée
                if prepared.operating.nb_chambres <= 0:
                    prepared.operating = HotelOperating(
                        nb_chambres=int(ctx.operating["nb_chambres"]),
                        taux_occupation=float(ctx.operating["taux_occupation"]),
                        guests_per_chambre=float(ctx.operating["guests_per_chambre"]),
                    )
                else:
                    # force guests brand si défaut générique 1.7 et contexte dispo
                    if prepared.operating.guests_per_chambre <= 0:
                        prepared.operating.guests_per_chambre = float(
                            ctx.operating["guests_per_chambre"]
                        )
                    if prepared.operating.taux_occupation <= 0:
                        prepared.operating.taux_occupation = float(
                            ctx.operating["taux_occupation"]
                        )

                if prepared.corner.m_lin is None and ctx.corner.get("m_lin") is not None:
                    prepared.corner.m_lin = float(ctx.corner["m_lin"])
                if prepared.corner.mix_fb is None and ctx.corner.get("mix_fb") is not None:
                    prepared.corner.mix_fb = float(ctx.corner["mix_fb"])
                if not prepared.corner.has_corner and ctx.corner.get("has_corner"):
                    prepared.corner.has_corner = True

                # Besoins clients : si tous True (défaut non touché) et model_data dispo
                ctx_needs = (ctx.client_profile or {}).get("client_needs") or {}
                if ctx_needs:
                    user_needs = prepared.client_profile.client_needs or {}
                    # remplace seulement si user n'a pas customisé (toutes valeurs défaut)
                    from archive.accor_1_0_6.pipelines.src.accor.user.models import DEFAULT_CLIENT_NEEDS

                    if not user_needs or user_needs == DEFAULT_CLIENT_NEEDS:
                        prepared.client_profile = ClientProfile(
                            loisirs_pct=float(
                                ctx.client_profile.get("loisirs_pct", 0.3)
                            ),
                            affaires_pct=float(
                                ctx.client_profile.get("affaires_pct", 0.7)
                            ),
                            national_pct=float(
                                ctx.client_profile.get("national_pct", 0.6)
                            ),
                            international_pct=float(
                                ctx.client_profile.get(
                                    "international_pct", 0.4
                                )
                            ),
                            client_needs=dict(ctx_needs),
                        )
            except Exception as exc:  # noqa: BLE001
                meta["warnings"].append(f"Hydratation admin impossible : {exc}")

        # Garde-fous finaux (évite CA = 0 par données vides)
        if prepared.operating.nb_chambres <= 0:
            prepared.operating.nb_chambres = 80
            meta["warnings"].append("nb_chambres imputé à 80 (garde-fou).")
        if prepared.operating.taux_occupation <= 0:
            prepared.operating.taux_occupation = 0.70
            meta["warnings"].append("TO imputé à 70 % (garde-fou).")
        if prepared.operating.guests_per_chambre <= 0:
            prepared.operating.guests_per_chambre = 1.7

        meta["indicators"] = {
            **meta.get("indicators", {}),
            "nb_chambres": prepared.operating.nb_chambres,
            "taux_occupation": prepared.operating.taux_occupation,
            "guests_per_chambre": prepared.operating.guests_per_chambre,
            "clients_jour": prepared.operating.clients_jour,
            "clients_mois": prepared.operating.clients_mois,
        }
        return prepared, meta

    def build_store(self, request: SimulationRequest, concept: str) -> StoreConfig:
        """Configuration store proposée pour un concept (sortie du moteur)."""
        concept = concept.upper()
        key = f"concepts.{concept}"
        default_fb = float(self.reference.get(f"{key}.mix_fb", 0.7) or 0.7)
        default_nf = float(self.reference.get(f"{key}.mix_nf", 0.3) or 0.3)
        default_m = float(self.reference.get(f"{key}.pivot_m_lin", 6) or 6)

        m_lin = request.corner.m_lin if request.corner.m_lin is not None else default_m
        # m_lin = 0 invalide → pilote
        if m_lin is None or float(m_lin) <= 0:
            m_lin = default_m

        if request.corner.mix_fb is not None:
            fb = float(request.corner.mix_fb)
            if fb > 1.0:
                fb = fb / 100.0
            fb = min(max(fb, 0.0), 1.0)
            nf = 1.0 - fb
        else:
            fb, nf = default_fb, default_nf

        return StoreConfig(
            concept=concept, m_lin=float(m_lin), mix_fb=float(fb), mix_nf=float(nf)
        )

    def request_for_concept(
        self, request: SimulationRequest, concept: str
    ) -> SimulationRequest:
        candidate = deepcopy(request)
        candidate.store = self.build_store(request, concept)
        return candidate

    def simulate_all(
        self,
        request: SimulationRequest,
        *,
        enrich: bool | None = None,
        light_enrich: bool = False,
        hydrate_from_admin: bool = True,
    ) -> FullSimulation:
        """
        Parameters
        ----------
        enrich :
            Force enrichissement (défaut = ``self.auto_enrich``).
        light_enrich :
            Si True, skip Overpass/Meteostat lents (holidays + géocode seulement).
        hydrate_from_admin :
            Complète depuis hotel_data + model_data si hotel_code fourni.
        """
        request, prep_meta = self.prepare_request(
            request, hydrate_from_admin=hydrate_from_admin
        )

        do_enrich = self.auto_enrich if enrich is None else enrich
        if do_enrich:
            request = self.enricher.enrich(
                request,
                do_proximity=not light_enrich,
                do_weather=not light_enrich,
                do_holidays=True,
            )

        allowed, reco_warnings = self.reco.allowed_concepts(request)
        warnings = (
            list(prep_meta.get("warnings") or [])
            + list(reco_warnings)
            + list(request.enriched.warnings or [])
        )

        by_concept = {}
        for concept in self.CONCEPTS:
            req = self.request_for_concept(request, concept)
            by_concept[concept] = self.simulator.simulate(req, concept)

        recommended, best_margin, reason = self.reco.recommend(
            by_concept, allowed, request=request
        )

        enriched = request.enriched.to_dict()
        enriched["indicators"] = prep_meta.get("indicators") or {}
        enriched["sources"] = prep_meta.get("sources") or {}
        enriched["operating"] = request.operating.to_dict()
        enriched["identity"] = request.identity.to_dict()

        return FullSimulation(
            by_concept=by_concept,
            recommended_concept=recommended,
            best_margin_concept=best_margin,
            recommendation_reason=reason,
            allowed_concepts=allowed,
            warnings=warnings,
            enriched=enriched,
        )
