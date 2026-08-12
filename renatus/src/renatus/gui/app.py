"""
Application FastAPI Renatus GUI : UI statique + routes /gui/*.

Reutilise les patterns d'erreurs de renatus.api.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

import yaml

from renatus.api.service import RelationSerializer

from .service import GuiService


def _static_dir() -> Path:
    return Path(__file__).resolve().parent / "static"


def _doc_dir() -> Path | None:
    """
    Dossier documentation HTML (F0109).

    Cherche doc/documentation.html a la racine du depot (install editable)
    ou sous le package (static/docs) en secours.
    """
    here = Path(__file__).resolve().parent
    candidates = [
        # src/renatus/gui -> repo root /doc
        here.parents[2] / "doc",
        # si package a la racine sans src/
        here.parents[1] / "doc",
        # fallback emballe dans static
        here / "static" / "docs",
    ]
    for cand in candidates:
        if (cand / "documentation.html").is_file():
            return cand
    return None


def _error_body(detail: str) -> dict[str, Any]:
    return {"ok": False, "error": detail, "detail": detail}


def _map_status(exc: Exception) -> int:
    if isinstance(exc, PermissionError):
        return 403
    if isinstance(exc, (KeyError, LookupError)):
        return 404
    if isinstance(exc, (TypeError, ValueError, yaml.YAMLError)):
        return 400
    return 500


def _exc_detail(exc: Exception) -> str:
    if isinstance(exc, KeyError):
        return str(exc).strip("'\"")
    if isinstance(exc, yaml.YAMLError):
        # Message actionnable pour corriger le fichier YAML (F0020)
        mark = getattr(exc, "problem_mark", None)
        problem = getattr(exc, "problem", None) or str(exc)
        if mark is not None:
            return (
                f"Erreur parsing YAML (ligne {mark.line + 1}, "
                f"colonne {mark.column + 1}): {problem}"
            )
        return f"Erreur parsing YAML: {problem}"
    return str(exc)


def _raise_http(exc: Exception) -> None:
    raise HTTPException(
        status_code=_map_status(exc),
        detail=_exc_detail(exc),
    ) from exc


def _get_gui(request: Request) -> GuiService:
    gui: GuiService | None = getattr(request.app.state, "gui", None)
    if gui is None:
        raise RuntimeError("GuiService non initialise")
    return gui


class ConnectBody(BaseModel):
    db_path: str
    pipeline_path: str
    read_only: bool = False


class ProjectSaveBody(BaseModel):
    path: str | None = None
    name: str | None = None


class ProjectOpenBody(BaseModel):
    path: str


class ProjectInspectBody(BaseModel):
    path: str


class ProjectCreateBody(BaseModel):
    path: str
    name: str | None = None
    db_path: str | None = None
    pipeline_path: str | None = None
    read_only: bool = False


class ProjectResumeBody(BaseModel):
    branch: str


class ChangelogApplyBody(BaseModel):
    """Apply forward-only: mode=file (un fichier) ou all (snapshot)."""

    commit: str
    mode: str = "file"  # file | all
    path: str | None = None


class StepPutBody(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    tab: str | None = None


class StepCreateBody(BaseModel):
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    tab: str | None = None


class TabCreateBody(BaseModel):
    name: str


class ZoneShareBody(BaseModel):
    """F0060: partager / retirer un objet d une zone (copie FS)."""

    zone_tab: str = Field(
        ...,
        min_length=1,
        description="Id onglet zone (ex. zone1 ou etl/sub)",
    )


class YamlTextBody(BaseModel):
    yaml: str = ""


class ConfigBody(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class ImportFlowBody(BaseModel):
    """F0102: import fichier YAML ou dossier de flux."""

    source: str = Field(..., min_length=1, description="Chemin fichier ou dossier")
    target_tab: str | None = Field(
        default=None,
        description="Zone cible (defaut = onglet actif)",
    )
    conflict: str = Field(
        default="keep_both",
        description="keep_both | keep_existing | replace",
    )
    dry_run: bool = False


class AutoZoneCreateBody(BaseModel):
    """F0139: template Auto → zone physique (init)."""

    type: str = Field(
        ...,
        description="flatzone|allzone|backzone|forzone|bidzone",
    )
    object: str | None = Field(
        default=None, description="Composant de reference (bac/for/bid)"
    )
    parent: str | None = Field(
        default=None,
        description="Zone parent source (flatzone) — id ou path",
    )
    label: str | None = None
    name: str | None = Field(
        default=None, description="Id de la zone creee (optionnel)"
    )


class AutoZoneConvertBody(BaseModel):
    """F0128: convert auto → zone physique."""

    new_zone_id: str | None = None
    name: str | None = None


class PythonSessionExecBody(BaseModel):
    """F0137: exec code dans le noyau session (notebook)."""

    code: str = ""
    venv: str | None = None
    step_id: str | None = None
    timeout: float | None = None


class GuiApp:
    """Constructeur POO de l'app FastAPI GUI."""

    def __init__(
        self,
        db_path: str | Path,
        pipeline_path: str | Path,
        *,
        read_only: bool = False,
        max_rows: int = RelationSerializer.DEFAULT_MAX_ROWS,
        title: str = "renatus GUI",
        version: str = "0.1.0",
    ) -> None:
        self.gui = GuiService(
            db_path,
            pipeline_path,
            read_only=read_only,
            max_rows=max_rows,
        )
        self.title = title
        self.version = version
        self._app: FastAPI | None = None

    def build(self) -> FastAPI:
        if self._app is not None:
            return self._app

        gui = self.gui
        static_dir = _static_dir()

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            gui.open()
            app.state.gui = gui
            try:
                yield
            finally:
                gui.close()

        app = FastAPI(
            title=self.title,
            version=self.version,
            description="Renatus GUI — GUI web pipeline DuckDB + YAML",
            lifespan=lifespan,
        )
        app.state.gui = gui

        self._register_exception_handlers(app)
        self._register_routes(app, static_dir)
        self._app = app
        return app

    def _register_exception_handlers(self, app: FastAPI) -> None:
        @app.exception_handler(StarletteHTTPException)
        async def http_exception_handler(
            request: Request,
            exc: StarletteHTTPException,
        ) -> JSONResponse:
            detail = exc.detail
            msg = detail if isinstance(detail, str) else str(detail)
            return JSONResponse(
                status_code=exc.status_code,
                content=_error_body(msg),
            )

        @app.exception_handler(RequestValidationError)
        async def validation_handler(
            request: Request,
            exc: RequestValidationError,
        ) -> JSONResponse:
            return JSONResponse(
                status_code=422,
                content=_error_body(str(exc.errors())),
            )

        @app.exception_handler(Exception)
        async def unhandled_handler(
            request: Request,
            exc: Exception,
        ) -> JSONResponse:
            return JSONResponse(
                status_code=_map_status(exc),
                content=_error_body(_exc_detail(exc)),
            )

    def _register_routes(self, app: FastAPI, static_dir: Path) -> None:
        index_path = static_dir / "index.html"

        def _index() -> HTMLResponse:
            if not index_path.is_file():
                raise HTTPException(
                    status_code=500,
                    detail=f"index.html introuvable: {index_path}",
                )
            return HTMLResponse(
                index_path.read_text(encoding="utf-8"),
                media_type="text/html; charset=utf-8",
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate",
                    "Pragma": "no-cache",
                },
            )

        @app.get("/", tags=["ui"], response_class=HTMLResponse)
        def root_ui() -> HTMLResponse:
            return _index()

        @app.get("/gui", tags=["ui"], response_class=HTMLResponse)
        def gui_ui() -> HTMLResponse:
            return _index()

        @app.get("/gui/", tags=["ui"], response_class=HTMLResponse)
        def gui_ui_slash() -> HTMLResponse:
            return _index()

        if static_dir.is_dir():
            app.mount(
                "/gui/static",
                StaticFiles(directory=str(static_dir)),
                name="gui-static",
            )

        @app.get("/gui/static/index.html", include_in_schema=False)
        def static_index_alias() -> FileResponse:
            return FileResponse(index_path)

        # F0109: documentation HTML (UML, guides) servie par renatus-gui
        doc_dir = _doc_dir()
        if doc_dir is not None:
            app.mount(
                "/gui/docs",
                StaticFiles(directory=str(doc_dir), html=True),
                name="gui-docs",
            )

        @app.get("/gui/documentation", tags=["ui"], include_in_schema=False)
        def gui_documentation_redirect() -> RedirectResponse:
            """Raccourci stable vers la doc HTML."""
            if _doc_dir() is None:
                raise HTTPException(
                    status_code=404,
                    detail="documentation.html introuvable (doc/)",
                )
            return RedirectResponse(
                url="/gui/docs/documentation.html",
                status_code=307,
            )

        @app.post("/gui/connect", tags=["gui"])
        def gui_connect(
            body: ConnectBody,
            request: Request,
        ) -> dict[str, Any]:
            try:
                gui = _get_gui(request)
                gui.connect(
                    body.db_path,
                    body.pipeline_path,
                    read_only=body.read_only,
                )
                return gui.workspace_info()
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.get("/gui/workspace", tags=["gui"])
        def gui_workspace(request: Request) -> dict[str, Any]:
            try:
                return _get_gui(request).workspace_info()
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.get("/gui/project", tags=["gui"])
        def gui_project_info(request: Request) -> dict[str, Any]:
            """Etat du projet courant (chemins db / pipelines)."""
            try:
                return _get_gui(request).project_info()
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/project/save", tags=["gui"])
        def gui_project_save(
            body: ProjectSaveBody,
            request: Request,
        ) -> dict[str, Any]:
            """
            Sauvegarde un fichier .renatus.yaml (db_path + pipeline_path).
            """
            try:
                return _get_gui(request).save_project(
                    body.path,
                    name=body.name,
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/project/open", tags=["gui"])
        def gui_project_open(
            body: ProjectOpenBody,
            request: Request,
        ) -> dict[str, Any]:
            """Ouvre un fichier ou dossier projet et reconnecte le workspace."""
            try:
                return _get_gui(request).open_project(body.path)
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/project/inspect", tags=["gui"])
        def gui_project_inspect(
            body: ProjectInspectBody,
            request: Request,
        ) -> dict[str, Any]:
            """
            Inspecte un chemin projet (existant vs nouveau) pour l UI (F0036).
            """
            try:
                return _get_gui(request).inspect_project_path(body.path)
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/project/create", tags=["gui"])
        def gui_project_create(
            body: ProjectCreateBody,
            request: Request,
        ) -> dict[str, Any]:
            """
            Cree un nouveau projet: .renatus.yaml + db + pipelines (F0036).
            """
            try:
                return _get_gui(request).create_project(
                    body.path,
                    name=body.name,
                    db_path=body.db_path,
                    pipeline_path=body.pipeline_path,
                    read_only=body.read_only,
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/project/resume", tags=["gui"])
        def gui_project_resume(
            body: ProjectResumeBody,
            request: Request,
        ) -> dict[str, Any]:
            """Charge une branche de travail (modifs non fusionnees)."""
            try:
                return _get_gui(request).resume_project_branch(body.branch)
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.get("/gui/changelog", tags=["gui"])
        def gui_changelog(
            request: Request,
            limit: int = Query(default=50, ge=1, le=200),
            step_id: str | None = Query(default=None),
        ) -> dict[str, Any]:
            """
            Timeline git du projet (F0035 / F0115).

            step_id: filtre aux commits du composant (zone = recursif).
            """
            try:
                return _get_gui(request).project_changelog(
                    limit=limit, step_id=step_id
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/changelog/reset-history", tags=["gui"])
        def gui_changelog_reset_history(
            request: Request,
        ) -> dict[str, Any]:
            """F0115: reinitialise l historique git (repart de zero)."""
            try:
                return _get_gui(request).project_changelog_reset_history()
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.get("/gui/changelog/{commit}", tags=["gui"])
        def gui_changelog_commit(
            commit: str,
            request: Request,
            path: str | None = Query(default=None),
        ) -> dict[str, Any]:
            """Detail d un commit: fichiers + diff du fichier focus."""
            try:
                return _get_gui(request).project_changelog_commit(
                    commit, path=path
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/changelog/apply", tags=["gui"])
        def gui_changelog_apply(
            body: ChangelogApplyBody,
            request: Request,
        ) -> dict[str, Any]:
            """
            Applique un etat passe (forward-only, nouveau commit).

            mode=file: un fichier; mode=all: snapshot complet au commit.
            """
            try:
                return _get_gui(request).project_changelog_apply(
                    body.commit,
                    mode=body.mode,
                    path=body.path,
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.get("/gui/tools", tags=["gui"])
        def gui_tools(request: Request) -> dict[str, Any]:
            try:
                tools = _get_gui(request).tools_catalog()
                return {"ok": True, "tools": tools}
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.get("/gui/graph", tags=["gui"])
        def gui_graph(
            request: Request,
            tab: str | None = Query(default=None),
        ) -> dict[str, Any]:
            """Graphe filtre par onglet (tab=main|etl|... ; *=tout)."""
            try:
                return _get_gui(request).graph(tab=tab)
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.get("/gui/tabs", tags=["gui"])
        def gui_tabs(request: Request) -> dict[str, Any]:
            try:
                return _get_gui(request).list_tabs()
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.get("/gui/import/zones", tags=["gui"])
        def gui_import_zones(request: Request) -> dict[str, Any]:
            """F0102: zones cibles pour import flux."""
            try:
                return _get_gui(request).list_import_zones()
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/import/flow", tags=["gui"])
        def gui_import_flow(
            body: ImportFlowBody,
            request: Request,
        ) -> dict[str, Any]:
            """F0102: importe un YAML ou un dossier de flux."""
            try:
                return _get_gui(request).import_flow(
                    body.source,
                    target_tab=body.target_tab,
                    conflict=body.conflict,
                    dry_run=body.dry_run,
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/auto-zone", tags=["gui"])
        def gui_create_auto_zone(
            body: AutoZoneCreateBody,
            request: Request,
        ) -> dict[str, Any]:
            """F0139: template Auto → zone physique initialisee."""
            try:
                return _get_gui(request).create_auto_zone(
                    body.type,
                    object_id=body.object,
                    parent_id=body.parent,
                    label=body.label,
                    name=body.name,
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/auto-zone/{name}/convert", tags=["gui"])
        def gui_convert_auto_zone(
            name: str,
            request: Request,
            body: AutoZoneConvertBody | None = None,
        ) -> dict[str, Any]:
            """F0128: convertit auto-zone → zone physique (copies YAML)."""
            try:
                b = body or AutoZoneConvertBody()
                return _get_gui(request).convert_auto_zone(
                    name,
                    new_zone_id=b.new_zone_id or b.name,
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.get("/gui/python/session/vars", tags=["gui"])
        def gui_python_session_vars(
            request: Request,
            venv: str | None = None,
            step_id: str | None = None,
        ) -> dict[str, Any]:
            """F0137: variables du noyau Python de session (notebook)."""
            try:
                return _get_gui(request).python_session_vars(
                    venv=venv, step_id=step_id
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/python/session/exec", tags=["gui"])
        def gui_python_session_exec(
            body: PythonSessionExecBody,
            request: Request,
        ) -> dict[str, Any]:
            """F0137: execute du code dans la session (sans build step)."""
            try:
                return _get_gui(request).python_session_exec(
                    body.code,
                    venv=body.venv,
                    step_id=body.step_id,
                    timeout=body.timeout,
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/tabs", tags=["gui"])
        def gui_tabs_create(
            body: TabCreateBody,
            request: Request,
        ) -> dict[str, Any]:
            try:
                return _get_gui(request).create_tab(body.name)
            except Exception as exc:
                _raise_http(exc)
                raise

        # name:path accepte les zones imbriquees (etl/sub) — F0052
        @app.post("/gui/tabs/{name:path}/activate", tags=["gui"])
        def gui_tabs_activate(
            name: str,
            request: Request,
        ) -> dict[str, Any]:
            try:
                return _get_gui(request).set_active_tab(name)
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/tabs/{name:path}/close", tags=["gui"])
        def gui_tabs_close(
            name: str,
            request: Request,
        ) -> dict[str, Any]:
            """Ferme l onglet (UI) sans supprimer la zone (F0052)."""
            try:
                return _get_gui(request).close_tab(name)
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.delete("/gui/tabs/{name:path}", tags=["gui"])
        def gui_tabs_delete(
            name: str,
            request: Request,
        ) -> dict[str, Any]:
            try:
                return _get_gui(request).delete_tab(name)
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.get("/gui/step/{name}", tags=["gui"])
        def gui_get_step(
            name: str,
            request: Request,
        ) -> dict[str, Any]:
            try:
                return _get_gui(request).get_step(name)
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.put("/gui/step/{name}", tags=["gui"])
        def gui_put_step(
            name: str,
            body: StepPutBody,
            request: Request,
        ) -> dict[str, Any]:
            try:
                return _get_gui(request).put_step(
                    name,
                    body.config,
                    tab=body.tab,
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/steps", tags=["gui"])
        def gui_create_step(
            body: StepCreateBody,
            request: Request,
        ) -> dict[str, Any]:
            try:
                return _get_gui(request).create_step(
                    body.name.strip(),
                    body.config,
                    tab=body.tab,
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/step/{name}/share-zone", tags=["gui"])
        def gui_share_zone(
            name: str,
            body: ZoneShareBody,
            request: Request,
        ) -> dict[str, Any]:
            """F0060: duplique le YAML de l objet dans le dossier zone."""
            try:
                return _get_gui(request).share_step_to_zone(
                    name, body.zone_tab
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/step/{name}/unshare-zone", tags=["gui"])
        def gui_unshare_zone(
            name: str,
            body: ZoneShareBody,
            request: Request,
        ) -> dict[str, Any]:
            """
            F0060: retire la copie dans une zone.
            Refuse si c est la seule presence.
            """
            try:
                return _get_gui(request).unshare_step_from_zone(
                    name, body.zone_tab
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.delete("/gui/step/{name}", tags=["gui"])
        def gui_delete_step(
            name: str,
            request: Request,
        ) -> dict[str, Any]:
            try:
                return _get_gui(request).delete_step(name)
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.get("/gui/build/{name}/plan", tags=["gui"])
        def gui_build_plan(
            name: str,
            request: Request,
        ) -> dict[str, Any]:
            """
            F0118: plan de build (zone → jobs ordonnes pour progression UI).
            """
            try:
                gui = _get_gui(request)
                # zone only for now; other types = single job
                pipe = gui.api.connection.pipeline
                cfg = pipe.get(name) or {}
                if str(cfg.get("type") or "") == "zone":
                    return gui.zone_build_plan(name)
                return {
                    "ok": True,
                    "zone_id": None,
                    "step_id": name,
                    "members": [name] if name in pipe else [],
                    "jobs": (
                        [
                            {
                                "id": name,
                                "line": 0,
                                "index": 0,
                                "label": str(
                                    cfg.get("label") or name
                                ),
                                "type": str(cfg.get("type") or ""),
                            }
                        ]
                        if name in pipe
                        else []
                    ),
                    "total": 1 if name in pipe else 0,
                    "workers": "queue",
                    "renatus_mode": None,
                    "flow_lines": 1,
                }
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/build/{name}/complete", tags=["gui"])
        async def gui_build_complete(
            name: str,
            request: Request,
        ) -> dict[str, Any]:
            """
            F0118: finalise un Renatus zone orchestre cote client
            (enregistre renatus_time zone sans re-executer les jobs).
            """
            try:
                body: dict[str, Any] = {}
                try:
                    raw = await request.json()
                    if isinstance(raw, dict):
                        body = raw
                except Exception:
                    body = {}
                elapsed = body.get("elapsed")
                try:
                    elapsed_f = (
                        float(elapsed) if elapsed is not None else None
                    )
                except (TypeError, ValueError):
                    elapsed_f = None
                built = body.get("built")
                if not isinstance(built, list):
                    built = None
                errors = body.get("errors")
                if not isinstance(errors, list):
                    errors = None
                return _get_gui(request).complete_zone_build(
                    name,
                    elapsed=elapsed_f,
                    built=built,
                    errors=errors,
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/build/{name}", tags=["gui"])
        def gui_build(
            name: str,
            request: Request,
            limit: int | None = Query(default=None, ge=1),
            max_rows: int | None = Query(default=None, ge=1),
        ) -> dict[str, Any]:
            try:
                return _get_gui(request).build(
                    name,
                    limit=limit if limit is not None else max_rows,
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.get("/gui/result/{name}", tags=["gui"])
        def gui_result(
            name: str,
            request: Request,
            limit: int | None = Query(default=None, ge=1),
            max_rows: int | None = Query(default=None, ge=1),
            offset: int = Query(default=0, ge=0),
        ) -> dict[str, Any]:
            try:
                return _get_gui(request).result(
                    name,
                    limit=limit if limit is not None else max_rows,
                    offset=offset,
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.get("/gui/preview/{name}", tags=["gui"])
        def gui_preview(
            name: str,
            request: Request,
            limit: int = Query(default=3, ge=1, le=100),
            offset: int = Query(default=0, ge=0),
            page: int | None = Query(default=None, ge=1),
            build: bool = Query(default=False),
        ) -> dict[str, Any]:
            """
            F0123: apercu paginé (datasets). Defaut limit=3, offset=0.
            ``page`` (1-based) optionnel → calcule offset = (page-1)*limit.
            """
            try:
                off = offset
                if page is not None:
                    off = max(0, (int(page) - 1) * int(limit))
                return _get_gui(request).preview(
                    name,
                    limit=limit,
                    offset=off,
                    build_if_missing=build,
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/config/to-yaml", tags=["gui"])
        def gui_config_to_yaml(body: ConfigBody) -> dict[str, Any]:
            try:
                text = GuiService.config_to_yaml(body.config)
                return {"ok": True, "yaml": text}
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/config/from-yaml", tags=["gui"])
        def gui_config_from_yaml(body: YamlTextBody) -> dict[str, Any]:
            try:
                config = GuiService.yaml_to_config(body.yaml)
                return {"ok": True, "config": config}
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.post("/gui/upload", tags=["gui"])
        async def gui_upload(
            request: Request,
            file: UploadFile = File(...),
            subdir: str = Query(default="input"),
            relative_path: str | None = Form(default=None),
        ) -> dict[str, Any]:
            """Upload fichier (picker / drag-drop) vers project_dir/input/.

            F0107: relative_path optionnel pour reconstituer une arborescence
            (import flux dossier).
            """
            try:
                raw = await file.read()
                name = file.filename or "upload.bin"
                return _get_gui(request).upload_input_file(
                    name,
                    raw,
                    subdir=subdir,
                    relative_path=relative_path,
                )
            except Exception as exc:
                _raise_http(exc)
                raise

        @app.get("/health", tags=["meta"])
        def health(request: Request) -> dict[str, Any]:
            try:
                return _get_gui(request).workspace_info()
            except Exception as exc:
                _raise_http(exc)
                raise


def create_gui_app(
    db_path: str | Path,
    pipeline_path: str | Path,
    *,
    read_only: bool = False,
    max_rows: int = RelationSerializer.DEFAULT_MAX_ROWS,
) -> FastAPI:
    """Factory publique de l'application GUI."""
    return GuiApp(
        db_path,
        pipeline_path,
        read_only=read_only,
        max_rows=max_rows,
    ).build()
