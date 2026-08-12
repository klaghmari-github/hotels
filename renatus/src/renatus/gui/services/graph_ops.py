"""
GraphOps — construction du graphe requires / catalogue (F0054-S1 / F0056).

F0056: onglet zone = membres de config.objects (ids), pas seulement FS.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from renatus.pipeline.steps import create_step
from renatus.pipeline.steps.org import normalize_zone_objects

from ..schemas import GraphEdge
from ..yaml_store import YamlStepStore

if TYPE_CHECKING:
    from ..service import GuiService


class GraphOps:
    """Construit nodes / edges / catalog pour un onglet (ou graphe complet)."""

    def __init__(self, gui: GuiService) -> None:
        self.gui = gui

    def zone_id_for_tab(
        self, tab_id: str, pipeline: dict[str, Any]
    ) -> str | None:
        """
        Si l onglet correspond a une zone (chemin ou id), renvoie l id step zone.

        Ex: tab zone_etl → step zone_etl ; tab a/b → step b si type zone.
        F0128: auto/bac_x → bac_x (type backzone).
        """
        from renatus.pipeline.steps.auto_zone import is_auto_zone_type

        tid = (tab_id or "").strip()
        if not tid or tid == YamlStepStore.ROOT_TAB:
            return None
        if tid == YamlStepStore.AUTO_TAB:
            return None

        def _is_zone_like(cfg: Any) -> bool:
            if not isinstance(cfg, dict):
                return False
            t = str(cfg.get("type") or "")
            return t == "zone" or is_auto_zone_type(t)

        # chemin imbrique: dernier segment = id zone
        candidate = tid.split("/")[-1]
        cfg = pipeline.get(candidate)
        if _is_zone_like(cfg):
            return candidate
        # id direct
        cfg2 = pipeline.get(tid)
        if _is_zone_like(cfg2):
            return tid
        return None

    def members_for_tab(
        self, tab_id: str, pipeline: dict[str, Any]
    ) -> set[str]:
        """
        Ensemble d ids a afficher dans le graphe de l onglet.

        - main (ou non-zone): steps dont le fichier est dans le tab (FS)
          + toutes les steps type zone dont le parent tab est ce tab
        - onglet zone: union des objects de la zone + eventuels objets
          encore poses dans le dossier FS de la zone
        """
        gui = self.gui
        from renatus.pipeline.steps.auto_zone import is_auto_zone_type

        zone_id = self.zone_id_for_tab(tab_id, pipeline)
        if zone_id:
            zcfg = pipeline.get(zone_id) or {}
            # F0128: auto-zone = membership calcule (vue logique)
            if is_auto_zone_type(str((zcfg or {}).get("type") or "")):
                objs = gui.effective_zone_objects(zone_id)
                return set(objs.keys())
            # F0060: presence = fichiers dans le dossier de la zone
            allowed = gui.store.steps_in_tab(tab_id)
            # + objects declares (sync disque a la sauvegarde zone)
            objects = normalize_zone_objects(zcfg.get("objects"))
            allowed |= {oid for oid in objects if oid in pipeline}
            allowed.discard(zone_id)
            return allowed

        # Racine / pack FS classique
        allowed = gui.store.steps_in_tab(tab_id)
        for name in pipeline:
            if name not in gui.store._origins:
                if (gui.store.active_tab or YamlStepStore.ROOT_TAB) == (
                    tab_id or YamlStepStore.ROOT_TAB
                ):
                    allowed.add(name)
        return allowed

    def build(self, tab: str | None = None) -> dict[str, Any]:
        """
        Graphe des steps.

        Si tab est fourni (ou active_tab), ne renvoie que les noeuds de
        cet onglet et les aretes internes (F0027 / F0056 objects).
        tab="*" ou tab="_all" : graphe complet.
        """
        gui = self.gui
        gui.store.refresh()
        raw_tab = tab if tab is not None else gui.active_tab
        show_all = raw_tab in {"*", "_all", "all"}
        from renatus.pipeline.steps.auto_zone import is_auto_zone_type

        pipeline = gui.api.connection.pipeline
        # F0144: normalise sous default/ sauf vues speciales / auto-zones
        if show_all:
            tab_id = YamlStepStore.ALL_TAB
        else:
            leaf = str(raw_tab or YamlStepStore.ROOT_TAB).strip()
            leaf_id = leaf.split("/")[-1] if leaf else leaf
            acfg = pipeline.get(leaf_id) if leaf_id in pipeline else None
            if acfg and is_auto_zone_type(str(acfg.get("type") or "")):
                tab_id = leaf_id
            else:
                tab_id = gui.store.normalize_tab_id(raw_tab)
        if show_all:
            # F0104 / F0128: vue "all" = tous les composants, SANS
            # zones ni auto-zones (vues logiques).
            allowed = {
                name
                for name, cfg in pipeline.items()
                if isinstance(cfg, dict)
                and str(cfg.get("type") or "") != "zone"
                and not is_auto_zone_type(str(cfg.get("type") or ""))
            }
        else:
            allowed = self.members_for_tab(
                tab_id or YamlStepStore.ROOT_TAB, pipeline
            )

        def _node_dict(
            name: str, *, external: bool = False
        ) -> dict[str, Any]:
            config = pipeline[name]
            origin = gui.store.origin_of(name)
            step = create_step(name, config)
            step_type = step.type
            rel_name = (
                gui.api.connection.relation_name(name)
                if step.produces_relation()
                else name
            )
            parent_tab = gui.store.tab_of(name)
            zone_path = None
            objects = None
            from renatus.pipeline.steps.auto_zone import is_auto_zone_type

            if step_type == "zone" or is_auto_zone_type(step_type):
                # F0131: auto-zone → zone_path = id (vue logique, pas auto/)
                if is_auto_zone_type(step_type):
                    zone_path = name
                else:
                    zone_path = gui.store.zone_path_for(name, parent_tab)
                # A0015 / F0128: objets effectifs (YAML ∪ FS ou calcule auto)
                objects = gui.effective_zone_objects(name)
            reqs = config.get("requires") or []
            if not isinstance(reqs, list):
                reqs = []
            return {
                "id": name,
                "label": str(config.get("label") or name),
                "type": step_type,
                "mode": config.get("mode"),
                "file_origin": str(origin) if origin else None,
                "relation_name": rel_name,
                "tab": parent_tab,
                "zone_path": zone_path,
                "objects": objects,
                # F0127: requires pour lineage client (grise hors amont)
                "requires": [str(r) for r in reqs if r is not None],
                # F0057: zones calculees (informatives; hors YAML)
                "zones": gui.zones_of(name),
                "external": bool(external),
            }

        node_rows: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        external_ids: set[str] = set()
        for name in sorted(allowed):
            if name not in pipeline:
                continue
            config = pipeline[name]
            node_rows.append(_node_dict(name, external=False))
            for dep in config.get("requires") or []:
                dep_s = str(dep)
                if dep_s in allowed:
                    edges.append(
                        GraphEdge(from_=dep_s, to=name).to_dict()
                    )
                elif (
                    not show_all
                    and dep_s in pipeline
                    and dep_s not in allowed
                ):
                    # F0039: require cross-onglet → noeud fantome + arete
                    external_ids.add(dep_s)
                    edges.append(
                        GraphEdge(from_=dep_s, to=name).to_dict()
                    )

        for dep_s in sorted(external_ids):
            node_rows.append(_node_dict(dep_s, external=True))

        # Catalogue leger pour pickers requires / zone.objects (ids stables).
        # F0133: ne pas reutiliser _node_dict pour TOUT le pipeline
        # (zones_of sur chaque step → O(n^2) et hang graphe apres gros import).
        # objects effectifs seulement pour les zones (besoin pickers / A0015).
        catalog: list[dict[str, Any]] = []
        for name in sorted(pipeline.keys()):
            cfg = pipeline.get(name)
            if not isinstance(cfg, dict):
                continue
            try:
                st = create_step(name, cfg)
                stype = st.type
            except Exception:
                stype = str(cfg.get("type") or "unknown")
            entry: dict[str, Any] = {
                "id": name,
                "label": str(cfg.get("label") or name),
                "type": stype,
                "mode": cfg.get("mode"),
                "tab": gui.store.tab_of(name),
                "external": False,
                "requires": [
                    str(r)
                    for r in (cfg.get("requires") or [])
                    if r is not None
                ]
                if isinstance(cfg.get("requires"), list)
                else [],
            }
            if stype == "zone" or is_auto_zone_type(stype):
                entry["objects"] = gui.effective_zone_objects(name)
            catalog.append(entry)

        zone_id = (
            None
            if show_all
            else self.zone_id_for_tab(
                tab_id or YamlStepStore.ROOT_TAB, pipeline
            )
        )

        return {
            "ok": True,
            # F0104: tab "all" reste identifiable cote UI
            "tab": (
                YamlStepStore.ALL_TAB
                if show_all
                else (tab_id or YamlStepStore.ROOT_TAB)
            ),
            "zone_id": zone_id,
            "virtual": bool(show_all),
            "nodes": node_rows,
            "edges": edges,
            "catalog": catalog,
        }
