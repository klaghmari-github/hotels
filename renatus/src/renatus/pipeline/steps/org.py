"""
OrgStep — composants organisationnels (zone = dossier UI).
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Step

# F0116: modes Renatus d une zone
RENATUS_MODE_LEAVES = "required_for_leaves"
RENATUS_MODE_ROOT = "root_to_leaves"
RENATUS_MODES = frozenset({RENATUS_MODE_LEAVES, RENATUS_MODE_ROOT})
WORKERS_AUTO = "auto"
WORKERS_QUEUE = "queue"


def normalize_zone_workers(raw: Any) -> str:
    """
    workers: 'auto' | 'queue' | entier >= 2 (max lignes // workers).

    auto = une ligne de flux independante = un worker (parallel logique).
    queue = une seule file sequentielle.
    """
    if raw is None or raw == "":
        return WORKERS_AUTO
    if isinstance(raw, (int, float)):
        n = int(raw)
        if n <= 1:
            return WORKERS_QUEUE
        return str(n)
    s = str(raw).strip().lower()
    if s in ("", "auto", "parallel", "*"):
        return WORKERS_AUTO
    if s in ("queue", "serial", "seq", "1", "sequential"):
        return WORKERS_QUEUE
    try:
        n = int(s)
        if n <= 1:
            return WORKERS_QUEUE
        return str(n)
    except ValueError:
        return WORKERS_AUTO


def normalize_renatus_mode(raw: Any) -> str:
    """renatus_mode: required_for_leaves | root_to_leaves."""
    if raw is None or raw == "":
        return RENATUS_MODE_LEAVES
    s = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "required_for_leaves": RENATUS_MODE_LEAVES,
        "requiredforleaves": RENATUS_MODE_LEAVES,
        "leaves": RENATUS_MODE_LEAVES,
        "leaf": RENATUS_MODE_LEAVES,
        "root_to_leaves": RENATUS_MODE_ROOT,
        "roottoleaves": RENATUS_MODE_ROOT,
        "root_to_leaf": RENATUS_MODE_ROOT,
        "pipeline": RENATUS_MODE_ROOT,
        "full": RENATUS_MODE_ROOT,
    }
    if s in aliases:
        return aliases[s]
    if s in RENATUS_MODES:
        return s
    return RENATUS_MODE_LEAVES


class OrgStep(Step):
    """Step purement structurelle (pas d'execution moteur)."""

    def should_process(self, pipeline_obj: Any) -> bool:
        return False

    def relation_name(self) -> str | None:
        return None

    def process(self, pipeline_obj: Any) -> None:
        # no-op par defaut
        return None


class ZoneStep(OrgStep):
    """
    Zone organisationnelle (F0052 / F0056 / F0116).

    process no-op. Membership via config['objects'] :
    dict { object_id: meta } — l id (cle) est immutable et unique
    dans le projet ; le meme id peut figurer dans plusieurs zones.

    F0116:
    - workers: auto | queue | N — parallelisation des lignes de flux
    - renatus_mode: required_for_leaves | root_to_leaves

    A0011: pas de file / script / mode create_* / name / requires / venv…
    """

    type: ClassVar[str] = "zone"
    ALLOWED_CONFIG_KEYS: ClassVar[frozenset[str] | None] = frozenset(
        {"type", "label", "objects", "workers", "renatus_mode"}
    )

    def __init__(
        self,
        step_id: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(step_id, config)
        self.objects: dict[str, Any] = normalize_zone_objects(
            self.config.get("objects")
        )
        # Toujours normaliser dans config pour serialisation stable
        self.config["objects"] = dict(self.objects)
        self.workers: str = normalize_zone_workers(self.config.get("workers"))
        self.renatus_mode: str = normalize_renatus_mode(
            self.config.get("renatus_mode")
        )
        self.config["workers"] = self.workers
        self.config["renatus_mode"] = self.renatus_mode

    def should_process(self, pipeline_obj: Any) -> bool:
        return False

    def process(self, pipeline_obj: Any) -> None:
        return None

    def build_action(self) -> str:
        # F0058/F0116: Build zone = build des membres selon renatus_mode
        return "zone_build"

    def object_ids(self) -> list[str]:
        """Ids des objets membres de la zone (ordre stable)."""
        return sorted(self.objects.keys())

    def validate(self, pipeline_keys: set[str] | frozenset[str]) -> None:
        """Zone: pas de requires; objects optionnels (ids connus si presents)."""
        for oid in self.objects:
            if not str(oid).strip():
                raise ValueError(
                    f"Zone {self.id}: cle objects vide invalide"
                )
        if self.renatus_mode not in RENATUS_MODES:
            raise ValueError(
                f"Zone {self.id}: renatus_mode invalide "
                f"(attendu: {', '.join(sorted(RENATUS_MODES))})"
            )

    def to_config(self) -> dict[str, Any]:
        out = super().to_config()
        out["type"] = self.type
        out["objects"] = dict(self.objects)
        out["workers"] = self.workers
        out["renatus_mode"] = self.renatus_mode
        # zones n ont pas de requires
        out.pop("requires", None)
        return out

    @classmethod
    def tool_meta(cls) -> dict[str, Any]:
        return {
            "id": "zone",
            "label": "Zone",
            "type": "zone",
            "description": (
                "Composant organisationnel. "
                "objects = dictionnaire d ids de composants. "
                "workers (auto|queue|N): parallelisation des lignes de flux. "
                "renatus_mode (required_for_leaves|root_to_leaves): "
                "strategie de build par ligne."
            ),
            "icon": "zone",
            "fields": [
                "name",
                "label",
                "objects",
                "workers",
                "renatus_mode",
            ],
            "region": "flow",
        }


def normalize_zone_objects(raw: Any) -> dict[str, Any]:
    """
    Normalise objects vers dict {id: meta}.

    Accepte:
    - None / {} / []
    - list d ids: ["a", "b"] → {"a": {}, "b": {}}
    - dict: {"a": {}, "b": null} → {"a": {}, "b": {}}
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        out: dict[str, Any] = {}
        for key, val in raw.items():
            kid = str(key).strip()
            if not kid:
                continue
            if val is None:
                out[kid] = {}
            elif isinstance(val, dict):
                out[kid] = dict(val)
            else:
                out[kid] = {"value": val}
        return out
    if isinstance(raw, (list, tuple, set)):
        out = {}
        for item in raw:
            if item is None:
                continue
            if isinstance(item, dict):
                # [{id: x}, ...] ou {id: meta}
                oid = item.get("id") or item.get("name")
                if oid:
                    out[str(oid).strip()] = {
                        k: v
                        for k, v in item.items()
                        if k not in {"id", "name"}
                    }
                continue
            kid = str(item).strip()
            if kid:
                out[kid] = {}
        return out
    raise ValueError(
        "objects de zone doit etre un dict {id: meta} ou une liste d ids"
    )
