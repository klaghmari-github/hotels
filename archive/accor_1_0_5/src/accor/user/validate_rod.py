"""
Validation rapide du moteur ROD (iso simulateur_rules.html).

Usage :
  PYTHONPATH=src python -m accor.user.validate_rod
"""

from __future__ import annotations

from archive.accor_1_0_5.src.accor.user.models import (
    DEFAULT_CLIENT_NEEDS,
    ClientProfile,
    HotelIdentity,
    HotelOperating,
    HotelServices,
    SimulationRequest,
    StoreConfig,
)
from archive.accor_1_0_5.src.accor.user.rules.costs import CostRules
from archive.accor_1_0_5.src.accor.user.rules.pilot_table import get_pilot
from archive.accor_1_0_5.src.accor.user.rules.recommendation import RecommendationRules
from archive.accor_1_0_5.src.accor.user.rules.revenue import RevenueRules
from archive.accor_1_0_5.src.accor.user.services.simulator import RodSimulator


def _all_on() -> dict[str, bool]:
    return {k: True for k in DEFAULT_CLIENT_NEEDS}


def _req(
    concept: str,
    *,
    rooms: int = 100,
    to: float = 0.75,
    guests: float = 1.5,
    m_lin: float = 6.0,
    mix: float = 0.7,
    needs: dict[str, bool] | None = None,
    frigos: int = 3,
    contract: str = "BUY",
    agencement: str = "CLASSIC",
    vitrine: bool = False,
) -> SimulationRequest:
    return SimulationRequest(
        identity=HotelIdentity(
            hotel_code="VAL001", hotel_name="Validation", hotel_brand="IBIS"
        ),
        operating=HotelOperating(
            nb_chambres=rooms, taux_occupation=to, guests_per_chambre=guests
        ),
        services=HotelServices(lobby_fridge=vitrine),
        client_profile=ClientProfile(client_needs=needs or _all_on()),
        store=StoreConfig(
            concept=concept,
            m_lin=m_lin,
            mix_fb=mix,
            mix_nf=1.0 - mix,
            nb_frigos_froid=frigos,
            nb_frigos_ambiant=0,
            nb_scanners=1,
            nb_caisses=1,
            nb_vitrines=1,
            contract=contract,
            agencement=agencement,
        ),
    )


def run_checks() -> list[str]:
    errors: list[str] = []
    rev = RevenueRules()
    cost = CostRules()
    sim = RodSimulator(rev, cost)
    reco = RecommendationRules()

    def check(cond: bool, msg: str) -> None:
        if not cond:
            errors.append(msg)

    # Pilotes
    p = get_pilot("SIMPLY")
    check(abs(p["clients_heb"] - 5350.92) < 0.01, "clients_heb Simply")
    check(p["ca_10_fb"] == 133.25, "ca_10_fb Simply")
    check(p["coeff_nfb"] == 1.45, "coeff_nfb simu = 1.45")

    # R1 à l'échelle pilote
    r = rev.compute(
        _req("SIMPLY", rooms=129, to=0.80, guests=1.7, m_lin=6, mix=0.40),
        "SIMPLY",
    )
    check(abs(r.breakdown["ca_r1_fb"] - 533) < 1, f"R1 FB={r.breakdown['ca_r1_fb']}")
    check(abs(r.breakdown["ca_r1_nfb"] - 187) < 1, f"R1 NFB={r.breakdown['ca_r1_nfb']}")
    check(abs(r.breakdown["mult_rule3_fb"] - 1.48) < 0.001, "R3 mult FB all ON")
    check(abs(r.breakdown["mult_rule3_nfb"] - 1.33) < 0.001, "R3 mult NFB all ON")

    # R2 +10 % F&B
    r2 = rev.compute(
        _req("SIMPLY", rooms=129, to=0.8, guests=1.7, m_lin=6, mix=0.50),
        "SIMPLY",
    )
    check(abs(r2.breakdown["ca_r2_fb"] - 666.25) < 0.5, "R2 +10% FB")
    check(abs(r2.breakdown["ca_r2_nfb"] - 155.83) < 0.5, "R2 -10% NFB")

    # R4 ML
    r4 = rev.compute(
        _req("SIMPLY", rooms=129, to=0.8, guests=1.7, m_lin=4, mix=0.4),
        "SIMPLY",
    )
    exp_fb = 533 * 1.48 - 2 * 88.83
    check(abs(r4.ca_fb_mensuel - exp_fb) < 0.5, f"R4 FB got {r4.ca_fb_mensuel}")

    # Connected frigos
    rc = rev.compute(
        _req(
            "CONNECTED",
            rooms=305,
            to=0.75,
            guests=1.8,
            m_lin=7,
            mix=0.80,
            frigos=3,
        ),
        "CONNECTED",
    )
    check(rc.breakdown["r4_mode"] == "frigos_froid", "R4 Connected mode")
    check(abs(rc.breakdown["ca_r1_fb"] - 3503) < 2, "Connected R1")

    # Coûts
    cs = cost.compute(
        _req("SIMPLY", rooms=129, to=0.8, guests=1.7, m_lin=6, mix=0.4),
        "SIMPLY",
    )
    check(abs(cs.annexes_monthly - 15) < 0.05, f"annexes Simply={cs.annexes_monthly}")
    check(
        abs(cs.techno_monthly - (500 / 60 + 800 / 60 + 50 + 1000 / 60)) < 0.05,
        "techno Simply",
    )

    cl = cost.compute(
        _req("LIBERTY", rooms=100, m_lin=8, mix=0.7, contract="LEASE"),
        "LIBERTY",
    )
    check(
        abs(cl.techno_monthly - (250 + 800 / 60 + 50 + 2000 / 60)) < 0.1,
        "Liberty LEASE techno",
    )

    # Full + amort
    full = sim.simulate(
        _req("SIMPLY", rooms=129, to=0.8, guests=1.7, m_lin=6, mix=0.4),
        "SIMPLY",
    )
    check(full.status in ("ok", "not_profitable"), "status")
    if full.marge_nette_mensuelle > 0:
        check(full.amort_months is not None, "amort set when profitable")

    # Reco
    rec, _, _ = reco.recommend_tree(
        _req("SIMPLY", rooms=40), m_lin=3, to=0.8
    )
    check(rec == "SIMPLY", f"reco 40ch={rec}")

    needs_no_life = _all_on()
    for k in (
        "nfb_cosmetics",
        "nfb_kids",
        "nfb_apparel",
        "nfb_accessories",
        "nfb_souvenirs",
    ):
        needs_no_life[k] = False
    rec, _, _ = reco.recommend_tree(
        _req("CONNECTED", rooms=100, needs=needs_no_life), m_lin=3, to=0.75
    )
    check(rec == "CONNECTED", f"reco connected path={rec}")

    return errors


def main() -> int:
    errs = run_checks()
    if errs:
        print("FAILED:")
        for e in errs:
            print(" -", e)
        return 1
    print("validate_rod: OK — moteur fidèle à simulateur_rules.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
