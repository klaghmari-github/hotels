from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import duckdb
import pandas as pd
import yaml

from src.pipeline.engine import (
    ConnectionPipeline,
    register_dataframe_as_relation,
)


def normalized_mix_name(
    family: str,
    value: str,
) -> str:
    clean = "".join(
        character.lower()
        if character.isalnum()
        else "_"
        for character in str(value)
    )
    clean = "_".join(
        part
        for part in clean.split("_")
        if part
    )
    return f"{family}_{clean}_part_natures"


def replace_restitution_input_views(
    cp: ConnectionPipeline,
    hotel_nb_chambres: float,
    hotel_to_annuel: float,
    hotel_guests_per_chambre: float,
    metres_lineaires: float,
    type_mix: dict[str, float],
    gamme_mix: dict[str, float],
) -> None:
    if hotel_nb_chambres <= 0:
        raise ValueError(
            "hotel_nb_chambres doit etre strictement positif"
        )
    if not 0 < hotel_to_annuel <= 1:
        raise ValueError(
            "hotel_to_annuel doit etre compris entre 0 et 1"
        )
    if hotel_guests_per_chambre <= 0:
        raise ValueError(
            "hotel_guests_per_chambre doit etre strictement positif"
        )
    if metres_lineaires <= 0:
        raise ValueError(
            "metres_lineaires doit etre strictement positif"
        )

    def validate_mix(
        name: str,
        values: dict[str, float],
    ) -> None:
        if not values:
            raise ValueError(
                f"Le mix {name} ne peut pas etre vide"
            )
        if any(value < 0 for value in values.values()):
            raise ValueError(
                f"Le mix {name} contient une part negative"
            )
        if not math.isclose(
            sum(values.values()),
            1.0,
            rel_tol=1e-6,
            abs_tol=1e-6,
        ):
            raise ValueError(
                f"La somme du mix {name} doit etre egale a 1"
            )

    validate_mix("type", type_mix)
    validate_mix("gamme", gamme_mix)

    cp.con.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW
            v_restitution_input_hotel
        AS
        SELECT
            {float(hotel_nb_chambres)}::DOUBLE
                AS hotel_nb_chambres,
            {float(hotel_to_annuel)}::DOUBLE
                AS hotel_to_annuel,
            {float(hotel_guests_per_chambre)}::DOUBLE
                AS hotel_guests_per_chambre,
            {float(metres_lineaires)}::DOUBLE
                AS metres_lineaires
        """
    )

    rows = []
    for group_value, part in type_mix.items():
        rows.append(
            (
                "type",
                normalized_mix_name("type", group_value),
                float(part),
            )
        )
    for group_value, part in gamme_mix.items():
        rows.append(
            (
                "gamme",
                normalized_mix_name("gamme", group_value),
                float(part),
            )
        )

    input_df = pd.DataFrame(
        rows,
        columns=[
            "variable_family",
            "variable_name",
            "target_part",
        ],
    )
    register_dataframe_as_relation(
        cp.con,
        "__restitution_input_mix_buffer",
        input_df,
        "table",
        replace=True,
    )
    cp.con.sql(
        """
        CREATE OR REPLACE TEMP VIEW
            v_restitution_input_mix
        AS
        SELECT *
        FROM __restitution_input_mix_buffer
        """
    )


def run_restitution(
    cp: ConnectionPipeline,
    hotel_nb_chambres: float = 200,
    hotel_to_annuel: float = 0.5,
    hotel_guests_per_chambre: float = 1.0,
    metres_lineaires: float = 10.0,
    type_mix: dict[str, float] | None = None,
    gamme_mix: dict[str, float] | None = None,
) -> pd.DataFrame:
    default_mix = cp.p_table_view(
        "v_restitution_default_input_mix"
    ).df()

    def family_rows(
        family: str,
        supplied: dict[str, float] | None,
    ) -> list[tuple[str, str, float]]:
        if supplied is None:
            family_default = default_mix[
                default_mix["variable_family"] == family
            ]
            return [
                (
                    family,
                    str(row.variable_name),
                    float(row.target_part),
                )
                for row in family_default.itertuples(index=False)
            ]

        if not supplied:
            raise ValueError(
                f"Le mix {family} ne peut pas etre vide"
            )
        if any(value < 0 for value in supplied.values()):
            raise ValueError(
                f"Le mix {family} contient une part negative"
            )
        if not math.isclose(
            sum(supplied.values()),
            1.0,
            rel_tol=1e-6,
            abs_tol=1e-6,
        ):
            raise ValueError(
                f"La somme du mix {family} doit etre egale a 1"
            )

        return [
            (
                family,
                normalized_mix_name(family, value),
                float(part),
            )
            for value, part in supplied.items()
        ]

    if hotel_nb_chambres <= 0:
        raise ValueError(
            "hotel_nb_chambres doit etre strictement positif"
        )
    if not 0 < hotel_to_annuel <= 1:
        raise ValueError(
            "hotel_to_annuel doit etre compris entre 0 et 1"
        )
    if hotel_guests_per_chambre <= 0:
        raise ValueError(
            "hotel_guests_per_chambre doit etre strictement positif"
        )
    if metres_lineaires <= 0:
        raise ValueError(
            "metres_lineaires doit etre strictement positif"
        )

    cp.con.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW
            v_restitution_input_hotel
        AS
        SELECT
            {float(hotel_nb_chambres)}::DOUBLE
                AS hotel_nb_chambres,
            {float(hotel_to_annuel)}::DOUBLE
                AS hotel_to_annuel,
            {float(hotel_guests_per_chambre)}::DOUBLE
                AS hotel_guests_per_chambre,
            {float(metres_lineaires)}::DOUBLE
                AS metres_lineaires
        """
    )

    rows = [
        *family_rows("type", type_mix),
        *family_rows("gamme", gamme_mix),
    ]
    input_df = pd.DataFrame(
        rows,
        columns=[
            "variable_family",
            "variable_name",
            "target_part",
        ],
    )
    register_dataframe_as_relation(
        cp.con,
        "__restitution_input_mix_buffer",
        input_df,
        "table",
        replace=True,
    )
    cp.con.sql(
        """
        CREATE OR REPLACE TEMP VIEW
            v_restitution_input_mix
        AS
        SELECT *
        FROM __restitution_input_mix_buffer
        """
    )

    cp.process_with_requires(
        "v_restitution_prediction",
        processed=set(),
    )
    return cp.table_view(
        "v_restitution_prediction"
    ).df()


