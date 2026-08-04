/**
 * Panneau Model Explore.
 *
 * Structure du modèle (pas l’évaluation métier) :
 *   liste design, meta (lignes train/éval), importances, arbres (cumul
 *   boosting), SVG, deploy.
 * Les R²/RMSE métier vs réel → onglet Evaluation (model_eval).
 */

import { $, escapeHtml } from "../../shared/js/dom.js";
import { api } from "../../shared/js/api.js";
import { toast } from "../../shared/js/toast.js";
import { Format } from "../../shared/js/format.js";
import { TreeSvgRenderer } from "./tree-svg.js";

export class ModelExplorePanel {
  /**
   * @param {import('./state.js').AdminState} state
   * @param {import('./nav-controller.js').NavController} nav
   */
  constructor(state, nav) {
    this.state = state;
    this.nav = nav;
    this.treeSvg = new TreeSvgRenderer();
  }

  async open() {
    if (this._openBusy) return;
    if (
      this.state.panel === "model-explore" &&
      this.state.explore?.models?.length
    ) {
      this.nav.showModelExplorePanel();
      return;
    }
    if (!this.state.confirmLeaveDirty()) return;
    this._openBusy = true;
    this.nav.setNavBusy("explore", true);
    try {
      this.nav.showModelExplorePanel();
      await this.loadModels();
    } finally {
      this._openBusy = false;
      this.nav.setNavBusy("explore", false);
    }
  }

  async loadModels() {
    const status = $("#explore-status");
    if (status) status.textContent = "Chargement…";
    try {
      const data = await api.get("/api/model/list");
      this.state.explore.models = data.models || [];
      this.fillModelSelect(this.state.explore.models, data.top_model);
      this.updateBanner(data.last_trained, data.top_model);
      if (this.state.explore.models.length) {
        const sel = $("#explore-model-select");
        const id = (sel && sel.value) || this.state.explore.models[0].id;
        await this.loadModel(id);
      } else {
        this.clearUI();
        if (status)
          status.textContent = "Aucun modèle design — utilisez Model Build.";
      }
    } catch (err) {
      if (status) status.textContent = err.message;
      toast.show(err.message, "err");
    }
  }

  updateBanner(last, top) {
    const elL = $("#explore-chip-last");
    const elT = $("#explore-chip-top");
    if (elL) {
      elL.textContent = last
        ? `Dernier entraîné : ${last.name || last.id}`
        : "Dernier entraîné : —";
    }
    if (elT) {
      elT.textContent = top
        ? `Top model : #${top.rank} ${top.name || top.id}`
        : "Top model : —";
    }
  }

  fillModelSelect(models, top) {
    const sel = $("#explore-model-select");
    if (!sel) return;
    sel.innerHTML = "";
    if (!models.length) {
      sel.innerHTML = `<option value="">— aucun —</option>`;
      return;
    }
    models.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m.id || m.name;
      const r2 = m.score_r2 != null ? Number(m.score_r2).toFixed(3) : "—";
      opt.textContent = `#${m.rank} · ${m.name || m.id} · R² ${r2}`;
      sel.appendChild(opt);
    });
    if (top && (top.id || top.name)) {
      sel.value = top.id || top.name;
    }
  }

  clearUI() {
    ["explore-importance", "explore-tree-view", "explore-trees-table"].forEach(
      (id) => {
        const el = $("#" + id);
        if (!el) return;
        el.innerHTML = "—";
        el.classList.add("empty");
      }
    );
    const gm = $("#explore-global-metrics");
    if (gm) {
      gm.innerHTML = "";
      gm.classList.add("empty");
    }
  }

  async loadModel(modelId) {
    if (!modelId) return;
    const status = $("#explore-status");
    if (status) status.textContent = `Chargement ${modelId}…`;
    this.clearUI();
    this.state.explore.overview = null;
    this.state.explore.treeMetrics = null;
    try {
      const [overview, trees] = await Promise.all([
        api.get(`/api/model/${encodeURIComponent(modelId)}/explore`),
        api.get(`/api/model/${encodeURIComponent(modelId)}/trees`),
      ]);
      this.state.explore.overview = overview;
      this.state.explore.treeMetrics = trees;
      this.state.explore.currentId = modelId;

      this.updateBanner(overview.last_trained, overview.top_model);
      const chipS = $("#explore-chip-stats");
      if (chipS) {
        chipS.textContent = `${overview.n_features} feat · ${overview.n_trees} arbres · rank #${overview.rank || "—"}`;
      }
      this.renderModelMeta(overview);
      this.renderImportanceBars(overview.global_feature_importance || []);
      this.renderTreesTable(trees);
      const nTrees = Math.max(1, overview.n_trees || trees.n_trees || 1);
      const slider = $("#explore-tree-slider");
      if (slider) {
        slider.max = String(Math.max(0, nTrees - 1));
        slider.value = "0";
      }
      const lab = $("#explore-tree-label");
      if (lab) lab.textContent = "0";
      await this.loadTreeOnly(modelId, 0);
      if (status) status.textContent = "";
    } catch (err) {
      if (status) status.textContent = err.message;
      toast.show(err.message, "err");
      this.clearUI();
    }
  }

  /**
   * Meta structurelle du modèle (pas les scores métier — voir Evaluation).
   */
  renderModelMeta(ov) {
    const gm = $("#explore-global-metrics");
    if (!gm) return;
    gm.classList.remove("empty");
    gm.innerHTML = `
      <div class="metric-box"><span class="m-label">Features</span><span class="m-value">${ov.n_features ?? "—"}</span></div>
      <div class="metric-box"><span class="m-label">Arbres</span><span class="m-value">${ov.n_trees ?? "—"}</span></div>
      <div class="metric-box"><span class="m-label">Cibles</span><span class="m-value">${ov.n_targets ?? "—"}</span></div>
      <div class="metric-box"><span class="m-label">Train / hold-out</span><span class="m-value">${ov.n_train ?? "—"} / ${ov.n_eval ?? "—"}</span></div>
      <div class="metric-box"><span class="m-label">Année hold-out</span><span class="m-value">${ov.eval_year ?? "—"}</span></div>
      <div class="metric-box"><span class="m-label">Cible ranking</span><span class="m-value">${escapeHtml(ov.main_target || "—")}</span></div>
    `;
  }

  renderImportanceBars(items) {
    const host = $("#explore-importance");
    if (!host) return;
    if (!items || !items.length) {
      host.className = "imp-bars empty";
      host.textContent = "Pas d’importance disponible.";
      return;
    }
    const max = Math.max(...items.map((x) => Number(x.importance) || 0), 1e-12);
    host.className = "imp-bars";
    host.innerHTML = items
      .slice(0, 30)
      .map((x) => {
        const v = Number(x.importance) || 0;
        const pct = Math.max(2, (v / max) * 100);
        return `<div class="imp-row">
          <span class="imp-name" title="${escapeHtml(x.feature)}">${escapeHtml(x.feature)}</span>
          <span class="imp-val">${v.toFixed(4)}</span>
          <div class="imp-bar-track"><div class="imp-bar-fill" style="width:${pct}%"></div></div>
        </div>`;
      })
      .join("");
  }

  renderTreesTable(data) {
    const host = $("#explore-trees-table");
    const note = $("#explore-trees-note");
    if (note && data.note) note.textContent = data.note;
    if (!host) return;
    const rows = data.trees || [];
    if (!rows.length) {
      host.innerHTML = `<div class="empty">${escapeHtml(data.note || "Aucun arbre")}</div>`;
      return;
    }
    host.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Arbre</th><th>Profondeur</th><th>n features</th>
            <th>R² cumulé</th><th>RMSE cumulé</th><th>MAE</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (s) => `<tr data-tree="${s.tree_index}">
                <td>#${s.tree_index}</td>
                <td>${s.depth}</td>
                <td>${s.n_features}</td>
                <td>${Format.fixed(s.r2_cumulative)}</td>
                <td>${Format.fixed(s.rmse_cumulative)}</td>
                <td>${Format.fixed(s.mae_cumulative)}</td>
              </tr>`
            )
            .join("")}
          ${
            data.global
              ? `<tr><td><strong>Global</strong></td><td colspan="2">${data.n_trees} arbres</td>
              <td><strong>${Format.fixed(data.global.r2)}</strong></td>
              <td><strong>${Format.fixed(data.global.rmse)}</strong></td>
              <td><strong>${Format.fixed(data.global.mae)}</strong></td></tr>`
              : ""
          }
        </tbody>
      </table>`;
    host.querySelectorAll("tr[data-tree]").forEach((tr) => {
      tr.addEventListener("click", () => {
        const slider = $("#explore-tree-slider");
        if (slider) {
          slider.value = tr.dataset.tree;
          this.loadTreeOnly();
        }
      });
    });
  }

  async loadTreeOnly(forceModelId, forceTreeIdx) {
    const modelId =
      forceModelId ||
      (this.state.explore && this.state.explore.currentId) ||
      ($("#explore-model-select") && $("#explore-model-select").value);
    const slider = $("#explore-tree-slider");
    if (!modelId) return;
    const treeIdx =
      forceTreeIdx != null
        ? Number(forceTreeIdx)
        : Number((slider && slider.value) || 0);
    const lab = $("#explore-tree-label");
    if (lab) lab.textContent = String(treeIdx);
    if (slider && String(slider.value) !== String(treeIdx)) {
      slider.value = String(treeIdx);
    }
    const host = $("#explore-tree-view");
    if (host) {
      host.className = "tree-view empty";
      host.textContent = `Chargement arbre #${treeIdx}…`;
    }
    try {
      const tree = await api.get(
        `/api/model/${encodeURIComponent(modelId)}/tree?tree=${treeIdx}`
      );
      if (this.state.explore.currentId && this.state.explore.currentId !== modelId)
        return;
      this.treeSvg.render(host, tree);
      const meta = $("#explore-tree-meta");
      if (meta) {
        const rows =
          (this.state.explore.treeMetrics && this.state.explore.treeMetrics.trees) ||
          [];
        let best = null;
        rows.forEach((r) => {
          if (r.tree_index <= treeIdx) best = r;
        });
        meta.textContent = best
          ? `Modèle ${modelId} · arbre #${treeIdx} · profondeur ${tree.depth} · ${tree.n_features} features · R² cumulé ${Format.fixed(
              best.r2_cumulative
            )} · RMSE ${Format.fixed(best.rmse_cumulative)} (cible ${tree.target_name})`
          : `Modèle ${modelId} · arbre #${treeIdx} · profondeur ${tree.depth} · ${tree.n_features} features · cible ${tree.target_name}`;
      }
      document
        .querySelectorAll("#explore-trees-table tr[data-tree]")
        .forEach((tr) => {
          tr.classList.toggle("active", Number(tr.dataset.tree) === treeIdx);
        });
    } catch (err) {
      if (host) {
        host.className = "tree-view empty";
        host.textContent = err.message;
      }
      toast.show(err.message, "err");
    }
  }

  async deploy() {
    const sel = $("#explore-model-select");
    const name = sel && sel.value;
    if (!name) {
      toast.show("Aucun modèle sélectionné", "err");
      return;
    }
    try {
      const res = await api.post("/api/model/deploy", { model_name: name });
      toast.show(`Deploy OK · ${res.deployed_from} → deploy/model`);
    } catch (err) {
      toast.show(err.message, "err");
    }
  }

  wire() {
    const btnRefresh = $("#btn-explore-refresh");
    if (btnRefresh) btnRefresh.addEventListener("click", () => this.loadModels());
    const btnDeploy = $("#btn-explore-deploy");
    if (btnDeploy) btnDeploy.addEventListener("click", () => this.deploy());
    const exploreModelSel = $("#explore-model-select");
    if (exploreModelSel) {
      exploreModelSel.addEventListener("change", () => {
        this.loadModel(exploreModelSel.value);
      });
    }
    const exploreSlider = $("#explore-tree-slider");
    if (exploreSlider) {
      exploreSlider.addEventListener("input", () => {
        const lab = $("#explore-tree-label");
        if (lab) lab.textContent = exploreSlider.value;
      });
      exploreSlider.addEventListener("change", () => this.loadTreeOnly());
    }
  }
}
