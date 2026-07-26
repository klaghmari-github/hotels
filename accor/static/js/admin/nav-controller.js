/**
 * Navigation sidebar admin.
 *
 * - Datasets (All / Pilotes)
 * - Simulateur ROD
 * - Modèle (Build / Explore / Éval ML)
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
    this.viewModelEval = $("#view-model-eval");
    this.navRodSim = $("#nav-rod-sim");
    this.navModelBuild = $("#nav-model-build");
    this.navModelExplore = $("#nav-model-explore");
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
    if (this.navRodSim)
      this.navRodSim.classList.toggle("active", which === "rod");
    if (this.navModelBuild)
      this.navModelBuild.classList.toggle("active", which === "build");
    if (this.navModelExplore)
      this.navModelExplore.classList.toggle("active", which === "explore");
    if (this.navModelEval)
      this.navModelEval.classList.toggle("active", which === "eval");
  }

  hideAllViews() {
    if (this.viewTable) this.viewTable.classList.add("hidden");
    if (this.viewRodSim) this.viewRodSim.classList.add("hidden");
    if (this.viewModelBuild) this.viewModelBuild.classList.add("hidden");
    if (this.viewModelExplore) this.viewModelExplore.classList.add("hidden");
    if (this.viewModelEval) this.viewModelEval.classList.add("hidden");
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

  showModelEvalPanel() {
    this.state.panel = "model-eval";
    this.hideAllViews();
    if (this.viewModelEval) this.viewModelEval.classList.remove("hidden");
    this.clearDatasetNavActive();
    this.setModelNavActive("eval");
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
  }
}
