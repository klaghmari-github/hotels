"""
RelationStep — dataframe / table / view (relations DuckDB).

Helpers partages : name physique, label, mode create_*.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Step, script_text


class RelationStep(Step):
    """Step produisant une relation en base (name/label/mode)."""

    DEFAULT_MODE: ClassVar[str] = "create_if_not_exists"

    def __init__(
        self,
        step_id: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(step_id, config)
        # name = entite physique SQL (F0048) ; sinon label ; sinon id
        explicit = self.config.get("name")
        self.physical_name: str | None = None
        if explicit is not None:
            text = str(explicit).strip()
            if text:
                self.physical_name = text

    def relation_name(self) -> str | None:
        if self.physical_name:
            return self.physical_name
        if self.label:
            return self.label
        return self.id

    def build_action(self) -> str:
        return "p_table_view"

    def has_tabular_result(self) -> bool:
        return True

    def produces_relation(self) -> bool:
        return True

    MODES: ClassVar[frozenset[str]] = frozenset(
        {"create_if_not_exists", "create_or_replace"}
    )

    @property
    def mode(self) -> str:
        raw = str(self.config.get("mode") or self.DEFAULT_MODE).strip()
        if raw not in self.MODES:
            return self.DEFAULT_MODE
        return raw

    def should_process(self, pipeline_obj: Any) -> bool:
        """
        create_or_replace: toujours re-executer.
        create_if_not_exists: skip si la relation existe deja
        (session DuckDB: dataframes registers + tables/vues materialisees).
        """
        if self.mode == "create_or_replace":
            return True
        rel = self.relation_name()
        assert rel is not None
        return not pipeline_obj.relation_exists(rel)

    def is_stable_frontier(self) -> bool:
        return self.mode == "create_if_not_exists"

    def validate(self, pipeline_keys: set[str] | frozenset[str]) -> None:
        super().validate(pipeline_keys)
        if "name" in self.config:
            rel = self.config.get("name")
            if rel is None or not str(rel).strip():
                raise ValueError(
                    f"name invalide pour {self.id}: "
                    "doit etre une chaine non vide "
                    "ou omis pour utiliser l id de la step"
                )
        if "mode" in self.config:
            raw = str(self.config.get("mode") or "").strip()
            if raw and raw not in self.MODES:
                raise ValueError(
                    f"mode invalide pour {self.id}: {raw!r} "
                    f"(attendu: {', '.join(sorted(self.MODES))})"
                )


class DataframeStep(RelationStep):
    """Charge un fichier (CSV/Excel/...) via pandas et register DuckDB."""

    type: ClassVar[str] = "dataframe"
    # F0119: mode create_* comme table/view (defaut create_if_not_exists)
    ALLOWED_CONFIG_KEYS: ClassVar[frozenset[str] | None] = frozenset(
        {"type", "label", "name", "file", "mode"}
    )

    def process(self, pipeline_obj: Any) -> None:
        reserved = pipeline_obj.RESERVED_KEYS
        kwargs = {
            key: value
            for key, value in self.config.items()
            if key not in reserved
        }
        rel = self.relation_name()
        assert rel is not None
        # create_or_replace: re-register ecrase la relation temp existante
        # create_if_not_exists: process uniquement si absent (should_process)
        pipeline_obj.con.register(
            rel,
            pipeline_obj.df_from_file(
                self.config["file"],
                **kwargs,
            ),
        )

    def to_config(self) -> dict[str, Any]:
        out = super().to_config()
        # Persiste le mode (defaut explicite pour YAML lisible)
        out["mode"] = self.mode
        return out

    @classmethod
    def tool_meta(cls) -> dict[str, Any]:
        return {
            "id": "dataframe",
            "label": "Dataframe (fichier)",
            "type": "dataframe",
            "description": (
                "Ajoute un nœud sur le graphe (nom horodate). "
                "Puis choisir le fichier (picker / drag-drop). "
                "Pas de SQL — lecture fichier uniquement. "
                "mode: create_if_not_exists (reuse session) "
                "ou create_or_replace (relecture source)."
            ),
            "icon": "df",
            "fields": ["name", "file", "mode"],
            "region": "datasets",
        }


class TableStep(RelationStep):
    """Cree une table materialisee via SQL."""

    type: ClassVar[str] = "table"
    ALLOWED_CONFIG_KEYS: ClassVar[frozenset[str] | None] = frozenset(
        {"type", "label", "name", "mode", "requires", "script"}
    )

    def process(self, pipeline_obj: Any) -> None:
        rel = self.relation_name()
        assert rel is not None
        pipeline_obj.create_relation(
            rel,
            script_text(self.config),
            "table",
            self.mode,
        )

    @classmethod
    def tool_meta(cls) -> dict[str, Any]:
        return {
            "id": "table",
            "label": "Table (SQL)",
            "type": "table",
            "description": (
                "Cree une table materialisee via une requete SQL. "
                "Sources: multi-select requires; apercu DataView au branchement."
            ),
            "icon": "table",
            "fields": ["name", "mode", "requires", "script"],
            "region": "datasets",
        }


class ViewStep(RelationStep):
    """Cree une vue SQL."""

    type: ClassVar[str] = "view"
    ALLOWED_CONFIG_KEYS: ClassVar[frozenset[str] | None] = frozenset(
        {"type", "label", "name", "mode", "requires", "script"}
    )

    def process(self, pipeline_obj: Any) -> None:
        rel = self.relation_name()
        assert rel is not None
        pipeline_obj.create_relation(
            rel,
            script_text(self.config),
            "view",
            self.mode,
        )

    @classmethod
    def tool_meta(cls) -> dict[str, Any]:
        return {
            "id": "view",
            "label": "Vue (SQL)",
            "type": "view",
            "description": (
                "Cree une vue SQL. Sources: multi-select requires; "
                "apercu DataView au branchement."
            ),
            "icon": "view",
            "fields": ["name", "mode", "requires", "script"],
            "region": "datasets",
        }
