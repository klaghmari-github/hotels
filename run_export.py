#!/usr/bin/env python3
"""Archive le projet pour audit : code source, données d'entrée et documentation."""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ExportStats:
    included: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


# Répertoires entièrement exclus (runtime, build, historique).
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "old",
    "exports",
    "node_modules",
}

# Chemins relatifs exclus (artefacts calculés, modèle, feature store runtime).
EXCLUDED_PREFIXES = (
    "data/processed/",
    "data/processed",
    "rod_ia/artifacts/",
    "rod_ia/artifacts",
    "rod_ia/feature_store/",
    "rod_ia/feature_store",
    "rod_ia/web/docs/",
    "rod_ia/web/docs",
)

# Fichiers de référence conservés dans data/reference/ (entrée manuelle).
REFERENCE_INPUTS = {
    "data/reference/hotel_identity_registry.json",
}

# Extensions autorisées par zone.
CODE_EXTENSIONS = {".py"}
WEB_EXTENSIONS = {".html", ".js", ".css"}
DOC_EXTENSIONS = {".md", ".txt"}
CONFIG_EXTENSIONS = {".toml", ".ini", ".cfg", ".yaml", ".yml"}
RAW_DATA_EXTENSIONS = {".csv", ".xlsx", ".xlsm", ".xls"}
DOC_ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
CONFIG_FILENAMES = {
    "requirements.txt",
    "README.md",
    ".gitignore",
    "MANIFEST.in",
}

ROOT_SHELL_SCRIPTS = {
    "init.sh",
    "run.sh",
    "test.sh",
    "zip.sh",
}


def _normalize_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_excluded_dir(part: str) -> bool:
    return part in EXCLUDED_DIRS


def _is_excluded_path(rel_posix: str) -> bool:
    if rel_posix in EXCLUDED_PREFIXES:
        return True
    return any(
        rel_posix == prefix or rel_posix.startswith(prefix + "/")
        for prefix in EXCLUDED_PREFIXES
    )


def _is_lock_or_temp(name: str) -> bool:
    return name.startswith(".~lock") or name.endswith("#") or name.startswith(".")


def _is_binary_artifact(name: str) -> bool:
    lowered = name.lower()
    return lowered.endswith(
        (".joblib", ".pkl", ".pickle", ".parquet", ".h5", ".hdf5", ".pt", ".pth", ".onnx")
    )


def _classify_file(rel_posix: str, path: Path) -> str | None:
    """Retourne une catégorie d'inclusion ou None si le fichier doit être ignoré."""
    name = path.name
    suffix = path.suffix.lower()

    if _is_lock_or_temp(name) or _is_binary_artifact(name):
        return None
    if name.endswith(".pyc") or name.endswith(".pyo"):
        return None
    if suffix == ".zip":
        return None

    parts = rel_posix.split("/")

    # Racine : scripts shell, points d'entrée, configuration.
    if len(parts) == 1:
        if name in CONFIG_FILENAMES or suffix in CONFIG_EXTENSIONS:
            return "config"
        if suffix == ".sh" and name in ROOT_SHELL_SCRIPTS:
            return "script"
        if (name.startswith("run_") and suffix == ".py") or name == "consignes.txt":
            return "entrypoint"
        return None

    top = parts[0]

    if top == "prepare":
        if suffix in CODE_EXTENSIONS:
            return "python"
        if suffix in DOC_EXTENSIONS:
            return "documentation"
        return None

    if top == "rod_ia":
        if suffix in CODE_EXTENSIONS:
            return "python"
        if parts[:2] == ["rod_ia", "web"] and len(parts) == 3 and suffix in WEB_EXTENSIONS:
            return "web"
        return None

    if top == "tests" and suffix in CODE_EXTENSIONS:
        return "test"

    if top == "scripts" and suffix in CODE_EXTENSIONS:
        return "script_py"

    if top == "docs" and suffix in DOC_EXTENSIONS | DOC_ASSET_EXTENSIONS:
        return "documentation"

    if top == "sources":
        # Données brutes et documentation associée dans sources/raw/.
        if suffix in RAW_DATA_EXTENSIONS | DOC_EXTENSIONS | DOC_ASSET_EXTENSIONS:
            return "raw_input"
        return None

    if top == "data":
        if rel_posix in REFERENCE_INPUTS:
            return "reference_input"
        return None

    return None


def collect_files(root: Path) -> ExportStats:
    stats = ExportStats()

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current = Path(dirpath)
        rel_dir = _normalize_rel(current, root) if current != root else ""

        if _is_excluded_path(rel_dir):
            dirnames.clear()
            continue

        dirnames[:] = sorted(
            d for d in dirnames if not _is_excluded_dir(d) and not d.startswith(".egg-info")
        )

        for filename in sorted(filenames):
            file_path = current / filename
            rel_posix = f"{rel_dir}/{filename}" if rel_dir else filename

            if _is_excluded_path(rel_posix):
                stats.skipped.append(rel_posix)
                continue

            category = _classify_file(rel_posix, file_path)
            if category is None:
                stats.skipped.append(rel_posix)
                continue

            if not file_path.is_file():
                stats.skipped.append(rel_posix)
                continue

            stats.included.append(rel_posix)

    return stats


def write_manifest(root: Path, stats: ExportStats, archive_name: str) -> str:
    lines = [
        "ROD-IA — archive d'audit",
        f"Générée le : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Archive : {archive_name}",
        "",
        "Contenu inclus :",
        "  - Code Python (rod_ia/, tests/, scripts/, run_*.py)",
        "  - Interface web source (rod_ia/web/*.html, *.js, *.css)",
        "  - Documentation (docs/, README.md)",
        "  - Données d'entrée brutes (sources/raw/)",
        "  - Registre identité hôtel (data/reference/hotel_identity_registry.json)",
        "  - Configuration (requirements.txt, pyproject.toml, scripts shell)",
        "",
        "Contenu exclu :",
        "  - Environnements virtuels, caches, dépôt git",
        "  - Artefacts ML (rod_ia/artifacts/, *.joblib)",
        "  - Datasets et rapports calculés (data/processed/)",
        "  - Références extraites d'Excel (data/reference/ sauf registre identité)",
        "  - Feature store runtime (geo, météo, simulations, targets)",
        "  - Documentation code générée (rod_ia/web/docs/)",
        "  - Répertoire old/",
        "",
        f"Fichiers inclus : {len(stats.included)}",
        f"Fichiers ignorés : {len(stats.skipped)}",
        "",
        "Liste des fichiers inclus :",
    ]
    lines.extend(f"  + {path}" for path in stats.included)
    return "\n".join(lines) + "\n"


def create_archive(root: Path, output_dir: Path, stamp: str | None = None) -> Path:
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"rod-ia-audit-{stamp}.zip"

    stats = collect_files(root)
    if not stats.included:
        raise RuntimeError("Aucun fichier à inclure — vérifiez les règles d'export.")

    manifest = write_manifest(root, stats, archive_path.name)

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel_posix in stats.included:
            zf.write(root / rel_posix, rel_posix)
        zf.writestr("EXPORT_MANIFEST.txt", manifest)

    return archive_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Génère une archive ZIP du projet pour audit (sources et entrées uniquement)."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Racine du projet (défaut : répertoire de run_export.py)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Répertoire de sortie (défaut : <root>/exports)",
    )
    parser.add_argument(
        "--stamp",
        default=None,
        help="Horodatage dans le nom de fichier (défaut : maintenant)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    output_dir = (args.output_dir or root / "exports").resolve()

    if not root.is_dir():
        print(f"Racine introuvable : {root}", file=sys.stderr)
        return 1

    try:
        archive = create_archive(root, output_dir, stamp=args.stamp)
    except Exception as exc:
        print(f"Échec export : {exc}", file=sys.stderr)
        return 1

    stats = collect_files(root)
    print(f"[export] Archive : {archive}")
    print(f"[export] Fichiers inclus : {len(stats.included)}")
    print(f"[export] Fichiers ignorés : {len(stats.skipped)}")
    print(f"[export] Manifeste : EXPORT_MANIFEST.txt (dans l'archive)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())