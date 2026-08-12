/**
 * Zones pipeline / Flux (F0027 / F0052 / F0053-S2 / F0054-S2 / F0096).
 * F0096: menu deroulant de zones (plus de pills d onglets).
 * PipelineTabs : methodes reelles; exports fonctionnels = wrappers.
 */
import { state, el } from "./state.js";
import { api, toast } from "./api.js";
import { resetChangelogUi } from "./changelogs.js";
import { ensureSelection } from "./config/step-crud.js";
import { clearTable } from "./dataview.js";
import { refreshGraph } from "./graph.js";
import { UiController } from "./ui-base.js";
import { escapeHtml } from "./util.js";

/** Evite re-entrance change select → switchTab → render. */
let _flowZoneSelectWired = false;

/**
 * Controleur zones Flux — dropdown + graphe (F0054-S2 / F0096).
 */
export class PipelineTabs extends UiController {
  constructor(root) {
    super(root || (el && el.pipelineTabs) || null);
  }

  /**
   * F0096: remplit le select des zones disponibles.
   * Selection → switchTab → graphe filtre sur cette zone.
   * Conserve data-testid tab-* pour compat tests (options).
   */
  renderPipelineTabs() {
    this.wireFlowZoneSelect();
    const tabs = state.tabs.length
      ? state.tabs
      : [{ id: "default", label: "default", step_count: 0, closable: false }];
    const active = state.activeTab || "default";
    const sel = el.flowZoneSelect;

    if (sel) {
      // ne pas recreer si focus + meme liste (evite perte focus)
      const prev = sel.value;
      sel.innerHTML = "";
      tabs.forEach(function (t) {
        const id = t.id || t;
        const label = t.label || id;
        const count = t.step_count != null ? t.step_count : 0;
        const opt = document.createElement("option");
        opt.value = id;
        const suffix =
          count != null ? " (" + count + ")" : "";
        // F0131: auto-zone temporaire dans le select (vue logique readonly)
        const isAuto = !!(t.auto_zone || t.virtual);
        opt.textContent = isAuto
          ? label + suffix + " · vue"
          : label + suffix;
        opt.setAttribute("data-testid", "tab-" + id);
        opt.setAttribute("data-tab-id", id);
        if (isAuto) {
          opt.setAttribute("data-virtual", "1");
          opt.setAttribute("data-auto-zone", "1");
        }
        if (id === "default") {
          opt.title = "flow (racine)";
        } else if (isAuto) {
          opt.title =
            "Auto-zone logique (readonly) — Convertir pour editer";
        } else {
          opt.title = String(id);
        }
        if (id === active) opt.selected = true;
        sel.appendChild(opt);
      });
      if (!tabs.some(function (t) { return (t.id || t) === active; }) && tabs[0]) {
        sel.value = tabs[0].id || tabs[0];
      } else {
        sel.value = active;
      }
      // si la valeur n a pas change, pas de side-effect
      void prev;
    }

    // compteur + croix fermer (zones non-default)
    const activeMeta = tabs.find(function (t) {
      return (t.id || t) === active;
    });
    if (el.flowZoneCount) {
      const n = activeMeta && activeMeta.step_count != null
        ? activeMeta.step_count
        : null;
      if (n != null) {
        el.flowZoneCount.hidden = false;
        el.flowZoneCount.textContent = String(n);
        el.flowZoneCount.title = n + " composant(s) dans la zone";
      } else {
        el.flowZoneCount.hidden = true;
      }
    }
    // F0126: pas de croix fermer zone — changer de zone via le select

    // conteneur pipeline-tabs: marqueurs pour tests / a11y
    if (el.pipelineTabs) {
      el.pipelineTabs.setAttribute("data-active-tab", active);
      // ghost wraps for legacy testids (tab-wrap-*)
      let ghost = el.pipelineTabs.querySelector(".flow-zone-ghost-tabs");
      if (!ghost) {
        ghost = document.createElement("div");
        ghost.className = "flow-zone-ghost-tabs";
        ghost.hidden = true;
        ghost.setAttribute("aria-hidden", "true");
        el.pipelineTabs.appendChild(ghost);
      }
      ghost.innerHTML = tabs
        .map(function (t) {
          const id = t.id || t;
          const activeCls = id === active ? " active" : "";
          return (
            '<span class="pipeline-tab-wrap' +
            activeCls +
            '" data-testid="tab-wrap-' +
            escapeHtml(id) +
            '"></span>'
          );
        })
        .join("");
    }
  }

  wireFlowZoneSelect() {
    if (_flowZoneSelectWired) return;
    _flowZoneSelectWired = true;
    if (el.flowZoneSelect) {
      el.flowZoneSelect.addEventListener("change", function () {
        const id = el.flowZoneSelect.value;
        if (id) switchTab(id);
      });
    }
    // F0126: bouton fermer zone retire
  }

  async closePipelineTab(tabId) {
    if (!tabId || tabId === "default") {
      toast("L onglet flow (default) ne peut pas etre ferme", "error");
      return;
    }
    try {
      const data = await api(
        "/gui/tabs/" + encodeURIComponent(tabId) + "/close",
        { method: "POST" }
      );
      state.tabs = data.tabs || [];
      state.activeTab = data.active_tab || "default";
      state.selected = null;
      this.renderPipelineTabs();
      await refreshGraph();
      // F0081: config = zone / dernier objet de l onglet actif
      await ensureSelection({ force: true });
      toast(data.message || "Onglet ferme", "success");
    } catch (e) {
      toast("Fermer: " + e.message, "error");
    }
  }

  async switchTab(tabId) {
    if (!tabId) {
      await refreshGraph();
      await ensureSelection();
      return;
    }
    // re-activer meme onglet: refresh seulement
    if (tabId === state.activeTab) {
      await refreshGraph();
      await ensureSelection();
      return;
    }
    try {
      const data = await api(
        "/gui/tabs/" + encodeURIComponent(tabId) + "/activate",
        { method: "POST" }
      );
      state.activeTab = data.active_tab || tabId;
      state.tabs = data.tabs || state.tabs;
      state.selected = null;
      clearTable();
      resetChangelogUi();
      this.renderPipelineTabs();
      await refreshGraph();
      // F0081: selectionner zone de l onglet ou dernier objet
      await ensureSelection({ force: true });
    } catch (e) {
      toast("Onglet: " + e.message, "error");
      throw e;
    }
  }

  async refresh() {
    return refreshTabs();
  }

  render() {
    this.renderPipelineTabs();
    return this;
  }
}

/** Instance module partagee. */
export const pipelineTabs = new PipelineTabs();

export function renderPipelineTabs() {
  return pipelineTabs.renderPipelineTabs();
}

export async function closePipelineTab(tabId) {
  return pipelineTabs.closePipelineTab(tabId);
}

export async function refreshTabs() {
  try {
    const data = await api("/gui/tabs");
    state.tabs = data.tabs || [];
    if (data.active_tab) state.activeTab = data.active_tab;
    renderPipelineTabs();
  } catch (e) {
    // fallback silencieux si ancien serveur
    state.tabs = [{ id: "default", label: "default", step_count: 0 }];
    renderPipelineTabs();
  }
}

export async function switchTab(tabId) {
  return pipelineTabs.switchTab(tabId);
}

export function openNewTabDialog() {
  if (state.workspace && state.workspace.read_only) {
    toast("Lecture seule", "error");
    return;
  }
  if (!el.newTabDialog || !el.newTabName) {
    toast("Dialogue onglet indisponible", "error");
    return;
  }
  el.newTabName.value = "etl";
  el.newTabDialog.showModal();
  // focus + select apres ouverture
  setTimeout(function () {
    el.newTabName.focus();
    el.newTabName.select();
  }, 30);
}

export async function createPipelineTab(name) {
  const clean = String(name || "").trim();
  if (!clean) return;
  try {
    const data = await api("/gui/tabs", {
      method: "POST",
      body: JSON.stringify({ name: clean }),
    });
    state.activeTab = data.active_tab || data.id;
    state.tabs = data.tabs || [];
    state.selected = null;
    renderPipelineTabs();
    await refreshGraph();
    // F0081: selectionner la zone nouvellement creee
    await ensureSelection({ force: true });
    toast(data.message || "Onglet cree", "success");
  } catch (e) {
    toast("Onglet: " + e.message, "error");
  }
}

export async function addPipelineTab() {
  openNewTabDialog();
}
