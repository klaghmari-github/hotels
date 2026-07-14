"""MeteoPrep — météo mensuelle par hôtel à partir de hotel_lat / hotel_lon.

Orchestration pipeline : charge les hôtels (coordonnées déjà résolues),
délègue le calcul météo à :class:`MonthlyWeather`, impute et sérialise.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

from .weather import (
    READABLE_WEATHER,
    MonthlyWeather,
    as_coord,
    default_target_years,
    impute_previous_year_month,
    resolve_years,
)

# Champs d'identification hôtel (RodPrep) utilisés par MeteoPrep.
HOTEL_IDENTITY_COLS = [
    "hotel_code",
    "hotel_name",
    "hotel_brand",
    "hotel_city",
    "hotel_lat",
    "hotel_lon",
]


class MeteoPrep:
    """Pipeline : hôtels géolocalisés → table météo mensuelle.

    La météo est demandée pour le point ``(hotel_lat, hotel_lon)`` via
    :class:`MonthlyWeather`. Aucun géocodage d'adresse : les coordonnées
    doivent déjà être présentes (responsabilité d'une autre étape, ex. RodPrep).

    Années cibles :
      - si ``target_years`` est fourni → ces années ;
      - sinon → année en cours uniquement.

    Imputation (sans jamais forcer à 0) :
      mois manquant de l'année Y ← même mois de l'année Y-1 (puis Y-2, …).
    """

    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        target_years: Sequence[int] | None = None,
        weather: MonthlyWeather | None = None,
    ) -> None:
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.target_years = resolve_years(target_years)
        # Fenêtre élargie d'un an en amont pour permettre l'imputation N←N-1.
        fetch_years = self._fetch_years()
        self.weather = weather or MonthlyWeather(years=fetch_years)

    def _fetch_years(self) -> tuple[int, ...]:
        """Années cibles + année précédente (source d'imputation)."""
        years = set(self.target_years)
        years.add(min(self.target_years) - 1)
        return tuple(sorted(years))

    # Compat notebooks / code existant qui lisent MeteoPrep.TARGET_YEARS
    @property
    def TARGET_YEARS(self) -> tuple[int, ...]:  # noqa: N802
        return self.target_years

    def load_input(self) -> pd.DataFrame:
        path = self.input_dir / "hotels.csv"
        if path.exists():
            return pd.read_csv(path)
        parquet = self.input_dir / "hotels.parquet"
        if parquet.exists():
            return pd.read_parquet(parquet)
        raise FileNotFoundError(f"Entrée MeteoPrep absente dans {self.input_dir}")

    def fill_input_from_rod(self, rod_output_dir: Path) -> Path:
        """Copie les champs d'identité hôtel depuis la sortie RodPrep.

        Les coordonnées ``hotel_lat`` / ``hotel_lon`` doivent déjà être
        renseignées ; aucun fallback adresse ici.
        """
        source = Path(rod_output_dir) / "hotel_lookup.parquet"
        if not source.exists():
            raise FileNotFoundError("Sortie RodPrep introuvable")
        frame = pd.read_parquet(source)
        cols = [c for c in HOTEL_IDENTITY_COLS if c in frame.columns]
        out = frame[cols].copy()
        if "hotel_code" in out.columns:
            out = out.dropna(subset=["hotel_code"]).drop_duplicates(subset=["hotel_code"])
            out["hotel_code"] = out["hotel_code"].astype(str)
        self.input_dir.mkdir(parents=True, exist_ok=True)
        path = self.input_dir / "hotels.parquet"
        out.to_parquet(path, index=False)
        out.to_csv(self.input_dir / "hotels.csv", index=False)
        return path

    def compute_meteo_final(
        self,
        geo: pd.DataFrame | None = None,
        years: Sequence[int] | None = None,
        *,
        use_pure_api: bool = True,
    ) -> pd.DataFrame:
        """Dataframe météo finale à partir des données de géo et des années.

        Parameters
        ----------
        geo :
            DataFrame de géolocalisation (``hotel_lat`` / ``hotel_lon``).
            Si ``None``, charge ``Input/``.
        years :
            Années cibles. Si ``None``, utilise ``self.target_years``.
        use_pure_api :
            Si ``True`` (défaut), délègue à
            :meth:`MonthlyWeather.compute_meteo_final` (geo + années → final).
            Si ``False``, parcours hôtel ligne-à-ligne (hook
            ``_fetch_weather_by_year_month``, utile pour les tests mockés).

        Returns
        -------
        pd.DataFrame
            Grille ``hotel_code × annee × mois`` avec indicateurs ``meteo_*``.
        """
        locations = geo if geo is not None else self.load_input()
        target = resolve_years(years) if years is not None else self.target_years

        if not use_pure_api:
            return self._compute_meteo_final_via_hotels(locations, target)

        id_cols = tuple(
            c for c in ("hotel_code", "hotel_name") if c in locations.columns
        )
        frame = MonthlyWeather.compute_meteo_final(
            locations,
            years=target,
            lat_col="hotel_lat",
            lon_col="hotel_lon",
            id_cols=id_cols or None,
            impute=True,
        )
        drop_geo = [c for c in ("lat", "lon") if c in frame.columns]
        if drop_geo:
            frame = frame.drop(columns=drop_geo)
        if frame.empty and id_cols:
            frame = pd.DataFrame(columns=list(id_cols) + ["annee", "mois"])
        return frame

    def _compute_meteo_final_via_hotels(
        self,
        hotels: pd.DataFrame,
        target_years: tuple[int, ...],
    ) -> pd.DataFrame:
        """Parcours step-by-step hôtel (fetch par point, grille, imputation)."""
        rows: list[dict] = []
        for _, hotel in hotels.iterrows():
            try:
                rows.extend(self._rows_for_hotel(hotel))
            except Exception as exc:
                code = str(hotel.get("hotel_code") or "")
                name = str(hotel.get("hotel_name") or code)
                rows.extend(self._empty_year_rows(code, name, warnings=[str(exc)]))

        frame = pd.DataFrame(rows)
        if frame.empty:
            return pd.DataFrame(columns=["hotel_code", "hotel_name", "annee", "mois"])

        frame = self._impute_missing(frame)
        frame = frame[frame["annee"].isin(target_years)].copy()
        return frame.sort_values(
            ["hotel_code", "annee", "mois"], kind="mergesort"
        ).reset_index(drop=True)

    def run(self) -> pd.DataFrame:
        # use_pure_api=False : conserve le hook mockable en tests unitaires
        frame = self.compute_meteo_final(use_pure_api=False)
        frame.to_parquet(self.output_dir / "meteo_monthly.parquet", index=False)
        frame.to_csv(self.output_dir / "meteo_monthly.csv", index=False)
        return frame

    def weather_for_hotel(self, hotel: pd.Series | dict[str, Any]) -> dict[str, Any]:
        """Récupère la météo au point hôtel (lat/lon uniquement).

        Sans coordonnées exploitables → ``source="failed"`` et météo vide.
        Pas de géocodage d'adresse (responsabilité d'une autre classe).
        """
        code = str(hotel.get("hotel_code") or "")
        name = str(hotel.get("hotel_name") or code)
        lat = as_coord(hotel.get("hotel_lat"))
        lon = as_coord(hotel.get("hotel_lon"))
        warnings: list[str] = []

        if lat is None or lon is None:
            warnings.append("Coordonnées absentes (hotel_lat / hotel_lon).")
            return {
                "hotel_code": code,
                "hotel_name": name,
                "hotel_lat": None,
                "hotel_lon": None,
                "source": "failed",
                "warnings": warnings,
                "weather_by_year_month": {},
                "nb_cles_meteo": 0,
            }

        start_year, end_year = min(self.weather.years), max(self.weather.years)
        try:
            # Hook interne (patchable en tests) → MonthlyWeather
            by_ym = self._fetch_weather_by_year_month(lat, lon, start_year, end_year)
        except Exception as exc:
            by_ym = {}
            warnings.append(f"Récupération météo en erreur: {exc}")

        n_keys = sum(len(v) for v in by_ym.values())
        return {
            "hotel_code": code,
            "hotel_name": name,
            "hotel_lat": lat,
            "hotel_lon": lon,
            "source": "hotel_coords",
            "warnings": warnings,
            "weather_by_year_month": by_ym,
            "nb_cles_meteo": n_keys,
        }

    def _fetch_weather_by_year_month(
        self,
        lat: float,
        lon: float,
        start_year: int,
        end_year: int,
    ) -> dict[tuple[int, int], dict[str, float]]:
        """Délègue à :class:`MonthlyWeather` (compat tests / appels internes)."""
        return self.weather.fetch_by_year_month(
            lat, lon, start_year=start_year, end_year=end_year
        )

    def _rows_for_hotel(self, hotel: pd.Series) -> list[dict]:
        info = self.weather_for_hotel(hotel)
        by_ym: dict[tuple[int, int], dict[str, float]] = (
            info.get("weather_by_year_month") or {}
        )
        code = info["hotel_code"]
        name = info["hotel_name"]

        # Grille : années cibles + année préc. pour imputer + années observées
        years = set(self.target_years)
        years.update(y for (y, _m) in by_ym.keys())
        years.add(min(self.target_years) - 1)
        years = {int(y) for y in years if y is not None}

        rows: list[dict] = []
        for year in sorted(years):
            for month in range(1, 13):
                row: dict[str, Any] = {
                    "hotel_code": code,
                    "hotel_name": name,
                    "annee": year,
                    "mois": month,
                }
                row.update(by_ym.get((year, month), {}))
                rows.append(row)
        return rows

    def _empty_year_rows(
        self,
        code: str,
        name: str,
        warnings: Iterable[str] | None = None,
    ) -> list[dict]:
        _ = warnings  # réservé logs / debug
        rows: list[dict] = []
        for year in self.target_years:
            for month in range(1, 13):
                rows.append(
                    {
                        "hotel_code": code,
                        "hotel_name": name,
                        "annee": int(year),
                        "mois": month,
                    }
                )
        return rows

    def _readable_monthly(self, weather: dict) -> dict[int, dict[str, float]]:
        """Compat : transforme clés ``[d_]m{MM}_{metric}_{stat}`` (sans année).

        Utilisé par le notebook d'exploration sur un profil mensuel aplati.
        Sans info d'année, les valeurs sont traitées comme année en cours.
        """
        from datetime import datetime

        by_month: dict[int, dict[str, float]] = {m: {} for m in range(1, 13)}
        if not weather:
            return by_month

        sample_key = next(iter(weather), None)
        if isinstance(sample_key, tuple) and len(sample_key) == 2:
            current_year = datetime.utcnow().year
            years = sorted({int(y) for y, _m in weather.keys()})
            preferred = (
                current_year if current_year in years else (years[-1] if years else current_year)
            )
            for (year, month), metrics in weather.items():
                if int(year) != preferred:
                    continue
                try:
                    month_i = int(month)
                except (TypeError, ValueError):
                    continue
                if 1 <= month_i <= 12 and isinstance(metrics, dict):
                    by_month[month_i] = {
                        k: float(v)
                        for k, v in metrics.items()
                        if k.startswith("meteo_")
                    }
            return by_month

        for key, value in weather.items():
            k = str(key)
            k = k[2:] if k.startswith("d_") else k
            if not k.startswith("m"):
                continue
            parts = k.split("_")
            if len(parts) < 3:
                continue
            try:
                month = int(parts[0].replace("m", ""))
            except ValueError:
                continue
            if month < 1 or month > 12:
                continue
            metric = parts[1]
            stat = parts[2]
            readable = READABLE_WEATHER.get(metric, metric)
            col = f"meteo_{readable}_{stat}"
            try:
                by_month.setdefault(month, {})[col] = float(value)
            except (TypeError, ValueError):
                continue
        return by_month

    @staticmethod
    def _month_vector(monthly: dict[int, dict[str, float]], month: int) -> dict[str, float]:
        return dict(monthly.get(month, {}))

    @staticmethod
    def _as_coord(value: Any) -> float | None:
        return as_coord(value)

    def _impute_missing(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Impute par hôtel : mois manquant ← même mois année précédente."""
        return impute_previous_year_month(
            frame,
            group_cols=("hotel_code",),
            year_col="annee",
            month_col="mois",
            value_prefix="meteo_",
        )
