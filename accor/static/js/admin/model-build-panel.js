/**
 * Panneau Model Build.
 *
 * Params XGBoost manuels + grilles (listes de valeurs) + poll progress.
 * POST /api/model/build  →  GET /api/model/build/progress
 * POST /api/model/build/count pour prévisualiser le nombre de jobs.
 */

import { $, escapeHtml } from "../../shared/js/dom.js";
import { api } from "../../shared/js/api.js";
import { toast } from "../../shared/js/toast.js";

export class ModelBuildPanel {
  /**
   * @param {import('./state.js').AdminState} state
   * @param {import('./nav-controller.js').NavController} nav
   */
  constructor(state, nav) {
    this.state = state;
    this.nav = nav;
    this._pollTimer = null;
  }

  async open() {
    if (!this.state.confirmLeaveDirty()) return;
    this.nav.showModelBuildPanel();
    await this.loadConfig();
    try {
      const prog = await api.get("/api/model/build/progress");
      this.updateProgressUI(prog);
      if (prog.status === "running") this.startPolling();
      if (prog.status === "done" && (prog.results || []).length) {
        this.renderResults(prog);
      }
    } catch {
      /* ignore */
    }
  }

  async loadConfig() {
    const status = $("#model-status");
    if (status) status.textContent = "Chargement…";
    try {
      const cfg = await api.get("/api/model/config");
      this.state.modelConfig = cfg;
      this.renderConfig(cfg);
      this.updateJobCountChip();
      if (status) status.textContent = "";
    } catch (err) {
      if (status) status.textContent = err.message;
      toast.show(err.message, "err");
    }
  }

  renderConfig(cfg) {
    const chipSrc = $("#model-chip-source");
    const chipStats = $("#model-chip-stats");
    if (chipSrc) chipSrc.textContent = "source · model_data";
    if (chipStats) {
      chipStats.textContent = `train ${cfg.n_train ?? "—"} · éval ${cfg.n_eval ?? "—"} · ${cfg.n_features ?? "—"} feat · ${cfg.n_targets ?? "—"} cibles`;
    }
    const nameEl = $("#model-name");
    if (nameEl && cfg.model_name) nameEl.value = cfg.model_name;

    const tgtSel = $("#model-main-target");
    if (tgtSel) {
      const targets = cfg.target_cols || [];
      const main = cfg.main_target || "montant_ventes";
      tgtSel.innerHTML = targets
        .map(
          (t) =>
            `<option value="${escapeHtml(t)}"${t === main ? " selected" : ""}>${escapeHtml(t)}</option>`
        )
        .join("");
      if (!targets.length) {
        tgtSel.innerHTML = `<option value="montant_ventes">montant_ventes</option>`;
      }
    }

    const metSel = $("#model-rank-metric");
    if (metSel && cfg.default_rank_metric) metSel.value = cfg.default_rank_metric;

    const params = cfg.xgb_params || {};
    const schema = cfg.param_schema || [];
    const defaultGrid = cfg.default_grid_search || {};

    const pHost = $("#model-params");
    if (pHost) {
      pHost.innerHTML = "";
      schema.forEach((spec) => {
        const field = document.createElement("label");
        field.className = "field";
        const val = params[spec.name] != null ? params[spec.name] : "";
        field.innerHTML = `
          <span>${escapeHtml(spec.label || spec.name)}</span>
          <input type="number" data-param="${escapeHtml(spec.name)}"
            value="${escapeHtml(String(val))}"
            min="${spec.min != null ? spec.min : ""}"
            max="${spec.max != null ? spec.max : ""}"
            step="${spec.step != null ? spec.step : "any"}" />`;
        pHost.appendChild(field);
      });
      pHost.querySelectorAll("input").forEach((el) => {
        el.addEventListener("input", () => this.updateJobCountChip());
      });
    }

    const gHost = $("#model-grid-params");
    if (gHost) {
      gHost.innerHTML = "";
      schema.forEach((spec) => {
        const field = document.createElement("label");
        field.className = "field";
        const def = defaultGrid[spec.name];
        const defStr = Array.isArray(def) ? def.join(", ") : "";
        field.innerHTML = `
          <span>${escapeHtml(spec.label || spec.name)} (grid)</span>
          <input type="text" data-grid-param="${escapeHtml(spec.name)}"
            placeholder="ex. ${escapeHtml(String(params[spec.name] ?? ""))}"
            value="${escapeHtml(defStr)}" />`;
        gHost.appendChild(field);
      });
      gHost.querySelectorAll("input").forEach((el) => {
        el.addEventListener("input", () => this.updateJobCountChip());
      });
    }

    const gridEn = $("#model-grid-enabled");
    if (gridEn) {
      gridEn.onchange = () => {
        if (gHost) gHost.style.opacity = gridEn.checked ? "1" : "0.45";
        this.updateJobCountChip();
      };
      if (gHost) gHost.style.opacity = gridEn.checked ? "1" : "0.45";
    }
  }

  getXgbParams() {
    const out = {};
    document.querySelectorAll("#model-params input[data-param]").forEach((el) => {
      const n = Number(el.value);
      out[el.dataset.param] = Number.isFinite(n) ? n : el.value;
    });
    return out;
  }

  getGridSearch() {
    const enabled = $("#model-grid-enabled");
    if (enabled && !enabled.checked) return {};
    const out = {};
    document
      .querySelectorAll("#model-grid-params input[data-grid-param]")
      .forEach((el) => {
        const raw = (el.value || "").trim();
        if (!raw) return;
        const vals = raw
          .split(/[,;\s]+/)
          .map((s) => s.trim())
          .filter(Boolean)
          .map((s) => {
            const n = Number(s);
            return Number.isFinite(n) ? n : s;
          });
        if (vals.length) out[el.dataset.gridParam] = vals;
      });
    return out;
  }

  countLocalJobs() {
    const grid = this.getGridSearch();
    const keys = Object.keys(grid);
    if (!keys.length) return { total: 1, n_manual: 1, n_grid: 0 };
    let n = 1;
    keys.forEach((k) => {
      n *= Math.max(1, grid[k].length);
    });
    return { total: 1 + n, n_manual: 1, n_grid: n };
  }

  updateJobCountChip() {
    const c = this.countLocalJobs();
    const chip = $("#model-chip-jobs");
    const hint = $("#model-grid-count");
    const msg =
      c.n_grid > 0
        ? `${c.total} modeles (1 manuel + jusqu a ${c.n_grid} grid)`
        : "1 modele (manuel uniquement)";
    if (chip) chip.textContent = msg;
    if (hint) hint.textContent = msg;
  }

  updateProgressUI(prog) {
    const fill = $("#model-build-progress-fill");
    const text = $("#model-build-progress-text");
    const count = $("#model-build-progress-count");
    const pctEl = $("#model-build-progress-pct");
    const phaseEl = $("#model-build-progress-phase");
    const detailEl = $("#model-build-progress-detail");
    const bar = $("#model-build-progress-bar");
    const wrap = $("#model-build-progress");
    const card = $("#model-build-progress-card");

    const done = Number(prog.done || 0);
    const total = Number(prog.total || 0);
    const totalSafe = Math.max(1, total);
    // pct backend (fraction dans le job) prioritaire, sinon done/total
    let pct =
      prog.pct != null && Number.isFinite(Number(prog.pct))
        ? Number(prog.pct)
        : prog.status === "idle" && done === 0
          ? 0
          : Math.min(100, (done / totalSafe) * 100);
    if (prog.status === "done") pct = 100;
    pct = Math.min(100, Math.max(0, pct));
    const pctRound = Math.round(pct * 10) / 10;

    if (fill) fill.style.width = `${pctRound}%`;
    if (bar) bar.setAttribute("aria-valuenow", String(Math.round(pctRound)));
    if (pctEl) pctEl.textContent = `${pctRound.toLocaleString("fr-FR")} %`;
    if (count) {
      count.textContent =
        total > 0 ? `${done} / ${total} modèle(s)` : "— / —";
    }

    const phaseMap = {
      prepare: "Préparation",
      train: "Entraînement",
      save: "Sauvegarde",
      done: "Terminé",
      error: "Erreur",
      idle: "En attente",
    };
    const phase = prog.phase || prog.status || "idle";
    if (phaseEl) phaseEl.textContent = phaseMap[phase] || phase;

    if (text) {
      if (prog.status === "running") {
        text.textContent =
          prog.message || prog.current_name || "Entraînement…";
      } else if (prog.status === "done") {
        text.textContent = prog.message || "Terminé";
      } else if (prog.status === "error") {
        text.textContent = prog.error || prog.message || "Erreur";
      } else {
        text.textContent = "En attente";
      }
    }
    if (detailEl) {
      const bits = [];
      if (prog.current_name) bits.push(`modèle · ${prog.current_name}`);
      if (prog.current_target) bits.push(`cible · ${prog.current_target}`);
      if (prog.job_fraction != null && prog.status === "running") {
        const jf = Math.round(Number(prog.job_fraction) * 100);
        if (Number.isFinite(jf)) bits.push(`job ${jf} %`);
      }
      detailEl.textContent = bits.join("  ·  ");
    }

    if (wrap) {
      wrap.classList.toggle("is-running", prog.status === "running");
      wrap.classList.toggle("is-done", prog.status === "done");
      wrap.classList.toggle("is-error", prog.status === "error");
    }
    if (card) card.classList.toggle("is-active", prog.status === "running");
  }

  renderResults(prog) {
    const host = $("#model-build-results");
    const hint = $("#model-results-hint");
    if (!host) return;
    const rows = prog.results || [];
    if (!rows.length) {
      host.classList.add("empty");
      host.textContent = "Aucun resultat.";
      return;
    }
    host.classList.remove("empty");
    const metric = prog.rank_metric || "r2";
    const main = prog.main_target || "montant_ventes";
    if (hint) {
      hint.textContent = `Tries par ${metric} sur ${main} (eval). Meilleur en premier.`;
    }
    const head = `
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Modele</th>
            <th>Type</th>
            <th>${escapeHtml(metric)} (${escapeHtml(main)})</th>
            <th>R2 mean</th>
            <th>RMSE mean</th>
            <th>Params</th>
          </tr>
        </thead>
        <tbody>
    `;
    const body = rows
      .map((r, i) => {
        const cls = !r.ok ? "is-err" : i === 0 ? "is-best" : "";
        const mt =
          (r.metrics_eval &&
            r.metrics_eval.per_target &&
            r.metrics_eval.per_target[main]) ||
          {};
        const metricVal =
          r.metric_value != null
            ? Number(r.metric_value).toFixed(4)
            : mt[metric] != null
              ? Number(mt[metric]).toFixed(4)
              : "—";
        const meanR2 =
          r.metrics_eval && r.metrics_eval.mean_r2 != null
            ? Number(r.metrics_eval.mean_r2).toFixed(3)
            : "—";
        const meanRmse =
          r.metrics_eval && r.metrics_eval.mean_rmse != null
            ? Number(r.metrics_eval.mean_rmse).toFixed(2)
            : "—";
        const p = r.xgb_params || {};
        const pShort = [
          p.n_estimators != null ? `ne=${p.n_estimators}` : "",
          p.max_depth != null ? `md=${p.max_depth}` : "",
          p.learning_rate != null ? `lr=${p.learning_rate}` : "",
        ]
          .filter(Boolean)
          .join(" ");
        return `<tr class="${cls}">
          <td>${r.rank || i + 1}</td>
          <td>${escapeHtml(r.name || r.id || "—")}${
            r.error ? "<br><small>" + escapeHtml(r.error) + "</small>" : ""
          }</td>
          <td><span class="kind-tag">${escapeHtml(r.kind || "—")}</span></td>
          <td>${metricVal}</td>
          <td>${meanR2}</td>
          <td>${meanRmse}</td>
          <td>${escapeHtml(pShort || "—")}</td>
        </tr>`;
      })
      .join("");
    host.innerHTML = head + body + "</tbody></table>";
  }

  stopPolling() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  }

  startPolling() {
    this.stopPolling();
    // Poll plus serré pendant l'entraînement (arbres / cibles)
    this._pollTimer = setInterval(async () => {
      try {
        const prog = await api.get("/api/model/build/progress");
        this.updateProgressUI(prog);
        if (prog.status === "done" || prog.status === "error") {
          this.stopPolling();
          this.renderResults(prog);
          const btn = $("#btn-model-build");
          if (btn) btn.disabled = false;
          if (prog.status === "done") {
            const best = (prog.results || []).find((r) => r.ok);
            toast.show(
              best
                ? `Build terminé · meilleur : ${best.name} (rang 1)`
                : "Build terminé"
            );
            const status = $("#model-status");
            if (status) status.textContent = prog.message || "Terminé";
          } else {
            toast.show(prog.error || "Erreur de build", "err");
          }
        }
      } catch {
        /* reseau temporaire */
      }
    }, 400);
  }

  async build() {
    const btn = $("#btn-model-build");
    const status = $("#model-status");
    const body = {
      model_name: ($("#model-name") && $("#model-name").value) || "xgb_sales",
      xgb_params: this.getXgbParams(),
      grid_search: this.getGridSearch(),
      main_target:
        ($("#model-main-target") && $("#model-main-target").value) ||
        "montant_ventes",
      rank_metric:
        ($("#model-rank-metric") && $("#model-rank-metric").value) || "r2",
      async: true,
    };
    if (btn) btn.disabled = true;
    if (status) status.textContent = "Lancement du build…";

    // scroller vers la carte progression
    const card = $("#model-build-progress-card");
    if (card && typeof card.scrollIntoView === "function") {
      card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    this.updateProgressUI({
      status: "running",
      phase: "prepare",
      done: 0,
      total: this.countLocalJobs().total,
      pct: 0,
      job_fraction: 0,
      message: "Démarrage…",
    });
    try {
      const res = await api.post("/api/model/build", body);
      if (!res.ok && res.error) throw new Error(res.error);
      const total =
        (res.counts && res.counts.total) ||
        res.total ||
        this.countLocalJobs().total;
      this.updateProgressUI({
        status: "running",
        phase: "prepare",
        done: 0,
        total,
        pct: 0,
        job_fraction: 0,
        message: `Build lancé · ${total} modèle(s)`,
      });
      if (status) status.textContent = `Build en cours · ${total} modèle(s)…`;
      this.startPolling();
    } catch (err) {
      toast.show(err.message, "err");
      if (status) status.textContent = err.message;
      if (btn) btn.disabled = false;
      this.stopPolling();
      this.updateProgressUI({
        status: "error",
        phase: "error",
        message: err.message,
        error: err.message,
      });
    }
  }

  wire() {
    const btn = $("#btn-model-build");
    if (btn) btn.addEventListener("click", () => this.build());
  }
}
