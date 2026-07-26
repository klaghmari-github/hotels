/**
 * Zone admin Simulateur ROD.
 *
 * Onglets :
 *   1. Prédiction ventes — étapes R0–R4 + marge produit
 *   2. Marge & coûts — SIMPLY / LIBERTY / CONNECTED
 *   3. Évaluation — CA sim vs réel (Σ mois / 12) sur les pilotes
 *
 * API : /api/rod/pilots, /api/rod/hotel/<code>/trace, /api/rod/eval
 */

import { $, $$, escapeHtml } from "../../shared/js/dom.js";
import { api } from "../../shared/js/api.js";
import { toast } from "../../shared/js/toast.js";

function fmt(v, d = 2) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("fr-FR", {
    maximumFractionDigits: d,
    minimumFractionDigits: 0,
  });
}

function euro(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return (
    Number(v).toLocaleString("fr-FR", {
      maximumFractionDigits: 0,
      minimumFractionDigits: 0,
    }) + " €"
  );
}

export class RodSimPanel {
  /**
   * @param {import('./state.js').AdminState} state
   * @param {import('./nav-controller.js').NavController} nav
   */
  constructor(state, nav) {
    this.state = state;
    this.nav = nav;
    this.pilots = null;
    this.trace = null;
    this.evalResult = null;
    this.concept = "SIMPLY";
    this.tab = "ventes";
  }

  async open() {
    if (!this.state.confirmLeaveDirty()) return;
    this.nav.showRodSimPanel();
    await this.loadPilots();
  }

  year() {
    return Number($("#rod-year")?.value || 2026);
  }

  async loadPilots() {
    const status = $("#rod-status");
    if (status) status.textContent = "Chargement pilotes…";
    try {
      const year = this.year();
      const data = await api.get("/api/rod/pilots", { year });
      this.pilots = data;
      const chipY = $("#rod-chip-year");
      if (chipY) chipY.textContent = `Année : ${data.year || year}`;
      const chipN = $("#rod-chip-n");
      if (chipN) {
        chipN.textContent = `${data.n || 0} hôtel(s) pilote(s)`;
      }
      this.fillHotels(data.hotels || []);
      if (status) status.textContent = "";
    } catch (err) {
      if (status) status.textContent = err.message;
      toast.show(err.message, "err");
    }
  }

  fillHotels(hotels) {
    const sel = $("#rod-hotel-select");
    if (!sel) return;
    const prev = sel.value;
    sel.innerHTML = "";
    if (!hotels.length) {
      sel.innerHTML = `<option value="">— aucun pilote —</option>`;
      return;
    }
    hotels.forEach((h) => {
      const opt = document.createElement("option");
      opt.value = h.hotel_code;
      opt.textContent = `${h.hotel_code} · ${h.hotel_name || "—"} · ${h.n_months} mois`;
      sel.appendChild(opt);
    });
    if (prev && hotels.some((h) => h.hotel_code === prev)) sel.value = prev;
    this.renderHotelMeta();
  }

  renderHotelMeta() {
    const host = $("#rod-hotel-meta");
    if (!host || !this.pilots) return;
    const code = $("#rod-hotel-select")?.value;
    const h = (this.pilots.hotels || []).find((x) => x.hotel_code === code);
    if (!h) {
      host.className = "metrics-grid empty";
      host.textContent = "—";
      return;
    }
    host.className = "metrics-grid";
    host.innerHTML = `
      <div class="metric-box"><span class="m-label">Marque</span><span class="m-value">${escapeHtml(h.hotel_brand || "—")}</span></div>
      <div class="metric-box"><span class="m-label">Mois ${this.year()}</span><span class="m-value">${escapeHtml((h.months || []).join(", "))}</span></div>
      <div class="metric-box"><span class="m-label">Σ réel</span><span class="m-value">${euro(h.sum_montant_ventes)}</span></div>
      <div class="metric-box good"><span class="m-label">Moy. mens. réelle (Σ/12)</span><span class="m-value">${euro(h.avg_monthly_true)}</span></div>
    `;
  }

  setTab(tab) {
    this.tab = tab;
    $$(".rod-tab").forEach((el) => {
      el.classList.toggle("active", el.dataset.rodTab === tab);
    });
    $$(".rod-panel").forEach((el) => {
      el.classList.toggle("hidden", el.dataset.rodPanel !== tab);
    });
    // concept card utile pour ventes/marge
    const cc = $("#rod-concept-card");
    if (cc) cc.classList.toggle("hidden", tab === "eval");
  }

  setConcept(c) {
    this.concept = c;
    $$(".rod-concept").forEach((el) => {
      el.classList.toggle("active", el.dataset.concept === c);
    });
    this.renderTrace();
  }

  async run() {
    const status = $("#rod-status");
    const btn = $("#btn-rod-run");
    const code = $("#rod-hotel-select")?.value;
    const year = this.year();

    if (btn) btn.disabled = true;
    if (status) status.textContent = "Calcul ROD…";

    try {
      // always refresh pilots meta for year
      await this.loadPilots();

      if (this.tab === "eval") {
        const data = await api.get("/api/rod/eval", { year });
        if (!data.ok) throw new Error(data.error || "Éval ROD échouée");
        this.evalResult = data;
        this.renderEval(data);
        if (status) status.textContent = `Éval · ${data.n_hotels} hôtels`;
        toast.show(`Évaluation ROD ${year} · ${data.n_hotels} hôtels`);
      } else {
        if (!code) throw new Error("Choisissez un hôtel pilote");
        const data = await api.get(
          `/api/rod/hotel/${encodeURIComponent(code)}/trace`,
          { year }
        );
        if (!data.ok) throw new Error(data.error || "Trace échouée");
        this.trace = data;
        this.renderTrace();
        if (status) status.textContent = `OK · ${code}`;
        toast.show(`Trace ROD · ${code}`);
      }
    } catch (err) {
      if (status) status.textContent = err.message;
      toast.show(err.message, "err");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  renderTrace() {
    if (!this.trace) return;
    const c = this.concept;
    const block = this.trace.by_concept?.[c];
    const kpi = $("#rod-concept-kpi");

    if (!block || block.error) {
      if (kpi) {
        kpi.className = "metrics-grid empty";
        kpi.textContent = block?.error || "Pas de données";
      }
      const steps = $("#rod-sales-steps");
      if (steps) {
        steps.className = "rod-steps empty";
        steps.textContent = block?.error || "—";
      }
      return;
    }

    const sales = block.sales || {};
    const margin = block.margin || {};
    const costs = block.costs || {};

    if (kpi) {
      kpi.className = "metrics-grid";
      kpi.innerHTML = `
        <div class="metric-box good"><span class="m-label">CA HT / mois</span><span class="m-value">${euro(sales.ca_ht_mensuel)}</span></div>
        <div class="metric-box"><span class="m-label">Marge produit</span><span class="m-value">${euro(margin.marge_produit_mensuelle)}</span></div>
        <div class="metric-box"><span class="m-label">Coûts / mois</span><span class="m-value">${euro(costs.monthly_cost)}</span></div>
        <div class="metric-box good"><span class="m-label">Marge nette / mois</span><span class="m-value">${euro(margin.marge_nette_mensuelle)}</span></div>
      `;
    }

    this.renderSalesSteps(sales.steps || []);
    this.renderMarginAll();
    this.renderCostLines(costs.cost_lines || []);
  }

  renderSalesSteps(steps) {
    const host = $("#rod-sales-steps");
    if (!host) return;
    if (!steps.length) {
      host.className = "rod-steps empty";
      host.textContent = "Aucune étape.";
      return;
    }
    host.className = "rod-steps";
    host.innerHTML = steps
      .map((s, i) => {
        const vals = s.values || {};
        const keys = Object.keys(vals);
        const grid = keys
          .map(
            (k) =>
              `<div class="rod-kv"><span>${escapeHtml(k)}</span><strong>${escapeHtml(
                String(vals[k] ?? "—")
              )}</strong></div>`
          )
          .join("");
        return `
        <article class="rod-step">
          <header>
            <span class="rod-step-n">${i + 1}</span>
            <div>
              <h3>${escapeHtml(s.title || s.id)}</h3>
              <p class="rod-rule">${escapeHtml(s.rule || "")}</p>
            </div>
            <div class="rod-step-ca">
              <span class="muted">CA HT</span>
              <strong>${euro(s.ca_ht)}</strong>
            </div>
          </header>
          <p class="rod-formula">${escapeHtml(s.formula || "")}</p>
          <div class="rod-kv-grid">${grid}</div>
          <div class="rod-step-split">
            <span>F&amp;B ${euro(s.ca_fb)}</span>
            <span>N-F&amp;B ${euro(s.ca_nf)}</span>
          </div>
        </article>`;
      })
      .join("");
  }

  renderMarginAll() {
    const host = $("#rod-margin-table");
    if (!host || !this.trace) return;
    const by = this.trace.by_concept || {};
    const concepts = ["SIMPLY", "LIBERTY", "CONNECTED"];
    host.className = "perf-table-wrap";
    host.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Concept</th>
            <th>CA HT / mois</th>
            <th>Marge produit</th>
            <th>Techno</th>
            <th>Annexes</th>
            <th>Agencement</th>
            <th>Coût total</th>
            <th>Marge nette</th>
            <th>Capex</th>
          </tr>
        </thead>
        <tbody>
          ${concepts
            .map((c) => {
              const b = by[c] || {};
              const s = b.sales || {};
              const m = b.margin || {};
              const co = b.costs || {};
              const active = c === this.concept ? "is-best" : "";
              return `<tr class="${active}">
                <td><strong>${c}</strong></td>
                <td>${euro(s.ca_ht_mensuel)}</td>
                <td>${euro(m.marge_produit_mensuelle)}</td>
                <td>${euro(co.techno_monthly)}</td>
                <td>${euro(co.annexes_monthly)}</td>
                <td>${euro(co.agencement_monthly)}</td>
                <td>${euro(co.monthly_cost)}</td>
                <td>${euro(m.marge_nette_mensuelle)}</td>
                <td>${euro(co.capex)}</td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>`;
  }

  renderCostLines(lines) {
    const host = $("#rod-cost-lines");
    if (!host) return;
    if (!lines.length) {
      host.className = "perf-table-wrap empty";
      host.textContent = "Aucune ligne de coût.";
      return;
    }
    host.className = "perf-table-wrap";
    host.innerHTML = `
      <table>
        <thead>
          <tr><th>Id</th><th>Libellé</th><th>Groupe</th><th>Qté</th><th>Mensuel</th><th>Capex</th></tr>
        </thead>
        <tbody>
          ${lines
            .map(
              (l) => `<tr>
              <td>${escapeHtml(l.id || "")}</td>
              <td>${escapeHtml(l.label || "")}</td>
              <td>${escapeHtml(l.group || "")}</td>
              <td>${fmt(l.qty, 2)}</td>
              <td>${euro(l.monthly)}</td>
              <td>${euro(l.capex)}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  }

  renderEval(data) {
    const method = $("#rod-eval-method");
    if (method && data.method) method.textContent = data.method;

    const m = data.metrics || {};
    const mh = $("#rod-eval-metrics");
    if (mh) {
      mh.className = "metrics-grid";
      mh.innerHTML = `
        <div class="metric-box"><span class="m-label">n hôtels</span><span class="m-value">${m.n ?? "—"}</span></div>
        <div class="metric-box"><span class="m-label">MAE écart</span><span class="m-value">${euro(m.mae)}</span></div>
        <div class="metric-box"><span class="m-label">RMSE</span><span class="m-value">${euro(m.rmse)}</span></div>
        <div class="metric-box"><span class="m-label">Biais (sim−réel)</span><span class="m-value">${euro(m.bias)}</span></div>
        <div class="metric-box"><span class="m-label">MAPE %</span><span class="m-value">${fmt(m.mape, 1)}</span></div>
        <div class="metric-box"><span class="m-label">Moy. réelle /12</span><span class="m-value">${euro(m.mean_true)}</span></div>
        <div class="metric-box good"><span class="m-label">Moy. sim (reco)</span><span class="m-value">${euro(m.mean_sim)}</span></div>
      `;
    }

    const host = $("#rod-eval-table");
    const rows = data.hotels || [];
    if (!host) return;
    if (!rows.length) {
      host.className = "perf-table-wrap empty";
      host.textContent = "Aucun hôtel.";
      return;
    }
    host.className = "perf-table-wrap";
    host.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Hôtel</th>
            <th>Mois</th>
            <th>Réel Σ/12</th>
            <th>Reco</th>
            <th>CA sim reco</th>
            <th>Écart</th>
            <th>%</th>
            <th>SIMPLY</th>
            <th>LIBERTY</th>
            <th>CONNECTED</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map((r) => {
              if (r.error) {
                return `<tr><td>${escapeHtml(r.hotel_code)}</td><td colspan="9">${escapeHtml(r.error)}</td></tr>`;
              }
              const bc = r.by_concept || {};
              const gap = r.gap_reco;
              const gapCls = (gap || 0) >= 0 ? "pos" : "neg";
              return `<tr>
                <td title="${escapeHtml(r.hotel_code)}">${escapeHtml(r.hotel_code)}<br><small>${escapeHtml(r.hotel_name || "")}</small></td>
                <td>${r.n_months || "—"} <small>(${escapeHtml((r.months || []).join(","))})</small></td>
                <td>${euro(r.avg_monthly_true)}</td>
                <td><strong>${escapeHtml(r.recommended_concept || "—")}</strong></td>
                <td>${euro(r.ca_sim_reco)}</td>
                <td class="${gapCls}">${euro(gap)}</td>
                <td>${r.gap_pct_reco != null ? fmt(r.gap_pct_reco, 1) + " %" : "—"}</td>
                <td>${euro(bc.SIMPLY?.ca_sim_mensuel)}</td>
                <td>${euro(bc.LIBERTY?.ca_sim_mensuel)}</td>
                <td>${euro(bc.CONNECTED?.ca_sim_mensuel)}</td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>`;
  }

  wire() {
    $("#btn-rod-run")?.addEventListener("click", () => this.run());
    $("#rod-hotel-select")?.addEventListener("change", () => {
      this.renderHotelMeta();
      this.trace = null;
    });
    $("#rod-year")?.addEventListener("change", () => this.loadPilots());

    $$(".rod-tab").forEach((el) => {
      el.addEventListener("click", () => this.setTab(el.dataset.rodTab));
    });
    $$(".rod-concept").forEach((el) => {
      el.addEventListener("click", () => this.setConcept(el.dataset.concept));
    });
  }
}
