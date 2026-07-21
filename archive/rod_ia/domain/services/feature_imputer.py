"""Imputation documentée des trous — booléens, règles métier, médiane marque."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.services.ml_column_naming import MLColumnNaming

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
}


@dataclass
class ImputationReport:
    """Trace chaque imputation (stratégie + justification)."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def add(
        self,
        hotel_id: str,
        column: str,
        strategy: str,
        justification: str,
        value: float,
    ) -> None:
        self.entries.append(
            {
                "hotel_id": hotel_id,
                "column": column,
                "strategy": strategy,
                "justification": justification,
                "imputed_value": value,
            }
        )

    def to_dict(self) -> dict:
        return {"entries": self.entries, "count": len(self.entries)}


class FeatureImputer:
    """Remplit les trous du récap ROD et dérive des variables exploitables.

    Stratégies (justifiées, pas de brouillon) :
    1. **booléen** → 0 si absent
    2. **TO / guests** → pilote marque (Excel) ou médiane marque dans le récap
    3. **panier moyen** → CA mensuel train / ventes mensuelles train (ventes CSV)
    4. **taux acheteur** → ventes / clients hébergés (règle Excel C21)
    5. **autres numériques** → médiane globale des hôtels renseignés
    6. **catégorielles** → non injectées dans X (exclues avant fit)
    """

    def __init__(
        self,
        identity_registry: HotelIdentityRegistry,
        reference: ReferenceRepository | None = None,
        schema_path: Path | None = None,
    ) -> None:
        self._registry = identity_registry
        self._reference = reference
        self._schema = self._load_schema(schema_path)

    @staticmethod
    def _load_schema(schema_path: Path | None) -> dict[str, str]:
        if not schema_path or not schema_path.exists():
            return {}
        import json as json_lib

        rows = json_lib.loads(schema_path.read_text(encoding="utf-8"))
        return {r["column"]: r.get("field_type_hint", "numeric") for r in rows}

    def _brand_of(self, hotel_id: str) -> str:
        record = self._registry.get(hotel_id)
        return record.brand.upper() if record and record.brand else "AUTRE"

    def _sales_derived(self, hotel_id: str, monthly_avg: pd.DataFrame) -> dict[str, float]:
        rows = monthly_avg[monthly_avg["hotel_id"] == hotel_id]
        if rows.empty:
            return {}
        ca = float(rows["avg_montant"].sum())
        ventes = float(rows["avg_nbr_ventes"].sum())
        panier = ca / ventes if ventes > 0 else 0.0
        return {"panier_moyen": panier, "ventes_mensuelles": ventes, "ca_mensuel": ca}

    def _rule_guests(self, hotel_id: str) -> float:
        brand = self._brand_of(hotel_id)
        return BRAND_GUESTS_DEFAULT.get(brand, 1.7)

    def _rule_to(self, hotel_id: str) -> float:
        brand = self._brand_of(hotel_id)
        return BRAND_TO_DEFAULT.get(brand, 0.75)

    def _rule_taux_acheteur(
        self, hotel_id: str, nb_ch: float, to: float, guests: float, ventes_m: float
    ) -> float:
        clients = nb_ch * to * guests * 30.5
        if clients <= 0:
            return 0.0
        return ventes_m / clients

    def _parse_existing_value(self, val: Any, hint: str) -> float | None:
        if pd.isna(val) or val == "":
            return None
        if hint == "boolean":
            return self._as_boolean(val)
        parsed = self._as_float(val, default=float("nan"))
        if pd.notna(parsed):
            return parsed
        return None

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(",", ".")
        if not text:
            return default
        try:
            return float(text)
        except ValueError:
            return default

    @staticmethod
    def _as_boolean(value: Any) -> float:
        if isinstance(value, str):
            token = value.strip().upper()
            if token in {"OUI", "YES", "X", "TRUE", "1"}:
                return 1.0
            if token in {"NON", "NO", "FALSE", "0"}:
                return 0.0
        try:
            return 1.0 if float(value) >= 0.5 else 0.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _col_matches(col: str, keywords: tuple[str, ...]) -> bool:
        c = col.lower()
        return any(k in c for k in keywords)

    def impute(
        self,
        dataset: pd.DataFrame,
        monthly_avg: pd.DataFrame | None = None,
    ) -> tuple[pd.DataFrame, ImputationReport]:
        frame = dataset.copy()
        report = ImputationReport()
        feature_cols = [c for c in frame.columns if c.startswith("d_")]

        for col in feature_cols:
            if not col.startswith("d_recap_"):
                continue
            hint = self._schema.get(col, "numeric")
            if hint == "categorical":
                if col in frame.columns:
                    frame = frame.drop(columns=[col])
                continue

            for idx, row in frame.iterrows():
                hotel_id = str(row["hotel_id"])
                val = row.get(col)
                parsed = self._parse_existing_value(val, hint)
                if parsed is not None:
                    frame.at[idx, col] = parsed
                    continue

                imputed: float | None = None
                strategy = ""
                justification = ""

                if hint == "boolean":
                    imputed = 0.0
                    strategy = "boolean_zero"
                    justification = "Champ booléen absent → 0 (faux)."

                elif self._col_matches(col, ("to_annuel", "to_annuel_moyen", "to_le_plus")):
                    imputed = self._rule_to(hotel_id)
                    strategy = "brand_pilot_to"
                    justification = f"TO absent → pilote marque {self._brand_of(hotel_id)}."

                elif self._col_matches(col, ("guests", "gueests", "adultes")):
                    imputed = self._rule_guests(hotel_id)
                    strategy = "brand_pilot_guests"
                    justification = "Guests/ch absent → pilote Excel par marque."

                elif self._col_matches(col, ("panier",)):
                    if monthly_avg is not None:
                        derived = self._sales_derived(hotel_id, monthly_avg)
                        imputed = derived.get("panier_moyen", 0.0)
                        strategy = "sales_derived_panier"
                        justification = "Panier absent → CA/ventes moyennes historiques (train)."
                    if not imputed:
                        imputed = 0.0
                        strategy = "zero_fallback"
                        justification = "Panier absent et pas de ventes train."

                elif self._col_matches(col, ("nb_de_chambres", "nb_chambres")):
                    record = self._registry.get(hotel_id)
                    imputed = float(record.nb_chambres or 100) if record else 100.0
                    strategy = "registry_nb_chambres"
                    justification = "Chambres absentes → registre identité."

                else:
                    series = pd.to_numeric(frame[col], errors="coerce")
                    median = float(series.median()) if series.notna().any() else 0.0
                    imputed = median
                    strategy = "global_median"
                    justification = "Numérique absent → médiane des hôtels renseignés."

                frame.at[idx, col] = imputed
                report.add(hotel_id, col, strategy, justification, float(imputed))

        frame = self._add_derived_operating(frame, monthly_avg, report)
        return frame, report

    def _add_derived_operating(
        self,
        frame: pd.DataFrame,
        monthly_avg: pd.DataFrame | None,
        report: ImputationReport,
    ) -> pd.DataFrame:
        """Ajoute clients/mois et taux acheteur estimés (règles Excel)."""
        cols = {
            "nb_chambres": MLColumnNaming.descriptive("nb_chambres"),
            "to": MLColumnNaming.descriptive("taux_occupation"),
            "guests": MLColumnNaming.descriptive("guests_per_chambre"),
            "clients": MLColumnNaming.descriptive("clients_mois"),
            "taux_ach": MLColumnNaming.descriptive("taux_acheteur"),
        }
        for col_name in cols.values():
            if col_name not in frame.columns:
                frame[col_name] = float("nan")

        recap_nb = [c for c in frame.columns if "recap" in c and "chambres" in c.lower()]
        recap_to = [c for c in frame.columns if "recap" in c and "to" in c.lower()]
        recap_guests = [c for c in frame.columns if "recap" in c and "guests" in c.lower()]

        for idx, row in frame.iterrows():
            hotel_id = str(row["hotel_id"])
            nb = row.get(cols["nb_chambres"])
            if pd.isna(nb) or nb == 0:
                nb = row[recap_nb[0]] if recap_nb else None
            if pd.isna(nb) or nb == 0:
                record = self._registry.get(hotel_id)
                nb = float(record.nb_chambres or 100) if record else 100.0

            to = row.get(cols["to"])
            if pd.isna(to) or to == 0:
                to = row[recap_to[0]] if recap_to else self._rule_to(hotel_id)

            guests = row.get(cols["guests"])
            if pd.isna(guests) or guests == 0:
                guests = row[recap_guests[0]] if recap_guests else self._rule_guests(hotel_id)

            nb = self._as_float(nb, default=100.0)
            to = self._as_float(to, default=self._rule_to(hotel_id))
            guests = self._as_float(guests, default=self._rule_guests(hotel_id))
            if to > 1:
                to /= 100.0

            clients = nb * to * guests * 30.5
            frame.at[idx, cols["nb_chambres"]] = nb
            frame.at[idx, cols["to"]] = to
            frame.at[idx, cols["guests"]] = guests
            frame.at[idx, cols["clients"]] = clients

            ventes_m = 0.0
            if monthly_avg is not None:
                ventes_m = self._sales_derived(hotel_id, monthly_avg).get("ventes_mensuelles", 0.0)
            taux = self._rule_taux_acheteur(hotel_id, nb, to, guests, ventes_m)
            frame.at[idx, cols["taux_ach"]] = taux
            report.add(
                hotel_id,
                cols["taux_ach"],
                "excel_rule_c21",
                "taux acheteur = ventes_mensuelles / clients_mois (C21).",
                taux,
            )
        return frame