"""
Enrichissement automatique des features manquantes.

Pipeline
--------
1. Géocode si lat/lon absents (adresse → Nominatim)
2. Proximity (Overpass) autour du point
3. Weather (Meteostat) — moyennes mensuelles récentes
4. Holidays — zone scolaire + compteurs mois type (union exclusive)

Les rebuilds massifs restent côté admin ; ici on calcule **pour un hôtel**.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from archive.accor_1_0_5.src.accor.user.models import EnrichedFeatures, HotelIdentity, SimulationRequest
from archive.accor_1_0_5.src.accor.user.services.geocode import Geocoder


class FeatureEnricher:
    """Calcule weather / proximity / holidays pour une saisie user."""

    def __init__(self, geocoder: Geocoder | None = None) -> None:
        self.geocoder = geocoder or Geocoder()

    def ensure_coords(self, identity: HotelIdentity) -> tuple[HotelIdentity, list[str]]:
        warnings: list[str] = []
        if identity.has_coords():
            return identity, warnings

        result = self.geocoder.geocode(
            street=identity.hotel_adresse_postale_1
            or identity.hotel_adresse_postale_2,
            postal_code=identity.hotel_code_postal,
            city=identity.hotel_city,
            free_text=identity.address_line() or identity.hotel_name,
        )
        if result.get("ok"):
            identity.hotel_lat = float(result["lat"])
            identity.hotel_lon = float(result["lon"])
            return identity, warnings

        warnings.append(
            f"Géocodage impossible : {result.get('error') or 'échec'}. "
            "Saisissez lat/lon manuellement."
        )
        return identity, warnings

    def enrich(
        self,
        request: SimulationRequest,
        *,
        do_proximity: bool = True,
        do_weather: bool = True,
        do_holidays: bool = True,
    ) -> SimulationRequest:
        warnings: list[str] = list(request.enriched.warnings or [])
        identity, w = self.ensure_coords(request.identity)
        request.identity = identity
        warnings.extend(w)

        lat, lon = identity.hotel_lat, identity.hotel_lon
        enriched = EnrichedFeatures(
            lat=lat,
            lon=lon,
            address_resolved=identity.address_line(),
            geocode_source="provided" if identity.has_coords() else "nominatim",
            warnings=warnings,
        )

        if lat is None or lon is None:
            enriched.warnings.append("Enrichissement météo/proximité sauté (pas de coords).")
            request.enriched = enriched
            return request

        if do_proximity:
            try:
                from archive.accor_1_0_5.src.accor.geo_proximity import ProximityFromGeo

                prox = ProximityFromGeo()
                enriched.proximity = {
                    k: float(v) for k, v in (prox.for_point(float(lat), float(lon)) or {}).items()
                    if v is not None
                }
            except Exception as exc:  # noqa: BLE001
                enriched.warnings.append(f"Proximité indisponible : {exc}")

        if do_weather:
            try:
                import pandas as pd
                from archive.accor_1_0_5.src.accor.geo_weather import WeatherFromGeo

                today = date.today()
                years = [today.year - 1]
                df = WeatherFromGeo(years=years).for_point(float(lat), float(lon))
                temps, precs = [], []
                if df is not None and not df.empty:
                    if "meteo_temperature_c_mean" in df.columns:
                        temps = [
                            float(x)
                            for x in pd.to_numeric(
                                df["meteo_temperature_c_mean"], errors="coerce"
                            ).dropna()
                        ]
                    if "meteo_precipitations_mm_mean" in df.columns:
                        precs = [
                            float(x)
                            for x in pd.to_numeric(
                                df["meteo_precipitations_mm_mean"], errors="coerce"
                            ).dropna()
                        ]
                enriched.weather = {
                    "meteo_temperature_c_mean": (
                        sum(temps) / len(temps) if temps else 0.0
                    ),
                    "meteo_precipitations_mm_mean": (
                        sum(precs) / len(precs) if precs else 0.0
                    ),
                    "n_months_observed": float(len(temps)),
                }
            except Exception as exc:  # noqa: BLE001
                enriched.warnings.append(f"Météo indisponible : {exc}")

        if do_holidays:
            try:
                enriched.holidays = self._holidays_summary(float(lat), float(lon))
            except Exception as exc:  # noqa: BLE001
                enriched.warnings.append(f"Holidays indisponibles : {exc}")

        request.enriched = enriched
        return request

    @staticmethod
    def _holidays_summary(lat: float, lon: float) -> dict[str, Any]:
        """Zone scolaire + stats annuelles approximatives pour un point."""
        from archive.accor_1_0_5.src.accor.geo_holidays import (
            _days_in_month,
            _days_in_ranges,
            _school_periods_for_year,
            _weekends_in_month,
            _zone_from_lat_lon,
            french_public_holidays,
        )

        zone = _zone_from_lat_lon(lat, lon)
        year = date.today().year - 1  # année complète
        school = _school_periods_for_year(year)
        vac_ranges = school.get(zone, [])

        nb_feries = nb_weekend = nb_vac = nb_hol = nb_days = 0
        for month in range(1, 13):
            days = _days_in_month(year, month)
            nb_days += len(days)
            feries = {d for d in days if d in french_public_holidays(year)}
            weekends = set(_weekends_in_month(days))
            vac = set(_days_in_ranges(days, vac_ranges))
            hol = feries | weekends | vac
            nb_feries += len(feries)
            nb_weekend += len(weekends)
            nb_vac += len(vac)
            nb_hol += len(hol)

        return {
            "zone": zone,
            "zone_scolaire_a": 1 if zone == "A" else 0,
            "zone_scolaire_b": 1 if zone == "B" else 0,
            "zone_scolaire_c": 1 if zone == "C" else 0,
            "ref_year": year,
            "nb_jours_feries_an": nb_feries,
            "nb_jours_weekend_an": nb_weekend,
            "nb_jours_vacances_scolaires_an": nb_vac,
            "nb_jours_holidays_an": nb_hol,
            "pct_jours_holidays": round(nb_hol / nb_days, 4) if nb_days else 0.0,
        }
