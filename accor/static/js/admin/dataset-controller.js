/**
 * Contrôleur datasets : fetch page, dirty save, add/delete, reload, rebuild.
 *
 * API : /api/datasets/*  (voir docs/API_ADMIN.md)
 * Rebuilds mappés via constants.REBUILD_MAP (sales, weather, all_data…).
 */

import { $, escapeHtml } from "../../shared/js/dom.js";
import { api } from "../../shared/js/api.js";
import { toast } from "../../shared/js/toast.js";
import { loading } from "../../shared/js/loading.js";
import {
  HEAVY_LOAD_SUB,
  REBUILD_MAP,
  REBUILD_TABS,
  REBUILD_TITLES,
} from "./constants.js";

export class DatasetController {
  /**
   * @param {import('./state.js').AdminState} state
   * @param {import('./nav-controller.js').NavController} nav
   * @param {import('./table-renderer.js').TableRenderer} table
   * @param {object} els
   */
  constructor(state, nav, table, els) {
    this.state = state;
    this.nav = nav;
    this.table = table;
    this.els = els;
  }

  loadingLabelsFor(datasetId) {
    const ds = this.state.datasets.find((d) => d.id === datasetId);
    const name = (ds && ds.label) || datasetId || "données";
    return {
      title: `Chargement · ${name}`,
      sub: HEAVY_LOAD_SUB[datasetId] || "Récupération de la page…",
    };
  }

  setDirtyUI() {
    const n = this.state.dirty.size;
    const { btnSave, chipDirty } = this.els;
    if (btnSave) btnSave.disabled = n === 0;
    if (chipDirty) {
      chipDirty.classList.toggle("hidden", n === 0);
      chipDirty.textContent =
        n === 0
          ? ""
          : `${n} ligne${n > 1 ? "s" : ""} modifiée${n > 1 ? "s" : ""}`;
    }
  }

  setStatus(msg) {
    if (this.els.statusMsg) this.els.statusMsg.textContent = msg || "";
  }

  updateDeleteBtn() {
    if (this.els.btnDelete)
      this.els.btnDelete.disabled = this.state.selected.size === 0;
  }

  onCellEdit(baseRow, col, value, payload) {
    const idx = baseRow._index;
    let row = this.state.dirty.get(idx);
    if (!row) {
      row = { _index: idx };
      payload.columns.forEach((c) => {
        row[c] = baseRow[c];
      });
      this.state.dirty.set(idx, row);
    }
    if ((payload.boolean_columns || []).includes(col)) {
      const n = Number(value);
      row[col] = Number.isFinite(n) ? n : value;
    } else if ((payload.array_columns || []).includes(col)) {
      row[col] = value;
    } else if (
      value !== "" &&
      !Number.isNaN(Number(value)) &&
      String(Number(value)) === String(value).trim()
    ) {
      row[col] = Number(value);
    } else {
      row[col] = value === "" ? null : value;
    }
    this.setDirtyUI();
    this.table.markRowDirty(idx);
  }

  async selectDataset(id, { keepPage = false } = {}) {
    if (this.state.currentId && this.state.currentId !== id) {
      if (!this.state.confirmLeaveDirty()) return;
    }
    this.nav.showTablePanel();
    if (this.state.currentId !== id) {
      this.state.clearEdits();
      if (!keepPage) this.state.page = 1;
      this.state.q = "";
      if (this.els.searchInput) this.els.searchInput.value = "";
    }
    this.state.currentId = id;

    const { btnRebuild } = this.els;
    if (btnRebuild) {
      btnRebuild.classList.toggle("hidden", !REBUILD_TABS.has(id));
      btnRebuild.title = REBUILD_TITLES[id] || "Reconstruire";
    }

    const ro =
      this.state.datasets.find((d) => d.id === id)?.readonly ||
      id === "sales" ||
      id === "concept_pilote";
    if ($("#btn-add")) $("#btn-add").classList.toggle("hidden", !!ro);
    if ($("#btn-save")) $("#btn-save").classList.toggle("hidden", !!ro);
    if ($("#btn-delete")) $("#btn-delete").classList.toggle("hidden", !!ro);

    this.nav.render();
    this.nav.setModelNavActive(null);
    await this.fetchPage();
  }

  async fetchPage({ silent = false } = {}) {
    if (!this.state.currentId) return;
    const labels = this.loadingLabelsFor(this.state.currentId);
    const { title, desc, chipFile, chipStats, pagerInfo, tbody } = this.els;

    if (!silent) {
      loading.show(labels.title, labels.sub);
      if (tbody) {
        tbody.innerHTML = `<tr><td class="empty-state empty-loading">Chargement de <strong>${escapeHtml(
          labels.title.replace(/^Chargement · /, "")
        )}</strong>…</td></tr>`;
      }
    }
    this.setStatus("Chargement…");
    try {
      const payload = await api.get(`/api/datasets/${this.state.currentId}`, {
        page: this.state.page,
        page_size: this.state.pageSize,
        q: this.state.q || undefined,
      });
      this.state.payload = payload;
      if (title) title.textContent = payload.label;
      if (desc) desc.textContent = payload.description || "";
      if (chipFile) chipFile.textContent = payload.filename;
      if (chipStats)
        chipStats.textContent = `${payload.total_rows} lignes · page ${payload.page}/${payload.total_pages}`;
      this.table.render(payload);
      if (pagerInfo)
        pagerInfo.textContent = `Page ${payload.page} / ${payload.total_pages} · ${payload.total_rows} lignes`;
      this.setStatus("");
      this.setDirtyUI();
      this.updateDeleteBtn();
    } catch (err) {
      if (tbody)
        tbody.innerHTML = `<tr><td class="empty-state">Erreur : ${escapeHtml(err.message)}</td></tr>`;
      this.setStatus(err.message);
      toast.show(err.message, "err");
    } finally {
      if (!silent) loading.hide();
    }
  }

  async saveDirty() {
    if (!this.state.dirty.size) return;
    const rows = Array.from(this.state.dirty.values());
    this.setStatus("Enregistrement…");
    if (this.els.btnSave) this.els.btnSave.disabled = true;
    try {
      const res = await api.put(`/api/datasets/${this.state.currentId}/rows`, {
        rows,
      });
      this.state.dirty.clear();
      this.setDirtyUI();
      toast.show(
        `Enregistré · ${res.updated} ligne(s) → ${String(res.saved_to || "")
          .split("/")
          .pop()}`
      );
      await this.fetchPage();
    } catch (err) {
      toast.show(err.message, "err");
      this.setDirtyUI();
    }
  }

  async addRow() {
    try {
      await api.post(`/api/datasets/${this.state.currentId}/rows`, { values: {} });
      toast.show("Ligne ajoutée");
      if (this.state.payload) {
        const total = (this.state.payload.total_rows || 0) + 1;
        this.state.page = Math.max(1, Math.ceil(total / this.state.pageSize));
      }
      await this.fetchPage();
    } catch (err) {
      toast.show(err.message, "err");
    }
  }

  async deleteSelected() {
    if (!this.state.selected.size) return;
    if (!confirm(`Supprimer ${this.state.selected.size} ligne(s) ?`)) return;
    try {
      await api.delete(`/api/datasets/${this.state.currentId}/rows`, {
        indices: Array.from(this.state.selected),
      });
      this.state.clearEdits();
      toast.show("Lignes supprimées");
      await this.fetchPage();
    } catch (err) {
      toast.show(err.message, "err");
    }
  }

  async reload() {
    if (this.state.dirty.size && !confirm("Recharger et perdre les modifications ?"))
      return;
    loading.show("Rechargement…", "Lecture du fichier Excel depuis le disque");
    try {
      await api.post(`/api/datasets/${this.state.currentId}/reload`);
      this.state.clearEdits();
      toast.show("Fichier Excel rechargé");
      await this.fetchPage({ silent: true });
    } catch (err) {
      toast.show(err.message, "err");
    } finally {
      loading.hide();
    }
  }

  async rebuildJoin() {
    if (
      this.state.dirty.size &&
      !confirm("Les modifications non sauvées seront perdues. Continuer ?")
    ) {
      return;
    }
    const id = this.state.currentId;
    const cfg = REBUILD_MAP[id];
    if (!cfg) {
      toast.show("Reconstruire non disponible sur cet onglet", "err");
      return;
    }
    this.setStatus(cfg.msg);
    if (this.els.btnRebuild) this.els.btnRebuild.disabled = true;
    loading.show("Reconstruction…", cfg.msg);
    try {
      const res = await api.post(cfg.url, cfg.body || {});
      this.state.clearEdits();
      toast.show(
        `Reconstruit · ${res.rows} lignes · ${
          res.n_columns || (res.columns || []).length
        } colonnes`
      );
      this.state.page = 1;
      await api.post(`/api/datasets/${id}/reload`);
      await this.fetchPage({ silent: true });
      this.setStatus("");
    } catch (err) {
      toast.show(err.message, "err");
      this.setStatus(err.message);
    } finally {
      loading.hide();
      if (this.els.btnRebuild) this.els.btnRebuild.disabled = false;
    }
  }

  async loadDatasets() {
    const data = await api.get("/api/datasets");
    this.state.datasets = data.datasets || [];
    this.nav.render();
    if (this.state.datasets.length) {
      await this.selectDataset(this.state.datasets[0].id);
    }
  }
}
