"""
Tables de paramètres figés du simulateur ROD (iso simulateur_rules.html).

Exposé à l'admin (onglet « Simulateur params ») — lecture seule.
Source unique pour l'UI : pilot_table + coûts Excel.
"""

from __future__ import annotations

from typing import Any

from archive.accor_1_0_6.pipelines.src.accor.user.rules.coeffs import CLIENT_NEED_LABELS
from archive.accor_1_0_6.pipelines.src.accor.user.rules.pilot_table import (
    AGENCEMENT_AMORT_MONTHS,
    AGENCEMENT_EUR_PER_ML,
    CAT_FB,
    CAT_NFB,
    JOURS_MOIS,
    PILOT,
)


def _round(v: Any, n: int = 4) -> Any:
    if isinstance(v, float):
        return round(v, n)
    return v


def build_sim_params() -> dict[str, Any]:
    """Payload JSON pour GET /api/rod/sim-params."""
    concepts = ("SIMPLY", "LIBERTY", "CONNECTED")

    # --- Pilotes (zone gauche Excel) ---
    pilot_rows = []
    for c in concepts:
        p = PILOT[c]
        pilot_rows.append(
            {
                "concept": c,
                "nb_chambres": p["nb_chambres"],
                "guests": p["guests"],
                "to": p["to"],
                "ml_ref": p.get("ml_ref"),
                "frigo_ref": p.get("frigo_ref"),
                "mix_fb": p["mix_fb"],
                "mix_nfb": round(1.0 - float(p["mix_fb"]), 4),
                "ventes_mois": p["ventes"],
                "ca_fb_ht": p["ca_fb"],
                "ca_nfb_ht": p["ca_nfb"],
                "ca_total_ht": round(float(p["ca_fb"]) + float(p["ca_nfb"]), 2),
                "clients_heb_pilote": round(float(p["clients_heb"]), 2),
                "coeff_fb": p["coeff_fb"],
                "coeff_nfb_simu": p["coeff_nfb"],
                "ca_10_fb": _round(p["ca_10_fb"], 3),
                "ca_10_nfb": _round(p["ca_10_nfb"], 3),
                "ca_1ml_fb": _round(p.get("ca_1ml_fb"), 3) if p.get("ca_1ml_fb") else None,
                "ca_1ml_nfb": _round(p.get("ca_1ml_nfb"), 3) if p.get("ca_1ml_nfb") else None,
                "ca_1frigo_fb": _round(p.get("ca_1frigo_fb"), 3)
                if p.get("ca_1frigo_fb")
                else None,
                "ca_1frigo_nfb": _round(p.get("ca_1frigo_nfb"), 3)
                if p.get("ca_1frigo_nfb")
                else None,
            }
        )

    # --- Marge produits ---
    margin_rows = []
    for c in concepts:
        p = PILOT[c]
        cfb, cnf = float(p["coeff_fb"]), float(p["coeff_nfb"])
        margin_rows.append(
            {
                "concept": c,
                "coeff_fb": cfb,
                "coeff_nfb": cnf,
                "marge_pct_fb": round((1.0 - 1.0 / cfb) * 100, 1),
                "marge_pct_nfb": round((1.0 - 1.0 / cnf) * 100, 1),
                "formule": "Marge = CA − CA/coeff  (= CA × (1 − 1/coeff))",
            }
        )
    # Note pilote Liberty/Connected hors simu
    margin_notes = [
        "Simulation : coeff N-F&B = 1,45 pour les 3 concepts.",
        "Zone pilote Excel : Liberty N-F&B = 2,0 · Connected N-F&B = 1,8 (hors simu défaut).",
    ]

    # --- R3 catégories ---
    cat_fb_rows = [
        {
            "id": k,
            "label": CLIENT_NEED_LABELS.get(k, k),
            "coeff": v,
            "effet_on": f"+{v:.0%}",
            "effet_off": f"−{v:.0%}",
        }
        for k, v in CAT_FB.items()
    ]
    cat_nfb_rows = [
        {
            "id": k,
            "label": CLIENT_NEED_LABELS.get(k, k),
            "coeff": v,
            "effet_on": f"+{v:.0%}",
            "effet_off": f"−{v:.0%}",
        }
        for k, v in CAT_NFB.items()
    ]

    # --- Coûts techno (BUY / LEASE) ---
    techno_rows = [
        {
            "element": "Équipement principal",
            "SIMPLY": "Scanner 500 € → 500/60 €/mois",
            "LIBERTY_BUY": "Caisse 15 000 × 0,80 = 12 000 → 200 €/mois",
            "LIBERTY_LEASE": "Caisse lease 250 €/mois",
            "CONNECTED_BUY": "Frigo froid 27 000 → 450 €/mois",
            "CONNECTED_LEASE": "Frigo froid lease 450 €/mois",
            "amort": "60 mois (BUY) ou mensuel (LEASE)",
        },
        {
            "element": "Vitrine",
            "SIMPLY": "800 € → 800/60 €/mois",
            "LIBERTY_BUY": "800 € → 800/60 €/mois",
            "LIBERTY_LEASE": "800 € → 800/60 €/mois",
            "CONNECTED_BUY": "—",
            "CONNECTED_LEASE": "—",
            "amort": "60 mois",
        },
        {
            "element": "Frigo ambiant",
            "SIMPLY": "—",
            "LIBERTY_BUY": "—",
            "LIBERTY_LEASE": "—",
            "CONNECTED_BUY": "24 000 € → 400 €/mois (si N-F&B ≥ 10 %)",
            "CONNECTED_LEASE": "24 000 € → 400 €/mois (si N-F&B ≥ 10 %)",
            "amort": "60 mois",
        },
        {
            "element": "Licence logicielle",
            "SIMPLY": "50 €/mois (capex ref. 3 000 €)",
            "LIBERTY_BUY": "50 €/mois",
            "LIBERTY_LEASE": "50 €/mois",
            "CONNECTED_BUY": "inclus / —",
            "CONNECTED_LEASE": "inclus / —",
            "amort": "mensuel",
        },
        {
            "element": "Frais OS",
            "SIMPLY": "1 000 € → 1 000/60 €/mois",
            "LIBERTY_BUY": "2 000 € → 2 000/60 €/mois",
            "LIBERTY_LEASE": "2 000 € → 2 000/60 €/mois",
            "CONNECTED_BUY": "3 000 € → 3 000/60 €/mois",
            "CONNECTED_LEASE": "3 000 € → 3 000/60 €/mois",
            "amort": "60 mois",
        },
    ]

    annexes_rows = [
        {
            "element": "Élec. équipement principal",
            "SIMPLY": "2 €/mois · scanner",
            "LIBERTY": "10 €/mois · caisse",
            "CONNECTED": "20 €/mois · frigo froid",
        },
        {
            "element": "Élec. vitrine / frigo amb.",
            "SIMPLY": "10 €/mois · vitrine",
            "LIBERTY": "10 €/mois · vitrine",
            "CONNECTED": "15 €/mois · frigo ambiant",
        },
        {
            "element": "Staff",
            "SIMPLY": "3 €/mois",
            "LIBERTY": "10 €/mois",
            "CONNECTED": "10 €/mois",
        },
    ]

    agencement_rows = []
    for kind in ("CLASSIC", "PREMIUM", "BESPOKE"):
        agencement_rows.append(
            {
                "type": kind.title(),
                "simply_liberty_eur_ml": AGENCEMENT_EUR_PER_ML["SIMPLY"][kind],
                "connected_eur_ml": AGENCEMENT_EUR_PER_ML["CONNECTED"][kind],
                "amort_months": AGENCEMENT_AMORT_MONTHS,
                "formule": f"(€/ML × nb_ML) / {int(AGENCEMENT_AMORT_MONTHS)}",
            }
        )

    # --- Amortissement / marge nette ---
    net_rules = {
        "marge_produits": "Marge_FB + Marge_NFB avec Marge = CA − CA/coeff",
        "marge_nette": "Marge_produits − Coûts_mensuels (techno + annexes + agencement)",
        "not_profitable": "Si marge nette < 0 ou CA < 0 → « Not profitable »",
        "taux_marge": "Marge_nette / CA_HT (si profitable)",
        "amortissement": (
            "cout_total_60_mois / Marge_nette "
            "(capex one-shot + 60 × (licence + annexes + agencement + leases))"
        ),
        "jours_mois": JOURS_MOIS,
    }

    # --- Ordre d'exécution ---
    order = [
        "1. Lire paramètres hôtel (chambres, guests, TO, ML, mix, catégories, équipements, contrat, agencement)",
        "2. Arbre de recommandation → solution mise en avant",
        "3. Pour chaque solution : R1 clients → R2 mix ±10 % → R3 catégories ±coeff → R4 ML/frigos",
        "4. Marge produits (2,6 / 1,45)",
        "5. Coûts techno + annexes + agencement",
        "6. Marge nette + amortissement (ou Not profitable)",
        "7. Affichage reco en premier · P&L des 3 solutions",
    ]

    reco_tree = [
        {"si": "nb_chambres ≤ 49", "alors": "SIMPLY"},
        {
            "si": "≥ 1 catégorie lifestyle N-F&B (cosmétiques, kids, PAP, accessoires, souvenirs)",
            "alors": "LIBERTY",
        },
        {"si": "mètres linéaires > 4", "alors": "LIBERTY"},
        {"si": "vitrine / frigo lobby présent", "alors": "LIBERTY"},
        {"si": "TO moyen < 0,70", "alors": "LIBERTY"},
        {"si": "sinon", "alors": "CONNECTED"},
    ]

    r_formulas = {
        "R1": (
            "clients = ch × guests × TO × 30,5 ; "
            "taux = ventes_pilote / clients_heb_pilote ; "
            "CA = (CA_pilote / ventes) × (clients × taux)"
        ),
        "R2": (
            "diff_FB = mix_user − mix_ref ; "
            "CA_FB += CA_10_FB × (diff × 10) ; "
            "CA_NFB += CA_10_NFB × (−diff × 10)"
        ),
        "R3": "mult = 1 + Σ(±coeff) ; CA × mult (séparé F&B / N-F&B)",
        "R4_simply_liberty": "CA ± CA_1ML × (ML − ML_ref)",
        "R4_connected": "CA ± CA_1frigo × (nb_frigos_froid − 3)",
    }

    guards = [
        "Minimum 2 mètres linéaires",
        "Mix F&B continu 0–100 % (pas de pas imposé 10 %)",
        "Toutes catégories OFF → CA forcé 0 / message",
        "Frigo froid Connected compté si mix F&B ≥ 10 %",
        "Frigo ambiant si mix N-F&B ≥ 10 %",
        "Min. 1 vitrine Simply/Liberty (sauf déjà en place)",
        "Reco = arbre métier, pas max CA",
        "Amortissement sur marge nette, pas sur CA",
    ]

    return {
        "ok": True,
        "source": "simulateur_rules.html + pilot_table.py + costs.py",
        "sections": [
            {
                "id": "pilots",
                "title": "Chiffres de référence pilotes",
                "description": "Zone gauche Excel — base Règle 1 (ventes, CA, mix, ML / frigos).",
                "columns": [
                    ("concept", "Concept"),
                    ("nb_chambres", "Ch. réf."),
                    ("guests", "Guests/ch"),
                    ("to", "TO"),
                    ("ml_ref", "ML réf."),
                    ("frigo_ref", "Frigos réf."),
                    ("mix_fb", "Mix F&B"),
                    ("mix_nfb", "Mix N-F&B"),
                    ("ventes_mois", "Ventes / mois"),
                    ("ca_fb_ht", "CA F&B HT"),
                    ("ca_nfb_ht", "CA N-F&B HT"),
                    ("ca_total_ht", "CA total HT"),
                    ("clients_heb_pilote", "Clients héb. pilote"),
                    ("ca_10_fb", "CA +10 % F&B"),
                    ("ca_10_nfb", "CA +10 % N-F&B"),
                    ("ca_1ml_fb", "CA / ML F&B"),
                    ("ca_1ml_nfb", "CA / ML N-F&B"),
                    ("ca_1frigo_fb", "CA / frigo F&B"),
                    ("ca_1frigo_nfb", "CA / frigo N-F&B"),
                ],
                "rows": pilot_rows,
            },
            {
                "id": "margins",
                "title": "Règles de marge produits",
                "description": "Hypothèses business PV/PR — simulation.",
                "notes": margin_notes,
                "columns": [
                    ("concept", "Concept"),
                    ("coeff_fb", "Coeff F&B"),
                    ("coeff_nfb", "Coeff N-F&B (simu)"),
                    ("marge_pct_fb", "Marge % F&B"),
                    ("marge_pct_nfb", "Marge % N-F&B"),
                    ("formule", "Formule"),
                ],
                "rows": margin_rows,
            },
            {
                "id": "cat_fb",
                "title": "Règle 3 — Catégories F&B (± coeff)",
                "description": "ON → +coeff · OFF → −coeff · cumuls additifs · mult = 1 + Σ±.",
                "columns": [
                    ("label", "Catégorie"),
                    ("id", "Clé"),
                    ("coeff", "Coeff"),
                    ("effet_on", "Si ON"),
                    ("effet_off", "Si OFF"),
                ],
                "rows": cat_fb_rows,
                "footer": f"Cumul max si toutes ON = {sum(CAT_FB.values()):.2f}",
            },
            {
                "id": "cat_nfb",
                "title": "Règle 3 — Catégories N-F&B (± coeff)",
                "description": "Même logique · 5 lifestyle servent aussi l’arbre de reco.",
                "columns": [
                    ("label", "Catégorie"),
                    ("id", "Clé"),
                    ("coeff", "Coeff"),
                    ("effet_on", "Si ON"),
                    ("effet_off", "Si OFF"),
                ],
                "rows": cat_nfb_rows,
                "footer": f"Cumul max si toutes ON = {sum(CAT_NFB.values()):.2f}",
            },
            {
                "id": "techno",
                "title": "Coûts techno — Achat (BUY) vs Location (LEASE)",
                "description": "Mensualisation BUY = prix / 60 mois.",
                "columns": [
                    ("element", "Élément"),
                    ("SIMPLY", "Simply"),
                    ("LIBERTY_BUY", "Liberty BUY"),
                    ("LIBERTY_LEASE", "Liberty LEASE"),
                    ("CONNECTED_BUY", "Connected BUY"),
                    ("CONNECTED_LEASE", "Connected LEASE"),
                    ("amort", "Amort."),
                ],
                "rows": techno_rows,
            },
            {
                "id": "annexes",
                "title": "Coûts annexes (élec. + staff)",
                "description": "Proportionnels au nombre d’équipements.",
                "columns": [
                    ("element", "Élément"),
                    ("SIMPLY", "Simply"),
                    ("LIBERTY", "Liberty"),
                    ("CONNECTED", "Connected"),
                ],
                "rows": annexes_rows,
            },
            {
                "id": "agencement",
                "title": "Coûts agencement (€ / ML)",
                "description": f"Amortis sur {int(AGENCEMENT_AMORT_MONTHS)} mois.",
                "columns": [
                    ("type", "Type"),
                    ("simply_liberty_eur_ml", "Simply / Liberty €/ML"),
                    ("connected_eur_ml", "Connected €/ML"),
                    ("amort_months", "Amort. mois"),
                    ("formule", "Formule mensuelle"),
                ],
                "rows": agencement_rows,
            },
            {
                "id": "reco",
                "title": "Arbre de recommandation",
                "description": "Première condition vraie gagne · ≠ max CA.",
                "columns": [("si", "Condition"), ("alors", "Reco")],
                "rows": reco_tree,
            },
        ],
        "formulas": r_formulas,
        "net_rules": net_rules,
        "order": order,
        "guards": guards,
    }
