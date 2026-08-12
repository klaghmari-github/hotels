"""
Noyau Python persistant (F0136) — session interactive style notebook.

Un sous-processus Python long-vecu par (interpreteur, cwd) conserve le
namespace entre les steps ``execute_python``. Les variables, imports et
definitions restent disponibles d un script YAML a l autre tant que la
connexion pipeline (session de travail) est ouverte.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Protocole: 1 ligne JSON stdin → 1 ligne JSON stdout (worker)
# { "op": "exec", "code": "..." } → { "returncode", "stdout", "stderr" }
# { "op": "shutdown" } → fin

_WORKER_SOURCE = r"""
import json
import sys
import traceback
from io import StringIO

# Namespace persistant (style notebook)
NS = {"__name__": "__main__"}

def _run_exec(code: str) -> dict:
    out_buf, err_buf = StringIO(), StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out_buf, err_buf
    rc = 0
    try:
        compiled = compile(code, "<execute_python>", "exec")
        exec(compiled, NS, NS)
    except SystemExit as e:
        code_ex = e.code
        if code_ex is None:
            rc = 0
        elif isinstance(code_ex, int):
            rc = code_ex
        else:
            rc = 1
            err_buf.write(str(code_ex) + "\n")
    except Exception:
        rc = 1
        err_buf.write(traceback.format_exc())
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    return {
        "returncode": int(rc),
        "stdout": out_buf.getvalue(),
        "stderr": err_buf.getvalue(),
    }

def _preview(val, limit: int = 140) -> str:
    try:
        tname = type(val).__name__
        # pandas / numpy hints
        if tname == "DataFrame":
            shape = getattr(val, "shape", None)
            cols = list(getattr(val, "columns", [])[:8])
            return f"DataFrame shape={shape} cols={cols}"
        if tname == "Series":
            return f"Series len={len(val)} dtype={getattr(val, 'dtype', '?')}"
        if tname == "ndarray":
            return f"ndarray shape={getattr(val, 'shape', '?')} dtype={getattr(val, 'dtype', '?')}"
        s = repr(val)
    except Exception as exc:
        return f"<preview error: {exc}>"
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s

def _list_vars() -> dict:
    items = []
    for k, v in list(NS.items()):
        if not isinstance(k, str):
            continue
        if k.startswith("_"):
            continue
        if k in ("In", "Out", "exit", "quit", "get_ipython"):
            continue
        try:
            t = type(v).__name__
            mod = getattr(type(v), "__module__", "") or ""
            full_type = f"{mod}.{t}" if mod and mod != "builtins" else t
        except Exception:
            t, full_type = "?", "?"
        items.append(
            {
                "name": k,
                "type": t,
                "type_full": full_type,
                "preview": _preview(v),
            }
        )
    items.sort(key=lambda x: x["name"].lower())
    return {"returncode": 0, "stdout": "", "stderr": "", "vars": items, "count": len(items)}

def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.stdout.write(
                json.dumps(
                    {
                        "returncode": 1,
                        "stdout": "",
                        "stderr": f"kernel protocol error: {exc}\n",
                    }
                )
                + "\n"
            )
            sys.stdout.flush()
            continue
        op = (msg or {}).get("op") or "exec"
        if op == "shutdown":
            break
        if op == "ping":
            sys.stdout.write(
                json.dumps({"returncode": 0, "stdout": "pong", "stderr": ""})
                + "\n"
            )
            sys.stdout.flush()
            continue
        if op == "vars":
            result = _list_vars()
            sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            continue
        code = (msg or {}).get("code")
        if code is None:
            code = ""
        result = _run_exec(str(code))
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
"""


class PythonKernel:
    """
    Sous-processus Python interactif (un namespace partage).

    Thread-safe: un lock serialise les exec (DuckDB mono-thread equivalent).
    """

    def __init__(
        self,
        python_exe: Path | str,
        *,
        cwd: Path | str,
        env: dict[str, str] | None = None,
    ) -> None:
        self.python_exe = Path(python_exe).resolve()
        self.cwd = Path(cwd).resolve()
        self.env = env if env is not None else os.environ.copy()
        self._lock = threading.RLock()
        self._proc: subprocess.Popen[str] | None = None
        self._start()

    def _start(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        logger.info(
            "python kernel start: %s (cwd=%s)",
            self.python_exe,
            self.cwd,
        )
        self._proc = subprocess.Popen(
            [str(self.python_exe), "-u", "-c", _WORKER_SOURCE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(self.cwd),
            env=self.env,
            bufsize=1,  # line buffered
        )

    def _ensure_alive(self) -> subprocess.Popen[str]:
        if self._proc is None or self._proc.poll() is not None:
            logger.warning("python kernel mort — redemarrage (namespace perdu)")
            self._start()
        assert self._proc is not None
        return self._proc

    def _request(
        self,
        payload: dict[str, Any],
        *,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        """Envoie une requete JSON ligne et lit la reponse (sous lock externe)."""
        proc = self._ensure_alive()
        if proc.stdin is None or proc.stdout is None:
            raise RuntimeError("python kernel: pipes indisponibles")
        line_out = json.dumps(payload, ensure_ascii=False)
        try:
            proc.stdin.write(line_out + "\n")
            proc.stdin.flush()
        except BrokenPipeError:
            self._start()
            proc = self._ensure_alive()
            assert proc.stdin is not None
            proc.stdin.write(line_out + "\n")
            proc.stdin.flush()

        result_box: list[str | None] = [None]
        err_box: list[BaseException | None] = [None]

        def _reader() -> None:
            try:
                assert proc.stdout is not None
                result_box[0] = proc.stdout.readline()
            except BaseException as exc:  # noqa: BLE001
                err_box[0] = exc

        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        t.join(timeout=max(0.05, float(timeout)))
        if t.is_alive():
            self.shutdown(force=True)
            raise TimeoutError(
                f"python kernel: timeout apres {timeout}s"
            )
        if err_box[0] is not None:
            raise RuntimeError(
                f"python kernel: lecture reponse: {err_box[0]}"
            ) from err_box[0]
        line = result_box[0]
        if not line:
            rc = proc.poll()
            stderr = ""
            if proc.stderr is not None:
                try:
                    stderr = proc.stderr.read() or ""
                except Exception:
                    stderr = ""
            raise RuntimeError(
                f"python kernel: pas de reponse (exit={rc})\n{stderr}"
            )
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"python kernel: reponse invalide: {line[:200]!r}"
            ) from exc
        if not isinstance(data, dict):
            raise RuntimeError("python kernel: reponse non-objet")
        return data

    def exec(
        self,
        code: str,
        *,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        """
        Execute ``code`` dans le namespace persistant.

        Retourne {returncode, stdout, stderr, python, cwd, session: True}.
        """
        with self._lock:
            data = self._request(
                {"op": "exec", "code": str(code)},
                timeout=timeout,
            )
            return {
                "returncode": int(data.get("returncode") or 0),
                "stdout": str(data.get("stdout") or ""),
                "stderr": str(data.get("stderr") or ""),
                "python": str(self.python_exe),
                "cwd": str(self.cwd),
                "session": True,
            }

    def list_vars(self, *, timeout: float = 15.0) -> dict[str, Any]:
        """F0137: variables du namespace session (pour inspecteur notebook)."""
        with self._lock:
            data = self._request({"op": "vars"}, timeout=timeout)
            vars_list = data.get("vars") if isinstance(data.get("vars"), list) else []
            return {
                "ok": True,
                "vars": vars_list,
                "count": int(data.get("count") or len(vars_list)),
                "python": str(self.python_exe),
                "cwd": str(self.cwd),
                "session": True,
            }

    def shutdown(self, *, force: bool = False) -> None:
        with self._lock:
            proc = self._proc
            self._proc = None
            if proc is None:
                return
            try:
                if proc.poll() is None and proc.stdin and not force:
                    try:
                        proc.stdin.write(
                            json.dumps({"op": "shutdown"}) + "\n"
                        )
                        proc.stdin.flush()
                    except Exception:
                        force = True
                if force and proc.poll() is None:
                    proc.kill()
                else:
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=2)
            finally:
                for stream in (proc.stdin, proc.stdout, proc.stderr):
                    try:
                        if stream:
                            stream.close()
                    except Exception:
                        pass
            logger.info("python kernel stopped: %s", self.python_exe)


class PythonKernelRegistry:
    """
    Un noyau par cle (python_exe, cwd) attache a une ConnectionPipeline.
    """

    def __init__(self) -> None:
        self._kernels: dict[str, PythonKernel] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _key(python_exe: Path | str, cwd: Path | str) -> str:
        return f"{Path(python_exe).resolve()}::{Path(cwd).resolve()}"

    def get(
        self,
        python_exe: Path | str,
        *,
        cwd: Path | str,
        env: dict[str, str] | None = None,
    ) -> PythonKernel:
        k = self._key(python_exe, cwd)
        with self._lock:
            ker = self._kernels.get(k)
            if ker is None or (
                ker._proc is not None and ker._proc.poll() is not None
            ):
                ker = PythonKernel(python_exe, cwd=cwd, env=env)
                self._kernels[k] = ker
            return ker

    def shutdown_all(self) -> None:
        with self._lock:
            for ker in list(self._kernels.values()):
                try:
                    ker.shutdown()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("kernel shutdown: %s", exc)
            self._kernels.clear()


def run_python_oneshot(
    python_exe: Path | str,
    code: str,
    *,
    cwd: Path | str,
    timeout: float = 60.0,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execution one-shot (process neuf) — mode ``fresh: true``."""
    env = env if env is not None else os.environ.copy()
    completed = subprocess.run(
        [str(python_exe), "-"],
        input=str(code),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=float(timeout),
        shell=False,
        env=env,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
        "python": str(python_exe),
        "cwd": str(cwd),
        "session": False,
    }
