"""
Auto-zone — initialisateurs de zone (F0128 / F0139).

Modele F0139:
  Une auto-zone n est **pas** un type persistant. C est un **constructeur**
  qui cree une zone physique normale (`type: zone`) avec une initialisation
  particuliere (copie des YAML membres).

Templates palette:
  - flatzone (ex allzone): parent zone → tous les objets feuille recursifs
  - backzone: object ref → requires recursifs
  - forzone: object ref → required_by recursifs
  - bidzone: object ref → amont + aval

Legacy: types allzone/backzone/... encore reconnus en lecture seule
jusqu a migration / convert.
"""

from __future__ import annotations

from typing import Any, Callable, ClassVar

from .org import OrgStep, ZoneStep, normalize_zone_objects

# Templates d initialisation (palette Auto)
AUTO_ZONE_TYPES = frozenset(
    {"flatzone", "allzone", "backzone", "forzone", "bidzone"}
)
# Alias creation
AUTO_ZONE_ALIASES = {
    "allzone": "flatzone",
    "all": "flatzone",
    "flat": "flatzone",
}
AUTO_TAB = "auto"
AUTO_PREFIX = {
    "flatzone": "flat_",
    "allzone": "flat_",
    "backzone": "bac_",
    "forzone": "for_",
    "bidzone": "bid_",
}


def is_auto_zone_type(type_name: str | None) -> bool:
    """True si type legacy ou template (pas une zone deja materialisee)."""
    t = str(type_name or "").strip()
    return t in AUTO_ZONE_TYPES


def normalize_auto_kind(kind: str | None) -> str:
    k = str(kind or "").strip()
    return AUTO_ZONE_ALIASES.get(k, k)


def auto_zone_id_for(kind: str, object_id: str | None = None) -> str:
    """
    Suggestion d id pour une zone creee depuis un template.

    Non garanti unique — l appelant suffixe si besoin.
    """
    k = normalize_auto_kind(kind)
    pref = AUTO_PREFIX.get(k, "z_")
    if k in {"flatzone", "allzone"}:
        oid = str(object_id or "main").strip() or "main"
        return f"{pref}{oid}"
    oid = str(object_id or "").strip()
    if not oid:
        raise ValueError(f"{k}: object de reference requis")
    if pref and oid.startswith(pref):
        return oid
    return f"{pref}{oid}"


def main_level_non_zone_ids(
    pipeline: dict[str, Any], main_step_ids: set[str]
) -> list[str]:
    """Composants du niveau main (hors type zone / auto)."""
    out: list[str] = []
    for sid in sorted(main_step_ids):
        cfg = pipeline.get(sid)
        if not isinstance(cfg, dict):
            continue
        t = str(cfg.get("type") or "")
        if t == "zone" or is_auto_zone_type(t):
            continue
        out.append(sid)
    return out


def recursive_requires(
    start_id: str,
    pipeline: dict[str, Any],
) -> set[str]:
    """Amont: requires recursifs (+ start)."""
    out: set[str] = set()
    stack = [str(start_id)]
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        cfg = pipeline.get(cur)
        if not isinstance(cfg, dict):
            continue
        for r in cfg.get("requires") or []:
            rid = str(r).strip()
            if rid and rid not in out and rid in pipeline:
                stack.append(rid)
    return out


def recursive_dependents(
    start_id: str,
    pipeline: dict[str, Any],
) -> set[str]:
    """Aval: required_by recursif (+ start)."""
    rev: dict[str, list[str]] = {}
    for sid, cfg in pipeline.items():
        if not isinstance(cfg, dict):
            continue
        for r in cfg.get("requires") or []:
            rid = str(r).strip()
            if not rid:
                continue
            rev.setdefault(rid, []).append(str(sid))
    out: set[str] = set()
    stack = [str(start_id)]
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        for d in rev.get(cur) or []:
            if d not in out and d in pipeline:
                stack.append(d)
    return out


def recursive_zone_leaf_ids(
    zone_id: str,
    pipeline: dict[str, Any],
    members_of: Callable[[str], dict[str, Any] | set[str] | list[str]],
) -> set[str]:
    """
    F0139 flatzone: tous les composants **feuille** (non-zone) sous zone_id,
    en parcourant recursivement les sous-zones.
    """
    leaves: set[str] = set()
    seen_zones: set[str] = set()
    stack = [str(zone_id)]
    while stack:
        z = stack.pop()
        if not z or z in seen_zones:
            continue
        seen_zones.add(z)
        raw = members_of(z)
        if isinstance(raw, dict):
            mids = list(raw.keys())
        else:
            mids = list(raw or [])
        for mid in mids:
            mid = str(mid)
            if mid == z:
                continue
            cfg = pipeline.get(mid)
            if not isinstance(cfg, dict):
                continue
            t = str(cfg.get("type") or "")
            if t == "zone" or is_auto_zone_type(t):
                stack.append(mid)
            else:
                leaves.add(mid)
    return leaves


def compute_auto_zone_members(
    kind: str,
    pipeline: dict[str, Any],
    *,
    object_id: str | None = None,
    parent_id: str | None = None,
    main_step_ids: set[str] | None = None,
    members_of: Callable[[str], dict[str, Any] | set[str] | list[str]]
    | None = None,
) -> dict[str, Any]:
    """
    Calcule le set d ids a copier pour initialiser une zone depuis un template.

    - flatzone / allzone: feuilles recursives de parent (defaut main)
    - back / for / bid: lineage autour de object_id
    """
    k = normalize_auto_kind(kind)
    members: set[str] = set()
    skip_types = {"zone"} | set(AUTO_ZONE_TYPES)

    if k in {"flatzone", "allzone"}:
        parent = str(parent_id or object_id or "main").strip() or "main"
        if members_of is not None:
            members = recursive_zone_leaf_ids(parent, pipeline, members_of)
        elif parent == "main" and main_step_ids is not None:
            members = set(main_level_non_zone_ids(pipeline, main_step_ids))
        else:
            # fallback: tous non-zone si pas de members_of
            members = {
                sid
                for sid, cfg in pipeline.items()
                if isinstance(cfg, dict)
                and str(cfg.get("type") or "") not in skip_types
            }
    else:
        oid = str(object_id or "").strip()
        if not oid or oid not in pipeline:
            return {}
        if k == "backzone":
            members = recursive_requires(oid, pipeline)
        elif k == "forzone":
            members = recursive_dependents(oid, pipeline)
        elif k == "bidzone":
            members = recursive_requires(oid, pipeline) | recursive_dependents(
                oid, pipeline
            )
        else:
            return {}

    out: dict[str, Any] = {}
    for sid in sorted(members):
        cfg = pipeline.get(sid)
        if not isinstance(cfg, dict):
            continue
        t = str(cfg.get("type") or "")
        if t == "zone" or is_auto_zone_type(t):
            continue
        out[sid] = {}
    return out


class AutoZoneStep(OrgStep):
    """
    Legacy: vue logique (F0128). F0139 cree des ZoneStep a la place.

    Conserve pour charger d anciens YAML allzone/backzone/...
    """

    type: ClassVar[str] = "allzone"
    KIND: ClassVar[str] = "allzone"
    ALLOWED_CONFIG_KEYS: ClassVar[frozenset[str] | None] = frozenset(
        {"type", "label", "object", "parent"}
    )

    def __init__(
        self,
        step_id: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(step_id, config)
        self.config["type"] = self.type
        if not self.label:
            self.label = step_id
            self.config["label"] = step_id
        raw_obj = self.config.get("object") or self.config.get("parent")
        self.object_id: str | None = (
            str(raw_obj).strip()
            if raw_obj is not None and str(raw_obj).strip()
            else None
        )
        if self.object_id:
            self.config["object"] = self.object_id

    def build_action(self) -> str:
        return "zone_build"

    def is_auto_zone(self) -> bool:
        return True

    def to_config(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "type": self.type,
            "label": self.label or self.id,
        }
        if self.object_id:
            out["object"] = self.object_id
        return out

    @classmethod
    def tool_meta(cls) -> dict[str, Any]:
        return {
            "id": "flatzone",
            "label": "Flat zone",
            "type": "flatzone",
            "description": (
                "Cree une zone (type zone) initialisee avec tous les "
                "composants feuille d une zone parent (recursif)."
            ),
            "icon": "zone",
            "fields": ["name", "parent"],
            "region": "auto",
        }


class FlatZoneStep(AutoZoneStep):
    type: ClassVar[str] = "flatzone"
    KIND: ClassVar[str] = "flatzone"

    @classmethod
    def tool_meta(cls) -> dict[str, Any]:
        return AutoZoneStep.tool_meta()


class AllZoneStep(AutoZoneStep):
    """Legacy id allzone — meme template que flatzone."""

    type: ClassVar[str] = "allzone"
    KIND: ClassVar[str] = "allzone"


class BackZoneStep(AutoZoneStep):
    type: ClassVar[str] = "backzone"
    KIND: ClassVar[str] = "backzone"

    @classmethod
    def tool_meta(cls) -> dict[str, Any]:
        return {
            "id": "backzone",
            "label": "Back zone",
            "type": "backzone",
            "description": (
                "Cree une zone initialisee avec le lineage requires "
                "(amont) du composant selectionne."
            ),
            "icon": "zone",
            "fields": ["name", "object"],
            "region": "auto",
        }


class ForZoneStep(AutoZoneStep):
    type: ClassVar[str] = "forzone"
    KIND: ClassVar[str] = "forzone"

    @classmethod
    def tool_meta(cls) -> dict[str, Any]:
        return {
            "id": "forzone",
            "label": "For zone",
            "type": "forzone",
            "description": (
                "Cree une zone initialisee avec le lineage required_by "
                "(aval) du composant selectionne."
            ),
            "icon": "zone",
            "fields": ["name", "object"],
            "region": "auto",
        }


class BidZoneStep(AutoZoneStep):
    type: ClassVar[str] = "bidzone"
    KIND: ClassVar[str] = "bidzone"

    @classmethod
    def tool_meta(cls) -> dict[str, Any]:
        return {
            "id": "bidzone",
            "label": "Bid zone",
            "type": "bidzone",
            "description": (
                "Cree une zone initialisee avec le lineage bidirectionnel "
                "du composant selectionne."
            ),
            "icon": "zone",
            "fields": ["name", "object"],
            "region": "auto",
        }


# re-export ZoneStep for type checkers / docs "herite de zone"
__all__ = [
    "AUTO_ZONE_TYPES",
    "AUTO_TAB",
    "is_auto_zone_type",
    "normalize_auto_kind",
    "auto_zone_id_for",
    "compute_auto_zone_members",
    "recursive_zone_leaf_ids",
    "recursive_requires",
    "recursive_dependents",
    "AutoZoneStep",
    "FlatZoneStep",
    "AllZoneStep",
    "BackZoneStep",
    "ForZoneStep",
    "BidZoneStep",
    "ZoneStep",
]
