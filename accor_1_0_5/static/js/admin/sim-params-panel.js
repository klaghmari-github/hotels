/**
 * Onglet admin « Simulateur params » — tables figées du moteur ROD.
 *
 * Source : GET /api/rod/sim-params (pilot_table + coûts Excel).
 */

import { $ } from "../../shared/js/dom.js";
import { api } from "../../shared/js/api.js";
import { toast } from "../../shared/js/toast.js";

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtCell(v, key = "") {
  if (v == null || v === "") return "—";
  if (typeof v === "number") {
    // Mix / TO (0–1) → %
    if (
      (key === "to" || key === "mix_fb" || key === "mix_nfb" || key === "coeff") &&
      v >= 0 &&
      v <= 1
    ) {
      if (key === "coeff") {
        return Number(v).toLocaleString("fr-FR", { maximumFractionDigits: 2 });
      }
      return `${Math.round(v * 1000) / 10} %`.replace(".0 %", " %");
    }
    if (Number.isInteger(v)) return String(v);
    return Number(v).toLocaleString("fr-FR", { maximumFractionDigits: 3 });
  }
  return esc(v);
}

export class SimParamsPanel {
  /**
   * @param {import('./state.js').AdminState} state
   * @param {import('./nav-controller.js').NavController} nav
   */
  constructor(state, nav) {
    this.state = state;
    this.nav = nav;
    this._loaded = false;
    this._data = null;
  }

  wire() {
    $("#btn-sim-params-reload")?.addEventListener("click", () => {
      this._loaded = false;
      this.open();
    });
  }

  async open() {
    if (typeof this.nav.showSimParamsPanel === "function") {
      this.nav.showSimParamsPanel();
    } else {
      this.state.panel = "sim-params";
      this.nav.hideAllViews();
      $("#view-sim-params")?.classList.remove("hidden");
      this.nav.clearDatasetNavActive();
      $("#nav-sim-params")?.classList.add("active");
    }
    const host = $("#sim-params-root");
    if (!host) return;
    if (this._loaded && this._data) {
      this.render(this._data);
      return;
    }
    host.innerHTML = `<p class="muted" style="padding:1rem">Chargement des paramètres simulateur…</p>`;
    try {
      const data = await api.get("/api/rod/sim-params");
      if (data.error && data.ok === false) throw new Error(data.error);
      this._data = data;
      this._loaded = true;
      this.render(data);
      const chip = $("#sim-params-chip");
      if (chip) chip.textContent = data.source || "paramètres figés";
    } catch (err) {
      host.innerHTML = `<p class="empty-state">Erreur : ${esc(err.message)}</p>`;
      toast.show(err.message, "err");
    }
  }

  render(data) {
    const host = $("#sim-params-root");
    if (!host) return;
    const sections = data.sections || [];
    let html = "";

    // Formules + ordre
    html += `<section class="card card-wide sim-params-card">
      <h2 class="card-title">Ordre d’exécution</h2>
      <ol class="sim-params-list">
        ${(data.order || []).map((s) => `<li>${esc(s)}</li>`).join("")}
      </ol>
    </section>`;

    html += `<section class="card card-wide sim-params-card">
      <h2 class="card-title">Formules R1 → R4</h2>
      <dl class="sim-params-dl">
        ${Object.entries(data.formulas || {})
          .map(
            ([k, v]) =>
              `<div><dt><code>${esc(k)}</code></dt><dd>${esc(v)}</dd></div>`
          )
          .join("")}
      </dl>
    </section>`;

    html += `<section class="card card-wide sim-params-card">
      <h2 class="card-title">Marge nette &amp; amortissement</h2>
      <dl class="sim-params-dl">
        ${Object.entries(data.net_rules || {})
          .map(
            ([k, v]) =>
              `<div><dt><code>${esc(k)}</code></dt><dd>${esc(v)}</dd></div>`
          )
          .join("")}
      </dl>
    </section>`;

    for (const sec of sections) {
      html += this._sectionTable(sec);
    }

    html += `<section class="card card-wide sim-params-card">
      <h2 class="card-title">Garde-fous</h2>
      <ul class="sim-params-list">
        ${(data.guards || []).map((g) => `<li>${esc(g)}</li>`).join("")}
      </ul>
      <p class="muted small" style="margin-top:0.75rem">Source : ${esc(
        data.source || "—"
      )}</p>
    </section>`;

    host.innerHTML = html;
  }

  _sectionTable(sec) {
    const cols = sec.columns || [];
    const rows = sec.rows || [];
    const notes = (sec.notes || [])
      .map((n) => `<p class="card-hint">${esc(n)}</p>`)
      .join("");
    let thead = "<tr>";
    for (const [, lab] of cols) thead += `<th>${esc(lab)}</th>`;
    thead += "</tr>";
    let body = "";
    for (const row of rows) {
      body += "<tr>";
      for (const [key] of cols) {
        const raw = row[key];
        let cell = fmtCell(raw, key);
        if (key === "concept" && typeof raw === "string") {
          const c = raw.toLowerCase();
          cell = `<span class="tag-sol tag-sol-${c}">${esc(raw)}</span>`;
        }
        body += `<td>${cell}</td>`;
      }
      body += "</tr>";
    }
    const footer = sec.footer
      ? `<p class="muted small" style="margin-top:0.5rem">${esc(sec.footer)}</p>`
      : "";
    return `<section class="card card-wide sim-params-card" id="sim-params-${esc(
      sec.id
    )}">
      <h2 class="card-title">${esc(sec.title)}</h2>
      ${sec.description ? `<p class="card-hint">${esc(sec.description)}</p>` : ""}
      ${notes}
      <div class="perf-table-wrap sim-params-table-wrap">
        <table class="data-table sim-params-table">
          <thead>${thead}</thead>
          <tbody>${body}</tbody>
        </table>
      </div>
      ${footer}
    </section>`;
  }
}
