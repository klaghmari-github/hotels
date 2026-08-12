"""
Arbre de dependances pipeline et frontiere stable pour seeds workers.
"""

from __future__ import annotations

from typing import Any

from renatus.pipeline.steps import create_step


class DependencyTree:
    def __init__(
        self,
        pipeline: dict[str, dict[str, Any]],
    ):
        self.pipeline = pipeline

    def stable_frontier(
        self,
        target: str,
    ) -> list[str]:
        frontier: set[str] = set()
        visiting: set[str] = set()

        def visit(name: str) -> None:
            if name in visiting:
                raise ValueError(
                    f"Dependance cyclique detectee autour de {name}"
                )

            config = self.pipeline[name]
            # F0053-S3: delegue a Step.is_stable_frontier
            # (table/view en mode create_if_not_exists)
            if create_step(name, config).is_stable_frontier():
                frontier.add(name)
                return

            visiting.add(name)

            for dependency in config.get(
                "requires",
                [],
            ):
                visit(dependency)

            visiting.remove(name)

        visit(target)

        return sorted(frontier)
