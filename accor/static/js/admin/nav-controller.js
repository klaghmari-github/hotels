/**
 * Navigation sidebar admin.
 *
 * - Datasets (All / Pilotes)
 * - Simulateur ROD
 * - Modèles intermédiaires (Build / Explore)
 * - Modèle final (Build / Explore)
 * - Éval ML
 */

import { $, $$, escapeHtml } from "../../shared/js/dom.js";
import { ICONS, PINNED_TOP_IDS } from "./constants.js";

export class NavController {
  /**
   * @param {import('./state.js').AdminState} state
   * @param {object} handlers
   */
  constructor(state, handlers) {
    this.state = state;
    this.handlers = handlers;
    this.nav = $("#nav-tabs");
    this.navPinnedTop = $("#nav-pinned-top");
    this.viewTable = $("#view-table");
    this.viewRodSim = $("#view-rod-sim");
    this.viewModelBuild = $("#view-model-build");
    this.viewModelExplore = $("#view-model-explore");
    this.viewFinalBuild = $("#view-final-build");
    this.viewFinalExplore = $("#view-final-explore");
    this.viewModelEval = $("#view-model-eval");
    this.navRodSim = $("#nav-rod-sim");
    this.navModelBuild = $("#nav-model-build");
    this.navModelExplore = $("#nav-model-explore");
    this.navFinalBuild = $("#nav-final-build");
    this.navFinalExplore = $("#nav-final-explore");
    this.navFinalEval = $("#nav-final-eval");
    this.navModelEval = $("#nav-model-eval");
  }

  makeNavButton(ds) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "nav-item" + (ds.id === this.state.currentId ? " active" : "");
    btn.dataset.id = ds.id;
    btn.innerHTML = `
      <span class="nav-icon">${ICONS[ds.icon] || ICONS.table}</span>
      <span>
        <span class="nav-label">${escapeHtml(ds.label)}</span>
        <span class="nav-desc">${escapeHtml(ds.description || "")}</span>
      </span>`;
    btn.addEventListener("click", () => this.handlers.onSelectDataset(ds.id));
    return btn;
  }

  render() {
    if (this.navPinnedTop) this.navPinnedTop.innerHTML = "";
    if (this.nav) this.nav.innerHTML = "";

    const pinned = [];
    const middle = [];
    this.state.datasets.forEach((ds) => {
      if (PINNED_TOP_IDS.includes(ds.id)) pinned.push(ds);
      else middle.push(ds);
    });
    pinned.sort(
      (a, b) => PINNED_TOP_IDS.indexOf(a.id) - PINNED_TOP_IDS.indexOf(b.id)
    );
    pinned.forEach((ds) => {
      if (this.navPinnedTop) this.navPinnedTop.appendChild(this.makeNavButton(ds));
    });
    middle.forEach((ds) => {
      if (this.nav) this.nav.appendChild(this.makeNavButton(ds));
    });
  }

  setModelNavActive(which) {
    const map = {
      rod: this.navRodSim,
      build: this.navModelBuild,
      explore: this.navModelExplore,
      eval: this.navModelEval,
      "final-build": this.navFinalBuild,
      "final-explore": this.navFinalExplore,
      "final-eval": this.navFinalEval,
    };
    Object.entries(map).forEach(([key, el]) => {
      if (el) el.classList.toggle("active", which === key);
    });
  }

  hideAllViews() {
    [
      this.viewTable,
      this.viewRodSim,
      this.viewModelBuild,
      this.viewModelExplore,
      this.viewFinalBuild,
      this.viewFinalExplore,
      this.viewModelEval,
    ].forEach((v) => v && v.classList.add("hidden"));
  }

  clearDatasetNavActive() {
    $$(".sidebar .nav-item[data-id]").forEach((el) =>
      el.classList.remove("active")
    );
  }

  showTablePanel() {
    this.state.panel = "table";
    this.hideAllViews();
    if (this.viewTable) this.viewTable.classList.remove("hidden");
    this.setModelNavActive(null);
  }

  showRodSimPanel() {
    this.state.panel = "rod-sim";
    this.hideAllViews();
    if (this.viewRodSim) this.viewRodSim.classList.remove("hidden");
    this.clearDatasetNavActive();
    this.setModelNavActive("rod");
  }

  showModelBuildPanel() {
    this.state.panel = "model-build";
    this.hideAllViews();
    if (this.viewModelBuild) this.viewModelBuild.classList.remove("hidden");
    this.clearDatasetNavActive();
    this.setModelNavActive("build");
  }

  showModelExplorePanel() {
    this.state.panel = "model-explore";
    this.hideAllViews();
    if (this.viewModelExplore) this.viewModelExplore.classList.remove("hidden");
    this.clearDatasetNavActive();
    this.setModelNavActive("explore");
  }

  showFinalBuildPanel() {
    this.state.panel = "final-build";
    this.hideAllViews();
    if (this.viewFinalBuild) this.viewFinalBuild.classList.remove("hidden");
    this.clearDatasetNavActive();
    this.setModelNavActive("final-build");
  }

  showFinalExplorePanel() {
    this.state.panel = "final-explore";
    this.hideAllViews();
    if (this.viewFinalExplore) this.viewFinalExplore.classList.remove("hidden");
    this.clearDatasetNavActive();
    this.setModelNavActive("final-explore");
  }

  showModelEvalPanel(tier = "intermediate") {
    this.state.panel = tier === "final" ? "final-eval" : "model-eval";
    this.hideAllViews();
    if (this.viewModelEval) this.viewModelEval.classList.remove("hidden");
    this.clearDatasetNavActive();
    this.setModelNavActive(tier === "final" ? "final-eval" : "eval");
  }

  wire() {
    if (this.navRodSim)
      this.navRodSim.addEventListener("click", this.handlers.onRodSim);
    if (this.navModelBuild)
      this.navModelBuild.addEventListener("click", this.handlers.onModelBuild);
    if (this.navModelExplore)
      this.navModelExplore.addEventListener("click", this.handlers.onModelExplore);
    if (this.navModelEval)
      this.navModelEval.addEventListener("click", this.handlers.onModelEval);
    if (this.navFinalBuild)
      this.navFinalBuild.addEventListener("click", this.handlers.onFinalBuild);
    if (this.navFinalExplore)
      this.navFinalExplore.addEventListener("click", this.handlers.onFinalExplore);
    if (this.navFinalEval)
      this.navFinalEval.addEventListener("click", this.handlers.onFinalEval);
  }
}
