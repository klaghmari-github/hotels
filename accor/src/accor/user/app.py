"""
Interface user — simulateur ROD pour le directeur d'hôtel.

Parcours simple : trouver l'hôtel, vérifier la fiche, régler le corner,
lire le résultat (CA, coûts, marge, solution recommandée).
Rien n'est enregistré en base depuis cette interface.

Lancer : python run_user.py  →  port 5056
"""

from __future__ import annotations

import argparse
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from accor.cache_bust import register_cache_bust
from accor.data_io import PROJECT_ROOT, STATIC_DIR, TEMPLATES_DIR

from accor.user.models import SimulationRequest
from accor.user.reference import RodReference
from accor.user.services.catalog import AdminCatalog
from accor.user.services.enrich import FeatureEnricher
from accor.user.services.geocode import Geocoder
from accor.user.services.hotel_context import HotelContextBuilder
from accor.user.services.orchestrator import SimulationOrchestrator

# static/ entier pour servir user/ + shared/ (modules ES communs)
ROOT = PROJECT_ROOT
app = Flask(
    __name__,
    template_folder=str(TEMPLATES_DIR / "user"),
    static_folder=None,  # servi via cache_bust (?dt=mtime)
    static_url_path="/static",
)
app.config["JSON_AS_ASCII"] = False
register_cache_bust(app, STATIC_DIR)

# Singletons légers
_catalog = AdminCatalog()
_reference = RodReference()
_orchestrator = SimulationOrchestrator(reference=_reference, auto_enrich=True)
_geocoder = Geocoder()
_enricher = FeatureEnricher(geocoder=_geocoder)
_context = HotelContextBuilder()


@app.get("/")
def index():
    """Page directeur (templates/user/index.html)."""
    return render_template("index.html")


@app.get("/api/health")
def health():
    """Sonde + concepts chargés depuis rod_reference.json."""
    return jsonify(
        {
            "status": "ok",
            "app": "accord-rod-user",
            "concepts": _reference.concept_names(),
            "reference_loaded": bool(_reference.concept_names()),
        }
    )


@app.get("/api/rod/meta")
@app.get("/api/meta")
def meta():
    """Métadonnées UI : sous-cat., défauts corner (aligné admin)."""
    from accor.rod_admin import rod_ui_meta

    base = rod_ui_meta()
    concepts = {}
    for name in _reference.concept_names():
        c = _reference.concept(name)
        concepts[name] = {
            "pivot_nb_chambres": c.get("pivot_nb_chambres"),
            "pivot_to": c.get("pivot_to"),
            "pivot_m_lin": c.get("pivot_m_lin"),
            "pivot_guests_per_chambre": c.get("pivot_guests_per_chambre"),
            "mix_fb": c.get("mix_fb"),
            "mix_nf": c.get("mix_nf"),
        }
    base["concepts"] = concepts
    base["model_defaults"] = _catalog.model_defaults()
    return jsonify(base)


@app.post("/api/rod/simulate")
def api_rod_simulate():
    """
    Simulation pour le directeur d'hôtel.

    Retourne un résumé clair : CA simulé, CA estimé par le modèle (si dispo),
    coûts, marge et solution recommandée pour Simply, Liberty et Connected.
    Les réglages ne sont pas enregistrés en base.
    """
    body = request.get_json(force=True, silent=True) or {}
    try:
        from accor.user.services.director import director_simulate

        result = director_simulate(body)
        status = 200 if result.get("ok") else 400
        return jsonify(result), status
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.get("/api/brands")
def brands():
    """Liste des marques (hotel_brand_data) pour listes déroulantes UI."""
    return jsonify({"brands": _catalog.list_brands()})


@app.get("/api/concept_pilote/brand/<path:brand>")
def concept_pilote_brand_averages(brand: str):
    """
    Étape 1 run_user — moyennes d'exploitation pour une marque.

    Lit ``concept_pilote.xlsx``, filtre la marque, exclut l'année la plus
    récente (ex. 2026), moyenne des champs utiles (sans mix F_B / N_F_B).
    Inclut aussi ``rule1`` : CA mensuel attendu par concept (impact TO + R1).
    """
    from accor.concept_pilote import brand_step1_averages

    result = brand_step1_averages(brand)
    return jsonify(result), (200 if result.get("ok") else 404)


@app.post("/api/rule1")
def api_rule1():
    """
    Applique impact TO + Règle 1 (scaling clients) pour SIMPLY / LIBERTY / CONNECTED.

    Body JSON : ``nb_chambres``, ``taux_occupation`` (0–1 ou %), ``guests_per_chambre``.
    """
    from accor.concept_pilote import rule1_ca_by_concept

    body = request.get_json(force=True, silent=True) or {}
    try:
        result = rule1_ca_by_concept(
            nb_chambres=float(body.get("nb_chambres") or 0),
            taux_occupation=float(body.get("taux_occupation") or 0),
            guests_per_chambre=float(body.get("guests_per_chambre") or 1.7),
        )
        return jsonify(result)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.get("/api/hotels")
def hotels():
    """Liste complete (peut etre lourde) — preferer /api/hotels/index pour l UI."""
    return jsonify({"hotels": _catalog.list_hotels(), "n": len(_catalog.list_hotels())})


@app.get("/api/hotels/index")
def hotels_index():
    """
    Index léger (code, nom, marque, ville) pour filtrage autocomplete côté client.

    Chargé une fois au démarrage du wizard ; le filtre se fait en local à la frappe.
    """
    items = _catalog.list_hotel_index()
    return jsonify({"ok": True, "n": len(items), "hotels": items})


@app.get("/api/hotels/search")
def hotels_search():
    """
    Autocomplete hotels (hotel_data).

    Query: q (code, nom, ville, marque ; vide = aperçu de la base),
    limit (défaut 40, max 80).
    """
    q = str(request.args.get("q") or request.args.get("query") or "").strip()
    try:
        limit = int(request.args.get("limit") or 40)
    except (TypeError, ValueError):
        limit = 40
    results = _catalog.search_hotels(q, limit=limit)
    return jsonify({"ok": True, "q": q, "n": len(results), "hotels": results})


@app.get("/api/hotels/<hotel_code>")
def hotel_detail(hotel_code: str):
    """
    Fiche hotel_data pour un code.

    Ne scrape pas : utiliser /context?fetch=1 si le code peut être absent.
    """
    h = _catalog.get_hotel(hotel_code)
    if not h:
        return jsonify({"error": "Hotel introuvable"}), 404
    return jsonify({"hotel": h})


@app.get("/api/hotels/<hotel_code>/context")
def hotel_context(hotel_code: str):
    """
    Contexte complet pour le wizard + simulateur.

    1. hotel_data + model_data si le code existe.
    2. Sinon scrape all.accor.com (par défaut **session only** : pas d'écriture
       dans hotel_data.xlsx). Passer ``persist=1`` pour forcer l'upsert (outils).
    """
    try:
        fetch = str(request.args.get("fetch") or "1").strip().lower() not in {
            "0",
            "false",
            "no",
        }
        # User app : ne jamais écrire en base par défaut
        persist = str(request.args.get("persist") or "0").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        ctx = _context.build(
            hotel_code,
            fetch_if_missing=fetch,
            persist_scrape=persist,
        )
        scrape_meta = (ctx.sources or {}).get("scrape") or {}
        if persist and scrape_meta.get("persisted"):
            _catalog.invalidate_hotels()
        payload = {
            "ok": True,
            **ctx.to_dict(),
            "payload": ctx.to_simulation_payload(),
            "scraped": bool(scrape_meta.get("scraped")),
            "session_only": bool(scrape_meta.get("session_only")),
            "persisted": bool(scrape_meta.get("persisted")),
        }
        return jsonify(payload)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/geocode")
def geocode():
    """
    Localise lat/lon : BAN (data.gouv) → fiche Accor (code/URL) → Nominatim.

    Body : street, postal_code, city, hotel_name, hotel_code, q / address / accor_url.
    Ex. hotel_code ``1545`` ou URL ``https://all.accor.com/hotel/1545/...``.
    """
    body = request.get_json(force=True, silent=True) or {}
    result = _geocoder.geocode(
        street=str(body.get("street") or body.get("hotel_adresse_postale_1") or ""),
        postal_code=str(body.get("postal_code") or body.get("hotel_code_postal") or ""),
        city=str(body.get("city") or body.get("hotel_city") or ""),
        free_text=str(body.get("q") or body.get("address") or body.get("accor_url") or ""),
        hotel_name=str(body.get("hotel_name") or ""),
        hotel_code=str(body.get("hotel_code") or ""),
        accor_url=str(body.get("accor_url") or body.get("url") or ""),
    )
    # 200 même en échec métier (l'UI lit ``ok``) — évite de confondre avec panne réseau
    return jsonify(result), 200


@app.post("/api/enrich")
def enrich():
    """
    Complète un SimulationRequest (coords, proximity, weather, holidays).

    Body = champs SimulationRequest (identity, operating, …).
    ``light: true`` saute Overpass et Meteostat (holidays restent calculés).
    """
    body = request.get_json(force=True, silent=True) or {}
    light = bool(body.get("light", False))
    try:
        req = SimulationRequest.from_dict(body)
        req = _enricher.enrich(
            req,
            do_proximity=not light,
            do_weather=not light,
            do_holidays=True,
        )
        return jsonify({"ok": True, "request": req.to_dict(), "enriched": req.enriched.to_dict()})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/simulate")
def simulate():
    """
    Simulation complète multi-concepts (revenus ROD + coûts + reco).

    Body JSON = ``SimulationRequest`` (identity, operating, services,
    client_profile, corner). Si ``hotel_code`` est fourni, les indicateurs
    manquants sont hydratés depuis hotel_data + model_data.

    Query ``?light=1`` saute Overpass/Meteostat (recommandé UI).
    """
    body = request.get_json(force=True, silent=True) or {}
    light = request.args.get("light") in {"1", "true", "yes"} or bool(
        body.get("light_enrich")
    )
    try:
        # Si seul hotel_code : hydrate 100 % depuis admin
        if body.get("hotel_code") and not body.get("identity") and not body.get("operating"):
            ctx = _context.build(str(body["hotel_code"]))
            body = {**ctx.to_simulation_payload(), **body}
        req = SimulationRequest.from_dict(body)
        result = _orchestrator.simulate_all(
            req, light_enrich=light, hydrate_from_admin=True
        )
        payload = result.to_dict()
        # Transparence : détail du calcul pour le concept recommandé
        reco = payload.get("recommended_concept")
        if reco and reco in payload.get("by_concept", {}):
            rev = payload["by_concept"][reco].get("revenue") or {}
            payload["calc_summary"] = {
                "recommended": reco,
                "clients_hotel": (rev.get("breakdown") or {}).get("clients_hotel"),
                "clients_pilote": (rev.get("breakdown") or {}).get("clients_pilote"),
                "client_factor": (rev.get("breakdown") or {}).get("client_factor"),
                "ca_ht_mensuel": rev.get("ca_ht_mensuel"),
                "ca_fb_mensuel": rev.get("ca_fb_mensuel"),
                "ca_nf_mensuel": rev.get("ca_nf_mensuel"),
                "historique": (payload.get("enriched") or {}).get("indicators") or {},
            }
        return jsonify({"ok": True, **payload})
    except Exception as exc:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc)}), 400


def main(argv: list[str] | None = None) -> None:
    """
    Point d'entrée serveur Flask user.

    Par défaut ``0.0.0.0`` (LAN + exposable publiquement).
    Override : ``--host 127.0.0.1`` ou env ``ACCOR_HOST`` / ``ACCOR_PORT``.
    """
    from accor.serve_utils import (
        default_host,
        default_port,
        print_listen_banner,
        run_flask_app,
    )

    parser = argparse.ArgumentParser(description="Accor ROD · User Simulator")
    parser.add_argument(
        "--host",
        default=default_host(),
        help="Adresse d'écoute (défaut 0.0.0.0 = toutes interfaces / réseau)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=default_port(5056),
        help="Port HTTP (défaut 5056, ou ACCOR_PORT)",
    )
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    print_listen_banner("Accor ROD · Simulateur directeur (user)", args.host, args.port)
    run_flask_app(app, host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
