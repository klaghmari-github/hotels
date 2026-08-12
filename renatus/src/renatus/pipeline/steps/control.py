"""
ControlStep — structures de controle (iterate).
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Step


class ControlStep(Step):
    """Step de controle de flux (pas de relation propre)."""

    def should_process(self, pipeline_obj: Any) -> bool:
        return True

    def relation_name(self) -> str | None:
        return None


class IterationStep(ControlStep):
    """
    Iterate sequentiel (ou parallel via ParallelIterationManager).

    Type YAML: ``iterate`` (alias legacy ``iteration`` — F0093).
    """

    type: ClassVar[str] = "iterate"
    # A0011: iterate = controle de flux (pas de file / objects / mode relation)
    ALLOWED_CONFIG_KEYS: ClassVar[frozenset[str] | None] = frozenset(
        {
            "type",
            "label",
            "requires",
            "target",
            "scenarios",
            "step_view",
            "script",
            "order_by",
            "completed_table",
            "completed_key",
            "completed_group_key",
            "expected_count_table",
            "execution",
            "tasks",
            "reserved_cpus",
            "max_workers",
            "duckdb_threads_per_worker",
        }
    )

    def process(self, pipeline_obj: Any) -> None:
        # Logique complete reste sur ConnectionPipeline (parallel, sequential)
        pipeline_obj.process_iteration(self.id)

    def build_action(self) -> str:
        return "p_iteration"

    @classmethod
    def tool_meta(cls) -> dict[str, Any]:
        return {
            "id": "iterate",
            "label": "Iterate",
            "type": "iterate",
            "description": (
                "Traitement iteratif (scenarios / buckets). "
                "Requires multi-select; target / scenarios / step_view; "
                "apercu DataView des sources."
            ),
            "icon": "iter",
            "fields": [
                "name",
                "requires",
                "target",
                "scenarios",
                "step_view",
                "script",
            ],
            "region": "flow",
        }
