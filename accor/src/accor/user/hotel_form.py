"""
Schéma des paramètres hôtel (hotel_data) pour le wizard run_user.

- Liste des champs éditables (hors identité pure).
- Déduplication (ex. pas de has_bar si compteur bar, pas de has_reunion
  si nb salles de réunion).
- Défauts globaux : majorité pour binaires, moyenne pour numériques.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

import numpy as np
import pandas as pd

from accor.data_io import DATA_DIR

Kind = Literal["bool", "int", "float", "rate"]


@dataclass(frozen=True)
class HotelFormField:
    """Un champ du formulaire paramètres de base."""

    id: str  # nom de colonne hotel_data (ou id synthétique)
    kind: Kind
    label: str
    section: str
    section_label: str
    hint: str = ""
    min_v: float | None = None
    max_v: float | None = None
    step: float | None = None
    # True = pas une colonne hotel_data (ex. guests_per_chambre)
    synthetic: bool = False


# Identité pure (affichée ailleurs) — jamais en formulaire paramètres
IDENTITY_COLS = frozenset(
    {
        "hotel_code",
        "hotel_name",
        "hotel_brand",
        "hotel_adresse_postale_1",
        "hotel_adresse_postale_2",
        "hotel_code_postal",
        "hotel_city",
        "hotel_country",
        "hotel_lat",
        "hotel_lon",
    }
)

# Solutions installées = résultat, pas paramètre de base saisi ici
SOLUTION_COLS = frozenset(
    {
        "hotel_solution_simply",
        "hotel_solution_liberty",
        "hotel_solution_connected",
    }
)

# Redondances à ne pas exposer (couvertes par un autre champ)
# - hotel_has_reunion ⇔ hotel_non_f_b_salles_de_reunion (>0)
# - has_bar / nb_bars : hotel_f_b_bar est binaire en base → un seul switch
# - has_restaurant ⇔ hotel_f_b_restaurant (compteur)
REDUNDANT_COLS = frozenset(
    {
        "hotel_has_reunion",
    }
)

SECTIONS: list[tuple[str, str]] = [
    ("exploitation", "Exploitation"),
    ("renovation", "Rénovation & contrat"),
    ("fb", "Restauration & bar"),
    ("nfb", "Services non F&B"),
    ("comfort", "Confort & accès"),
    ("lobby", "Équipements lobby"),
    ("clientele", "Clientèle"),
    ("corner", "Corner actuel"),
]


def _f(
    id_: str,
    kind: Kind,
    label: str,
    section: str,
    *,
    hint: str = "",
    min_v: float | None = None,
    max_v: float | None = None,
    step: float | None = None,
    synthetic: bool = False,
) -> HotelFormField:
    lab = dict(SECTIONS).get(section, section)
    return HotelFormField(
        id=id_,
        kind=kind,
        label=label,
        section=section,
        section_label=lab,
        hint=hint,
        min_v=min_v,
        max_v=max_v,
        step=step,
        synthetic=synthetic,
    )


# Ordre d'affichage = ordre de saisie métier
HOTEL_FORM_FIELDS: list[HotelFormField] = [
    # Exploitation
    _f("hotel_nb_chambres", "int", "Nombre de chambres", "exploitation", min_v=1, max_v=2000, step=1),
    _f(
        "hotel_to_annuel",
        "rate",
        "Taux d’occupation annuel (%)",
        "exploitation",
        min_v=1,
        max_v=100,
        step=0.1,
    ),
    _f(
        "guests_per_chambre",
        "float",
        "Clients par chambre",
        "exploitation",
        min_v=0.5,
        max_v=5,
        step=0.1,
        synthetic=True,
    ),
    _f(
        "hotel_to_le_plus_bas_taux",
        "rate",
        "TO le plus bas (%)",
        "exploitation",
        min_v=1,
        max_v=100,
        step=0.1,
    ),
    _f(
        "hotel_to_le_plus_haut_taux",
        "rate",
        "TO le plus haut (%)",
        "exploitation",
        min_v=1,
        max_v=100,
        step=0.1,
    ),
    # Rénovation / contrat
    _f(
        "hotel_contrat_signe_annee",
        "int",
        "Année signature contrat",
        "renovation",
        min_v=1950,
        max_v=2100,
        step=1,
    ),
    _f(
        "hotel_derniere_reno",
        "int",
        "Dernière rénovation (année)",
        "renovation",
        min_v=1950,
        max_v=2100,
        step=1,
    ),
    _f(
        "hotel_lobby_derniere_reno",
        "int",
        "Dernière rénovation lobby",
        "renovation",
        min_v=1950,
        max_v=2100,
        step=1,
    ),
    _f("hotel_contrat_type_franchise", "bool", "Contrat franchise", "renovation"),
    _f("hotel_contrat_type_manage", "bool", "Contrat managé", "renovation"),
    # F&B — restaurant = compteur ; bar = binaire (pas de double has_bar)
    _f(
        "hotel_f_b_restaurant",
        "int",
        "Nombre de restaurants",
        "fb",
        min_v=0,
        max_v=20,
        step=1,
        hint="Compteur (pas de case « a un restaurant » en plus)",
    ),
    _f("hotel_f_b_bar", "bool", "Bar", "fb", hint="Présence d’un bar (0/1 en base)"),
    _f("hotel_f_b_minibar", "bool", "Minibar", "fb"),
    _f("hotel_f_b_room_service", "bool", "Room service", "fb"),
    # Non F&B — salles réunion en compteur (pas hotel_has_reunion)
    _f("hotel_non_f_b_piscine", "bool", "Piscine", "nfb"),
    _f(
        "hotel_non_f_b_salle_de_sport",
        "int",
        "Salles de sport",
        "nfb",
        min_v=0,
        max_v=20,
        step=1,
    ),
    _f(
        "hotel_non_f_b_salles_de_reunion",
        "int",
        "Salles de réunion",
        "nfb",
        min_v=0,
        max_v=50,
        step=1,
        hint="Remplace l’indicateur binaire has_reunion",
    ),
    _f("hotel_non_f_b_spa", "bool", "Spa", "nfb"),
    # Confort
    _f("hotel_has_parking", "bool", "Parking", "comfort"),
    _f("hotel_has_wifi", "bool", "Wi‑Fi", "comfort"),
    _f("hotel_has_clim", "bool", "Climatisation", "comfort"),
    _f("hotel_has_petit_dejeuner", "bool", "Petit-déjeuner", "comfort"),
    _f("hotel_has_accessible", "bool", "Accessibilité PMR", "comfort"),
    _f("hotel_has_animaux", "bool", "Animaux acceptés", "comfort"),
    _f("hotel_has_non_fumeur", "bool", "Non-fumeur", "comfort"),
    _f("hotel_has_navette", "bool", "Navette", "comfort"),
    # Lobby
    _f("hotel_dispo_dans_lobby_assises", "bool", "Assises en lobby", "lobby"),
    _f("hotel_dispo_dans_lobby_bouilloire", "bool", "Bouilloire", "lobby"),
    _f("hotel_dispo_dans_lobby_fontaine_a_eau", "bool", "Fontaine à eau", "lobby"),
    _f("hotel_dispo_dans_lobby_machine_a_cafe", "bool", "Machine à café", "lobby"),
    _f("hotel_dispo_dans_lobby_micro_ondes", "bool", "Micro-ondes", "lobby"),
    _f(
        "hotel_dispo_dans_lobby_vitrine_refrigeree",
        "bool",
        "Vitrine réfrigérée",
        "lobby",
        hint="Si déjà présente, le coût vitrine n’est pas ajouté (Simply / Liberty)",
    ),
    # Clientèle
    _f(
        "hotel_affaires_pct",
        "rate",
        "Part clientèle affaires (%)",
        "clientele",
        min_v=0,
        max_v=100,
        step=1,
    ),
    _f(
        "hotel_loisirs_pct",
        "rate",
        "Part clientèle loisirs (%)",
        "clientele",
        min_v=0,
        max_v=100,
        step=1,
    ),
    _f(
        "hotel_national_pct",
        "rate",
        "Part clientèle nationale (%)",
        "clientele",
        min_v=0,
        max_v=100,
        step=1,
    ),
    _f(
        "hotel_international_pct",
        "rate",
        "Part clientèle internationale (%)",
        "clientele",
        min_v=0,
        max_v=100,
        step=1,
    ),
    _f("hotel_loisirs_top_1_amis", "bool", "Top loisirs · amis", "clientele"),
    _f("hotel_loisirs_top_1_couples", "bool", "Top loisirs · couples", "clientele"),
    _f("hotel_loisirs_top_1_familles", "bool", "Top loisirs · familles", "clientele"),
    # Corner actuel
    _f("hotel_corner_actuel_existe_deja", "bool", "Corner déjà en place", "corner"),
    _f(
        "hotel_metres_lineaires_dedies_corner",
        "int",
        "Mètres linéaires dédiés corner",
        "corner",
        min_v=0,
        max_v=40,
        step=1,
    ),
    _f(
        "hotel_corner_de_vente_actuel_metres_lineaires",
        "int",
        "ML corner actuel (si différent)",
        "corner",
        min_v=0,
        max_v=40,
        step=1,
    ),
    _f(
        "hotel_corner_actuel_offre_f_b_caisse_code_barres",
        "bool",
        "Offre F&B · caisse code-barres",
        "corner",
    ),
    _f(
        "hotel_corner_actuel_offre_f_b_distributeur_auto",
        "bool",
        "Offre F&B · distributeur auto",
        "corner",
    ),
    _f(
        "hotel_corner_actuel_offre_f_b_frigo_connecte",
        "bool",
        "Offre F&B · frigo connecté",
        "corner",
    ),
    _f(
        "hotel_corner_actuel_offre_f_b_reception",
        "bool",
        "Offre F&B · réception",
        "corner",
    ),
    _f(
        "hotel_corner_actuel_offre_f_b_snacking_comptoir",
        "bool",
        "Offre F&B · snacking comptoir",
        "corner",
    ),
    _f(
        "hotel_corner_actuel_offre_non_f_b_armoire_connectee",
        "bool",
        "Offre non F&B · armoire connectée",
        "corner",
    ),
    _f(
        "hotel_corner_actuel_offre_non_f_b_caisse_code_barres",
        "bool",
        "Offre non F&B · caisse code-barres",
        "corner",
    ),
    _f(
        "hotel_corner_actuel_offre_non_f_b_distributeur_auto",
        "bool",
        "Offre non F&B · distributeur auto",
        "corner",
    ),
    _f(
        "hotel_corner_actuel_offre_non_f_b_reception",
        "bool",
        "Offre non F&B · réception",
        "corner",
    ),
]


def field_by_id() -> dict[str, HotelFormField]:
    return {f.id: f for f in HOTEL_FORM_FIELDS}


def schema_for_api() -> dict[str, Any]:
    """Schéma JSON pour le front (sections + champs)."""
    sections: dict[str, dict[str, Any]] = {}
    for sid, lab in SECTIONS:
        sections[sid] = {"id": sid, "label": lab, "fields": []}
    for f in HOTEL_FORM_FIELDS:
        if f.section not in sections:
            sections[f.section] = {
                "id": f.section,
                "label": f.section_label,
                "fields": [],
            }
        sections[f.section]["fields"].append(
            {
                "id": f.id,
                "kind": f.kind,
                "label": f.label,
                "hint": f.hint,
                "min": f.min_v,
                "max": f.max_v,
                "step": f.step,
                "synthetic": f.synthetic,
            }
        )
    return {
        "sections": [sections[s] for s, _ in SECTIONS if sections[s]["fields"]],
        "fields": [x for s in sections.values() for x in s["fields"]],
        "skipped_redundant": sorted(REDUNDANT_COLS),
        "identity_excluded": sorted(IDENTITY_COLS),
        "solution_excluded": sorted(SOLUTION_COLS),
    }


def _load_hotel_df() -> pd.DataFrame:
    path = DATA_DIR / "hotel_data.xlsx"
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path)
    except Exception:
        return pd.DataFrame()


def _series_numeric(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _is_missing(v: Any) -> bool:
    if v is None or v == "":
        return True
    try:
        if isinstance(v, float) and pd.isna(v):
            return True
    except Exception:
        pass
    return False


def _majority_bool(s: pd.Series) -> bool:
    sn = _series_numeric(s).dropna()
    if sn.empty:
        return False
    # valeurs 0/1 (ou proches)
    vals = (sn > 0.5).astype(int)
    return bool(vals.mode().iloc[0] >= 1) if len(vals) else False


def _mean_num(s: pd.Series) -> float | None:
    sn = _series_numeric(s).dropna()
    if sn.empty:
        return None
    return float(sn.mean())


@lru_cache(maxsize=1)
def compute_global_defaults() -> dict[str, Any]:
    """
    Défauts population hotel_data :
    - bool → majorité (mode)
    - int/float/rate → moyenne
    """
    df = _load_hotel_df()
    out: dict[str, Any] = {}
    for f in HOTEL_FORM_FIELDS:
        if f.synthetic:
            continue
        if df.empty or f.id not in df.columns:
            out[f.id] = False if f.kind == "bool" else None
            continue
        col = df[f.id]
        if f.kind == "bool":
            out[f.id] = _majority_bool(col)
        else:
            m = _mean_num(col)
            if m is None:
                out[f.id] = None
            elif f.kind == "int":
                out[f.id] = int(round(m))
            elif f.kind == "rate":
                # stocké 0–1 en base souvent
                v = float(m)
                if v > 1.0:
                    v = v / 100.0
                out[f.id] = round(min(max(v, 0.0), 1.0), 4)
            else:
                out[f.id] = round(float(m), 4)

    # guests : pas en hotel_data → moyenne raisonnable
    out.setdefault("guests_per_chambre", 1.7)
    if out.get("hotel_nb_chambres") in (None, 0):
        out["hotel_nb_chambres"] = 100
    if out.get("hotel_to_annuel") is None:
        out["hotel_to_annuel"] = 0.70
    return out


def invalidate_defaults_cache() -> None:
    compute_global_defaults.cache_clear()


def extract_row_params(row: dict[str, Any] | pd.Series | None) -> dict[str, Any]:
    """Valeurs hotel_data pour une fiche (None si manquant)."""
    if row is None:
        return {f.id: None for f in HOTEL_FORM_FIELDS}
    if isinstance(row, pd.Series):
        data = row.to_dict()
    else:
        data = dict(row)
    out: dict[str, Any] = {}
    for f in HOTEL_FORM_FIELDS:
        if f.synthetic:
            out[f.id] = None
            continue
        raw = data.get(f.id)
        if _is_missing(raw):
            out[f.id] = None
            continue
        try:
            if f.kind == "bool":
                out[f.id] = bool(int(float(raw)) > 0)
            elif f.kind == "int":
                out[f.id] = int(round(float(raw)))
            elif f.kind == "rate":
                v = float(raw)
                if v > 1.0:
                    v = v / 100.0
                out[f.id] = round(min(max(v, 0.0), 1.0), 4)
            else:
                out[f.id] = float(raw)
        except (TypeError, ValueError):
            out[f.id] = None
    return out


def resolve_params(
    hotel_values: dict[str, Any] | None,
    user_values: dict[str, Any] | None = None,
    *,
    guests_fallback: float | None = None,
) -> dict[str, Any]:
    """
    Fusion : saisie user > valeur fiche hôtel > défaut global (majorité/moyenne).
    """
    defaults = compute_global_defaults()
    hotel_values = hotel_values or {}
    user_values = user_values or {}
    resolved: dict[str, Any] = {}
    for f in HOTEL_FORM_FIELDS:
        u = user_values.get(f.id)
        if not _is_missing(u):
            resolved[f.id] = _coerce(f, u)
            continue
        h = hotel_values.get(f.id)
        if not _is_missing(h):
            resolved[f.id] = _coerce(f, h)
            continue
        if f.id == "guests_per_chambre" and guests_fallback is not None:
            resolved[f.id] = float(guests_fallback)
            continue
        d = defaults.get(f.id)
        if d is None and f.kind == "bool":
            d = False
        if d is None and f.kind == "int":
            d = 0
        if d is None and f.kind in ("float", "rate"):
            d = 0.0 if f.kind == "float" else 0.7
        resolved[f.id] = d
    return resolved


def _coerce(f: HotelFormField, raw: Any) -> Any:
    if f.kind == "bool":
        if isinstance(raw, str):
            return raw.strip().lower() in ("1", "true", "yes", "oui", "on")
        try:
            return bool(int(float(raw)) > 0) if not isinstance(raw, bool) else raw
        except (TypeError, ValueError):
            return bool(raw)
    if f.kind == "int":
        try:
            return int(round(float(raw)))
        except (TypeError, ValueError):
            return 0
    if f.kind == "rate":
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return 0.0
        if v > 1.0:
            v = v / 100.0
        return min(max(v, 0.0), 1.0)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def params_to_services(params: dict[str, Any]) -> dict[str, Any]:
    """Mappe les colonnes hotel_* vers HotelServices / indicateurs legacy."""
    p = params or {}
    n_rest = int(p.get("hotel_f_b_restaurant") or 0)
    bar = bool(p.get("hotel_f_b_bar"))
    n_meet = int(p.get("hotel_non_f_b_salles_de_reunion") or 0)
    n_gym = int(p.get("hotel_non_f_b_salle_de_sport") or 0)
    vitrine = bool(p.get("hotel_dispo_dans_lobby_vitrine_refrigeree"))
    return {
        "bar": bar,
        "nb_bars": 1 if bar else 0,
        "restaurant": n_rest > 0,
        "nb_restaurants": n_rest,
        "room_service": bool(p.get("hotel_f_b_room_service")),
        "minibar": bool(p.get("hotel_f_b_minibar")),
        "meeting_rooms": n_meet > 0,
        "nb_meeting_rooms": n_meet,
        "gym": n_gym > 0,
        "nb_gym": n_gym,
        "spa": bool(p.get("hotel_non_f_b_spa")),
        "pool": bool(p.get("hotel_non_f_b_piscine")),
        "parking": bool(p.get("hotel_has_parking")),
        "wifi": bool(p.get("hotel_has_wifi")),
        "clim": bool(p.get("hotel_has_clim")),
        "breakfast": bool(p.get("hotel_has_petit_dejeuner")),
        "accessible": bool(p.get("hotel_has_accessible")),
        "pets": bool(p.get("hotel_has_animaux")),
        "non_smoking": bool(p.get("hotel_has_non_fumeur")),
        "shuttle": bool(p.get("hotel_has_navette")),
        "lobby_seating": bool(p.get("hotel_dispo_dans_lobby_assises")),
        "lobby_kettle": bool(p.get("hotel_dispo_dans_lobby_bouilloire")),
        "lobby_water": bool(p.get("hotel_dispo_dans_lobby_fontaine_a_eau")),
        "lobby_coffee": bool(p.get("hotel_dispo_dans_lobby_machine_a_cafe")),
        "lobby_microwave": bool(p.get("hotel_dispo_dans_lobby_micro_ondes")),
        "lobby_fridge": vitrine,
        "has_vitrine": vitrine,
        "has_pool": bool(p.get("hotel_non_f_b_piscine")),
        "corner_fb_caisse": bool(p.get("hotel_corner_actuel_offre_f_b_caisse_code_barres")),
        "corner_fb_distributeur": bool(
            p.get("hotel_corner_actuel_offre_f_b_distributeur_auto")
        ),
        "corner_fb_frigo": bool(p.get("hotel_corner_actuel_offre_f_b_frigo_connecte")),
        "corner_fb_reception": bool(p.get("hotel_corner_actuel_offre_f_b_reception")),
        "corner_fb_snacking": bool(
            p.get("hotel_corner_actuel_offre_f_b_snacking_comptoir")
        ),
        "corner_nfb_armoire": bool(
            p.get("hotel_corner_actuel_offre_non_f_b_armoire_connectee")
        ),
        "corner_nfb_caisse": bool(
            p.get("hotel_corner_actuel_offre_non_f_b_caisse_code_barres")
        ),
        "corner_nfb_distributeur": bool(
            p.get("hotel_corner_actuel_offre_non_f_b_distributeur_auto")
        ),
        "corner_nfb_reception": bool(p.get("hotel_corner_actuel_offre_non_f_b_reception")),
    }


def params_to_feature_overrides(params: dict[str, Any]) -> dict[str, Any]:
    """Colonnes model/hotel pour la prédiction IA."""
    out: dict[str, Any] = {}
    for f in HOTEL_FORM_FIELDS:
        if f.synthetic:
            continue
        v = params.get(f.id)
        if v is None:
            continue
        if f.kind == "bool":
            out[f.id] = 1 if v else 0
        else:
            out[f.id] = v
    # dérivés utiles
    if "hotel_non_f_b_salles_de_reunion" in params:
        out["hotel_has_reunion"] = (
            1 if int(params.get("hotel_non_f_b_salles_de_reunion") or 0) > 0 else 0
        )
    return out


def ui_display_value(f: HotelFormField, value: Any) -> Any:
    """Valeur prête pour l'input HTML (rates en %)."""
    if value is None:
        return ""
    if f.kind == "bool":
        return bool(value)
    if f.kind == "rate":
        v = float(value)
        if v <= 1.0:
            v *= 100.0
        return round(v, 1)
    if f.kind == "int":
        return int(round(float(value)))
    return value
