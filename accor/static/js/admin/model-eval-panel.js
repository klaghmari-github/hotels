/**
 * Onglet Evaluation — scores métier pred vs réel (Σ mois / 12).
 *
 * Deux instances indépendantes :
 *   - intermediate → models/design (multi-cibles)
 *   - final        → models/final/design (stacking)
 *
 * API : GET /api/model/eval/meta?tier=… , POST /api/model/eval { tier }
 */

import { $, escapeHtml } from "../../shared/js/dom.js";
import { api } from "../../shared/js/api.js";
import { toast } from "../../shared/js/toast.js";

/**
 * @typedef {object} EvalUiIds
 * @property {string} view
 * @property {string} title
 * @property {string} subtitle
 * @property {string} btnRun
 * @property {string} status
 * @property {string} chipYear
 * @property {string} chipMonths
 * @property {string} chipN
 * @property {string} modelSelect
 * @property {string} targetSelect
 * @property {string} year
 * @property {string} methodHint
 * @property {string} metrics
 * @property {string} totals
 * @property {string} hotelsTable
 * @property {string} monthsTable
 */

const INTER_IDS = {
  view: "view-model-eval",
  title: "eval-page-title",
  subtitle: "eval-page-subtitle",
  btnRun: "btn-eval-run",
  status: "eval-status",
  chipYear: "eval-chip-year",
  chipMonths: "eval-chip-months",
  chipN: "eval-chip-n",
  modelSelect: "eval-model-select",
  targetSelect: "eval-target-select",
  year: "eval-year",
  methodHint: "eval-method-hint",
  metrics: "eval-metrics",
  totals: "eval-totals",
  hotelsTable: "eval-hotels-table",
  monthsTable: "eval-months-table",
};

const FINAL_IDS = {
  view: "view-final-eval",
  title: "final-eval-page-title",
  subtitle: "final-eval-page-subtitle",
  btnRun: "btn-final-eval-run",
  status: "final-eval-status",
  chipYear: "final-eval-chip-year",
  chipMonths: "final-eval-chip-months",
  chipN: "final-eval-chip-n",
  modelSelect: "final-eval-model-select",
  targetSelect: "final-eval-target-select",
  year: "final-eval-year",
  methodHint: "final-eval-method-hint",
  metrics: "final-eval-metrics",
  totals: "final-eval-totals",
  hotelsTable: "final-eval-hotels-table",
  monthsTable: "final-eval-months-table",
};

export class ModelEvalPanel {
  /**
   * @param {import('./state.js').AdminState} state
   * @param {import('./nav-controller.js').NavController} nav
   * @param {"intermediate"|"final"} tier
   */
  constructor(state, nav, tier = "intermediate") {
    this.state = state;
    this.nav = nav;
    /** @type {"intermediate"|"final"} */
    this.tier = tier === "final" ? "final" : "intermediate";
    /** @type {EvalUiIds} */
    this.ids = this.tier === "final" ? FINAL_IDS : INTER_IDS;
    this.meta = null;
    this.lastResult = null;
    this.solution = "SIMPLY";
  }

  el(key) {
    const id = this.ids[key];
    return id ? document.getElementById(id) : null;
  }

  async open() {
    if (this._openBusy) return;
    const navKey = this.tier === "final" ? "final-eval" : "eval";
    const panelKey = this.tier === "final" ? "final-eval" : "model-eval";
    // Déjà ouvert + meta chargée → pas de rechargement
    if (this.state.panel === panelKey && this.meta) {
      if (this.tier === "final") this.nav.showFinalEvalPanel();
      else this.nav.showModelEvalPanel();
      if (this.lastResult) this.render(this.lastResult);
      return;
    }
    if (!this.state.confirmLeaveDirty()) return;
    this._openBusy = true;
    this.nav.setNavBusy(navKey, true);
    try {
      if (this.tier === "final") this.nav.showFinalEvalPanel();
      else this.nav.showModelEvalPanel();
      this._wireSolTabs();
      await this.loadMeta();
      if (this.lastResult) this.render(this.lastResult);
    } finally {
      this._openBusy = false;
      this.nav.setNavBusy(navKey, false);
    }
  }

  _wireSolTabs() {
    if (this.tier !== "intermediate") return;
    if (this._solWired) return;
    this._solWired = true;
    document.querySelectorAll("#eval-sol-tabs .sol-tab").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const sol = btn.dataset.solution;
        if (!sol || sol === this.solution) return;
        this.solution = sol;
        document.querySelectorAll("#eval-sol-tabs .sol-tab").forEach((b) => {
          b.classList.toggle("active", b.dataset.solution === sol);
        });
        this.lastResult = null;
        await this.loadMeta();
      });
    });
  }

  async loadMeta() {
    const status = this.el("status");
    if (status) status.textContent = "Chargement…";
    try {
      const meta = await api.get("/api/model/eval/meta", {
        tier: this.tier,
        solution: this.solution || undefined,
      });
      this.meta = meta;
      this.fillModels(meta.models || [], meta.top_model);
      this.fillTargets(meta.target_cols || [], meta.main_target);
      const yearEl = this.el("year");
      if (yearEl && meta.eval_year) yearEl.value = String(meta.eval_year);
      const chipY = this.el("chipYear");
      if (chipY) chipY.textContent = `Annee : ${meta.eval_year || "—"}`;
      const hint = this.el("methodHint");
      if (hint && meta.method) hint.textContent = meta.method;
      if (status) status.textContent = "";
    } catch (err) {
      if (status) status.textContent = err.message;
      toast.show(err.message, "err");
    }
  }

  fillModels(models, top) {
    const sel = this.el("modelSelect");
    if (!sel) return;
    sel.innerHTML = "";
    if (!models.length) {
      sel.innerHTML = `<option value="">— aucun modele —</option>`;
      return;
    }
    models.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m.id || m.name;
      let mae = "—";
      const main = m.main_target || "montant_ventes";
      const per = m.metrics_eval?.per_target?.[main];
      if (per?.mae != null) mae = Number(per.mae).toFixed(0);
      else if (m.metrics_eval?.mean_mae != null)
        mae = Number(m.metrics_eval.mean_mae).toFixed(0);
      const tag = this.tier === "final" ? "final" : "inter";
      opt.textContent = `[${tag}] ${m.name || m.id} · MAE ${mae}`;
      sel.appendChild(opt);
    });
    if (top && (top.id || top.name)) {
      sel.value = top.id || top.name;
    }
  }

  fillTargets(targets, main) {
    const sel = this.el("targetSelect");
    if (!sel) return;
    sel.innerHTML = "";
    const list = targets.length ? targets : [main || "montant_ventes"];
    list.forEach((t) => {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t === main ? `${t} (principale)` : t;
      if (t === main) opt.selected = true;
      sel.appendChild(opt);
    });
    if (main && list.includes(main)) sel.value = main;
  }

  async run() {
    const status = this.el("status");
    const btn = this.el("btnRun");
    const modelId = this.el("modelSelect")?.value;
    const target = this.el("targetSelect")?.value;
    const year = Number(this.el("year")?.value || 2026);
    if (!modelId) {
      toast.show("Choisissez un modele", "err");
      return;
    }
    if (btn) btn.disabled = true;
    if (status) status.textContent = "Evaluation en cours…";
    try {
      const res = await api.post("/api/model/eval", {
        model_id: modelId,
        target,
        year,
        tier: this.tier,
        solution: this.solution || undefined,
      });
      if (!res.ok) throw new Error(res.error || "Echec evaluation");
      this.lastResult = res;
      this.render(res);
      if (status) status.textContent = "OK";
      const label = this.tier === "final" ? "final" : "intermédiaire";
      toast.show(
        `Eval ${label} ${res.eval_year} · ${res.n_hotels} hotels · ${res.n_month_rows} mois`
      );
    } catch (err) {
      if (status) status.textContent = err.message;
      toast.show(err.message, "err");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  render(res) {
    const chipY = this.el("chipYear");
    const chipM = this.el("chipMonths");
    const chipN = this.el("chipN");
    if (chipY) chipY.textContent = `Annee : ${res.eval_year}`;
    if (chipM) {
      chipM.textContent = `Mois : ${(res.months_present || []).join(", ") || "—"}`;
    }
    if (chipN) {
      const tierLab = res.tier === "final" ? "final" : "inter";
      chipN.textContent = `${tierLab} · ${res.n_hotels} hotels · ${res.n_month_rows} lignes · ${res.target}`;
    }

    this.renderMetrics(this.el("metrics"), res.metrics_hotel_avg, "hotel · mois dispo");
    const tot = res.totals || {};
    const totHost = this.el("totals");
    if (totHost) {
      totHost.classList.remove("empty");
      totHost.innerHTML = `
        <div class="metric-box"><span class="m-label">Σ réel</span><span class="m-value">${fmtNum(tot.sum_true)}</span></div>
        <div class="metric-box"><span class="m-label">Σ prédit</span><span class="m-value">${fmtNum(tot.sum_pred)}</span></div>
        <div class="metric-box"><span class="m-label">Moy. mens. réelle (Σ/n mois)</span><span class="m-value">${fmtNum(tot.avg_monthly_true_all)}</span></div>
        <div class="metric-box good"><span class="m-label">Moy. mens. prédite (Σ/n mois)</span><span class="m-value">${fmtNum(tot.avg_monthly_pred_all)}</span></div>
        <p class="card-hint" style="grid-column:1/-1;margin:0.35rem 0 0">
          La comparaison avec le CA réel n'est fiable que pour la solution déjà
          installée dans l'hôtel. Les scénarios des autres solutions sont indicatifs.
        </p>
      `;
    }

    this.renderHotelsTable(res.hotels || []);
    this.renderMonthsTable(res.months_detail || []);
  }

  renderMetrics(host, m, label) {
    if (!host) return;
    if (!m || !m.n) {
      host.className = "metrics-grid empty";
      host.textContent = "Pas de metriques.";
      return;
    }
    host.className = "metrics-grid";
    host.innerHTML = `
      <div class="metric-box good"><span class="m-label">MAE (${escapeHtml(label)})</span><span class="m-value">${fmtNum(m.mae, 0)}</span></div>
      <div class="metric-box"><span class="m-label">MSE</span><span class="m-value">${fmtNum(m.mse, 0)}</span></div>
      <div class="metric-box"><span class="m-label">Biais (préd − réel)</span><span class="m-value">${fmtNum(m.bias, 0)}</span></div>
      <div class="metric-box"><span class="m-label">n hôtels</span><span class="m-value">${m.n}</span></div>
      <div class="metric-box"><span class="m-label">Moy. réelle</span><span class="m-value">${fmtNum(m.mean_true, 0)}</span></div>
      <div class="metric-box"><span class="m-label">Moy. prédite</span><span class="m-value">${fmtNum(m.mean_pred, 0)}</span></div>
    `;
  }

  renderHotelsTable(rows) {
    const host = this.el("hotelsTable");
    if (!host) return;
    if (!rows.length) {
      host.className = "perf-table-wrap empty";
      host.textContent = "Aucun hotel.";
      return;
    }
    host.className = "perf-table-wrap";
    host.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Hotel</th><th>Marque</th><th>Mois</th>
            <th>Σ reel</th><th>Σ pred</th>
            <th>Moy/12 reel</th><th>Moy/12 pred</th>
            <th>Erreur</th><th>%</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (r) => `<tr>
              <td title="${escapeHtml(r.hotel_code)}">${escapeHtml(r.hotel_code)}<br><small>${escapeHtml(r.hotel_name || "")}</small></td>
              <td>${escapeHtml(r.hotel_brand || "—")}</td>
              <td>${r.n_months} <small>(${escapeHtml((r.months || []).join(","))})</small></td>
              <td>${fmtNum(r.sum_true, 1)}</td>
              <td>${fmtNum(r.sum_pred, 1)}</td>
              <td>${fmtNum(r.avg_monthly_true, 1)}</td>
              <td>${fmtNum(r.avg_monthly_pred, 1)}</td>
              <td class="${(r.error_avg || 0) >= 0 ? "pos" : "neg"}">${fmtNum(r.error_avg, 1)}</td>
              <td>${r.pct_error != null ? fmtNum(r.pct_error, 1) + " %" : "—"}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  }

  renderMonthsTable(rows) {
    const host = this.el("monthsTable");
    if (!host) return;
    if (!rows.length) {
      host.className = "perf-table-wrap empty";
      host.textContent = "Aucun mois.";
      return;
    }
    host.className = "perf-table-wrap";
    const shown = rows.slice(0, 200);
    host.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Hotel</th><th>Mois</th><th>Reel</th><th>Pred</th><th>Erreur</th>
          </tr>
        </thead>
        <tbody>
          ${shown
            .map(
              (r) => `<tr>
              <td>${escapeHtml(r.hotel_code)}</td>
              <td>${r.annee}-${String(r.mois).padStart(2, "0")}</td>
              <td>${fmtNum(r.y_true, 1)}</td>
              <td>${fmtNum(r.y_pred, 1)}</td>
              <td class="${(r.error || 0) >= 0 ? "pos" : "neg"}">${fmtNum(r.error, 1)}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
      ${
        rows.length > shown.length
          ? `<p class="card-hint">${shown.length} / ${rows.length} lignes affichees</p>`
          : ""
      }`;
  }

  wire() {
    this.el("btnRun")?.addEventListener("click", () => this.run());
  }
}

function fmtNum(v, digits = 2) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("fr-FR", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  });
}
