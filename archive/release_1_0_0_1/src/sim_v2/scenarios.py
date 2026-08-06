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

from src.pipeline.engine import ConnectionPipeline
from src.pipeline.paths import release_root


class ScenarioGenerator:
    GROUPS = {
        "categorie": (
            "t_rank_nature_by_categorie",
            "t_rank_categorie",
            "categorie",
        ),
        "gamme": (
            "t_rank_nature_by_gamme",
            "t_rank_gamme",
            "gamme",
        ),
        "type": (
            "t_rank_nature_by_type",
            "t_rank_type",
            "type",
        ),
        "marque": (
            "t_rank_nature_by_marque",
            "t_rank_marque",
            "marque",
        ),
        "fournisseur": (
            "t_rank_nature_by_fournisseur",
            "t_rank_fournisseur",
            "fournisseur",
        ),
    }

    def __init__(
        self,
        cp: ConnectionPipeline,
        output_excel_path: str | Path | None = None,
    ):
        self.cp = cp
        if output_excel_path is None:
            output_excel_path = (
                release_root()
                / "data"
                / "files"
                / "input"
                / "scenarios.xlsx"
            )
        path = Path(output_excel_path).expanduser()
        if not path.is_absolute():
            path = release_root() / path
        self.output_excel_path = path.resolve()
        self.output_excel_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self._scenarios: set[
            tuple[str, ...]
        ] = {()}

    @staticmethod
    def canonical_natures(
        values: Iterable[Any],
    ) -> tuple[str, ...]:
        clean = {
            str(value).strip()
            for value in values
            if value is not None
            and not pd.isna(value)
            and str(value).strip()
        }

        return tuple(
            sorted(
                clean,
                key=lambda value: (
                    value.casefold(),
                    value,
                ),
            )
        )

    @staticmethod
    def scenario_hash(
        values: tuple[str, ...],
    ) -> str:
        payload = json.dumps(
            list(values),
            ensure_ascii=False,
            separators=(",", ":"),
        )

        return hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest()

    def add(
        self,
        values: Iterable[Any],
    ) -> None:
        self._scenarios.add(
            self.canonical_natures(values)
        )

    def add_cumulative(
        self,
        values: list[str],
        include_full_removal: bool,
    ) -> None:
        stop = (
            len(values)
            if include_full_removal
            else max(
                0,
                len(values) - 1,
            )
        )

        for size in range(
            1,
            stop + 1,
        ):
            self.add(
                values[:size]
            )

    def add_balanced_group_scenarios(
        self,
        nature_table: str,
        group_column: str,
        include_full_removal: bool = True,
    ) -> None:
        """
        Genere des retraits equilibres entre les sous-groupes d'une dimension.

        Pour chaque hotel, le niveau 1 retire la nature la moins rentable
        de chaque sous-groupe. Le niveau 2 retire les deux natures les moins
        rentables de chaque sous-groupe, puis ainsi de suite.

        Lorsqu'un sous-groupe contient moins de natures que le niveau courant,
        toutes ses natures deja disponibles restent dans le scenario.
        """
        dataframe = self.cp.p_table_view(
            nature_table
        ).df()

        required_columns = {
            "hotel_code",
            group_column,
            "nature",
            "rang_nature",
        }

        missing_columns = (
            required_columns
            - set(dataframe.columns)
        )

        if missing_columns:
            raise ValueError(
                f"Colonnes manquantes dans {nature_table} : "
                f"{sorted(missing_columns)}"
            )

        for _, hotel_dataframe in dataframe.groupby(
            "hotel_code",
            sort=True,
        ):
            hotel_dataframe = (
                hotel_dataframe
                .dropna(
                    subset=[
                        group_column,
                        "nature",
                        "rang_nature",
                    ]
                )
                .copy()
            )

            if hotel_dataframe.empty:
                continue

            hotel_dataframe["rang_nature"] = (
                hotel_dataframe["rang_nature"]
                .astype(int)
            )

            max_rank = int(
                hotel_dataframe["rang_nature"].max()
            )

            if not include_full_removal:
                total_natures = (
                    hotel_dataframe["nature"]
                    .nunique()
                )
            else:
                total_natures = None

            previous_scenario: tuple[str, ...] = ()

            for rank_level in range(
                1,
                max_rank + 1,
            ):
                selected_natures = (
                    hotel_dataframe.loc[
                        hotel_dataframe["rang_nature"]
                        <= rank_level,
                        "nature",
                    ]
                    .tolist()
                )

                scenario = self.canonical_natures(
                    selected_natures
                )

                if not scenario:
                    continue

                if scenario == previous_scenario:
                    continue

                if (
                    not include_full_removal
                    and total_natures is not None
                    and len(scenario) >= total_natures
                ):
                    break

                self.add(scenario)
                previous_scenario = scenario

    def generate_rank_scenarios(
        self,
        include_full_removal: bool = True,
    ) -> None:
        global_df = self.cp.p_table_view(
            "t_rank_nature"
        ).df()

        for _, hotel_df in global_df.groupby(
            "hotel_code",
            sort=True,
        ):
            ordered = (
                hotel_df
                .sort_values(
                    [
                        "rang_nature",
                        "nature",
                    ]
                )["nature"]
                .tolist()
            )

            self.add_cumulative(
                ordered,
                include_full_removal,
            )

        for (
            group_name,
            (
                nature_table,
                group_table,
                group_column,
            ),
        ) in self.GROUPS.items():
            nature_df = self.cp.p_table_view(
                nature_table
            ).df()

            for _, group_df in nature_df.groupby(
                [
                    "hotel_code",
                    group_column,
                ],
                sort=True,
                dropna=False,
            ):
                ordered = (
                    group_df
                    .sort_values(
                        [
                            "rang_nature",
                            "nature",
                        ]
                    )["nature"]
                    .tolist()
                )

                self.add_cumulative(
                    ordered,
                    include_full_removal,
                )

            # Retraits equilibres entre tous les sous-groupes
            self.add_balanced_group_scenarios(
                nature_table=nature_table,
                group_column=group_column,
                include_full_removal=(
                    include_full_removal
                ),
            )

            ranked_groups = self.cp.p_table_view(
                group_table
            ).df()

            for _, hotel_df in ranked_groups.groupby(
                "hotel_code",
                sort=True,
            ):
                cumulative: list[str] = []

                rows = (
                    hotel_df
                    .sort_values(
                        [
                            f"rang_{group_name}",
                            group_column,
                        ]
                    )
                    .to_dict(
                        orient="records",
                    )
                )

                stop = (
                    len(rows)
                    if include_full_removal
                    else max(
                        0,
                        len(rows) - 1,
                    )
                )

                for row in rows[:stop]:
                    cumulative.extend(
                        list(
                            row["natures"]
                        )
                    )
                    self.add(cumulative)

    def dataframe(
        self,
    ) -> pd.DataFrame:
        ordered = sorted(
            self._scenarios,
            key=lambda values: (
                len(values),
                tuple(
                    value.casefold()
                    for value in values
                ),
                values,
            ),
        )

        return pd.DataFrame(
            {
                "scenario_id": [
                    self.scenario_hash(values)
                    for values in ordered
                ],
                "scenario_removed_natures_json": [
                    json.dumps(
                        list(values),
                        ensure_ascii=False,
                    )
                    for values in ordered
                ],
            }
        )

    def write_excel(
        self,
    ) -> pd.DataFrame:
        dataframe = self.dataframe()
        dataframe.to_excel(
            self.output_excel_path,
            index=False,
        )
        return dataframe


