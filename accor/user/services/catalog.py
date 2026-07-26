"""
Catalogue lecture seule depuis les datasets admin (``accor/data/*.xlsx``).

* Marques → ``hotel_brand_data.xlsx`` (pas de saisie user)
* Hôtels  → ``hotel_data.xlsx`` (préremplissage du wizard)
* Stats model_data → valeurs par défaut / moyennes de référence
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from data_io import DATA_DIR, cell_to_python, read_excel as _read_excel_path


def _read_excel(name: str, sheet: str | int = 0) -> pd.DataFrame:
    return _read_excel_path(DATA_DIR / name, sheet=sheet)


class AdminCatalog:
    """Accès aux données déjà saisies par l'admin."""

    def __init__(self) -> None:
        self._hotels_cache: list[dict[str, Any]] | None = None
        self._hotels_mtime: float | None = None

    def _hotel_path(self) -> Path:
        return DATA_DIR / "hotel_data.xlsx"

    def invalidate_hotels(self) -> None:
        self._hotels_cache = None
        self._hotels_mtime = None

    def list_brands(self) -> list[dict[str, Any]]:
        """
        Marques depuis ``hotel_brand_data.xlsx`` (colonne ``Marque``).

        Complété par les ``hotel_brand`` distincts de ``hotel_data`` si
        une marque y figure sans être dans le fichier brand.
        """
        frame = _read_excel("hotel_brand_data.xlsx")
        out: list[dict[str, Any]] = []
        seen: set[str] = set()

        if not frame.empty:
            # colonne Marque (schéma admin) ou variantes
            col = None
            for candidate in ("Marque", "marque", "brand", "hotel_brand"):
                if candidate in frame.columns:
                    col = candidate
                    break
            if col is None:
                col = frame.columns[0]
            for _, row in frame.iterrows():
                name = str(row.get(col) or "").strip()
                if not name or name.lower() in {"nan", "none"}:
                    continue
                key = name.upper()
                if key in seen:
                    continue
                seen.add(key)
                item: dict[str, Any] = {"brand": name, "Marque": name}
                for c in frame.columns:
                    if c == col:
                        continue
                    val = row.get(c)
                    if pd.isna(val):
                        continue
                    item[str(c)] = val.item() if hasattr(val, "item") else val
                out.append(item)

        # Union avec hotel_data (au cas où)
        hotels = _read_excel("hotel_data.xlsx")
        if not hotels.empty and "hotel_brand" in hotels.columns:
            for raw in hotels["hotel_brand"].dropna().unique():
                name = str(raw).strip()
                if not name or name.lower() in {"nan", "none"}:
                    continue
                key = name.upper()
                if key in seen:
                    continue
                seen.add(key)
                out.append({"brand": name, "Marque": name, "source": "hotel_data"})

        out.sort(key=lambda x: str(x.get("brand") or "").upper())
        return out

    # Colonnes utiles pour le wizard (identite + exploitation + equipements)
    _HOTEL_COLS = [
        "hotel_code",
        "hotel_name",
        "hotel_brand",
        "hotel_lat",
        "hotel_lon",
        "hotel_adresse_postale_1",
        "hotel_adresse_postale_2",
        "hotel_code_postal",
        "hotel_city",
        "hotel_country",
        "hotel_nb_chambres",
        "hotel_to_annuel",
        "hotel_to_le_plus_bas_taux",
        "hotel_to_le_plus_haut_taux",
        "hotel_affaires_pct",
        "hotel_loisirs_pct",
        "hotel_international_pct",
        "hotel_national_pct",
        "hotel_loisirs_top_1_amis",
        "hotel_loisirs_top_1_couples",
        "hotel_loisirs_top_1_familles",
        # F&B
        "hotel_f_b_bar",
        "hotel_f_b_restaurant",
        "hotel_f_b_minibar",
        "hotel_f_b_room_service",
        # Non F&B
        "hotel_non_f_b_piscine",
        "hotel_non_f_b_salle_de_sport",
        "hotel_non_f_b_spa",
        "hotel_non_f_b_salles_de_reunion",
        # Confort / access
        "hotel_has_parking",
        "hotel_has_wifi",
        "hotel_has_clim",
        "hotel_has_petit_dejeuner",
        "hotel_has_accessible",
        "hotel_has_animaux",
        "hotel_has_non_fumeur",
        "hotel_has_navette",
        "hotel_has_reunion",
        # Lobby
        "hotel_dispo_dans_lobby_assises",
        "hotel_dispo_dans_lobby_bouilloire",
        "hotel_dispo_dans_lobby_fontaine_a_eau",
        "hotel_dispo_dans_lobby_machine_a_cafe",
        "hotel_dispo_dans_lobby_micro_ondes",
        "hotel_dispo_dans_lobby_vitrine_refrigeree",
        # Corner
        "hotel_corner_actuel_existe_deja",
        "hotel_metres_lineaires_dedies_corner",
        "hotel_corner_de_vente_actuel_metres_lineaires",
        "hotel_corner_actuel_offre_f_b_caisse_code_barres",
        "hotel_corner_actuel_offre_f_b_distributeur_auto",
        "hotel_corner_actuel_offre_f_b_frigo_connecte",
        "hotel_corner_actuel_offre_f_b_reception",
        "hotel_corner_actuel_offre_f_b_snacking_comptoir",
        "hotel_corner_actuel_offre_non_f_b_armoire_connectee",
        "hotel_corner_actuel_offre_non_f_b_caisse_code_barres",
        "hotel_corner_actuel_offre_non_f_b_distributeur_auto",
        "hotel_corner_actuel_offre_non_f_b_reception",
        "hotel_contrat_type_franchise",
        "hotel_contrat_type_manage",
    ]

    def list_hotels(self, *, force: bool = False) -> list[dict[str, Any]]:
        path = self._hotel_path()
        mtime = path.stat().st_mtime if path.exists() else None
        if (
            not force
            and self._hotels_cache is not None
            and self._hotels_mtime == mtime
        ):
            return self._hotels_cache

        frame = _read_excel("hotel_data.xlsx")
        if frame.empty:
            self._hotels_cache = []
            self._hotels_mtime = mtime
            return []

        present = [c for c in self._HOTEL_COLS if c in frame.columns]
        # garder aussi toute autre colonne hotel_* (future-proof)
        for c in frame.columns:
            if str(c).startswith("hotel_") and c not in present:
                present.append(c)

        out: list[dict[str, Any]] = []
        for _, row in frame.iterrows():
            item: dict[str, Any] = {
                str(c): cell_to_python(row.get(c)) for c in present
            }
            code = str(item.get("hotel_code") or "").strip()
            name = str(item.get("hotel_name") or "").strip()
            if code or name:
                if code:
                    item["hotel_code"] = code
                out.append(item)

        self._hotels_cache = out
        self._hotels_mtime = mtime
        return out

    def search_hotels(self, query: str, *, limit: int = 25) -> list[dict[str, Any]]:
        """
        Autocomplete : code, nom, ville, marque (hotel_data).

        Retourne un resume leger pour la liste + champs d affiche.
        """
        q = str(query or "").strip().lower()
        if len(q) < 1:
            return []
        limit = max(1, min(int(limit or 25), 50))
        hotels = self.list_hotels()
        scored: list[tuple[int, dict[str, Any]]] = []
        q_compact = q.replace(" ", "")
        for h in hotels:
            code = str(h.get("hotel_code") or "").strip()
            name = str(h.get("hotel_name") or "").strip()
            city = str(h.get("hotel_city") or "").strip()
            brand = str(h.get("hotel_brand") or "").strip()
            code_l = code.lower()
            name_l = name.lower()
            city_l = city.lower()
            brand_l = brand.lower()
            score = 0
            if code_l == q or code_l == q_compact:
                score = 100
            elif code_l.startswith(q) or code_l.startswith(q_compact):
                score = 90
            elif q in code_l:
                score = 70
            elif name_l.startswith(q):
                score = 80
            elif q in name_l:
                score = 60
            elif q in city_l:
                score = 40
            elif q in brand_l:
                score = 30
            else:
                continue
            scored.append(
                (
                    score,
                    {
                        "hotel_code": code,
                        "hotel_name": name,
                        "hotel_brand": brand,
                        "hotel_city": city,
                        "hotel_code_postal": h.get("hotel_code_postal"),
                        "hotel_country": h.get("hotel_country"),
                        "label": f"{code} — {name}" if code and name else (code or name),
                    },
                )
            )
        scored.sort(key=lambda x: (-x[0], str(x[1].get("hotel_name") or "")))
        return [item for _, item in scored[:limit]]

    def get_hotel(self, hotel_code: str) -> dict[str, Any] | None:
        code = str(hotel_code or "").strip().upper()
        code_alt = code[1:] if code.startswith("H") else f"H{code}"
        for h in self.list_hotels():
            hc = str(h.get("hotel_code") or "").strip().upper()
            if hc == code or hc == code_alt:
                return h
        return None

    def model_defaults(self) -> dict[str, Any]:
        """Moyennes issues de model_data (référence descriptive)."""
        frame = _read_excel("model_data.xlsx", sheet="model_data")
        if frame.empty:
            return {}
        out: dict[str, Any] = {"n_rows": len(frame)}
        for col in (
            "hotel_nb_chambres",
            "hotel_to_annuel",
            "nb_jours_holidays",
            "pct_jours_holidays",
            "meteo_temperature_c_mean",
            "plage_distance_km",
        ):
            if col in frame.columns:
                s = pd.to_numeric(frame[col], errors="coerce")
                out[f"mean_{col}"] = float(s.mean()) if s.notna().any() else None
        return out
