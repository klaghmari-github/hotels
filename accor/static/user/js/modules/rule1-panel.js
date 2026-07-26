/**
 * Derive clients + CA Regle 1.
 */

import { $, debounce } from "../../../shared/js/dom.js";
import { api } from "../../../shared/js/api.js";
import { Format } from "../../../shared/js/format.js";

export class Rule1Panel {
  constructor() {
    this._fetch = debounce((n, to, g) => this._doFetch(n, to, g), 200);
  }

  updateDerived() {
    const nEl = $("#nb_chambres");
    const toEl = $("#taux_occupation");
    const gEl = $("#guests_per_chambre");
    const outJ = $("#out-clients-jour");
    const outM = $("#out-clients-mois");
    const formula = $("#clients-formula");

    let n = nEl ? parseFloat(nEl.value) : 80;
    if (!Number.isFinite(n) || n < 0) n = 0;
    const to = Format.toRate(toEl ? toEl.value : 65);
    let g = gEl ? parseFloat(gEl.value) : 1.7;
    if (!Number.isFinite(g) || g < 0) g = 0;

    const jour = n * to * g;
    const mois = jour * 30.5;
    const fmt = (x) =>
      Format.locale(x, { maximumFractionDigits: 1, minimumFractionDigits: 0 });

    if (outJ) outJ.textContent = fmt(jour);
    if (outM) outM.textContent = fmt(mois);
    if (formula) {
      const toPct = Math.round(to * 1000) / 10;
      formula.innerHTML =
        `<div>${n} ch × ${toPct} % TO × ${g} guests/ch = <strong>${fmt(jour)} clients/jour</strong></div>` +
        `<div>${fmt(jour)} clients/jour × 30,5 = <strong>${fmt(mois)} clients/mois</strong></div>`;
    }
    this._fetch(n, to, g);
  }

  async _doFetch(n, to, g) {
    try {
      const data = await api.post("/api/rule1", {
        nb_chambres: n,
        taux_occupation: to,
        guests_per_chambre: g,
      });
      this.render(data);
    } catch (e) {
      console.error("[ROD] rule1", e);
      this.render(null);
    }
  }

  render(data) {
    const detail = $("#rule1-detail");
    const meta = $("#rule1-meta");
    if (!data || !data.ok || !data.by_concept) {
      ["SIMPLY", "LIBERTY", "CONNECTED"].forEach((c) => {
        const caEl = $("#r1-ca-" + c);
        const subEl = $("#r1-sub-" + c);
        if (caEl) caEl.textContent = "—";
        if (subEl) subEl.textContent = "";
        const card = document.querySelector(`.rule1-card[data-concept="${c}"]`);
        if (card) card.classList.remove("best");
      });
      if (detail) detail.textContent = "";
      return;
    }

    if (meta) {
      meta.textContent =
        "Vos clients / mois : " +
        Format.locale(data.clients_mois, { maximumFractionDigits: 1 }) +
        " — CA = (CA pilote + impact TO) × (clients hôtel ÷ clients pilote)";
    }

    let best = null;
    let bestCa = -Infinity;
    ["SIMPLY", "LIBERTY", "CONNECTED"].forEach((c) => {
      const row = data.by_concept[c] || {};
      const ca = Number(row.ca_ht_mensuel);
      if (Number.isFinite(ca) && ca > bestCa) {
        bestCa = ca;
        best = c;
      }
      const caEl = $("#r1-ca-" + c);
      const subEl = $("#r1-sub-" + c);
      if (caEl) caEl.textContent = Number.isFinite(ca) ? Format.euro(ca) : "—";
      if (subEl) {
        subEl.innerHTML =
          "pilote " +
          Format.euro(row.ca_ht_pilote) +
          "<br>facteur ×" +
          (row.client_factor != null ? Number(row.client_factor).toFixed(2) : "—");
      }
      const card = document.querySelector(`.rule1-card[data-concept="${c}"]`);
      if (card) card.classList.toggle("best", c === best);
    });

    if (detail && best) {
      const b = data.by_concept[best];
      detail.textContent =
        "Meilleur CA Règle 1 : " +
        best +
        " (" +
        Format.euro(b.ca_ht_mensuel) +
        "/mois) — clients pilote " +
        Format.locale(b.clients_pilote, { maximumFractionDigits: 0 }) +
        ", facteur " +
        Number(b.client_factor).toFixed(3) +
        ". (R2 mix, R3 catégories et R4 m lin. viennent ensuite.)";
    }
  }
}
