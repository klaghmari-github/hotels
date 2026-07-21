"""Convention de nommage ML : ``d_`` (descriptives) et ``t_`` (targets)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Iterable


INFO_COLUMNS = frozenset(
    {
        "hotel_id",
        "hotel_name_raw",
        "name_ventes",
        "name_rod",
        "name_display",
        "city",
        "brand",
        "lat",
        "lon",
        "geo_source",
        "source_file",
    }
)


@dataclass
class ColumnManifestEntry:
    column: str
    prefix: str
    role: str
    source: str
    description: str

    def to_dict(self) -> dict:
        return asdict(self)


class MLColumnNaming:
    """Utilitaires pour préfixer et filtrer les colonnes du dataset ML."""

    TARGET_PREFIX = "t_"
    DESCRIPTIVE_PREFIX = "d_"
    _RECAP_STRIP_PREFIXES = (
        re.compile(r"^d_recap_\d+_informations_"),
        re.compile(r"^d_recap_\d+_simulateur_de_revenus_ecran_"),
    )

    @staticmethod
    def fold_accents(value: str) -> str:
        text = unicodedata.normalize("NFKD", str(value))
        return "".join(c for c in text if not unicodedata.combining(c))

    @classmethod
    def descriptive(cls, name: str) -> str:
        base = cls._sanitize(name)
        return base if base.startswith(cls.DESCRIPTIVE_PREFIX) else f"{cls.DESCRIPTIVE_PREFIX}{base}"

    @classmethod
    def recap_column(cls, field_key: str) -> str:
        """Colonne récap ``d_recap_*`` (accents conservés en ASCII, préfixes raccourcis)."""
        return cls.shorten_recap_column(cls.descriptive(f"recap_{field_key}"))

    @classmethod
    def shorten_recap_column(cls, name: str) -> str:
        text = name
        for pattern in cls._RECAP_STRIP_PREFIXES:
            text = pattern.sub("d_recap_", text)
        return text

    @classmethod
    def target(cls, name: str) -> str:
        base = cls._sanitize(name)
        return base if base.startswith(cls.TARGET_PREFIX) else f"{cls.TARGET_PREFIX}{base}"

    @classmethod
    def target_month_type_gamme(
        cls, month: int, type_label: str, gamme: str, metric: str
    ) -> str:
        type_slug = cls._sanitize(type_label)
        gamme_slug = cls._sanitize(gamme)
        metric_slug = "montant" if "montant" in metric else "nbr_ventes"
        return cls.target(f"m{month:02d}_{type_slug}_{gamme_slug}_{metric_slug}")

    @classmethod
    def pct_month(cls, month: int) -> str:
        return cls.descriptive(f"pct_mois_m{month:02d}")

    @classmethod
    def pct_month_type(cls, month: int, type_label: str) -> str:
        return cls.descriptive(f"pct_mois_m{month:02d}_type_{cls._sanitize(type_label)}")

    @classmethod
    def pct_month_type_gamme(cls, month: int, type_label: str, gamme: str) -> str:
        return cls.descriptive(
            f"pct_mois_m{month:02d}_type_{cls._sanitize(type_label)}_gamme_{cls._sanitize(gamme)}"
        )

    @classmethod
    def feature_columns(cls, columns: Iterable[str]) -> list[str]:
        return [c for c in columns if c.startswith(cls.DESCRIPTIVE_PREFIX)]

    @classmethod
    def target_columns(cls, columns: Iterable[str]) -> list[str]:
        return [c for c in columns if c.startswith(cls.TARGET_PREFIX)]

    @classmethod
    def assert_no_target_leakage(cls, feature_cols: Iterable[str]) -> None:
        leaked = [c for c in feature_cols if c.startswith(cls.TARGET_PREFIX)]
        if leaked:
            raise ValueError(f"Fuite de targets dans X: {leaked[:5]}")

    @classmethod
    def build_manifest(cls, columns: Iterable[str], source: str = "pipeline") -> list[dict]:
        manifest: list[ColumnManifestEntry] = []
        for col in columns:
            if col in INFO_COLUMNS:
                role = "informational"
                prefix = ""
            elif col.startswith(cls.TARGET_PREFIX):
                role = "target"
                prefix = cls.TARGET_PREFIX
            elif col.startswith(cls.DESCRIPTIVE_PREFIX):
                role = "descriptive"
                prefix = cls.DESCRIPTIVE_PREFIX
            else:
                role = "informational"
                prefix = ""
            manifest.append(
                ColumnManifestEntry(
                    column=col,
                    prefix=prefix,
                    role=role,
                    source=source,
                    description=f"Colonne {role} générée par {source}",
                ).to_dict()
            )
        return manifest

    @classmethod
    def _sanitize(cls, value: str) -> str:
        text = cls.fold_accents(value).strip().lower()
        text = text.replace("&", "and")
        text = re.sub(r"[^a-z0-9]+", "_", text)
        return re.sub(r"_+", "_", text).strip("_")