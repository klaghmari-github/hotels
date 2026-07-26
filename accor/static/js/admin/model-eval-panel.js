/**
 * Onglet Evaluation.
 *
 * Compare le modèle design à la vérité terrain sur une année incomplete
 * (souvent 2026). Pour chaque hôtel :
 *   moyenne mensuelle = somme(mois disponibles) / 12
 * même formule côté prédit et réel, puis MAE / RMSE / R²…
 *
 * API : GET /api/model/eval/meta , POST /api/model/eval
 * Backend : accor.model_eval
 */

import { $, escapeHtml } from "../../shared/js/dom.js";
import { api } from "../../shared/js/api.js";
import { toast } from "../../shared/js/toast.js";
import { Format } from "../../shared/js/format.js";

export class ModelEvalPanel {
  /**
   * @param {import('./state.js').AdminState} state
   * @param {import('./nav-controller.js').NavController} nav
   */
  constructor(state, nav) {
    this.state = state;
    this.nav = nav;
    this.meta = null;
    this.lastResult = null;
  }

  async open() {
    if (!this.state.confirmLeaveDirty()) return;
    this.nav.showModelEvalPanel();
    await this.loadMeta();
  }

  async loadMeta() {
    const status = $("#eval-status");
    if (status) status.textContent = "Chargement…";
    try {
      const meta = await api.get("/api/model/eval/meta");
      this.meta = meta;
      this.fillModels(meta.models || [], meta.top_model);
      this.fillTargets(meta.target_cols || [], meta.main_target);
      const yearEl = $("#eval-year");
      if (yearEl && meta.eval_year) yearEl.value = String(meta.eval_year);
      const chipY = $("#eval-chip-year");
      if (chipY) chipY.textContent = `Annee : ${meta.eval_year || "—"}`;
      const hint = $("#eval-method-hint");
      if (hint && meta.method) hint.textContent = meta.method;
      if (status) status.textContent = "";
    } catch (err) {
      if (status) status.textContent = err.message;
      toast.show(err.message, "err");
    }
  }

  fillModels(models, top) {
    const sel = $("#eval-model-select");
    if (!sel) return;
    sel.innerHTML = "";
    if (!models.length) {
      sel.innerHTML = `<option value="">— aucun modele —</option>`;
      return;
    }
    models.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m.id || m.name;
      const r2 =
        m.score_r2 != null
          ? Number(m.score_r2).toFixed(3)
          : m.metrics_eval?.mean_r2 != null
            ? Number(m.metrics_eval.mean_r2).toFixed(3)
            : "—";
      opt.textContent = `${m.name || m.id} · R² ${r2}`;
      sel.appendChild(opt);
    });
    if (top && (top.id || top.name)) {
      sel.value = top.id || top.name;
    }
  }

  fillTargets(targets, main) {
    const sel = $("#eval-target-select");
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
    const status = $("#eval-status");
    const btn = $("#btn-eval-run");
    const modelId = $("#eval-model-select")?.value;
    const target = $("#eval-target-select")?.value;
    const year = Number($("#eval-year")?.value || 2026);
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
      });
      if (!res.ok) throw new Error(res.error || "Echec evaluation");
      this.lastResult = res;
      this.render(res);
      if (status) status.textContent = "OK";
      toast.show(
        `Eval ${res.eval_year} · ${res.n_hotels} hotels · ${res.n_month_rows} mois`
      );
    } catch (err) {
      if (status) status.textContent = err.message;
      toast.show(err.message, "err");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  render(res) {
    const chipY = $("#eval-chip-year");
    const chipM = $("#eval-chip-months");
    const chipN = $("#eval-chip-n");
    if (chipY) chipY.textContent = `Annee : ${res.eval_year}`;
    if (chipM) {
      chipM.textContent = `Mois : ${(res.months_present || []).join(", ") || "—"}`;
    }
    if (chipN) {
      chipN.textContent = `${res.n_hotels} hotels · ${res.n_month_rows} lignes · cible ${res.target}`;
    }

    this.renderMetrics($("#eval-metrics"), res.metrics_hotel_avg, "hotel /12");
    const tot = res.totals || {};
    const totHost = $("#eval-totals");
    if (totHost) {
      totHost.classList.remove("empty");
      totHost.innerHTML = `
        <div class="metric-box"><span class="m-label">Σ reel</span><span class="m-value">${fmtNum(tot.sum_true)}</span></div>
        <div class="metric-box"><span class="m-label">Σ pred</span><span class="m-value">${fmtNum(tot.sum_pred)}</span></div>
        <div class="metric-box"><span class="m-label">Moy. mens. reelle (Σ/12)</span><span class="m-value">${fmtNum(tot.avg_monthly_true_all)}</span></div>
        <div class="metric-box good"><span class="m-label">Moy. mens. pred (Σ/12)</span><span class="m-value">${fmtNum(tot.avg_monthly_pred_all)}</span></div>
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
      <div class="metric-box good"><span class="m-label">R² (${escapeHtml(label)})</span><span class="m-value">${fmtNum(m.r2, 3)}</span></div>
      <div class="metric-box"><span class="m-label">RMSE</span><span class="m-value">${fmtNum(m.rmse, 2)}</span></div>
      <div class="metric-box"><span class="m-label">MAE</span><span class="m-value">${fmtNum(m.mae, 2)}</span></div>
      <div class="metric-box"><span class="m-label">MAPE %</span><span class="m-value">${fmtNum(m.mape, 1)}</span></div>
      <div class="metric-box"><span class="m-label">Biais (pred−reel)</span><span class="m-value">${fmtNum(m.bias, 2)}</span></div>
      <div class="metric-box"><span class="m-label">n hotels</span><span class="m-value">${m.n}</span></div>
      <div class="metric-box"><span class="m-label">Moy. reelle</span><span class="m-value">${fmtNum(m.mean_true, 2)}</span></div>
      <div class="metric-box"><span class="m-label">Moy. pred</span><span class="m-value">${fmtNum(m.mean_pred, 2)}</span></div>
    `;
  }

  renderHotelsTable(rows) {
    const host = $("#eval-hotels-table");
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
    const host = $("#eval-months-table");
    if (!host) return;
    if (!rows.length) {
      host.className = "perf-table-wrap empty";
      host.textContent = "Aucun mois.";
      return;
    }
    host.className = "perf-table-wrap";
    // cap display for large tables
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
    $("#btn-eval-run")?.addEventListener("click", () => this.run());
  }
}

function fmtNum(v, digits = 2) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("fr-FR", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  });
}
