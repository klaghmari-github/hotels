/**
 * Simulateur ROD — admin (pilotes + éval temporelle).
 *
 * Recalcul auto dès qu'un paramètre change (pas de bouton Simuler).
 * Split temporel : ref hors 2026, éval 2026. Pas d'exclusion d'hôtel.
 *
 * Onglets :
 *   - CA (règles)     : étapes ROD
 *   - Coûts & marge   : étude économique
 *   - Écart réel/sim  : validation vs ventes réelles (séparé)
 *   - Batch           : MAE sur tous les pilotes
 */

import { $, $$, escapeHtml, debounce } from "../../shared/js/dom.js";
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
  constructor(state, nav) {
    this.state = state;
    this.nav = nav;
    this.pilots = null;
    this.meta = null;
    this.trace = null;
    this.evalResult = null;
    this.concept = "SIMPLY";
    this.tab = "ca";
    this._simBusy = false;
    this._simQueued = false;
    this._evalBusy = false;
    this._paramsTouched = false;
    this._simSeq = 0;
  }

  async open() {
    if (!this.state.confirmLeaveDirty()) return;
    this.nav.showRodSimPanel();
    await this.loadMeta();
    await this.loadPilots();
  }

  year() {
    return Number($("#rod-year")?.value || 2026);
  }

  setStatus(msg) {
    const status = $("#rod-status");
    if (status) status.textContent = msg || "";
  }

  async loadMeta() {
    try {
      this.meta = await api.get("/api/rod/meta");
      this.renderNeedsToggles(this.meta);
      const d = this.meta.defaults || {};
      if (!$("#rod-m-lin")?.value) {
        this.setMLin(d.m_lin ?? 6);
      }
      if (!$("#rod-mix-fb")?.value) {
        this.setMix(Math.round((d.mix_fb ?? 0.7) * 100));
      }
    } catch (err) {
      console.error(err);
      toast.show(err.message, "err");
    }
  }

  renderNeedsToggles(meta) {
    const fill = (hostId, items) => {
      const host = $("#" + hostId);
      if (!host) return;
      host.innerHTML = (items || [])
        .map(
          (it) => `
        <label class="rod-need-item">
          <span>${escapeHtml(it.label || it.id)}</span>
          <span class="switch">
            <input type="checkbox" data-need="${escapeHtml(it.id)}" ${
              it.default !== false ? "checked" : ""
            } />
            <span></span>
          </span>
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
    fill("rod-needs-fb", meta.client_needs_fb);
    fill("rod-needs-nfb", meta.client_needs_nfb);
  }

  setNeedsAll(on) {
    $$("#rod-needs-fb input[data-need], #rod-needs-nfb input[data-need]").forEach(
      (el) => {
        el.checked = !!on;
      }
    );
    this._paramsTouched = true;
    this.scheduleSim();
  }

  collectNeeds() {
    const needs = {};
    $$("#rod-needs-fb input[data-need], #rod-needs-nfb input[data-need]").forEach(
      (el) => {
        needs[el.dataset.need] = !!el.checked;
      }
    );
    return needs;
  }

  setMLin(v) {
    const n = Number(v);
    const slider = $("#rod-m-lin-slider");
    const input = $("#rod-m-lin");
    if (slider) slider.value = String(n);
    if (input) input.value = String(n);
  }

  setMix(pct) {
    const p = Math.min(100, Math.max(0, Number(pct)));
    const slider = $("#rod-mix-slider");
    const input = $("#rod-mix-fb");
    if (slider) slider.value = String(p);
    if (input) input.value = String(p);
    const nf = $("#rod-mix-nf-label");
    if (nf) nf.textContent = `N-F&B = ${100 - p} %`;
  }

  collectParams() {
    const mixPct = Number($("#rod-mix-fb")?.value ?? 70);
    const mLin = Number($("#rod-m-lin")?.value ?? 6);
    const toRaw = $("#rod-to")?.value;
    const nRaw = $("#rod-nb-chambres")?.value;
    const gRaw = $("#rod-guests")?.value;
    return {
      year: this.year(),
      m_lin: mLin,
      mix_fb: mixPct / 100,
      client_needs: this.collectNeeds(),
      nb_chambres: nRaw === "" || nRaw == null ? null : Number(nRaw),
      taux_occupation: toRaw === "" || toRaw == null ? null : Number(toRaw),
      guests_per_chambre: gRaw === "" || gRaw == null ? null : Number(gRaw),
    };
  }

  async loadPilots() {
    this.setStatus("Chargement…");
    try {
      const year = this.year();
      const data = await api.get("/api/rod/pilots", { year });
      this.pilots = data;
      const chipY = $("#rod-chip-year");
      if (chipY) {
        const train = (data.train_years || []).join(", ") || "—";
        chipY.textContent = `Apprend ${train} · éval ${data.eval_year || year}`;
      }
      const chipN = $("#rod-chip-n");
      if (chipN) chipN.textContent = `${data.n || 0} pilote(s)`;
      this.fillHotels(data.hotels || []);
      this.setStatus("");
    } catch (err) {
      this.setStatus(err.message);
      toast.show(err.message, "err");
    }
  }

  fillHotels(hotels) {
    const sel = $("#rod-hotel-select");
    if (!sel) return;
    const prev = sel.value;
    sel.innerHTML = "";
    if (!hotels.length) {
      sel.innerHTML = `<option value="">— aucun —</option>`;
      return;
    }
    hotels.forEach((h) => {
      const opt = document.createElement("option");
      opt.value = h.hotel_code;
      const realPart = h.has_holdout
        ? `réel ${fmt(h.avg_monthly_true, 0)} €/mois`
        : "pas de réel éval";
      opt.textContent = `${h.hotel_code} · ${h.hotel_name || "—"} · ${
        h.category || "?"
      } · ${realPart}`;
      sel.appendChild(opt);
    });
    if (prev && hotels.some((h) => h.hotel_code === prev)) sel.value = prev;
    this.renderHotelMeta();
    if (sel.value) this.scheduleSim();
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
    const monthsVal = h.has_holdout
      ? (h.months || []).join(", ") || "—"
      : "—";
    host.className = "metrics-grid";
    host.innerHTML = `
      <div class="metric-box"><span class="m-label">Marque</span><span class="m-value">${escapeHtml(h.hotel_brand || "—")}</span></div>
      <div class="metric-box"><span class="m-label">Catégorie</span><span class="m-value">${escapeHtml(h.category || "—")}</span></div>
      <div class="metric-box"><span class="m-label">Mois réel</span><span class="m-value">${escapeHtml(monthsVal)}</span></div>
      <div class="metric-box ${h.has_holdout ? "good" : ""}"><span class="m-label">Réel éval Σ/12</span><span class="m-value">${h.has_holdout ? euro(h.avg_monthly_true) : "—"}</span></div>
    `;
  }

  scheduleSim() {
    if (this._simDebounced) this._simDebounced();
  }

  /**
   * Recalcule la simu hôtel courant (auto à chaque changement).
   * Ne lance PAS le batch — le batch est sur l'onglet dédié.
   */
  async runSim() {
    const code = $("#rod-hotel-select")?.value;
    if (!code) {
      this.setStatus("Choisissez un hôtel");
      return;
    }

    if (this._simBusy) {
      this._simQueued = true;
      return;
    }
    this._simBusy = true;
    const seq = ++this._simSeq;
    this.setStatus("Calcul…");

    try {
      const params = this.collectParams();
      const data = await api.post(
        `/api/rod/hotel/${encodeURIComponent(code)}/trace`,
        params
      );
      // réponse obsolète (nouvelle demande en file) → ignorer
      if (seq !== this._simSeq && this._simQueued) {
        return;
      }
      if (!data.ok) throw new Error(data.error || "Simulation échouée");
      this.trace = data;

      const p = data.params || {};
      if (!this._paramsTouched) {
        if (p.m_lin != null) this.setMLin(p.m_lin);
        if (p.mix_fb != null) this.setMix(Math.round(Number(p.mix_fb) * 100));
        if (p.nb_chambres != null && $("#rod-nb-chambres"))
          $("#rod-nb-chambres").value = String(Math.round(p.nb_chambres));
        if (p.taux_occupation != null && $("#rod-to")) {
          let to = Number(p.taux_occupation);
          if (to <= 1) to *= 100;
          $("#rod-to").value = String(Math.round(to * 10) / 10);
        }
        if (p.guests_per_chambre != null && $("#rod-guests"))
          $("#rod-guests").value = String(Number(p.guests_per_chambre).toFixed(1));
        const needs = p.client_needs || data.client_needs || {};
        Object.keys(needs).forEach((id) => {
          const el = document.querySelector(`input[data-need="${id}"]`);
          if (el) el.checked = !!needs[id];
        });
      }

      const reco = data.recommendation?.recommended_concept;
      if (reco) this.concept = reco;
      $$(".rod-concept").forEach((el) => {
        el.classList.toggle("active", el.dataset.concept === this.concept);
      });
      this.renderTrace();
      this.setStatus(
        `${code} · reco ${reco || "—"} · ${fmt(p.m_lin ?? params.m_lin, 1)} m · mix ${Math.round(
          (p.mix_fb ?? params.mix_fb) * 100
        )} %`
      );
    } catch (err) {
      this.setStatus(err.message);
      toast.show(err.message, "err");
    } finally {
      this._simBusy = false;
      if (this._simQueued) {
        this._simQueued = false;
        this.scheduleSim();
      }
    }
  }

  async runEvalBatch() {
    if (this._evalBusy) return;
    this._evalBusy = true;
    this.setStatus("Batch…");
    try {
      const year = this.year();
      const data = await api.get("/api/rod/eval", { year });
      if (!data.ok) throw new Error(data.error || "Éval échouée");
      this.evalResult = data;
      this.renderEval(data);
      const nScored = data.metrics?.n ?? "—";
      this.setStatus(
        `Batch ${data.eval_year} · ${data.n_hotels} pilote(s) · MAE n=${nScored}`
      );
    } catch (err) {
      this.setStatus(err.message);
      toast.show(err.message, "err");
    } finally {
      this._evalBusy = false;
    }
  }

  setTab(tab) {
    this.tab = tab;
    $$(".rod-tab").forEach((el) => {
      el.classList.toggle("active", el.dataset.rodTab === tab);
    });
    $$(".rod-panel").forEach((el) => {
      el.classList.toggle("hidden", el.dataset.rodPanel !== tab);
    });
    // Batch : lancer à l'entrée de l'onglet
    if (tab === "eval" && !this.evalResult) {
      this.runEvalBatch();
    }
    // Re-render panneaux si trace déjà là
    if (this.trace && tab !== "eval") {
      this.renderTrace();
    }
  }

  setConcept(c) {
    this.concept = c;
    $$(".rod-concept").forEach((el) => {
      el.classList.toggle("active", el.dataset.concept === c);
    });
    this.renderTrace();
  }

  renderTrace() {
    if (!this.trace) return;
    this.renderCategoryRef();
    this.renderRecoBanner();
    this.renderConceptKpi();
    this.renderSalesSteps(
      (this.trace.by_concept?.[this.concept] || {}).sales?.steps || []
    );
    this.renderMarginAll();
    this.renderCostLines(
      (this.trace.by_concept?.[this.concept] || {}).costs?.cost_lines || []
    );
    this.renderGapKpi();
    this.renderGapDetail();
  }

  /** KPI solution : CA / marges seulement (pas d'écart ici). */
  renderConceptKpi() {
    const kpi = $("#rod-concept-kpi");
    if (!kpi) return;
    const block = this.trace?.by_concept?.[this.concept];
    if (!block || block.ok === false || block.error) {
      kpi.className = "metrics-grid empty";
      kpi.textContent = block?.error || "—";
      return;
    }
    const sales = block.sales || {};
    const margin = block.margin || {};
    kpi.className = "metrics-grid";
    kpi.innerHTML = `
      <div class="metric-box good"><span class="m-label">CA sim / mois</span><span class="m-value">${euro(sales.ca_ht_mensuel)}</span></div>
      <div class="metric-box"><span class="m-label">Marge produit</span><span class="m-value">${euro(margin.marge_produit_mensuelle)}</span></div>
      <div class="metric-box good"><span class="m-label">Marge nette</span><span class="m-value">${euro(margin.marge_nette_mensuelle)}</span></div>
      <div class="metric-box"><span class="m-label">Coût / mois</span><span class="m-value">${euro(margin.cout_mensuel)}</span></div>
    `;
  }

  renderCategoryRef() {
    const host = $("#rod-category-ref");
    if (!host || !this.trace) return;
    const r = this.trace.category_reference || {};
    const train = (this.trace.train_years || r.train_years || []).join(", ");
    host.className = "metrics-grid";
    host.innerHTML = `
      <div class="metric-box"><span class="m-label">Catégorie</span><span class="m-value">${escapeHtml(r.category || "—")}</span></div>
      <div class="metric-box"><span class="m-label">Années train</span><span class="m-value">${escapeHtml(train || "—")}</span></div>
      <div class="metric-box"><span class="m-label">n hôtels ref</span><span class="m-value">${r.n_hotels ?? "—"}</span></div>
      <div class="metric-box good"><span class="m-label">CA mensuel ref</span><span class="m-value">${euro(r.ca_monthly_ref)}</span></div>
      <div class="metric-box"><span class="m-label">Clients/mois ref</span><span class="m-value">${fmt(r.clients_mois_ref, 1)}</span></div>
      <div class="metric-box"><span class="m-label">Année éval</span><span class="m-value">${this.trace.eval_year ?? "—"}</span></div>
    `;
  }

  renderRecoBanner() {
    const host = $("#rod-reco-banner");
    if (!host || !this.trace) return;
    const rec = this.trace.recommendation || {};
    if (!rec.recommended_concept) {
      host.classList.add("hidden");
      return;
    }
    host.classList.remove("hidden");
    host.innerHTML = `
      <div class="tag">Reco</div>
      <h2>${escapeHtml(rec.recommended_concept)}</h2>
    `;
  }

  /** KPI dédiés écart réel vs sim (solution affichée). */
  renderGapKpi() {
    const host = $("#rod-gap-kpi");
    if (!host || !this.trace) return;
    const c = this.concept;
    const gap = (this.trace.gaps || {})[c] || {};
    const real = this.trace.real_holdout || {};
    const hasHold = !!(this.trace.has_holdout || real.available);
    const ca =
      gap.ca_sim_mensuel ??
      this.trace.by_concept?.[c]?.sales?.ca_ht_mensuel;
    const avgTrue = gap.avg_monthly_true ?? real.avg_monthly_true;
    const gapCls =
      hasHold && gap.gap != null
        ? (gap.gap || 0) >= 0
          ? "good"
          : "warn"
        : "";

    host.className = "metrics-grid rod-gap-kpi";
    if (!hasHold) {
      host.innerHTML = `
        <div class="metric-box"><span class="m-label">Solution</span><span class="m-value">${escapeHtml(c)}</span></div>
        <div class="metric-box good"><span class="m-label">CA simulé / mois</span><span class="m-value">${euro(ca)}</span></div>
        <div class="metric-box"><span class="m-label">Réel éval</span><span class="m-value">—</span></div>
        <div class="metric-box"><span class="m-label">Écart</span><span class="m-value">—</span></div>
      `;
      return;
    }
    host.innerHTML = `
      <div class="metric-box"><span class="m-label">Solution</span><span class="m-value">${escapeHtml(c)}</span></div>
      <div class="metric-box good"><span class="m-label">CA simulé / mois</span><span class="m-value">${euro(ca)}</span></div>
      <div class="metric-box"><span class="m-label">Réel ${real.year || ""} Σ/12</span><span class="m-value">${euro(avgTrue)}</span></div>
      <div class="metric-box ${gapCls}"><span class="m-label">Écart (sim − réel)</span><span class="m-value">${euro(gap.gap)}${gap.gap_pct != null ? " · " + fmt(gap.gap_pct, 1) + " %" : ""}</span></div>
    `;
  }

  renderGapDetail() {
    const host = $("#rod-gap-table");
    if (!host || !this.trace) return;
    const gaps = this.trace.gaps || {};
    const real = this.trace.real_holdout || {};
    const reco = this.trace.recommendation?.recommended_concept;
    const hasHold = !!(this.trace.has_holdout || real.available);
    host.className = "perf-table-wrap";
    host.innerHTML = `
      <table id="rod-gap-table-inner">
        <thead>
          <tr>
            <th>Solution</th>
            <th>CA simulé / mois</th>
            <th>Réel ${real.year || ""} Σ/12</th>
            <th>Écart (sim − réel)</th>
            <th>%</th>
          </tr>
        </thead>
        <tbody>
          ${["SIMPLY", "LIBERTY", "CONNECTED"]
            .map((c) => {
              const g = gaps[c] || {};
              const ca =
                g.ca_sim_mensuel ??
                this.trace.by_concept?.[c]?.sales?.ca_ht_mensuel;
              const cls =
                g.gap != null ? ((g.gap || 0) >= 0 ? "pos" : "neg") : "";
              return `<tr class="${c === reco || c === this.concept ? "is-best" : ""}">
                <td><strong>${c}</strong>${c === reco ? " ★" : ""}</td>
                <td>${euro(ca)}</td>
                <td>${hasHold ? euro(g.avg_monthly_true ?? real.avg_monthly_true) : "—"}</td>
                <td class="${cls}">${hasHold ? euro(g.gap) : "—"}</td>
                <td class="${cls}">${hasHold && g.gap_pct != null ? fmt(g.gap_pct, 1) + " %" : "—"}</td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>`;
  }

  renderSalesSteps(steps) {
    const host = $("#rod-sales-steps");
    if (!host) return;
    if (!steps.length) {
      host.className = "rod-steps empty";
      host.textContent = "—";
      return;
    }
    host.className = "rod-steps";
    host.innerHTML = steps
      .map((s, i) => {
        const vals = s.values || {};
        const grid = Object.keys(vals)
          .map((k) => {
            let val = vals[k];
            if (Array.isArray(val)) val = val.join(", ");
            return `<div class="rod-kv"><span>${escapeHtml(k)}</span><strong>${escapeHtml(
              String(val ?? "—")
            )}</strong></div>`;
          })
          .join("");
        const caBlock =
          s.ca_ht != null
            ? `<div class="rod-step-ca"><span class="muted">CA HT</span><strong>${euro(
                s.ca_ht
              )}</strong></div>`
            : "";
        return `
        <article class="rod-step">
          <header>
            <span class="rod-step-n">${i + 1}</span>
            <div>
              <h3>${escapeHtml(s.title || s.id)}</h3>
              <p class="rod-rule">${escapeHtml(s.rule || "")}</p>
            </div>
            ${caBlock}
          </header>
          <p class="rod-formula">${escapeHtml(s.formula || "")}</p>
          <div class="rod-kv-grid">${grid}</div>
          ${
            s.ca_fb != null
              ? `<div class="rod-step-split"><span>F&amp;B ${euro(
                  s.ca_fb
                )}</span><span>N-F&amp;B ${euro(s.ca_nf)}</span></div>`
              : ""
          }
        </article>`;
      })
      .join("");
  }

  renderMarginAll() {
    const host = $("#rod-margin-table");
    if (!host || !this.trace) return;
    const by = this.trace.by_concept || {};
    const reco = this.trace.recommendation?.recommended_concept;
    host.className = "perf-table-wrap";
    host.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Solution</th>
            <th>CA HT</th>
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
      host.textContent = "—";
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
    const m = data.metrics || {};
    const mh = $("#rod-eval-metrics");
    if (mh) {
      mh.className = "metrics-grid";
      mh.innerHTML = `
        <div class="metric-box"><span class="m-label">n pilotes</span><span class="m-value">${m.n_predicted ?? data.n_hotels ?? "—"}</span></div>
        <div class="metric-box"><span class="m-label">n éval (réel)</span><span class="m-value">${m.n ?? "—"}</span></div>
        <div class="metric-box"><span class="m-label">MAE</span><span class="m-value">${euro(m.mae)}</span></div>
        <div class="metric-box"><span class="m-label">RMSE</span><span class="m-value">${euro(m.rmse)}</span></div>
        <div class="metric-box"><span class="m-label">Biais</span><span class="m-value">${euro(m.bias)}</span></div>
        <div class="metric-box"><span class="m-label">MAPE %</span><span class="m-value">${fmt(m.mape, 1)}</span></div>
        <div class="metric-box good"><span class="m-label">Moy. sim reco</span><span class="m-value">${euro(m.mean_sim ?? m.mean_sim_all)}</span></div>
        <div class="metric-box"><span class="m-label">Moy. réel</span><span class="m-value">${euro(m.mean_true)}</span></div>
      `;
    }
    const host = $("#rod-eval-table");
    const rows = data.hotels || [];
    if (!host) return;
    host.className = "perf-table-wrap";
    host.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Hôtel</th><th>Catégorie</th><th>CA ref</th><th>Réel Σ/12</th>
            <th>Reco</th><th>CA sim</th><th>Écart</th><th>%</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map((r) => {
              if (r.error)
                return `<tr><td>${escapeHtml(r.hotel_code)}</td><td colspan="7">${escapeHtml(
                  r.error
                )}</td></tr>`;
              const hasH = !!r.has_holdout;
              const gapCls =
                r.gap_reco != null ? ((r.gap_reco || 0) >= 0 ? "pos" : "neg") : "";
              return `<tr>
                <td>${escapeHtml(r.hotel_code)}<br><small>${escapeHtml(
                  r.hotel_name || ""
                )}</small></td>
                <td>${escapeHtml(r.category || "—")}</td>
                <td>${euro(r.ca_ref_categorie)}</td>
                <td>${hasH ? euro(r.avg_monthly_true) : "—"}</td>
                <td><strong>${escapeHtml(r.recommended_concept || "—")}</strong></td>
                <td>${euro(r.ca_sim_reco)}</td>
                <td class="${gapCls}">${hasH ? euro(r.gap_reco) : "—"}</td>
                <td class="${gapCls}">${hasH && r.gap_pct_reco != null ? fmt(r.gap_pct_reco, 1) + " %" : "—"}</td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>`;
  }

  wire() {
    // Auto-recalc (pas de bouton Simuler)
    this._simDebounced = debounce(() => this.runSim(), 400);

    $("#rod-hotel-select")?.addEventListener("change", () => {
      this._paramsTouched = false;
      this.evalResult = null;
      this.renderHotelMeta();
      this.scheduleSim();
    });
    $("#rod-year")?.addEventListener("change", async () => {
      this._paramsTouched = false;
      this.evalResult = null;
      await this.loadPilots();
      if (this.tab === "eval") this.runEvalBatch();
    });

    const linkM = (sliderId, inputId) => {
      const s = $("#" + sliderId);
      const i = $("#" + inputId);
      if (s && i) {
        s.addEventListener("input", () => {
          i.value = s.value;
          if (inputId === "rod-mix-fb") this.setMix(s.value);
          this._paramsTouched = true;
          this.scheduleSim();
        });
        i.addEventListener("change", () => {
          if (inputId === "rod-mix-fb") this.setMix(i.value);
          else this.setMLin(i.value);
          this._paramsTouched = true;
          this.scheduleSim();
        });
        i.addEventListener("input", () => {
          this._paramsTouched = true;
          this.scheduleSim();
        });
      }
    };
    linkM("rod-m-lin-slider", "rod-m-lin");
    linkM("rod-mix-slider", "rod-mix-fb");

    ["rod-nb-chambres", "rod-to", "rod-guests"].forEach((id) => {
      const el = $("#" + id);
      if (!el) return;
      el.addEventListener("change", () => {
        this._paramsTouched = true;
        this.scheduleSim();
      });
      el.addEventListener("input", () => {
        this._paramsTouched = true;
        this.scheduleSim();
      });
    });

    $("#rod-needs-all-on")?.addEventListener("click", () => this.setNeedsAll(true));
    $("#rod-needs-all-off")?.addEventListener("click", () => this.setNeedsAll(false));

    $$(".rod-tab").forEach((el) => {
      el.addEventListener("click", () => this.setTab(el.dataset.rodTab));
    });
    $$(".rod-concept").forEach((el) => {
      el.addEventListener("click", () => this.setConcept(el.dataset.concept));
    });
  }
}
