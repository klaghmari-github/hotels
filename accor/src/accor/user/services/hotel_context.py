"""
Contexte hôtel pour le simulateur ROD.

Rôle
----
À partir des données **admin** déjà gérées dans run_admin :

* ``hotel_data.xlsx`` — identité, chambres, TO, équipements, corner
* ``model_data.xlsx`` — agrégats mensuels réels (CA, ventes, mix %, holidays…)
* défauts marque (TO / guests) alignés archive FeatureImputer

on construit les **indicateurs d'entrée** du moteur ROD :

=============================  ================================================
Indicateur                     Source / règle
=============================  ================================================
nb_chambres                    hotel_data / model_data
taux_occupation                hotel_data (sinon défaut marque)
guests_per_chambre             défaut marque (IBB 1.7, …)
clients_mois                   n × TO × guests × 30.5  (REV-01/02)
mix_fb / mix_nf                moyenne ``pct_cat_*_nombre_ventes`` model_data
m_lin                          corner hôtel (sinon pilote concept)
client_needs                   sous-cat model_data (seuil de présence)
ca_historique_mensuel          moyenne ``montant_ventes`` model_data
ventes_historiques_mensuelles  moyenne ``nombre_ventes`` model_data
=============================  ================================================

Ces indicateurs alimentent les règles Excel (scaling clients, mix, m_lin).
Le CA **projeté** reste issu des pilotes ``rod_reference.json`` (pas une
copie du CA historique) — le CA historique est exposé pour contrôle.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from accor.data_io import DATA_DIR

# Aligné archive ``feature_imputer.BRAND_*``
BRAND_GUESTS_DEFAULT: dict[str, float] = {
    "IBIS BUDGET": 1.7,
    "IBIS STYLES": 2.0,
    "NOVOTEL": 1.8,
    "MERCURE": 2.0,
    "IBIS": 1.8,
}

BRAND_TO_DEFAULT: dict[str, float] = {
    "IBIS BUDGET": 0.78,
    "IBIS STYLES": 0.85,
    "NOVOTEL": 0.75,
    "MERCURE": 0.72,
    "IBIS": 0.80,
}

# model_data sous-cat → besoin client (Règle 3)
SOUS_CAT_TO_NEED: dict[str, str] = {
    "pct_sous_cat_sans_alcool_nombre_ventes": "fb_soft_drinks",
    "pct_sous_cat_alcool_nombre_ventes": "fb_alcohol",
    "pct_sous_cat_food_salee_nombre_ventes": "fb_salty_meals",
    "pct_sous_cat_food_sucree_nombre_ventes": "fb_sweet_snacks",
    "pct_sous_cat_sos_nombre_ventes": "nfb_sos",
    "pct_sous_cat_cosmetique_nombre_ventes": "nfb_cosmetics",
    "pct_sous_cat_jeux_enfants_nombre_ventes": "nfb_kids",
    "pct_sous_cat_pap_nombre_ventes": "nfb_apparel",
    "pct_sous_cat_accessoires_nombre_ventes": "nfb_accessories",
    "pct_sous_cat_souvenirs_nombre_ventes": "nfb_souvenirs",
}

# Seuil : sous-cat active si part moyenne > 1 %
NEED_PRESENCE_THRESHOLD = 0.01


def _norm_brand(brand: str) -> str:
    return (brand or "").strip().upper().replace("_", " ")


def _as_rate(value: Any, default: float) -> float:
    """Normalise un taux (0–1 ou 0–100) vers [0, 1]."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v > 1.0:
        v = v / 100.0
    return min(max(v, 0.0), 1.0)


def _as_float(value: Any, default: float | None = None) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    f = _as_float(value, None)
    if f is None:
        return default
    return int(round(f))


@dataclass
class HotelContext:
    """Profil prêt pour préremplir le wizard + lancer le simulateur."""

    hotel_code: str
    identity: dict[str, Any] = field(default_factory=dict)
    operating: dict[str, Any] = field(default_factory=dict)
    services: dict[str, Any] = field(default_factory=dict)
    client_profile: dict[str, Any] = field(default_factory=dict)
    corner: dict[str, Any] = field(default_factory=dict)
    # Indicateurs calculés (model_data + dérivés)
    indicators: dict[str, Any] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_simulation_payload(self) -> dict[str, Any]:
        """Payload JSON compatible ``SimulationRequest.from_dict``."""
        return {
            "identity": self.identity,
            "operating": self.operating,
            "services": self.services,
            "client_profile": self.client_profile,
            "corner": self.corner,
            "indicators": self.indicators,
        }


class HotelContextBuilder:
    """Agrège hotel_data + model_data → contexte simulateur."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or DATA_DIR
        self._hotels: pd.DataFrame | None = None
        self._model: pd.DataFrame | None = None

    def invalidate(self) -> None:
        """Recharge hotel_data / model_data au prochain acces."""
        self._hotels = None
        self._model = None

    def _load_hotels(self) -> pd.DataFrame:
        if self._hotels is not None:
            return self._hotels
        path = self.data_dir / "hotel_data.xlsx"
        if not path.exists():
            self._hotels = pd.DataFrame()
            return self._hotels
        self._hotels = pd.read_excel(path, sheet_name=0, dtype={"hotel_code": str})
        return self._hotels

    def _load_model(self) -> pd.DataFrame:
        if self._model is not None:
            return self._model
        path = self.data_dir / "model_data.xlsx"
        if not path.exists():
            self._model = pd.DataFrame()
            return self._model
        try:
            self._model = pd.read_excel(path, sheet_name="model_data")
        except ValueError:
            self._model = pd.read_excel(path, sheet_name=0)
        return self._model

    def list_hotel_codes(self) -> list[str]:
        h = self._load_hotels()
        if h.empty or "hotel_code" not in h.columns:
            return []
        return [str(c).strip() for c in h["hotel_code"].dropna().unique()]

    def build(
        self,
        hotel_code: str,
        *,
        fetch_if_missing: bool = True,
        persist_scrape: bool = False,
        session_row: dict[str, Any] | None = None,
    ) -> HotelContext:
        code = str(hotel_code or "").strip()
        warnings: list[str] = []
        sources: dict[str, str] = {}
        scraped_meta: dict[str, Any] = {}

        hotels = self._load_hotels()
        model = self._load_model()

        row: dict[str, Any] = {}
        if not hotels.empty and "hotel_code" in hotels.columns:
            codes = hotels["hotel_code"].astype(str).str.strip()
            match = hotels[codes.str.upper() == code.upper()]
            if match.empty:
                # variantes H / pad
                from accor.user.services.hotel_fetch import code_variants

                for v in code_variants(code):
                    match = hotels[codes.str.upper() == v.upper()]
                    if not match.empty:
                        code = str(match.iloc[0]["hotel_code"]).strip()
                        break
            if not match.empty:
                row = match.iloc[0].to_dict()
                sources["identity"] = "hotel_data.xlsx"
            else:
                warnings.append(f"Code {code} absent de hotel_data.")
        else:
            warnings.append("hotel_data.xlsx vide ou introuvable.")

        # Ligne fournie par la session navigateur (jamais écrite en base)
        if not row and session_row:
            row = dict(session_row)
            code = str(row.get("hotel_code") or code).strip()
            sources["identity"] = "session"
            scraped_meta = {
                "scraped": bool(session_row.get("_scraped")),
                "session_only": True,
                "hotel_code": code,
            }

        # Hôtel inconnu → scrape Accor (défaut user : mémoire seule, pas d'Excel)
        if not row and fetch_if_missing and code:
            try:
                from accor.user.services.hotel_fetch import (
                    fetch_and_upsert_hotel,
                    fetch_hotel_session,
                )

                if persist_scrape:
                    fetched = fetch_and_upsert_hotel(code, persist=True)
                else:
                    fetched = fetch_hotel_session(code)

                if fetched.get("ok") and fetched.get("scraped") and fetched.get("row"):
                    row = dict(fetched["row"])
                    code = str(fetched.get("hotel_code") or row.get("hotel_code") or code).strip()
                    sources["identity"] = (
                        "all.accor.com (scrape+fichier)"
                        if persist_scrape
                        else "all.accor.com (session)"
                    )
                    scraped_meta = {
                        "scraped": True,
                        "session_only": not persist_scrape,
                        "persisted": bool(fetched.get("persisted")),
                        "url": fetched.get("url"),
                        "hotel_code": code,
                    }
                    if persist_scrape:
                        self.invalidate()
                        warnings.append(
                            f"Hôtel {code} récupéré depuis all.accor.com et ajouté à hotel_data."
                        )
                    else:
                        warnings.append(
                            f"Hôtel {code} récupéré depuis all.accor.com."
                        )
                elif fetched.get("ok") and not fetched.get("scraped"):
                    code = str(fetched.get("hotel_code") or code).strip()
                    self.invalidate()
                    hotels = self._load_hotels()
                    if not hotels.empty:
                        codes = hotels["hotel_code"].astype(str).str.strip()
                        match = hotels[codes.str.upper() == code.upper()]
                        if not match.empty:
                            row = match.iloc[0].to_dict()
                            sources["identity"] = "hotel_data.xlsx"
                elif not fetched.get("ok"):
                    warnings.append(
                        fetched.get("error")
                        or f"Scrape Accor échoué pour {code}."
                    )
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Scrape Accor indisponible : {exc}")

        if not row:
            warnings.append(f"Fallback model_data pour {code}.")

        # Agrégats model_data pour cet hôtel
        md_stats: dict[str, Any] = {}
        md_sub = pd.DataFrame()
        if not model.empty and "hotel_code" in model.columns:
            md_sub = model[model["hotel_code"].astype(str).str.strip() == code]
            if not md_sub.empty:
                sources["sales_mix"] = "model_data.xlsx"
                md_stats = self._aggregate_model(md_sub)
                # Complète identité si manquante
                if not row:
                    r0 = md_sub.iloc[0]
                    row = {
                        "hotel_code": code,
                        "hotel_name": r0.get("hotel_name") or r0.get("nom_hotel"),
                        "hotel_brand": r0.get("hotel_brand"),
                        "hotel_lat": r0.get("hotel_lat"),
                        "hotel_lon": r0.get("hotel_lon"),
                        "hotel_city": r0.get("hotel_city"),
                        "hotel_adresse_postale_1": r0.get("hotel_adresse_postale_1"),
                        "hotel_adresse_postale_2": r0.get("hotel_adresse_postale_2"),
                        "hotel_code_postal": r0.get("hotel_code_postal"),
                        "hotel_nb_chambres": r0.get("hotel_nb_chambres"),
                        "hotel_to_annuel": r0.get("hotel_to_annuel"),
                    }
                    sources["identity"] = "model_data.xlsx"
            else:
                warnings.append(f"Aucune ligne model_data pour {code}.")
        else:
            warnings.append("model_data.xlsx vide ou introuvable.")

        brand = str(row.get("hotel_brand") or md_stats.get("hotel_brand") or "").strip()
        brand_key = _norm_brand(brand)

        # Categorie de marque (economy / midscale / …) pour imputation pilotes
        from accor.brand_category import brand_to_category_map, mean_for_category

        brand_cat = brand_to_category_map().get(brand_key)
        if brand_cat is None and any(
            str(row.get(f"cat_{c}") or 0) in {"1", "1.0"} or row.get(f"cat_{c}") == 1
            for c in (
                "economy",
                "midscale",
                "premium",
                "luxury",
                "lifestyle_by_ennismore",
                "partner_brands",
            )
        ):
            from accor.brand_category import category_from_dummies

            brand_cat = category_from_dummies(row)
        sources["brand_category"] = brand_cat or ""

        # Series de reference pilotes (hotel_data × ventes) pour moyennes categorie
        def _pilot_feature_mean(col: str) -> tuple[float | None, str]:
            try:
                hotels_df = self._load_hotels()
                from accor.brand_category import (
                    pilot_hotel_codes,
                    resolve_category_series,
                )

                if hotels_df.empty or col not in hotels_df.columns:
                    return None, "none"
                codes = hotels_df["hotel_code"].astype(str).str.strip()
                pilots = pilot_hotel_codes()
                pmask = codes.isin(pilots) if pilots else pd.Series(True, index=hotels_df.index)
                cats = resolve_category_series(hotels_df)
                return mean_for_category(
                    hotels_df[col], cats, pmask, brand_cat
                )
            except Exception:
                return None, "none"

        # --- Operating (entrées REV-01/02) ---
        nb_chambres = _as_int(
            row.get("hotel_nb_chambres") or md_stats.get("hotel_nb_chambres"), 0
        )
        if nb_chambres <= 0:
            cat_val, cat_src = _pilot_feature_mean("hotel_nb_chambres")
            if cat_val is not None and cat_val > 0:
                nb_chambres = int(round(cat_val))
                sources["nb_chambres"] = cat_src
                warnings.append(
                    f"nb_chambres impute par moyenne pilotes ({cat_src}) = {nb_chambres}."
                )
            else:
                warnings.append("nb_chambres manquant — imputation 80.")
                nb_chambres = 80
                sources["nb_chambres"] = "default"
        else:
            sources["nb_chambres"] = sources.get("identity", "hotel_data")

        to_default = BRAND_TO_DEFAULT.get(brand_key, 0.70)
        to_raw = row.get("hotel_to_annuel")
        if to_raw is None or (isinstance(to_raw, float) and pd.isna(to_raw)):
            to_raw = md_stats.get("hotel_to_annuel")
            if to_raw is not None:
                sources["taux_occupation"] = "model_data"
            else:
                cat_val, cat_src = _pilot_feature_mean("hotel_to_annuel")
                if cat_val is not None:
                    to_raw = cat_val
                    sources["taux_occupation"] = cat_src
                    warnings.append(
                        f"TO impute par moyenne pilotes ({cat_src})."
                    )
                else:
                    sources["taux_occupation"] = f"brand_default:{brand_key or 'AUTRE'}"
        else:
            sources["taux_occupation"] = "hotel_data"
        taux_occupation = _as_rate(to_raw, to_default)

        guests_default = BRAND_GUESTS_DEFAULT.get(brand_key, 1.7)
        guests = guests_default
        sources["guests_per_chambre"] = f"brand_default:{brand_key or 'AUTRE'}"
        # hotel_data n'a pas de guests : tenter moyenne marque concept_pilote
        if brand:
            try:
                from accor.concept_pilote import brand_step1_averages

                bp = brand_step1_averages(brand)
                g_bp = (bp.get("averages") or {}).get("guests_per_chambre")
                if bp.get("ok") and g_bp is not None and float(g_bp) > 0:
                    guests = float(g_bp)
                    sources["guests_per_chambre"] = "concept_pilote_brand"
            except Exception:
                pass

        clients_jour = nb_chambres * taux_occupation * guests
        clients_mois = clients_jour * 30.5

        # --- Mix F&B (Règle 2) ---
        mix_fb = md_stats.get("mix_fb")
        mix_nf = md_stats.get("mix_nf")
        if mix_fb is not None and mix_nf is not None and (mix_fb + mix_nf) > 0:
            total = mix_fb + mix_nf
            mix_fb, mix_nf = mix_fb / total, mix_nf / total
            sources["mix"] = "model_data pct_cat_*_nombre_ventes"
        else:
            mix_fb, mix_nf = None, None  # orchestrateur → pilote concept
            sources["mix"] = "concept_pilot_default"

        # --- Client needs (Règle 3) ---
        client_needs = md_stats.get("client_needs") or {}
        if not client_needs:
            # tout actif sauf hygiène / alcool par défaut ROD
            from accor.user.models import DEFAULT_CLIENT_NEEDS

            client_needs = dict(DEFAULT_CLIENT_NEEDS)
            sources["client_needs"] = "default_rod"
        else:
            sources["client_needs"] = "model_data sous-cat > 1%"

        # --- Corner / m_lin (Règle 4) ---
        m_lin = _as_float(row.get("hotel_metres_lineaires_dedies_corner"), None)
        if m_lin is None:
            m_lin = _as_float(row.get("hotel_corner_de_vente_actuel_metres_lineaires"), None)
        has_corner = bool(
            _as_int(row.get("hotel_corner_actuel_existe_deja"), 0)
            or (m_lin is not None and m_lin > 0)
        )
        if m_lin is not None:
            sources["m_lin"] = "hotel_data corner"
        else:
            sources["m_lin"] = "concept_pilot_default"

        # Préférer model_data (si hôtel connu) pour les attributs hôteliers UI / IA
        def _pref(col: str, default: Any = None) -> Any:
            """Valeur model_data d'abord, sinon hotel_data."""
            if col in md_stats and md_stats.get(col) is not None:
                return md_stats.get(col)
            if row.get(col) is not None and not (
                isinstance(row.get(col), float) and pd.isna(row.get(col))
            ):
                return row.get(col)
            return default

        derniere_reno = _as_int(_pref("hotel_derniere_reno"), 0) or None
        if derniere_reno is not None and (derniere_reno < 1950 or derniere_reno > 2100):
            derniere_reno = None
        nb_restaurants = max(0, _as_int(_pref("hotel_f_b_restaurant"), 0))
        nb_bars = max(0, _as_int(_pref("hotel_f_b_bar"), 0))
        has_pool = bool(_as_int(_pref("hotel_non_f_b_piscine"), 0))
        has_vitrine = bool(
            _as_int(_pref("hotel_dispo_dans_lobby_vitrine_refrigeree"), 0)
        )
        if md_stats.get("hotel_derniere_reno") is not None:
            sources["derniere_reno"] = "model_data"
        elif row.get("hotel_derniere_reno") is not None:
            sources["derniere_reno"] = "hotel_data"
        else:
            sources["derniere_reno"] = "empty"

        # --- Services ---
        services = {
            # F&B (bool + compteurs exposés aussi dans operating)
            "bar": nb_bars > 0,
            "restaurant": nb_restaurants > 0,
            "nb_bars": nb_bars,
            "nb_restaurants": nb_restaurants,
            "room_service": bool(_as_int(_pref("hotel_f_b_room_service"), 0)),
            "minibar": bool(_as_int(_pref("hotel_f_b_minibar"), 0)),
            # Non F&B
            "meeting_rooms": bool(
                _as_int(row.get("hotel_non_f_b_salles_de_reunion"), 0)
                or _as_int(row.get("hotel_has_reunion"), 0)
            ),
            "gym": bool(_as_int(row.get("hotel_non_f_b_salle_de_sport"), 0)),
            "spa": bool(_as_int(row.get("hotel_non_f_b_spa"), 0)),
            "pool": has_pool,
            # Confort / access (hotel_has_*)
            "parking": bool(_as_int(row.get("hotel_has_parking"), 0)),
            "wifi": bool(_as_int(row.get("hotel_has_wifi"), 0)),
            "clim": bool(_as_int(row.get("hotel_has_clim"), 0)),
            "breakfast": bool(_as_int(row.get("hotel_has_petit_dejeuner"), 0)),
            "accessible": bool(_as_int(row.get("hotel_has_accessible"), 0)),
            "pets": bool(_as_int(row.get("hotel_has_animaux"), 0)),
            "non_smoking": bool(_as_int(row.get("hotel_has_non_fumeur"), 0)),
            "shuttle": bool(_as_int(row.get("hotel_has_navette"), 0)),
            # Lobby
            "lobby_fridge": has_vitrine,
            "has_vitrine": has_vitrine,
            "lobby_microwave": bool(
                _as_int(row.get("hotel_dispo_dans_lobby_micro_ondes"), 0)
            ),
            "lobby_water": bool(
                _as_int(row.get("hotel_dispo_dans_lobby_fontaine_a_eau"), 0)
            ),
            "lobby_coffee": bool(
                _as_int(row.get("hotel_dispo_dans_lobby_machine_a_cafe"), 0)
            ),
            "lobby_kettle": bool(
                _as_int(row.get("hotel_dispo_dans_lobby_bouilloire"), 0)
            ),
            "lobby_seating": bool(
                _as_int(row.get("hotel_dispo_dans_lobby_assises"), 0)
            ),
            # Offres corner actuel (pour etape boutique)
            "corner_fb_caisse": bool(
                _as_int(row.get("hotel_corner_actuel_offre_f_b_caisse_code_barres"), 0)
            ),
            "corner_fb_distributeur": bool(
                _as_int(row.get("hotel_corner_actuel_offre_f_b_distributeur_auto"), 0)
            ),
            "corner_fb_frigo": bool(
                _as_int(row.get("hotel_corner_actuel_offre_f_b_frigo_connecte"), 0)
            ),
            "corner_fb_reception": bool(
                _as_int(row.get("hotel_corner_actuel_offre_f_b_reception"), 0)
            ),
            "corner_fb_snacking": bool(
                _as_int(row.get("hotel_corner_actuel_offre_f_b_snacking_comptoir"), 0)
            ),
            "corner_nfb_armoire": bool(
                _as_int(row.get("hotel_corner_actuel_offre_non_f_b_armoire_connectee"), 0)
            ),
            "corner_nfb_caisse": bool(
                _as_int(row.get("hotel_corner_actuel_offre_non_f_b_caisse_code_barres"), 0)
            ),
            "corner_nfb_distributeur": bool(
                _as_int(row.get("hotel_corner_actuel_offre_non_f_b_distributeur_auto"), 0)
            ),
            "corner_nfb_reception": bool(
                _as_int(row.get("hotel_corner_actuel_offre_non_f_b_reception"), 0)
            ),
        }

        # Profil clients (% — hotel_data peut être fraction ou %)
        loisirs = _as_rate(row.get("hotel_loisirs_pct"), 0.30)
        affaires = _as_rate(row.get("hotel_affaires_pct"), 0.70)
        # si les deux sont renseignés mais absurdes (ex. 10.2 et 0), renormalise
        if loisirs + affaires > 0 and loisirs + affaires != 1.0:
            # si valeurs > 1 déjà gérées ; si une seule dominante
            if loisirs + affaires > 1.5:
                # probablement mal scalé (ex. 10.2 + 0) → ignore, défauts
                loisirs, affaires = 0.30, 0.70
            else:
                s = loisirs + affaires
                loisirs, affaires = loisirs / s, affaires / s
        national = _as_rate(row.get("hotel_national_pct"), 0.60)
        international = _as_rate(row.get("hotel_international_pct"), 0.40)
        if national + international > 0:
            s = national + international
            if s > 1.5:
                national, international = 0.60, 0.40
            else:
                national, international = national / s, international / s

        identity = {
            "hotel_code": code or str(row.get("hotel_code") or ""),
            "hotel_name": str(row.get("hotel_name") or row.get("nom_hotel") or "").strip(),
            "hotel_brand": brand,
            "hotel_lat": _as_float(row.get("hotel_lat")),
            "hotel_lon": _as_float(row.get("hotel_lon")),
            "hotel_adresse_postale_1": str(row.get("hotel_adresse_postale_1") or "").strip(),
            "hotel_adresse_postale_2": str(row.get("hotel_adresse_postale_2") or "").strip()
            if row.get("hotel_adresse_postale_2") is not None
            and not (isinstance(row.get("hotel_adresse_postale_2"), float) and pd.isna(row.get("hotel_adresse_postale_2")))
            else "",
            "hotel_code_postal": str(row.get("hotel_code_postal") or "").replace(".0", ""),
            "hotel_city": str(row.get("hotel_city") or "").strip(),
        }

        indicators = {
            "nb_chambres": nb_chambres,
            "taux_occupation": taux_occupation,
            "guests_per_chambre": guests,
            "clients_jour": round(clients_jour, 2),
            "clients_mois": round(clients_mois, 2),
            "mix_fb": mix_fb,
            "mix_nf": mix_nf,
            "m_lin": m_lin,
            "derniere_reno": derniere_reno,
            "nb_restaurants": nb_restaurants,
            "nb_bars": nb_bars,
            "has_pool": has_pool,
            "has_vitrine": has_vitrine,
            "ca_historique_mensuel": md_stats.get("ca_historique_mensuel"),
            "ventes_historiques_mensuelles": md_stats.get("ventes_historiques_mensuelles"),
            "n_months_model_data": md_stats.get("n_months", 0),
            "pct_jours_holidays_mean": md_stats.get("pct_jours_holidays_mean"),
            "meteo_temperature_c_mean": md_stats.get("meteo_temperature_c_mean"),
            "brand_key": brand_key,
        }

        if scraped_meta:
            sources["scrape"] = scraped_meta

        return HotelContext(
            hotel_code=code,
            identity=identity,
            operating={
                "nb_chambres": nb_chambres,
                "taux_occupation": taux_occupation,
                "guests_per_chambre": guests,
                "clients_jour": clients_jour,
                "clients_mois": clients_mois,
                "derniere_reno": derniere_reno,
                "nb_restaurants": nb_restaurants,
                "nb_bars": nb_bars,
                "has_pool": has_pool,
                "has_vitrine": has_vitrine,
            },
            services=services,
            client_profile={
                "loisirs_pct": loisirs,
                "affaires_pct": affaires,
                "national_pct": national,
                "international_pct": international,
                "client_needs": client_needs,
            },
            corner={
                "has_corner": has_corner,
                "m_lin": m_lin,
                "mix_fb": mix_fb,
            },
            indicators=indicators,
            sources=sources,
            warnings=warnings,
        )

    def _aggregate_model(self, frame: pd.DataFrame) -> dict[str, Any]:
        """Moyennes mensuelles et mix à partir des lignes model_data d'un hôtel."""
        out: dict[str, Any] = {"n_months": int(len(frame))}

        def mean_col(col: str) -> float | None:
            if col not in frame.columns:
                return None
            s = pd.to_numeric(frame[col], errors="coerce").dropna()
            return float(s.mean()) if not s.empty else None

        out["ca_historique_mensuel"] = mean_col("montant_ventes")
        out["ventes_historiques_mensuelles"] = mean_col("nombre_ventes")
        out["hotel_nb_chambres"] = mean_col("hotel_nb_chambres")
        out["hotel_to_annuel"] = mean_col("hotel_to_annuel")
        out["pct_jours_holidays_mean"] = mean_col("pct_jours_holidays")
        out["meteo_temperature_c_mean"] = mean_col("meteo_temperature_c_mean")

        mix_fb = mean_col("pct_cat_f_b_nombre_ventes")
        mix_nf = mean_col("pct_cat_n_f_b_nombre_ventes")
        # parfois les % ne somment pas à 1 (mois partiels) → on les garde relatifs
        out["mix_fb"] = mix_fb
        out["mix_nf"] = mix_nf

        if "hotel_brand" in frame.columns:
            out["hotel_brand"] = str(frame["hotel_brand"].iloc[0] or "")

        # Attributs hôteliers (souvent constants sur les mois) — source model_data
        def first_num(col: str) -> float | None:
            if col not in frame.columns:
                return None
            s = pd.to_numeric(frame[col], errors="coerce").dropna()
            if s.empty:
                return None
            return float(s.iloc[0])

        out["hotel_derniere_reno"] = first_num("hotel_derniere_reno")
        out["hotel_lobby_derniere_reno"] = first_num("hotel_lobby_derniere_reno")
        out["hotel_f_b_restaurant"] = first_num("hotel_f_b_restaurant")
        out["hotel_f_b_bar"] = first_num("hotel_f_b_bar")
        out["hotel_non_f_b_piscine"] = first_num("hotel_non_f_b_piscine")
        out["hotel_dispo_dans_lobby_vitrine_refrigeree"] = first_num(
            "hotel_dispo_dans_lobby_vitrine_refrigeree"
        )
        out["hotel_f_b_minibar"] = first_num("hotel_f_b_minibar")
        out["hotel_f_b_room_service"] = first_num("hotel_f_b_room_service")

        needs: dict[str, bool] = {}
        for col, need_id in SOUS_CAT_TO_NEED.items():
            m = mean_col(col)
            if m is None:
                continue
            needs[need_id] = m >= NEED_PRESENCE_THRESHOLD
        # besoins sans colonne dédiée : défauts raisonnables
        if needs:
            needs.setdefault("fb_salty_snacks", needs.get("fb_salty_meals", False))
            needs.setdefault("fb_sweet_desserts", needs.get("fb_sweet_snacks", False))
            needs.setdefault("fb_gourmet", needs.get("fb_salty_meals", False))
            needs.setdefault("nfb_hygiene", False)
        out["client_needs"] = needs
        return out
