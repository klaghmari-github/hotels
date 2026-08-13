"""
PythonActionStep — execution de code Python hors DuckDB (F0055 / F0136).

Type YAML distinct de ``execute`` (SQL) : ``execute_python``.

F0136: par defaut le code s execute dans un **noyau Python persistant**
(session de travail), comme un notebook Jupyter : variables, imports et
definitions survivent d une step a l autre. ``fresh: true`` (ou
``session: false``) force un process neuf one-shot.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar

from .base import Step

logger = logging.getLogger(__name__)

# Timeout defaut (secondes) — evite les scripts hangs
DEFAULT_TIMEOUT_S = 60
# Cap raisonnable (secondes)
MAX_TIMEOUT_S = 3600


def resolve_venv_python(
    project_dir: Path,
    venv: str | None = None,
) -> Path:
    """
    Resolut l'interpreteur Python a utiliser (F0055 / F0068).

    - venv vide / absent / None → Python **local** (``sys.executable``)
      du process renatus (pas de .venv impose)
    - venv renseigne (relatif a project_dir ou absolu) → ce venv / binaire
    - accepte un chemin vers le dossier venv OU vers le binaire python
    """
    raw = (venv or "").strip()
    # F0068: defaut = python local (celui qui execute renatus)
    if not raw:
        return Path(sys.executable).resolve()

    root = Path(project_dir).expanduser().resolve()
    p = Path(raw).expanduser()
    base = p.resolve() if p.is_absolute() else (root / p).resolve()

    candidates: list[Path] = []
    # Chemin direct vers un binaire python
    if base.is_file():
        candidates.append(base)
    # Layout venv Unix / Windows
    candidates.extend(
        [
            base / "bin" / "python",
            base / "bin" / "python3",
            base / "Scripts" / "python.exe",
            base / "Scripts" / "python",
        ]
    )
    for cand in candidates:
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
        # Windows : is_file suffit souvent (pas de bit X)
        if cand.is_file():
            return cand

    raise FileNotFoundError(
        f"Interpreteur Python introuvable pour venv={raw!r} "
        f"(base={base}). Indiquez un dossier venv (bin/python) "
        f"ou un chemin de binaire ; vide = python local."
    )


def _parse_timeout(value: Any) -> float:
    if value is None or value == "":
        return float(DEFAULT_TIMEOUT_S)
    try:
        t = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"timeout invalide: {value!r} (nombre de secondes attendu)"
        ) from exc
    if t <= 0:
        raise ValueError(f"timeout doit etre > 0 (recu {t})")
    if t > MAX_TIMEOUT_S:
        raise ValueError(
            f"timeout trop eleve: {t}s (max {MAX_TIMEOUT_S}s)"
        )
    return t


class PythonActionStep(Step):
    """Step executant du code Python via subprocess (pas de relation DuckDB)."""

    def should_process(self, pipeline_obj: Any) -> bool:
        return True

    def relation_name(self) -> str | None:
        return None


def _wants_fresh_session(config: dict[str, Any]) -> bool:
    """
    True = process neuf (pas de persistance).

    - fresh: true  → one-shot
    - session: false → one-shot
    - defaut F0136 → session persistante (notebook)
    """
    if "fresh" in config and config.get("fresh") is not None:
        v = config.get("fresh")
        if isinstance(v, str):
            return v.strip().lower() in {"1", "true", "yes", "on"}
        return bool(v)
    if "session" in config and config.get("session") is not None:
        v = config.get("session")
        if isinstance(v, str):
            return v.strip().lower() in {"0", "false", "no", "off"}
        return not bool(v)
    return False


class ExecutePythonStep(PythonActionStep):
    """
    Execute un script Python (F0055 / F0068 / F0136).

    Config YAML :
      - script (str, requis) : code Python
      - venv (str, optionnel) : chemin venv ou binaire ;
        vide / absent = Python local (sys.executable)
      - timeout (number, optionnel) : secondes ; defaut 60
      - requires (list, optionnel)
      - session (bool, optionnel) : defaut true — namespace persistant
      - fresh (bool, optionnel) : true = process neuf (ignore session)
    """

    type: ClassVar[str] = "execute_python"
    ALLOWED_CONFIG_KEYS: ClassVar[frozenset[str] | None] = frozenset(
        {
            "type",
            "label",
            "requires",
            "script",
            "venv",
            "timeout",
            "session",
            "fresh",
        }
    )

    def _resolve_script_text(self, pipeline_obj: Any) -> str:
        """
        F0146: lit <id>.py a cote du YAML si present, sinon config.script.
        """
        from renatus.pipeline.steps.source_files import (
            script_from_sidecar_path,
            sidecar_ext_for,
        )

        # 1) chemin pipeline + id
        pipe_path = getattr(pipeline_obj, "pipeline_path", None)
        if pipe_path is not None:
            root = Path(pipe_path)
            ext = sidecar_ext_for(self.type) or ".py"
            # cherche <id>.py n importe ou sous flow (premier match rglob)
            if root.is_dir():
                matches = sorted(root.rglob(f"{self.id}{ext}"))
                for m in matches:
                    if m.is_file() or m.is_symlink():
                        text = script_from_sidecar_path(m)
                        if text.strip():
                            return text
            elif root.is_file():
                side = root.with_name(f"{self.id}{ext}")
                if side.exists():
                    text = script_from_sidecar_path(side)
                    if text.strip():
                        return text
        # 2) legacy YAML
        script = self.config.get("script")
        if script is not None and str(script).strip():
            return str(script)
        return ""

    def validate(self, pipeline_keys: set[str] | frozenset[str]) -> None:
        super().validate(pipeline_keys)
        # F0146: script peut vivre uniquement dans le sidecar — validate
        # souple ici; process re-verifie apres lecture fichier
        # timeout valide si present
        if "timeout" in self.config and self.config["timeout"] is not None:
            _parse_timeout(self.config.get("timeout"))

    def process(self, pipeline_obj: Any) -> None:
        from renatus.pipeline.python_kernel import (
            run_python_oneshot,
        )

        script_text = self._resolve_script_text(pipeline_obj)
        if not script_text.strip():
            raise ValueError(
                f"script manquant ou vide pour {self.id} "
                f"(fichier {self.id}.py ou champ script)"
            )
        project_dir = Path(pipeline_obj.project_dir).resolve()
        venv_cfg = self.config.get("venv")
        venv_str = (
            str(venv_cfg).strip()
            if venv_cfg is not None and str(venv_cfg).strip()
            else None
        )
        python_exe = resolve_venv_python(project_dir, venv_str)
        timeout = _parse_timeout(self.config.get("timeout"))
        fresh = _wants_fresh_session(self.config)

        logger.info(
            "execute_python %s: %s (cwd=%s, timeout=%ss, session=%s)",
            self.id,
            python_exe,
            project_dir,
            timeout,
            not fresh,
        )

        try:
            if fresh:
                result = run_python_oneshot(
                    python_exe,
                    script_text,
                    cwd=project_dir,
                    timeout=timeout,
                    env=os.environ.copy(),
                )
            else:
                # F0136: noyau persistant attache a la ConnectionPipeline
                get_ker = getattr(pipeline_obj, "get_python_kernel", None)
                if callable(get_ker):
                    kernel = get_ker(python_exe, cwd=project_dir)
                    result = kernel.exec(script_text, timeout=timeout)
                else:
                    # fallback si pipeline sans registry (tests legers)
                    result = run_python_oneshot(
                        python_exe,
                        script_text,
                        cwd=project_dir,
                        timeout=timeout,
                        env=os.environ.copy(),
                    )
        except TimeoutError as exc:
            raise RuntimeError(
                f"execute_python {self.id}: timeout apres {timeout}s\n"
                f"{exc}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            raise RuntimeError(
                f"execute_python {self.id}: timeout apres {timeout}s\n"
                f"--- stdout ---\n{stdout}\n"
                f"--- stderr ---\n{stderr}"
            ) from exc
        except OSError as exc:
            raise RuntimeError(
                f"execute_python {self.id}: echec lancement "
                f"{python_exe}: {exc}"
            ) from exc

        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        returncode = int(result.get("returncode") or 0)

        if stdout:
            logger.info(
                "execute_python %s stdout:\n%s",
                self.id,
                stdout.rstrip(),
            )
        if stderr:
            logger.warning(
                "execute_python %s stderr:\n%s",
                self.id,
                stderr.rstrip(),
            )

        # Stocke le resultat sur la step et sur le pipeline (F0062 DataView)
        self.last_result: dict[str, Any] = {
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "python": str(result.get("python") or python_exe),
            "cwd": str(result.get("cwd") or project_dir),
            "session": bool(result.get("session")),
        }
        # Acces GUI apres process_with_requires (une entree par step id)
        store = getattr(pipeline_obj, "python_run_results", None)
        if store is None:
            store = {}
            pipeline_obj.python_run_results = store
        store[self.id] = dict(self.last_result)

        if returncode != 0:
            raise RuntimeError(
                f"execute_python {self.id}: exit {returncode}\n"
                f"python={python_exe}\n"
                f"--- stdout ---\n{stdout}\n"
                f"--- stderr ---\n{stderr}"
            )

    def build_action(self) -> str:
        return "process_with_requires"

    @classmethod
    def tool_meta(cls) -> dict[str, Any]:
        return {
            "id": "execute_python",
            "label": "Python",
            "type": "execute_python",
            "description": (
                "Execute un script Python (session persistante style "
                "notebook). Defaut = python local ; venv optionnel. "
                "fresh: true pour un process neuf."
            ),
            "icon": "py",
            "fields": ["name", "requires", "script", "venv", "timeout"],
            "region": "execute",
        }


def default_project_python(project_dir: Path | None = None) -> Path:
    """
    Helper tests / debug : meme regle que le moteur (F0068).

    venv vide → sys.executable ; sinon resolve_venv_python(project, venv).
    """
    return resolve_venv_python(
        Path(project_dir) if project_dir is not None else Path.cwd(),
        None,
    )


class NotebookStep(ExecutePythonStep):
    """
    F0137: composant notebook — meme moteur session que execute_python,
    UI = editeur style Jupyter Lab + inspecteur de variables session.
    """

    type: ClassVar[str] = "notebook"

    def validate(self, pipeline_keys: set[str] | frozenset[str]) -> None:
        # script peut etre vide au depart (cellule a remplir)
        from renatus.pipeline.steps.base import Step

        Step.validate(self, pipeline_keys)
        if "timeout" in self.config and self.config["timeout"] is not None:
            _parse_timeout(self.config.get("timeout"))

    def process(self, pipeline_obj: Any) -> None:
        script_text = self._resolve_script_text(pipeline_obj)
        if not script_text.strip():
            # notebook vide = no-op (pas d erreur a build)
            self.last_result = {
                "returncode": 0,
                "stdout": "",
                "stderr": "",
                "python": "",
                "cwd": str(getattr(pipeline_obj, "project_dir", "")),
                "session": True,
                "skipped": True,
            }
            store = getattr(pipeline_obj, "python_run_results", None)
            if store is None:
                store = {}
                pipeline_obj.python_run_results = store
            store[self.id] = dict(self.last_result)
            return
        # injecte pour super.process (qui relit aussi le sidecar)
        self.config = dict(self.config)
        self.config["script"] = script_text
        super().process(pipeline_obj)

    @classmethod
    def tool_meta(cls) -> dict[str, Any]:
        return {
            "id": "notebook",
            "label": "Notebook",
            "type": "notebook",
            "description": (
                "Notebook Python multi-cellules (session persistante). "
                "Fichier .ipynb a cote du YAML ; venv optionnel."
            ),
            "icon": "nb",
            "fields": ["name", "requires", "script", "venv", "timeout"],
            "region": "execute",
        }
