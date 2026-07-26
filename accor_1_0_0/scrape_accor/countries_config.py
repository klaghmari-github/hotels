#!/usr/bin/env python3
"""
Configuration des pays Accor (catalog API query + page destination).

Les queries ont été validées contre x-total-count + pays des résultats.
Attention : certaines queries trop larges (ex. « britain ») mélangent la France.
"""

from __future__ import annotations

from typing import Any

# slug → {label, query, dest_url?, expected_country_substr?}
# expected_country_substr : filtre optionnel si la query fuit un peu
COUNTRIES: dict[str, dict[str, Any]] = {
    # ── Europe ──────────────────────────────────────────────
    "france": {
        "label": "France",
        "query": "france",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-france-pfr.html",
    },
    "germany": {
        "label": "Allemagne",
        "query": "germany",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-germany-pde.html",
    },
    "united-kingdom": {
        "label": "Royaume-Uni",
        "query": "united kingdom",  # PAS "britain" (pollué FR)
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-united-kingdom-pgb.html",
    },
    "italy": {
        "label": "Italie",
        "query": "italy",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-italy-pit.html",
    },
    "spain": {
        "label": "Espagne",
        "query": "spain",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-spain-pes.html",
    },
    "portugal": {
        "label": "Portugal",
        "query": "portugal",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-portugal-ppt.html",
    },
    "belgium": {
        "label": "Belgique",
        "query": "belgium",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-belgium-pbe.html",
    },
    "netherlands": {
        "label": "Pays-Bas",
        "query": "netherlands",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-netherlands-pnl.html",
    },
    "switzerland": {
        "label": "Suisse",
        "query": "switzerland",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-switzerland-pch.html",
    },
    "austria": {
        "label": "Autriche",
        "query": "austria",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-austria-pat.html",
    },
    "poland": {
        "label": "Pologne",
        "query": "poland",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-poland-ppl.html",
    },
    "hungary": {
        "label": "Hongrie",
        "query": "hungary",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-hungary-phu.html",
    },
    "romania": {
        "label": "Roumanie",
        "query": "romania",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-romania-pro.html",
    },
    "czech-republic": {
        "label": "République tchèque",
        "query": "czech republic",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-czech-republic-pcz.html",
    },
    "greece": {
        "label": "Grèce",
        "query": "greece",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-greece-pgr.html",
    },
    "croatia": {
        "label": "Croatie",
        "query": "croatia",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-croatia-phr.html",
    },
    "albania": {
        "label": "Albanie",
        "query": "albania",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-albania-pal.html",
    },
    "bosnia": {
        "label": "Bosnie-Herzégovine",
        "query": "bosnia",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-bosnia-and-herzegovina-pba.html",
    },
    "bulgaria": {
        "label": "Bulgarie",
        "query": "bulgaria",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-bulgaria-pbg.html",
    },
    "cyprus": {
        "label": "Chypre",
        "query": "cyprus",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-cyprus-pcy.html",
    },
    "luxembourg": {
        "label": "Luxembourg",
        "query": "luxembourg",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-luxembourg-plu.html",
    },
    "monaco": {
        "label": "Monaco",
        "query": "monaco",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-monaco-pmc.html",
    },
    # Russie : catalog vide au moment du probe (0)
    "russia": {
        "label": "Russie",
        "query": "russia",
        "region": "europe",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-russia-pru.html",
    },
    # ── Afrique & Moyen-Orient ──────────────────────────────
    "algeria": {
        "label": "Algérie",
        "query": "algeria",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-algeria-pdz.html",
    },
    "morocco": {
        "label": "Maroc",
        "query": "maroc",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-morocco-pma.html",
    },
    "egypt": {
        "label": "Égypte",
        "query": "egypt",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-egypt-peg.html",
    },
    "tunisia": {
        "label": "Tunisie",
        "query": "tunisia",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-tunisia-ptn.html",
    },
    "senegal": {
        "label": "Sénégal",
        "query": "senegal",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-senegal-psn.html",
    },
    "ivory-coast": {
        "label": "Côte d'Ivoire",
        "query": "ivory coast",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-ivory-coast-pci.html",
    },
    "cameroon": {
        "label": "Cameroun",
        "query": "cameroon",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-cameroon-pcm.html",
    },
    "angola": {
        "label": "Angola",
        "query": "angola",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-angola-pao.html",
    },
    "nigeria": {
        "label": "Nigeria",
        "query": "nigeria",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-nigeria-png.html",
    },
    "south-africa": {
        "label": "Afrique du Sud",
        "query": "south africa",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-south-africa-pza.html",
    },
    "uae": {
        "label": "Émirats arabes unis",
        "query": "united arab emirates",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-united-arab-emirates-pae.html",
    },
    "saudi-arabia": {
        "label": "Arabie saoudite",
        "query": "saudi arabia",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-saudi-arabia-psa.html",
    },
    "qatar": {
        "label": "Qatar",
        "query": "qatar",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-qatar-pqa.html",
    },
    "kuwait": {
        "label": "Koweït",
        "query": "kuwait",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-kuwait-pkw.html",
    },
    "bahrain": {
        "label": "Bahreïn",
        "query": "bahrain",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-bahrain-pbh.html",
    },
    "jordan": {
        "label": "Jordanie",
        "query": "jordan",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-jordan-pjo.html",
    },
    "israel": {
        "label": "Israël",
        "query": "israel",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-israel-pil.html",
    },
    "turkey": {
        "label": "Turquie",
        "query": "turkey",
        "region": "africa_me",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-turkey-ptr.html",
    },
    # ── Asie ────────────────────────────────────────────────
    "china": {
        "label": "Chine",
        "query": "china",
        "region": "asia",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-china-pcn.html",
    },
    "hong-kong": {
        "label": "Hong Kong",
        "query": "hong kong",
        "region": "asia",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-hong-kong-phk.html",
    },
    "macau": {
        "label": "Macao",
        "query": "macau",
        "region": "asia",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-macau-pmo.html",
    },
    "india": {
        "label": "Inde",
        "query": "india",
        "region": "asia",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-india-pin.html",
    },
    "indonesia": {
        "label": "Indonésie",
        "query": "indonesia",
        "region": "asia",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-indonesia-pid.html",
    },
    "thailand": {
        "label": "Thaïlande",
        "query": "thailand",
        "region": "asia",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-thailand-pth.html",
    },
    "vietnam": {
        "label": "Vietnam",
        "query": "vietnam",
        "region": "asia",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-vietnam-pvn.html",
    },
    "singapore": {
        "label": "Singapour",
        "query": "singapore",
        "region": "asia",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-singapore-psg.html",
    },
    "malaysia": {
        "label": "Malaisie",
        "query": "malaysia",
        "region": "asia",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-malaysia-pmy.html",
    },
    "japan": {
        "label": "Japon",
        "query": "japan",
        "region": "asia",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-japan-pjp.html",
    },
    "south-korea": {
        "label": "Corée du Sud",
        "query": "south korea",
        "region": "asia",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-south-korea-pkr.html",
    },
    "philippines": {
        "label": "Philippines",
        "query": "philippines",
        "region": "asia",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-philippines-pph.html",
    },
    "cambodia": {
        "label": "Cambodge",
        "query": "cambodia",
        "region": "asia",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-cambodia-pkh.html",
    },
    "laos": {
        "label": "Laos",
        "query": "laos",
        "region": "asia",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-laos-pla.html",
    },
    "myanmar": {
        "label": "Myanmar",
        "query": "myanmar",
        "region": "asia",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-myanmar-pmm.html",
    },
    "mongolia": {
        "label": "Mongolie",
        "query": "mongolia",
        "region": "asia",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-mongolia-pmn.html",
    },
    "maldives": {
        "label": "Maldives",
        "query": "maldives",
        "region": "asia",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-maldives-pmv.html",
    },
    # ── Océanie ─────────────────────────────────────────────
    "australia": {
        "label": "Australie",
        "query": "australia",
        "region": "oceania",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-australia-pau.html",
    },
    "new-zealand": {
        "label": "Nouvelle-Zélande",
        "query": "new zealand",
        "region": "oceania",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-new-zealand-pnz.html",
    },
    "fiji": {
        "label": "Fidji",
        "query": "fiji",
        "region": "oceania",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-fiji-pfj.html",
    },
    "french-polynesia": {
        "label": "Polynésie française",
        "query": "french polynesia",
        "region": "oceania",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-french-polynesia-ppf.html",
    },
    # ── Amériques ───────────────────────────────────────────
    "united-states": {
        "label": "États-Unis",
        "query": "united states",
        "region": "americas",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-united-states-pus.html",
    },
    "canada": {
        "label": "Canada",
        "query": "canada",
        "region": "americas",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-canada-pca.html",
    },
    "mexico": {
        "label": "Mexique",
        "query": "mexico",
        "region": "americas",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-mexico-pmx.html",
    },
    "brazil": {
        "label": "Brésil",
        "query": "brazil",
        "region": "americas",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-brazil-pbr.html",
    },
    "argentina": {
        "label": "Argentine",
        "query": "argentina",
        "region": "americas",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-argentina-par.html",
    },
    "chile": {
        "label": "Chili",
        "query": "chile",
        "region": "americas",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-chile-pcl.html",
    },
    "colombia": {
        "label": "Colombie",
        "query": "colombia",
        "region": "americas",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-colombia-pco.html",
    },
    "peru": {
        "label": "Pérou",
        "query": "peru",
        "region": "americas",
        "dest_url": "https://all.accor.com/a/fr/destination/country/hotels-peru-ppe.html",
    },
}

# Tous les pays de la liste utilisateur
WORLD_SLUGS: tuple[str, ...] = tuple(COUNTRIES.keys())
