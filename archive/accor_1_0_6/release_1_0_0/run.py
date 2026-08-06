#!/usr/bin/env python3
"""
Point d'entree release 1.0.0

  python run.py serve [--port 5080]
  python run.py sim-v1 --rebuild
  python run.py sim-v2 --rebuild
  python run.py ml --rebuild
  python run.py all --rebuild
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from archive.accor_1_0_6.release_1_0_0.src.pipeline.paths import Paths


def cmd_serve(args: argparse.Namespace) -> int:
    from archive.accor_1_0_6.release_1_0_0.src.web.app import create_web_app

    paths = Paths(ROOT).ensure()
    app = create_web_app(paths)
    print(f"Web + API — http://127.0.0.1:{args.port}/")
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


def cmd_sim_v1(args: argparse.Namespace) -> int:
    from archive.accor_1_0_6.release_1_0_0.src.sim_v1.service import SimV1Service

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    svc = SimV1Service(Paths(ROOT))
    path = svc.export_loo()
    print(f"sim_v1 LOO → {path}")
    return 0


def cmd_sim_v2(args: argparse.Namespace) -> int:
    from archive.accor_1_0_6.release_1_0_0.src.sim_v2.service import SimV2Service

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    svc = SimV2Service(Paths(ROOT))
    result = svc.run_loo(rebuild=bool(args.rebuild))
    path = svc.export_loo(result)
    print(f"sim_v2 LOO → {path}")
    return 0


def cmd_ml(args: argparse.Namespace) -> int:
    from archive.accor_1_0_6.release_1_0_0.src.ml.catboost_model import CatBoostService

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    svc = CatBoostService(Paths(ROOT))
    result = svc.run_full()
    print(result["metrics"].to_string(index=False))
    print(f"CatBoost LOO → {result['excel']}")
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    if args.rebuild or True:
        cmd_sim_v1(args)
        try:
            cmd_sim_v2(args)
        except Exception as exc:  # noqa: BLE001
            print(f"sim_v2 skip/erreur : {exc}")
        cmd_ml(args)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Accor ROD release 1.0.0")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_serve = sub.add_parser("serve", help="GUI + API")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=5080)
    p_serve.set_defaults(func=cmd_serve)

    for name, fn in (
        ("sim-v1", cmd_sim_v1),
        ("sim-v2", cmd_sim_v2),
        ("ml", cmd_ml),
        ("all", cmd_all),
    ):
        p = sub.add_parser(name)
        p.add_argument("--rebuild", action="store_true", default=True)
        p.set_defaults(func=fn)

    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
