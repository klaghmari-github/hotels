/**
 * Panneau Modèle final · Build (stacking).
 *
 * Params XGBoost manuels + grilles (listes de valeurs) + poll progress.
 * POST /api/model/final/build → GET /api/model/final/build/progress
 * POST /api/model/build/count pour prévisualiser le nombre de jobs.
 */

import { $, escapeHtml } from "../../shared/js/dom.js";
import { api } from "../../shared/js/api.js";
import { toast } from "../../shared/js/toast.js";

export class FinalModelBuildPanel {
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
    if (this._openBusy) return;
    if (this.state.panel === "final-build" && this._openedOnce) {
      this.nav.showFinalBuildPanel();
      return;
    }
    if (!this.state.confirmLeaveDirty()) return;
    this._openBusy = true;
    this.nav.setNavBusy("final-build", true);
    try {
      this.nav.showFinalBuildPanel();
      await this.loadConfig();
      try {
        const prog = await api.get("/api/model/final/build/progress");
        this.updateProgressUI(prog);
        if (prog.status === "running") this.startPolling();
        if (prog.status === "done" && (prog.results || []).length) {
          this.renderResults(prog);
        }
      } catch {
        /* ignore */
      }
      this._openedOnce = true;
    } finally {
      this._openBusy = false;
      this.nav.setNavBusy("final-build", false);
    }
  }

  async loadConfig() {
    const status = $("#final-status");
    if (status) status.textContent = "Chargement…";
    try {
      const cfg = await api.get("/api/model/final/config");
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
    const chipSrc = $("#final-chip-source");
    const chipStats = $("#final-chip-stats");
    if (chipSrc) chipSrc.textContent = "stacking · descriptives + pred_*";
    // liste intermédiaires
    const interSel = $("#final-intermediate-select");
    if (interSel) {
      const inter = cfg.intermediate_models || [];
      const def = cfg.default_intermediate_id;
      interSel.innerHTML = inter.length
        ? inter.map((m) => {
            const id = m.id || m.name;
            const lab = `#${m.rank || "?"} ${m.name || id}`;
            return `<option value="${id}"${id === def ? " selected" : ""}>${lab}</option>`;
          }).join("")
        : `<option value="">— aucun intermédiaire (Build d\'abord) —</option>`;
    }
    const pipe = $("#final-pipeline-hint");
    if (pipe && cfg.pipeline && cfg.pipeline.note) {
      pipe.textContent = cfg.pipeline.note;
    }
    if (chipStats) {
      chipStats.textContent = `train ${cfg.n_train ?? "—"} · éval ${cfg.n_eval ?? "—"} · ${cfg.n_features ?? "—"} feat · ${cfg.n_targets ?? "—"} cibles`;
    }
    const nameEl = $("#final-model-name");
    if (nameEl && cfg.model_name) nameEl.value = cfg.model_name;

    const tgtSel = $("#final-main-target");
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

    const metSel = $("#final-rank-metric");
    if (metSel && cfg.default_rank_metric) metSel.value = cfg.default_rank_metric;

    const params = cfg.xgb_params || {};
    const schema = cfg.param_schema || [];
    const defaultGrid = cfg.default_grid_search || {};

    const pHost = $("#final-params");
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

    const gHost = $("#final-grid-params");
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

    const gridEn = $("#final-grid-enabled");
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
    document.querySelectorAll("#final-params input[data-param]").forEach((el) => {
      const n = Number(el.value);
      out[el.dataset.param] = Number.isFinite(n) ? n : el.value;
    });
    return out;
  }

  getGridSearch() {
    const enabled = $("#final-grid-enabled");
    if (enabled && !enabled.checked) return {};
    const out = {};
    document
      .querySelectorAll("#final-grid-params input[data-grid-param]")
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
    const chip = $("#final-chip-jobs");
    const hint = $("#final-grid-count");
    const msg =
      c.n_grid > 0
        ? `${c.total} modeles (1 manuel + jusqu a ${c.n_grid} grid)`
        : "1 modele (manuel uniquement)";
    if (chip) chip.textContent = msg;
    if (hint) hint.textContent = msg;
  }

  updateProgressUI(prog) {
    const fill = $("#final-build-progress-fill");
    const text = $("#final-build-progress-text");
    const count = $("#final-build-progress-count");
    const pctEl = $("#final-build-progress-pct");
    const phaseEl = $("#final-build-progress-phase");
    const detailEl = $("#final-build-progress-detail");
    const bar = $("#final-build-progress-bar");
    const wrap = $("#final-build-progress");
    const card = $("#final-build-progress-card");
    const stagesEl = $("#final-build-stages");

    const done = Number(prog.done || 0);
    const total = Number(prog.total || 0);
    const totalSafe = Math.max(1, total);
    const status = prog.status || "idle";

    // pct backend (fraction dans le job) prioritaire
    let pct =
      prog.pct != null && Number.isFinite(Number(prog.pct))
        ? Number(prog.pct)
        : status === "idle" && done === 0
          ? 0
          : Math.min(100, (done / totalSafe) * 100);
    if (status === "done") pct = 100;
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
      manual: "Config manuelle",
      grid: "Grid search",
      train: "Entraînement",
      save: "Sauvegarde",
      done: "Terminé",
      error: "Erreur",
      idle: "En attente",
    };
    const phase = prog.phase || status || "idle";
    const stageLabel = prog.stage_label || phaseMap[phase] || phase;
    if (phaseEl) {
      phaseEl.textContent = stageLabel;
      phaseEl.dataset.phase = phase;
    }

    if (text) {
      if (status === "running") {
        text.textContent =
          prog.message || prog.current_name || "Entraînement…";
      } else if (status === "done") {
        text.textContent = prog.message || "Terminé";
      } else if (status === "error") {
        text.textContent = prog.error || prog.message || "Erreur";
      } else {
        text.textContent = "En attente d’un build";
      }
    }

    // Bandeau étapes : Manuel / Grid
    if (stagesEl) {
      const nMan = Number(prog.n_manual || 0);
      const nGrid = Number(prog.n_grid || 0);
      const manDone = Number(prog.manual_done || 0);
      const gridDone = Number(prog.grid_done || 0);
      if (status === "idle" && !total) {
        stagesEl.innerHTML = "";
        stagesEl.classList.add("hidden");
      } else {
        stagesEl.classList.remove("hidden");
        const manActive = phase === "manual" || (status === "running" && prog.current_kind === "manual");
        const gridActive = phase === "grid" || (status === "running" && prog.current_kind === "grid");
        const manCls =
          status === "done" || manDone >= nMan
            ? "is-done"
            : manActive
              ? "is-active"
              : manDone > 0
                ? "is-done"
                : "";
        const gridCls =
          nGrid <= 0
            ? "is-skip"
            : status === "done" || gridDone >= nGrid
              ? "is-done"
              : gridActive
                ? "is-active"
                : "";
        stagesEl.innerHTML = `
          <div class="build-stage ${manCls}">
            <span class="build-stage-n">1</span>
            <div>
              <strong>Config manuelle</strong>
              <span>${manDone}/${Math.max(nMan, 1)} modèle(s)</span>
            </div>
          </div>
          <div class="build-stage ${gridCls}">
            <span class="build-stage-n">2</span>
            <div>
              <strong>Grid search</strong>
              <span>${
                nGrid > 0
                  ? `${gridDone}/${nGrid} combinaison(s)`
                  : "désactivé"
              }</span>
            </div>
          </div>`;
      }
    }

    if (detailEl) {
      const bits = [];
      if (prog.current_kind === "manual") bits.push("étape · config manuelle");
      if (prog.current_kind === "grid") bits.push("étape · grid search");
      if (prog.current_name) bits.push(`modèle · ${prog.current_name}`);
      if (prog.current_target) bits.push(`cible · ${prog.current_target}`);
      if (prog.job_fraction != null && status === "running") {
        const jf = Math.round(Number(prog.job_fraction) * 100);
        if (Number.isFinite(jf)) bits.push(`dans ce modèle ${jf} %`);
      }
      detailEl.textContent = bits.join("  ·  ");
    }

    if (wrap) {
      wrap.classList.toggle("is-running", status === "running");
      wrap.classList.toggle("is-done", status === "done");
      wrap.classList.toggle("is-error", status === "error");
    }
    if (card) card.classList.toggle("is-active", status === "running");
  }

  renderResults(prog) {
    const host = $("#final-build-results");
    const hint = $("#final-results-hint");
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
        const prog = await api.get("/api/model/final/build/progress");
        this.updateProgressUI(prog);
        if (prog.status === "done" || prog.status === "error") {
          this.stopPolling();
          this.renderResults(prog);
          const btn = $("#btn-final-build");
          if (btn) btn.disabled = false;
          if (prog.status === "done") {
            const best = (prog.results || []).find((r) => r.ok);
            toast.show(
              best
                ? `Build final terminé · meilleur : ${best.name} (rang 1)`
                : "Build final terminé"
            );
            const status = $("#final-status");
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
    const btn = $("#btn-final-build");
    const status = $("#final-status");
    const body = {
      model_name: ($("#final-name") && $("#final-name").value) || "xgb_final",
      xgb_params: this.getXgbParams(),
      grid_search: this.getGridSearch(),
      main_target:
        ($("#final-main-target") && $("#final-main-target").value) ||
        "montant_ventes",
      rank_metric:
        ($("#final-rank-metric") && $("#final-rank-metric").value) || "r2",
      async: true,
    };
    if (btn) btn.disabled = true;
    if (status) status.textContent = "Lancement du build final…";

    // scroller vers la carte progression
    const card = $("#final-build-progress-card");
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
      const res = await api.post("/api/model/final/build", body);
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
    const btn = $("#btn-final-build");
    if (btn) btn.addEventListener("click", () => this.build());
  }
}
