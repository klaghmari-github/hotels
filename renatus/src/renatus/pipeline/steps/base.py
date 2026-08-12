"""
ABC Step — type de composant pipeline (F0053-S1).

Serialisation YAML reste un dict ; les classes encapsulent
validation, relation, should_process et process.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar


def normalize_script_key(config: dict[str, Any]) -> dict[str, Any]:
    """
    F0067: property unifiee ``script`` (SQL ou Python selon le type).

    - lit ``script`` en priorite ; sinon migre ``sql`` legacy → ``script``
    - retire la cle ``sql`` du dict retourne (ecriture propre)
    """
    if not isinstance(config, dict):
        return config
    out = dict(config)
    has_script = "script" in out and out.get("script") is not None
    has_sql = "sql" in out and out.get("sql") is not None
    if has_script:
        out["script"] = out.get("script")
        out.pop("sql", None)
    elif has_sql:
        out["script"] = out.pop("sql")
    else:
        out.pop("sql", None)
    return out


def script_text(config: dict[str, Any] | None) -> str:
    """
    Corps du script (SQL ou Python). Accepte legacy ``sql``.
    """
    cfg = config or {}
    if cfg.get("script") is not None:
        return str(cfg.get("script"))
    if cfg.get("sql") is not None:
        return str(cfg.get("sql"))
    raise KeyError("script")


class Step(ABC):
    """Composant pipeline : id YAML + config dict + comportement type."""

    # Cle YAML "type" (ex: "dataframe", "zone")
    type: ClassVar[str] = ""

    # A0011: cles YAML autorisees pour ce type (None = pas de filtre strict).
    # Sous-classes definissent un frozenset pour ecarter les attributs incoherents
    # (ex: zone sans file/script/mode).
    ALLOWED_CONFIG_KEYS: ClassVar[frozenset[str] | None] = None

    def __init__(
        self,
        step_id: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.id = step_id
        raw = normalize_script_key(dict(config or {}))
        # type toujours aligne sur la classe
        raw["type"] = self.type
        # A0011: purge immediate des cles hors allow-list (ex: file sur zone)
        if self.ALLOWED_CONFIG_KEYS is not None:
            raw = {
                k: v
                for k, v in raw.items()
                if k in self.ALLOWED_CONFIG_KEYS
            }
            raw["type"] = self.type
        self.config = raw
        self.label: str | None = (
            str(raw["label"]).strip()
            if raw.get("label") is not None and str(raw["label"]).strip()
            else None
        )
        requires = raw.get("requires") or []
        if not isinstance(requires, list):
            # si requires n est pas autorise pour ce type, ignore
            if self.ALLOWED_CONFIG_KEYS is not None and (
                "requires" not in self.ALLOWED_CONFIG_KEYS
            ):
                requires = []
            else:
                raise ValueError(
                    f"requires invalide pour {step_id}: liste attendue"
                )
        self.requires: list[str] = list(requires)

    # -- serialisation ------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        step_id: str,
        config: dict[str, Any],
    ) -> Step:
        """Instancie depuis un dict YAML (type doit matcher la classe)."""
        return cls(step_id, config)

    def to_config(self) -> dict[str, Any]:
        """Dict serialisable YAML (copie), filtre allow-list (A0011)."""
        out = dict(self.config)
        out["type"] = self.type
        if self.requires:
            out["requires"] = list(self.requires)
        elif "requires" in out and not out["requires"]:
            out["requires"] = []
        if self.label is not None:
            out["label"] = self.label
        if self.ALLOWED_CONFIG_KEYS is not None:
            out = {
                k: v
                for k, v in out.items()
                if k in self.ALLOWED_CONFIG_KEYS
            }
            out["type"] = self.type
            # ne pas forcer requires: [] si non autorise (zone)
            if "requires" not in self.ALLOWED_CONFIG_KEYS:
                out.pop("requires", None)
            elif self.requires:
                out["requires"] = list(self.requires)
            elif "requires" in self.config:
                out["requires"] = list(self.requires)
            if self.label is not None and "label" in self.ALLOWED_CONFIG_KEYS:
                out["label"] = self.label
        return out

    # -- validation ---------------------------------------------------------

    def validate(self, pipeline_keys: set[str] | frozenset[str]) -> None:
        """Valide config + requires present dans le pipeline."""
        for dep in self.requires:
            if dep not in pipeline_keys:
                raise ValueError(
                    f"Dependance absente pour {self.id}: {dep}"
                )

    # -- execution ----------------------------------------------------------

    def should_process(self, pipeline_obj: Any) -> bool:
        """True si la step doit etre executee (defaut: toujours)."""
        return True

    @abstractmethod
    def process(self, pipeline_obj: Any) -> None:
        """Execute la step sur le ConnectionPipeline (ctx)."""

    def relation_name(self) -> str | None:
        """
        Nom physique en base, ou None si pas de relation
        (execute / iteration / zone).
        """
        return None

    def is_stable_frontier(self) -> bool:
        """True si arret du parcours stable_frontier (table/view IF NOT EXISTS)."""
        return False

    # -- GUI build (F0054-S1) ---------------------------------------------

    def build_action(self) -> str:
        """
        Action GuiService.build :
        "p_table_view" | "p_iteration" | "process_with_requires" | "zone_noop"
        """
        return "process_with_requires"

    def has_tabular_result(self) -> bool:
        """True si build renvoie colonnes/lignes (table/view/dataframe)."""
        return False

    def produces_relation(self) -> bool:
        """True si la step materialise une relation DuckDB (df/table/view)."""
        return False

    # -- GUI palette -----------------------------------------------------

    @classmethod
    def tool_meta(cls) -> dict[str, Any]:
        """Metadonnees palette GUI (id, label, type, description, icon, fields)."""
        raise NotImplementedError(
            f"{cls.__name__}.tool_meta() non implemente"
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self.id!r}, type={self.type!r})"
