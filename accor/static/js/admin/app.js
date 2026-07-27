/**
 * Point d'entrée admin — Accor Data & Model Studio.
 *
 * Modules ES (pas de bundler) :
 *   shared/  → dom, api, toast, loading, format
 *   admin/   → state, nav, table, datasets,
 *              rod-sim, model build / explore / eval
 *
 * HTML : templates/index.html
 * API  : /api/datasets/* , /api/model/* , /api/rod/*
 * Doc  : README.md (sections Interface admin + Front)
 *
 * Debug navigateur : window.AccorAdmin
 */

import { $, debounce } from "../../shared/js/dom.js";
import { toast } from "../../shared/js/toast.js";
import { AdminState } from "./state.js";
import { NavController } from "./nav-controller.js";
import { TableRenderer } from "./table-renderer.js";
import { DatasetController } from "./dataset-controller.js";
import { ModelBuildPanel } from "./model-build-panel.js";
import { ModelExplorePanel } from "./model-explore-panel.js";
import { FinalModelBuildPanel } from "./final-model-build-panel.js";
import { FinalModelExplorePanel } from "./final-model-explore-panel.js";
import { ModelEvalPanel } from "./model-eval-panel.js";
import { RodSimPanel } from "./rod-sim-panel.js";
import { RodExcelPanel } from "./rod-excel-panel.js";

export class AdminApp {
  constructor() {
    this.state = new AdminState();
    this.els = this._bindDom();

    this.nav = new NavController(this.state, {
      onSelectDataset: (id) => this.datasets.selectDataset(id),
      onRodSim: () => this.rodSim.open(),
      onRodExcel: () => this.rodExcel.open(),
      onModelBuild: () => this.modelBuild.open(),
      onModelExplore: () => this.modelExplore.open(),
      onModelEval: () => this.modelEval.open(),
      onFinalBuild: () => this.finalBuild.open(),
      onFinalExplore: () => this.finalExplore.open(),
      onFinalEval: () => this.finalEval.open(),
    });

    this.table = new TableRenderer(this.state, this.els, {
      onEdit: (row, col, value, payload) =>
        this.datasets.onCellEdit(row, col, value, payload),
      onSelectionChange: () => this.datasets.updateDeleteBtn(),
    });

    this.datasets = new DatasetController(
      this.state,
      this.nav,
      this.table,
      this.els
    );
    this.rodSim = new RodSimPanel(this.state, this.nav);
    this.rodExcel = new RodExcelPanel(this.state, this.nav);
    this.modelBuild = new ModelBuildPanel(this.state, this.nav);
    this.modelExplore = new ModelExplorePanel(this.state, this.nav);
    this.finalBuild = new FinalModelBuildPanel(this.state, this.nav);
    this.finalExplore = new FinalModelExplorePanel(this.state, this.nav);
    this.modelEval = new ModelEvalPanel(this.state, this.nav, "intermediate");
    this.finalEval = new ModelEvalPanel(this.state, this.nav, "final");
  }

  _bindDom() {
    return {
      title: $("#panel-title"),
      desc: $("#panel-desc"),
      chipFile: $("#chip-file"),
      chipStats: $("#chip-stats"),
      chipDirty: $("#chip-dirty"),
      statusMsg: $("#status-msg"),
      thead: $("#table-head"),
      tbody: $("#table-body"),
      pagerInfo: $("#pager-info"),
      btnSave: $("#btn-save"),
      btnDelete: $("#btn-delete"),
      btnRebuild: $("#btn-rebuild"),
      searchInput: $("#search-input"),
      pageSizeSel: $("#page-size"),
    };
  }

  wireEvents() {
    const { els, datasets, state } = this;

    $("#btn-save")?.addEventListener("click", () => datasets.saveDirty());
    $("#btn-add")?.addEventListener("click", () => datasets.addRow());
    $("#btn-delete")?.addEventListener("click", () => datasets.deleteSelected());
    $("#btn-reload")?.addEventListener("click", () => datasets.reload());
    if (els.btnRebuild)
      els.btnRebuild.addEventListener("click", () => datasets.rebuildJoin());

    $("#btn-first")?.addEventListener("click", () => {
      state.page = 1;
      datasets.fetchPage();
    });
    $("#btn-prev")?.addEventListener("click", () => {
      state.page = Math.max(1, state.page - 1);
      datasets.fetchPage();
    });
    $("#btn-next")?.addEventListener("click", () => {
      if (!state.payload) return;
      state.page = Math.min(state.payload.total_pages, state.page + 1);
      datasets.fetchPage();
    });
    $("#btn-last")?.addEventListener("click", () => {
      if (!state.payload) return;
      state.page = state.payload.total_pages;
      datasets.fetchPage();
    });

    if (els.pageSizeSel) {
      els.pageSizeSel.addEventListener("change", () => {
        state.pageSize = Number(els.pageSizeSel.value) || 25;
        state.page = 1;
        datasets.fetchPage();
      });
    }

    if (els.searchInput) {
      const onSearch = debounce(() => {
        state.q = els.searchInput.value.trim();
        state.page = 1;
        datasets.fetchPage();
      }, 280);
      els.searchInput.addEventListener("input", onSearch);
    }

    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        if (state.panel === "table" && els.btnSave && !els.btnSave.disabled) {
          datasets.saveDirty();
        }
      }
    });

    this.nav.wire();
    this.rodSim.wire();
    this.rodExcel.wire();
    this.modelBuild.wire();
    this.modelExplore.wire();
    this.finalBuild.wire();
    this.finalExplore.wire();
    this.modelEval.wire();
    this.finalEval.wire();
  }

  async boot() {
    this.wireEvents();
    try {
      await this.datasets.loadDatasets();
    } catch (err) {
      toast.show(err.message, "err");
    }
  }
}

const app = new AdminApp();
app.boot();

// Debug console
window.AccorAdmin = app;
