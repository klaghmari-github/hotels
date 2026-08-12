"""
Iteration parallele : buckets workers, seeds, merge resultats.
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from renatus.pipeline.engine import (
    ConnectionPipeline,
    ensure_table_schema,
    ensure_varchar_array_column,
    ensure_varchar_column,
    pipeline_fingerprint,
    register_dataframe_as_relation,
    relation_schema,
    relation_type,
    source_fingerprint,
    worker_metadata_matches,
    write_worker_metadata,
)


@dataclass
class ParallelismConfig:
    bucket_count: int
    max_workers: int
    reserved_cpus: int
    duckdb_threads_per_worker: int


def resolve_parallelism(
    tasks: int | str,
    reserved_cpus: int = 2,
    duckdb_threads_per_worker: int = 1,
) -> ParallelismConfig:
    logical_cpus = os.cpu_count() or 1
    worker_capacity = max(
        1,
        logical_cpus - reserved_cpus,
    )

    if isinstance(
        tasks,
        str,
    ):
        if tasks.lower() != "auto":
            raise ValueError(
                "tasks doit etre un entier "
                "strictement positif ou auto"
            )
        bucket_count = worker_capacity
    else:
        bucket_count = int(tasks)

        if bucket_count <= 0:
            raise ValueError(
                "tasks doit etre strictement positif"
            )

    max_workers = min(
        bucket_count,
        worker_capacity,
    )

    return ParallelismConfig(
        bucket_count=bucket_count,
        max_workers=max_workers,
        reserved_cpus=reserved_cpus,
        duckdb_threads_per_worker=(
            duckdb_threads_per_worker
        ),
    )


def scenario_bucket(
    scenario_id: str,
    bucket_count: int,
) -> int:
    return (
        int(
            scenario_id[:16],
            16,
        )
        % bucket_count
    )


def run_iteration_bucket(
    worker_db_path: str,
    pipeline_path: str,
    iteration_name: str,
    duckdb_threads: int,
    bucket_id: int,
) -> dict[str, Any]:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            f"%(asctime)s | task {bucket_id:03d} | "
            "%(levelname)s | %(message)s"
        ),
        force=True,
    )

    cp = ConnectionPipeline(
        worker_db_path,
        pipeline_path,
    )

    cp.con.execute(
        f"SET threads = {int(duckdb_threads)}"
    )

    scenarios_name = cp.pipeline[
        iteration_name
    ]["scenarios"]

    cp.process_with_requires(
        scenarios_name,
        processed=set(),
    )

    scenarios_before = cp.con.sql(
        f"""
        SELECT COUNT(*)
        FROM "{scenarios_name}"
        """
    ).fetchone()[0]

    started = time.perf_counter()

    cp.process_iteration_sequential(
        iteration_name,
    )

    duration = (
        time.perf_counter()
        - started
    )

    result_count = cp.con.sql(
        """
        SELECT COUNT(*)
        FROM t_dataset_pivot
        """
    ).fetchone()[0]

    cp.close()

    return {
        "bucket_id": bucket_id,
        "scenario_count": scenarios_before,
        "result_count": result_count,
        "duration": duration,
        "worker_db_path": worker_db_path,
    }


class ParallelIterationManager:
    def __init__(
        self,
        shared_cp: ConnectionPipeline,
        iteration_name: str,
    ):
        self.shared_cp = shared_cp
        self.iteration_name = iteration_name
        self.config = shared_cp.pipeline[
            iteration_name
        ]

        parallelism = resolve_parallelism(
            self.config.get(
                "tasks",
                "auto",
            ),
            reserved_cpus=int(
                self.config.get(
                    "reserved_cpus",
                    2,
                )
            ),
            duckdb_threads_per_worker=int(
                self.config.get(
                    "duckdb_threads_per_worker",
                    1,
                )
            ),
        )

        self.parallelism = parallelism
        self.result_table = self.config.get(
            "result_table",
            self.config.get(
                "completed_table",
                "t_dataset_pivot",
            ),
        )
        self.pipeline_hash = pipeline_fingerprint(
            shared_cp.pipeline_path
        )
        self.source_hash = source_fingerprint(
            shared_cp
        )

    def worker_db_path(
        self,
        bucket_id: int,
    ) -> Path:
        pattern = self.config.get(
            "worker_database_pattern",
            "data/duckdb/workers/"
            "simulation_task_{task_id:03d}.duckdb",
        )

        relative = pattern.format(
            task_id=bucket_id,
        )

        return self.shared_cp.resolve_project_path(
            relative
        )

    def ensure_shared_result_table(
        self,
    ) -> None:
        if self.shared_cp.table_exists(
            self.result_table
        ):
            ensure_varchar_column(
                self.shared_cp.con,
                self.result_table,
                "scenario_id",
            )
            ensure_varchar_array_column(
                self.shared_cp.con,
                self.result_table,
                "scenario_removed_natures",
            )
            return

        step_view = self.config["step_view"]

        baseline = self.shared_cp.con.sql(
            """
            SELECT
                scenario_id,
                scenario_removed_natures
            FROM t_scenarios
            WHERE
                COALESCE(
                    LEN(scenario_removed_natures),
                    0
                ) = 0
            LIMIT 1
            """
        ).df()

        if baseline.empty:
            raise ValueError(
                "Le scenario initial avec une liste "
                "vide est absent de t_scenarios"
            )

        self.shared_cp.replace_step_view(
            step_view,
            baseline.iloc[0].to_dict(),
        )

        self.shared_cp.process_with_requires(
            self.result_table,
            processed=set(),
        )

        ensure_varchar_column(
            self.shared_cp.con,
            self.result_table,
            "scenario_id",
        )
        ensure_varchar_array_column(
            self.shared_cp.con,
            self.result_table,
            "scenario_removed_natures",
        )

    def merge_existing_worker_results(
        self,
    ) -> int:
        merged = 0

        for bucket_id in range(
            self.parallelism.bucket_count
        ):
            worker_path = self.worker_db_path(
                bucket_id
            )

            if not worker_path.exists():
                continue

            worker_connection = duckdb.connect(
                str(worker_path),
                read_only=True,
            )

            if not worker_metadata_matches(
                worker_connection,
                self.source_hash,
                self.pipeline_hash,
                self.parallelism.bucket_count,
                bucket_id,
            ):
                worker_connection.close()
                continue

            table_exists = worker_connection.sql(
                f"""
                SELECT COUNT(*) > 0
                FROM information_schema.tables
                WHERE table_name = '{self.result_table}'
                  AND table_type = 'BASE TABLE'
                """
            ).fetchone()[0]

            if not table_exists:
                worker_connection.close()
                continue

            dataframe = worker_connection.sql(
                f'SELECT * FROM "{self.result_table}"'
            ).df()
            worker_connection.close()

            if dataframe.empty:
                continue

            merged += self.merge_result_dataframe(
                dataframe
            )

        return merged

    def merge_result_dataframe(
        self,
        dataframe: pd.DataFrame,
    ) -> int:
        before = self.shared_cp.con.sql(
            f"""
            SELECT COUNT(*)
            FROM "{self.result_table}"
            """
        ).fetchone()[0]

        register_dataframe_as_relation(
            self.shared_cp.con,
            "__worker_result_buffer",
            dataframe,
            "table",
            replace=True,
        )

        self.shared_cp.con.sql(
            f"""
            INSERT INTO "{self.result_table}" BY NAME
            SELECT source.*
            FROM "__worker_result_buffer"
                AS source
            WHERE NOT EXISTS (
                SELECT 1
                FROM "{self.result_table}"
                    AS target
                WHERE
                    target.scenario_id
                        = source.scenario_id
                    AND target.hotel_code
                        = source.hotel_code
            )
            """
        )

        self.shared_cp.con.sql(
            """
            DROP TABLE IF EXISTS
                "__worker_result_buffer"
            """
        )

        after = self.shared_cp.con.sql(
            f"""
            SELECT COUNT(*)
            FROM "{self.result_table}"
            """
        ).fetchone()[0]

        return int(after - before)

    def stable_seed_frames(
        self,
    ) -> dict[str, dict[str, Any]]:
        target = self.config["target"]
        frontier = self.shared_cp.tree.stable_frontier(
            target
        )

        frames: dict[str, dict[str, Any]] = {}

        for name in frontier:
            if name in {
                "t_scenarios",
                self.result_table,
            }:
                continue

            self.shared_cp.process_with_requires(
                name,
                processed=set(),
            )
            frames[name] = {
                "dataframe": (
                    self.shared_cp
                    .table_view(name)
                    .df()
                ),
                "relation_type": (
                    self.shared_cp.pipeline[name]["type"]
                ),
            }

        return frames

    def pending_scenarios(
        self,
    ) -> pd.DataFrame:
        scenarios_name = self.config["scenarios"]

        self.shared_cp.process_with_requires(
            scenarios_name,
            processed=set(),
        )

        return self.shared_cp.table_view(
            scenarios_name
        ).df()

    def prepare_worker_databases(
        self,
        pending: pd.DataFrame,
        seed_frames: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        workers: list[dict[str, Any]] = []

        if pending.empty:
            return workers

        pending = pending.copy()
        pending["bucket_id"] = (
            pending["scenario_id"]
            .astype(str)
            .map(
                lambda value: scenario_bucket(
                    value,
                    self.parallelism.bucket_count,
                )
            )
        )

        result_schema = relation_schema(
            self.shared_cp.con,
            self.result_table,
        )

        for bucket_id, bucket_df in pending.groupby(
            "bucket_id",
            sort=True,
        ):
            worker_path = self.worker_db_path(
                int(bucket_id)
            )
            worker_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            existing_connection = None

            if worker_path.exists():
                existing_connection = duckdb.connect(
                    str(worker_path)
                )
                metadata_ok = worker_metadata_matches(
                    existing_connection,
                    self.source_hash,
                    self.pipeline_hash,
                    self.parallelism.bucket_count,
                    int(bucket_id),
                )
                existing_connection.close()

                if not metadata_ok:
                    worker_path.unlink()

            worker_connection = duckdb.connect(
                str(worker_path)
            )

            metadata_ok = worker_metadata_matches(
                worker_connection,
                self.source_hash,
                self.pipeline_hash,
                self.parallelism.bucket_count,
                int(bucket_id),
            )

            if not metadata_ok:
                for name, seed in seed_frames.items():
                    register_dataframe_as_relation(
                        worker_connection,
                        name,
                        seed["dataframe"],
                        seed["relation_type"],
                        replace=True,
                    )

                ensure_table_schema(
                    worker_connection,
                    self.result_table,
                    result_schema,
                )

                write_worker_metadata(
                    worker_connection,
                    self.source_hash,
                    self.pipeline_hash,
                    self.parallelism.bucket_count,
                    int(bucket_id),
                )
            else:
                for name, seed in seed_frames.items():
                    current_type = relation_type(
                        worker_connection,
                        name,
                    )

                    expected_type = str(
                        seed["relation_type"]
                    ).lower()

                    if current_type != expected_type:
                        register_dataframe_as_relation(
                            worker_connection,
                            name,
                            seed["dataframe"],
                            expected_type,
                            replace=True,
                        )

            ensure_table_schema(
                worker_connection,
                self.result_table,
                result_schema,
            )

            local_scenarios = bucket_df[
                [
                    "scenario_id",
                    "scenario_removed_natures",
                ]
            ].copy()
            local_scenarios["scenario_id"] = (
                local_scenarios["scenario_id"]
                .astype(str)
            )

            register_dataframe_as_relation(
                worker_connection,
                "t_scenarios",
                local_scenarios,
                "table",
                replace=True,
            )

            worker_connection.close()

            workers.append(
                {
                    "bucket_id": int(bucket_id),
                    "worker_db_path": str(
                        worker_path
                    ),
                }
            )

        return workers

    def execute(
        self,
    ) -> dict[str, Any]:
        self.ensure_shared_result_table()

        merged_before = (
            self.merge_existing_worker_results()
        )

        pending = self.pending_scenarios()

        logging.info(
            "Parallelisation : buckets=%s | "
            "workers=%s | cpu_reserves=%s | "
            "scenarios_restants=%s",
            self.parallelism.bucket_count,
            self.parallelism.max_workers,
            self.parallelism.reserved_cpus,
            len(pending),
        )

        if pending.empty:
            return {
                "bucket_count": (
                    self.parallelism.bucket_count
                ),
                "max_workers": (
                    self.parallelism.max_workers
                ),
                "pending_scenarios": 0,
                "completed_buckets": 0,
                "merged_rows_before": merged_before,
                "merged_rows_after": 0,
            }

        seed_frames = self.stable_seed_frames()
        worker_configs = (
            self.prepare_worker_databases(
                pending,
                seed_frames,
            )
        )

        self.shared_cp.close()

        completed: list[dict[str, Any]] = []
        started = time.perf_counter()

        with ProcessPoolExecutor(
            max_workers=(
                self.parallelism.max_workers
            )
        ) as pool:
            futures = {
                pool.submit(
                    run_iteration_bucket,
                    worker["worker_db_path"],
                    str(
                        self.shared_cp.pipeline_path
                    ),
                    self.iteration_name,
                    self.parallelism
                    .duckdb_threads_per_worker,
                    worker["bucket_id"],
                ): worker
                for worker in worker_configs
            }

            total_buckets = len(futures)

            for index, future in enumerate(
                as_completed(futures),
                start=1,
            ):
                result = future.result()
                completed.append(result)

                elapsed = (
                    time.perf_counter()
                    - started
                )
                remaining = (
                    elapsed
                    / index
                    * (total_buckets - index)
                    if index
                    else 0
                )

                logging.info(
                    "Bucket %s termine | %s/%s | "
                    "scenarios=%s | duree=%.1fs | "
                    "reste_estime=%.1fs",
                    result["bucket_id"],
                    index,
                    total_buckets,
                    result["scenario_count"],
                    result["duration"],
                    remaining,
                )

        self.shared_cp = ConnectionPipeline(
            self.shared_cp.db_path,
            self.shared_cp.pipeline_path,
        )

        merged_after = (
            self.merge_existing_worker_results()
        )

        return {
            "bucket_count": (
                self.parallelism.bucket_count
            ),
            "max_workers": (
                self.parallelism.max_workers
            ),
            "pending_scenarios": len(pending),
            "completed_buckets": len(completed),
            "merged_rows_before": merged_before,
            "merged_rows_after": merged_after,
            "workers": completed,
        }
