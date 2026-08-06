"""
Simulateur v2 : scenarios d'assortiment, restitution, LOO, orchestration modelisation.
"""

from .loo import run_leave_one_out
from .modeling import main, run_modeling_simulation
from .restitution import (
    normalized_mix_name,
    replace_restitution_input_views,
    run_restitution,
)
from .scenarios import ScenarioGenerator
from .service import SimV2Service

__all__ = [
    "SimV2Service",
    "ScenarioGenerator",
    "normalized_mix_name",
    "replace_restitution_input_views",
    "run_restitution",
    "run_leave_one_out",
    "run_modeling_simulation",
    "main",
]
