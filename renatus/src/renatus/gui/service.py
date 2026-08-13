"""
Service metier Renatus GUI.

Reutilise RenatusService (F0009) pour le moteur DuckDB.
Ajoute : graphe requires, persistance YAML par step, build unifie.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import yaml

from renatus.api.service import RelationSerializer, RenatusService
from renatus.pipeline.project import (
    RenatusProject,
    ensure_pipelines_inside_project,
    find_project_file,
    is_project_file,
    is_under_directory,
    resolve_project_target,
)
from renatus.pipeline.project_git import ProjectGit

from .schemas import (
    GuiConnectResponse,
    GuiSaveResponse,
    GuiStepResponse,
)
from .yaml_store import YamlStepStore


class GuiService:
    """
    Facade gui : connexion, graphe, edition YAML, build, resultats.

    Serialise les appels via le RLock du RenatusService sous-jacent
    et un verrou local pour connect/reload.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        pipeline_path: str | Path | None = None,
        *,
        read_only: bool = False,
        max_rows: int = RelationSerializer.DEFAULT_MAX_ROWS,
    ) -> None:
        self._lock = threading.RLock()
        self._api: RenatusService | None = None
        self._store: YamlStepStore | None = None
        self._max_rows = max_rows
        self._read_only = read_only
        self._project_file: str | None = None
        self._project_name: str | None = None
        self._work_branch: str | None = None
        self._active_tab: str = YamlStepStore.ROOT_TAB
        # F0052: onglets ouverts dans l UI (main toujours present)
        self._open_tabs: list[str] = [YamlStepStore.ROOT_TAB]
        # F0093: duree dernier Renatus (secondes) par step id — hors YAML
        self._renatus_times: dict[str, float] = {}
        if db_path is not None and pipeline_path is not None:
            self.connect(db_path, pipeline_path, read_only=read_only)

    # -- cycle de vie -------------------------------------------------------

    def open(self) -> GuiService:
        with self._lock:
            if self._api is None:
                raise RuntimeError(
                    "GuiService sans chemins : appelez connect() d'abord"
                )
            self._api.open()
            if self._store is None:
                self._store = YamlStepStore(self._api.pipeline_path)
            else:
                self._store.refresh()
        return self

    def close(self) -> None:
        with self._lock:
            if self._api is not None:
                self._api.close()

    def __enter__(self) -> GuiService:
        return self.open()

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def api(self) -> RenatusService:
        if self._api is None:
            raise RuntimeError("GuiService non connecte")
        return self._api

    @property
    def store(self) -> YamlStepStore:
        if self._store is None:
            raise RuntimeError("GuiService non connecte")
        return self._store

    def connect(
        self,
        db_path: str | Path,
        pipeline_path: str | Path,
        *,
        read_only: bool | None = None,
        keep_project: bool = False,
    ) -> GuiConnectResponse:
        """Reconnecte (ferme l'ancienne connexion si besoin)."""
        from renatus.pipeline.workspace import prepare_workspace

        with self._lock:
            ro = self._read_only if read_only is None else bool(read_only)
            if self._api is not None:
                self._api.close()
            self._read_only = ro
            db_ready, pipe_ready = prepare_workspace(
                db_path,
                pipeline_path,
                read_only=ro,
                create=not ro,
            )
            self._api = RenatusService(
                db_ready,
                pipe_ready,
                read_only=ro,
                max_rows=self._max_rows,
            )
            self._api.open()
            self._store = YamlStepStore(self._api.pipeline_path)
            self._active_tab = YamlStepStore.ROOT_TAB
            self._open_tabs = [YamlStepStore.ROOT_TAB]
            self._store.active_tab = self._active_tab
            if not keep_project:
                self._project_file = None
            # F0065: activer git local meme sur workspace defaut
            if not ro:
                try:
                    self._ensure_project_tracking()
                except Exception:
                    pass
            return self.connect_info()

    def connect_info(self) -> GuiConnectResponse:
        with self._lock:
            health = self.api.health()
            return GuiConnectResponse(
                ok=True,
                status=health.status,
                db_path=health.db_path,
                pipeline_path=health.pipeline_path,
                pipelines_dir=health.pipelines_dir,
                read_only=health.read_only,
                step_count=health.step_count,
            )

    def _reload_pipeline(self) -> None:
        """Ferme et rouvre la connexion pour recharger les YAML."""
        api = self.api
        db = api.db_path
        pipe = api.pipeline_path
        ro = api.read_only
        api.close()
        self._api = RenatusService(
            db,
            pipe,
            read_only=ro,
            max_rows=self._max_rows,
        )
        self._api.open()
        self._store = YamlStepStore(pipe)
        self._store.active_tab = self._active_tab

    # -- onglets pipeline (F0027 / F0052) -----------------------------------

    @property
    def active_tab(self) -> str:
        return self._active_tab or YamlStepStore.ROOT_TAB

    def _ensure_open_tabs(self) -> None:
        if not self._open_tabs:
            self._open_tabs = [YamlStepStore.ROOT_TAB]
        if YamlStepStore.ROOT_TAB not in self._open_tabs:
            self._open_tabs.insert(0, YamlStepStore.ROOT_TAB)

    def _open_tab_id(self, tab_id: str) -> None:
        """Ajoute un onglet a la liste ouverte (sans changer l actif)."""
        self._ensure_open_tabs()
        tid = self.store.normalize_tab_id(tab_id)
        if tid not in self._open_tabs:
            self._open_tabs.append(tid)

    def _canonical_zone_tabs(self) -> list[dict[str, Any]]:
        """
        F0138: selecteur Zone = main + **une entree par zone id**.

        Ne liste plus tous les sous-dossiers FS (apres import, des chemins
        fantomes pipeline/x/ml, pipeline/common/ml, pipeline/ml donnaient
        3 fois le label « ml »). Chemin = zone_path canonique du step zone.
        """
        store = self.store
        store.refresh()
        pipe = self.api.connection.pipeline or {}
        # zone_id -> chemin onglet (plus court gagne si ambiguite)
        zone_paths: dict[str, str] = {}
        for name, cfg in pipe.items():
            if not isinstance(cfg, dict):
                continue
            if str(cfg.get("type") or "") != "zone":
                continue
            if name == YamlStepStore.ROOT_TAB:
                continue
            parent_tab = store.tab_of(name)
            zpath = store.zone_path_for(name, parent_tab)
            zpath = str(zpath or name).strip().replace("\\", "/")
            if not zpath or zpath in {
                YamlStepStore.ALL_TAB,
                "*",
                "_all",
                YamlStepStore.AUTO_TAB,
            }:
                continue
            if zpath.startswith(YamlStepStore.AUTO_TAB + "/"):
                continue
            prev = zone_paths.get(name)
            if prev is None or zpath.count("/") < prev.count("/"):
                zone_paths[name] = zpath

        tabs: list[dict[str, Any]] = [store.tab_meta(YamlStepStore.ROOT_TAB)]
        # compte main = objets effectifs si possible
        try:
            tabs[0]["step_count"] = len(
                self.effective_zone_objects(YamlStepStore.ROOT_TAB)
            )
        except Exception:
            pass

        ordered = sorted(
            zone_paths.items(),
            key=lambda kv: (kv[1].count("/"), kv[1].lower(), kv[0].lower()),
        )
        # disambiguation labels: leaf unique → leaf ; sinon chemin complet
        leaf_count: dict[str, int] = {}
        for _zid, zpath in ordered:
            leaf = zpath.split("/")[-1]
            leaf_count[leaf] = leaf_count.get(leaf, 0) + 1

        for zid, zpath in ordered:
            meta = store.tab_meta(zpath)
            leaf = zpath.split("/")[-1]
            if leaf_count.get(leaf, 0) > 1 or "/" in zpath:
                meta["label"] = zpath
            else:
                meta["label"] = str(
                    (pipe.get(zid) or {}).get("label") or leaf
                )
            meta["zone_id"] = zid
            try:
                meta["step_count"] = len(self.effective_zone_objects(zid))
            except Exception:
                pass
            tabs.append(meta)
        return tabs

    def list_tabs(self) -> dict[str, Any]:
        with self._lock:
            from renatus.pipeline.steps.auto_zone import is_auto_zone_type

            self._ensure_open_tabs()
            # F0131 / F0138: main + zones canoniques (1 par id), pas all, pas auto/*
            tabs = self._canonical_zone_tabs()
            pipe = self.api.connection.pipeline or {}
            # Si on visualise une auto-zone (double-clic), l afficher
            # temporairement dans le select (pas listee par defaut).
            active = self.active_tab or YamlStepStore.ROOT_TAB
            existing = {str(t.get("id") or "") for t in tabs}
            if active not in existing and active in pipe:
                acfg = pipe.get(active) or {}
                if is_auto_zone_type(str(acfg.get("type") or "")):
                    tabs.append(
                        {
                            "id": active,
                            "label": str(acfg.get("label") or active),
                            "path": None,
                            "step_count": len(
                                self.effective_zone_objects(active)
                            ),
                            "closable": False,
                            "virtual": True,
                            "auto_zone": True,
                            "zone_id": active,
                        }
                    )
            return {
                "ok": True,
                "tabs": tabs,
                "active_tab": self.active_tab,
                "open_tabs": list(self._open_tabs),
            }

    def set_active_tab(self, tab: str) -> dict[str, Any]:
        """Active un onglet (l ouvre s il existe sur disque)."""
        with self._lock:
            from renatus.pipeline.steps.auto_zone import is_auto_zone_type

            raw = (tab or YamlStepStore.ROOT_TAB).strip() or YamlStepStore.ROOT_TAB
            # F0131: plus de vue calculee "all" dans le selecteur —
            # utiliser le composant allzone (auto-zone) depose dans default.
            if raw in {YamlStepStore.ALL_TAB, "*", "_all"}:
                # compat: redirige vers allzone si present, sinon default
                pipe = self.api.connection.pipeline or {}
                if "allzone" in pipe and is_auto_zone_type(
                    str((pipe.get("allzone") or {}).get("type") or "")
                ):
                    raw = "allzone"
                else:
                    raw = YamlStepStore.ROOT_TAB
            # F0131: auto-zone logique = id step (pas de dossier contenu)
            pipe = self.api.connection.pipeline or {}
            leaf = raw.split("/")[-1] if raw else raw
            acfg = pipe.get(raw) if isinstance(pipe.get(raw), dict) else None
            if acfg is None and leaf != raw:
                acfg = pipe.get(leaf) if isinstance(pipe.get(leaf), dict) else None
            if acfg and is_auto_zone_type(str(acfg.get("type") or "")):
                self._active_tab = raw if raw in pipe else leaf
                # store.active_tab reste un onglet FS (default) pour saves
                return self.list_tabs()
            tab_id = self.store.normalize_tab_id(raw)
            if tab_id != YamlStepStore.ROOT_TAB:
                dest = self.store.dir_for_tab(tab_id)
                if not dest.is_dir():
                    raise KeyError(f"Zone introuvable : {tab_id}")
            self._open_tab_id(tab_id)
            self._active_tab = tab_id
            self.store.active_tab = tab_id
            return self.list_tabs()

    def close_tab(self, name: str) -> dict[str, Any]:
        """
        Ferme un onglet dans l UI sans supprimer la zone (F0052).

        L onglet default (flow) n est pas fermable.
        """
        with self._lock:
            tab_id = self.store.normalize_tab_id(name)
            if not tab_id or tab_id == YamlStepStore.ROOT_TAB:
                raise ValueError(
                    "Impossible de fermer l onglet racine (flow / default)"
                )
            if tab_id == YamlStepStore.ALL_TAB:
                raise ValueError(
                    "Impossible de fermer la vue calculee 'all'"
                )
            self._ensure_open_tabs()
            if tab_id in self._open_tabs:
                self._open_tabs = [t for t in self._open_tabs if t != tab_id]
            if self._active_tab == tab_id:
                self._active_tab = YamlStepStore.ROOT_TAB
                self.store.active_tab = self._active_tab
            return {
                "ok": True,
                "id": tab_id,
                "message": f"Onglet {tab_id} ferme",
                **self.list_tabs(),
            }

    def _close_open_tabs_for_zone(self, zpath: str) -> list[str]:
        """
        F0064: retire de _open_tabs l onglet zone et ses sous-onglets.

        Appeler sous self._lock. Retourne les ids fermes.
        Si l onglet actif etait concerné, bascule sur default.
        """
        path = self.store.normalize_tab_id(zpath)
        if not path or path == YamlStepStore.ROOT_TAB:
            return []
        self._ensure_open_tabs()
        closed: list[str] = []
        kept: list[str] = []
        prefix = path + "/"
        for tid in self._open_tabs:
            if tid == path or tid.startswith(prefix):
                closed.append(tid)
            else:
                kept.append(tid)
        if closed:
            self._open_tabs = kept
            self._ensure_open_tabs()
        active = self._active_tab or YamlStepStore.ROOT_TAB
        if active == path or active.startswith(prefix):
            self._active_tab = YamlStepStore.ROOT_TAB
            self.store.active_tab = self._active_tab
        return closed

    def create_tab(self, name: str) -> dict[str, Any]:
        """
        Cree une zone = sous-dossier + step type zone (F0027 / F0045 / F0052).

        Si l onglet actif n est pas main, cree une sous-zone imbriquee.
        """
        with self._lock:
            if self.api.read_only:
                raise PermissionError(
                    "GUI en lecture seule : creation de zone impossible"
                )
            segment = YamlStepStore.validate_tab_segment(name)
            root = self.api.pipeline_path
            if root.is_file():
                raise ValueError(
                    "Impossible de creer une zone : pipeline est un fichier unique"
                )
            parent_tab = self.active_tab
            zone_path = self.store.zone_path_for(segment, parent_tab)
            dest = self.store.dir_for_tab(zone_path)
            if dest.exists():
                raise ValueError(f"Zone deja presente : {zone_path}")
            dest.mkdir(parents=True, exist_ok=False)

            # Step organisationnelle visible dans le graphe parent
            zone_id = segment
            if zone_id in self.api.connection.pipeline:
                # conflit id global — le dossier est cree, on netoie
                try:
                    dest.rmdir()
                except OSError:
                    pass
                raise ValueError(
                    f"Id deja utilise : {zone_id} "
                    "(l id est unique dans tout le pipeline)"
                )
            cfg = {
                "type": "zone",
                "label": zone_id,
                "objects": {},
                "workers": "auto",
                "renatus_mode": "required_for_leaves",
            }
            path = self.store.save_step(zone_id, cfg, tab=parent_tab)
            self._reload_pipeline()

            self._open_tab_id(zone_path)
            self._active_tab = zone_path
            self.store.active_tab = zone_path
            self._autocommit(
                f"create zone {zone_path}",
                components=[zone_id],
            )
            return {
                "ok": True,
                "id": zone_path,
                "zone_id": zone_id,
                "path": str(dest.resolve()),
                "file_origin": str(path),
                "message": f"Zone {zone_path} creee",
                **self.list_tabs(),
            }

    def delete_tab(self, name: str) -> dict[str, Any]:
        """Supprime une zone vide (pas main) et retire l onglet."""
        with self._lock:
            if self.api.read_only:
                raise PermissionError(
                    "GUI en lecture seule : suppression d onglet impossible"
                )
            tab_id = self.store.normalize_tab_id(name)
            if tab_id in {
                YamlStepStore.ROOT_TAB,
                YamlStepStore.LEGACY_ROOT_TAB,
            }:
                raise ValueError(
                    f"Impossible de supprimer l onglet {YamlStepStore.ROOT_TAB}"
                )
            steps = self.store.steps_in_tab(tab_id)
            if steps:
                raise ValueError(
                    f"Onglet {tab_id} non vide ({len(steps)} step(s)) ; "
                    "supprimez les steps d abord"
                )
            dest = self.store.dir_for_tab(tab_id)
            if dest.is_dir():
                remaining = list(dest.iterdir())
                if remaining:
                    raise ValueError(
                        f"Onglet {tab_id} contient encore des fichiers"
                    )
                dest.rmdir()
            # retire le yaml type zone (parent) s il pointe vers ce dossier
            zone_name = tab_id.split("/")[-1]
            if zone_name in self.api.connection.pipeline:
                zcfg = self.api.connection.pipeline.get(zone_name) or {}
                if str(zcfg.get("type") or "") == "zone":
                    origin = self.store.origin_of(zone_name)
                    if origin is not None and origin.is_file():
                        try:
                            content = yaml.safe_load(
                                origin.read_text(encoding="utf-8")
                            ) or {}
                            if isinstance(content, dict) and zone_name in content:
                                del content[zone_name]
                                if content:
                                    origin.write_text(
                                        yaml.dump(
                                            content,
                                            default_flow_style=False,
                                            allow_unicode=True,
                                            sort_keys=False,
                                        ),
                                        encoding="utf-8",
                                    )
                                else:
                                    origin.unlink(missing_ok=True)
                        except OSError:
                            pass
                    self._reload_pipeline()
            if tab_id in self._open_tabs:
                self._open_tabs = [t for t in self._open_tabs if t != tab_id]
            if self._active_tab == tab_id:
                self._active_tab = YamlStepStore.ROOT_TAB
                self.store.active_tab = self._active_tab
            self.store.refresh()
            return {
                "ok": True,
                "id": tab_id,
                "message": f"Onglet {tab_id} supprime",
                **self.list_tabs(),
            }

    # -- graphe -------------------------------------------------------------

    def graph(self, tab: str | None = None) -> dict[str, Any]:
        """
        Graphe des steps.

        Si tab est fourni (ou active_tab), ne renvoie que les noeuds de
        cet onglet et les aretes internes (F0027).
        tab="*" ou tab="_all" : graphe complet.
        """
        from renatus.gui.services import GraphOps

        with self._lock:
            return GraphOps(self).build(tab)

    # -- steps config -------------------------------------------------------

    def dependents_of(self, step_id: str) -> list[dict[str, Any]]:
        """
        Dependances inverses calculees (F0041).

        Steps dont requires contient step_id.
        Non stocke dans le YAML : derive du graphe requires.
        """
        pipeline = self.api.connection.pipeline
        sid = str(step_id)
        out: list[dict[str, Any]] = []
        for name, config in pipeline.items():
            if not isinstance(config, dict):
                continue
            reqs = config.get("requires") or []
            hit = False
            for r in reqs:
                if str(r) == sid:
                    hit = True
                    break
            if not hit:
                continue
            out.append(
                {
                    "id": name,
                    "label": str(config.get("label") or name),
                    "type": str(config.get("type") or "unknown"),
                    "tab": self.store.tab_of(name),
                }
            )
        out.sort(key=lambda x: (x.get("tab") or "", x.get("label") or x["id"]))
        return out

    def effective_zone_objects(self, zone_id: str) -> dict[str, Any]:
        """
        Membres effectifs d une zone (A0015 / F0056 / F0060 / F0128).

        Union de:
        - config.objects declares dans le YAML de la zone
        - steps presents dans le dossier FS de la zone (steps_in_tab)

        F0128 auto-zone: membership purement calcule (pas de FS contenu).
        """
        from renatus.pipeline.steps.auto_zone import (
            compute_auto_zone_members,
            is_auto_zone_type,
        )
        from renatus.pipeline.steps.org import normalize_zone_objects

        zid = str(zone_id or "").strip()
        if not zid:
            return {}
        pipeline = self.api.connection.pipeline
        zcfg = pipeline.get(zid) if isinstance(pipeline.get(zid), dict) else {}
        ztype = str((zcfg or {}).get("type") or "")

        # F0128: auto-zones = vues logiques recalculees a chaque lecture
        if is_auto_zone_type(ztype):
            main_ids = self.store.steps_in_tab(YamlStepStore.ROOT_TAB)
            return compute_auto_zone_members(
                ztype,
                pipeline,
                object_id=(zcfg or {}).get("object"),
                main_step_ids=main_ids,
            )

        declared = normalize_zone_objects((zcfg or {}).get("objects"))

        # chemin d onglet / dossier contenu de la zone
        if zid == YamlStepStore.ROOT_TAB:
            zpath = YamlStepStore.ROOT_TAB
        else:
            parent_tab = (
                self.store.tab_of(zid)
                if zid in pipeline
                else YamlStepStore.ROOT_TAB
            )
            try:
                zpath = self.store.zone_path_for(zid, parent_tab)
            except Exception:
                zpath = zid

        fs_ids = self.store.steps_in_tab(zpath)
        out: dict[str, Any] = {}
        for oid, meta in declared.items():
            if oid == zid:
                continue
            if oid not in pipeline:
                out[oid] = meta if isinstance(meta, dict) else {}
                continue
            out[oid] = meta if isinstance(meta, dict) else {}
        for oid in sorted(fs_ids):
            if oid == zid or oid in out:
                continue
            if oid not in pipeline:
                continue
            out[oid] = {}
        return out

    def zones_of(self, step_id: str) -> list[dict[str, Any]]:
        """
        Zones ou apparait un objet (F0057/F0060/F0145) — calcule, non stocke YAML.

        Source de verite: presences disque <id>.yaml (fichier ou symlink) sous flow/.
        - default si presence a la racine protegee
        - zone X si presence dans le dossier de la zone
        can_remove = True ssi plus d une presence (sinon il faut supprimer l objet).
        """
        pipeline = self.api.connection.pipeline
        sid = str(step_id)
        if sid not in pipeline and not self.store.origins_of(sid):
            return []

        tabs = self.store.tabs_of(sid)
        n_copies = len(self.store.origins_of(sid))
        can_remove_any = n_copies > 1

        out: list[dict[str, Any]] = []
        seen: set[str] = set()

        for tab in tabs:
            if tab == YamlStepStore.ROOT_TAB:
                zid = YamlStepStore.ROOT_TAB
                label = YamlStepStore.ROOT_TAB
                zpath = YamlStepStore.ROOT_TAB
                kind = "home" if tab == self.store.tab_of(sid) else "member"
            else:
                # segment zone: dernier nom de dossier
                zid = tab.split("/")[-1]
                zcfg = pipeline.get(zid) if isinstance(pipeline.get(zid), dict) else {}
                label = str((zcfg or {}).get("label") or zid)
                zpath = tab
                kind = "home" if tab == self.store.tab_of(sid) else "member"
            if zid in seen:
                continue
            seen.add(zid)
            # presence symlink?
            is_link = False
            for op in self.store.origins_of(sid):
                if self.store.tab_of_path(op) == tab:
                    is_link = op.is_symlink()
                    break
            out.append(
                {
                    "id": zid,
                    "label": label,
                    "zone_path": zpath,
                    "tab": tab,
                    "kind": kind,
                    # F0060/F0145: retirable ssi >1 presence disque
                    "can_remove": n_copies > 1,
                    "copies": n_copies,
                    "symlink": is_link,
                }
            )

        def _sort_key(z: dict[str, Any]) -> tuple:
            zid = z.get("id") or ""
            if zid == YamlStepStore.ROOT_TAB:
                return (0, "")
            return (1, str(z.get("label") or zid).lower())

        out.sort(key=_sort_key)
        return out

    def share_step_to_zone(self, step_id: str, zone_tab: str) -> dict[str, Any]:
        """Lien symbolique <id>.yaml vers l objet dans la zone (F0060/F0145)."""
        with self._lock:
            if self.api.read_only:
                raise PermissionError("Lecture seule")
            path = self.store.attach_to_tab(step_id, zone_tab)
            self._reload_pipeline()
            self._autocommit(
                f"share {step_id} -> {zone_tab}",
                components=[step_id, zone_tab.split("/")[-1]],
            )
            return {
                "ok": True,
                "id": step_id,
                "tab": zone_tab,
                "path": str(path),
                "symlink": path.is_symlink(),
                "zones": self.zones_of(step_id),
                "message": f"{step_id} lie dans {zone_tab}",
            }

    def unshare_step_from_zone(
        self, step_id: str, zone_tab: str
    ) -> dict[str, Any]:
        """
        Retire le lien (ou la presence) dans une zone (F0060/F0145).

        Refuse si seule presence → il faut delete_step.
        """
        with self._lock:
            if self.api.read_only:
                raise PermissionError("Lecture seule")
            self.store.detach_from_tab(step_id, zone_tab)
            self._reload_pipeline()
            self._autocommit(
                f"unshare {step_id} from {zone_tab}",
                components=[step_id, zone_tab.split("/")[-1]],
            )
            return {
                "ok": True,
                "id": step_id,
                "tab": zone_tab,
                "zones": self.zones_of(step_id),
                "message": f"{step_id} retire de {zone_tab}",
            }

    def dataset_schema(self, step_id: str) -> list[dict[str, str]]:
        """
        F0091: schema calcule d un dataset (dataframe/table/view).

        Liste de {name, type} pour chaque colonne de la relation en base.
        Vide si la relation n existe pas encore (pas encore de Renatus).
        Non stocke dans le YAML.
        """
        pipeline = self.api.connection.pipeline
        if step_id not in pipeline:
            return []
        from renatus.pipeline.schema_helpers import relation_schema
        from renatus.pipeline.steps import create_step

        cfg = pipeline[step_id]
        if not isinstance(cfg, dict):
            return []
        step = create_step(step_id, cfg)
        if not step.produces_relation():
            return []
        rel = self.api.connection.relation_name(step_id)
        if not rel:
            return []
        try:
            # ConnectionPipeline expose la connexion DuckDB sous .con
            conn = self.api.connection.con
            pairs = relation_schema(conn, rel)
        except (KeyError, Exception):
            return []
        return [
            {"name": str(col), "type": str(dtype)}
            for col, dtype in pairs
        ]

    def dataset_shape(
        self, step_id: str, *, schema: list[dict[str, str]] | None = None
    ) -> list[int] | None:
        """
        F0092: shape calcule [rows, cols] pour dataframe/table/view.

        Disponible uniquement si la relation existe en base (apres un build
        reussi). Se met a jour a chaque build / relecture.
        Non stocke dans le YAML. None si non materialise.
        """
        pipeline = self.api.connection.pipeline
        if step_id not in pipeline:
            return None
        from renatus.pipeline.steps import create_step

        cfg = pipeline[step_id]
        if not isinstance(cfg, dict):
            return None
        step = create_step(step_id, cfg)
        if not step.produces_relation():
            return None
        rel = self.api.connection.relation_name(step_id)
        if not rel:
            return None
        cp = self.api.connection
        if not cp.relation_exists(rel):
            return None
        cols_list = schema if schema is not None else self.dataset_schema(step_id)
        n_cols = len(cols_list)
        try:
            conn = cp.con
            row = conn.execute(
                f'SELECT COUNT(*) FROM "{rel}"'
            ).fetchone()
            n_rows = int(row[0]) if row is not None else 0
        except Exception:
            return None
        return [n_rows, n_cols]

    def get_step(self, name: str) -> dict[str, Any]:
        with self._lock:
            if name not in self.api.connection.pipeline:
                raise KeyError(f"Objet absent du pipeline : {name}")
            raw = dict(self.api.connection.pipeline[name])
            # ne jamais exposer de cle reverse-deps dans config (non stockee)
            raw.pop("dependents", None)
            raw.pop("required_by", None)
            raw.pop("zones", None)  # F0057: calcule hors YAML
            raw.pop("schema", None)  # F0091: calcule hors YAML
            raw.pop("shape", None)  # F0092: calcule hors YAML
            raw.pop("renatus_time", None)  # F0093
            raw.pop("renatus-time", None)
            from renatus.pipeline.steps import create_step

            # A0011: config exposee = allow-list du type (pas de file sur zone…)
            step = create_step(name, raw)
            config = step.to_config()
            # A0015: Objects effectifs (YAML ∪ FS) pour afficher la liste
            # meme si main.objects est encore vide.
            if step.type == "zone":
                config = dict(config)
                config["objects"] = self.effective_zone_objects(name)
            origin = self.store.origin_of(name)
            # F0146: script affiche = contenu sidecar .py / .ipynb
            source_file = None
            source_format = None
            notebook = None
            from renatus.pipeline.steps.source_files import (
                SIDECAR_TYPES,
                parse_ipynb,
                sidecar_ext_for,
            )

            if step.type in SIDECAR_TYPES and origin is not None:
                side = self.store.sidecar_path_for(
                    name, step_type=step.type, yaml_path=origin
                )
                if side is not None:
                    source_file = str(side)
                    source_format = side.suffix.lstrip(".").lower()
                    script_txt = self.store.read_script_for_step(
                        name, {**raw, "type": step.type}
                    )
                    config = dict(config)
                    config["script"] = script_txt
                    if step.type == "notebook" and side.exists():
                        try:
                            notebook = parse_ipynb(
                                side.read_text(encoding="utf-8")
                            )
                        except OSError:
                            notebook = parse_ipynb(script_txt)
            label = str(config.get("label") or name)
            body = GuiStepResponse(
                ok=True,
                name=name,
                config=config,
                file_origin=str(origin) if origin else None,
            )
            rel = None
            if step.produces_relation():
                rel = self.api.connection.relation_name(name)
            dependents = self.dependents_of(name)
            zones = self.zones_of(name)
            # F0091 / F0092: schema + shape dataset (dataframe/table/view)
            schema: list[dict[str, str]] = []
            shape: list[int] | None = None
            if step.produces_relation():
                schema = self.dataset_schema(name)
                shape = self.dataset_shape(name, schema=schema)
            parent_tab = self.store.tab_of(name)
            zone_path = None
            if step.type == "zone":
                zone_path = self.store.zone_path_for(name, parent_tab)
            return {
                "ok": body.ok,
                "name": body.name,
                "id": name,
                "label": label,
                "config": body.config,
                "file_origin": body.file_origin,
                "relation_name": rel or name,
                "tab": parent_tab,
                "zone_path": zone_path,
                # F0041: calcule, lecture seule, hors config YAML
                "dependents": dependents,
                "dependents_count": len(dependents),
                # F0057: zones d appartenance (inverse de zone.objects)
                "zones": zones,
                "zones_count": len(zones),
                # F0091: schema colonnes (calcule)
                "schema": schema,
                "schema_count": len(schema),
                # F0092: shape [rows, cols] (calcule)
                "shape": shape,
                # F0093: duree dernier Renatus (secondes), None si jamais build
                "renatus_time": self._renatus_times.get(str(name)),
                # F0146: fichier source (.py / .ipynb) + notebook structure
                "source_file": source_file,
                "source_format": source_format,
                "notebook": notebook,
            }

    def put_step(
        self,
        name: str,
        config: dict[str, Any],
        *,
        tab: str | None = None,
    ) -> dict[str, Any]:
        """
        Met a jour la config d une step identifiee par son id (immutable).

        F0031: l utilisateur ne renomme pas l id; seul label/config changent.
        Le fichier cible est toujours <id>.yaml.
        """
        with self._lock:
            if self.api.read_only:
                raise PermissionError(
                    "GUI en lecture seule : save YAML impossible"
                )
            if not isinstance(config, dict):
                raise TypeError("config doit etre un dict")

            # F0101: id = shortname YAML (pas de path, pas d extension)
            step_id = YamlStepStore.normalize_step_id(name)

            # Refuse un champ id different de la cle (anti-renommage)
            if "id" in config and str(config["id"]).strip() not in (
                "",
                step_id,
            ):
                try:
                    cfg_id = YamlStepStore.normalize_step_id(
                        str(config["id"])
                    )
                except ValueError:
                    cfg_id = str(config["id"]).strip()
                if cfg_id not in ("", step_id):
                    raise ValueError(
                        "L id du composant est gere par l application "
                        "et ne peut pas etre modifie "
                        f"(id={step_id!r} = stem du fichier YAML)"
                    )

            # F0041/F0057/F0091: calculees jamais persistees
            config = dict(config)
            config.pop("dependents", None)
            config.pop("required_by", None)
            config.pop("used_by", None)
            config.pop("zones", None)
            config.pop("schema", None)
            config.pop("shape", None)
            config.pop("renatus_time", None)
            config.pop("renatus-time", None)
            # F0146: structure notebook → sidecar .ipynb (pas dans YAML)
            nb_struct = config.pop("notebook", None)
            if nb_struct is not None and not isinstance(nb_struct, dict):
                nb_struct = None
            if nb_struct is not None:
                # derive script affichage depuis cellules si absente
                if not str(config.get("script") or "").strip():
                    from renatus.pipeline.steps.source_files import (
                        ipynb_to_script,
                    )

                    config["script"] = ipynb_to_script(nb_struct)

            # Valide le type de base avant ecriture disque
            from renatus.pipeline.steps import create_step
            from renatus.pipeline.steps.factory import (
                allowed_types,
                normalize_step_type,
            )

            step_type = normalize_step_type(config.get("type"))
            config["type"] = step_type
            # F0053: allow-list unique = registry steps
            if step_type not in allowed_types():
                raise ValueError(
                    f"Type invalide pour {step_id}: {step_type}"
                )

            from renatus.pipeline.steps.auto_zone import is_auto_zone_type

            # Label avant modif (F0042: propagation affichage / heal)
            existed = step_id in self.api.connection.pipeline
            prev = self.api.connection.pipeline.get(step_id) or {}
            # F0128: auto-zones = lecture seule (vues logiques)
            if existed and is_auto_zone_type(
                str(prev.get("type") or step_type)
            ):
                raise PermissionError(
                    "Auto-zone en lecture seule — utilisez "
                    "« Convertir en zone » pour une version editable"
                )
            if is_auto_zone_type(step_type):
                # F0131: definition deposee dans main
                tab = YamlStepStore.ROOT_TAB
            old_label = str(prev.get("label") or step_id).strip()
            new_label = str(
                config.get("label") or step_id
            ).strip() or step_id

            tab_id = tab if tab is not None else self.active_tab
            # F0052/F0056/F0060: zone = dossier + objects + copies FS
            prev_zone_objects: dict[str, Any] = {}
            zone_content_tab: str | None = None
            # conserve le corps script avant sanitize allow-list
            script_body = config.get("script")
            if step_type == "zone":
                from renatus.pipeline.steps.org import normalize_zone_objects

                folder = self.store.zone_folder_for(step_id, tab_id)
                folder.mkdir(parents=True, exist_ok=True)
                # A0015: prev effectif (YAML ∪ FS) pour que retirer un
                # membre FS-only detache bien la copie disque.
                if existed:
                    prev_zone_objects = self.effective_zone_objects(step_id)
                else:
                    prev_zone_objects = normalize_zone_objects(
                        (prev or {}).get("objects")
                    )
                from renatus.pipeline.steps.org import (
                    normalize_renatus_mode,
                    normalize_zone_workers,
                )

                objects = normalize_zone_objects(config.get("objects"))
                # ne pas se referencer soi-meme
                objects.pop(step_id, None)
                # F0116: workers + renatus_mode (defauts auto / required_for_leaves)
                workers = normalize_zone_workers(
                    config.get("workers", (prev or {}).get("workers"))
                )
                renatus_mode = normalize_renatus_mode(
                    config.get(
                        "renatus_mode", (prev or {}).get("renatus_mode")
                    )
                )
                config = {
                    "type": "zone",
                    "label": new_label,
                    "objects": objects,
                    "workers": workers,
                    "renatus_mode": renatus_mode,
                }
                zone_content_tab = self.store.zone_path_for(step_id, tab_id)
            else:
                # A0011: sanitize allow-list pour tous les types non-zone
                config.setdefault("label", new_label)
                config = create_step(step_id, config).to_config()
                if "label" not in config and new_label:
                    config["label"] = new_label
                # F0146: re-injecte script + notebook pour sidecar
                if script_body is not None:
                    config["script"] = script_body
                if nb_struct is not None:
                    config["_notebook"] = nb_struct
            path = self.store.save_step(step_id, config, tab=tab_id)

            # F0060: sync copies disque pour membership zone
            if step_type == "zone" and zone_content_tab:
                from renatus.pipeline.steps.org import normalize_zone_objects

                objects = normalize_zone_objects(config.get("objects"))
                # ajouter copies pour nouveaux membres
                for oid in objects:
                    if oid == step_id:
                        continue
                    if oid not in self.api.connection.pipeline and oid not in (
                        self.store._origins or {}
                    ):
                        # objet inconnu: ignore (validate soft)
                        continue
                    try:
                        self.store.attach_to_tab(oid, zone_content_tab)
                    except Exception:
                        # source absente encore: skip
                        pass
                # retirer membres decochés (A0016: seule copie → supprimer)
                removed = [
                    oid
                    for oid in prev_zone_objects
                    if oid not in objects and oid != step_id
                ]
                self._evict_members_from_zone(
                    removed, zone_content_tab
                )

            # Recharge le pipeline en memoire (ConnectionPipeline charge au init)
            self._reload_pipeline()

            if step_id not in self.api.connection.pipeline:
                raise RuntimeError(
                    f"Step {step_id} absente apres reload pipeline"
                )

            label_changed = old_label != new_label

            # F0032/F0065/F0115: auto-commit git filtrable par composant
            action = "update" if existed else "create"
            msg = f"{action} step {step_id}"
            if label_changed and existed:
                msg += f" label {old_label!r}->{new_label!r}"
            # si zone: inclure aussi les membres impactes par objects
            comps = [step_id]
            if step_type == "zone":
                try:
                    for mid in self.effective_zone_objects(step_id):
                        if mid != step_id:
                            comps.append(mid)
                except Exception:
                    pass
            self._autocommit(msg, components=comps)

            stored = self.api.connection.pipeline[step_id]
            # Meta requires / dependents avec labels a jour (affichage)
            # Les YAML des autres steps gardent l id; seul le label source change.
            requires_meta = self._requires_meta(step_id)
            dependents = self.dependents_of(step_id)
            zones = self.zones_of(step_id)
            body = GuiSaveResponse(
                ok=True,
                name=step_id,
                file_origin=str(path),
                message=f"Step {step_id} enregistree dans {path.name}",
            )
            msg = body.message
            if label_changed:
                msg += (
                    f" — label « {old_label} » → « {new_label} » "
                    f"propage a l affichage "
                    f"({len(dependents)} dependant(s), "
                    f"{len(requires_meta)} require(s))"
                )
            return {
                "ok": body.ok,
                "name": body.name,
                "id": step_id,
                "label": str(stored.get("label") or step_id),
                "file_origin": body.file_origin,
                "message": msg,
                "tab": self.store.tab_of(step_id),
                "label_changed": label_changed,
                "label_old": old_label if label_changed else None,
                "label_new": new_label if label_changed else None,
                "requires": requires_meta,
                "dependents": dependents,
                "dependents_count": len(dependents),
                "zones": zones,
                "zones_count": len(zones),
            }

    def _requires_meta(self, step_id: str) -> list[dict[str, Any]]:
        """Liste requires de step_id avec labels + name SQL a jour (affichage)."""
        pipeline = self.api.connection.pipeline
        cfg = pipeline.get(step_id) or {}
        out: list[dict[str, Any]] = []
        for r in cfg.get("requires") or []:
            rid = str(r)
            other = pipeline.get(rid) or {}
            rel = None
            if rid in pipeline:
                try:
                    rel = self.api.connection.relation_name(rid)
                except Exception:
                    rel = other.get("name") or other.get("label") or rid
            out.append(
                {
                    "id": rid,
                    "label": str(other.get("label") or rid),
                    # F0049: name SQL pour ecrire FROM <name> dans le SQL
                    "relation_name": str(rel or rid),
                    "type": str(other.get("type") or "unknown"),
                    "tab": self.store.tab_of(rid)
                    if rid in pipeline
                    else None,
                    "missing": rid not in pipeline,
                }
            )
        return out

    # -- build / result -----------------------------------------------------

    @staticmethod
    def _topo_order_steps(
        ids: list[str], pipeline: dict[str, Any]
    ) -> list[str]:
        """
        Ordonne les ids par requires (Kahn), ignore deps hors ensemble.
        """
        id_set = set(ids)
        indeg: dict[str, int] = {i: 0 for i in ids}
        children: dict[str, list[str]] = {i: [] for i in ids}
        for sid in ids:
            cfg = pipeline.get(sid) or {}
            for dep in cfg.get("requires") or []:
                d = str(dep)
                if d in id_set:
                    children[d].append(sid)
                    indeg[sid] = indeg.get(sid, 0) + 1
        queue = [i for i in ids if indeg.get(i, 0) == 0]
        # ordre stable alpha parmi les racines
        queue.sort()
        ordered: list[str] = []
        while queue:
            n = queue.pop(0)
            ordered.append(n)
            for c in sorted(children.get(n) or []):
                indeg[c] -= 1
                if indeg[c] == 0:
                    queue.append(c)
                    queue.sort()
        # cycles: append remaining
        for sid in ids:
            if sid not in ordered:
                ordered.append(sid)
        return ordered

    def _record_renatus_time(
        self, name: str, elapsed_s: float, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """F0093: memoire + champ renatus_time (secondes) sur la reponse build."""
        sec = max(0.0, float(elapsed_s))
        self._renatus_times[str(name)] = sec
        out = dict(payload)
        out["renatus_time"] = round(sec, 6)
        return out

    def _build_one_unlocked(
        self,
        name: str,
        limit: int | None = None,
        max_rows: int | None = None,
        *,
        _zone_stack: set[str] | None = None,
    ) -> dict[str, Any]:
        """Build un step (appelant doit detenir le lock). F0093: chronometre."""
        import time

        t0 = time.perf_counter()
        try:
            result = self._build_one_body_unlocked(
                name,
                limit=limit,
                max_rows=max_rows,
                _zone_stack=_zone_stack,
            )
        except Exception:
            # echec: on ne garde pas un temps partiel comme succes
            raise
        elapsed = time.perf_counter() - t0
        return self._record_renatus_time(name, elapsed, result)

    def _build_one_body_unlocked(
        self,
        name: str,
        limit: int | None = None,
        max_rows: int | None = None,
        *,
        _zone_stack: set[str] | None = None,
    ) -> dict[str, Any]:
        """Corps du build sans chronometrage (appele sous lock)."""
        from renatus.pipeline.steps import create_step

        pipeline = self.api.connection.pipeline
        if name not in pipeline:
            raise KeyError(f"Objet absent du pipeline : {name}")
        step = create_step(name, pipeline[name])
        action = step.build_action()

        if action == "zone_build" or step.type == "zone":
            return self._build_zone_unlocked(
                name, limit=limit, max_rows=max_rows, _zone_stack=_zone_stack
            )

        # compat ancien nom d action
        if action == "zone_noop":
            return self._build_zone_unlocked(
                name, limit=limit, max_rows=max_rows, _zone_stack=_zone_stack
            )

        if action == "p_table_view":
            # F0123: build retourne une page (defaut limit client=3), pas toute la table
            data = self.api.p_table_view(
                name, limit=limit, max_rows=max_rows, offset=0
            )
            page = self._page_payload_from_relation_data(
                data,
                name=name,
                relation_name=str(data.name or name),
                extra={
                    "action": "p_table_view",
                    "has_result": step.has_tabular_result(),
                    "message": f"OK p_table_view {name}",
                },
            )
            return page

        if action == "p_iteration":
            result = self.api.p_iteration(name)
            return {
                "ok": True,
                "name": name,
                "action": "p_iteration",
                "columns": [],
                "rows": [],
                "row_count": 0,
                "truncated": False,
                "has_result": False,
                "limit": None,
                "message": result.message,
            }

        # execute / execute_python / defaut
        step_type = str(
            (self.api.connection.pipeline.get(name) or {}).get("type") or ""
        )
        try:
            result = self.api.process_with_requires(name)
        except Exception as exc:
            # F0062/F0075: meme en echec, remonter stdout/stderr process
            py_err = self._python_output_payload(name)
            if py_err is not None:
                py_err["ok"] = False
                py_err["action"] = step_type or py_err.get("action")
                py_err["message"] = str(exc)
                return py_err
            raise

        # F0062/F0075: process python ou shell → stdout/stderr DataView
        if step_type in {"execute_python", "notebook", "execute_shell"}:
            py_ok = self._python_output_payload(name)
            if py_ok is not None:
                py_ok["ok"] = True
                py_ok["action"] = step_type
                py_ok["message"] = (
                    result.message
                    + " — stdout/stderr dans DataView"
                )
                return py_ok

        return {
            "ok": True,
            "name": name,
            "action": "process_with_requires",
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "has_result": False,
            "limit": None,
            "message": result.message,
        }

    def _python_output_payload(self, name: str) -> dict[str, Any] | None:
        """
        Formate stdout/stderr d un process (execute_python / execute_shell)
        pour la DataView (F0062 / F0075).

        Colonnes: stream | content (stdout puis stderr).
        """
        store = getattr(self.api.connection, "python_run_results", None)
        if not isinstance(store, dict):
            return None
        data = store.get(name)
        if not isinstance(data, dict):
            return None
        stdout = str(data.get("stdout") or "")
        stderr = str(data.get("stderr") or "")
        rc = data.get("returncode")
        py = str(data.get("python") or data.get("shell") or "")
        step_type = str(
            (self.api.connection.pipeline.get(name) or {}).get("type") or ""
        ) or "execute_python"
        rows = [
            ["stdout", stdout if stdout else "(vide)"],
            ["stderr", stderr if stderr else "(vide)"],
            ["returncode", str(rc if rc is not None else "")],
            ["runtime", py or "(?)"],
        ]
        return {
            "name": name,
            "action": step_type,
            "columns": ["stream", "content"],
            "rows": rows,
            "row_count": len(rows),
            "truncated": False,
            "has_result": True,
            "limit": None,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": rc,
            "python": py,
        }

    @staticmethod
    def _zone_flow_lines(
        member_ids: list[str], pipeline: dict[str, Any]
    ) -> list[list[str]]:
        """
        F0116: lignes de flux independantes (composantes connexes du DAG requires).

        Deux membres sont relies s ils partagent une dependance requires
        (dans un sens ou l autre) parmi l ensemble.
        """
        id_set = set(member_ids)
        if not id_set:
            return []
        # graphe non oriente
        adj: dict[str, set[str]] = {i: set() for i in member_ids}
        for sid in member_ids:
            cfg = pipeline.get(sid) or {}
            for dep in cfg.get("requires") or []:
                d = str(dep)
                if d in id_set and d != sid:
                    adj[sid].add(d)
                    adj[d].add(sid)
        seen: set[str] = set()
        lines: list[list[str]] = []
        for start in sorted(member_ids):
            if start in seen:
                continue
            stack = [start]
            comp: list[str] = []
            seen.add(start)
            while stack:
                n = stack.pop()
                comp.append(n)
                for nb in adj.get(n) or ():
                    if nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
            lines.append(sorted(comp))
        return lines

    @staticmethod
    def _zone_line_leaves(
        line_ids: list[str], pipeline: dict[str, Any]
    ) -> list[str]:
        """
        Feuilles (puits) d une ligne: nœuds qui ne sont dependance d aucun
        autre membre de la ligne (fin de flux).
        """
        id_set = set(line_ids)
        is_dep: set[str] = set()
        for sid in line_ids:
            cfg = pipeline.get(sid) or {}
            for dep in cfg.get("requires") or []:
                d = str(dep)
                if d in id_set:
                    is_dep.add(d)
        # feuille = pas une dependance d un autre (sink)
        leaves = [sid for sid in line_ids if sid not in is_dep]
        return sorted(leaves) if leaves else sorted(line_ids)

    @staticmethod
    def _zone_ancestors_in_line(
        leaf: str,
        line_ids: list[str],
        pipeline: dict[str, Any],
    ) -> set[str]:
        """
        Ancêtres de leaf dans la ligne (requires transitifs + leaf).
        F0117: permet de chronometrer chaque composant buildé.
        """
        id_set = set(line_ids)
        needed: set[str] = set()
        stack = [leaf]
        while stack:
            n = stack.pop()
            if n not in id_set or n in needed:
                continue
            needed.add(n)
            cfg = pipeline.get(n) or {}
            for dep in cfg.get("requires") or []:
                d = str(dep)
                if d in id_set:
                    stack.append(d)
        return needed

    @staticmethod
    def _zone_build_targets(
        line_ids: list[str],
        pipeline: dict[str, Any],
        renatus_mode: str,
        topo_fn: Any,
    ) -> list[str]:
        """Cibles a builder pour une ligne selon renatus_mode."""
        from renatus.pipeline.steps.org import (
            RENATUS_MODE_LEAVES,
            normalize_renatus_mode,
        )

        mode = normalize_renatus_mode(renatus_mode)
        if mode == RENATUS_MODE_LEAVES:
            # required_for_leaves: feuilles + leurs requires dans la ligne
            # (chaque nœud est renatus individuellement → renatus_time a jour)
            leaves = GuiService._zone_line_leaves(line_ids, pipeline)
            needed: set[str] = set()
            for leaf in leaves:
                needed |= GuiService._zone_ancestors_in_line(
                    leaf, line_ids, pipeline
                )
            if not needed:
                needed = set(line_ids)
            return topo_fn(sorted(needed), pipeline)
        # root_to_leaves: tous les composants, ordre pipeline
        return topo_fn(line_ids, pipeline)

    def _zone_jobs_plan(
        self, zone_id: str
    ) -> dict[str, Any]:
        """
        F0116/F0118: calcule le plan de build d une zone (sans executer).

        Retourne members, lines, jobs [{id, line, index}], workers, renatus_mode.
        """
        from renatus.pipeline.steps.org import (
            WORKERS_AUTO,
            WORKERS_QUEUE,
            normalize_renatus_mode,
            normalize_zone_workers,
        )

        pipeline = self.api.connection.pipeline
        if zone_id not in pipeline:
            raise KeyError(f"Objet absent du pipeline : {zone_id}")
        zcfg = pipeline.get(zone_id) or {}
        workers = normalize_zone_workers(zcfg.get("workers"))
        renatus_mode = normalize_renatus_mode(zcfg.get("renatus_mode"))

        objects = self.effective_zone_objects(zone_id)
        member_ids = [
            oid
            for oid in objects
            if oid in pipeline and oid != zone_id
        ]
        lines = self._zone_flow_lines(member_ids, pipeline)

        jobs_t: list[tuple[int, str]] = []
        n_workers_eff = 1
        if workers == WORKERS_QUEUE:
            targets = self._zone_build_targets(
                member_ids,
                pipeline,
                renatus_mode,
                self._topo_order_steps,
            )
            jobs_t = [(0, tid) for tid in targets]
            n_workers_eff = 1
        else:
            n_workers_eff = (
                max(1, len(lines))
                if workers == WORKERS_AUTO
                else max(1, int(workers))
            )
            for li, line in enumerate(lines):
                targets = self._zone_build_targets(
                    line,
                    pipeline,
                    renatus_mode,
                    self._topo_order_steps,
                )
                for tid in targets:
                    jobs_t.append((li, tid))

        # dedupe preserve order
        seen: set[str] = set()
        jobs: list[dict[str, Any]] = []
        for li, tid in jobs_t:
            if tid in seen:
                continue
            seen.add(tid)
            jobs.append(
                {
                    "id": tid,
                    "line": li,
                    "index": len(jobs),
                    "label": str(
                        (pipeline.get(tid) or {}).get("label") or tid
                    ),
                    "type": str(
                        (pipeline.get(tid) or {}).get("type") or ""
                    ),
                }
            )
        return {
            "ok": True,
            "zone_id": zone_id,
            "members": member_ids,
            "jobs": jobs,
            "total": len(jobs),
            "workers": workers,
            "renatus_mode": renatus_mode,
            "flow_lines": len(lines),
            "workers_effective": n_workers_eff,
        }

    def zone_build_plan(self, zone_id: str) -> dict[str, Any]:
        """API: plan de build zone (F0118 progression UI)."""
        with self._lock:
            self.store.refresh()
            return self._zone_jobs_plan(zone_id)

    def complete_zone_build(
        self,
        zone_id: str,
        *,
        elapsed: float | None = None,
        built: list[dict[str, Any]] | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        F0118: finalise un build zone orchestre cote client (job par job).

        N execute pas les jobs: enregistre renatus_time de la zone et
        renvoie un resume zone_build a partir des temps membres en memoire.
        """
        with self._lock:
            self.store.refresh()
            plan = self._zone_jobs_plan(zone_id)
            pipeline = self.api.connection.pipeline
            member_times: dict[str, float] = {}
            built_out: list[dict[str, Any]] = []
            if built:
                for b in built:
                    bid = str((b or {}).get("id") or "")
                    if not bid:
                        continue
                    rt = (b or {}).get("renatus_time")
                    if rt is None:
                        rt = self._renatus_times.get(bid)
                    entry = {
                        "id": bid,
                        "ok": bool((b or {}).get("ok", True)),
                        "action": (b or {}).get("action") or "build",
                        "message": (b or {}).get("message"),
                        "label": str(
                            (b or {}).get("label")
                            or (pipeline.get(bid) or {}).get("label")
                            or bid
                        ),
                        "line": (b or {}).get("line"),
                        "renatus_time": (
                            float(rt) if rt is not None else None
                        ),
                    }
                    if entry["renatus_time"] is not None:
                        member_times[bid] = float(entry["renatus_time"])
                    built_out.append(entry)
            else:
                for j in plan.get("jobs") or []:
                    bid = str(j.get("id") or "")
                    if not bid:
                        continue
                    rt = self._renatus_times.get(bid)
                    entry = {
                        "id": bid,
                        "ok": True,
                        "action": "build",
                        "message": None,
                        "label": str(
                            j.get("label")
                            or (pipeline.get(bid) or {}).get("label")
                            or bid
                        ),
                        "line": j.get("line"),
                        "renatus_time": (
                            float(rt) if rt is not None else None
                        ),
                    }
                    if entry["renatus_time"] is not None:
                        member_times[bid] = float(entry["renatus_time"])
                    built_out.append(entry)

            err_list = list(errors or [])
            ok = len(err_list) == 0 and all(
                b.get("ok") for b in built_out
            )
            n_ok = sum(1 for b in built_out if b.get("ok"))
            n_jobs = len(built_out)
            workers = plan.get("workers")
            renatus_mode = plan.get("renatus_mode")
            lines_n = int(plan.get("flow_lines") or 0)
            n_workers_eff = int(plan.get("workers_effective") or 1)
            if elapsed is None:
                elapsed = (
                    sum(member_times.values()) if member_times else 0.0
                )
            sec = max(0.0, float(elapsed))
            self._renatus_times[str(zone_id)] = sec
            msg = (
                f"Zone {zone_id}: {n_ok}/{n_jobs} build OK"
                f" · mode={renatus_mode} · workers={workers}"
                f" · {lines_n} ligne(s)"
                if n_jobs
                else f"Zone {zone_id}: aucun objet a builder (objects vide)"
            )
            if err_list:
                msg += f" — {len(err_list)} erreur(s)"
            return {
                "ok": ok,
                "name": zone_id,
                "action": "zone_build",
                "columns": [],
                "rows": [],
                "row_count": 0,
                "truncated": False,
                "has_result": False,
                "limit": None,
                "built": built_out,
                "errors": err_list,
                "message": msg,
                "workers": workers,
                "renatus_mode": renatus_mode,
                "flow_lines": lines_n,
                "workers_effective": n_workers_eff,
                "member_renatus_times": member_times,
                "renatus_time": round(sec, 6),
                "orchestrated": True,
            }

    def _build_zone_unlocked(
        self,
        zone_id: str,
        limit: int | None = None,
        max_rows: int | None = None,
        *,
        _zone_stack: set[str] | None = None,
    ) -> dict[str, Any]:
        """
        F0058 / F0116: Build d une zone.

        - A0015: membres = effective_zone_objects (YAML ∪ FS)
        - F0116 workers: auto = 1 worker par ligne de flux independante
          (exec sequentielle DuckDB-safe; structure pret pour multi-db)
          queue = une seule file sur toutes les cibles
        - F0116 renatus_mode:
          required_for_leaves = Renatus sur chaque feuille (requires geres)
          root_to_leaves = Renatus sur chaque nœud dans l ordre pipeline
        """
        stack = set(_zone_stack or ())
        if zone_id in stack:
            return {
                "ok": False,
                "name": zone_id,
                "action": "zone_build",
                "columns": [],
                "rows": [],
                "row_count": 0,
                "truncated": False,
                "has_result": False,
                "limit": None,
                "built": [],
                "errors": [{"id": zone_id, "error": "cycle de zones"}],
                "message": f"Cycle de zones detecte autour de {zone_id}",
            }
        stack.add(zone_id)

        plan = self._zone_jobs_plan(zone_id)
        workers = plan["workers"]
        renatus_mode = plan["renatus_mode"]
        lines_n = int(plan.get("flow_lines") or 0)
        n_workers_eff = int(plan.get("workers_effective") or 1)
        pipeline = self.api.connection.pipeline
        jobs = [(int(j["line"]), str(j["id"])) for j in plan.get("jobs") or []]
        lines = list(range(lines_n))  # indices only for branching logic

        built: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        last_table: dict[str, Any] | None = None
        seen_build: set[str] = set()

        def _run_one(oid: str, line_idx: int) -> dict[str, Any]:
            if oid in seen_build:
                return {
                    "id": oid,
                    "ok": True,
                    "action": "skip_dup",
                    "message": "deja builde dans cette zone",
                    "label": str(
                        (pipeline.get(oid) or {}).get("label") or oid
                    ),
                    "line": line_idx,
                    "renatus_time": self._renatus_times.get(str(oid)),
                    "_last": None,
                }
            seen_build.add(oid)
            try:
                res = self._build_one_unlocked(
                    oid,
                    limit=limit,
                    max_rows=max_rows,
                    _zone_stack=stack,
                )
                last = (
                    res
                    if res.get("has_result") and res.get("columns") is not None
                    else None
                )
                # F0117: temps calcule du membre (deja en memoire via _record)
                rt = res.get("renatus_time")
                if rt is None:
                    rt = self._renatus_times.get(str(oid))
                return {
                    "id": oid,
                    "ok": bool(res.get("ok")),
                    "action": res.get("action"),
                    "message": res.get("message"),
                    "label": str(
                        (pipeline.get(oid) or {}).get("label") or oid
                    ),
                    "line": line_idx,
                    "renatus_time": rt,
                    "_last": last,
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "id": oid,
                    "ok": False,
                    "action": "error",
                    "message": str(exc),
                    "label": str(
                        (pipeline.get(oid) or {}).get("label") or oid
                    ),
                    "line": line_idx,
                    "renatus_time": None,
                    "_last": None,
                }

        # DuckDB mono-connexion: exec sequentielle des jobs.
        from renatus.pipeline.steps.org import WORKERS_AUTO, WORKERS_QUEUE

        if workers != WORKERS_QUEUE and lines_n > 1:
            by_line: dict[int, list[str]] = {}
            for li, tid in jobs:
                by_line.setdefault(li, []).append(tid)
            for li in sorted(by_line.keys()):
                for tid in by_line[li]:
                    entry = _run_one(tid, li)
                    last = entry.pop("_last", None)
                    built.append(entry)
                    if last is not None:
                        last_table = last
                    if not entry.get("ok"):
                        errors.append(
                            {
                                "id": entry["id"],
                                "error": entry.get("message") or "echec",
                            }
                        )
        else:
            for li, tid in jobs:
                entry = _run_one(tid, li)
                last = entry.pop("_last", None)
                built.append(entry)
                if last is not None:
                    last_table = last
                if not entry.get("ok"):
                    errors.append(
                        {
                            "id": entry["id"],
                            "error": entry.get("message") or "echec",
                        }
                    )

        ok = len(errors) == 0
        n_ok = sum(1 for b in built if b.get("ok"))
        n_jobs = len(built)
        mode_label = renatus_mode
        msg = (
            f"Zone {zone_id}: {n_ok}/{n_jobs} build OK"
            f" · mode={mode_label} · workers={workers}"
            f" · {len(lines)} ligne(s)"
            if n_jobs
            else f"Zone {zone_id}: aucun objet a builder (objects vide)"
        )
        if workers == WORKERS_AUTO and lines_n > 1:
            msg += " (lignes independantes)"
        if errors:
            msg += f" — {len(errors)} erreur(s)"

        # F0117: carte renatus_time de tous les membres buildes
        member_times: dict[str, float] = {}
        for b in built:
            bid = str(b.get("id") or "")
            rt = b.get("renatus_time")
            if bid and rt is not None:
                try:
                    member_times[bid] = float(rt)
                except (TypeError, ValueError):
                    pass
            elif bid and bid in self._renatus_times:
                member_times[bid] = float(self._renatus_times[bid])
                b["renatus_time"] = round(member_times[bid], 6)

        out: dict[str, Any] = {
            "ok": ok,
            "name": zone_id,
            "action": "zone_build",
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "has_result": False,
            "limit": limit,
            "built": built,
            "errors": errors,
            "message": msg,
            "workers": workers,
            "renatus_mode": renatus_mode,
            "flow_lines": lines_n,
            "workers_effective": n_workers_eff,
            # F0117: temps par membre (en plus du renatus_time global zone)
            "member_renatus_times": member_times,
        }
        if last_table and last_table.get("has_result"):
            out["columns"] = last_table.get("columns") or []
            out["rows"] = last_table.get("rows") or []
            out["row_count"] = last_table.get("row_count") or 0
            out["truncated"] = bool(last_table.get("truncated"))
            out["has_result"] = True
            out["limit"] = last_table.get("limit")
        return out

    def build(
        self,
        name: str,
        limit: int | None = None,
        max_rows: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            return self._build_one_unlocked(
                name, limit=limit, max_rows=max_rows
            )

    def result(
        self,
        name: str,
        limit: int | None = None,
        max_rows: int | None = None,
        *,
        offset: int = 0,
    ) -> dict[str, Any]:
        with self._lock:
            data = self.api.table_view(
                name,
                limit=limit,
                max_rows=max_rows,
                offset=offset,
            )
            return self._page_payload_from_relation_data(
                data,
                name=data.name or name,
                relation_name=data.name or name,
            )

    # -- toolbox / creation (F0012) -----------------------------------------

    @staticmethod
    def tools_catalog() -> list[dict[str, Any]]:
        """Boite a outils GUI : catalogue unique depuis pipeline.steps (F0053-S1)."""
        from renatus.pipeline.steps import tools_catalog as steps_tools_catalog

        return steps_tools_catalog()

    @staticmethod
    def display_labels(
        db_path: str | Path,
        pipeline_path: str | Path,
    ) -> dict[str, str]:
        """Labels courts UI : nom duckdb sans extension, nom dossier flow."""
        db = Path(db_path)
        pipe = Path(pipeline_path)
        db_label = db.stem if db.suffix.lower() == ".duckdb" else db.name
        if pipe.is_file():
            pipe_label = pipe.parent.name or str(pipe.parent)
        else:
            pipe_label = pipe.name or str(pipe)
        return {
            "db_label": db_label,
            "pipeline_label": pipe_label,
            "db_path": str(db),
            "pipeline_path": str(pipe),
        }

    def workspace_info(self) -> dict[str, Any]:
        """Infos connexion + labels d'affichage + catalogue outils."""
        info = self.connect_info()
        labels = self.display_labels(info.db_path, info.pipeline_path)
        return {
            "ok": True,
            "status": info.status,
            "db_path": info.db_path,
            "pipeline_path": info.pipeline_path,
            "pipelines_dir": info.pipelines_dir,
            "read_only": info.read_only,
            "step_count": info.step_count,
            "db_label": labels["db_label"],
            "pipeline_label": labels["pipeline_label"],
            "project_file": self._project_file,
            "project_name": self._project_name
            or labels["db_label"]
            or "renatus",
            "tools": self.tools_catalog(),
        }

    # -- projet renatus (.renatus.yaml) -------------------------------------

    def current_project(self) -> RenatusProject:
        """Construit un RenatusProject depuis la connexion courante."""
        info = self.connect_info()
        return RenatusProject.from_workspace(
            info.db_path,
            info.pipeline_path,
            name=self._project_name,
            read_only=info.read_only,
            project_file=self._project_file,
        )

    def project_info(self) -> dict[str, Any]:
        """Etat projet pour l UI / API."""
        with self._lock:
            info = self.workspace_info()
            proj = self.current_project()
            suggested = str(proj.default_save_path())
            git_info: dict[str, Any] = {"is_repo": False}
            if self._project_file:
                git_info = ProjectGit(
                    Path(self._project_file).parent
                ).status_summary()
            return {
                "ok": True,
                "name": info["project_name"],
                "project_file": self._project_file,
                "db_path": info["db_path"],
                "pipeline_path": info["pipeline_path"],
                "read_only": info["read_only"],
                "suggested_path": suggested,
                "has_project_file": bool(self._project_file),
                "git": git_info,
                "work_branch": self._work_branch or git_info.get("branch"),
            }

    def _project_root(self) -> Path | None:
        if not self._project_file:
            return None
        return Path(self._project_file).expanduser().resolve().parent

    def _infer_project_root(self) -> Path | None:
        """
        Racine projet pour le git (F0065).

        Prefer project_file parent; sinon parent de flow/ (workspace).
        """
        root = self._project_root()
        if root is not None:
            return root
        if self._api is None:
            return None
        try:
            pipe = Path(self.api.pipeline_path).expanduser().resolve()
        except OSError:
            return None
        if pipe.is_dir() and pipe.name.lower() in {
            "flow",
            "pipelines",
            "pipeline",
        }:
            return pipe.parent
        if pipe.is_file():
            # mono-fichier legacy: racine = parent
            return pipe.parent
        # dossier flow custom (nom libre)
        return pipe.parent if pipe.is_dir() else pipe.parent

    def _ensure_project_tracking(self) -> ProjectGit | None:
        """
        F0065 / F0032: assure fichier projet + depot git + branche travail.

        Appelé a la connexion et avant chaque auto-commit. No-op en RO.
        Retourne ProjectGit pret, ou None si impossible.
        """
        if self._api is None or self.api.read_only:
            return None
        root = self._infer_project_root()
        if root is None:
            return None
        try:
            root.mkdir(parents=True, exist_ok=True)
            root = root.resolve()
        except OSError:
            return None

        # Fichier .renatus.yaml a la racine si absent
        if not self._project_file:
            # reutiliser un .renatus.yaml deja present
            found = find_project_file(root)
            if found is not None:
                self._project_file = str(found)
                try:
                    proj = RenatusProject.load(found)
                    self._project_name = proj.name
                except Exception:
                    pass
            else:
                label = (
                    (self._project_name or "").strip()
                    or root.name
                    or "workspace"
                )
                safe = "".join(
                    c if c.isalnum() or c in "-_" else "_" for c in label
                ).strip("_") or "workspace"
                project_file = root / f"{safe}.renatus.yaml"
                project = RenatusProject.from_workspace(
                    self.api.db_path,
                    self.api.pipeline_path,
                    name=label,
                    read_only=False,
                    project_file=project_file,
                )
                try:
                    written = project.save(project_file)
                    self._project_file = str(written)
                    self._project_name = project.name
                except OSError:
                    return None

        git = ProjectGit(root)
        try:
            if not git.is_repo():
                self._work_branch = git.init_repository()
            else:
                self._work_branch = git.ensure_work_branch()
            self._work_branch = git.current_branch()
        except Exception:
            return None
        return git

    def _autocommit(
        self,
        message: str,
        *,
        components: list[str] | None = None,
        paths: list[str] | None = None,
    ) -> None:
        """
        Commit automatique sur la branche de travail (F0032 / F0065 / F0115).

        F0115: trailers renatus-component / renatus-path pour filtrer Track.
        """
        if self._api is None or self.api.read_only:
            return
        try:
            git = self._ensure_project_tracking()
            if git is None:
                return
            # chemins relatifs au repo si non fournis
            rel_paths = list(paths or [])
            comp_ids = [str(c).strip() for c in (components or []) if str(c).strip()]
            if not rel_paths and comp_ids:
                for cid in comp_ids:
                    rel_paths.extend(self._git_relpaths_for_step(cid, git))
            # dedupe paths
            seen: set[str] = set()
            uniq_paths: list[str] = []
            for p in rel_paths:
                if p and p not in seen:
                    seen.add(p)
                    uniq_paths.append(p)
            git.commit_all(
                message,
                components=comp_ids or None,
                paths=uniq_paths or None,
            )
            self._work_branch = git.current_branch()
        except Exception:
            # ne bloque pas l UI si git echoue
            return

    def _git_relpaths_for_step(
        self,
        step_id: str,
        git: ProjectGit | None = None,
        *,
        recursive_zone: bool = True,
        _seen: set[str] | None = None,
    ) -> list[str]:
        """
        F0115: chemins git (relatifs) lies a un composant.

        - step normal: toutes ses copies YAML
        - zone: yaml de la zone + membres effectifs (recursif sous-zones)
        """
        sid = str(step_id or "").strip()
        if not sid:
            return []
        seen = _seen if _seen is not None else set()
        if sid in seen:
            return []
        seen.add(sid)
        if git is None:
            try:
                git = self._require_project_git()
            except Exception:
                return []
        out: list[str] = []
        for origin in self.store.origins_of(sid):
            try:
                out.append(git.relpath(origin))
            except Exception:
                continue
        pipe = self.api.connection.pipeline
        cfg = pipe.get(sid) if isinstance(pipe.get(sid), dict) else {}
        if recursive_zone and str((cfg or {}).get("type") or "") == "zone":
            # dossier zone (fichiers presents meme hors objects)
            try:
                parent_tab = self.store.tab_of(sid)
                folder = self.store.zone_folder_for(sid, parent_tab)
                if folder.is_dir():
                    for f in sorted(folder.rglob("*")):
                        if f.is_file() and f.suffix.lower() in (
                            ".yaml",
                            ".yml",
                        ):
                            try:
                                out.append(git.relpath(f))
                            except Exception:
                                pass
            except Exception:
                pass
            # membres effectifs (YAML ∪ FS) — recursion
            try:
                members = self.effective_zone_objects(sid)
            except Exception:
                members = {}
            for mid in members:
                if mid == sid:
                    continue
                out.extend(
                    self._git_relpaths_for_step(
                        mid,
                        git,
                        recursive_zone=True,
                        _seen=seen,
                    )
                )
        # dedupe preserve order
        uniq: list[str] = []
        seen_p: set[str] = set()
        for p in out:
            if p not in seen_p:
                seen_p.add(p)
                uniq.append(p)
        return uniq

    def save_project(
        self,
        path: str | Path | None = None,
        *,
        name: str | None = None,
    ) -> dict[str, Any]:
        """
        Sauvegarde le projet (db + pipelines) + git (F0032).

        - Ecrit le .renatus.yaml
        - Si nouveau repo: init + main + branche b_timestamp
        - Si repo existant: merge branche de travail → main (Save utilisateur)
        """
        with self._lock:
            if self.api.read_only:
                raise PermissionError(
                    "GUI en lecture seule : sauvegarde projet impossible"
                )
            if name and str(name).strip():
                self._project_name = str(name).strip()
            project = self.current_project()
            target = Path(path).expanduser() if path else project.default_save_path()
            # F0043: pipelines versionnes → obligatoirement sous le root projet
            root_for_pipe = (
                target.parent if is_project_file(target) else target
            )
            try:
                root_for_pipe = root_for_pipe.expanduser().resolve()
            except OSError:
                root_for_pipe = root_for_pipe.expanduser()
            try:
                pipe_ok = ensure_pipelines_inside_project(
                    root_for_pipe, project.pipeline_path
                )
            except ValueError as exc:
                raise ValueError(
                    f"{exc} Placez flow_path sous {root_for_pipe}/flow"
                ) from exc
            project.pipeline_path = str(pipe_ok)
            Path(pipe_ok).mkdir(parents=True, exist_ok=True)
            written = project.save(target)
            self._project_file = str(written)
            self._project_name = project.name
            root = written.parent
            git = ProjectGit(root)
            git_msg = ""
            if not git.is_repo():
                self._work_branch = git.init_repository()
                git_msg = f" ; depot git init, branche {self._work_branch}"
            else:
                # Save utilisateur = fusion dans main
                try:
                    result = git.merge_into_main(self._work_branch)
                except Exception as exc:
                    return {
                        "ok": False,
                        "path": str(written),
                        "name": project.name,
                        "db_path": project.db_path,
                        "pipeline_path": project.pipeline_path,
                        "read_only": project.read_only,
                        "work_branch": self._work_branch,
                        "message": f"Projet yaml OK, merge git echoue: {exc}",
                        "error": str(exc),
                    }
                self._work_branch = result.get("work_branch") or git.current_branch()
                git_msg = " ; " + str(result.get("message") or "")
                if not result.get("ok"):
                    return {
                        "ok": False,
                        "path": str(written),
                        "name": project.name,
                        "db_path": project.db_path,
                        "pipeline_path": project.pipeline_path,
                        "read_only": project.read_only,
                        "work_branch": self._work_branch,
                        "message": f"Projet yaml OK, merge git echoue{git_msg}",
                        "error": result.get("message"),
                    }
            return {
                "ok": True,
                "path": str(written),
                "name": project.name,
                "db_path": project.db_path,
                "pipeline_path": project.pipeline_path,
                "read_only": project.read_only,
                "work_branch": self._work_branch,
                "message": f"Projet enregistre : {written}{git_msg}",
            }

    def inspect_project_path(self, path: str | Path) -> dict[str, Any]:
        """
        Analyse un chemin projet (dossier ou .renatus.yaml) pour l UI (F0036).

        - existing: fichier projet present → charge name/db/pipeline
        - new: chemin libre → propose defauts db + pipelines
        """
        raw = str(path or "").strip()
        if not raw:
            return {
                "ok": False,
                "kind": "invalid",
                "message": "Chemin projet requis",
            }
        p = Path(raw).expanduser()
        found = find_project_file(p)
        if found is None and p.is_file() and not is_project_file(p):
            return {
                "ok": False,
                "kind": "invalid",
                "path": str(p.resolve()) if p.exists() else str(p),
                "message": "Fichier non reconnu (attendu .renatus.yaml)",
            }
        if found is not None:
            try:
                project = RenatusProject.load(found)
            except Exception as exc:
                return {
                    "ok": False,
                    "kind": "invalid",
                    "path": str(found),
                    "project_file": str(found),
                    "message": f"Projet illisible: {exc}",
                }
            return {
                "ok": True,
                "kind": "existing",
                "path": str(found),
                "project_file": str(found),
                "project_root": str(found.parent),
                "name": project.name,
                "db_path": project.db_path,
                "pipeline_path": project.pipeline_path,
                "read_only": project.read_only,
                "message": f"Projet existant : {project.name}",
            }

        # nouveau projet
        project_file, root = resolve_project_target(p)
        root_resolved = root.expanduser()
        try:
            root_display = str(root_resolved.resolve())
        except Exception:
            root_display = str(root_resolved)
        try:
            pf_display = str(project_file.expanduser().resolve())
        except Exception:
            pf_display = str(project_file.expanduser())

        suggested_name = root_resolved.name or "renatus"
        # db: defaut sous le projet mais peut etre hors (donnees privees)
        suggested_db = str((root_resolved / f"{suggested_name}.duckdb"))
        # flow: TOUJOURS dans le projet (git)
        suggested_pipe = str(root_resolved / "flow")
        return {
            "ok": True,
            "kind": "new",
            "path": raw,
            "project_file": pf_display,
            "project_root": root_display,
            "name": suggested_name,
            "db_path": suggested_db,
            "pipeline_path": suggested_pipe,
            "flow_path": suggested_pipe,
            "suggested_name": suggested_name,
            "suggested_db_path": suggested_db,
            "suggested_pipeline_path": suggested_pipe,
            "suggested_flow_path": suggested_pipe,
            "pipelines_must_be_inside": True,
            "db_may_be_external": True,
            "read_only": False,
            "message": (
                "Nouveau projet — flux (flow/) dans le dossier projet (git) ; "
                "base DuckDB / donnees peuvent rester hors workspace"
            ),
        }

    def create_project(
        self,
        path: str | Path,
        *,
        name: str | None = None,
        db_path: str | Path | None = None,
        pipeline_path: str | Path | None = None,
        read_only: bool = False,
    ) -> dict[str, Any]:
        """
        Cree un nouveau projet renatus (F0036 / F0043).

        - dossier projet + .renatus.yaml (config connexion)
        - pipelines **obligatoirement** sous le root projet (git)
        - db_path : chemin de connexion (peut etre hors projet)
        - donnees sources : referencees, non imposees dans le git
        - init git
        """
        with self._lock:
            if self._api is not None and self.api.read_only:
                raise PermissionError(
                    "GUI en lecture seule : creation projet impossible"
                )

            inspect = self.inspect_project_path(path)
            if inspect.get("kind") == "existing":
                raise ValueError(
                    "Un projet existe deja a ce chemin — utilisez Ouvrir"
                )
            if inspect.get("kind") == "invalid":
                raise ValueError(
                    inspect.get("message") or "Chemin projet invalide"
                )

            project_file, root = resolve_project_target(path)
            root = root.expanduser()
            root.mkdir(parents=True, exist_ok=True)
            try:
                root = root.resolve()
            except OSError:
                pass
            project_file = project_file.expanduser()
            if not is_project_file(project_file):
                label = (name or root.name or "renatus").strip() or "renatus"
                safe = "".join(
                    c if c.isalnum() or c in "-_" else "_" for c in label
                ).strip("_") or "renatus"
                project_file = root / f"{safe}.renatus.yaml"

            label = (name or "").strip() or root.name or "renatus"
            # DB : chemin libre (prive / hors git OK)
            if db_path is None or not str(db_path).strip():
                db_p = root / f"{label}.duckdb"
            else:
                db_p = Path(str(db_path).strip()).expanduser()
                if not db_p.is_absolute():
                    db_p = (root / db_p).resolve()
                else:
                    db_p = db_p.resolve()

            # Pipelines : strictement dans le projet
            pipe_p = ensure_pipelines_inside_project(root, pipeline_path)

            pipe_p.mkdir(parents=True, exist_ok=True)
            db_p.parent.mkdir(parents=True, exist_ok=True)

            project = RenatusProject.from_workspace(
                db_p,
                pipe_p,
                name=label,
                read_only=bool(read_only),
                project_file=project_file,
            )
            written = project.save(project_file)

            # connecte le gui
            self.connect(
                project.db_path,
                project.pipeline_path,
                read_only=project.read_only,
                keep_project=True,
            )
            self._project_file = str(written)
            self._project_name = project.name

            git_msg = ""
            git = ProjectGit(written.parent)
            if not git.is_repo():
                self._work_branch = git.init_repository()
                git_msg = f" ; git init {self._work_branch}"
            else:
                self._work_branch = git.ensure_work_branch()
                git_msg = f" ; branche {self._work_branch}"

            info = self.workspace_info()
            db_external = not is_under_directory(project.db_path, root)
            return {
                "ok": True,
                "created": True,
                "path": str(written),
                "project_file": str(written),
                "project_root": str(root),
                "name": project.name,
                "db_path": project.db_path,
                "pipeline_path": project.pipeline_path,
                "pipelines_inside_project": True,
                "db_external": db_external,
                "read_only": project.read_only,
                "work_branch": self._work_branch,
                "message": (
                    f"Projet cree : {written}{git_msg}"
                    + (
                        " ; base DuckDB hors projet (donnees privees)"
                        if db_external
                        else ""
                    )
                ),
                **info,
            }

    def open_project(self, path: str | Path) -> dict[str, Any]:
        """
        Ouvre un fichier ou dossier projet et reconnecte le GUI.

        F0032: checkout main; signale une branche de travail en avance.
        F0036: accepte un dossier contenant un .renatus.yaml.
        """
        raw = Path(path).expanduser()
        found = find_project_file(raw)
        if found is None:
            if raw.is_dir():
                raise FileNotFoundError(
                    f"Aucun fichier .renatus.yaml dans {raw}"
                )
            # fallback: path direct
            found = raw
        project = RenatusProject.load(found)
        with self._lock:
            self.connect(
                project.db_path,
                project.pipeline_path,
                read_only=project.read_only,
                keep_project=True,
            )
            self._project_file = project.project_file
            self._project_name = project.name
            pending = None
            branch = None
            root = self._project_root()
            if root is not None:
                git = ProjectGit(root)
                if git.is_repo():
                    try:
                        git.checkout("main")
                    except Exception:
                        pass
                    branch = git.current_branch()
                    self._work_branch = branch
                    pend = git.find_latest_branch_ahead_of_main()
                    if pend is not None:
                        pending = pend.to_dict()
            info = self.workspace_info()
            info["message"] = f"Projet ouvert : {project.name}"
            info["project_file"] = self._project_file
            info["project_name"] = self._project_name
            info["git_branch"] = branch
            info["pending_branch"] = pending
            if pending:
                info["message"] += (
                    f" — modifications non fusionnees sur {pending['name']}"
                )
            return info

    def resume_project_branch(self, branch: str) -> dict[str, Any]:
        """Checkout une branche de travail (apres proposition UI)."""
        with self._lock:
            root = self._project_root()
            if root is None:
                raise RuntimeError("Aucun projet ouvert")
            git = ProjectGit(root)
            if not git.is_repo():
                raise RuntimeError("Projet sans depot git")
            git.checkout(branch)
            self._work_branch = git.current_branch()
            # recharger les YAML de la branche
            self._reload_pipeline()
            return {
                "ok": True,
                "branch": self._work_branch,
                "message": f"Branche {self._work_branch} chargee",
                **self.workspace_info(),
            }

    # -- changelog global projet (F0035, corrige F0033) ---------------------

    def _require_project_git(self) -> ProjectGit:
        """
        Git projet requis pour les changelogs.

        F0065: tente d activer le tracking (workspace defaut inclus)
        avant d echouer.
        """
        git = None
        if not self.api.read_only:
            try:
                git = self._ensure_project_tracking()
            except Exception:
                git = None
        if git is None:
            root = self._project_root() or self._infer_project_root()
            if root is not None and ProjectGit(root).is_repo():
                git = ProjectGit(root)
        if git is None or not git.is_repo():
            raise RuntimeError(
                "Changelogs indisponibles : impossible d initialiser le git "
                "du projet (workspace en lecture seule ou chemin invalide)"
            )
        return git

    @staticmethod
    def _step_id_from_path(rel_path: str) -> str | None:
        """Si le chemin ressemble a un YAML de step, retourne un id candidat."""
        if not rel_path:
            return None
        p = Path(rel_path)
        if p.suffix.lower() not in (".yaml", ".yml"):
            return None
        # flow/<id>.yaml ou flow/<tab>/<id>.yaml
        name = p.stem
        if name and name not in (".renatus",):
            return name
        return None

    def project_changelog(
        self,
        *,
        limit: int = 50,
        step_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Timeline des commits du projet (recent en premier).

        F0115: si step_id fourni, filtre aux commits touchant les fichiers
        du composant (zone = recursif sur membres + sous-zones).
        """
        with self._lock:
            git = self._require_project_git()
            sid = str(step_id or "").strip() or None
            scope_paths: list[str] = []
            if sid:
                # F0115 Track: filtre composant (zone = recursif)
                scope_paths = self._git_relpaths_for_step(sid, git)
                entries = (
                    git.paths_log(scope_paths, limit=limit)
                    if scope_paths
                    else []
                )
            else:
                # sans step_id: timeline globale (API / debug) — UI Track
                # demande toujours step_id
                entries = git.global_log(limit=limit)
            return {
                "ok": True,
                "branch": git.current_branch(),
                "step_id": sid,
                "paths": scope_paths,
                "entries": entries,
                "count": len(entries),
            }

    def project_changelog_reset_history(self) -> dict[str, Any]:
        """
        F0115: reinitialise l historique git du projet (repart de zero).

        Un commit initial propre; les prochains commits portent les trailers
        renatus-component / renatus-path.
        """
        with self._lock:
            if self.api.read_only:
                raise PermissionError(
                    "GUI en lecture seule : reset historique impossible"
                )
            git = self._require_project_git()
            result = git.reinit_history(
                "chore: renatus history reset (component tracking F0115)"
            )
            self._work_branch = git.current_branch()
            # re-assurer branche de travail
            try:
                self._work_branch = git.ensure_work_branch()
            except Exception:
                pass
            return {
                "ok": True,
                "message": result.get("message")
                or "Historique git reinitialise",
                "branch": self._work_branch or git.current_branch(),
            }

    def project_changelog_commit(
        self,
        commit: str,
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        """
        Detail d un commit: fichiers touches + diff du fichier focus.

        Si path est omis, focus = premier fichier de la liste.
        """
        with self._lock:
            git = self._require_project_git()
            files = git.commit_files(commit)
            focus = path or (files[0] if files else None)
            diff = ""
            content = None
            if focus:
                data = git.file_diff_at(commit, focus)
                diff = data.get("diff") or ""
                content = git.file_content_at(commit, focus)
            step_id = self._step_id_from_path(focus) if focus else None
            # meta commit
            meta_r = git._run(
                "log",
                "-1",
                "--format=%H|%h|%cI|%s",
                commit,
                check=False,
            )
            short, date, subject = "", "", ""
            full = commit
            if meta_r.returncode == 0 and meta_r.stdout:
                parts = meta_r.stdout.strip().split("|", 3)
                if len(parts) >= 4:
                    full, short, date, subject = (
                        parts[0],
                        parts[1],
                        parts[2],
                        parts[3],
                    )
            return {
                "ok": True,
                "commit": full,
                "short": short or commit[:8],
                "date": date,
                "subject": subject,
                "files": files,
                "path": focus,
                "diff": diff,
                "content": content,
                "step_id": step_id,
                "branch": git.current_branch(),
                "message": "OK",
            }

    def project_changelog_apply(
        self,
        commit: str,
        *,
        mode: str = "file",
        path: str | None = None,
    ) -> dict[str, Any]:
        """
        Applique un etat passe en forward-only (nouveau commit, pas de reset).

        mode:
        - file: restaure uniquement `path` (fichier en cours de consultation)
        - all: restaure le snapshot complet au commit (tous les fichiers)
        """
        with self._lock:
            if self.api.read_only:
                raise PermissionError(
                    "GUI en lecture seule : apply version impossible"
                )
            git = self._require_project_git()
            mode_norm = (mode or "file").strip().lower()
            if mode_norm not in ("file", "all"):
                raise ValueError("mode doit etre 'file' ou 'all'")
            if mode_norm == "file":
                if not path:
                    files = git.commit_files(commit)
                    path = files[0] if files else None
                if not path:
                    raise ValueError("Aucun fichier a restaurer pour ce commit")
                result = git.restore_file_from_commit(
                    commit,
                    path,
                    message=f"apply file {path} from {commit[:8]} (ff)",
                )
            else:
                result = git.restore_snapshot_from_commit(
                    commit,
                    message=f"apply snapshot from {commit[:8]} (ff all)",
                )
            if not result.get("ok"):
                raise RuntimeError(result.get("message") or "Apply echoue")
            self._work_branch = result.get("branch") or git.current_branch()
            self._reload_pipeline()
            focus = path if mode_norm == "file" else None
            step_id = self._step_id_from_path(focus) if focus else None
            cfg = None
            if step_id and step_id in self.api.connection.pipeline:
                cfg = dict(self.api.connection.pipeline.get(step_id) or {})
            return {
                "ok": True,
                "mode": mode_norm,
                "path": focus,
                "from_commit": commit,
                "branch": self._work_branch,
                "committed": result.get("committed"),
                "paths": result.get("paths") or [],
                "removed": result.get("removed") or [],
                "step_id": step_id,
                "config": cfg,
                "message": result.get("message"),
                **self.workspace_info(),
            }

    def list_import_zones(self) -> dict[str, Any]:
        """Zones disponibles comme cible d import (F0102)."""
        with self._lock:
            tabs = self.list_tabs()
            zones = []
            seen: set[str] = set()
            for t in tabs.get("tabs") or []:
                tid = str(t.get("id") or "")
                # F0104: all n est pas une zone d import cible
                if (
                    not tid
                    or tid in seen
                    or tid == YamlStepStore.ALL_TAB
                    or t.get("virtual")
                ):
                    continue
                seen.add(tid)
                zones.append(
                    {
                        "id": tid,
                        "label": t.get("label") or tid,
                        "step_count": t.get("step_count"),
                    }
                )
            # zones connues du pipeline non ouvertes
            for sid, cfg in (self.api.connection.pipeline or {}).items():
                if not isinstance(cfg, dict):
                    continue
                if str(cfg.get("type") or "") != "zone":
                    continue
                zpath = self.store.zone_path_for(
                    sid, self.store.tab_of(sid)
                )
                if zpath in seen:
                    continue
                seen.add(zpath)
                zones.append(
                    {
                        "id": zpath,
                        "label": str(cfg.get("label") or sid),
                        "step_count": None,
                    }
                )
            zones.sort(key=lambda z: str(z["id"]))
            return {
                "ok": True,
                "zones": zones,
                "active_tab": self.active_tab,
            }

    def import_flow(
        self,
        source: str | Path,
        *,
        target_tab: str | None = None,
        conflict: str = "keep_both",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        F0102: importe un YAML ou un dossier de flux dans une zone cible.

        conflict: keep_both | keep_existing | replace
        dry_run: plan seulement (pas d ecriture)
        """
        from renatus.gui.import_flow import (
            apply_import_plan,
            collect_import_plan,
        )

        with self._lock:
            if self.api.read_only and not dry_run:
                raise PermissionError(
                    "GUI en lecture seule : import impossible"
                )
            src = Path(source).expanduser().resolve()
            target = (
                (target_tab or self.active_tab or YamlStepStore.ROOT_TAB)
                .strip()
                .replace("\\", "/")
            )
            if not target:
                target = YamlStepStore.ROOT_TAB
            existing = set(self.api.connection.pipeline.keys())
            plan = collect_import_plan(
                src,
                target_tab=target,
                existing_ids=existing,
                conflict=conflict,  # type: ignore[arg-type]
            )
            if dry_run:
                return {**plan, "dry_run": True}

            def ensure_zone(tab_path: str) -> bool:
                return self._ensure_zone_path_unlocked(tab_path)

            result = apply_import_plan(
                self.store,
                self.api.connection.pipeline,
                plan,
                ensure_zone_fn=ensure_zone,
            )
            # F0125: synchronise objects des zones (FS = source de verite)
            # et ouvre les chemins importes dans le selecteur.
            zone_tabs = list(plan.get("zone_tabs") or [])
            for ztab in zone_tabs:
                self._open_tab_id(ztab)
                zid = ztab.split("/")[-1] if ztab else ""
                if zid:
                    self._sync_zone_objects_from_fs_unlocked(zid)
            # parent cible (ex. main) recoit aussi les zones racines importees
            if target and target != YamlStepStore.ALL_TAB:
                parent_zid = (
                    YamlStepStore.ROOT_TAB
                    if target == YamlStepStore.ROOT_TAB
                    else target.split("/")[-1]
                )
                self._sync_zone_objects_from_fs_unlocked(parent_zid)
            # active la zone racine d import si creee (premier segment)
            root_import = None
            if zone_tabs:
                root_import = sorted(zone_tabs, key=lambda s: s.count("/"))[0]
                self._open_tab_id(root_import)
                self._active_tab = root_import
                self.store.active_tab = root_import
            self._reload_pipeline()
            self._autocommit(
                f"import flow {src.name} -> {target} "
                f"({result.get('count', 0)} steps)"
            )
            # F0143: purger le staging import_flow (deja integre dans flow/)
            cleaned = self._cleanup_import_flow_staging_unlocked(src)
            out = {
                **result,
                "target_tab": target,
                "source": str(src),
                "active_tab": self.active_tab,
                "root_import_tab": root_import,
                **self.list_tabs(),
            }
            if cleaned:
                out["staging_cleaned"] = cleaned
            return out

    def _cleanup_import_flow_staging_unlocked(
        self, source: Path
    ) -> dict[str, Any] | None:
        """
        F0143: supprime le dossier/fichier temporaire sous project/import_flow/
        apres un import reussi. Ne touche pas aux sources hors staging
        (chemin absolu utilisateur).
        """
        import shutil

        try:
            project_dir = Path(self.api.connection.project_dir).resolve()
            staging_root = (project_dir / "import_flow").resolve()
            src = Path(source).expanduser().resolve()
        except Exception:
            return None
        if not staging_root.is_dir():
            return None
        try:
            rel = src.relative_to(staging_root)
        except ValueError:
            # source hors import_flow — ne pas supprimer
            return None
        if not rel.parts:
            return None
        # supprime le bundle de 1er niveau (ex. mon_flow_2026-.../)
        # ou le fichier depose a la racine de import_flow/
        target = staging_root / rel.parts[0]
        if not target.exists():
            return None
        removed = str(target)
        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)
        except OSError as exc:
            return {
                "ok": False,
                "path": removed,
                "error": str(exc),
            }
        # si import_flow est vide, le laisser (gitignore) ou le garder
        return {"ok": True, "path": removed}

    def _sync_zone_objects_from_fs_unlocked(self, zone_id: str) -> None:
        """
        F0125: aligne config.objects d une zone sur le contenu FS du dossier.

        Presence dans une zone = fichiers <id>.yaml dans le dossier de zone
        (steps_in_tab) + declarations YAML existantes. Persiste le YAML zone.
        Appeler sous lock.
        """
        from renatus.pipeline.steps.org import (
            normalize_renatus_mode,
            normalize_zone_objects,
            normalize_zone_workers,
        )

        zid = str(zone_id or "").strip()
        if not zid:
            return
        pipeline = self.api.connection.pipeline
        if zid not in pipeline and zid != YamlStepStore.ROOT_TAB:
            return
        zcfg = pipeline.get(zid) if isinstance(pipeline.get(zid), dict) else {}
        if zid != YamlStepStore.ROOT_TAB and str(
            (zcfg or {}).get("type") or ""
        ) != "zone":
            return
        # chemin contenu
        if zid == YamlStepStore.ROOT_TAB:
            zpath = YamlStepStore.ROOT_TAB
        else:
            parent_tab = self.store.tab_of(zid)
            try:
                zpath = self.store.zone_path_for(zid, parent_tab)
            except Exception:
                zpath = zid
        declared = normalize_zone_objects((zcfg or {}).get("objects"))
        fs_ids = self.store.steps_in_tab(zpath)
        objects: dict[str, Any] = {}
        for oid, meta in declared.items():
            if oid == zid:
                continue
            if oid in pipeline or oid in fs_ids:
                objects[oid] = meta if isinstance(meta, dict) else {}
        for oid in sorted(fs_ids):
            if oid == zid or oid in objects:
                continue
            if oid not in pipeline:
                continue
            objects[oid] = {}
        label = str((zcfg or {}).get("label") or zid)
        workers = normalize_zone_workers((zcfg or {}).get("workers"))
        renatus_mode = normalize_renatus_mode(
            (zcfg or {}).get("renatus_mode")
        )
        new_cfg = {
            "type": "zone",
            "label": label,
            "objects": objects,
            "workers": workers,
            "renatus_mode": renatus_mode,
        }
        parent_tab = (
            YamlStepStore.ROOT_TAB
            if zid == YamlStepStore.ROOT_TAB
            else self.store.tab_of(zid)
        )
        try:
            self.store.save_step(zid, new_cfg, tab=parent_tab)
        except Exception:
            # zone absente disque: maj RAM seule
            pass
        pipeline[zid] = new_cfg

    def _ensure_zone_path_unlocked(self, tab_path: str) -> bool:
        """
        Cree dossiers + steps zone manquants pour un chemin (F0102 / F0125).
        Retourne True si au moins une zone a ete creee.
        Appeler sous lock. Enchaine parent → enfant et rattache objects.
        """
        path = (tab_path or "").strip().replace("\\", "/")
        if not path or path == YamlStepStore.ROOT_TAB:
            return False
        root = self.api.pipeline_path
        if root.is_file():
            raise ValueError(
                "Import de dossiers impossible : pipeline fichier unique"
            )
        created = False
        parts = [p for p in path.split("/") if p]
        for i, segment in enumerate(parts):
            parent = (
                "/".join(parts[:i])
                if i > 0
                else YamlStepStore.ROOT_TAB
            )
            zone_path = "/".join(parts[: i + 1])
            dest = self.store.dir_for_tab(zone_path)
            if not dest.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                created = True
            zone_id = segment
            parent_zone_id = (
                parts[i - 1]
                if i > 0
                else YamlStepStore.ROOT_TAB
            )
            # id deja pris
            if zone_id in self.api.connection.pipeline:
                existing_type = str(
                    (self.api.connection.pipeline[zone_id] or {}).get(
                        "type"
                    )
                    or ""
                )
                if existing_type == "zone":
                    # s assure du rattachement parent → enfant
                    self._attach_object_to_zone_unlocked(
                        parent_zone_id, zone_id
                    )
                    continue
                # conflit non-zone: dossier garde le segment, pas de step zone
                continue
            cfg = {
                "type": "zone",
                "label": zone_id,
                "objects": {},
                "workers": "auto",
                "renatus_mode": "required_for_leaves",
            }
            self.store.save_step(
                zone_id,
                cfg,
                tab=(
                    parent
                    if parent != YamlStepStore.ROOT_TAB
                    else YamlStepStore.ROOT_TAB
                ),
            )
            # maj RAM locale avant suite
            self.api.connection.pipeline[zone_id] = cfg
            self._attach_object_to_zone_unlocked(parent_zone_id, zone_id)
            created = True
        return created

    def _attach_object_to_zone_unlocked(
        self, zone_id: str, member_id: str
    ) -> None:
        """Ajoute member_id dans objects de zone_id (YAML + RAM). Sous lock."""
        zid = str(zone_id or "").strip()
        mid = str(member_id or "").strip()
        if not zid or not mid or zid == mid:
            return
        pipeline = self.api.connection.pipeline
        if zid not in pipeline:
            return
        pz = pipeline.get(zid)
        if not isinstance(pz, dict):
            return
        if str(pz.get("type") or "") != "zone" and zid != YamlStepStore.ROOT_TAB:
            return
        from renatus.pipeline.steps.org import normalize_zone_objects

        objects = normalize_zone_objects(pz.get("objects"))
        if mid in objects:
            return
        objects[mid] = {}
        new_pz = dict(pz)
        new_pz["type"] = "zone"
        new_pz["objects"] = objects
        if not new_pz.get("label"):
            new_pz["label"] = zid
        pipeline[zid] = new_pz
        parent_tab = (
            YamlStepStore.ROOT_TAB
            if zid == YamlStepStore.ROOT_TAB
            else self.store.tab_of(zid)
        )
        try:
            self.store.save_step(zid, new_pz, tab=parent_tab)
        except Exception:
            pass

    def create_step(
        self,
        name: str,
        config: dict[str, Any],
        *,
        tab: str | None = None,
    ) -> dict[str, Any]:
        """
        Cree une step.

        name = id applicatif (ex. dataframe_YYYY_MM_DD_hh_mm_ss).
        F0031/F0101: id = shortname fichier YAML (stem), immutable.
        F0128: auto-zones → id canonique + tab auto (definition seule).
        """
        from renatus.pipeline.steps.auto_zone import is_auto_zone_type

        cfg = dict(config or {})
        stype = str(cfg.get("type") or "").strip()
        if is_auto_zone_type(stype):
            # F0139: template → zone physique immediate
            return self.create_auto_zone(
                stype,
                object_id=cfg.get("object") or cfg.get("object_id"),
                parent_id=cfg.get("parent") or cfg.get("parent_id"),
                label=cfg.get("label"),
                name=cfg.get("name") or name,
            )

        step_id = YamlStepStore.normalize_step_id(name)
        with self._lock:
            if step_id in self.api.connection.pipeline:
                raise ValueError(
                    f"Id deja utilise : {step_id} "
                    "(l id est unique et non modifiable)"
                )
        if not cfg.get("label"):
            cfg["label"] = step_id
        return self.put_step(step_id, cfg, tab=tab)

    def create_auto_zone(
        self,
        kind: str,
        *,
        object_id: str | None = None,
        parent_id: str | None = None,
        label: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """
        F0139: template Auto → **zone physique normale** (type zone).

        L auto-zone n est plus un type persistant : a la creation on copie
        les YAML des membres calcules et on enregistre une vraie zone.

        - flatzone (ex allzone): parent zone requis → feuilles recursives
        - backzone / forzone / bidzone: object de reference requis
        """
        from renatus.pipeline.steps.auto_zone import (
            AUTO_ZONE_TYPES,
            auto_zone_id_for,
            compute_auto_zone_members,
            normalize_auto_kind,
        )
        from renatus.pipeline.steps.org import (
            normalize_renatus_mode,
            normalize_zone_workers,
        )
        import shutil

        k = normalize_auto_kind(kind)
        if k not in AUTO_ZONE_TYPES and k not in {
            "flatzone",
            "backzone",
            "forzone",
            "bidzone",
        }:
            raise ValueError(f"Type auto-zone invalide: {kind}")
        oid = str(object_id).strip() if object_id is not None else None
        parent = (
            str(parent_id).strip()
            if parent_id is not None and str(parent_id).strip()
            else None
        )
        if k in {"flatzone", "allzone"}:
            # parent = zone source (defaut: zone courante ou main)
            if not parent:
                parent = (
                    oid
                    or self.active_tab
                    or YamlStepStore.ROOT_TAB
                )
            parent = str(parent).strip() or YamlStepStore.ROOT_TAB
            # si path imbrique, id zone = dernier segment
            parent_zone = (
                parent
                if parent == YamlStepStore.ROOT_TAB
                else parent.split("/")[-1]
            )
            seed_ref = parent_zone
        else:
            if not oid:
                raise ValueError(f"{k}: object de reference requis")
            seed_ref = oid

        with self._lock:
            if self.api.read_only:
                raise PermissionError("GUI en lecture seule")
            pipe = self.api.connection.pipeline
            if k not in {"flatzone", "allzone"}:
                if oid not in pipe:
                    raise KeyError(f"Composant de reference absent: {oid}")
            else:
                if parent_zone != YamlStepStore.ROOT_TAB and parent_zone not in pipe:
                    raise KeyError(f"Zone parent absente: {parent_zone}")
                pcfg = pipe.get(parent_zone) if parent_zone != YamlStepStore.ROOT_TAB else {
                    "type": "zone"
                }
                if parent_zone != YamlStepStore.ROOT_TAB and str(
                    (pcfg or {}).get("type") or ""
                ) not in {"zone"}:
                    # parent path tab: accepte aussi tab path existant
                    if not self.store.dir_for_tab(parent).is_dir():
                        raise ValueError(
                            f"Parent doit etre une zone: {parent_zone}"
                        )

            def _members_of(zid: str) -> dict[str, Any]:
                return self.effective_zone_objects(zid)

            members_map = compute_auto_zone_members(
                k,
                pipe,
                object_id=oid,
                parent_id=parent_zone if k in {"flatzone", "allzone"} else None,
                main_step_ids=self.store.steps_in_tab(YamlStepStore.ROOT_TAB),
                members_of=_members_of,
            )
            member_ids = list(members_map.keys())

            # id zone physique unique
            if name and str(name).strip():
                base = YamlStepStore.normalize_step_id(str(name).strip())
            else:
                base = YamlStepStore.normalize_step_id(
                    auto_zone_id_for(k, seed_ref)
                )
            zid = base
            n = 2
            while zid in pipe or (
                self.api.pipeline_path.is_dir()
                and (self.api.pipeline_path / zid).exists()
            ):
                zid = f"{base}_{n}"
                n += 1

            lab = (
                str(label).strip()
                if label and str(label).strip()
                else zid
            )

            # Placement: sous l onglet actif (depot workspace), sinon main
            parent_tab = self.active_tab or YamlStepStore.ROOT_TAB
            if parent_tab in {
                YamlStepStore.ALL_TAB,
                "*",
                "_all",
            }:
                parent_tab = YamlStepStore.ROOT_TAB
            root = self.api.pipeline_path
            if not root.is_dir():
                raise ValueError(
                    "Pipeline fichier unique: creation zone impossible"
                )

            # dossier contenu
            zone_path = self.store.zone_path_for(zid, parent_tab)
            dest_dir = self.store.dir_for_tab(zone_path)
            if dest_dir.exists() and any(dest_dir.iterdir()):
                # evite ecraser
                raise ValueError(f"Dossier zone deja present: {zone_path}")
            dest_dir.mkdir(parents=True, exist_ok=True)

            objects: dict[str, Any] = {}
            copied: list[str] = []
            # F0145: materialise membres via symlinks (pas de copies YAML)
            for mid in member_ids:
                if mid not in pipe or mid == zid:
                    continue
                origin = self.store.origin_of(mid)
                if origin is None or not origin.is_file():
                    continue
                try:
                    self.store.attach_to_tab(mid, zone_path)
                except Exception:
                    continue
                objects[mid] = {}
                copied.append(mid)

            zcfg = {
                "type": "zone",
                "label": lab,
                "objects": objects,
                "workers": normalize_zone_workers(None),
                "renatus_mode": normalize_renatus_mode(None),
            }
            zpath = self.store.save_step(zid, zcfg, tab=parent_tab)
            self._reload_pipeline()
            # rattache a la zone parent du tab (default ou zone active)
            attach_parent = (
                YamlStepStore.ROOT_TAB
                if parent_tab == YamlStepStore.ROOT_TAB
                else parent_tab.split("/")[-1]
            )
            self._attach_object_to_zone_unlocked(attach_parent, zid)
            self._reload_pipeline()
            self._open_tab_id(zone_path)
            self._active_tab = zone_path
            self.store.active_tab = zone_path
            self._autocommit(
                f"init zone {zid} from template {k} "
                f"({len(copied)} symlink members)",
                components=[zid] + copied,
            )
            return {
                "ok": True,
                "id": zid,
                "name": zid,
                "reused": False,
                "type": "zone",
                "init_from": k,
                "config": self.api.connection.pipeline.get(zid),
                "file_origin": str(zpath),
                "message": (
                    f"Zone {zid} creee ({k}) — "
                    f"{len(copied)} composant(s) lies"
                ),
                "tab": zone_path,
                "zone_path": zone_path,
                "objects": objects,
                "member_count": len(copied),
                "copied": copied,
                "parent_source": parent_zone if k in {"flatzone", "allzone"} else oid,
                "active_tab": zone_path,
                **self.list_tabs(),
            }

    def convert_auto_zone(
        self,
        auto_id: str,
        *,
        new_zone_id: str | None = None,
    ) -> dict[str, Any]:
        """
        F0128: convertit une auto-zone en zone physique sous main.

        Copie les YAML des membres dans flow/<new_id>/ + definition zone.
        """
        from renatus.pipeline.steps.auto_zone import is_auto_zone_type
        from renatus.pipeline.steps.org import (
            normalize_renatus_mode,
            normalize_zone_workers,
        )
        import shutil

        aid = YamlStepStore.normalize_step_id(auto_id)
        with self._lock:
            if self.api.read_only:
                raise PermissionError("GUI en lecture seule")
            pipe = self.api.connection.pipeline
            cfg = pipe.get(aid)
            if not isinstance(cfg, dict) or not is_auto_zone_type(
                str(cfg.get("type") or "")
            ):
                raise KeyError(f"Auto-zone absente: {aid}")
            members = list(self.effective_zone_objects(aid).keys())
            # id zone physique
            base = (
                YamlStepStore.normalize_step_id(new_zone_id)
                if new_zone_id
                else YamlStepStore.normalize_step_id(f"z_{aid}")
            )
            zid = base
            n = 2
            while zid in pipe:
                zid = f"{base}_{n}"
                n += 1
            root = self.api.pipeline_path
            if not root.is_dir():
                raise ValueError("Pipeline fichier unique: convert impossible")
            zone_path = self.store.zone_path_for(zid, YamlStepStore.ROOT_TAB)
            dest_dir = self.store.dir_for_tab(zone_path)
            if dest_dir.exists() and any(dest_dir.iterdir()):
                raise ValueError(f"Dossier zone deja present: {zone_path}")
            dest_dir.mkdir(parents=True, exist_ok=True)
            objects: dict[str, Any] = {}
            copied: list[str] = []
            # F0145: liens symboliques vers les membres (pas de copies)
            for mid in members:
                if mid not in pipe:
                    continue
                origin = self.store.origin_of(mid)
                if origin is None or not origin.is_file():
                    continue
                try:
                    self.store.attach_to_tab(mid, zone_path)
                except Exception:
                    continue
                objects[mid] = {}
                copied.append(mid)
            zcfg = {
                "type": "zone",
                "label": str(cfg.get("label") or zid),
                "objects": objects,
                "workers": normalize_zone_workers(None),
                "renatus_mode": normalize_renatus_mode(None),
            }
            zpath = self.store.save_step(
                zid, zcfg, tab=YamlStepStore.ROOT_TAB
            )
            self._reload_pipeline()
            self._open_tab_id(zone_path)
            self._active_tab = zone_path
            self.store.active_tab = zone_path
            self._autocommit(
                f"convert auto-zone {aid} -> zone {zid}",
                components=[zid] + copied,
            )
            return {
                "ok": True,
                "id": zid,
                "zone_id": zid,
                "from_auto": aid,
                "copied": copied,
                "objects": objects,
                "file_origin": str(zpath),
                "message": (
                    f"Zone {zid} creee depuis {aid} "
                    f"({len(copied)} fichier(s) copies)"
                ),
                "active_tab": zid,
                **self.list_tabs(),
            }

    def _resolve_session_python(
        self,
        *,
        venv: str | None = None,
        step_id: str | None = None,
    ) -> tuple[Any, Any]:
        """
        Resolut (python_exe, project_dir) pour la session notebook / kernel.
        """
        from renatus.pipeline.steps.python_action import resolve_venv_python

        con = self.api.connection
        project_dir = Path(con.project_dir).resolve()
        venv_str = (venv or "").strip() or None
        if not venv_str and step_id:
            cfg = con.pipeline.get(step_id) or {}
            if isinstance(cfg, dict) and cfg.get("venv"):
                venv_str = str(cfg.get("venv")).strip() or None
        python_exe = resolve_venv_python(project_dir, venv_str)
        return python_exe, project_dir

    def python_session_vars(
        self,
        *,
        venv: str | None = None,
        step_id: str | None = None,
    ) -> dict[str, Any]:
        """
        F0137: liste les variables du noyau Python de session.
        """
        with self._lock:
            python_exe, project_dir = self._resolve_session_python(
                venv=venv, step_id=step_id
            )
            kernel = self.api.connection.get_python_kernel(
                python_exe, cwd=project_dir
            )
            data = kernel.list_vars()
            return {
                "ok": True,
                **data,
                "step_id": step_id,
            }

    def python_session_exec(
        self,
        code: str,
        *,
        venv: str | None = None,
        step_id: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """
        F0137: execute du code dans le noyau session (sans build step).
        Conserve le namespace (dataframes, imports…).
        """
        with self._lock:
            if self.api.read_only:
                raise PermissionError("GUI en lecture seule")
            python_exe, project_dir = self._resolve_session_python(
                venv=venv, step_id=step_id
            )
            kernel = self.api.connection.get_python_kernel(
                python_exe, cwd=project_dir
            )
            to = 60.0 if timeout is None else float(timeout)
            if to <= 0:
                to = 60.0
            try:
                result = kernel.exec(str(code or ""), timeout=to)
            except TimeoutError as exc:
                raise RuntimeError(str(exc)) from exc
            # optionnel: refresh vars apres exec
            try:
                vars_data = kernel.list_vars()
                vars_list = vars_data.get("vars") or []
            except Exception:
                vars_list = []
            return {
                "ok": True,
                "returncode": result.get("returncode"),
                "stdout": result.get("stdout") or "",
                "stderr": result.get("stderr") or "",
                "python": result.get("python"),
                "cwd": result.get("cwd"),
                "session": True,
                "vars": vars_list,
                "step_id": step_id,
            }

    def _detach_deleted_from_dependents(
        self, step_id: str
    ) -> list[str]:
        """
        A0010: avant suppression, retire step_id des requires (et zone.objects)
        de tous les autres composants pour garder le pipeline valide.
        """
        sid = str(step_id)
        pipeline = self.api.connection.pipeline
        updated: list[str] = []
        for name, config in list(pipeline.items()):
            if name == sid or not isinstance(config, dict):
                continue
            changed = False
            new_cfg = dict(config)
            # requires
            reqs = list(new_cfg.get("requires") or [])
            if any(str(r) == sid for r in reqs):
                new_cfg["requires"] = [r for r in reqs if str(r) != sid]
                changed = True
            # zone.objects membership
            if str(new_cfg.get("type") or "") == "zone":
                objects = new_cfg.get("objects")
                if isinstance(objects, dict) and sid in objects:
                    objects = dict(objects)
                    objects.pop(sid, None)
                    new_cfg["objects"] = objects
                    changed = True
                elif isinstance(objects, list) and sid in [
                    str(x) for x in objects
                ]:
                    new_cfg["objects"] = [
                        x for x in objects if str(x) != sid
                    ]
                    changed = True
            if not changed:
                continue
            tab = self.store.tab_of(name)
            self.store.save_step(name, new_cfg, tab=tab)
            # maj RAM avant suite
            pipeline[name] = new_cfg
            updated.append(name)
        return updated

    def _evict_members_from_zone(
        self,
        member_ids: list[str],
        zone_content_tab: str,
    ) -> list[str]:
        """
        A0016: retire des membres d une zone apres edition Objects.

        - multi-copies → detach_from_tab (retire la copie de la zone)
        - seule copie → suppression complete de l objet (cascade sous-zones)

        Retourne la liste des ids supprimes.
        """
        deleted: list[str] = []
        # non-zones d abord, puis zones (profondeur decroissante)
        pipeline = self.api.connection.pipeline

        def _is_zone(oid: str) -> bool:
            cfg = pipeline.get(oid) or {}
            return str(cfg.get("type") or "") == "zone"

        def _zone_depth(oid: str, seen: set[str] | None = None) -> int:
            if not _is_zone(oid):
                return 0
            st = seen or set()
            if oid in st:
                return 0
            st.add(oid)
            members = self.effective_zone_objects(oid)
            depths = [
                _zone_depth(m, st)
                for m in members
                if m != oid and _is_zone(m)
            ]
            return 1 + (max(depths) if depths else 0)

        ordered = sorted(
            member_ids,
            key=lambda oid: (
                1 if _is_zone(oid) else 0,
                -_zone_depth(oid) if _is_zone(oid) else 0,
                str(oid),
            ),
        )
        for oid in ordered:
            if not oid or oid == YamlStepStore.ROOT_TAB:
                continue
            # peut deja avoir ete cascade-supprime
            if oid not in self.api.connection.pipeline and not self.store.origins_of(
                oid
            ):
                continue
            try:
                self.store.detach_from_tab(oid, zone_content_tab)
            except LookupError:
                # pas de copie dans cet onglet (deja hors FS) — OK
                continue
            except ValueError:
                # seule copie → supprimer l objet (cascade si sous-zone)
                self._delete_step_cascade_unlocked(oid)
                deleted.append(oid)
        return deleted

    def _delete_step_cascade_unlocked(self, name: str) -> None:
        """
        A0016: supprime un composant ; si zone, vide d abord ses membres.

        Doit etre appele sous self._lock (RLock).
        """
        sid = str(name).strip()
        if not sid or sid in {
            YamlStepStore.ROOT_TAB,
            YamlStepStore.LEGACY_ROOT_TAB,
        }:
            raise ValueError(
                f"Zone {YamlStepStore.ROOT_TAB} protegee : "
                "suppression interdite"
            )
        if sid not in self.api.connection.pipeline:
            # fichier orphelin eventuel
            paths = self.store.origins_of(sid)
            for p in paths:
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
            self.store.refresh()
            return
        cfg = self.api.connection.pipeline.get(sid) or {}
        st = str(cfg.get("type") or "")
        if st == "zone":
            members = list(self.effective_zone_objects(sid).keys())
            zpath = self.store.zone_path_for(sid, self.store.tab_of(sid))
            # vider la zone (recursif) avant de supprimer le conteneur
            if members:
                self._evict_members_from_zone(members, zpath)
            # recharger etat apres evictions
            self._reload_pipeline()
        # suppression (reentre sur RLock)
        self.delete_step(sid)

    def delete_step(self, name: str) -> dict[str, Any]:
        """Supprime une step du YAML d'origine et recharge le pipeline."""
        with self._lock:
            if self.api.read_only:
                raise PermissionError(
                    "GUI en lecture seule : delete impossible"
                )
            if name not in self.api.connection.pipeline:
                raise KeyError(f"Objet absent du pipeline : {name}")
            cfg = self.api.connection.pipeline[name]
            step_type = str(cfg.get("type") or "")
            # F0082: zone main protegee (flow/main/)
            if (
                str(name) == YamlStepStore.ROOT_TAB
                or (
                    step_type == "zone"
                    and str(name) == YamlStepStore.ROOT_TAB
                )
            ):
                raise ValueError(
                    "Zone main protegee : suppression interdite"
                )
            # A0010: detacher des requires/objects des dependants AVANT delete
            detached = self._detach_deleted_from_dependents(str(name))
            parent_tab = self.store.tab_of(name)
            paths = self.store.origins_of(name)
            if not paths:
                raise LookupError(f"Fichier YAML introuvable pour {name}")
            # F0052: zone — dossier doit etre vide avant suppression
            # A0016: si encore du contenu, cascade (evite erreur « non vide »)
            closed_tabs: list[str] = []
            if step_type == "zone":
                folder = self.store.zone_folder_for(name, parent_tab)
                zpath = self.store.zone_path_for(name, parent_tab)
                if folder.is_dir():
                    remaining = [
                        p
                        for p in folder.iterdir()
                        if p.name != f"{name}.yaml"
                    ]
                    if remaining:
                        # vider d abord (membres effectifs)
                        members = list(
                            self.effective_zone_objects(str(name)).keys()
                        )
                        if members:
                            self._evict_members_from_zone(members, zpath)
                            self._reload_pipeline()
                        # re-check
                        remaining = [
                            p
                            for p in folder.iterdir()
                            if p.name != f"{name}.yaml"
                        ]
                        if remaining:
                            raise ValueError(
                                f"Zone {name} non vide "
                                f"({len(remaining)} element(s)) ; "
                                "supprimez le contenu d abord"
                            )
                # F0064: fermer l onglet zone + sous-onglets ouverts
                closed_tabs = self._close_open_tabs_for_zone(zpath)
            # F0060/F0145: supprimer toutes les presences (symlinks d abord)
            ordered = sorted(
                paths,
                key=lambda p: (0 if p.is_symlink() else 1, str(p)),
            )
            for origin in ordered:
                try:
                    if origin.is_symlink():
                        origin.unlink(missing_ok=True)
                        fold = origin.with_suffix("")
                        if fold.is_symlink():
                            fold.unlink(missing_ok=True)
                        continue
                    if not origin.is_file():
                        continue
                    content = yaml.safe_load(
                        origin.read_text(encoding="utf-8")
                    ) or {}
                    if isinstance(content, dict) and name in content:
                        del content[name]
                        if content:
                            origin.write_text(
                                yaml.dump(
                                    content,
                                    default_flow_style=False,
                                    allow_unicode=True,
                                    sort_keys=False,
                                ),
                                encoding="utf-8",
                            )
                        else:
                            origin.unlink(missing_ok=True)
                    else:
                        origin.unlink(missing_ok=True)
                except OSError:
                    pass
            if step_type == "zone":
                # tous les dossiers zone (reel + symlinks de dossier)
                for origin in ordered:
                    fold = origin.with_suffix("")
                    try:
                        if fold.is_symlink():
                            fold.unlink(missing_ok=True)
                        elif fold.is_dir() and not any(fold.iterdir()):
                            fold.rmdir()
                    except OSError:
                        pass
                folder = self.store.zone_folder_for(name, parent_tab)
                try:
                    if folder.is_symlink():
                        folder.unlink(missing_ok=True)
                    elif folder.is_dir() and not any(folder.iterdir()):
                        folder.rmdir()
                except OSError:
                    pass
            self._reload_pipeline()
            self._autocommit(
                f"delete step {name}",
                components=[str(name)],
            )
            # F0064: renvoyer l etat des onglets pour resync GUI
            tabs_state = self.list_tabs()
            msg = f"Step {name} supprimee ({len(paths)} presence(s))"
            if detached:
                msg += f" ; requires nettoyes sur {len(detached)} dependant(s)"
            return {
                "ok": True,
                "name": name,
                "message": msg,
                "closed_tabs": closed_tabs,
                "detached_from": detached,
                **tabs_state,
            }

    @staticmethod
    def config_to_yaml(config: dict[str, Any]) -> str:
        """Dump YAML (meme style que la persistence pipeline)."""
        if not isinstance(config, dict):
            raise TypeError("config doit etre un dict")
        return yaml.dump(
            config,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    @staticmethod
    def yaml_to_config(text: str) -> dict[str, Any]:
        """Parse YAML vers dict config step.

        Leve yaml.YAMLError ou ValueError si le texte est invalide
        (message exploitable cote GUI pour corriger le fichier).
        """
        try:
            parsed = yaml.safe_load(text or "") or {}
        except yaml.YAMLError:
            raise
        if not isinstance(parsed, dict):
            raise ValueError("YAML doit decrire un objet (mapping)")
        return parsed

    def upload_input_file(
        self,
        filename: str,
        content: bytes,
        *,
        subdir: str = "input",
        relative_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Enregistre un fichier local (picker / drag-drop) sous project_dir/subdir/.

        Convenience UI uniquement (F0043) : le dossier input/ est gitignore.
        Preferer un chemin absolu hors projet pour les donnees privees.

        F0107: relative_path optionnel (arborescence dossier import flux)
        ex. mon_flow/sub/a.yaml sous subdir=import_flow.

        Retourne le chemin relatif a utiliser dans config.file (ex: input/sales.csv).
        """
        with self._lock:
            if self.api.read_only:
                raise PermissionError(
                    "GUI en lecture seule : upload impossible"
                )
            project_dir = self.api.connection.project_dir
            dest_dir = (project_dir / subdir).resolve()
            # ensure dest_dir stays under project_dir
            if not is_under_directory(dest_dir, project_dir):
                raise ValueError("Sous-dossier hors projet")

            rel_under: Path
            if relative_path and str(relative_path).strip():
                # F0107: chemin relatif sanitize (pas de .., pas d absolu)
                raw = str(relative_path).replace("\\", "/").strip().lstrip("/")
                parts = [p for p in Path(raw).parts if p not in ("", ".", "..")]
                if not parts:
                    raise ValueError("Chemin relatif invalide")
                # chaque segment simple
                for p in parts:
                    if Path(p).name != p or p.startswith("."):
                        raise ValueError(f"Segment de chemin invalide: {p}")
                rel_under = Path(*parts)
            else:
                safe_name = Path(filename).name
                if not safe_name or safe_name in {".", ".."}:
                    raise ValueError("Nom de fichier invalide")
                if Path(safe_name).name != safe_name:
                    raise ValueError("Nom de fichier invalide")
                rel_under = Path(safe_name)

            dest = (dest_dir / rel_under).resolve()
            try:
                dest.relative_to(dest_dir)
            except ValueError as exc:
                raise ValueError("Chemin hors sous-dossier cible") from exc

            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            rel = f"{subdir.rstrip('/')}/{rel_under.as_posix()}"
            return {
                "ok": True,
                "filename": dest.name,
                "path": rel,
                "absolute": str(dest),
                "size": len(content),
                "git_tracked": False,
                "message": (
                    f"Fichier enregistre : {rel} "
                    "(hors git — preferer un chemin absolu pour donnees privees)"
                ),
            }

    @staticmethod
    def _page_payload_from_relation_data(
        data: Any,
        *,
        name: str,
        relation_name: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """F0123: champs pagination communs (preview / result)."""
        limit = getattr(data, "limit", None)
        offset = int(getattr(data, "offset", 0) or 0)
        total_rows = getattr(data, "total_rows", None)
        page = getattr(data, "page", None)
        page_size = getattr(data, "page_size", None) or limit
        total_pages = getattr(data, "total_pages", None)
        rows = list(getattr(data, "rows", None) or [])
        out: dict[str, Any] = {
            "ok": True,
            "name": name,
            "relation_name": relation_name,
            "columns": list(getattr(data, "columns", None) or []),
            "rows": rows,
            "row_count": len(rows),
            "truncated": bool(getattr(data, "truncated", False)),
            "limit": limit,
            "offset": offset,
            "total_rows": total_rows,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_prev": offset > 0,
            "has_next": bool(getattr(data, "truncated", False)),
        }
        if total_rows is not None:
            out["message"] = (
                f"lignes {offset + 1}–{offset + len(rows)} / {total_rows}"
                if rows
                else f"0 / {total_rows} ligne(s)"
            )
        else:
            out["message"] = f"{len(rows)} ligne(s) (limit {limit})"
        if extra:
            out.update(extra)
        return out

    def preview(
        self,
        name: str,
        *,
        limit: int = 3,
        offset: int = 0,
        build_if_missing: bool = False,
    ) -> dict[str, Any]:
        """
        DataView: page de `limit` lignes (defaut 3) + offset (F0123 pagination).

        Si ``build_if_missing`` (bouton Renatus View): toujours ``build``
        chronometre (F0093 renatus_time + schema/shape a jour apres).
        Sinon lecture seule si materialise; dataframe orphelin en session
        peut etre re-register legerement pour l apercu.
        """
        with self._lock:
            con = self.api.connection
            rel = (
                con.relation_name(name)
                if name in con.pipeline
                else name
            )
            off = max(0, int(offset or 0))
            # A0014 / F0093: Renatus View = build unifie (temps + datasets)
            if build_if_missing:
                built = self._build_one_unlocked(name, limit=limit)
                out = dict(built)
                out["relation_name"] = rel
                out["exists"] = True
                out["built"] = True
                # F0123: toujours re-lire une page (pas toute la table)
                if con.relation_exists(rel):
                    data = self.api.table_view(
                        name, limit=limit, offset=off
                    )
                    page = self._page_payload_from_relation_data(
                        data,
                        name=name,
                        relation_name=rel,
                        extra={
                            "exists": True,
                            "built": True,
                            "has_result": True,
                        },
                    )
                    if out.get("message"):
                        page["build_message"] = out["message"]
                    for k in (
                        "renatus_time",
                        "stdout",
                        "stderr",
                        "returncode",
                        "python",
                        "member_renatus_times",
                        "action",
                    ):
                        if k in out and out[k] is not None:
                            page[k] = out[k]
                    return page
                return out

            exists = con.relation_exists(rel)
            built_flag = False

            # Dataframe: register session (catalogue temp) peut manquer
            # apres un redemarrage — re-process leger depuis le fichier.
            if (
                not exists
                and name in con.pipeline
                and str(con.pipeline[name].get("type", "")) == "dataframe"
            ):
                try:
                    con.process(name)
                    exists = con.relation_exists(rel)
                    built_flag = exists
                except Exception:
                    exists = False

            if not exists:
                return {
                    "ok": True,
                    "name": name,
                    "relation_name": rel,
                    "exists": False,
                    "built": False,
                    "columns": [],
                    "rows": [],
                    "row_count": 0,
                    "limit": limit,
                    "offset": off,
                    "total_rows": 0,
                    "page": 1,
                    "page_size": limit,
                    "total_pages": 0,
                    "has_prev": False,
                    "has_next": False,
                    "message": (
                        f"Dataset {rel} non materialise. "
                        "Utilisez Build pour le generer."
                    ),
                }

            data = self.api.table_view(name, limit=limit, offset=off)
            return self._page_payload_from_relation_data(
                data,
                name=name,
                relation_name=rel,
                extra={"exists": True, "built": built_flag},
            )
