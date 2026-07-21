"""HolidaysPrep — jours fériés et vacances scolaires par hôtel × année × mois.

Entrée : identité RodPrep (``hotel_code`` Accor + ``hotel_lat`` / ``hotel_lon``).
Sortie : table mensuelle + Excel dans ``Output/``.

Colonnes clés :
  - ``nb_jours_feries``
  - ``nb_jours_vacances_scolaires`` (tous les jours de vacances dans le mois)
  - ``nb_jours_vacances_hors_feries`` (vacances scolaires hors jours fériés)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from prepare.holidays_prep.calendar import SchoolHolidayCalendar


def as_coord(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        coord = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(coord):
        return None
    return coord


HOTEL_IDENTITY_COLS = [
    "hotel_code",
    "hotel_name",
    "hotel_brand",
    "hotel_city",
    "hotel_lat",
    "hotel_lon",
]


def default_target_years(now: datetime | None = None) -> tuple[int, ...]:
    year = (now or datetime.utcnow()).year
    return tuple(range(year - 3, year + 1))


class HolidaysPrep:
    """Pipeline : hôtels géolocalisés → jours fériés / vacances par mois."""

    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        *,
        target_years: Sequence[int] | None = None,
        calendar: SchoolHolidayCalendar | None = None,
    ) -> None:
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.target_years = (
            tuple(int(y) for y in target_years)
            if target_years
            else default_target_years()
        )
        self.calendar = calendar or SchoolHolidayCalendar()

    def fill_input_from_rod(self, rod_output_dir: Path) -> Path:
        """Copie l'identité hôtel depuis RodPrep (code Accor + coords)."""
        source = Path(rod_output_dir) / "hotel_lookup.parquet"
        if not source.exists():
            raise FileNotFoundError(f"Sortie RodPrep introuvable : {source}")
        frame = pd.read_parquet(source)
        cols = [c for c in HOTEL_IDENTITY_COLS if c in frame.columns]
        out = frame[cols].copy()
        if "hotel_code" not in out.columns:
            raise ValueError("hotel_lookup sans hotel_code — relancer RodPrep.")
        out = out.dropna(subset=["hotel_code"]).drop_duplicates(subset=["hotel_code"])
        out["hotel_code"] = out["hotel_code"].astype(str).str.strip()
        out = out[out["hotel_code"].ne("") & out["hotel_code"].str.lower().ne("none")]
        out = out[out["hotel_code"].str.lower().ne("nan")]
        self.input_dir.mkdir(parents=True, exist_ok=True)
        path = self.input_dir / "hotels.parquet"
        out.to_parquet(path, index=False)
        out.to_csv(self.input_dir / "hotels.csv", index=False)
        return path

    def load_input(self) -> pd.DataFrame:
        path = self.input_dir / "hotels.parquet"
        if path.exists():
            return pd.read_parquet(path)
        csv_path = self.input_dir / "hotels.csv"
        if csv_path.exists():
            return pd.read_csv(csv_path)
        raise FileNotFoundError(f"Entrée HolidaysPrep absente dans {self.input_dir}")

    def run(self) -> pd.DataFrame:
        hotels = self.load_input()
        rows: list[dict[str, Any]] = []
        for _, hotel in hotels.iterrows():
            try:
                rows.extend(self._rows_for_hotel(hotel))
            except Exception as exc:
                rows.extend(self._empty_rows(hotel, warnings=[str(exc)]))

        frame = pd.DataFrame(rows)
        if frame.empty:
            frame = pd.DataFrame(columns=self._output_columns())
        else:
            frame = frame.sort_values(
                ["hotel_code", "annee", "mois"], kind="mergesort"
            ).reset_index(drop=True)

        self._write_outputs(frame)
        return frame

    def _rows_for_hotel(self, hotel: pd.Series) -> list[dict[str, Any]]:
        code = self._normalize_code(hotel.get("hotel_code"))
        name = str(hotel.get("hotel_name") or code or "").strip()
        lat = as_coord(hotel.get("hotel_lat"))
        lon = as_coord(hotel.get("hotel_lon"))

        if not code:
            return self._empty_rows(
                hotel, warnings=["hotel_code Accor absent"]
            )
        if lat is None or lon is None:
            return self._empty_rows(
                hotel, warnings=["Coordonnées hotel_lat/hotel_lon absentes"]
            )

        geo, monthly = self.calendar.monthly_for_point(lat, lon, self.target_years)
        base = {
            "hotel_code": code,
            "hotel_name": name,
            "hotel_lat": lat,
            "hotel_lon": lon,
            "departement": geo.departement,
            "commune": geo.commune,
            "zone_scolaire": geo.zone,
            "localisation": geo.label,
        }
        rows: list[dict[str, Any]] = []
        for m in monthly:
            rows.append(
                {
                    **base,
                    "annee": m.annee,
                    "mois": m.mois,
                    "nb_jours_feries": m.nb_jours_feries,
                    "nb_jours_vacances_scolaires": m.nb_jours_vacances_scolaires,
                    "nb_jours_vacances_hors_feries": m.nb_jours_vacances_hors_feries,
                    "nb_jours_dans_mois": m.nb_jours_dans_mois,
                }
            )
        return rows

    def _empty_rows(
        self,
        hotel: pd.Series | dict[str, Any],
        *,
        warnings: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        code = self._normalize_code(hotel.get("hotel_code")) or ""
        name = str(hotel.get("hotel_name") or code or "").strip()
        base = {
            "hotel_code": code,
            "hotel_name": name,
            "hotel_lat": as_coord(hotel.get("hotel_lat")),
            "hotel_lon": as_coord(hotel.get("hotel_lon")),
            "departement": None,
            "commune": None,
            "zone_scolaire": None,
            "localisation": None,
            "warnings": "; ".join(warnings or []),
        }
        rows: list[dict[str, Any]] = []
        for year in self.target_years:
            for month in range(1, 13):
                rows.append(
                    {
                        **base,
                        "annee": year,
                        "mois": month,
                        "nb_jours_feries": None,
                        "nb_jours_vacances_scolaires": None,
                        "nb_jours_vacances_hors_feries": None,
                        "nb_jours_dans_mois": monthrange_days(year, month),
                    }
                )
        return rows

    def _write_outputs(self, frame: pd.DataFrame) -> None:
        parquet = self.output_dir / "holidays_monthly.parquet"
        csv = self.output_dir / "holidays_monthly.csv"
        xlsx = self.output_dir / "holidays_monthly.xlsx"
        frame.to_parquet(parquet, index=False)
        frame.to_csv(csv, index=False)

        summary = pd.DataFrame()
        if not frame.empty and "hotel_code" in frame.columns:
            summary = (
                frame.groupby(
                    [
                        "hotel_code",
                        "hotel_name",
                        "zone_scolaire",
                        "departement",
                        "annee",
                    ],
                    dropna=False,
                )[
                    [
                        "nb_jours_feries",
                        "nb_jours_vacances_scolaires",
                        "nb_jours_vacances_hors_feries",
                    ]
                ]
                .sum(min_count=1)
                .reset_index()
            )

        with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
            frame.to_excel(writer, index=False, sheet_name="holidays_monthly")
            if not summary.empty:
                summary.to_excel(writer, index=False, sheet_name="resume_annuel")


    @staticmethod
    def _output_columns() -> list[str]:
        return [
            "hotel_code",
            "hotel_name",
            "hotel_lat",
            "hotel_lon",
            "departement",
            "commune",
            "zone_scolaire",
            "localisation",
            "annee",
            "mois",
            "nb_jours_feries",
            "nb_jours_vacances_scolaires",
            "nb_jours_vacances_hors_feries",
            "nb_jours_dans_mois",
        ]

    @staticmethod
    def _normalize_code(value: Any) -> str | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        text = str(value).strip()
        if not text or text.lower() in {"none", "nan", "null"}:
            return None
        return text


def monthrange_days(year: int, month: int) -> int:
    from calendar import monthrange

    return monthrange(year, month)[1]
