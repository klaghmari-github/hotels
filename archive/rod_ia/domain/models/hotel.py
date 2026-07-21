"""Modèles d'identité et d'état opérationnel d'un hôtel."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class HotelIdentity:
    """Identité saisie par le directeur (écran ROD connexion / infos générales)."""

    hotel_name: str
    city: str = ""
    address: str = ""
    brand: str = ""
    hotel_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> HotelIdentity:
        data = data or {}
        return cls(**{k: data.get(k) for k in cls.__dataclass_fields__})


class HotelOperatingState:
    """État hôtel avec variables interdépendantes (chambres, TO, clients).

    Les setters recalculent automatiquement les grandeurs dérivées
    (chambres occupées, clients/jour, clients/mois).
    """

    def __init__(
        self,
        nb_chambres: int,
        taux_occupation: float,
        guests_per_chambre: float = 1.7,
        jours_mois: float = 30.5,
    ) -> None:
        self._nb_chambres = max(int(nb_chambres), 0)
        self._taux_occupation = self._clip_rate(float(taux_occupation))
        self._guests_per_chambre = max(float(guests_per_chambre), 0.0)
        self._jours_mois = max(float(jours_mois), 1.0)
        self._recompute_from_rate()

    @staticmethod
    def _clip_rate(value: float) -> float:
        if value > 1.0:
            value /= 100.0
        return min(max(value, 0.0), 1.0)

    def _recompute_from_rate(self) -> None:
        self._chambres_occupees = self._nb_chambres * self._taux_occupation
        self._clients_jour = self._chambres_occupees * self._guests_per_chambre
        self._clients_mois = self._clients_jour * self._jours_mois

    def _recompute_rate_from_clients_jour(self) -> None:
        denom = self._nb_chambres * self._guests_per_chambre
        self._taux_occupation = (
            self._clip_rate(self._clients_jour / denom) if denom else 0.0
        )
        self._chambres_occupees = self._nb_chambres * self._taux_occupation
        self._clients_mois = self._clients_jour * self._jours_mois

    @property
    def nb_chambres(self) -> int:
        return self._nb_chambres

    @nb_chambres.setter
    def nb_chambres(self, value: int) -> None:
        self._nb_chambres = max(int(value), 0)
        self._recompute_from_rate()

    @property
    def taux_occupation(self) -> float:
        return self._taux_occupation

    @taux_occupation.setter
    def taux_occupation(self, value: float) -> None:
        self._taux_occupation = self._clip_rate(float(value))
        self._recompute_from_rate()

    @property
    def guests_per_chambre(self) -> float:
        return self._guests_per_chambre

    @guests_per_chambre.setter
    def guests_per_chambre(self, value: float) -> None:
        self._guests_per_chambre = max(float(value), 0.0)
        self._recompute_from_rate()

    @property
    def chambres_occupees(self) -> float:
        return self._chambres_occupees

    @chambres_occupees.setter
    def chambres_occupees(self, value: float) -> None:
        self._chambres_occupees = max(float(value), 0.0)
        self._taux_occupation = (
            self._clip_rate(self._chambres_occupees / self._nb_chambres)
            if self._nb_chambres
            else 0.0
        )
        self._clients_jour = self._chambres_occupees * self._guests_per_chambre
        self._clients_mois = self._clients_jour * self._jours_mois

    @property
    def clients_jour(self) -> float:
        return self._clients_jour

    @clients_jour.setter
    def clients_jour(self, value: float) -> None:
        self._clients_jour = max(float(value), 0.0)
        self._recompute_rate_from_clients_jour()

    @property
    def clients_mois(self) -> float:
        return self._clients_mois

    @clients_mois.setter
    def clients_mois(self, value: float) -> None:
        self._clients_mois = max(float(value), 0.0)
        self._clients_jour = self._clients_mois / self._jours_mois
        self._recompute_rate_from_clients_jour()

    def to_dict(self) -> dict:
        return {
            "nb_chambres": self.nb_chambres,
            "taux_occupation": self.taux_occupation,
            "guests_per_chambre": self.guests_per_chambre,
            "chambres_occupees": self.chambres_occupees,
            "clients_jour": self.clients_jour,
            "clients_mois": self.clients_mois,
            "jours_mois": self._jours_mois,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> HotelOperatingState:
        data = data or {}
        return cls(
            nb_chambres=data.get("nb_chambres", 0),
            taux_occupation=data.get("taux_occupation", 0),
            guests_per_chambre=data.get("guests_per_chambre", 1.7),
            jours_mois=data.get("jours_mois", 30.5),
        )