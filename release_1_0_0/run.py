#!/usr/bin/env python3
"""
CLI haut niveau release 1.0.0 — appelle les services, n'implemente pas la logique.

  python run.py serve [--port 5080]
  python run.py warm [--rebuild]      # materialise t_rich_data + ml super LOO
  python run.py duckdb-ui             # UI web DuckDB sur main.duckdb
  python run.py sim-v1 --rebuild
  python run.py sim-v2 --rebuild
  python run.py sim-v2-build          # modelisation complete (scenarios + simulation)
  python run.py ml --rebuild          # super-modele (GUI ml)
  python run.py ml1 --rebuild         # XGBoost sim_v2 seul
  python run.py ml2 --rebuild         # XGBoost sim_v2 + rich + brand
  python run.py ml-xgb --rebuild      # legacy alias ml2/xgb
  python run.py ml-super --rebuild    # alias super
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

from src.pipeline.paths import Paths


def _log() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def cmd_serve(args: argparse.Namespace) -> int:
    from src.web.app import create_web_app

    app = create_web_app(Paths(ROOT).ensure())
    print(f"Web + API — http://127.0.0.1:{args.port}/")
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


def cmd_duckdb_ui(args: argparse.Namespace) -> int:
    """Ouvre DuckDB UI (CALL start_ui) sur main.duckdb."""
    import importlib.util

    script = ROOT / "scripts" / "start_duckdb_ui.py"
    spec = importlib.util.spec_from_file_location("start_duckdb_ui", script)
    if spec is None or spec.loader is None:
        print(f"Script introuvable : {script}", file=sys.stderr)
        return 1
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    argv: list[str] = []
    if getattr(args, "write", False):
        argv.append("--write")
    if getattr(args, "db", None):
        argv.extend(["--db", str(args.db)])
    return int(mod.main(argv) or 0)


def cmd_warm(args: argparse.Namespace) -> int:
    """
    Prechauffe la base pour un 1er chargement web rapide :
      1) materialise t_rich_data via cp.p_table_view(\"t_rich_data\")
      2) entraine ml (super = XGB sim_v2 + stacking) + LOO GUI
    """
    from src.pipeline.connection import PipelineFactory

    _log()
    log = logging.getLogger("warm")
    paths = Paths(ROOT).ensure()
    factory = PipelineFactory(paths)
    cp = factory.open(read_only=False)
    try:
        if getattr(args, "rebuild", False):
            # force recreate (mode create_if_not_exists sinon no-op)
            for name in ("v_web_rich_data", "t_rich_data"):
                try:
                    cp.con.execute(f"DROP VIEW IF EXISTS {name}")
                except Exception:  # noqa: BLE001
                    pass
                try:
                    cp.con.execute(f"DROP TABLE IF EXISTS {name}")
                except Exception:  # noqa: BLE001
                    pass
            log.info("DROP t_rich_data / v_web_rich_data (rebuild)")

        # Jointure concrete pipeline (hotel_data + proximity + weather + holidays)
        log.info('cp.p_table_view("t_rich_data") …')
        rich = cp.p_table_view("t_rich_data").df()
        n_hotels = (
            int(rich["hotel_code"].nunique())
            if "hotel_code" in rich.columns
            else 0
        )
        log.info(
            "t_rich_data OK — rows=%s cols=%s hotels=%s",
            len(rich),
            rich.shape[1],
            n_hotels,
        )

        # Vues / tables souvent lues au 1er hit web (create_if_not_exists → no-op si present)
        for name in (
            "v_web_rich_data",
            "t_hotel_data",
            "t_hotel_brand_data",
            "t_hotel_proximity_data",
            "v_ml_training_dataset",
        ):
            try:
                cp.p_table_view(name)
                log.info("warm %s OK", name)
            except Exception as exc:  # noqa: BLE001
                log.warning("warm %s skip: %s", name, exc)
    finally:
        cp.close()

    # ml = super-modele (XGB sur sim_v2 + stacking sim_v2)
    log.info("ml super run_full (XGB sim_v2 + meta) …")
    from src.ml.super_model import SuperModelService

    result = SuperModelService(paths).run_full()
    print(result["metrics"].to_string(index=False))
    print(f"ml LOO → {result['excel']}")
    print("Warm termine : t_rich_data + ml (super) prets pour la GUI.")
    return 0


def cmd_sim_v1(args: argparse.Namespace) -> int:
    from src.sim_v1.service import SimV1Service

    _log()
    path = SimV1Service(Paths(ROOT)).export_loo()
    print(f"sim_v1 LOO → {path}")
    return 0


def cmd_sim_v2(args: argparse.Namespace) -> int:
    from src.sim_v2.service import SimV2Service

    _log()
    svc = SimV2Service(Paths(ROOT))
    result = svc.run_loo(rebuild=bool(args.rebuild))
    path = svc.export_loo(result)
    print(f"sim_v2 LOO → {path}")
    return 0


def cmd_sim_v2_build(args: argparse.Namespace) -> int:
    """Lance la modelisation complete (ScenarioGenerator + iteration)."""
    from src.sim_v2.service import SimV2Service

    _log()
    stats = SimV2Service(Paths(ROOT)).build_modeling(
        include_full_removal=not args.no_full_removal,
    )["stats"]
    print(stats)
    return 0


def cmd_ml(args: argparse.Namespace) -> int:
    """
    Modele ml = super-modele :
      XGB base sur simulations sim_v2 + stacking avec pred sim_v2.
    """
    from src.ml.super_model import SuperModelService

    _log()
    result = SuperModelService(Paths(ROOT)).run_full()
    print(result["metrics"].to_string(index=False))
    print(f"ml (super) LOO → {result['excel']}")
    return 0


def cmd_ml_xgb(args: argparse.Namespace) -> int:
    from src.ml.xgboost_model import XGBoostService

    _log()
    result = XGBoostService(Paths(ROOT), variant="xgboost").run_full()
    print(result["metrics"].to_string(index=False))
    print(f"XGBoost LOO → {result['excel']}")
    return 0


def cmd_ml1(args: argparse.Namespace) -> int:
    """XGBoost sur liste de simulations sim_v2 uniquement."""
    from src.ml.xgboost_model import XGBoostService

    _log()
    result = XGBoostService(Paths(ROOT), variant="ml1").run_full()
    print(result["metrics"].to_string(index=False))
    print(f"ml1 LOO → {result['excel']} (source={result.get('source')})")
    return 0


def cmd_ml2(args: argparse.Namespace) -> int:
    """XGBoost sim_v2 + rich (proximite, weather moyenne, hotel) + brand."""
    from src.ml.xgboost_model import XGBoostService

    _log()
    result = XGBoostService(Paths(ROOT), variant="ml2").run_full()
    print(result["metrics"].to_string(index=False))
    print(f"ml2 LOO → {result['excel']} (source={result.get('source')})")
    return 0


def cmd_ml_super(args: argparse.Namespace) -> int:
    from src.ml.super_model import SuperModelService

    _log()
    result = SuperModelService(Paths(ROOT)).run_full()
    print(result["metrics"].to_string(index=False))
    print(f"Super LOO → {result['excel']}")
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    cmd_sim_v1(args)
    try:
        cmd_sim_v2(args)
    except Exception as exc:  # noqa: BLE001
        print(f"sim_v2 skip/erreur : {exc}")
    cmd_ml(args)
    try:
        cmd_ml1(args)
    except Exception as exc:  # noqa: BLE001
        print(f"ml1 skip/erreur : {exc}")
    try:
        cmd_ml2(args)
    except Exception as exc:  # noqa: BLE001
        print(f"ml2 skip/erreur : {exc}")
    try:
        cmd_ml_xgb(args)
    except Exception as exc:  # noqa: BLE001
        print(f"ml-xgb skip/erreur : {exc}")
    try:
        cmd_ml_super(args)
    except Exception as exc:  # noqa: BLE001
        print(f"ml-super skip/erreur : {exc}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Accor ROD release 1.0.0")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_serve = sub.add_parser("serve", help="GUI + API")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=5080)
    p_serve.set_defaults(func=cmd_serve)

    p_ui = sub.add_parser(
        "duckdb-ui",
        help="Interface web DuckDB (start_ui) sur main.duckdb",
    )
    p_ui.add_argument(
        "--write",
        action="store_true",
        help="Ouvre la base en ecriture (defaut: lecture seule)",
    )
    p_ui.add_argument(
        "--db",
        default=None,
        help="Chemin .duckdb (defaut: data/duckdb/main/main.duckdb)",
    )
    p_ui.set_defaults(func=cmd_duckdb_ui)

    for name, fn in (
        ("sim-v1", cmd_sim_v1),
        ("sim-v2", cmd_sim_v2),
        ("ml", cmd_ml),
        ("ml1", cmd_ml1),
        ("ml2", cmd_ml2),
        ("ml-xgb", cmd_ml_xgb),
        ("ml-super", cmd_ml_super),
        ("all", cmd_all),
    ):
        p = sub.add_parser(name)
        p.add_argument("--rebuild", action="store_true", default=True)
        p.set_defaults(func=fn)

    p_build = sub.add_parser(
        "sim-v2-build",
        help="Modelisation sim_v2 (scenarios + simulation pipeline)",
    )
    p_build.add_argument(
        "--no-full-removal",
        action="store_true",
        help="Ne pas generer le scenario retrait total",
    )
    p_build.set_defaults(func=cmd_sim_v2_build)

    p_warm = sub.add_parser(
        "warm",
        help=(
            "Materialise t_rich_data (p_table_view) + CatBoost LOO pour la GUI"
        ),
    )
    p_warm.add_argument(
        "--rebuild",
        action="store_true",
        help="Drop t_rich_data puis recree la jointure avant le ML",
    )
    p_warm.set_defaults(func=cmd_warm)

    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
