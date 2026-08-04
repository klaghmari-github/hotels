/**
 * Simulation ROD + rendu resultats.
 */

import { $, escapeHtml } from "../../../shared/js/dom.js";
import { api } from "../../../shared/js/api.js";
import { toast } from "../../../shared/js/toast.js";
import { Format } from "../../../shared/js/format.js";

export class SimulationPanel {
  /**
   * @param {() => object} collectPayload
   */
  constructor(collectPayload) {
    this.collectPayload = collectPayload;
  }

  renderResults(data) {
    const reco = data.recommended_concept;
    const banner = $("#sim-reco");
    if (banner) {
      banner.classList.remove("hidden");
      banner.innerHTML =
        '<div class="tag">Recommandation</div><h2>' +
        escapeHtml(reco) +
        "</h2><p>" +
        escapeHtml(data.recommendation_reason || "") +
        "</p>";
    }

    const calc = $("#sim-calc");
    const ind = (data.enriched && data.enriched.indicators) || {};
    const sum = data.calc_summary || {};
    const recoRev =
      (data.by_concept &&
        data.by_concept[reco] &&
        data.by_concept[reco].revenue &&
        data.by_concept[reco].revenue.breakdown) ||
      {};
    const items = [
      ["Chambres", ind.nb_chambres != null ? ind.nb_chambres : recoRev.nb_chambres],
      [
        "TO",
        Format.pct(
          ind.taux_occupation != null ? ind.taux_occupation : recoRev.taux_occupation
        ),
      ],
      [
        "Guests/ch",
        ind.guests_per_chambre != null
          ? ind.guests_per_chambre
          : recoRev.guests_per_chambre,
      ],
      ["Clients / mois", Math.round(ind.clients_mois || recoRev.clients_hotel || 0)],
      ["Clients pilote", Math.round(recoRev.clients_pilote || 0)],
      [
        "Facteur clients (R1)",
        recoRev.client_factor != null
          ? Number(recoRev.client_factor).toFixed(3)
          : "—",
      ],
      ["CA pilote concept", Format.euro(recoRev.ca_ht_ref_pilote)],
      [
        "CA projeté / mois",
        Format.euro(
          sum.ca_ht_mensuel ||
            (data.by_concept && data.by_concept[reco]
              ? data.by_concept[reco].ca_mensuel
              : null)
        ),
      ],
      [
        "CA historique",
        ind.ca_historique_mensuel != null
          ? Format.euro(ind.ca_historique_mensuel)
          : "—",
      ],
      ["Mix F&B effectif", Format.pct(recoRev.mix_fb_effective)],
      ["m lin.", recoRev.m_lin],
    ];
    if (calc) {
      calc.classList.remove("hidden");
      calc.innerHTML =
        '<h2 class="card-title">Détail calcul revenus (ROD · ' +
        escapeHtml(reco || "") +
        ')</h2><div class="calc-grid">' +
        items
          .map(
            (pair) =>
              `<div class="calc-item"><span class="k">${escapeHtml(pair[0])}</span><span class="v">${escapeHtml(pair[1])}</span></div>`
          )
          .join("") +
        '</div><p class="hint" style="margin-top:.75rem">' +
        "Règle 1 = CA pilote × (clients hôtel / clients pilote). " +
        "Puis règles 2–4 (mix, catégories, m lin.) et impact TO." +
        "</p>";
    }

    const allowed = {};
    (data.allowed_concepts || []).forEach((c) => {
      allowed[c] = true;
    });
    const grid = $("#sim-cards");
    if (!grid) return;
    grid.innerHTML = "";
    ["SIMPLY", "LIBERTY", "CONNECTED"].forEach((name) => {
      const c = (data.by_concept || {})[name];
      if (!c) return;
      const isReco = name === reco;
      const isAllowed = !!allowed[name];
      const card = document.createElement("article");
      card.className = "concept-card" + (isReco ? " recommended" : "");
      const mn = Number(c.marge_nette_annuelle) || 0;
      card.innerHTML =
        "<h3>" +
        escapeHtml(name) +
        "</h3>" +
        (!isAllowed
          ? '<div class="blocked">Non autorisé par les règles reco</div>'
          : "") +
        '<div class="metric"><span class="metric-label">CA HT / mois</span><span class="v">' +
        Format.euro(c.ca_mensuel) +
        "</span></div>" +
        '<div class="metric"><span class="metric-label">CA HT / an</span><span class="v">' +
        Format.euro(c.ca_annuel) +
        "</span></div>" +
        '<div class="metric"><span class="metric-label">Marge produit / an</span><span class="v">' +
        Format.euro(c.marge_produit_annuelle) +
        "</span></div>" +
        '<div class="metric"><span class="metric-label">Coûts / an</span><span class="v">' +
        Format.euro(c.cout_annuel) +
        "</span></div>" +
        '<div class="metric"><span class="metric-label">Marge nette / an</span><span class="v ' +
        (mn >= 0 ? "pos" : "neg") +
        '">' +
        Format.euro(mn) +
        "</span></div>" +
        '<div class="metric"><span class="metric-label">Capex</span><span class="v">' +
        Format.euro(c.capex) +
        "</span></div>" +
        '<div class="metric"><span class="metric-label">ROI</span><span class="v">' +
        (c.roi_months != null ? Math.round(c.roi_months) + " mois" : "—") +
        "</span></div>" +
        '<div class="metric"><span class="metric-label">m lin.</span><span class="v">' +
        ((c.store && c.store.m_lin) || "—") +
        "</span></div>";
      grid.appendChild(card);
    });

    const en = data.enriched || {};
    const body = $("#enrich-body");
    const enrichItems = [];
    if (en.lat != null) enrichItems.push(["Latitude", en.lat]);
    if (en.lon != null) enrichItems.push(["Longitude", en.lon]);
    if (en.holidays) {
      enrichItems.push(["Zone scolaire", en.holidays.zone || "—"]);
      enrichItems.push([
        "% jours holidays",
        ((en.holidays.pct_jours_holidays || 0) * 100).toFixed(1) + " %",
      ]);
    }
    if (en.weather && en.weather.meteo_temperature_c_mean != null) {
      enrichItems.push([
        "Temp. moy.",
        Number(en.weather.meteo_temperature_c_mean).toFixed(1) + " °C",
      ]);
    }
    if (en.proximity) {
      const p = en.proximity;
      if (p.commerce_fb_500m != null)
        enrichItems.push(["F&B 500 m", p.commerce_fb_500m]);
      if (p.plage_distance_km != null)
        enrichItems.push([
          "Plage (km)",
          Number(p.plage_distance_km).toFixed(1),
        ]);
    }
    const simEnrich = $("#sim-enrich");
    if (enrichItems.length && body && simEnrich) {
      simEnrich.classList.remove("hidden");
      body.innerHTML = enrichItems
        .map(
          (pair) =>
            `<div class="enrich-item"><span class="k">${escapeHtml(pair[0])}</span><span class="v">${escapeHtml(pair[1])}</span></div>`
        )
        .join("");
    }

    const warns = data.warnings || [];
    const wbox = $("#sim-warnings");
    if (wbox) {
      if (warns.length) {
        wbox.classList.remove("hidden");
        wbox.innerHTML =
          '<div class="warn-list"><strong>Avertissements</strong><ul>' +
          warns.map((w) => "<li>" + escapeHtml(w) + "</li>").join("") +
          "</ul></div>";
      } else {
        wbox.classList.add("hidden");
      }
    }
  }

  async run() {
    const load = $("#sim-loading");
    const err = $("#sim-error");
    const btnSim = $("#btn-simulate");
    const btnNext = $("#btn-next");
    if (load) load.classList.remove("hidden");
    if (err) err.classList.add("hidden");
    const reco = $("#sim-reco");
    if (reco) reco.classList.add("hidden");
    const calc = $("#sim-calc");
    if (calc) calc.classList.add("hidden");
    const cards = $("#sim-cards");
    if (cards) cards.innerHTML = "";
    if (btnSim) {
      btnSim.disabled = true;
      btnSim.classList.add("busy");
    }
    if (btnNext) {
      btnNext.disabled = true;
      btnNext.classList.add("busy");
    }
    toast.show("Veuillez patienter — simulation en cours…");

    try {
      const payload = this.collectPayload();
      const data = await api.request("/api/simulate?light=1", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!data.ok) throw new Error(data.error || "Échec simulation");
      this.renderResults(data);
      toast.show("Simulation terminée");
    } catch (e) {
      if (err) {
        err.classList.remove("hidden");
        err.textContent = e.message || String(e);
      }
    } finally {
      if (load) load.classList.add("hidden");
      if (btnSim) {
        btnSim.disabled = false;
        btnSim.classList.remove("busy");
      }
      if (btnNext) {
        btnNext.disabled = false;
        btnNext.classList.remove("busy");
      }
    }
  }
}
