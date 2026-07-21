"""Calendrier scolaire et jours fériés France (indépendant du domaine hôtel).

Flux :
  1. ``(lat, lon)`` → département (API adresse data.gouv) → zone A/B/C
  2. Vacances scolaires de la zone (API education.gouv)
  3. Jours fériés légaux (calcul local, + Alsace-Moselle)
  4. Agrégation mensuelle : nb fériés / nb jours de vacances hors fériés
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Sequence
from zoneinfo import ZoneInfo

import requests

PARIS_TZ = ZoneInfo("Europe/Paris")

# ---------------------------------------------------------------------------
# Département → zone scolaire (académies métropolitaines, calendrier national)
# Source : regroupement officiel des académies en zones A / B / C.
# ---------------------------------------------------------------------------

def _zone_map() -> dict[str, str]:
    """Construit la table code département → zone (A, B, C)."""
    zone_a = {
        "01", "03", "07", "15", "16", "17", "19", "21", "23", "24", "25", "26",
        "33", "38", "39", "40", "42", "43", "47", "58", "63", "64", "69", "70",
        "71", "73", "74", "79", "86", "87", "89", "90",
    }
    zone_c = {
        # Île-de-France
        "75", "77", "78", "91", "92", "93", "94", "95",
        # Académies Montpellier / Toulouse
        "09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82",
    }
    # Tout le reste métropole → B (y compris Corse souvent alignée B/C selon années ;
    # on classe 2A/2B en B par défaut si l'API zone Corse n'est pas dispo)
    zone_b = {
        "02", "04", "05", "06", "08", "10", "13", "14", "18", "22", "27", "28",
        "29", "35", "36", "37", "41", "44", "45", "49", "50", "51", "52", "53",
        "54", "55", "56", "57", "59", "60", "61", "62", "67", "68", "72", "76",
        "80", "83", "84", "85", "88", "2A", "2B",
    }
    out: dict[str, str] = {}
    for d in zone_a:
        out[d] = "A"
    for d in zone_b:
        out[d] = "B"
    for d in zone_c:
        out[d] = "C"
    return out


DEPARTEMENT_TO_ZONE: dict[str, str] = _zone_map()

# Départements Alsace-Moselle : vendredi saint + 26 décembre
ALSACE_MOSELLE = frozenset({"57", "67", "68"})


# ---------------------------------------------------------------------------
# Jours fériés
# ---------------------------------------------------------------------------

def easter_sunday(year: int) -> date:
    """Dimanche de Pâques (algorithme de Meeus/Jones/Butcher, calendrier grégorien)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month, day = divmod(h + ll - 7 * m + 114, 31)
    return date(year, month, day + 1)


def french_public_holidays(year: int, *, departement: str | None = None) -> set[date]:
    """Jours fériés légaux en France pour une année civile."""
    easter = easter_sunday(year)
    days = {
        date(year, 1, 1),    # Jour de l'an
        easter + timedelta(days=1),  # Lundi de Pâques
        date(year, 5, 1),    # Fête du travail
        date(year, 5, 8),    # Victoire 1945
        easter + timedelta(days=39),  # Ascension
        easter + timedelta(days=50),  # Lundi de Pentecôte
        date(year, 7, 14),   # Fête nationale
        date(year, 8, 15),   # Assomption
        date(year, 11, 1),   # Toussaint
        date(year, 11, 11),  # Armistice
        date(year, 12, 25),  # Noël
    }
    dep = (departement or "").upper()
    if dep in ALSACE_MOSELLE:
        days.add(easter - timedelta(days=2))  # Vendredi saint
        days.add(date(year, 12, 26))  # Saint-Étienne
    return days


# ---------------------------------------------------------------------------
# Géocodage inverse → département / zone
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GeoZone:
    zone: str
    departement: str
    commune: str
    label: str


def extract_departement(props: dict[str, Any]) -> str | None:
    """Extrait le code département depuis une feature API adresse."""
    code = props.get("codeDepartement")
    if code:
        return str(code).strip().upper()

    citycode = str(props.get("citycode") or "").strip()
    if citycode.startswith("97") and len(citycode) >= 3:
        return citycode[:3]  # DOM
    if citycode.startswith("20") and len(citycode) >= 5:
        # Corse : 2A / 2B via citycode communal
        # 2A si citycode < 20200 approx — plus fiable via postcode
        pass
    if len(citycode) >= 2 and not citycode.startswith("97"):
        # Paris arrondissements 751xx → 75
        if citycode.startswith("75"):
            return "75"
        if citycode.startswith("20"):
            # fallback postcode
            pass
        else:
            return citycode[:2].upper()

    postcode = str(props.get("postcode") or "").strip()
    if postcode.startswith("20"):
        # Corse-du-Sud 200xx/201xx → 2A ; Haute-Corse 202xx → 2B
        try:
            n = int(postcode)
        except ValueError:
            return "2A"
        return "2A" if n < 20200 else "2B"
    if postcode.startswith("97") and len(postcode) >= 3:
        return postcode[:3]
    if len(postcode) >= 2:
        return postcode[:2]

    context = str(props.get("context") or "")
    # ex. "75, Paris, Île-de-France"
    if context:
        first = context.split(",")[0].strip().upper()
        if first:
            return first
    return None


def resolve_zone_from_coords(
    lat: float,
    lon: float,
    *,
    session: requests.Session | None = None,
    timeout: float = 15.0,
) -> GeoZone:
    """``(lat, lon)`` → zone scolaire via reverse geocode data.gouv."""
    http = session or requests
    url = "https://api-adresse.data.gouv.fr/reverse/"
    resp = http.get(url, params={"lat": lat, "lon": lon, "limit": 1}, timeout=timeout)
    resp.raise_for_status()
    features = resp.json().get("features") or []
    if not features:
        raise ValueError(f"Aucune commune pour lat={lat}, lon={lon}")

    props = features[0].get("properties") or {}
    dep = extract_departement(props)
    if not dep:
        raise ValueError(f"Département introuvable pour lat={lat}, lon={lon}")

    dep = dep.upper()
    if len(dep) == 1:
        dep = dep.zfill(2)

    zone = DEPARTEMENT_TO_ZONE.get(dep)
    if zone is None:
        # DOM / hors table → zone B par défaut (métropole) ou A pour inconnu
        zone = "B" if not dep.startswith("97") else "B"

    commune = str(props.get("city") or props.get("name") or "Inconnue")
    label = f"{commune} ({dep})"
    return GeoZone(zone=zone, departement=dep, commune=commune, label=label)


# ---------------------------------------------------------------------------
# Vacances scolaires (API education.gouv)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SchoolPeriod:
    description: str
    start: date  # inclus
    end: date    # exclus (jour de reprise)
    zone: str
    annee_scolaire: str | None = None


def _parse_api_date(value: str) -> date:
    """Parse une date API (souvent ISO UTC) en date civile Europe/Paris."""
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return date.fromisoformat(text[:10])
    if dt.tzinfo is None:
        return dt.date()
    return dt.astimezone(PARIS_TZ).date()


def fetch_school_holidays(
    zone: str,
    *,
    years: Sequence[int] | None = None,
    session: requests.Session | None = None,
    timeout: float = 30.0,
) -> list[SchoolPeriod]:
    """Récupère les périodes de vacances pour une zone A/B/C."""
    http = session or requests
    zone_label = f"Zone {zone}" if zone in {"A", "B", "C"} else zone

    url = "https://data.education.gouv.fr/api/records/1.0/search/"
    params: dict[str, Any] = {
        "dataset": "fr-en-calendrier-scolaire",
        "rows": 1000,
        "sort": "start_date",
        "refine.zones": zone_label,
    }
    resp = http.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    records = resp.json().get("records") or []

    year_set = set(years) if years is not None else None
    periods: list[SchoolPeriod] = []
    seen: set[tuple[date, date, str]] = set()

    for record in records:
        fields = record.get("fields") or {}
        start_raw = fields.get("start_date")
        end_raw = fields.get("end_date")
        if not start_raw or not end_raw:
            continue
        start = _parse_api_date(start_raw)
        end = _parse_api_date(end_raw)
        if end <= start:
            continue
        # Filtre années civiles touchées
        if year_set is not None:
            if not any(start.year == y or end.year == y or (start.year < y < end.year) for y in year_set):
                # aussi mois de l'année cible dans l'intervalle
                if not any(start <= date(y, 12, 31) and end > date(y, 1, 1) for y in year_set):
                    continue
        key = (start, end, str(fields.get("description") or ""))
        if key in seen:
            continue
        seen.add(key)
        periods.append(
            SchoolPeriod(
                description=str(fields.get("description") or ""),
                start=start,
                end=end,
                zone=zone,
                annee_scolaire=fields.get("annee_scolaire"),
            )
        )
    return sorted(periods, key=lambda p: p.start)


def iter_days(start: date, end: date) -> Iterable[date]:
    """Jours dans ``[start, end)``."""
    cur = start
    while cur < end:
        yield cur
        cur += timedelta(days=1)


def school_holiday_days(
    periods: Sequence[SchoolPeriod],
    year: int,
    month: int,
) -> set[date]:
    """Ensemble des jours de vacances scolaires dans (année, mois)."""
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    month_end_excl = last + timedelta(days=1)
    days: set[date] = set()
    for period in periods:
        # intersection [period.start, period.end) ∩ [first, month_end_excl)
        a = max(period.start, first)
        b = min(period.end, month_end_excl)
        if a < b:
            days.update(iter_days(a, b))
    return days


# ---------------------------------------------------------------------------
# Agrégation mensuelle
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MonthlyHolidayCounts:
    annee: int
    mois: int
    nb_jours_feries: int
    nb_jours_vacances_scolaires: int
    nb_jours_vacances_hors_feries: int
    nb_jours_dans_mois: int
    # Listes des jours concernés (ISO YYYY-MM-DD), triées
    jours_feries: tuple[str, ...]
    jours_vacances_scolaires: tuple[str, ...]
    jours_vacances_hors_feries: tuple[str, ...]


def _dates_to_iso(days: Iterable[date]) -> tuple[str, ...]:
    return tuple(sorted(d.isoformat() for d in days))


def monthly_counts_for_year(
    year: int,
    *,
    periods: Sequence[SchoolPeriod],
    departement: str | None = None,
) -> list[MonthlyHolidayCounts]:
    """12 lignes (jan–déc) : fériés vs vacances hors fériés (+ listes de jours)."""
    public = french_public_holidays(year, departement=departement)
    rows: list[MonthlyHolidayCounts] = []
    for month in range(1, 13):
        n_days = monthrange(year, month)[1]
        feries = {d for d in public if d.month == month}
        vacances = school_holiday_days(periods, year, month)
        vacances_hors = vacances - feries
        rows.append(
            MonthlyHolidayCounts(
                annee=year,
                mois=month,
                nb_jours_feries=len(feries),
                nb_jours_vacances_scolaires=len(vacances),
                nb_jours_vacances_hors_feries=len(vacances_hors),
                nb_jours_dans_mois=n_days,
                jours_feries=_dates_to_iso(feries),
                jours_vacances_scolaires=_dates_to_iso(vacances),
                jours_vacances_hors_feries=_dates_to_iso(vacances_hors),
            )
        )
    return rows



class SchoolHolidayCalendar:
    """Orchestration pure : coords + années → compteurs mensuels."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        resolve_zone: Callable[[float, float], GeoZone] | None = None,
        fetch_periods: Callable[[str, Sequence[int]], list[SchoolPeriod]] | None = None,
    ) -> None:
        self._session = session or requests.Session()
        self._resolve_zone = resolve_zone
        self._fetch_periods = fetch_periods
        self._zone_cache: dict[tuple[float, float], GeoZone] = {}
        self._periods_cache: dict[str, list[SchoolPeriod]] = {}

    def zone_for(self, lat: float, lon: float) -> GeoZone:
        key = (round(lat, 5), round(lon, 5))
        if key not in self._zone_cache:
            if self._resolve_zone:
                self._zone_cache[key] = self._resolve_zone(lat, lon)
            else:
                self._zone_cache[key] = resolve_zone_from_coords(
                    lat, lon, session=self._session
                )
        return self._zone_cache[key]

    def periods_for(self, zone: str, years: Sequence[int]) -> list[SchoolPeriod]:
        if zone not in self._periods_cache:
            if self._fetch_periods:
                self._periods_cache[zone] = self._fetch_periods(zone, years)
            else:
                self._periods_cache[zone] = fetch_school_holidays(
                    zone, years=years, session=self._session
                )
        return self._periods_cache[zone]

    def monthly_for_point(
        self,
        lat: float,
        lon: float,
        years: Sequence[int],
    ) -> tuple[GeoZone, list[MonthlyHolidayCounts]]:
        geo = self.zone_for(lat, lon)
        periods = self.periods_for(geo.zone, years)
        rows: list[MonthlyHolidayCounts] = []
        for year in years:
            rows.extend(
                monthly_counts_for_year(
                    int(year), periods=periods, departement=geo.departement
                )
            )
        return geo, rows
