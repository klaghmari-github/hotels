"""HolidaysPrep — jours fériés et vacances scolaires par hôtel × année × mois.

Entrée : identité RodPrep (``hotel_code`` Accor + ``hotel_lat`` / ``hotel_lon``).
Sortie principale : ``hotel_holidays_data.xlsx`` (+ parquet/csv).

Colonnes clés :
  - ``nb_jours_feries`` / ``jours_feries`` (array ISO dates)
  - ``nb_jours_vacances_scolaires`` / ``jours_vacances_scolaires``
  - ``nb_jours_vacances_hors_feries`` / ``jours_vacances_hors_feries``
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from prepare.holidays_prep.calendar import SchoolHolidayCalendar

# Fichiers de sortie canoniques
OUTPUT_XLSX = "hotel_holidays_data.xlsx"
OUTPUT_PARQUET = "hotel_holidays_data.parquet"
OUTPUT_CSV = "hotel_holidays_data.csv"
# Alias rétrocompat
LEGACY_STEM = "holidays_monthly"

ARRAY_COLS = (
    "jours_feries",
    "jours_vacances_scolaires",
    "jours_vacances_hors_feries",
)


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


def dates_to_json_array(dates: Sequence[str] | None) -> str:
    """Sérialise une liste de dates ISO en JSON array (compatible Excel)."""
    if not dates:
        return "[]"
    return json.dumps(list(dates), ensure_ascii=False)


def parse_json_array(value: Any) -> list[str]:
    """Parse un champ array (liste Python, JSON string, numpy array, ou vide)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    # numpy.ndarray / pandas arrays
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        try:
            value = value.tolist()
        except Exception:
            pass
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for x in value:
            # évite double-encodage "['2024-01-01']"
            if isinstance(x, (list, tuple)):
                out.extend(str(i) for i in x)
            else:
                s = str(x).strip()
                if s.startswith("[") and s.endswith("]"):
                    try:
                        nested = json.loads(s.replace("'", '"'))
                        if isinstance(nested, list):
                            out.extend(str(i) for i in nested)
                            continue
                    except json.JSONDecodeError:
                        pass
                out.append(s)
        return out
    text = str(value).strip()
    if not text or text == "[]" or text.lower() == "nan":
        return []
    # Python repr de liste avec quotes simples
    if text.startswith("[") and text.endswith("]"):
        try:
            data = json.loads(text.replace("'", '"'))
            if isinstance(data, list):
                return [str(x) for x in data]
        except json.JSONDecodeError:
            pass
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [str(x) for x in data]
    except json.JSONDecodeError:
        pass
    # fallback séparateurs
    for sep in ("|", ";", ","):
        if sep in text:
            return [p.strip().strip("'\"") for p in text.split(sep) if p.strip()]
    return [text]



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
        # Copie optionnelle vers SalesPrep/Input
        sales_input_dir: Path | None = None,
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
        self.sales_input_dir = Path(sales_input_dir) if sales_input_dir else None

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
            return self._empty_rows(hotel, warnings=["hotel_code Accor absent"])
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
                    # Arrays (listes Python → parquet list ; Excel = JSON)
                    "jours_feries": list(m.jours_feries),
                    "jours_vacances_scolaires": list(m.jours_vacances_scolaires),
                    "jours_vacances_hors_feries": list(m.jours_vacances_hors_feries),
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
                        "jours_feries": [],
                        "jours_vacances_scolaires": [],
                        "jours_vacances_hors_feries": [],
                    }
                )
        return rows

    def _write_outputs(self, frame: pd.DataFrame) -> None:
        # Parquet conserve les listes natives
        parquet_path = self.output_dir / OUTPUT_PARQUET
        frame.to_parquet(parquet_path, index=False)

        # CSV / Excel : arrays en JSON string
        excel_frame = frame.copy()
        for col in ARRAY_COLS:
            if col in excel_frame.columns:
                excel_frame[col] = excel_frame[col].map(
                    lambda v: dates_to_json_array(v if isinstance(v, (list, tuple)) else parse_json_array(v))
                )

        excel_frame.to_csv(self.output_dir / OUTPUT_CSV, index=False)

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

        xlsx_path = self.output_dir / OUTPUT_XLSX
        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
            excel_frame.to_excel(writer, index=False, sheet_name="hotel_holidays")
            if not summary.empty:
                summary.to_excel(writer, index=False, sheet_name="resume_annuel")

        # Alias rétrocompat
        for stem, ext in (
            (LEGACY_STEM, ".parquet"),
            (LEGACY_STEM, ".csv"),
            (LEGACY_STEM, ".xlsx"),
        ):
            src = {
                ".parquet": parquet_path,
                ".csv": self.output_dir / OUTPUT_CSV,
                ".xlsx": xlsx_path,
            }[ext]
            dst = self.output_dir / f"{stem}{ext}"
            if src.exists():
                dst.write_bytes(src.read_bytes())

        # Alimente SalesPrep/Input si configuré
        if self.sales_input_dir is not None:
            self.sales_input_dir.mkdir(parents=True, exist_ok=True)
            target = self.sales_input_dir / OUTPUT_XLSX
            target.write_bytes(xlsx_path.read_bytes())
            # parquet aussi pour jointure typée
            (self.sales_input_dir / OUTPUT_PARQUET).write_bytes(parquet_path.read_bytes())

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
            "jours_feries",
            "jours_vacances_scolaires",
            "jours_vacances_hors_feries",
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


def load_hotel_holidays(path: Path) -> pd.DataFrame:
    """Charge ``hotel_holidays_data`` (xlsx / parquet / csv) pour SalesPrep."""
    path = Path(path)
    if path.is_dir():
        for name in (OUTPUT_PARQUET, OUTPUT_XLSX, OUTPUT_CSV, f"{LEGACY_STEM}.parquet"):
            candidate = path / name
            if candidate.exists():
                path = candidate
                break
    if not path.exists():
        raise FileNotFoundError(f"hotel_holidays_data introuvable : {path}")

    if path.suffix.lower() in {".parquet"}:
        frame = pd.read_parquet(path)
    elif path.suffix.lower() in {".xlsx", ".xls"}:
        # Feuille principale
        try:
            frame = pd.read_excel(path, sheet_name="hotel_holidays")
        except ValueError:
            frame = pd.read_excel(path, sheet_name=0)
    else:
        frame = pd.read_csv(path)

    for col in ARRAY_COLS:
        if col in frame.columns:
            frame[col] = frame[col].map(parse_json_array)
    return frame
