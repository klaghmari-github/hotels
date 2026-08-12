"""
YamlStepStore — persistence monocomposant + onglets/zones.

F0031: un composant = fichiers <id>.yaml
F0060: multi-presence = plusieurs copies <id>.yaml (meme id) sous
differents dossiers de zone. Save propage sur toutes les copies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class YamlStepStore:
    """
    Index step -> liste de fichiers YAML (copies multi-zones F0060).

    Onglets / zones :
    - tab "default" = flow/default/*.yaml (F0082 / F0144, zone racine protegee)
    - legacy "main" migre vers "default" a l ouverture
    - sous-zones : flow/default/<zone>/… (hierarchie)
    - Presence dans une zone = fichier <id>.yaml dans ce dossier
    - Partage = duplication du fichier (meme id)

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
            content = yaml.safe_load(
                yaml_file.read_text(encoding="utf-8")
            ) or {}
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
        # dedupe + tri stable (main d abord = chemin plus court)
        for name, paths in list(origins.items()):
            uniq: list[Path] = []
            seen: set[Path] = set()
            for p in sorted(paths, key=lambda x: (len(x.parts), str(x))):
                r = p.resolve()
                if r in seen:
                    continue
                seen.add(r)
                uniq.append(p)
            origins[name] = uniq
        self._origins = origins

    def origins_of(self, name: str) -> list[Path]:
        """Toutes les copies disque de l objet (F0060)."""
        return list(self._origins.get(str(name), []))

    def origin_of(self, name: str) -> Path | None:
        """Copie primaire (home preferentiel: main / chemin le plus court)."""
        paths = self.origins_of(name)
        if not paths:
            return None
        # preferer main
        for p in paths:
            if self.tab_of_path(p) == self.ROOT_TAB:
                return p
        return paths[0]

    def tabs_of(self, name: str) -> list[str]:
        """Tous les onglets/zones FS ou l objet a une copie."""
        tabs = {self.tab_of_path(p) for p in self.origins_of(name)}
        if not tabs:
            return [self.active_tab or self.ROOT_TAB]
        # main d abord
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
        """
        path = self.pipeline_path
        if path.is_file():
            return self.ROOT_TAB
        try:
            rel = file_path.resolve().relative_to(path.resolve())
        except ValueError:
            return self.ROOT_TAB
        parts = rel.parts
        if len(parts) <= 1:
            # racine flow: default.yaml ou legacy step.yaml
            return self.ROOT_TAB
        parent = "/".join(parts[:-1])
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
        path.parent.mkdir(parents=True, exist_ok=True)
        content = {step_id: clean}
        dumped = yaml.dump(
            content,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        path.write_text(dumped, encoding="utf-8")

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
        Persiste une step dans TOUTES ses copies <id>.yaml (F0031 / F0060).

        - F0031: un composant = un fichier <id>.yaml (extraction depuis multi-cles)
        - F0060: multi-presence = N fichiers synchronises
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
        if not paths:
            target = self.default_path_for(
                step_id, tab=tab, step_type=step_type
            )
            self._dump_step_file(target, step_id, clean)
            self._origins[step_id] = [target]
            return target

        written: list[Path] = []
        for origin in paths:
            if origin.name == dedicated:
                # copie monocomposant (F0060 multi-zone)
                self._dump_step_file(origin, step_id, clean)
                written.append(origin)
            else:
                # F0031: extraire du YAML multi-cles vers <id>.yaml
                tab_id = self.tab_of_path(origin)
                target = self.default_path_for(
                    step_id, tab=tab_id, step_type=step_type
                )
                self._dump_step_file(target, step_id, clean)
                written.append(target)
                if origin.resolve() != target.resolve():
                    self._remove_step_from_multikey(origin, step_id)

        self.refresh()
        return written[0] if written else (
            self.origin_of(step_id) or paths[0]
        )

    def attach_to_tab(self, step_id: str, tab: str) -> Path:
        """
        F0060: partage — duplique <id>.yaml dans le dossier de l onglet/zone.
        """
        step_id = str(step_id).strip()
        tab_id = (tab or self.ROOT_TAB).strip() or self.ROOT_TAB
        if step_id not in self._origins and not self.origin_of(step_id):
            # peut arriver avant refresh
            self.refresh()
        primary = self.origin_of(step_id)
        if primary is None or not primary.is_file():
            raise LookupError(
                f"Impossible de partager {step_id}: aucune copie source"
            )
        content = yaml.safe_load(primary.read_text(encoding="utf-8")) or {}
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
        if dest.resolve() == primary.resolve():
            return dest
        if dest.is_file():
            # deja present
            self.refresh()
            return dest
        self._dump_step_file(dest, step_id, clean)
        self.refresh()
        return dest

    def detach_from_tab(self, step_id: str, tab: str) -> None:
        """
        F0060: retire une copie de zone.

        Refuse si c est la seule copie (evite objet orphelin / reference perdue).
        """
        step_id = str(step_id).strip()
        tab_id = (tab or self.ROOT_TAB).strip() or self.ROOT_TAB
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
                f"{step_id} n a pas de copie dans l onglet {tab_id}"
            )
        for p in to_remove:
            try:
                if p.is_file():
                    # monocomposant attendu
                    p.unlink(missing_ok=True)
            except OSError as exc:
                raise OSError(f"Echec suppression {p}: {exc}") from exc
        self.refresh()

    def move_to_tab(self, step_id: str, tab: str) -> Path:
        """
        F0060: deplace l unique copie vers un onglet (si multi: refuse).
        """
        paths = self.origins_of(step_id)
        if len(paths) != 1:
            raise ValueError(
                f"Deplacement de {step_id} refuse: "
                f"{len(paths)} copie(s) — utilisez share/detach"
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
        content = src.read_text(encoding="utf-8")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        src.unlink(missing_ok=True)
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


