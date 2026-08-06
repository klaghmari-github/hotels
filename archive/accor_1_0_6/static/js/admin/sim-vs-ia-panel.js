/**
 * Évaluation Simulateur vs IA (pilotes 2026).
 * Vrai CA · CA simulé · CA prédit pour SIMPLY / LIBERTY / CONNECTED.
 * Métriques : MAE, MSE. Moyenne mensuelle = somme / n mois dispo.
 */

import { $ } from "../../shared/js/dom.js";
import { api } from "../../shared/js/api.js";
import { toast } from "../../shared/js/toast.js";

const CONCEPTS = ["SIMPLY", "LIBERTY", "CONNECTED"];

function euro(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return (
    Number(v).toLocaleString("fr-FR", {
      maximumFractionDigits: 0,
      minimumFractionDigits: 0,
    }) + " €"
  );
}

function num(v, d = 0) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("fr-FR", {
    maximumFractionDigits: d,
    minimumFractionDigits: 0,
  });
}

export class SimVsIaPanel {
  constructor(state, nav) {
    this.state = state;
    this.nav = nav;
    this.result = null;
  }

  wire() {
    $("#btn-sim-vs-ia-run")?.addEventListener("click", () => this.run());
  }

  async open() {
    if (!this.state.confirmLeaveDirty()) return;
    this.nav.showSimVsIaPanel?.() || this._showView();
    this.nav.setModelNavActive?.("sim-vs-ia");
    // auto-run if empty
    if (!this.result) await this.run();
  }

  _showView() {
    this.nav.hideAllViews?.();
    const v = $("#view-sim-vs-ia");
    if (v) v.classList.remove("hidden");
    this.state.panel = "sim-vs-ia";
    this.nav.clearDatasetNavActive?.();
  }

  async run() {
    const status = $("#sim-vs-ia-status");
    const btn = $("#btn-sim-vs-ia-run");
    const year = Number($("#sim-vs-ia-year")?.value || 2026);
    const tier = $("#sim-vs-ia-tier")?.value || "final";
    if (btn) btn.disabled = true;
    if (status) status.textContent = "Calcul en cours (simulateur + IA)…";
    try {
      const res = await api.post("/api/rod/eval/compare", { year, tier });
      if (!res?.ok) throw new Error(res?.error || "Échec comparaison");
      this.result = res;
      this.render(res);
      if (status) status.textContent = "OK";
      toast.show(
        `Éval ${res.eval_year} · ${res.n_pilots} pilotes` +
          (res.has_ml ? ` · modèle ${res.model_name || res.model_id}` : " · sans modèle IA")
      );
    } catch (err) {
      if (status) status.textContent = err.message;
      toast.show(err.message, "err");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  render(res) {
    const chip = $("#sim-vs-ia-chip");
    if (chip) {
      chip.textContent = `${res.eval_year} · ${res.n_pilots} pilotes · ${
        res.has_ml ? res.model_name || "IA" : "sans IA"
      }`;
    }
    const method = $("#sim-vs-ia-method");
    if (method) method.textContent = res.method || "";

    // Metrics MAE/MSE per solution
    const metHost = $("#sim-vs-ia-metrics");
    if (metHost) {
      const blocks = [];
      for (const c of CONCEPTS) {
        const ms = res.metrics_sim_vs_true?.[c];
        const mp = res.metrics_pred_vs_true?.[c];
        blocks.push(`
          <div class="card">
            <h3 class="card-title">${c}</h3>
            <div class="metrics-grid">
              <div class="metric-box"><span class="m-label">MAE sim vs réel</span><span class="m-value">${
                ms ? num(ms.mae, 0) : "—"
              }</span></div>
              <div class="metric-box"><span class="m-label">MSE sim vs réel</span><span class="m-value">${
                ms ? num(ms.mse, 0) : "—"
              }</span></div>
              <div class="metric-box good"><span class="m-label">MAE IA vs réel</span><span class="m-value">${
                mp ? num(mp.mae, 0) : "—"
              }</span></div>
              <div class="metric-box"><span class="m-label">MSE IA vs réel</span><span class="m-value">${
                mp ? num(mp.mse, 0) : "—"
              }</span></div>
            </div>
          </div>`);
      }
      metHost.innerHTML = blocks.join("");
    }

    // Hotels table
    const host = $("#sim-vs-ia-table");
    if (!host) return;
    const rows = res.hotels || [];
    if (!rows.length) {
      host.innerHTML = `<p class="empty-state">Aucun pilote.</p>`;
      return;
    }
    let html = `<table class="data-table"><thead><tr>
      <th>Hôtel</th><th>Solution installée</th><th>Mois éval</th>
      <th>Vrai CA moy./mois</th>
      <th>Sim Simply</th><th>Sim Liberty</th><th>Sim Connected</th>
      <th>IA Simply</th><th>IA Liberty</th><th>IA Connected</th>
    </tr></thead><tbody>`;
    for (const r of rows) {
      const inst = r.installed_solution || "—";
      html += `<tr>
        <td><strong>${r.hotel_code}</strong><br><span class="muted small">${
          r.hotel_name || ""
        }</span></td>
        <td><span class="chip">${inst}</span></td>
        <td>${r.n_months_eval || 0}<br><span class="muted small">${(
          r.months_eval || []
        ).join(", ")}</span></td>
        <td class="xl-strong">${euro(r.true_avg_monthly_ca)}</td>
        ${CONCEPTS.map(
          (c) =>
            `<td class="${
              inst === c ? "is-installed" : ""
            }">${euro(r.sim?.[c])}</td>`
        ).join("")}
        ${CONCEPTS.map(
          (c) =>
            `<td class="${
              inst === c ? "is-installed" : ""
            }">${euro(r.pred?.[c])}</td>`
        ).join("")}
      </tr>`;
    }
    html += `</tbody></table>
      <p class="card-hint">
        CA mensuel moyen = somme des mois disponibles ÷ nombre de mois (pas ÷ 12).
        Cellules en surbrillance = solution réellement installée sur le pilote.
      </p>
      <p class="card-hint" style="margin-top:0.5rem">
        <strong>À retenir pour l'évaluation :</strong> même si l'on calcule le CA
        pour les trois solutions, la comparaison avec le CA réel n'est fiable
        que pour la solution déjà en place dans l'hôtel. Si l'hôtel est en Simply
        et que l'on regarde Liberty ou Connected, l'écart avec le réel est normal&nbsp;:
        ce n'est pas le même dispositif. Simply / Liberty / Connected hors solution
        installée restent utiles à titre indicatif.
      </p>`;
    host.innerHTML = html;
  }
}
