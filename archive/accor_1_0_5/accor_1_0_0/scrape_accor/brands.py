#!/usr/bin/env python3
"""
Extraction des marques Accor depuis https://all.accor.com/a/fr/brands.html

Sorties (``accord/data/marques/``) :
* ``marques.xlsx`` — noms en **MAJUSCULES**, catégorie, chemins logos
* ``{categorie_slug}/{MARQUE_SLUG}.png`` — logos par sous-dossier catégorie

Convention jointure
-------------------
``marque_nom`` est toujours en full uppercase (ex. ``IBIS BUDGET``, ``MERCURE``)
pour faciliter les jointures avec hotel_brand / concept_pilote.
"""

from __future__ import annotations

import re
import shutil
from html import unescape
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

from archive.accor_1_0_5.accor_1_0_0.scrape_accor.http_util import fetch

BRANDS_URL = "https://all.accor.com/a/fr/brands.html"
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "marques"
XLSX_NAME = "marques.xlsx"


def _slugify(name: str) -> str:
    """Slug fichier (minuscules, underscores) — pas pour jointures métier."""
    text = unescape(name or "").strip().lower()
    text = (
        text.replace("&", "et")
        .replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("à", "a")
        .replace("ù", "u")
        .replace("ô", "o")
        .replace("ö", "o")
        .replace("ü", "u")
        .replace("'", "")
        .replace("’", "")
        .replace("/", " ")
    )
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or ""


def normalize_brand_name(name: str) -> str:
    """Nom de marque en **MAJUSCULES** (jointures)."""
    text = unescape(name or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text.upper()


def normalize_category(category: str) -> str:
    """Libellé catégorie en **MAJUSCULES** (jointures / affichage)."""
    text = unescape(category or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text.upper() if text else "AUTRES"


def category_dir_name(category: str) -> str:
    """
    Nom de sous-dossier pour une catégorie (slug stable, minuscules).

    Ex. ``LIFESTYLE BY ENNISMORE`` → ``lifestyle_by_ennismore``
    """
    return _slugify(category) or "autres"


def _parse_brands(html: str) -> list[dict[str, Any]]:
    """Parse les cartes ``brands__item``."""
    pattern = re.compile(
        r'<div class="brands__item" data-brand="([^"]*)" data-category="([^"]*)">\s*'
        r'<a href="([^"]+)"[^>]*>\s*'
        r'<div class="brands__item-header">\s*'
        r'<span class="brands__item-logo">\s*'
        r'<img[^>]+src="([^"]+)"',
        re.S | re.I,
    )
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, m in enumerate(pattern.finditer(html), start=1):
        raw_name = unescape(m.group(1)).strip()
        raw_category = unescape(m.group(2)).strip()
        url = m.group(3).strip()
        logo_url = m.group(4).strip()
        slug_m = re.search(r"/brands/([^/]+)\.html", url, re.I)
        slug = slug_m.group(1).lower() if slug_m else _slugify(raw_name)
        nom_extractable = bool(raw_name)
        if not raw_name:
            raw_name = f"marque_{i}"
            slug = f"marque_{i}"
        name = normalize_brand_name(raw_name)
        category = normalize_category(raw_category)
        key = slug or f"marque_{i}"
        if key in seen:
            key = f"{key}_{i}"
        seen.add(key)
        cat_dir = category_dir_name(category)
        rows.append(
            {
                "marque_id": i,
                "marque_nom": name,
                "marque_slug": (slug or f"marque_{i}").upper().replace("-", "_"),
                "categorie": category,
                "categorie_slug": cat_dir,
                "url_marque": url,
                "logo_url": logo_url,
                "logo_file": "",
                "logo_path": "",
                "nom_extractable": nom_extractable,
            }
        )
    return rows


def _is_svg_bytes(data: bytes) -> bool:
    head = data[:512].lstrip().lower()
    return head.startswith(b"<svg") or head.startswith(b"<?xml") or b"<svg" in head


def _download_logo(logo_url: str, dest: Path) -> bool:
    """
    Télécharge le logo Accor.

    Accor renvoie souvent du **SVG** (même avec ``fmt=png-alpha``).
    On enregistre :
    * vrai PNG si décodable par Pillow
    * sinon le SVG brut (l'API admin sert ``image/svg+xml`` au navigateur)
    """
    if not logo_url:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = logo_url
    if "m.ahstatic.com" in url and "?" not in url:
        url = url + "?fmt=png-alpha&wid=400"
    try:
        code, data = fetch(url, binary=True, pause_s=0.2, timeout=30)
        if code != 200 or not data:
            return False
    except Exception:
        return False

    # Vrai raster
    try:
        from PIL import Image

        img = Image.open(BytesIO(data))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        img.save(dest, format="PNG")
        return True
    except Exception:
        pass

    # SVG (cas Accor monochrome) — on garde le contenu tel quel sous .png
    # (chemin stable) ; l'endpoint Flask sniffe le MIME pour le navigateur.
    try:
        if _is_svg_bytes(data):
            dest.write_bytes(data)
            return True
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def extract_brands(*, out_dir: Path | None = None, force: bool = False) -> dict[str, Any]:
    """
    Scrape la page marques + logos → ``marques.xlsx`` + PNG par catégorie.

    * ``marque_nom`` et ``categorie`` en MAJUSCULES
    * logos dans ``out_dir / {categorie_slug} / {slug}.png``
    """
    out_dir = out_dir or OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    code, html = fetch(BRANDS_URL, pause_s=0.5, timeout=40)
    if code != 200 or not html:
        raise RuntimeError(f"Page marques inaccessible (HTTP {code})")

    brands = _parse_brands(html)
    if not brands:
        raise RuntimeError("Aucune marque extraite — structure HTML changée ?")

    for row in brands:
        row["categorie"] = normalize_category(str(row.get("categorie") or ""))
        row["categorie_slug"] = category_dir_name(row["categorie"])
        cat_dir = row["categorie_slug"]
        slug_file = _slugify(row["marque_nom"]) or f"marque_{row['marque_id']}"
        if not row["nom_extractable"]:
            fname = f"marque_{row['marque_id']:02d}.png"
        else:
            fname = f"{slug_file}.png"
        rel = f"{cat_dir}/{fname}"
        dest = out_dir / cat_dir / fname
        if force or not dest.exists():
            ok = _download_logo(row["logo_url"], dest)
            if not ok:
                ok = _download_logo(re.sub(r"\?.*$", "", row["logo_url"]), dest)
            row["logo_ok"] = ok
        else:
            row["logo_ok"] = True
        row["logo_file"] = fname if dest.exists() else ""
        row["logo_path"] = rel if dest.exists() else ""
        row["marque_slug"] = slug_file.upper()

    frame = pd.DataFrame(brands)
    # Garantir uppercase
    frame["marque_nom"] = frame["marque_nom"].map(normalize_brand_name)
    frame["categorie"] = frame["categorie"].map(normalize_category)
    cols = [
        "marque_id",
        "marque_nom",
        "marque_slug",
        "categorie",
        "categorie_slug",
        "url_marque",
        "logo_file",
        "logo_path",
        "logo_url",
        "logo_ok",
        "nom_extractable",
    ]
    frame = frame[[c for c in cols if c in frame.columns]]
    xlsx = out_dir / XLSX_NAME
    frame.to_excel(xlsx, index=False, sheet_name="marques")

    return {
        "ok": True,
        "path": str(xlsx),
        "out_dir": str(out_dir),
        "n_brands": len(frame),
        "n_logos": int(frame["logo_ok"].sum()) if "logo_ok" in frame.columns else 0,
        "categories": sorted(frame["categorie"].dropna().unique().tolist()),
        "brands": frame["marque_nom"].tolist(),
    }


def reorganize_existing_marques(*, out_dir: Path | None = None) -> dict[str, Any]:
    """
    Réorganise un scrape déjà fait :
    * ``marque_nom`` et ``categorie`` en MAJUSCULES dans ``marques.xlsx``
    * logos déplacés vers ``{categorie_slug}/{slug}.png``
    * nettoyage des PNG à la racine de ``marques/``
    """
    out_dir = out_dir or OUT_DIR
    xlsx = out_dir / XLSX_NAME
    if not xlsx.exists():
        raise FileNotFoundError(f"{xlsx} introuvable — lancez d'abord extract_brands()")

    frame = pd.read_excel(xlsx)
    if "marque_nom" not in frame.columns or "categorie" not in frame.columns:
        raise ValueError("marques.xlsx incomplet (marque_nom / categorie requis)")

    moved = 0
    missing = 0
    rows_out: list[dict[str, Any]] = []

    for i, row in frame.iterrows():
        nom = normalize_brand_name(str(row.get("marque_nom") or ""))
        cat = normalize_category(str(row.get("categorie") or "autres"))
        cat_slug = category_dir_name(cat)
        old_file = str(row.get("logo_file") or "").strip()
        slug_file = _slugify(nom) or f"marque_{int(row.get('marque_id') or i) + 1:02d}"
        fname = f"{slug_file}.png"
        if not nom or nom.startswith("MARQUE_"):
            mid = int(row.get("marque_id") or (i + 1))
            fname = f"marque_{mid:02d}.png"

        dest = out_dir / cat_slug / fname
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Chercher le fichier source (racine ou déjà en sous-dossier)
        candidates = []
        if old_file:
            candidates.append(out_dir / old_file)
            candidates.append(out_dir / Path(old_file).name)
        if "logo_path" in row and pd.notna(row.get("logo_path")):
            candidates.append(out_dir / str(row["logo_path"]))
        candidates.append(out_dir / f"{_slugify(str(row.get('marque_nom') or ''))}.png")
        candidates.append(out_dir / fname)

        src = next((p for p in candidates if p.exists() and p.is_file()), None)
        if src is None:
            # chercher par ancien slug
            for p in out_dir.glob("*.png"):
                if p.stem.lower() in {
                    _slugify(str(row.get("marque_nom") or "")),
                    str(row.get("marque_slug") or "").lower(),
                    Path(old_file).stem.lower() if old_file else "",
                }:
                    src = p
                    break

        logo_ok = False
        if src and src.exists():
            if src.resolve() != dest.resolve():
                shutil.move(str(src), str(dest))
                moved += 1
            logo_ok = True
        else:
            missing += 1

        rows_out.append(
            {
                "marque_id": int(row.get("marque_id") or (i + 1)),
                "marque_nom": nom,
                "marque_slug": slug_file.upper(),
                "categorie": cat,
                "categorie_slug": cat_slug,
                "url_marque": row.get("url_marque"),
                "logo_file": fname if logo_ok else "",
                "logo_path": f"{cat_slug}/{fname}" if logo_ok else "",
                "logo_url": row.get("logo_url"),
                "logo_ok": logo_ok,
                "nom_extractable": bool(nom) and not nom.startswith("MARQUE_"),
            }
        )

    out = pd.DataFrame(rows_out)
    out.to_excel(xlsx, index=False, sheet_name="marques")

    # Supprimer PNG orphelins à la racine (hors sous-dossiers hotels*)
    cleaned = 0
    for p in out_dir.glob("*.png"):
        try:
            p.unlink()
            cleaned += 1
        except Exception:
            pass

    return {
        "ok": True,
        "path": str(xlsx),
        "n_brands": len(out),
        "moved": moved,
        "missing_logos": missing,
        "cleaned_root_png": cleaned,
        "categories": sorted(out["categorie"].dropna().unique().tolist()),
        "brands": out["marque_nom"].tolist(),
    }


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Scrape / organise marques Accor")
    p.add_argument("--force", action="store_true", help="Retélécharger les logos")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument(
        "--reorganize-only",
        action="store_true",
        help="Réorganise marques.xlsx existant (MAJUSCULES + sous-dossiers catégorie)",
    )
    args = p.parse_args()
    if args.reorganize_only:
        result = reorganize_existing_marques(out_dir=args.out)
    else:
        result = extract_brands(out_dir=args.out, force=args.force)
    print(result)


if __name__ == "__main__":
    main()
