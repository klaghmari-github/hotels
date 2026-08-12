"""
A0004 — port deja utilise : bascule auto ou erreur stricte.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from renatus.pipeline.netutil import find_free_port, is_port_free


def _occupy(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(1)
    return sock


def test_is_port_free_and_find_next():
    host = "127.0.0.1"
    # trouver un port libre pour le test
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        base = probe.getsockname()[1]

    holder = _occupy(host, base)
    try:
        assert is_port_free(host, base) is False
        next_port = find_free_port(host, base, strict=False)
        assert next_port != base
        assert next_port > base
        assert is_port_free(host, next_port) is True
    finally:
        holder.close()


def test_find_free_port_strict_raises():
    host = "127.0.0.1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        base = probe.getsockname()[1]

    holder = _occupy(host, base)
    try:
        with pytest.raises(OSError, match="deja utilisee|utilise"):
            find_free_port(host, base, strict=True)
    finally:
        holder.close()


def test_gui_main_auto_port_when_busy(tmp_path: Path, monkeypatch, capsys):
    import uvicorn

    from renatus.gui import server as gui_server

    host = "127.0.0.1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        busy = probe.getsockname()[1]

    holder = _occupy(host, busy)
    used: dict = {}

    def fake_run(app, host=None, port=None, log_level="info"):
        used["port"] = port
        used["host"] = host

    monkeypatch.setattr(uvicorn, "run", fake_run)

    try:
        db = tmp_path / "t.duckdb"
        pipe = tmp_path / "pipes"
        code = gui_server.main(
            [str(db), str(pipe), "--host", host, "--port", str(busy)]
        )
        assert code == 0
        assert used["port"] != busy
        assert used["port"] > busy
        err = capsys.readouterr().err
        assert "occupe" in err.lower() or str(used["port"]) in err
    finally:
        holder.close()


def test_gui_main_strict_port_fails(tmp_path: Path, monkeypatch):
    import uvicorn

    from renatus.gui import server as gui_server

    host = "127.0.0.1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        busy = probe.getsockname()[1]

    holder = _occupy(host, busy)
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    try:
        code = gui_server.main(
            [
                str(tmp_path / "t.duckdb"),
                str(tmp_path / "pipes"),
                "--host",
                host,
                "--port",
                str(busy),
                "--strict-port",
            ]
        )
        assert code == 1
    finally:
        holder.close()
