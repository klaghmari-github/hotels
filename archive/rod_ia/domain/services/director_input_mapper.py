"""Applique les saisies directeur sur la configuration store / contraintes."""

from __future__ import annotations

from copy import deepcopy

from rod_ia.domain.models.director_inputs import (
    excluded_gammes_from_needs,
    mix_from_client_needs,
)
from rod_ia.domain.models.simulation import RodSimulationRequest
from rod_ia.domain.models.store import CategoryMix, StoreConfiguration


class DirectorInputMapper:
    """Fusionne wizard directeur + références concept pour la simulation."""

    @staticmethod
    def apply_store_overrides(
        request: RodSimulationRequest,
        *,
        default_fb: float,
        default_nf: float,
        default_m_lin: float,
        concept: str,
    ) -> StoreConfiguration:
        """Construit la config store en tenant compte des saisies utilisateur."""
        excluded = list(request.constraints.get("excluded_categories") or [])
        locked = list(request.constraints.get("locked_fields") or [])

        needs = request.client_profile.client_needs
        excluded_from_needs = excluded_gammes_from_needs(needs)
        for gamme in excluded_from_needs:
            if gamme not in excluded:
                excluded.append(gamme)

        fb_share, nf_share = default_fb, default_nf
        if excluded_from_needs:
            fb_share, nf_share = mix_from_client_needs(
                needs, default_fb=default_fb, default_nf=default_nf
            )

        subcategory_shares: dict[str, float] = {}
        if request.store and request.store.mix.subcategory_shares:
            subcategory_shares = dict(request.store.mix.subcategory_shares)

        if request.store:
            if request.store.mix.fb_share is not None:
                fb_share = float(request.store.mix.fb_share)
                nf_share = float(request.store.mix.non_fb_share)
            if request.store.excluded_categories:
                excluded = list(request.store.excluded_categories)
            if request.store.locked_fields:
                locked = list(request.store.locked_fields)
            if request.store.mix.subcategory_shares:
                subcategory_shares = dict(request.store.mix.subcategory_shares)

        m_lin = default_m_lin
        if request.store and request.store.m_lin:
            m_lin = float(request.store.m_lin)
        elif request.corner.m_lin is not None:
            m_lin = float(request.corner.m_lin)

        return StoreConfiguration(
            concept=concept,
            m_lin=m_lin,
            mix=CategoryMix(
                fb_share=fb_share,
                non_fb_share=nf_share,
                subcategory_shares=subcategory_shares,
            ).normalize(),
            excluded_categories=excluded,
            locked_fields=locked,
        )

    @staticmethod
    def guests_per_chambre(request: RodSimulationRequest) -> float:
        """Priorité à operating ; repli sur adultes + enfants (étape infos générales)."""
        op_guests = float(request.operating.guests_per_chambre)
        if op_guests > 0:
            return op_guests
        general = request.general
        total = float(general.adults_per_room) + float(general.children_per_room)
        return total if total > 0 else 1.7

    @staticmethod
    def prepare_request(request: RodSimulationRequest) -> RodSimulationRequest:
        """Normalise operating.guests_per_chambre depuis les infos générales."""
        prepared = deepcopy(request)
        prepared.operating.guests_per_chambre = DirectorInputMapper.guests_per_chambre(
            prepared
        )
        return prepared