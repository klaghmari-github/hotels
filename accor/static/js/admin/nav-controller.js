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
    this.viewRodExcel = $("#view-rod-excel");
    this.viewModelBuild = $("#view-model-build");
    this.viewModelExplore = $("#view-model-explore");
    this.viewFinalBuild = $("#view-final-build");
    this.viewFinalExplore = $("#view-final-explore");
    this.viewFinalEval = $("#view-final-eval");
    this.viewModelEval = $("#view-model-eval");
    this.navRodSim = $("#nav-rod-sim");
    this.navRodExcelSimply = $("#nav-rod-excel-simply");
    this.navRodExcelLiberty = $("#nav-rod-excel-liberty");
    this.navRodExcelConnected = $("#nav-rod-excel-connected");
    this.navSimVsIa = $("#nav-sim-vs-ia");
    this.navRodEval = $("#nav-rod-eval");
    this.navModelBuild = $("#nav-model-build");
    this.viewSimVsIa = $("#view-sim-vs-ia");
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

  _navButtonMap() {
    return {
      rod: this.navRodSim,
      "excel-simply": this.navRodExcelSimply,
      "excel-liberty": this.navRodExcelLiberty,
      "excel-connected": this.navRodExcelConnected,
      "sim-vs-ia": this.navSimVsIa,
      "rod-eval": this.navRodEval,
      build: this.navModelBuild,
      explore: this.navModelExplore,
      eval: this.navModelEval,
      "final-build": this.navFinalBuild,
      "final-explore": this.navFinalExplore,
      "final-eval": this.navFinalEval,
    };
  }

  setModelNavActive(which) {
    Object.entries(this._navButtonMap()).forEach(([key, el]) => {
      if (el) el.classList.toggle("active", which === key);
    });
  }

  /**
   * Désactive un bouton de nav pendant le chargement d'un panneau
   * (évite re-clic → rechargements multiples).
   * @param {string} key  rod | build | explore | eval | final-*
   * @param {boolean} busy
   */
  setNavBusy(key, busy) {
    const el = this._navButtonMap()[key];
    if (!el) return;
    el.disabled = !!busy;
    el.classList.toggle("is-loading", !!busy);
    el.setAttribute("aria-busy", busy ? "true" : "false");
    if (busy) el.setAttribute("title", "Chargement en cours…");
    else el.removeAttribute("title");
  }

  /**
   * Busy sur un bouton dataset (data-id).
   * @param {string|null} datasetId  null = clear all dataset busy
   * @param {boolean} busy
   */
  setDatasetNavBusy(datasetId, busy) {
    $$(".sidebar .nav-item[data-id]").forEach((el) => {
      const match = datasetId != null && el.dataset.id === datasetId;
      const on = !!busy && match;
      el.disabled = on;
      el.classList.toggle("is-loading", on);
      el.setAttribute("aria-busy", on ? "true" : "false");
    });
  }

  hideAllViews() {
    [
      this.viewTable,
      this.viewRodSim,
      this.viewRodExcel,
      this.viewSimVsIa,
      this.viewModelBuild,
      this.viewModelExplore,
      this.viewModelEval,
      this.viewFinalBuild,
      this.viewFinalExplore,
      this.viewFinalEval,
    ].forEach((v) => v && v.classList.add("hidden"));
  }

  showSimVsIaPanel() {
    this.state.panel = "sim-vs-ia";
    this.hideAllViews();
    if (this.viewSimVsIa) this.viewSimVsIa.classList.remove("hidden");
    this.clearDatasetNavActive();
    this.setModelNavActive("sim-vs-ia");
  }

  showRodEvalPanel() {
    // Même vue Compare (évaluation simulateur zone)
    this.showSimVsIaPanel();
    this.setModelNavActive("rod-eval");
  }

  clearDatasetNavActive() {
    $$(".sidebar .nav-item[data-id]").forEach((el) =>
      el.classList.remove("active")
    );
  }

  showTablePanel(datasetId = null) {
    this.state.panel = "table";
    this.hideAllViews();
    if (this.viewTable) this.viewTable.classList.remove("hidden");
    this.setModelNavActive(null);
    // Active le dataset dans la section Pilotes (si présent)
    if (datasetId) {
      $$(".sidebar .nav-item[data-id]").forEach((el) => {
        el.classList.toggle("active", el.dataset.id === datasetId);
      });
    }
  }

  showRodSimPanel() {
    this.state.panel = "rod-sim";
    this.hideAllViews();
    if (this.viewRodSim) this.viewRodSim.classList.remove("hidden");
    this.clearDatasetNavActive();
    this.setModelNavActive("rod");
  }

  showRodExcelPanel(concept = "SIMPLY") {
    const c = String(concept || "SIMPLY").toUpperCase();
    const key =
      c === "LIBERTY"
        ? "excel-liberty"
        : c === "CONNECTED"
          ? "excel-connected"
          : "excel-simply";
    this.state.panel = `rod-excel-${c.toLowerCase()}`;
    this.hideAllViews();
    if (this.viewRodExcel) this.viewRodExcel.classList.remove("hidden");
    this.clearDatasetNavActive();
    this.setModelNavActive(key);
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

  showModelEvalPanel() {
    this.state.panel = "model-eval";
    this.hideAllViews();
    if (this.viewModelEval) this.viewModelEval.classList.remove("hidden");
    this.clearDatasetNavActive();
    this.setModelNavActive("eval");
  }

  showFinalEvalPanel() {
    this.state.panel = "final-eval";
    this.hideAllViews();
    if (this.viewFinalEval) this.viewFinalEval.classList.remove("hidden");
    this.clearDatasetNavActive();
    this.setModelNavActive("final-eval");
  }

  wire() {
    if (this.navRodSim)
      this.navRodSim.addEventListener("click", this.handlers.onRodSim);
    if (this.navRodExcelSimply)
      this.navRodExcelSimply.addEventListener("click", () =>
        this.handlers.onRodExcel?.("SIMPLY")
      );
    if (this.navRodExcelLiberty)
      this.navRodExcelLiberty.addEventListener("click", () =>
        this.handlers.onRodExcel?.("LIBERTY")
      );
    if (this.navRodExcelConnected)
      this.navRodExcelConnected.addEventListener("click", () =>
        this.handlers.onRodExcel?.("CONNECTED")
      );
    if (this.navSimVsIa)
      this.navSimVsIa.addEventListener("click", () =>
        this.handlers.onSimVsIa?.()
      );
    if (this.navRodEval)
      this.navRodEval.addEventListener("click", () =>
        this.handlers.onRodEval?.()
      );
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
