from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from pathlib import Path
from typing import Any, Iterable

import duckdb
import pandas as pd
import yaml


class ConnectionUtils:
    def __init__(self, db_con_str: str | Path):
        self.db_path = Path(db_con_str).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(self.db_path))

    def table_exists(self, name: str) -> bool:
        return bool(self.con.execute("""
            SELECT COUNT(*) > 0
            FROM information_schema.tables
            WHERE table_catalog = current_database()
              AND table_schema = current_schema()
              AND table_name = ?
              AND table_type = 'BASE TABLE'
        """, [name]).fetchone()[0])

    def view_exists(self, name: str) -> bool:
        return bool(self.con.execute("""
            SELECT COUNT(*) > 0
            FROM information_schema.views
            WHERE table_catalog = current_database()
              AND table_schema = current_schema()
              AND table_name = ?
        """, [name]).fetchone()[0])

    def relation_exists(self, name: str) -> bool:
        return self.table_exists(name) or self.view_exists(name)

    def table_view(self, name: str):
        return self.con.sql(f'SELECT * FROM "{name}"')

    def create_relation(self, name: str, sql: str, relation_type: str, mode: str) -> None:
        relation_type = relation_type.upper()
        sql = sql.strip().rstrip(';')
        if relation_type not in {'TABLE', 'VIEW'}:
            raise ValueError(f'Type non supporte : {relation_type}')
        if mode == 'create_if_not_exists':
            self.con.sql(f'CREATE {relation_type} IF NOT EXISTS "{name}" AS ({sql})')
        elif mode == 'create_or_replace':
            self.con.sql(f'CREATE OR REPLACE {relation_type} "{name}" AS ({sql})')
        else:
            raise ValueError(f'Mode non supporte : {mode}')


class ConnectionPipeline(ConnectionUtils):
    RESERVED_KEYS = {
        'type', 'mode', 'requires', 'file', 'sql', 'target', 'scenarios',
        'step_view', 'order_by', 'completed_table', 'completed_key',
        'completed_group_key', 'expected_count_table'
    }

    def __init__(self, db_con_str: str | Path, pipeline_path: str | Path):
        super().__init__(db_con_str)
        self.pipeline_path = Path(pipeline_path).expanduser().resolve()
        self.pipeline = self.load_pipeline()

    def load_pipeline(self) -> dict[str, dict[str, Any]]:
        path = self.pipeline_path
        yaml_files = [path] if path.is_file() else sorted([*path.rglob('*.yaml'), *path.rglob('*.yml')])
        if not yaml_files:
            raise FileNotFoundError(f'Aucun fichier YAML trouve dans {path}')
        merged: dict[str, dict[str, Any]] = {}
        origins: dict[str, Path] = {}
        for yaml_file in yaml_files:
            content = yaml.safe_load(yaml_file.read_text(encoding='utf-8')) or {}
            if not isinstance(content, dict):
                raise ValueError(f'Contenu YAML invalide : {yaml_file}')
            for name, config in content.items():
                if name in merged:
                    raise ValueError(f'Objet {name} defini dans {origins[name]} et {yaml_file}')
                merged[name] = config
                origins[name] = yaml_file
        self.validate_pipeline(merged)
        return merged

    @staticmethod
    def validate_pipeline(pipeline: dict[str, dict[str, Any]]) -> None:
        allowed = {'dataframe', 'table', 'view', 'execute', 'iteration'}
        for name, config in pipeline.items():
            if config.get('type') not in allowed:
                raise ValueError(f'Type invalide pour {name}: {config.get("type")}')
            for dependency in config.get('requires', []):
                if dependency not in pipeline:
                    raise ValueError(f'Dependance absente pour {name}: {dependency}')

    def df_from_file(self, file: str | Path, **kwargs) -> pd.DataFrame:
        path = Path(file).expanduser()
        if not path.is_absolute():
            base_dir = self.pipeline_path.parent if self.pipeline_path.is_file() else self.pipeline_path.parent
            path = base_dir / path
        path = path.resolve()
        suffix = path.suffix.lower()
        if suffix in {'.xlsx', '.xls', '.xlsm'}:
            return pd.read_excel(path, **kwargs)
        if suffix == '.csv':
            return pd.read_csv(path, **kwargs)
        if suffix == '.tsv':
            return pd.read_csv(path, sep='\t', **kwargs)
        if suffix == '.json':
            return pd.read_json(path, **kwargs)
        if suffix == '.parquet':
            return pd.read_parquet(path, **kwargs)
        raise ValueError(f'Extension non supportee : {suffix}')

    def should_process(self, name: str) -> bool:
        config = self.pipeline[name]
        object_type = config['type']
        mode = config.get('mode', 'create_if_not_exists')
        if object_type in {'execute', 'iteration'}:
            return True
        if object_type == 'dataframe':
            return not self.relation_exists(name)
        if mode == 'create_or_replace':
            return True
        return not self.relation_exists(name)

    def process(self, name: str) -> None:
        config = self.pipeline[name]
        object_type = config['type']
        if object_type == 'dataframe':
            kwargs = {k: v for k, v in config.items() if k not in self.RESERVED_KEYS}
            self.con.register(name, self.df_from_file(config['file'], **kwargs))
        elif object_type in {'table', 'view'}:
            self.create_relation(name, config['sql'], object_type, config.get('mode', 'create_if_not_exists'))
        elif object_type == 'execute':
            self.con.sql(config['sql'].strip().rstrip(';'))
        elif object_type == 'iteration':
            self.process_iteration(name)

    def process_with_requires(self, name: str, processed: set[str] | None = None) -> None:
        if name not in self.pipeline:
            raise KeyError(f'Objet absent du pipeline : {name}')
        if processed is None:
            processed = set()
        if name in processed or not self.should_process(name):
            return
        for dependency in self.pipeline[name].get('requires', []):
            self.process_with_requires(dependency, processed)
        self.process(name)
        processed.add(name)

    def p_table_view(self, name: str):
        if self.pipeline[name]['type'] in {'execute', 'iteration'}:
            raise TypeError(f'{name} n est pas une table ou une vue')
        self.process_with_requires(name)
        return self.table_view(name)

    def p_iteration(self, name: str) -> None:
        if self.pipeline[name]['type'] != 'iteration':
            raise TypeError(f'{name} n est pas une iteration')
        self.process_with_requires(name)

    @staticmethod
    def sql_string(value: Any) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    def replace_step_view(self, step_view: str, row: dict[str, Any]) -> None:
        scenario_id = self.sql_string(row['scenario_id'])
        natures = row.get('scenario_removed_natures')
        if natures is None:
            natures = []
        elif hasattr(natures, 'tolist'):
            natures = natures.tolist()
        array_sql = ', '.join(self.sql_string(value) for value in natures)
        self.con.sql(f"""CREATE OR REPLACE TEMP VIEW \"{step_view}\" AS
            SELECT {scenario_id}::VARCHAR AS scenario_id,
                   [{array_sql}]::VARCHAR[] AS scenario_removed_natures""")

    def process_iteration(self, name: str) -> None:
        config = self.pipeline[name]
        scenarios_name = config['scenarios']
        step_view = config['step_view']
        target = config['target']
        order_by = config.get('order_by', [])
        order_sql = ' ORDER BY ' + ', '.join(order_by) if order_by else ''
        scenarios = self.con.sql(f'SELECT * FROM "{scenarios_name}"{order_sql}').df()

        completed_table = config.get('completed_table')
        completed_key = config.get('completed_key', 'scenario_id')
        completed_ids: set[str] = set()
        if completed_table and self.table_exists(completed_table):
            completed_group_key = config.get('completed_group_key')
            expected_count_table = config.get('expected_count_table')
            if completed_group_key and expected_count_table:
                completed_ids = {
                    str(row[0]) for row in self.con.sql(
                        f'''SELECT "{completed_key}"
                            FROM "{completed_table}"
                            GROUP BY "{completed_key}"
                            HAVING COUNT(DISTINCT "{completed_group_key}") =
                                   (SELECT COUNT(*) FROM "{expected_count_table}")'''
                    ).fetchall()
                }
            else:
                completed_ids = {
                    str(row[0]) for row in self.con.sql(
                        f'SELECT DISTINCT "{completed_key}" FROM "{completed_table}"'
                    ).fetchall()
                }
        pending = scenarios[~scenarios['scenario_id'].astype(str).isin(completed_ids)].copy()
        total = len(scenarios)
        done = total - len(pending)
        logging.info('Scenarios total : %s | deja calcules : %s | a simuler : %s', total, done, len(pending))
        started = time.perf_counter()
        for index, row in enumerate(pending.to_dict(orient='records'), start=1):
            scenario_started = time.perf_counter()
            scenario_id = str(row['scenario_id'])
            logging.info('Scenario %s/%s | id=%s | debut', index, len(pending), scenario_id[:12])
            self.replace_step_view(step_view, row)
            self.process_with_requires(target, processed=set())
            duration = time.perf_counter() - scenario_started
            elapsed = time.perf_counter() - started
            remaining = (elapsed / index) * (len(pending) - index) if index else 0
            logging.info('Scenario %s/%s | id=%s | duree=%.1fs | reste_estime=%.1fs', index, len(pending), scenario_id[:12], duration, remaining)

    def refresh_scenarios(self, scenarios_df: pd.DataFrame) -> None:
        name = '__scenarios_refresh'
        try:
            self.con.unregister(name)
        except Exception:
            pass
        self.con.register(name, scenarios_df)
        self.con.sql('DROP TABLE IF EXISTS t_scenarios')
        self.con.sql(f"""CREATE TABLE t_scenarios AS
            SELECT CAST(scenario_id AS VARCHAR) AS scenario_id,
                   FROM_JSON(scenario_removed_natures_json, '[\"VARCHAR\"]') AS scenario_removed_natures
            FROM {name}
            ORDER BY scenario_id""")


class ScenarioGenerator:
    GROUPS = {
        'categorie': ('t_rank_nature_by_categorie', 't_rank_categorie', 'categorie'),
        'gamme': ('t_rank_nature_by_gamme', 't_rank_gamme', 'gamme'),
        'type': ('t_rank_nature_by_type', 't_rank_type', 'type'),
        'marque': ('t_rank_nature_by_marque', 't_rank_marque', 'marque'),
        'fournisseur': ('t_rank_nature_by_fournisseur', 't_rank_fournisseur', 'fournisseur'),
    }

    def __init__(self, cp: ConnectionPipeline, output_excel_path: str | Path = 'data/scenarios.xlsx'):
        self.cp = cp
        self.output_excel_path = Path(output_excel_path).expanduser().resolve()
        self.output_excel_path.parent.mkdir(parents=True, exist_ok=True)
        self._scenarios: set[tuple[str, ...]] = {()}

    @staticmethod
    def canonical_natures(values: Iterable[Any]) -> tuple[str, ...]:
        clean = {str(value).strip() for value in values if value is not None and not pd.isna(value) and str(value).strip()}
        return tuple(sorted(clean, key=lambda value: (value.casefold(), value)))

    @staticmethod
    def scenario_hash(values: tuple[str, ...]) -> str:
        payload = json.dumps(list(values), ensure_ascii=False, separators=(',', ':'))
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def add(self, values: Iterable[Any]) -> None:
        self._scenarios.add(self.canonical_natures(values))

    def add_cumulative(self, values: list[str], include_full_removal: bool) -> None:
        stop = len(values) if include_full_removal else max(0, len(values) - 1)
        for size in range(1, stop + 1):
            self.add(values[:size])

    def generate_rank_scenarios(self, include_full_removal: bool = True) -> None:
        global_df = self.cp.p_table_view('t_rank_nature').df()
        for _, hotel_df in global_df.groupby('hotel_code', sort=True):
            ordered = hotel_df.sort_values(['rang_nature', 'nature'])['nature'].tolist()
            self.add_cumulative(ordered, include_full_removal)

        for group_name, (nature_table, group_table, group_column) in self.GROUPS.items():
            nature_df = self.cp.p_table_view(nature_table).df()
            for _, group_df in nature_df.groupby(['hotel_code', group_column], sort=True, dropna=False):
                ordered = group_df.sort_values(['rang_nature', 'nature'])['nature'].tolist()
                self.add_cumulative(ordered, include_full_removal)

            group_df = self.cp.p_table_view(group_table).df()
            for _, hotel_df in group_df.groupby('hotel_code', sort=True):
                cumulative: list[str] = []
                rows = hotel_df.sort_values([f'rang_{group_name}', group_column]).to_dict(orient='records')
                stop = len(rows) if include_full_removal else max(0, len(rows) - 1)
                for row in rows[:stop]:
                    cumulative.extend(list(row['natures']))
                    self.add(cumulative)

    def dataframe(self) -> pd.DataFrame:
        ordered = sorted(self._scenarios, key=lambda values: (len(values), tuple(v.casefold() for v in values), values))
        return pd.DataFrame({
            'scenario_id': [self.scenario_hash(values) for values in ordered],
            'scenario_removed_natures_json': [json.dumps(list(values), ensure_ascii=False) for values in ordered],
        })

    def write_excel(self) -> pd.DataFrame:
        df = self.dataframe()
        df.to_excel(self.output_excel_path, index=False)
        return df


def main(
    db_con_str: str | Path = 'duckdb/pilotes/sim_v2/sim_v2.duckdb',
    pipeline_path: str | Path = 'config',
    scenarios_excel_path: str | Path = 'data/scenarios.xlsx',
    include_full_removal: bool = True,
) -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s', force=True)
    cp = ConnectionPipeline(db_con_str, pipeline_path)
    generator = ScenarioGenerator(cp, scenarios_excel_path)
    generator.generate_rank_scenarios(include_full_removal=include_full_removal)
    scenarios = generator.write_excel()
    cp.refresh_scenarios(scenarios)
    cp.p_iteration('i_iteration_scenario')
    result = cp.table_view('t_dataset_pivot')
    return {
        'cp': cp,
        'scenario_generator': generator,
        'scenarios': scenarios,
        'result': result,
        'stats': {
            'scenario_count': len(scenarios),
            'result_count': result.count('*').fetchone()[0],
        },
    }


if __name__ == '__main__':
    simulation = main()
    print(simulation['stats'])
