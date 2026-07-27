/**
 * ROD User — simulateur directeur.
 *
 * Moteur : POST /api/rod/simulate (même logique admin, sans écart hold-out).
 * Recalcul auto à chaque changement. UI orientée grands résultats.
 */

import { $, $$, escapeHtml, debounce } from "../../../shared/js/dom.js";
import { api } from "../../../shared/js/api.js";
import { toast } from "../../../shared/js/toast.js";

function fmt(v, d = 1) {
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

class DirectorApp {
  constructor() {
    this.meta = null;
    this.trace = null;
    this.concept = "SIMPLY";
    this.tab = "resultat";
    this._paramsTouched = false;
    this._busy = false;
    this._queued = false;
    this._seq = 0;
    this._searchTimer = null;
  }

  async init() {
    await this.loadMeta();
    this.wire();
  }

  setStatus(msg) {
    const el = $("#dir-status");
    if (el) el.textContent = msg || "";
  }

  async loadMeta() {
    try {
      this.meta = await api.get("/api/rod/meta");
      this.renderNeeds(this.meta);
      const d = this.meta.defaults || {};
      this.setMLin(d.m_lin ?? 6);
      this.setMix(Math.round((d.mix_fb ?? 0.7) * 100));
    } catch (err) {
      toast.show(err.message, "err");
    }
  }

  renderNeeds(meta) {
    const fill = (hostId, items) => {
      const host = $("#" + hostId);
      if (!host) return;
      host.innerHTML = (items || [])
        .map(
          (it) => `
        <label class="need-item">
          <span>${escapeHtml(it.label || it.id)}</span>
          <input type="checkbox" data-need="${escapeHtml(it.id)}" ${
            it.default !== false ? "checked" : ""
          } />
        </label>`
        )
        .join("");
      host.querySelectorAll("input[data-need]").forEach((el) => {
        el.addEventListener("change", () => {
          this._paramsTouched = true;
          this.scheduleSim();
        });
      });
    };
    fill("needs-fb", meta.client_needs_fb);
    fill("needs-nfb", meta.client_needs_nfb);
  }

  setMLin(v) {
    const n = Number(v) || 6;
    const s = $("#m_lin_slider");
    const i = $("#m_lin");
    if (s) s.value = String(n);
    if (i) i.value = String(n);
    const lab = $("#m-lin-val");
    if (lab) lab.textContent = fmt(n, 1);
  }

  setMix(pct) {
    const p = Math.min(100, Math.max(0, Number(pct) || 0));
    const s = $("#mix_slider");
    const i = $("#mix_fb");
    if (s) s.value = String(p);
    if (i) i.value = String(p);
    if ($("#mix-val")) $("#mix-val").textContent = String(Math.round(p));
    if ($("#mix-nf-val")) $("#mix-nf-val").textContent = String(100 - Math.round(p));
  }

  collectNeeds() {
    const needs = {};
    $$("#needs-fb input[data-need], #needs-nfb input[data-need]").forEach((el) => {
      needs[el.dataset.need] = !!el.checked;
    });
    return needs;
  }

  collectParams() {
    const code = ($("#hotel_code")?.value || "").trim();
    const mixPct = Number($("#mix_fb")?.value ?? 70);
    const mLin = Number($("#m_lin")?.value ?? 6);
    const nRaw = $("#nb_chambres")?.value;
    const toRaw = $("#taux_occupation")?.value;
    const gRaw = $("#guests_per_chambre")?.value;
    return {
      hotel_code: code,
      m_lin: mLin,
      mix_fb: mixPct / 100,
      client_needs: this.collectNeeds(),
      nb_chambres: nRaw === "" || nRaw == null ? null : Number(nRaw),
      taux_occupation: toRaw === "" || toRaw == null ? null : Number(toRaw),
      guests_per_chambre: gRaw === "" || gRaw == null ? null : Number(gRaw),
    };
  }

  scheduleSim() {
    if (this._debounced) this._debounced();
  }

  async runSim() {
    const params = this.collectParams();
    if (!params.hotel_code) {
      this.setStatus("");
      return;
    }
    if (this._busy) {
      this._queued = true;
      return;
    }
    this._busy = true;
    const seq = ++this._seq;
    this.setStatus("Calcul…");

    try {
      const data = await api.post("/api/rod/simulate", params);
      if (seq !== this._seq && this._queued) return;
      if (!data.ok) throw new Error(data.error || "Simulation échouée");
      this.trace = data;

      // préremplir champs non touchés
      const p = data.params || {};
      const op = data.operating || {};
      if (!this._paramsTouched) {
        if (p.m_lin != null) this.setMLin(p.m_lin);
        if (p.mix_fb != null) this.setMix(Math.round(Number(p.mix_fb) * 100));
        if (op.nb_chambres != null && $("#nb_chambres") && !$("#nb_chambres").value)
          $("#nb_chambres").value = String(Math.round(op.nb_chambres));
        if (op.taux_occupation != null && $("#taux_occupation") && !$("#taux_occupation").value) {
          let to = Number(op.taux_occupation);
          if (to <= 1) to *= 100;
          $("#taux_occupation").value = String(Math.round(to * 10) / 10);
        }
        if (
          op.guests_per_chambre != null &&
          $("#guests_per_chambre") &&
          !$("#guests_per_chambre").value
        )
          $("#guests_per_chambre").value = String(
            Number(op.guests_per_chambre).toFixed(1)
          );
      }

      const reco = data.recommendation?.recommended_concept;
      if (reco) this.concept = reco;
      this.showResults();
      this.renderAll();
      this.setStatus(
        `${data.hotel_code} · ${reco || "—"} · ${fmt(p.m_lin ?? params.m_lin, 1)} m`
      );
    } catch (err) {
      this.setStatus(err.message);
      toast.show(err.message, "err");
    } finally {
      this._busy = false;
      if (this._queued) {
        this._queued = false;
        this.scheduleSim();
      }
    }
  }

  showResults() {
    $("#dir-empty")?.classList.add("hidden");
    $("#dir-results")?.classList.remove("hidden");
  }

  renderAll() {
    if (!this.trace) return;
    this.renderHero();
    this.renderBigMetrics();
    this.renderConceptPills();
    this.renderConceptCards();
    this.renderCaPanel();
    this.renderMarginPanel();
  }

  renderHero() {
    const reco = this.trace.recommendation?.recommended_concept || "—";
    const name = $("#dir-reco-name");
    if (name) name.textContent = reco;
    const line = $("#dir-hotel-line");
    if (line) {
      const id = this.trace.identity || {};
      const parts = [
        this.trace.hotel_code,
        id.hotel_name || this.trace.hotel_name,
        id.hotel_brand || this.trace.hotel_brand,
        this.trace.category ? `cat. ${this.trace.category}` : "",
      ].filter(Boolean);
      line.textContent = parts.join(" · ");
    }
  }

  /** Gros chiffres de la reco (ce que le directeur regarde d'abord). */
  renderBigMetrics() {
    const host = $("#dir-big-metrics");
    if (!host) return;
    const reco = this.trace.recommendation?.recommended_concept;
    const block = this.trace.by_concept?.[reco] || {};
    const sales = block.sales || {};
    const margin = block.margin || {};
    const costs = block.costs || {};
    host.innerHTML = `
      <div class="big-metric primary">
        <span class="bm-label">CA HT / mois</span>
        <span class="bm-value">${euro(sales.ca_ht_mensuel)}</span>
        <span class="bm-sub">${euro(sales.ca_ht_mensuel != null ? sales.ca_ht_mensuel * 12 : null)} / an</span>
      </div>
      <div class="big-metric">
        <span class="bm-label">Marge nette / mois</span>
        <span class="bm-value ${Number(margin.marge_nette_mensuelle) >= 0 ? "pos" : "neg"}">${euro(margin.marge_nette_mensuelle)}</span>
        <span class="bm-sub">${euro(margin.marge_nette_annuelle)} / an</span>
      </div>
      <div class="big-metric">
        <span class="bm-label">Coûts / mois</span>
        <span class="bm-value">${euro(margin.cout_mensuel ?? costs.monthly_cost)}</span>
        <span class="bm-sub">Capex ${euro(costs.capex)}</span>
      </div>
      <div class="big-metric">
        <span class="bm-label">Marge produit / mois</span>
        <span class="bm-value">${euro(margin.marge_produit_mensuelle)}</span>
        <span class="bm-sub">avant coûts fixes</span>
      </div>
    `;
  }

  renderConceptPills() {
    const reco = this.trace.recommendation?.recommended_concept;
    $$(".concept-pill").forEach((el) => {
      const c = el.dataset.concept;
      el.classList.toggle("active", c === this.concept);
      el.classList.toggle("is-reco", c === reco);
    });
  }

  renderConceptCards() {
    const host = $("#dir-concept-cards");
    if (!host || !this.trace) return;
    const reco = this.trace.recommendation?.recommended_concept;
    const allowed = new Set(this.trace.recommendation?.allowed_concepts || []);
    host.innerHTML = ["SIMPLY", "LIBERTY", "CONNECTED"]
      .map((c) => {
        const b = this.trace.by_concept?.[c] || {};
        const s = b.sales || {};
        const m = b.margin || {};
        const co = b.costs || {};
        const isReco = c === reco;
        const isOn = c === this.concept;
        const ok = allowed.has(c);
        return `
        <article class="concept-card ${isReco ? "recommended" : ""} ${isOn ? "selected" : ""} ${!ok ? "blocked" : ""}" data-concept="${c}">
          <header>
            <h3>${c}${isReco ? " ★" : ""}</h3>
            ${!ok ? '<span class="badge-off">non autorisé</span>' : ""}
          </header>
          <div class="cc-row"><span>CA / mois</span><strong>${euro(s.ca_ht_mensuel)}</strong></div>
          <div class="cc-row"><span>Marge nette / mois</span><strong class="${Number(m.marge_nette_mensuelle) >= 0 ? "pos" : "neg"}">${euro(m.marge_nette_mensuelle)}</strong></div>
          <div class="cc-row"><span>Coût / mois</span><strong>${euro(m.cout_mensuel ?? co.monthly_cost)}</strong></div>
          <div class="cc-row"><span>Capex</span><strong>${euro(co.capex)}</strong></div>
        </article>`;
      })
      .join("");

    host.querySelectorAll(".concept-card").forEach((el) => {
      el.addEventListener("click", () => {
        this.concept = el.dataset.concept;
        this.renderConceptPills();
        this.renderConceptCards();
        this.renderCaPanel();
        this.renderMarginPanel();
      });
    });
  }

  renderCaPanel() {
    const block = this.trace?.by_concept?.[this.concept] || {};
    const sales = block.sales || {};
    const kpi = $("#dir-ca-kpi");
    if (kpi) {
      kpi.innerHTML = `
        <div class="panel-kpi-item"><span>Solution</span><strong>${escapeHtml(this.concept)}</strong></div>
        <div class="panel-kpi-item primary"><span>CA HT / mois</span><strong>${euro(sales.ca_ht_mensuel)}</strong></div>
        <div class="panel-kpi-item"><span>CA F&amp;B</span><strong>${euro(sales.ca_fb_mensuel)}</strong></div>
        <div class="panel-kpi-item"><span>CA N-F&amp;B</span><strong>${euro(sales.ca_nf_mensuel)}</strong></div>
      `;
    }
    const steps = sales.steps || [];
    const host = $("#dir-sales-steps");
    if (!host) return;
    if (!steps.length) {
      host.innerHTML = "<p class='muted'>—</p>";
      return;
    }
    host.innerHTML = steps
      .map((s, i) => {
        const vals = s.values || {};
        const grid = Object.keys(vals)
          .map((k) => {
            let val = vals[k];
            if (Array.isArray(val)) val = val.join(", ");
            return `<div class="step-kv"><span>${escapeHtml(k)}</span><strong>${escapeHtml(String(val ?? "—"))}</strong></div>`;
          })
          .join("");
        return `
        <article class="dir-step">
          <div class="dir-step-n">${i + 1}</div>
          <div class="dir-step-body">
            <h4>${escapeHtml(s.title || s.id)}</h4>
            ${s.ca_ht != null ? `<div class="dir-step-ca">${euro(s.ca_ht)}</div>` : ""}
            <p class="dir-step-formula">${escapeHtml(s.formula || s.rule || "")}</p>
            <div class="step-kv-grid">${grid}</div>
          </div>
        </article>`;
      })
      .join("");
  }

  renderMarginPanel() {
    const host = $("#dir-margin-table");
    if (!host || !this.trace) return;
    const by = this.trace.by_concept || {};
    const reco = this.trace.recommendation?.recommended_concept;
    host.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Solution</th><th>CA HT</th><th>Marge produit</th>
            <th>Techno</th><th>Annexes</th><th>Agencement</th>
            <th>Coût total</th><th>Marge nette</th><th>Capex</th>
          </tr>
        </thead>
        <tbody>
          ${["SIMPLY", "LIBERTY", "CONNECTED"]
            .map((c) => {
              const b = by[c] || {};
              const s = b.sales || {};
              const m = b.margin || {};
              const co = b.costs || {};
              return `<tr class="${c === reco || c === this.concept ? "is-best" : ""}">
                <td><strong>${c}</strong>${c === reco ? " ★" : ""}</td>
                <td>${euro(s.ca_ht_mensuel)}</td>
                <td>${euro(m.marge_produit_mensuelle)}</td>
                <td>${euro(co.techno_monthly)}</td>
                <td>${euro(co.annexes_monthly)}</td>
                <td>${euro(co.agencement_monthly)}</td>
                <td>${euro(co.monthly_cost)}</td>
                <td class="${Number(m.marge_nette_mensuelle) >= 0 ? "pos" : "neg"}">${euro(m.marge_nette_mensuelle)}</td>
                <td>${euro(co.capex)}</td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>`;

    const lines = (by[this.concept] || {}).costs?.cost_lines || [];
    const cl = $("#dir-cost-lines");
    if (!cl) return;
    if (!lines.length) {
      cl.innerHTML = "<p class='muted'>—</p>";
      return;
    }
    cl.innerHTML = `
      <table>
        <thead><tr><th>Libellé</th><th>Groupe</th><th>Mensuel</th><th>Capex</th></tr></thead>
        <tbody>
          ${lines
            .map(
              (l) => `<tr>
              <td>${escapeHtml(l.label || l.id || "")}</td>
              <td>${escapeHtml(l.group || "")}</td>
              <td>${euro(l.monthly)}</td>
              <td>${euro(l.capex)}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  }

  setTab(tab) {
    this.tab = tab;
    $$(".dir-tab").forEach((el) => {
      el.classList.toggle("active", el.dataset.tab === tab);
    });
    $$(".dir-panel").forEach((el) => {
      el.classList.toggle("hidden", el.dataset.panel !== tab);
    });
  }

  async searchHotels(q) {
    const list = $("#ac-hotels");
    if (!list) return;
    if (!q || q.length < 1) {
      list.classList.add("hidden");
      list.innerHTML = "";
      return;
    }
    try {
      const data = await api.get("/api/hotels/search", { q, limit: 12 });
      const hotels = data.hotels || [];
      if (!hotels.length) {
        list.innerHTML = `<li class="ac-empty">Aucun résultat</li>`;
        list.classList.remove("hidden");
        return;
      }
      list.innerHTML = hotels
        .map(
          (h) =>
            `<li role="option" data-code="${escapeHtml(h.hotel_code)}" data-name="${escapeHtml(h.hotel_name || "")}" data-brand="${escapeHtml(h.hotel_brand || "")}">
              <strong>${escapeHtml(h.hotel_code)}</strong>
              <span>${escapeHtml(h.hotel_name || "—")}</span>
              <em>${escapeHtml(h.hotel_brand || "")}${h.hotel_city ? " · " + escapeHtml(h.hotel_city) : ""}</em>
            </li>`
        )
        .join("");
      list.classList.remove("hidden");
      list.querySelectorAll("li[data-code]").forEach((li) => {
        li.addEventListener("click", () => this.selectHotel(li.dataset));
      });
    } catch (err) {
      console.error(err);
    }
  }

  selectHotel(ds) {
    const code = ds.code;
    $("#hotel_code").value = code;
    $("#hotel_search").value = `${code} · ${ds.name || ""}`.trim();
    $("#ac-hotels")?.classList.add("hidden");
    const sum = $("#hotel-summary");
    if (sum) {
      sum.classList.remove("empty");
      sum.innerHTML = `
        <div class="hs-code">${escapeHtml(code)}</div>
        <div class="hs-name">${escapeHtml(ds.name || "—")}</div>
        <div class="hs-brand">${escapeHtml(ds.brand || "")}</div>
      `;
    }
    this._paramsTouched = false;
    // reset exploitation pour recharger depuis contexte
    ["nb_chambres", "taux_occupation", "guests_per_chambre"].forEach((id) => {
      const el = $("#" + id);
      if (el) el.value = "";
    });
    this.scheduleSim();
  }

  wire() {
    this._debounced = debounce(() => this.runSim(), 400);

    const search = $("#hotel_search");
    search?.addEventListener("input", () => {
      clearTimeout(this._searchTimer);
      const q = search.value.trim();
      this._searchTimer = setTimeout(() => this.searchHotels(q), 220);
    });
    search?.addEventListener("keydown", (e) => {
      if (e.key === "Escape") $("#ac-hotels")?.classList.add("hidden");
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".ac-wrap")) $("#ac-hotels")?.classList.add("hidden");
    });

    const linkSlider = (sliderId, inputId, onVal) => {
      const s = $("#" + sliderId);
      const i = $("#" + inputId);
      if (!s || !i) return;
      s.addEventListener("input", () => {
        i.value = s.value;
        onVal(s.value);
        this._paramsTouched = true;
        this.scheduleSim();
      });
      i.addEventListener("input", () => {
        onVal(i.value);
        this._paramsTouched = true;
        this.scheduleSim();
      });
    };
    linkSlider("m_lin_slider", "m_lin", (v) => this.setMLin(v));
    linkSlider("mix_slider", "mix_fb", (v) => this.setMix(v));

    ["nb_chambres", "taux_occupation", "guests_per_chambre"].forEach((id) => {
      $("#" + id)?.addEventListener("input", () => {
        this._paramsTouched = true;
        this.scheduleSim();
      });
    });

    $("#needs-all-on")?.addEventListener("click", () => {
      $$("#needs-fb input, #needs-nfb input").forEach((el) => {
        el.checked = true;
      });
      this._paramsTouched = true;
      this.scheduleSim();
    });
    $("#needs-all-off")?.addEventListener("click", () => {
      $$("#needs-fb input, #needs-nfb input").forEach((el) => {
        el.checked = false;
      });
      this._paramsTouched = true;
      this.scheduleSim();
    });

    $$(".dir-tab").forEach((el) => {
      el.addEventListener("click", () => this.setTab(el.dataset.tab));
    });
    $$(".concept-pill").forEach((el) => {
      el.addEventListener("click", () => {
        this.concept = el.dataset.concept;
        this.renderConceptPills();
        this.renderConceptCards();
        this.renderCaPanel();
        this.renderMarginPanel();
      });
    });
  }
}

const app = new DirectorApp();
app.init();
window.RODUser = app;
export { DirectorApp };
