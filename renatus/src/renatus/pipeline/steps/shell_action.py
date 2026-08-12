"""
ShellActionStep — execution de commandes shell (F0075).

Type YAML : ``execute_shell``.
``script`` = commandes shell (bash) a lancer dans le cwd projet.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, ClassVar

from .base import Step
from .python_action import DEFAULT_TIMEOUT_S, _parse_timeout

logger = logging.getLogger(__name__)


def resolve_shell_binary() -> str:
    """bash prefere, sinon sh."""
    for name in ("bash", "sh"):
        path = shutil.which(name)
        if path:
            return path
    # fallbacks Unix classiques
    for cand in ("/bin/bash", "/usr/bin/bash", "/bin/sh"):
        if Path(cand).is_file():
            return cand
    return "/bin/sh"


class ShellActionStep(Step):
    """Step executant du shell via subprocess (pas de relation DuckDB)."""

    def should_process(self, pipeline_obj: Any) -> bool:
        return True

    def relation_name(self) -> str | None:
        return None


class ExecuteShellStep(ShellActionStep):
    """
    Execute un script shell (F0075).

    Config YAML :
      - script (str, requis) : commandes shell
      - timeout (number, optionnel) : secondes ; defaut 60
      - requires (list, optionnel)
    """

    type: ClassVar[str] = "execute_shell"
    ALLOWED_CONFIG_KEYS: ClassVar[frozenset[str] | None] = frozenset(
        {"type", "label", "requires", "script", "timeout"}
    )

    def validate(self, pipeline_keys: set[str] | frozenset[str]) -> None:
        super().validate(pipeline_keys)
        script = self.config.get("script")
        if script is None or not str(script).strip():
            raise ValueError(
                f"script manquant ou vide pour {self.id}"
            )
        if "timeout" in self.config and self.config["timeout"] is not None:
            _parse_timeout(self.config.get("timeout"))

    def process(self, pipeline_obj: Any) -> None:
        script = self.config.get("script")
        if script is None or not str(script).strip():
            raise ValueError(
                f"script manquant ou vide pour {self.id}"
            )
        script_text = str(script)
        project_dir = Path(pipeline_obj.project_dir).resolve()
        timeout = _parse_timeout(self.config.get("timeout"))
        shell_bin = resolve_shell_binary()
        # bash/sh -c <script> : multi-lignes, pas de shell=True Python
        cmd = [shell_bin, "-c", script_text]
        logger.info(
            "execute_shell %s: %s (cwd=%s, timeout=%ss)",
            self.id,
            shell_bin,
            project_dir,
            timeout,
        )
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(project_dir),
                timeout=timeout,
                shell=False,
                env=os.environ.copy(),
            )
        except subprocess.TimeoutExpired as exc:
            stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            raise RuntimeError(
                f"execute_shell {self.id}: timeout apres {timeout}s\n"
                f"--- stdout ---\n{stdout}\n"
                f"--- stderr ---\n{stderr}"
            ) from exc
        except OSError as exc:
            raise RuntimeError(
                f"execute_shell {self.id}: echec lancement "
                f"{shell_bin}: {exc}"
            ) from exc

        if completed.stdout:
            logger.info(
                "execute_shell %s stdout:\n%s",
                self.id,
                completed.stdout.rstrip(),
            )
        if completed.stderr:
            logger.warning(
                "execute_shell %s stderr:\n%s",
                self.id,
                completed.stderr.rstrip(),
            )

        self.last_result: dict[str, Any] = {
            "returncode": completed.returncode,
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
            "shell": shell_bin,
            "cwd": str(project_dir),
        }
        # Reutilise le store process (F0062/F0073 DataView Output/Error)
        store = getattr(pipeline_obj, "python_run_results", None)
        if store is None:
            store = {}
            pipeline_obj.python_run_results = store
        store[self.id] = dict(self.last_result)

        if completed.returncode != 0:
            raise RuntimeError(
                f"execute_shell {self.id}: exit {completed.returncode}\n"
                f"shell={shell_bin}\n"
                f"--- stdout ---\n{completed.stdout or ''}\n"
                f"--- stderr ---\n{completed.stderr or ''}"
            )

    def build_action(self) -> str:
        return "process_with_requires"

    @classmethod
    def tool_meta(cls) -> dict[str, Any]:
        return {
            "id": "execute_shell",
            "label": "Shell",
            "type": "execute_shell",
            "description": (
                "Execute des commandes shell (bash). "
                "script = commandes ; cwd = racine projet."
            ),
            "icon": "shell",
            "fields": ["name", "requires", "script", "timeout"],
            "region": "execute",
        }
