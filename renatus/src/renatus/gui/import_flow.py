"""
Import de flux YAML (fichier ou dossier) dans une zone cible (F0102 / F0103).

Regles:
- 1 composant Renatus = 1 fichier <id>.yaml (split des multi-cles)
- id = shortname (stem) — F0101
- Conflit avec l existant: keep_both | keep_existing | replace (choix user)
- Conflit entre fichiers d import: prefixe = stem du fichier source
  (ex. bundle.yaml + t1 → bundle_t1 si t1 deja pris dans le batch)
- Sinon id = cle YAML (ou label normalise si plus stable)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml

from renatus.gui.yaml_store import YamlStepStore
from renatus.pipeline.steps.base import normalize_script_key
from renatus.pipeline.steps.factory import normalize_step_type

ConflictPolicy = Literal["keep_both", "keep_existing", "replace"]
CONFLICT_POLICIES = frozenset({"keep_both", "keep_existing", "replace"})


def _is_yaml(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in {".yaml", ".yml"}


def _safe_id_fragment(raw: str) -> str:
    """Normalise une chaine en fragment d id (stem-safe)."""
    s = str(raw or "").strip().replace("\\", "/").replace(" ", "_")
    if "/" in s:
        s = s.rsplit("/", 1)[-1]
    low = s.lower()
    if low.endswith(".yaml"):
        s = s[:-5]
    elif low.endswith(".yml"):
        s = s[:-4]
    # caracteres autorises proche validate_tab_segment
    allowed = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    )
    out = "".join(c if c in allowed else "_" for c in s)
    out = out.strip("_") or "obj"
    return YamlStepStore.normalize_step_id(out)


def _preferred_object_id(key: str, config: dict[str, Any]) -> str:
    """
    Id propose pour un objet declare dans un YAML.
    Prefere la cle YAML; sinon label.
    """
    try:
        return YamlStepStore.normalize_step_id(str(key))
    except ValueError:
        pass
    lab = config.get("label")
    if lab is not None and str(lab).strip():
        try:
            return _safe_id_fragment(str(lab))
        except ValueError:
            pass
    return _safe_id_fragment(str(key) or "obj")


def _load_yaml_objects(path: Path) -> list[tuple[str, dict[str, Any]]]:
    """
    F0103: parcourt un fichier YAML et renvoie tous les objets declares
    (1 entree par cle top-level). Multi-cles → split en monocomposants.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict) or not raw:
        raise ValueError(f"YAML vide ou invalide: {path}")
    out: list[tuple[str, dict[str, Any]]] = []
    for key, cfg in raw.items():
        if not isinstance(cfg, dict):
            raise ValueError(
                f"Config invalide pour {key!r} dans {path}"
            )
        # ignore pure metadata non-step (pas de type)
        if "type" not in cfg and not cfg:
            continue
        if "type" not in cfg:
            # legacy fragment: refuse
            raise ValueError(
                f"Objet {key!r} sans type dans {path}"
            )
        pref = _preferred_object_id(str(key), cfg)
        out.append((pref, dict(cfg)))
    if not out:
        raise ValueError(f"Aucun composant dans {path}")
    return out


def _join_tab(base: str, *parts: str) -> str:
    segs: list[str] = []
    b = (base or YamlStepStore.ROOT_TAB).strip().replace("\\", "/")
    if b and b not in {YamlStepStore.ROOT_TAB, "*", "_all"}:
        segs.extend([p for p in b.split("/") if p])
    for part in parts:
        for s in str(part).replace("\\", "/").split("/"):
            if s and s not in {".", ".."}:
                segs.append(s)
    return "/".join(segs) if segs else YamlStepStore.ROOT_TAB


def _normalize_cfg(step_id: str, config: dict[str, Any]) -> dict[str, Any]:
    cfg = normalize_script_key(dict(config))
    if "type" in cfg:
        cfg["type"] = normalize_step_type(cfg.get("type"))
    cfg = YamlStepStore.normalize_step_config(step_id, cfg)
    return cfg


def _import_companions(
    store: YamlStepStore,
    *,
    source_yaml: Path | None,
    dest_yaml: Path,
    final_id: str,
    step_type: str,
    cfg: dict[str, Any],
) -> list[str]:
    """
    F0146: copie les fichiers du meme stem (hors yaml) depuis le dossier source.

    Si le stem source differe de final_id, renomme en final_id.<ext>.
    """
    from renatus.pipeline.steps.source_files import (
        SIDECAR_TYPES,
        companion_files,
        script_from_sidecar_path,
        write_sidecar_content,
    )

    copied: list[str] = []
    if source_yaml is None or not source_yaml.is_file():
        # creer sidecar defaut pour python/notebook si absent
        if step_type in SIDECAR_TYPES:
            side = store.sidecar_path_for(
                final_id, step_type=step_type, yaml_path=dest_yaml
            )
            if side is not None and not side.exists():
                write_sidecar_content(
                    side,
                    step_type=step_type,
                    script=str(cfg.get("script") or ""),
                )
                copied.append(side.name)
        return copied

    src_parent = source_yaml.parent
    src_stem = source_yaml.stem
    dest_parent = Path(dest_yaml).parent
    dest_parent.mkdir(parents=True, exist_ok=True)

    for companion in companion_files(source_yaml):
        # renomme vers final_id si id change (conflit rename)
        dest_name = companion.name
        if companion.stem == src_stem and src_stem != final_id:
            dest_name = final_id + companion.suffix
        dest = dest_parent / dest_name
        if dest.exists() or dest.is_symlink():
            continue
        try:
            # copie reelle a l import (pas symlink vers source hors projet)
            data = companion.read_bytes()
            dest.write_bytes(data)
            copied.append(dest.name)
        except OSError:
            continue

    # si type sidecar et pas de fichier source, generer depuis script yaml
    if step_type in SIDECAR_TYPES:
        side = store.sidecar_path_for(
            final_id, step_type=step_type, yaml_path=dest_yaml
        )
        if side is not None and not side.exists():
            # peut-etre deja copie sous autre nom
            script = str(cfg.get("script") or "")
            # tente de lire un compagnon deja copie
            for c in companion_files(dest_yaml):
                if c.suffix.lower() in {".py", ".ipynb"}:
                    script = script_from_sidecar_path(c) or script
                    break
            if not any(
                c.suffix.lower() in {".py", ".ipynb"}
                for c in companion_files(dest_yaml)
            ):
                write_sidecar_content(
                    side, step_type=step_type, script=script
                )
                copied.append(side.name)
    return copied


def _remap_refs(config: dict[str, Any], id_map: dict[str, str]) -> dict[str, Any]:
    """Remappe requires / objects / iterate selon le plan d import."""
    out = dict(config)
    reqs = out.get("requires")
    if isinstance(reqs, list):
        out["requires"] = [
            id_map.get(str(r), str(r)) for r in reqs if r is not None
        ]
    objects = out.get("objects")
    if isinstance(objects, dict):
        new_o: dict[str, Any] = {}
        for k, v in objects.items():
            nk = id_map.get(str(k), str(k))
            new_o[nk] = v if isinstance(v, dict) else {}
        out["objects"] = new_o
    elif isinstance(objects, list):
        out["objects"] = [
            id_map.get(str(x), str(x)) for x in objects if x is not None
        ]
    for fld in ("target", "scenarios", "step_view"):
        if fld in out and out[fld] is not None:
            val = str(out[fld]).strip()
            if val in id_map:
                out[fld] = id_map[val]
    return out


def _next_free(base: str, taken: set[str], batch_used: set[str]) -> str:
    """Premier id libre base, base_2, base_3..."""
    if base not in taken and base not in batch_used:
        return base
    i = 2
    while True:
        cand = f"{base}_{i}"
        if cand not in taken and cand not in batch_used:
            return cand
        i += 1
        if i > 100000:
            raise ValueError(f"Impossible de generer un id unique pour {base}")


def _claim_id(
    preferred: str,
    *,
    taken: set[str],
    batch_used: set[str],
    file_stem: str,
    multi_file_batch: bool,
    policy: ConflictPolicy,
) -> tuple[str | None, str]:
    """
    Reserve un id unique.

    Retourne (final_id|None, action) action in import|rename|replace|skip.
    - Conflit batch: prefixe stem fichier source
    - Conflit existant: politique user (keep_both / keep_existing / replace)
    """
    base = _safe_id_fragment(preferred)

    def free(name: str) -> bool:
        return name not in taken and name not in batch_used

    def take(name: str) -> None:
        batch_used.add(name)
        taken.add(name)

    # libre globalement
    if free(base):
        take(base)
        return base, "import"

    # Conflit avec un autre objet du meme import → prefixe fichier source
    if base in batch_used:
        prefixed = _safe_id_fragment(f"{file_stem}_{base}")
        nid = _next_free(prefixed, taken, batch_used)
        take(nid)
        return nid, "rename"

    # Conflit avec l existant du projet
    if base in taken:
        if policy == "keep_existing":
            return None, "skip"
        if policy == "replace":
            take(base)
            return base, "replace"
        # keep_both: renommer l import
        if multi_file_batch:
            seed = _safe_id_fragment(f"{file_stem}_{base}")
        else:
            seed = base
        nid = _next_free(seed, taken, batch_used)
        # si seed==base et base pris, _next_free donne base_2
        take(nid)
        return nid, "rename"

    take(base)
    return base, "import"


def collect_import_plan(
    source: Path,
    *,
    target_tab: str,
    existing_ids: set[str],
    conflict: ConflictPolicy,
) -> dict[str, Any]:
    """
    Construit le plan d import sans ecrire.

    Chaque objet declare dans chaque YAML devient un item monocomposant.
    """
    source = source.expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Source introuvable: {source}")
    if conflict not in CONFLICT_POLICIES:
        raise ValueError(
            f"conflict invalide: {conflict!r} "
            f"(keep_both|keep_existing|replace)"
        )

    # Liste des fichiers YAML a parcourir
    yaml_files: list[tuple[Path, str]] = []
    # path, rel_tab_suffix (dossiers sous la zone cible)

    if source.is_file():
        if not _is_yaml(source):
            raise ValueError(f"Fichier non YAML: {source}")
        yaml_files.append((source, ""))
        root_label = source.stem
        multi_file_batch = False
    elif source.is_dir():
        root_label = source.name
        found = sorted(
            {
                *source.rglob("*.yaml"),
                *source.rglob("*.yml"),
            }
        )
        for yf in found:
            if not yf.is_file():
                continue
            rel = yf.relative_to(source)
            parent_parts = (root_label,) + rel.parts[:-1]
            rel_suffix = "/".join(p for p in parent_parts if p)
            yaml_files.append((yf, rel_suffix))
        multi_file_batch = len(yaml_files) > 1
    else:
        raise ValueError(f"Source ni fichier ni dossier: {source}")

    if not yaml_files:
        raise ValueError(f"Aucun fichier YAML dans {source}")

    # Expand: chaque fichier → N objets
    raw_objects: list[dict[str, Any]] = []
    # {source_path, file_stem, rel_suffix, preferred_id, config, key_index}
    for yf, rel_suffix in yaml_files:
        file_stem = _safe_id_fragment(yf.stem)
        try:
            objects = _load_yaml_objects(yf)
        except Exception as exc:
            raise ValueError(f"Lecture {yf}: {exc}") from exc
        multi_in_file = len(objects) > 1
        for idx, (pref_id, cfg) in enumerate(objects):
            # multi-objets dans un seul fichier: si collision interne, prefix stem
            raw_objects.append(
                {
                    "source": str(yf),
                    "file_stem": file_stem,
                    "rel_suffix": rel_suffix,
                    "preferred_id": pref_id,
                    "config": cfg,
                    "key_index": idx,
                    "multi_in_file": multi_in_file,
                    "multi_file_batch": multi_file_batch or multi_in_file,
                }
            )

    taken = set(existing_ids)
    batch_used: set[str] = set()
    id_map: dict[str, str] = {}  # preferred/orig → final (global, last wins)
    id_map_by_source: dict[str, dict[str, str]] = {}  # source → {orig: final}
    items: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    zone_tabs: set[str] = set()

    for obj in raw_objects:
        pref = str(obj["preferred_id"])
        file_stem = str(obj["file_stem"])
        src_path = str(obj["source"])
        # Preferer prefixe fichier si multi-objets dans le fichier et id deja
        # vu dans le batch (split multi-cles)
        candidate = pref
        if obj["multi_in_file"] and pref in batch_used:
            candidate = _safe_id_fragment(f"{file_stem}_{pref}")

        final, action = _claim_id(
            candidate,
            taken=taken,
            batch_used=batch_used,
            file_stem=file_stem,
            multi_file_batch=bool(obj["multi_file_batch"]),
            policy=conflict,
        )
        if final is None:
            conflicts.append(
                {
                    "source": src_path,
                    "id": pref,
                    "action": "skip",
                    "reason": "keep_existing",
                }
            )
            continue

        if action != "import":
            conflicts.append(
                {
                    "source": src_path,
                    "id": pref,
                    "final_id": final,
                    "action": action,
                }
            )

        id_map[pref] = final
        if candidate != pref:
            id_map[candidate] = final
        id_map_by_source.setdefault(src_path, {})[pref] = final

        rel_suffix = str(obj["rel_suffix"] or "")
        dest_tab = (
            _join_tab(target_tab, rel_suffix)
            if rel_suffix
            else (target_tab or YamlStepStore.ROOT_TAB)
        )
        if dest_tab and dest_tab != YamlStepStore.ROOT_TAB:
            parts = dest_tab.split("/")
            for i in range(len(parts)):
                zone_tabs.add("/".join(parts[: i + 1]))

        items.append(
            {
                "source": src_path,
                "orig_id": pref,
                "final_id": final,
                "dest_tab": dest_tab,
                "config": obj["config"],
                "type": str((obj["config"] or {}).get("type") or ""),
                "file_stem": file_stem,
            }
        )

    return {
        "ok": True,
        "source": str(source),
        "source_kind": "file" if source.is_file() else "directory",
        "root_label": root_label,
        "target_tab": target_tab or YamlStepStore.ROOT_TAB,
        "conflict": conflict,
        "items": items,
        "id_map": id_map,
        "id_map_by_source": id_map_by_source,
        "conflicts": conflicts,
        "zone_tabs": sorted(zone_tabs),
        "count": len(items),
        "split_objects": len(raw_objects),
    }


def apply_import_plan(
    store: YamlStepStore,
    pipeline: dict[str, dict[str, Any]],
    plan: dict[str, Any],
    *,
    ensure_zone_fn: Any,
) -> dict[str, Any]:
    """
    Applique le plan: 1 fichier monocomposant par item, zones creees.
    """
    id_map: dict[str, str] = dict(plan.get("id_map") or {})
    id_map_by_source: dict[str, dict[str, str]] = dict(
        plan.get("id_map_by_source") or {}
    )
    imported: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    zones_created: list[str] = []

    for ztab in plan.get("zone_tabs") or []:
        if ensure_zone_fn(ztab):
            zones_created.append(ztab)

    for item in plan.get("items") or []:
        final_id = str(item["final_id"])
        dest_tab = str(item.get("dest_tab") or YamlStepStore.ROOT_TAB)
        src = str(item.get("source") or "")
        # remap: carte locale au fichier d abord (split multi-cles), puis global
        local = dict(id_map_by_source.get(src) or {})
        merged_map = {**id_map, **local}
        cfg = _remap_refs(dict(item["config"]), merged_map)
        cfg = _normalize_cfg(final_id, cfg)
        step_type = str(cfg.get("type") or "")
        path = store.save_step(final_id, cfg, tab=dest_tab)
        pipeline[final_id] = cfg
        # F0146: copier les fichiers compagnons (meme stem) du dossier source
        try:
            _import_companions(
                store,
                source_yaml=Path(src) if src else None,
                dest_yaml=path,
                final_id=final_id,
                step_type=step_type,
                cfg=cfg,
            )
        except Exception:
            pass
        # rattacher a la zone parente (objects)
        parent_zone_id = (
            dest_tab.split("/")[-1]
            if dest_tab and dest_tab != YamlStepStore.ROOT_TAB
            else YamlStepStore.ROOT_TAB
        )
        if parent_zone_id in pipeline:
            pz = pipeline[parent_zone_id]
            if isinstance(pz, dict) and str(pz.get("type")) == "zone":
                objects = pz.get("objects")
                if not isinstance(objects, dict):
                    objects = {}
                else:
                    objects = dict(objects)
                if final_id not in objects and final_id != parent_zone_id:
                    objects[final_id] = {}
                    pz = dict(pz)
                    pz["objects"] = objects
                    pipeline[parent_zone_id] = pz
                    try:
                        store.save_step(
                            parent_zone_id,
                            pz,
                            tab=store.tab_of(parent_zone_id),
                        )
                    except Exception:
                        pass
        imported.append(
            {
                "id": final_id,
                "orig_id": item["orig_id"],
                "tab": dest_tab,
                "path": str(path),
                "type": step_type,
                "source": item.get("source"),
            }
        )

    for c in plan.get("conflicts") or []:
        if c.get("action") == "skip":
            skipped.append(c)

    return {
        "ok": True,
        "imported": imported,
        "skipped": skipped,
        "zones_created": zones_created,
        "id_map": id_map,
        "count": len(imported),
        "message": (
            f"Import: {len(imported)} composant(s) "
            f"(1 fichier chacun), "
            f"{len(skipped)} ignore(s), "
            f"{len(zones_created)} zone(s) creee(s)"
        ),
    }
