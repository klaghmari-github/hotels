"""
Cache-busting : ``?dt=<mtime>`` sur assets statiques et imports JS/CSS.

Si un fichier change, son URL change → le navigateur recharge sans vider
le cache manuellement.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from flask import Flask, Response, request, send_from_directory

# import … from "./foo.js"  |  import "./foo.js"
_JS_FROM = re.compile(
    r"""(?P<pre>(?:import|export)\s+(?:type\s+)?(?:[^'"\n]+?\s+from\s+|))"""
    r"""(?P<q>['"])(?P<path>\.?\.?/+[^'"]+\.(?:js|mjs|css|json))(?P=q)""",
    re.MULTILINE,
)
_JS_SIDE = re.compile(
    r"""(?P<pre>import\s*)(?P<q>['"])(?P<path>\.?\.?/+[^'"]+\.(?:js|mjs|css|json))(?P=q)""",
    re.MULTILINE,
)
# url("…") / url(…)
_CSS_URL = re.compile(
    r"""url\(\s*(?P<q>['"]?)(?P<path>(?!data:)(?!https?:)(?!//)[^)'"\s]+?)(?P=q)\s*\)""",
    re.IGNORECASE,
)


def file_dt(path: Path) -> int:
    try:
        return int(path.stat().st_mtime)
    except OSError:
        return 0


def with_dt(url: str, mtime: int) -> str:
    if "dt=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}dt={mtime}"


def resolve_rel(base_file: Path, rel: str, static_root: Path) -> Path | None:
    rel_clean = rel.split("?")[0].split("#")[0]
    if rel_clean.startswith("/static/"):
        candidate = static_root / rel_clean[len("/static/") :]
    elif rel_clean.startswith("/"):
        return None
    else:
        candidate = (base_file.parent / rel_clean).resolve()
    try:
        candidate.relative_to(static_root.resolve())
    except ValueError:
        # allow if under static_root via symlink resolution fail
        if not str(candidate).startswith(str(static_root.resolve())):
            return candidate if candidate.exists() else None
    return candidate if candidate.exists() else None


def rewrite_js_imports(content: str, base_file: Path, static_root: Path) -> str:
    def repl(m: re.Match[str]) -> str:
        path = m.group("path")
        target = resolve_rel(base_file, path, static_root)
        dt = file_dt(target) if target else 0
        new_path = with_dt(path, dt) if dt else path
        return f"{m.group('pre')}{m.group('q')}{new_path}{m.group('q')}"

    out = _JS_FROM.sub(repl, content)
    out = _JS_SIDE.sub(repl, out)
    return out


def rewrite_css_urls(content: str, base_file: Path, static_root: Path) -> str:
    def repl(m: re.Match[str]) -> str:
        path = m.group("path")
        if path.startswith(("data:", "http://", "https://", "//")):
            return m.group(0)
        target = resolve_rel(base_file, path, static_root)
        dt = file_dt(target) if target else 0
        new_path = with_dt(path, dt) if dt else path
        q = m.group("q") or ""
        return f"url({q}{new_path}{q})"

    return _CSS_URL.sub(repl, content)


def make_asset_helper(static_root: Path) -> Callable[[str], str]:
    """Pour templates Jinja : ``{{ asset('css/app.css') }}`` → ``/static/css/app.css?dt=…``."""
    import os

    prefix = (os.environ.get("ACCOR_URL_PREFIX") or "").strip().rstrip("/")

    def asset(rel: str) -> str:
        rel = rel.lstrip("/")
        if rel.startswith("static/"):
            rel = rel[len("static/") :]
        path = static_root / rel
        return with_dt(f"{prefix}/static/{rel}", file_dt(path))

    return asset


def register_cache_bust(app: Flask, static_root: Path) -> None:
    """
    * ``asset()`` dans les templates (``?dt=<mtime>``)
    * route ``/static/<path>`` qui réécrit imports JS/CSS avec ``?dt=``
    * HTML / API : jamais de cache navigateur agressif
    * Static avec ``?dt=`` : cache long (URL change si le fichier change)
    """
    import os

    static_root = Path(static_root).resolve()
    asset = make_asset_helper(static_root)
    url_prefix = (os.environ.get("ACCOR_URL_PREFIX") or "").strip().rstrip("/")

    # Recharge templates dès qu'un .html change (sans redémarrer le process)
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    @app.context_processor
    def _inject_asset():
        return {
            "asset": asset,
            "static_dt": asset,
            "url_prefix": url_prefix,
        }

    @app.after_request
    def _no_cache_html_and_api(resp: Response):
        """
        Le HTML doit toujours être rechargé : il porte les ?dt= des JS/CSS.
        Sans ça, un vieux index.html garde d'anciens dt → faux cache « vide-cache ».
        """
        ctype = (resp.content_type or "").split(";")[0].strip().lower()
        path = request.path or ""
        if ctype in ("text/html", "application/xhtml+xml"):
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
        elif path.startswith("/api/") or ctype == "application/json":
            resp.headers.setdefault(
                "Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"
            )
        return resp

    # Remplace l'envoi static Flask par une version cache-bust
    @app.route("/static/<path:filename>")
    def cache_busted_static(filename: str):
        full = (static_root / filename).resolve()
        try:
            full.relative_to(static_root)
        except ValueError:
            return Response("Forbidden", status=403)

        if not full.is_file():
            return Response("Not Found", status=404)

        # client may request with ?dt= — ignore for disk path
        suffix = full.suffix.lower()
        if suffix in {".js", ".mjs"}:
            text = full.read_text(encoding="utf-8", errors="replace")
            body = rewrite_js_imports(text, full, static_root)
            resp = Response(body, mimetype="application/javascript; charset=utf-8")
        elif suffix == ".css":
            text = full.read_text(encoding="utf-8", errors="replace")
            body = rewrite_css_urls(text, full, static_root)
            resp = Response(body, mimetype="text/css; charset=utf-8")
        else:
            resp = send_from_directory(static_root, filename)
            # send_from_directory returns a Response already
            if not isinstance(resp, Response):
                return resp
            # fall through to headers

        # Avec ?dt= (via asset()) → cache long sûr. Sans dt → revalider (évite vieux JS).
        has_dt = "dt=" in (request.query_string.decode("utf-8", errors="ignore") or "")
        if has_dt:
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            resp.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        # Aide reverse-proxy / CDN à ne pas coller un vieux static sans dt
        try:
            resp.headers["Last-Modified"] = (
                __import__("email.utils", fromlist=["formatdate"]).formatdate(
                    full.stat().st_mtime, usegmt=True
                )
            )
        except OSError:
            pass
        return resp
