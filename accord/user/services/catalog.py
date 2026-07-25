"""
Catalogue lecture seule depuis les datasets **admin** (``accord/data/*.xlsx``).

* Marques → ``hotel_brand_data.xlsx`` (pas de saisie user)
* Hôtels  → ``hotel_data.xlsx`` (préremplissage du wizard)
* Stats model_data → valeurs par défaut / moyennes de référence
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _read_excel(name: str, sheet: str | int = 0) -> pd.DataFrame:
    path = DATA_DIR / name
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=sheet)
    except Exception:
        try:
            return pd.read_excel(path, sheet_name=0)
        except Exception:
            return pd.DataFrame()


class AdminCatalog:
    """Accès aux données déjà saisies par l'admin."""

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

    def list_hotels(self) -> list[dict[str, Any]]:
        frame = _read_excel("hotel_data.xlsx")
        if frame.empty:
            return []
        cols_keep = [
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
            "hotel_affaires_pct",
            "hotel_loisirs_pct",
            "hotel_international_pct",
            "hotel_national_pct",
            "hotel_f_b_bar",
            "hotel_f_b_restaurant",
            "hotel_f_b_minibar",
            "hotel_non_f_b_piscine",
            "hotel_non_f_b_salle_de_sport",
            "hotel_non_f_b_spa",
            "hotel_non_f_b_salles_de_reunion",
            "hotel_corner_actuel_existe_deja",
            "hotel_metres_lineaires_dedies_corner",
            "hotel_dispo_dans_lobby_fontaine_a_eau",
            "hotel_dispo_dans_lobby_machine_a_cafe",
            "hotel_dispo_dans_lobby_micro_ondes",
            "hotel_dispo_dans_lobby_vitrine_refrigeree",
        ]
        present = [c for c in cols_keep if c in frame.columns]
        out: list[dict[str, Any]] = []
        for _, row in frame.iterrows():
            item: dict[str, Any] = {}
            for c in present:
                val = row.get(c)
                if pd.isna(val):
                    item[c] = None
                elif hasattr(val, "item"):
                    try:
                        item[c] = val.item()
                    except Exception:
                        item[c] = val
                else:
                    item[c] = val
            if item.get("hotel_code") or item.get("hotel_name"):
                out.append(item)
        return out

    def get_hotel(self, hotel_code: str) -> dict[str, Any] | None:
        code = str(hotel_code or "").strip()
        for h in self.list_hotels():
            if str(h.get("hotel_code") or "").strip() == code:
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
