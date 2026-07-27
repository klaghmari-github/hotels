/**
 * État central de l'admin (une instance mutable par session page).
 *
 * datasets, currentId, page/pageSize/q, payload page courante,
 * dirty (Map index → row patch), selected indices, panel courant
 * (table | rod-sim | model-build | model-explore | model-eval).
 *
 * confirmLeaveDirty() — garde-fou avant de quitter un dataset modifié.
 */

export class AdminState {
  constructor() {
    this.datasets = [];
    this.currentId = null;
    this.page = 1;
    this.pageSize = 25;
    this.q = "";
    this.payload = null;
    /** @type {Map<number, object>} */
    this.dirty = new Map();
    /** @type {Set<number>} */
    this.selected = new Set();
    /** @type {string} */
    this.panel = "table";
    this.modelConfig = null;
    this.explore = {
      models: [],
      overview: null,
      treeMetrics: null,
      impScope: "global",
      currentId: null,
    };
    this.finalExplore = {
      models: [],
      overview: null,
      treeMetrics: null,
      impScope: "global",
      currentId: null,
    };
  }

  clearEdits() {
    this.dirty.clear();
    this.selected.clear();
  }

  confirmLeaveDirty(message) {
    if (!this.dirty.size) return true;
    return confirm(
      message || "Des modifications non enregistrées seront perdues. Continuer ?"
    );
  }
}
