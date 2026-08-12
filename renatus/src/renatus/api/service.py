"""
Service API renatus : facade POO autour de ConnectionPipeline.

Deux facades equivalentes (contrats tests) :
  - RenatusService(db, pipeline) — context manager, health()/list_pipeline()
  - RenatusApiRuntime(db, pipelines).service — PipelineApiService

Les methodes acceptent limit= ou max_rows= ; health avec ou sans args.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from renatus.pipeline import ConnectionPipeline

from .schemas import (
    ActionResponse,
    HealthResponse,
    PipelineListResponse,
    PipelineStepDetailResponse,
    PipelineStepInfo,
    RelationDataResponse,
    RelationInfoResponse,
)


class RelationSerializer:
    """
    Serialise une relation DuckDB.

    Constructeurs acceptes :
      RelationSerializer(max_rows=N)
      RelationSerializer(default_limit=N, max_limit=M)
    serialize(..., limit=) ou serialize(..., max_rows=)
    """

    DEFAULT_LIMIT = 200
    MAX_LIMIT = 5000
    DEFAULT_MAX_ROWS = 10_000

    def __init__(
        self,
        max_rows: int | None = None,
        default_limit: int | None = None,
        max_limit: int = MAX_LIMIT,
    ) -> None:
        if max_rows is not None:
            if max_rows < 1:
                raise ValueError("max_rows doit etre >= 1")
            self.default_limit = max_rows
            self.max_limit = max(max_rows, max_limit)
            self.max_rows = max_rows
        else:
            dl = self.DEFAULT_LIMIT if default_limit is None else default_limit
            if dl < 1:
                raise ValueError("default_limit doit etre >= 1")
            if max_limit < 1:
                raise ValueError("max_limit doit etre >= 1")
            self.default_limit = dl
            self.max_limit = max_limit
            self.max_rows = dl

    def resolve_limit(
        self,
        limit: int | None = None,
        max_rows: int | None = None,
    ) -> int:
        value = limit if limit is not None else max_rows
        if value is None:
            return self.default_limit
        value = int(value)
        if value < 1:
            raise ValueError("max_rows/limit doit etre >= 1")
        if value > self.max_limit and self.max_limit < self.DEFAULT_MAX_ROWS:
            # plafond strict seulement si max_limit explicite bas (contrat limit)
            raise ValueError(
                f"limit {value} depasse le maximum autorise ({self.max_limit})"
            )
        return value

    def serialize(
        self,
        relation: Any,
        name: str,
        limit: int | None = None,
        max_rows: int | None = None,
        *,
        offset: int = 0,
        with_total: bool = True,
    ) -> RelationDataResponse:
        """
        Serialise une page de lignes.

        F0123: ``offset`` + ``limit`` = pagination (defaut UI View: limit=3).
        ``total_rows`` via COUNT(*) pour naviguer sans charger toute la table.
        """
        resolved = self.resolve_limit(limit=limit, max_rows=max_rows)
        off = max(0, int(offset or 0))
        columns = [col[0] for col in relation.description]

        total_rows: int | None = None
        if with_total:
            try:
                total_rows = int(
                    relation.aggregate("count(*)").fetchone()[0]
                )
            except Exception:
                total_rows = None

        # DuckDB: Relation.limit(n, offset)
        try:
            page_rel = relation.limit(resolved, off)
        except TypeError:
            # repli SQL-like si signature differente
            page_rel = relation.limit(resolved + off)
            raw_all = page_rel.fetchall()
            raw_rows = raw_all[off : off + resolved]
            truncated = (
                total_rows is not None and (off + len(raw_rows)) < total_rows
            ) or (total_rows is None and len(raw_all) > off + resolved)
            rows = [
                [self._jsonable(cell) for cell in row] for row in raw_rows
            ]
            page = (off // resolved) + 1 if resolved else 1
            total_pages = (
                max(1, (total_rows + resolved - 1) // resolved)
                if total_rows is not None and resolved
                else None
            )
            return RelationDataResponse(
                ok=True,
                name=name,
                columns=columns,
                rows=rows,
                row_count=len(rows),
                truncated=bool(truncated),
                limit=resolved,
                offset=off,
                total_rows=total_rows,
                page=page,
                page_size=resolved,
                total_pages=total_pages,
            )

        raw_rows = page_rel.fetchall()
        rows = [[self._jsonable(cell) for cell in row] for row in raw_rows]
        if total_rows is not None:
            truncated = (off + len(rows)) < total_rows
        else:
            # sonde une ligne de plus
            try:
                probe = relation.limit(1, off + resolved).fetchall()
                truncated = len(probe) > 0
            except Exception:
                truncated = len(rows) >= resolved

        page = (off // resolved) + 1 if resolved else 1
        total_pages = (
            max(1, (int(total_rows) + resolved - 1) // resolved)
            if total_rows is not None and resolved
            else None
        )
        return RelationDataResponse(
            ok=True,
            name=name,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=bool(truncated),
            limit=resolved,
            offset=off,
            total_rows=total_rows,
            page=page,
            page_size=resolved,
            total_pages=total_pages,
        )

    @staticmethod
    def _jsonable(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (list, tuple)):
            return [RelationSerializer._jsonable(item) for item in value]
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:
                return str(value)
        if hasattr(value, "item"):
            try:
                return RelationSerializer._jsonable(value.item())
            except Exception:
                pass
        return str(value)


class RenatusService:
    """
    Service metier principal (context manager).

    Usage:
      with RenatusService(db_path, pipeline_path) as svc:
          svc.p_table_view("v_sales")
    """

    def __init__(
        self,
        db_path: str | Path,
        pipeline_path: str | Path,
        *,
        read_only: bool = False,
        max_rows: int = RelationSerializer.DEFAULT_MAX_ROWS,
        default_limit: int | None = None,
        max_limit: int = RelationSerializer.MAX_LIMIT,
    ) -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.pipeline_path = Path(pipeline_path).expanduser().resolve()
        self.pipelines_dir = self.pipeline_path
        self.read_only = read_only
        if default_limit is not None:
            self._serializer = RelationSerializer(
                default_limit=default_limit,
                max_limit=max_limit,
            )
        else:
            self._serializer = RelationSerializer(max_rows=max_rows)
        self._lock = threading.RLock()
        self._connection: ConnectionPipeline | None = None

    def open(self) -> RenatusService:
        with self._lock:
            if self._connection is None:
                self._connection = ConnectionPipeline(
                    self.db_path,
                    self.pipeline_path,
                    read_only=self.read_only,
                )
        return self

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def __enter__(self) -> RenatusService:
        return self.open()

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def connection(self) -> ConnectionPipeline:
        if self._connection is None:
            raise RuntimeError(
                "RenatusService non ouvert : appelez open() ou use with"
            )
        return self._connection

    def health(
        self,
        db_path: Path | str | None = None,
        pipelines_dir: Path | str | None = None,
        read_only: bool | None = None,
    ) -> HealthResponse:
        """
        Sans args : contrat RenatusService (status=up).
        Avec args : contrat PipelineApiService (status=ok).
        """
        with self._lock:
            if db_path is None:
                db_s = str(self.db_path)
                pipe_s = str(self.pipeline_path)
                ro = self.read_only
                status = "up"
            else:
                db_s = str(Path(db_path))
                pipe_s = str(
                    Path(
                        pipelines_dir
                        if pipelines_dir is not None
                        else self.pipelines_dir
                    )
                )
                ro = self.read_only if read_only is None else bool(read_only)
                status = "ok"
            return HealthResponse(
                ok=True,
                status=status,
                db_path=db_s,
                pipeline_path=pipe_s,
                pipelines_dir=pipe_s,
                read_only=ro,
                step_count=len(self.connection.pipeline),
            )

    def list_pipeline(self) -> PipelineListResponse:
        with self._lock:
            steps: list[PipelineStepInfo] = []
            for name, config in sorted(self.connection.pipeline.items()):
                steps.append(
                    PipelineStepInfo(
                        name=name,
                        type=str(config.get("type", "unknown")),
                        requires=list(config.get("requires") or []),
                        mode=config.get("mode"),
                    )
                )
            return PipelineListResponse(
                ok=True, steps=steps, count=len(steps)
            )

    def list_steps(self) -> PipelineListResponse:
        """Alias list_pipeline (contrat RenatusApiRuntime)."""
        return self.list_pipeline()

    def pipeline_step(self, name: str) -> PipelineStepDetailResponse:
        with self._lock:
            if name not in self.connection.pipeline:
                raise KeyError(f"Objet absent du pipeline : {name}")
            return PipelineStepDetailResponse(
                ok=True,
                name=name,
                config=dict(self.connection.pipeline[name]),
            )

    def relation_info(self, name: str) -> RelationInfoResponse:
        with self._lock:
            con = self.connection
            is_table = con.table_exists(name)
            is_view = con.view_exists(name)
            kind: str | None = None
            if is_table:
                kind = "table"
            elif is_view:
                kind = "view"
            return RelationInfoResponse(
                ok=True,
                name=name,
                exists=is_table or is_view,
                kind=kind,
            )

    def relation_exists(self, name: str) -> RelationInfoResponse:
        """Alias relation_info (contrat RenatusApiRuntime)."""
        return self.relation_info(name)

    def p_table_view(
        self,
        name: str,
        limit: int | None = None,
        max_rows: int | None = None,
        *,
        offset: int = 0,
    ) -> RelationDataResponse:
        with self._lock:
            if name not in self.connection.pipeline:
                raise KeyError(f"Objet absent du pipeline : {name}")
            relation = self.connection.p_table_view(name)
            return self._serializer.serialize(
                relation,
                name,
                limit=limit,
                max_rows=max_rows,
                offset=offset,
            )

    def table_view(
        self,
        name: str,
        limit: int | None = None,
        max_rows: int | None = None,
        *,
        offset: int = 0,
    ) -> RelationDataResponse:
        with self._lock:
            # name peut etre l id de step (YAML) ou deja le nom de relation
            if name in self.connection.pipeline:
                relation_name = self.connection.relation_name(name)
            else:
                relation_name = name
            if not self.connection.relation_exists(relation_name):
                raise LookupError(
                    f"Relation absente de la base : {relation_name} "
                    "(table_view ne cree pas de dependances; "
                    "utilisez p_table_view pour le lineage)"
                )
            relation = self.connection.table_view(relation_name)
            return self._serializer.serialize(
                relation,
                relation_name,
                limit=limit,
                max_rows=max_rows,
                offset=offset,
            )

    def process(self, name: str) -> ActionResponse:
        with self._lock:
            if name not in self.connection.pipeline:
                raise KeyError(f"Objet absent du pipeline : {name}")
            self.connection.process(name)
            return ActionResponse(
                ok=True,
                action="process",
                name=name,
                message=f"OK process {name}",
            )

    def process_with_requires(self, name: str) -> ActionResponse:
        with self._lock:
            if name not in self.connection.pipeline:
                raise KeyError(f"Objet absent du pipeline : {name}")
            self.connection.process_with_requires(name)
            return ActionResponse(
                ok=True,
                action="process_with_requires",
                name=name,
                message=f"OK process_with_requires {name}",
            )

    def p_iteration(self, name: str) -> ActionResponse:
        with self._lock:
            if name not in self.connection.pipeline:
                raise KeyError(f"Objet absent du pipeline : {name}")
            self.connection.p_iteration(name)
            return ActionResponse(
                ok=True,
                action="p_iteration",
                name=name,
                message=f"OK p_iteration {name}",
            )


# Alias : le service est aussi le "PipelineApiService" du runtime
PipelineApiService = RenatusService


class RenatusApiRuntime:
    """
    Runtime db + pipelines_dir exposant .service (RenatusService).

    with RenatusApiRuntime(db, pipelines) as runtime:
        runtime.service.list_steps()
    """

    def __init__(
        self,
        db_path: str | Path,
        pipelines_dir: str | Path,
        *,
        read_only: bool = False,
        max_rows: int = RelationSerializer.DEFAULT_MAX_ROWS,
    ) -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.pipelines_dir = Path(pipelines_dir).expanduser().resolve()
        self.pipeline_path = self.pipelines_dir
        self.read_only = read_only
        self.max_rows = max_rows
        self._service = RenatusService(
            self.db_path,
            self.pipelines_dir,
            read_only=read_only,
            max_rows=max_rows,
        )

    @property
    def service(self) -> RenatusService:
        return self._service

    @property
    def connection(self) -> ConnectionPipeline:
        return self._service.connection

    def start(self) -> RenatusService:
        self._service.open()
        return self._service

    def stop(self) -> None:
        self._service.close()

    def __enter__(self) -> RenatusApiRuntime:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()
