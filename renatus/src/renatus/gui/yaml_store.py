"""
YamlStepStore — persistence monocomposant + onglets/zones.

F0031: un composant = fichiers <id>.yaml
F0060 / F0145: multi-presence = un seul fichier physique + symlinks
<id>.yaml (meme nom/id) sous chaque zone qui l utilise.
Dossier zone partage = symlink de dossier du meme nom.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


class YamlStepStore:
    """
    Index step -> liste de chemins YAML (presence multi-zones F0060/F0145).

    Onglets / zones :
    - tab "default" = flow/default/*.yaml (F0082 / F0144, zone racine protegee)
    - legacy "main" migre vers "default" a l ouverture
    - sous-zones : flow/default/<zone>/… (hierarchie)
    - Presence dans une zone = fichier <id>.yaml (reel ou symlink) dans ce dossier
    - Partage = symlink relatif vers l unique fichier physique (meme nom = meme id)

    F0101: id composant = shortname du fichier YAML
    (stem: sans dossiers parents, sans extension .yaml/.yml).
    """

    ROOT_TAB = "default"
    # F0144: ancien nom de la zone racine (migration)
    LEGACY_ROOT_TAB = "main"
    # F0128: dossier definitions auto-zones (vues logiques)
    AUTO_TAB = "auto"
    # F0104: zone calculee — tous les composants (hors type zone)
    ALL_TAB = "all"

    @staticmethod
    def normalize_step_id(raw: str | None) -> str:
        """
        F0101: id = shortname fichier YAML.

        - retire chemins parents (a/b/c → c)
        - retire extension .yaml / .yml
        - refuse id vide ou contenant encore des separateurs
        """
        s = str(raw or "").strip().replace("\\", "/")
        if not s:
            raise ValueError("id de step vide")
        # dernier segment seulement (pas de prefixe dossier)
        if "/" in s:
            s = s.rsplit("/", 1)[-1]
        low = s.lower()
        if low.endswith(".yaml"):
            s = s[:-5]
        elif low.endswith(".yml"):
            s = s[:-4]
        s = s.strip()
        if not s or s in {".", ".."}:
            raise ValueError(f"id de step invalide: {raw!r}")
        if "/" in s or "\\" in s:
            raise ValueError(
                f"id de step ne doit pas contenir de chemin: {raw!r}"
            )
        return s

    @staticmethod
    def step_id_from_yaml_path(path: Path) -> str:
        """Id canonique depuis un chemin fichier YAML (stem normalise)."""
        return YamlStepStore.normalize_step_id(Path(path).stem)

    def __init__(
        self,
        pipeline_path: str | Path,
        *,
        ensure_main: bool = True,
        ensure_default: bool | None = None,
    ) -> None:
        self.pipeline_path = Path(pipeline_path).expanduser().resolve()
        # F0060: plusieurs chemins par id (copies)
        self._origins: dict[str, list[Path]] = {}
        self.active_tab: str = self.ROOT_TAB
        # ensure_main: alias historique de ensure_default (F0144)
        do_ensure = ensure_default if ensure_default is not None else ensure_main
        if do_ensure:
            try:
                self.ensure_default_zone()
            except OSError:
                pass
        self.refresh()

    def ensure_main_zone(self) -> Path:
        """Alias F0082 → ensure_default_zone (F0144)."""
        return self.ensure_default_zone()

    def ensure_default_zone(self) -> Path:
        """
        F0082 / F0144: assure flow/default/ + default.yaml (zone racine).

        - migre legacy main → default (dossier + yaml + cle YAML)
        - cree default/ + default.yaml si manquants
        - migre les steps a la racine flow/ vers flow/default/
        - migre les zones top-level (zid.yaml + zid/) sous flow/default/
        """
        path = self.pipeline_path
        if path.is_file() or not path.exists():
            if not path.exists() and path.suffix == "":
                path.mkdir(parents=True, exist_ok=True)
            else:
                return path
        if not path.is_dir():
            return path

        # --- F0144: migration main → default ---
        legacy = self.LEGACY_ROOT_TAB
        root = self.ROOT_TAB
        leg_dir = path / legacy
        leg_yaml = path / f"{legacy}.yaml"
        def_dir = path / root
        def_yaml = path / f"{root}.yaml"

        if leg_dir.is_dir() and not def_dir.exists():
            try:
                leg_dir.rename(def_dir)
            except OSError:
                pass
        if leg_yaml.is_file() and not def_yaml.is_file():
            try:
                # renomme le fichier + cle YAML interne
                raw = yaml.safe_load(leg_yaml.read_text(encoding="utf-8")) or {}
                if isinstance(raw, dict) and legacy in raw and root not in raw:
                    raw[root] = raw.pop(legacy)
                    if isinstance(raw[root], dict):
                        raw[root]["type"] = "zone"
                        lab = str(raw[root].get("label") or "").strip()
                        if not lab or lab == legacy:
                            raw[root]["label"] = root
                leg_yaml.write_text(
                    yaml.dump(
                        raw,
                        default_flow_style=False,
                        allow_unicode=True,
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )
                leg_yaml.rename(def_yaml)
            except OSError:
                pass
        # si les deux existent encore: fusion douce — garde default, ignore main
        # (contenu deja sous default apres rename partiel)

        def_dir = path / root
        def_dir.mkdir(parents=True, exist_ok=True)

        # Migrer steps a la racine (hors definitions de zone top-level)
        for p in sorted(path.glob("*.yaml")) + sorted(path.glob("*.yml")):
            if p.name in {
                f"{root}.yaml",
                f"{root}.yml",
                f"{legacy}.yaml",
                f"{legacy}.yml",
            }:
                continue
            stem = p.stem
            if (path / stem).is_dir():
                # zone top-level → deplacer sous default/
                dest_yaml = def_dir / p.name
                dest_folder = def_dir / stem
                try:
                    if not dest_yaml.exists():
                        p.rename(dest_yaml)
                    if (path / stem).is_dir() and not dest_folder.exists():
                        (path / stem).rename(dest_folder)
                except OSError:
                    pass
                continue
            dest = def_dir / p.name
            if dest.exists():
                continue
            try:
                p.rename(dest)
            except OSError:
                pass

        # Dossiers orphelins a la racine (zones sans yaml deja deplace)
        for d in sorted(path.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            if d.name in {root, legacy, self.AUTO_TAB}:
                continue
            dest_folder = def_dir / d.name
            if dest_folder.exists():
                continue
            try:
                d.rename(dest_folder)
            except OSError:
                pass

        def_yaml = path / f"{root}.yaml"
        if not def_yaml.is_file():
            body = {
                root: {
                    "type": "zone",
                    "label": root,
                    "objects": {},
                    "workers": "auto",
                    "renatus_mode": "required_for_leaves",
                }
            }
            def_yaml.write_text(
                yaml.dump(
                    body,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
        else:
            # assure cle default + type zone
            try:
                raw = yaml.safe_load(def_yaml.read_text(encoding="utf-8")) or {}
                if isinstance(raw, dict):
                    changed = False
                    if legacy in raw and root not in raw:
                        raw[root] = raw.pop(legacy)
                        changed = True
                    if root not in raw:
                        raw[root] = {
                            "type": "zone",
                            "label": root,
                            "objects": {},
                            "workers": "auto",
                            "renatus_mode": "required_for_leaves",
                        }
                        changed = True
                    elif isinstance(raw[root], dict):
                        if str(raw[root].get("type") or "") != "zone":
                            raw[root]["type"] = "zone"
                            changed = True
                        lab = str(raw[root].get("label") or "").strip()
                        if not lab or lab == legacy:
                            raw[root]["label"] = root
                            changed = True
                    if changed:
                        def_yaml.write_text(
                            yaml.dump(
                                raw,
                                default_flow_style=False,
                                allow_unicode=True,
                                sort_keys=False,
                            ),
                            encoding="utf-8",
                        )
            except Exception:
                pass
        return def_dir

    def refresh(self) -> None:
        path = self.pipeline_path
        if path.is_file():
            yaml_files = [path]
        elif path.is_dir():
            yaml_files = sorted(
                [*path.rglob("*.yaml"), *path.rglob("*.yml")]
            )
        else:
            yaml_files = []

        origins: dict[str, list[Path]] = {}
        for yaml_file in yaml_files:
            try:
                if not yaml_file.exists():
                    # symlink casse
                    continue
                content = yaml.safe_load(
                    yaml_file.read_text(encoding="utf-8")
                ) or {}
            except OSError:
                continue
            if not isinstance(content, dict):
                continue
            # F0101: monocomposant <id>.yaml → index par stem ;
            # multi-cles / residu legacy → index par cle normalisee
            keys = [str(k) for k in content.keys()]
            if len(keys) == 1:
                try:
                    stem = self.step_id_from_yaml_path(yaml_file)
                except ValueError:
                    stem = self.normalize_step_id(keys[0])
                if yaml_file.name in {f"{stem}.yaml", f"{stem}.yml"}:
                    origins.setdefault(stem, []).append(yaml_file)
                else:
                    try:
                        sid = self.normalize_step_id(keys[0])
                    except ValueError:
                        sid = stem
                    origins.setdefault(sid, []).append(yaml_file)
                continue
            for name in keys:
                try:
                    sid = self.normalize_step_id(name)
                except ValueError:
                    continue
                origins.setdefault(sid, []).append(yaml_file)
        # F0145: garder chaque presence path (reel + symlink), pas dedupe resolve
        for name, paths in list(origins.items()):
            uniq: list[Path] = []
            seen: set[str] = set()
            for p in sorted(
                paths,
                key=lambda x: (
                    0 if self.tab_of_path(x) == self.ROOT_TAB else 1,
                    0 if not x.is_symlink() else 1,
                    len(x.parts),
                    str(x),
                ),
            ):
                key = str(p)
                if key in seen:
                    continue
                seen.add(key)
                uniq.append(p)
            origins[name] = uniq
        self._origins = origins

    def origins_of(self, name: str) -> list[Path]:
        """Toutes les presences disque de l objet (F0060/F0145)."""
        return list(self._origins.get(str(name), []))

    def origin_of(self, name: str) -> Path | None:
        """
        Presence primaire (fichier physique prefere, puis default / chemin court).
        """
        paths = self.origins_of(name)
        if not paths:
            return None
        # preferer fichier reel (pas symlink)
        real = [p for p in paths if not p.is_symlink()]
        candidates = real or paths
        for p in candidates:
            if self.tab_of_path(p) == self.ROOT_TAB:
                return p
        return sorted(
            candidates, key=lambda x: (len(x.parts), str(x))
        )[0]

    def canonical_path_of(self, name: str) -> Path | None:
        """Fichier physique resolu (unique) pour l id, si present."""
        primary = self.origin_of(name)
        if primary is None:
            return None
        try:
            if primary.exists():
                return primary.resolve()
        except OSError:
            pass
        return primary

    def tabs_of(self, name: str) -> list[str]:
        """Tous les onglets/zones FS ou l objet a une presence."""
        tabs = {self.tab_of_path(p) for p in self.origins_of(name)}
        if not tabs:
            return [self.active_tab or self.ROOT_TAB]
        # default d abord
        ordered = []
        if self.ROOT_TAB in tabs:
            ordered.append(self.ROOT_TAB)
        ordered.extend(sorted(t for t in tabs if t != self.ROOT_TAB))
        return ordered

    def tab_of(self, name: str) -> str:
        """Onglet home (primaire) de la step."""
        origin = self.origin_of(name)
        if origin is None:
            return self.normalize_tab_id(self.active_tab or self.ROOT_TAB)
        return self.tab_of_path(origin)

    def normalize_tab_id(self, tab: str | None = None) -> str:
        """
        F0144: canonise un id d onglet sous la zone racine default/.

        - main / legacy → default
        - all / auto / * → vues speciales inchangees
        - default ou default/... → inchange
        - etl ou zone_a/sub → default/etl, default/zone_a/sub
        """
        raw = (tab if tab is not None else self.active_tab) or self.ROOT_TAB
        tab_id = str(raw).strip().replace("\\", "/") or self.ROOT_TAB
        if tab_id in {"*", "_all"}:
            return self.ALL_TAB
        if tab_id == self.LEGACY_ROOT_TAB:
            return self.ROOT_TAB
        if tab_id in {self.ROOT_TAB, self.ALL_TAB, self.AUTO_TAB}:
            return tab_id
        if tab_id.startswith(self.LEGACY_ROOT_TAB + "/"):
            tab_id = self.ROOT_TAB + tab_id[len(self.LEGACY_ROOT_TAB) :]
        if tab_id == self.ROOT_TAB or tab_id.startswith(self.ROOT_TAB + "/"):
            return tab_id
        if tab_id.startswith(self.AUTO_TAB + "/"):
            return tab_id
        # Toute zone projet vit sous default/
        return f"{self.ROOT_TAB}/{tab_id}"

    def tab_of_path(self, file_path: Path) -> str:
        """
        Id d onglet = chemin relatif du dossier parent du YAML.

        flow/default/a.yaml        → default   (F0082 / F0144)
        flow/a.yaml                → default   (legacy racine)
        flow/default.yaml          → default   (definition zone default)
        flow/default/etl/b.yaml    → default/etl
        flow/default/etl/sub/c.yaml → default/etl/sub

        F0145: ne pas resolve() le fichier lui-meme (symlink) sinon la
        presence sous zone_a/obj.yaml → ../obj.yaml serait vue dans default.
        On resolve uniquement le dossier parent.
        """
        path = self.pipeline_path
        if path.is_file():
            return self.ROOT_TAB
        fp = Path(file_path)
        try:
            parent_res = fp.parent.resolve()
            root_res = path.resolve()
            rel_parent = parent_res.relative_to(root_res)
        except ValueError:
            return self.ROOT_TAB
        parts = rel_parent.parts
        if not parts:
            # YAML directement sous flow/ (ex. default.yaml)
            return self.ROOT_TAB
        parent = "/".join(parts)
        # flow/default/xxx → onglet default
        if parent == self.ROOT_TAB or parent == self.LEGACY_ROOT_TAB:
            return self.ROOT_TAB
        # legacy flow/main/... → default/...
        if parent == self.LEGACY_ROOT_TAB or parent.startswith(
            self.LEGACY_ROOT_TAB + "/"
        ):
            parent = self.ROOT_TAB + parent[len(self.LEGACY_ROOT_TAB) :]
        return parent

    def dir_for_tab(self, tab: str | None = None) -> Path:
        """Repertoire filesystem correspondant a un onglet / zone."""
        path = self.pipeline_path
        if path.is_file():
            return path.parent
        tab_id = self.normalize_tab_id(tab)
        # F0082 / F0144: default = sous-dossier flow/default/
        if tab_id == self.ROOT_TAB:
            return path / self.ROOT_TAB if path.is_dir() else path.parent
        return path.joinpath(*tab_id.split("/"))

    def zone_folder_for(self, zone_id: str, parent_tab: str | None = None) -> Path:
        """
        Dossier contenu d une zone.

        F0082 / F0144: zone default → flow/default/
        Autres: dir_for_tab(zone_path) pour rester aligne avec create_tab.
        """
        zid = str(zone_id).strip()
        if zid in {self.ROOT_TAB, self.LEGACY_ROOT_TAB}:
            return self.dir_for_tab(self.ROOT_TAB)
        zpath = self.zone_path_for(zid, parent_tab)
        return self.dir_for_tab(zpath)

    def zone_path_for(self, zone_id: str, parent_tab: str | None = None) -> str:
        """
        Id d onglet a ouvrir pour une zone (chemin relatif).

        F0144: sous-zones de la racine vivent sous default/<id>
        (tout le projet sous la zone default).
        """
        zid = str(zone_id).strip()
        if zid in {self.ROOT_TAB, self.LEGACY_ROOT_TAB}:
            return self.ROOT_TAB
        parent = self.normalize_tab_id(parent_tab)
        if parent == self.ROOT_TAB:
            return f"{self.ROOT_TAB}/{zid}"
        return f"{parent}/{zid}"

    def default_path_for(
        self,
        name: str,
        tab: str | None = None,
        *,
        step_type: str | None = None,
    ) -> Path:
        """
        Fichier dedie <id>.yaml (F0031: un composant = un fichier).

        name = id immutable de la step.
        tab peut etre imbrique (etl/sub) ou bare (normalise sous default/).
        F0082 / F0144:
        - zone default.yaml → flow/default.yaml
        - zone enfant depuis default → flow/default/<id>.yaml
        - steps de l onglet default → flow/default/<id>.yaml
        """
        path = self.pipeline_path
        if path.is_file():
            # mode fichier unique legacy: conserve le fichier donne
            return path
        tab_id = self.normalize_tab_id(tab)
        # F0101: fichier = <id>.yaml uniquement (id = shortname)
        safe = self.normalize_step_id(name)
        st = str(step_type or "").strip()
        # definition de la zone protegee default: flow/default.yaml
        if safe in {self.ROOT_TAB, self.LEGACY_ROOT_TAB}:
            return path / f"{self.ROOT_TAB}.yaml"
        # F0131: auto-zones = composants logiques deposes dans default
        from renatus.pipeline.steps.auto_zone import is_auto_zone_type

        if is_auto_zone_type(st):
            root_dir = path / self.ROOT_TAB
            root_dir.mkdir(parents=True, exist_ok=True)
            return root_dir / f"{safe}.yaml"
        # F0144: zones et steps sous default/ (ou tab imbrique)
        if tab_id == self.ROOT_TAB:
            return (path / self.ROOT_TAB) / f"{safe}.yaml"
        return path.joinpath(*tab_id.split("/")) / f"{safe}.yaml"

    @staticmethod
    def normalize_step_config(
        step_id: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Prepare la config a ecrire.

        - id n est pas stocke en double (la cle YAML est l id)
        - label optionnel (defaut = id) pour affichage; modifiable
        - name (relation physique) pour dataframe/table/view:
          defaut = label, independant ensuite (F0048)
        """
        if not isinstance(config, dict):
            raise TypeError("config doit etre un dict")
        if "type" not in config:
            raise ValueError(f"config de {step_id} sans cle 'type'")
        out = dict(config)
        # L id applicatif est la cle du mapping, pas un champ libre
        out.pop("id", None)
        label = out.get("label")
        if label is None or not str(label).strip():
            out["label"] = str(step_id)
        else:
            out["label"] = str(label).strip()
        # F0048: name = entite en base (SQL / register)
        step_type = str(out.get("type") or "")
        if step_type in {"dataframe", "table", "view"}:
            rel = out.get("name")
            if rel is None or not str(rel).strip():
                out["name"] = out["label"]
            else:
                out["name"] = str(rel).strip()
        # F0067: sql legacy → script (SQL ou Python selon le type)
        from renatus.pipeline.steps.base import normalize_script_key
        from renatus.pipeline.steps.factory import normalize_step_type

        out = normalize_script_key(out)
        # F0078: execute → execute_sql
        if "type" in out:
            out["type"] = normalize_step_type(out.get("type"))
        return out

    def _dump_step_file(self, path: Path, step_id: str, clean: dict[str, Any]) -> None:
        # Ecriture via symlink: pathlib ecrit la cible (F0145)
        if not path.is_symlink():
            path.parent.mkdir(parents=True, exist_ok=True)
        content = {step_id: clean}
        dumped = yaml.dump(
            content,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        path.write_text(dumped, encoding="utf-8")

    def sidecar_path_for(
        self,
        step_id: str,
        tab: str | None = None,
        *,
        step_type: str | None = None,
        yaml_path: Path | None = None,
    ) -> Path | None:
        """Chemin <id>.py / <id>.ipynb a cote du YAML (F0146)."""
        from renatus.pipeline.steps.source_files import sidecar_ext_for

        ext = sidecar_ext_for(step_type)
        if not ext:
            return None
        if yaml_path is not None:
            return Path(yaml_path).with_suffix(ext)
        ypath = self.default_path_for(
            step_id, tab=tab, step_type=step_type
        )
        return ypath.with_suffix(ext)

    def write_sidecar_for_step(
        self,
        step_id: str,
        clean: dict[str, Any],
        *,
        yaml_path: Path,
        notebook: dict[str, Any] | None = None,
    ) -> Path | None:
        """Ecrit le fichier source a cote du yaml; retourne le path ou None."""
        from renatus.pipeline.steps.source_files import (
            SIDECAR_TYPES,
            write_sidecar_content,
        )

        st = str(clean.get("type") or "").strip()
        if st not in SIDECAR_TYPES:
            return None
        side = self.sidecar_path_for(
            step_id, step_type=st, yaml_path=yaml_path
        )
        if side is None:
            return None
        # ne pas ecraser un symlink cible (ecrit via le lien)
        script = clean.get("script")
        return write_sidecar_content(
            side,
            step_type=st,
            script=None if script is None else str(script),
            notebook=notebook,
        )

    def read_script_for_step(
        self,
        step_id: str,
        config: dict[str, Any] | None = None,
    ) -> str:
        """
        F0146: code executable — sidecar prioritaire, sinon config.script legacy.
        """
        from renatus.pipeline.steps.source_files import (
            SIDECAR_TYPES,
            script_from_sidecar_path,
        )

        cfg = config if isinstance(config, dict) else {}
        st = str(cfg.get("type") or "").strip()
        origin = self.origin_of(step_id)
        if origin is not None and st in SIDECAR_TYPES:
            side = self.sidecar_path_for(
                step_id, step_type=st, yaml_path=origin
            )
            if side is not None and side.exists():
                text = script_from_sidecar_path(side)
                if text or st == "notebook":
                    return text
        if cfg.get("script") is not None:
            return str(cfg.get("script"))
        return ""

    def symlink_companions(self, master_yaml: Path, dest_yaml: Path) -> list[Path]:
        """
        F0146: symlink tous les fichiers meme stem que master dans dest dir.

        Ex: obj1.yaml + obj1.py → dest/obj1.yaml + dest/obj1.py (liens).
        """
        from renatus.pipeline.steps.source_files import companion_files

        master = Path(master_yaml)
        dest = Path(dest_yaml)
        linked: list[Path] = []
        try:
            master_res = (
                master if not master.is_symlink() else master.resolve()
            )
        except OSError:
            master_res = master
        for companion in companion_files(master_res):
            try:
                src = (
                    companion
                    if not companion.is_symlink()
                    else companion.resolve()
                )
            except OSError:
                src = companion
            dest_c = dest.parent / companion.name
            try:
                if dest_c.resolve() == src.resolve():
                    linked.append(dest_c)
                    continue
            except OSError:
                pass
            try:
                self._relative_symlink(src, dest_c)
                linked.append(dest_c)
            except Exception:
                continue
        return linked

    @staticmethod
    def _relative_symlink(source: Path, dest: Path) -> Path:
        """
        F0145: cree dest comme symlink relatif vers source (meme basename).
        """
        src = Path(source)
        dst = Path(dest)
        try:
            src_res = src.resolve()
        except OSError:
            src_res = src
        if not src_res.exists() and not src.exists():
            raise LookupError(f"Cible symlink introuvable: {source}")

        if dst.exists() or dst.is_symlink():
            try:
                if dst.resolve() == src_res:
                    return dst
            except OSError:
                pass
            # remplace une ancienne copie reelle ou un lien casse
            if dst.is_symlink() or dst.is_file():
                dst.unlink(missing_ok=True)
            elif dst.is_dir():
                try:
                    next(dst.iterdir())
                    raise ValueError(
                        f"Impossible de lier {dst}: dossier reel non vide"
                    )
                except StopIteration:
                    dst.rmdir()

        dst.parent.mkdir(parents=True, exist_ok=True)
        rel = os.path.relpath(str(src_res), start=str(dst.parent.resolve()))
        dst.symlink_to(rel, target_is_directory=src_res.is_dir())
        return dst

    def _unlink_presence(self, path: Path) -> None:
        """Supprime une presence (symlink ou fichier) + compagnons + dossier zone."""
        from renatus.pipeline.steps.source_files import companion_files

        p = Path(path)
        folder = (
            p.with_suffix("")
            if p.suffix.lower() in {".yaml", ".yml"}
            else None
        )
        # F0146: retirer aussi .py / .ipynb jumeaux (symlinks ou reels si multi)
        if p.suffix.lower() in {".yaml", ".yml"}:
            for c in companion_files(p):
                try:
                    if c.is_symlink() or c.is_file():
                        c.unlink(missing_ok=True)
                except OSError:
                    pass
        try:
            if p.is_symlink() or p.is_file():
                p.unlink(missing_ok=True)
        except OSError as exc:
            raise OSError(f"Echec suppression {p}: {exc}") from exc
        if folder is not None and folder.is_symlink():
            try:
                folder.unlink(missing_ok=True)
            except OSError:
                pass

    def _promote_symlink_to_real(self, master: Path, promote: Path) -> Path:
        """
        Avant de retirer le fichier physique master: transforme promote
        (symlink) en fichier reel et re-pointe les autres liens.
        """
        if not promote.is_symlink():
            return promote
        try:
            if promote.resolve() != master.resolve():
                return promote
        except OSError:
            return promote
        content = master.read_bytes()
        master_folder = master.with_suffix("")
        promote_folder = promote.with_suffix("")
        promote.unlink(missing_ok=True)
        promote.write_bytes(content)
        if master_folder.is_dir() and not master_folder.is_symlink():
            if promote_folder.is_symlink():
                promote_folder.unlink(missing_ok=True)
            if not promote_folder.exists():
                try:
                    master_folder.rename(promote_folder)
                except OSError:
                    pass
        stem = master.stem
        root = self.pipeline_path
        if root.is_dir():
            for other in root.rglob(f"{stem}.yaml"):
                try:
                    if other.resolve() == promote.resolve():
                        continue
                except OSError:
                    continue
                if other.is_symlink():
                    try:
                        other.unlink(missing_ok=True)
                        self._relative_symlink(promote, other)
                    except OSError:
                        pass
                ofold = other.with_suffix("")
                if ofold.is_symlink() and promote_folder.exists():
                    try:
                        ofold.unlink(missing_ok=True)
                        self._relative_symlink(promote_folder, ofold)
                    except OSError:
                        pass
        try:
            if master.exists() or master.is_symlink():
                master.unlink(missing_ok=True)
        except OSError:
            pass
        return promote

    def _remove_step_from_multikey(self, path: Path, step_id: str) -> None:
        """
        Retire step_id d un YAML multi-cles (legacy gui.yaml).

        F0101: s il ne reste qu une cle, extrait vers <id>.yaml et supprime
        le fichier multi (evite residu bundle.yaml avec id=bundle).
        """
        if not path.is_file():
            return
        try:
            prev = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except OSError:
            return
        if not isinstance(prev, dict) or step_id not in prev:
            return
        del prev[step_id]
        try:
            if not prev:
                path.unlink(missing_ok=True)
                return
            remaining = list(prev.keys())
            # Une seule step restante → monocomposant <id>.yaml
            if len(remaining) == 1:
                rem_id = self.normalize_step_id(str(remaining[0]))
                cfg = prev[remaining[0]]
                if not isinstance(cfg, dict):
                    cfg = {}
                dest = path.parent / f"{rem_id}.yaml"
                if dest.resolve() != path.resolve():
                    self._dump_step_file(
                        dest, rem_id, self.normalize_step_config(rem_id, cfg)
                    )
                    path.unlink(missing_ok=True)
                    return
            path.write_text(
                yaml.dump(
                    prev,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def save_step(
        self,
        name: str,
        config: dict[str, Any],
        *,
        tab: str | None = None,
    ) -> Path:
        """
        Persiste une step (F0031 / F0060 / F0145).

        - F0031: un composant = un fichier <id>.yaml
        - F0145: un seul contenu physique ; les symlinks voient la meme donnee
        - F0067: config normalisee (sql → script)
        """
        step_id = self.normalize_step_id(name)
        clean = self.normalize_step_config(step_id, config)
        dedicated = f"{step_id}.yaml"

        paths = self.origins_of(step_id)
        if self.pipeline_path.is_file():
            target = self.pipeline_path
            self._dump_step_file(target, step_id, clean)
            self._origins[step_id] = [target]
            return target

        step_type = str(clean.get("type") or "") or None
        # F0146: notebook payload optionnel (dict) avant strip script yaml
        notebook_payload = clean.pop("_notebook", None)
        from renatus.pipeline.steps.source_files import SIDECAR_TYPES

        # YAML: ne stocke plus le corps du script (sidecar = verite)
        yaml_clean = dict(clean)
        if step_type in SIDECAR_TYPES:
            # garde un marqueur leger pour l UI / imports
            if yaml_clean.get("script") is not None:
                yaml_clean["script"] = ""  # corps dans .py / .ipynb

        def _persist_yaml_and_side(target: Path, body: dict[str, Any]) -> None:
            self._dump_step_file(target, step_id, body)
            self.write_sidecar_for_step(
                step_id,
                clean,  # version avec script complet
                yaml_path=target,
                notebook=(
                    notebook_payload
                    if isinstance(notebook_payload, dict)
                    else None
                ),
            )

        if not paths:
            target = self.default_path_for(
                step_id, tab=tab, step_type=step_type
            )
            _persist_yaml_and_side(target, yaml_clean)
            self._origins[step_id] = [target]
            return target

        # F0145: ecrire une fois par fichier physique resolu
        written: list[Path] = []
        seen_resolved: set[Path] = set()
        for origin in paths:
            try:
                resolved = origin.resolve()
            except OSError:
                resolved = origin
            if origin.name == dedicated:
                if resolved in seen_resolved:
                    continue
                seen_resolved.add(resolved)
                # preferer ecrire via le chemin non-symlink
                target = origin if not origin.is_symlink() else resolved
                _persist_yaml_and_side(target, yaml_clean)
                written.append(origin)
            else:
                # F0031: extraire du YAML multi-cles vers <id>.yaml
                tab_id = self.tab_of_path(origin)
                target = self.default_path_for(
                    step_id, tab=tab_id, step_type=step_type
                )
                try:
                    tres = target.resolve()
                except OSError:
                    tres = target
                if tres not in seen_resolved:
                    seen_resolved.add(tres)
                    _persist_yaml_and_side(target, yaml_clean)
                    written.append(target)
                if origin.resolve() != target.resolve():
                    self._remove_step_from_multikey(origin, step_id)

        self.refresh()
        return (
            self.origin_of(step_id)
            or (written[0] if written else paths[0])
        )

    def attach_to_tab(self, step_id: str, tab: str) -> Path:
        """
        F0060 / F0145: partage — symlink <id>.yaml (meme nom) vers le
        fichier physique unique. Si zone, symlink aussi le dossier homonyme.
        """
        step_id = str(step_id).strip()
        tab_id = self.normalize_tab_id(tab)
        if step_id not in self._origins and not self.origin_of(step_id):
            self.refresh()
        primary = self.origin_of(step_id)
        if primary is None or not primary.is_file():
            raise LookupError(
                f"Impossible de partager {step_id}: aucune source physique"
            )
        # master physique (pas un lien)
        try:
            master = primary if not primary.is_symlink() else primary.resolve()
        except OSError:
            master = primary
        if not master.is_file():
            raise LookupError(
                f"Impossible de partager {step_id}: source invalide"
            )
        content = yaml.safe_load(master.read_text(encoding="utf-8")) or {}
        if not isinstance(content, dict) or step_id not in content:
            raise LookupError(f"Config source absente pour {step_id}")
        clean = self.normalize_step_config(
            step_id, dict(content[step_id] or {})
        )
        dest = self.default_path_for(
            step_id,
            tab=tab_id,
            step_type=str(clean.get("type") or "") or None,
        )
        try:
            if dest.resolve() == master.resolve():
                return dest
        except OSError:
            if dest == master:
                return dest

        # presence deja un lien correct
        if dest.is_symlink():
            try:
                if dest.resolve() == master.resolve():
                    self.refresh()
                    return dest
            except OSError:
                pass

        # F0145: symlink fichier (remplace une ancienne copie reelle)
        self._relative_symlink(master, dest)

        # F0146: symlink compagnons meme stem (.py, .ipynb, …) non recursif
        try:
            self.symlink_companions(master, dest)
        except Exception:
            pass

        # Dossier zone homonyme → symlink de dossier
        src_folder = master.with_suffix("")
        if src_folder.is_dir() or src_folder.is_symlink():
            dest_folder = dest.with_suffix("")
            try:
                if not (
                    dest_folder.exists()
                    and dest_folder.resolve() == src_folder.resolve()
                    and dest_folder == src_folder
                ):
                    self._relative_symlink(src_folder, dest_folder)
            except Exception:
                # dossier optionnel (composant non-zone sans dossier)
                pass

        self.refresh()
        return dest

    def detach_from_tab(self, step_id: str, tab: str) -> None:
        """
        F0060 / F0145: retire une presence (symlink ou copie) d une zone.

        Refuse si c est la seule presence. Si on retire le fichier physique
        alors que d autres liens existent, un lien est promu en fichier reel.
        """
        step_id = str(step_id).strip()
        tab_id = self.normalize_tab_id(tab)
        paths = self.origins_of(step_id)
        if not paths:
            self.refresh()
            paths = self.origins_of(step_id)
        if len(paths) <= 1:
            raise ValueError(
                f"Impossible de retirer {step_id} de la zone {tab_id}: "
                "c est sa seule presence. Supprimez l objet completement "
                "ou partagez-le d abord dans une autre zone."
            )
        to_remove = [
            p for p in paths if self.tab_of_path(p) == tab_id
        ]
        if not to_remove:
            raise LookupError(
                f"{step_id} n a pas de presence dans l onglet {tab_id}"
            )
        remaining = [p for p in paths if p not in to_remove]
        for p in to_remove:
            if not p.is_symlink() and remaining:
                # retirer le master physique: promouvoir un autre lien
                promote = next(
                    (r for r in remaining if r.is_symlink()),
                    remaining[0],
                )
                try:
                    if p.resolve() == promote.resolve() or promote.is_symlink():
                        self._promote_symlink_to_real(p, promote)
                        continue
                except OSError:
                    pass
            self._unlink_presence(p)
        self.refresh()

    def move_to_tab(self, step_id: str, tab: str) -> Path:
        """
        F0060: deplace l unique presence physique vers un onglet (si multi: refuse).
        """
        paths = self.origins_of(step_id)
        if len(paths) != 1:
            raise ValueError(
                f"Deplacement de {step_id} refuse: "
                f"{len(paths)} presence(s) — utilisez share/detach"
            )
        src = paths[0]
        step_type = None
        try:
            raw = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict) and step_id in raw:
                step_type = str((raw[step_id] or {}).get("type") or "") or None
        except OSError:
            pass
        dest = self.default_path_for(step_id, tab=tab, step_type=step_type)
        if src.resolve() == dest.resolve():
            return dest
        # deplace fichier reel (+ dossier zone jumeau)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            raise ValueError(f"Destination deja presente: {dest}")
        src_folder = src.with_suffix("")
        src.rename(dest)
        if src_folder.is_dir() and not src_folder.is_symlink():
            dest_folder = dest.with_suffix("")
            if not dest_folder.exists():
                try:
                    src_folder.rename(dest_folder)
                except OSError:
                    pass
        self.refresh()
        return dest

    def list_all_zone_paths(self) -> list[str]:
        """
        Tous les chemins de zone existants (dossiers sous flow/).

        Inclut les niveaux imbriques (etl, etl/sub).
        F0082: exclut le dossier main (c est ROOT_TAB, pas une zone en plus).
        """
        path = self.pipeline_path
        if not path.is_dir():
            return []
        out: list[str] = []
        for p in sorted(path.rglob("*")):
            if not p.is_dir() or p.name.startswith("."):
                continue
            try:
                rel = p.resolve().relative_to(path.resolve())
            except ValueError:
                continue
            if not rel.parts:
                continue
            if any(part.startswith(".") for part in rel.parts):
                continue
            tid = "/".join(rel.parts)
            if tid == self.ROOT_TAB:
                continue
            # F0131: dossier auto/ n est pas une zone selectionnable
            if tid == self.AUTO_TAB or tid.startswith(self.AUTO_TAB + "/"):
                continue
            out.append(tid)
        return out

    def tab_meta(self, tab_id: str) -> dict[str, Any]:
        """Metadonnees d un onglet (chemin, compte, label)."""
        tid = self.normalize_tab_id(tab_id)
        d = self.dir_for_tab(tid)
        count = len(self.steps_in_tab(tid))
        label = tid if tid == self.ROOT_TAB else tid.split("/")[-1]
        return {
            "id": tid,
            "label": label,
            "path": str(d.resolve() if d.exists() else d),
            "step_count": count,
            "closable": tid != self.ROOT_TAB,
        }

    def list_tabs(self, open_ids: list[str] | None = None) -> list[dict[str, Any]]:
        """
        Liste les onglets a afficher.

        F0052: si open_ids est fourni, ne renvoie que ces onglets
        (main toujours inclus). Sinon comportement large: main +
        tous les dossiers de zone connus (compat F0027).
        """
        self.refresh()
        path = self.pipeline_path

        if path.is_file():
            return [
                {
                    "id": self.ROOT_TAB,
                    "label": self.ROOT_TAB,
                    "path": str(path),
                    "step_count": len(self._origins),
                    "closable": False,
                }
            ]

        if open_ids is not None:
            ordered: list[str] = []
            seen: set[str] = set()
            for tid in [self.ROOT_TAB, *open_ids]:
                clean = self.normalize_tab_id(tid)
                if clean in seen:
                    continue
                seen.add(clean)
                ordered.append(clean)
            return [self.tab_meta(tid) for tid in ordered]

        # Compat: main + toutes les zones existantes
        ids = [self.ROOT_TAB] + self.list_all_zone_paths()
        return [self.tab_meta(tid) for tid in ids]

    def steps_in_tab(self, tab: str) -> set[str]:
        """
        Steps dont au moins une copie YAML est dans le dossier de l onglet.

        F0060: un id peut apparaitre dans plusieurs tabs (copies).
        F0082: main.yaml (definition zone a la racine) n est pas un contenu
        de l onglet main — seulement flow/main/*.yaml.
        """
        tab_id = self.normalize_tab_id(tab)
        out: set[str] = set()
        root = self.pipeline_path
        for name, paths in self._origins.items():
            for p in paths:
                if self.tab_of_path(p) != tab_id:
                    continue
                # exclure flow/default.yaml du contenu de l onglet default
                if (
                    name == self.ROOT_TAB
                    and tab_id == self.ROOT_TAB
                    and root.is_dir()
                ):
                    try:
                        if p.resolve().parent == root.resolve():
                            continue
                    except OSError:
                        pass
                out.add(name)
                break
        return out

    @staticmethod
    def validate_tab_segment(name: str) -> str:
        """Valide un segment de nom de zone (pas de slash)."""
        raw = (name or "").strip()
        if not raw:
            raise ValueError("Nom de zone vide")
        if raw in {
            YamlStepStore.ROOT_TAB,
            YamlStepStore.LEGACY_ROOT_TAB,
        }:
            raise ValueError(
                f"Le nom '{YamlStepStore.ROOT_TAB}' est reserve a la racine"
            )
        if raw == YamlStepStore.ALL_TAB:
            raise ValueError(
                f"Le nom '{YamlStepStore.ALL_TAB}' est reserve "
                "(vue calculee tous composants)"
            )
        if raw.startswith(".") or "/" in raw or "\\" in raw:
            raise ValueError("Nom de zone invalide")
        allowed = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        )
        if any(c not in allowed for c in raw):
            raise ValueError(
                "Nom de zone: lettres, chiffres, _ et - uniquement"
            )
        return raw

    @staticmethod
    def validate_tab_name(name: str) -> str:
        """
        Valide un id d onglet (segment simple ou chemin imbrique a/b).
        """
        raw = (name or "").strip().replace("\\", "/")
        if not raw:
            raise ValueError("Nom d onglet vide")
        if raw in {
            YamlStepStore.ROOT_TAB,
            YamlStepStore.LEGACY_ROOT_TAB,
        }:
            raise ValueError(
                f"L onglet '{YamlStepStore.ROOT_TAB}' est reserve a la racine"
            )
        if raw == YamlStepStore.ALL_TAB or raw.startswith(
            YamlStepStore.ALL_TAB + "/"
        ):
            raise ValueError(
                f"L onglet '{YamlStepStore.ALL_TAB}' est reserve "
                "(vue calculee)"
            )
        parts = [p for p in raw.split("/") if p]
        if not parts:
            raise ValueError("Nom d onglet vide")
        for part in parts:
            YamlStepStore.validate_tab_segment(part)
        return "/".join(parts)


