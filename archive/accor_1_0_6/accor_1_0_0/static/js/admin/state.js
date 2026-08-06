/**
 * Etat central de l'admin (mutable, une instance).
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
    /** @type {"table"|"model-build"|"model-explore"} */
    this.panel = "table";
    this.modelConfig = null;
    this.explore = {
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
