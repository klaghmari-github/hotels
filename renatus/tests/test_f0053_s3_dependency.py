"""
F0053-S3 — DependencyTree.stable_frontier via Step.is_stable_frontier.

- table/view create_if_not_exists = frontiere (arret du parcours)
- create_or_replace / execute / zone = traverse requires
- detection de cycles
"""

from __future__ import annotations

import pytest

from renatus.pipeline.engine import DependencyTree
from renatus.pipeline.steps import create_step


def test_stable_frontier_stops_on_table_if_not_exists():
    pipeline = {
        "df_src": {"type": "dataframe", "file": "a.csv"},
        "t_base": {
            "type": "table",
            "sql": "SELECT 1 AS x",
            "mode": "create_if_not_exists",
            "requires": ["df_src"],
        },
        "v_top": {
            "type": "view",
            "sql": "SELECT * FROM t_base",
            "mode": "create_or_replace",
            "requires": ["t_base"],
        },
    }
    tree = DependencyTree(pipeline)
    # v_top n'est pas stable → descend ; t_base est frontier → stop
    assert tree.stable_frontier("v_top") == ["t_base"]
    # t_base lui-meme est frontier
    assert tree.stable_frontier("t_base") == ["t_base"]


def test_stable_frontier_view_if_not_exists():
    pipeline = {
        "v_seed": {
            "type": "view",
            "sql": "SELECT 1",
            "mode": "create_if_not_exists",
        },
        "t_child": {
            "type": "table",
            "sql": "SELECT * FROM v_seed",
            "mode": "create_or_replace",
            "requires": ["v_seed"],
        },
    }
    tree = DependencyTree(pipeline)
    assert tree.stable_frontier("t_child") == ["v_seed"]
    assert tree.stable_frontier("v_seed") == ["v_seed"]


def test_stable_frontier_create_or_replace_traverses():
    pipeline = {
        "t_a": {
            "type": "table",
            "sql": "SELECT 1",
            "mode": "create_or_replace",
        },
        "t_b": {
            "type": "table",
            "sql": "SELECT * FROM t_a",
            "mode": "create_or_replace",
            "requires": ["t_a"],
        },
    }
    tree = DependencyTree(pipeline)
    # aucun nœud stable → frontiere vide
    assert tree.stable_frontier("t_b") == []


def test_stable_frontier_zone_and_execute_not_frontier():
    pipeline = {
        "z1": {"type": "zone", "label": "A"},
        "t_stable": {
            "type": "table",
            "sql": "SELECT 1",
            "mode": "create_if_not_exists",
            "requires": ["z1"],
        },
        "ex": {
            "type": "execute_sql",
            "sql": "SELECT 1",
            "requires": ["t_stable"],
        },
    }
    tree = DependencyTree(pipeline)
    assert create_step("z1", pipeline["z1"]).is_stable_frontier() is False
    assert create_step("ex", pipeline["ex"]).is_stable_frontier() is False
    # ex n'est pas frontier ; t_stable l'est
    assert tree.stable_frontier("ex") == ["t_stable"]


def test_stable_frontier_multiple_seeds_sorted():
    pipeline = {
        "t1": {
            "type": "table",
            "sql": "SELECT 1",
            "mode": "create_if_not_exists",
        },
        "t2": {
            "type": "table",
            "sql": "SELECT 2",
            "mode": "create_if_not_exists",
        },
        "t_join": {
            "type": "table",
            "sql": "SELECT 1",
            "mode": "create_or_replace",
            "requires": ["t2", "t1"],
        },
    }
    tree = DependencyTree(pipeline)
    assert tree.stable_frontier("t_join") == ["t1", "t2"]


def test_stable_frontier_cycle_raises():
    pipeline = {
        "a": {
            "type": "table",
            "sql": "SELECT 1",
            "mode": "create_or_replace",
            "requires": ["b"],
        },
        "b": {
            "type": "table",
            "sql": "SELECT 1",
            "mode": "create_or_replace",
            "requires": ["a"],
        },
    }
    tree = DependencyTree(pipeline)
    with pytest.raises(ValueError, match="cyclique"):
        tree.stable_frontier("a")


def test_is_stable_frontier_on_steps_matches_tree():
    """Coherence Step API ↔ DependencyTree (pas de strings hard-codees)."""
    cases = [
        (
            {"type": "table", "sql": "SELECT 1", "mode": "create_if_not_exists"},
            True,
        ),
        (
            {"type": "view", "sql": "SELECT 1", "mode": "create_if_not_exists"},
            True,
        ),
        (
            {"type": "table", "sql": "SELECT 1", "mode": "create_or_replace"},
            False,
        ),
        # F0119: dataframe create_if_not_exists (defaut) = frontier stable
        ({"type": "dataframe", "file": "x.csv"}, True),
        (
            {
                "type": "dataframe",
                "file": "x.csv",
                "mode": "create_or_replace",
            },
            False,
        ),
        ({"type": "zone"}, False),
        ({"type": "execute_sql", "sql": "SELECT 1"}, False),
    ]
    for config, expected in cases:
        step = create_step("s", config)
        assert step.is_stable_frontier() is expected, config
        tree = DependencyTree({"s": config})
        frontier = tree.stable_frontier("s")
        if expected:
            assert frontier == ["s"]
        else:
            assert frontier == []
