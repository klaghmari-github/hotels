#!/usr/bin/env python3
"""
Compatibilité Apache Adixon : ProxyPass /studio → 127.0.0.1:8001/studio

release_1_0_0 expose l'admin sur /admin (même process que /user sur :8000).
Ce mini-service redirige /studio* vers https://rod-ia.adixon-dev.fr/admin*.
"""

from __future__ import annotations

import argparse
import os
from urllib.parse import quote

from flask import Flask, redirect, request

app = Flask(__name__)


def _public_base() -> str:
    return (
        os.environ.get("ROD_PUBLIC_BASE")
        or "https://rod-ia.adixon-dev.fr"
    ).rstrip("/")


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def redirect_studio(path: str):
    base = _public_base()
    # PATH_INFO peut être "studio", "studio/", "studio/foo"
    rest = path
    if rest == "studio" or rest.startswith("studio/"):
        rest = rest[len("studio") :].lstrip("/")
    if not rest or rest in {"studio", "login"}:
        target = f"{base}/admin"
    elif rest.startswith("admin"):
        target = f"{base}/{rest}"
    else:
        target = f"{base}/admin/{rest}"
    qs = request.query_string.decode("utf-8", errors="ignore")
    if qs:
        target = f"{target}?{qs}"
    # next= relative → rewrite vers /admin
    return redirect(target, code=302)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8001)
    args = p.parse_args()
    print(f"studio_redirect → {_public_base()}/admin  on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
