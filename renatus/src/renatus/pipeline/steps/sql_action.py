"""
SqlActionStep — actions SQL sans relation creee (execute).
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Step, script_text


class SqlActionStep(Step):
    """Step executant du SQL sans materialiser une relation nommee."""

    def should_process(self, pipeline_obj: Any) -> bool:
        return True

    def relation_name(self) -> str | None:
        return None


class ExecuteStep(SqlActionStep):
    """
    Execute une requete SQL (INSERT/DELETE/UPDATE/...).

    Type YAML: ``execute_sql`` (F0078). Legacy ``execute`` accepte en lecture.
    """

    type: ClassVar[str] = "execute_sql"
    ALLOWED_CONFIG_KEYS: ClassVar[frozenset[str] | None] = frozenset(
        {"type", "label", "requires", "script"}
    )

    def process(self, pipeline_obj: Any) -> None:
        # F0067: corps dans ``script`` (legacy ``sql`` accepte via normalize)
        sql = script_text(self.config).strip().rstrip(";")
        pipeline_obj.con.sql(sql)

    def build_action(self) -> str:
        return "process_with_requires"

    @classmethod
    def tool_meta(cls) -> dict[str, Any]:
        return {
            "id": "execute_sql",
            "label": "SQL",
            "type": "execute_sql",
            "description": (
                "Execute une requete SQL sans creer de relation "
                "(ex: DELETE, INSERT)."
            ),
            "icon": "exec",
            "fields": ["name", "requires", "script"],
            "region": "execute",
        }
