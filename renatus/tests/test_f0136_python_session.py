"""F0136 — session Python persistante (style notebook) entre execute_python."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0136_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0136" in text


def _pipe(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "p"
    flow = project / "flow"
    flow.mkdir(parents=True)
    return project, flow


def test_variables_persist_across_steps(tmp_path: Path):
    """Comme un notebook: x defini dans step A, lu dans step B."""
    from renatus.pipeline import ConnectionPipeline

    project, flow = _pipe(tmp_path)
    (flow / "a.yaml").write_text(
        yaml.dump(
            {
                "a": {
                    "type": "execute_python",
                    "requires": [],
                    "script": "x = 42\nname = 'renatus'\n",
                }
            }
        ),
        encoding="utf-8",
    )
    (flow / "b.yaml").write_text(
        yaml.dump(
            {
                "b": {
                    "type": "execute_python",
                    "requires": ["a"],
                    "script": "print(x)\nprint(name)\n",
                }
            }
        ),
        encoding="utf-8",
    )
    cp = ConnectionPipeline(str(project / "db.duckdb"), flow)
    try:
        cp.process_with_requires("b")
        res = (getattr(cp, "python_run_results", None) or {}).get("b") or {}
        assert res.get("returncode") == 0
        out = res.get("stdout") or ""
        assert "42" in out
        assert "renatus" in out
        assert res.get("session") is True
    finally:
        cp.close()


def test_fresh_true_isolates_namespace(tmp_path: Path):
    """fresh: true → process neuf, variables precedentes absentes."""
    from renatus.pipeline import ConnectionPipeline

    project, flow = _pipe(tmp_path)
    (flow / "a.yaml").write_text(
        yaml.dump(
            {
                "a": {
                    "type": "execute_python",
                    "requires": [],
                    "script": "secret = 99\n",
                }
            }
        ),
        encoding="utf-8",
    )
    (flow / "b.yaml").write_text(
        yaml.dump(
            {
                "b": {
                    "type": "execute_python",
                    "requires": ["a"],
                    "fresh": True,
                    "script": (
                        "try:\n"
                        "    print(secret)\n"
                        "except NameError:\n"
                        "    print('ISOLATED')\n"
                    ),
                }
            }
        ),
        encoding="utf-8",
    )
    cp = ConnectionPipeline(str(project / "db.duckdb"), flow)
    try:
        cp.process_with_requires("b")
        res = (getattr(cp, "python_run_results", None) or {}).get("b") or {}
        assert res.get("returncode") == 0
        assert "ISOLATED" in (res.get("stdout") or "")
        assert res.get("session") is False
    finally:
        cp.close()


def test_close_shuts_down_kernel(tmp_path: Path):
    from renatus.pipeline import ConnectionPipeline

    project, flow = _pipe(tmp_path)
    (flow / "a.yaml").write_text(
        yaml.dump(
            {
                "a": {
                    "type": "execute_python",
                    "requires": [],
                    "script": "k = 1\n",
                }
            }
        ),
        encoding="utf-8",
    )
    cp = ConnectionPipeline(str(project / "db.duckdb"), flow)
    try:
        cp.process("a")
        assert len(cp._python_kernels._kernels) >= 1
    finally:
        cp.close()
    assert len(cp._python_kernels._kernels) == 0


def test_kernel_unit_roundtrip(tmp_path: Path):
    import sys

    from renatus.pipeline.python_kernel import PythonKernel

    ker = PythonKernel(sys.executable, cwd=tmp_path)
    try:
        r1 = ker.exec("acc = []\nacc.append(1)\n")
        assert r1["returncode"] == 0
        r2 = ker.exec("print(sum(acc))\nacc.append(2)\nprint(len(acc))\n")
        assert r2["returncode"] == 0
        assert "1" in r2["stdout"]
        assert "2" in r2["stdout"]
    finally:
        ker.shutdown()
