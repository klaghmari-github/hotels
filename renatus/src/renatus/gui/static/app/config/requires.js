/**
 * Requires view/edit (F0054-S2 / F0095).
 * View: chips des required. Edit: popup graphe zone (dropdown + dblclick).
 */
import { state, el } from "../state.js";
import { api, toast } from "../api.js";
import { switchBottomTab } from "../changelogs.js";
import { confirmDialog } from "../confirm-dialog.js";
import { loadDataView } from "../dataview.js";
import { typeColor, typeFill, typeIconSvg, typeIconSvgGroup } from "../icons.js";
import { switchTab } from "../tabs.js";
import { escapeHtml } from "../util.js";
import { formToYamlEditor } from "./form-sync.js";
import { selectStep } from "./step-crud.js";

/** Snapshot requires a l ouverture du dialog (Annuler). */
let _requiresEditSnapshot = null;
/** Zone active dans le dialog. */
let _requiresEditZone = "default";
/** Selection en cours dans le dialog (avant OK). */
let _requiresEditList = [];

export function splitRequires(s) {
  return String(s || "")
    .split(",")
    .map(function (x) { return x.trim(); })
    .filter(Boolean);
}

/**
 * Requires selectionnees — source de verite = miroir hidden (F0095).
 * Plus de checkboxes dans le panneau Config.
 */
export function getSelectedRequires() {
  return splitRequires(el.cfgRequires ? el.cfgRequires.value : "");
}

export function setRequiresMirror(list) {
  const arr = Array.isArray(list) ? list : splitRequires(list);
  if (el.cfgRequires) {
    el.cfgRequires.value = arr.join(", ");
  }
  return arr;
}

export function refreshStepNamesDatalist() {
  if (!el.stepNamesList) return;
  // F0039: toutes les steps du projet (pas seulement l onglet courant)
  const nodes = state.allSteps.length
    ? state.allSteps
    : state.graph.nodes || [];
  el.stepNamesList.innerHTML = nodes
    .map(function (n) {
      return '<option value="' + escapeHtml(n.id) + '"></option>';
    })
    .join("");
}

export function lookupStepMeta(stepId) {
  const catalog = state.allSteps.length
    ? state.allSteps
    : state.graph.nodes || [];
  for (let i = 0; i < catalog.length; i++) {
    if (catalog[i] && catalog[i].id === stepId) return catalog[i];
  }
  return { id: stepId, label: stepId, type: "?", tab: null };
}

/** F0042: met a jour le label d un step dans le cache UI (graphe + catalog). */
export function patchStepLabelInState(stepId, newLabel) {
  if (!stepId) return;
  const lab = newLabel || stepId;
  function patch(list) {
    if (!list) return;
    for (let i = 0; i < list.length; i++) {
      if (list[i] && list[i].id === stepId) {
        list[i].label = lab;
      }
    }
  }
  patch(state.allSteps);
  patch(state.graph.nodes);
}

/**
 * Ouvre la config d un composant require (F0040).
 * requires = id de step YAML (pas le nom de relation SQL).
 * Bascule d onglet si le composant est ailleurs.
 */
export async function openRequireComponent(stepId) {
  if (!stepId) return;
  const meta = lookupStepMeta(stepId);
  const tab = meta.tab || "default";
  try {
    if (tab !== (state.activeTab || "default")) {
      await switchTab(tab);
    }
    await selectStep(stepId);
    // rester sur Data preview pour voir aussi le resultat
    if (state.bottomTab === "changelogs") {
      switchBottomTab("data-preview");
    }
  } catch (e) {
    toast("Ouvrir require: " + e.message, "error");
  }
}

/**
 * Chips des requires selectionnees — liens vers les composants (F0040 / F0095).
 * Mode view: label + logo type; clic ouvre le composant.
 * @param {string[]} selectedList
 * @param {{container?: HTMLElement, removable?: boolean, onRemove?: function}|undefined} opts
 */
export function renderRequiresSelected(selectedList, opts) {
  const options = opts || {};
  const host = options.container || el.cfgRequiresSelected;
  if (!host) return;
  const list = Array.isArray(selectedList) ? selectedList : [];
  host.innerHTML = "";
  const isMainView = host === el.cfgRequiresSelected;
  if (!list.length) {
    if (isMainView) {
      host.hidden = true;
      if (el.requiresEmpty) {
        el.requiresEmpty.hidden = false;
        el.requiresEmpty.textContent = "—";
      }
    }
    return;
  }
  if (isMainView) {
    host.hidden = false;
    if (el.requiresEmpty) el.requiresEmpty.hidden = true;
  }
  list.forEach(function (id) {
    const meta = lookupStepMeta(id);
    const label = meta.label || id;
    const wrap = document.createElement("span");
    wrap.className = "require-chip-wrap";
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "require-chip";
    chip.setAttribute("data-testid", "require-chip-" + id);
    chip.setAttribute("data-require-id", id);
    const relSql = meta.relation_name || meta.name || "";
    chip.innerHTML =
      typeIconSvg(meta.type || "table", {
        size: 12,
        className: "require-chip-icon",
        strokeWidth: 2,
      }) +
      '<span class="require-chip-label require-link" data-require-link="' +
      escapeHtml(id) +
      '">' +
      escapeHtml(label) +
      "</span>" +
      (meta.type
        ? '<span class="require-chip-type">' +
          escapeHtml(meta.type) +
          "</span>"
        : "");
    chip.title =
      "Composant " +
      label +
      (relSql ? " — SQL " + relSql : "") +
      " (requires = id " +
      id +
      ")";
    chip.addEventListener("click", function (ev) {
      ev.preventDefault();
      if (options.removable) return; // dans le dialog: croix pour retirer
      openRequireComponent(id);
    });
    wrap.appendChild(chip);
    if (options.removable) {
      const rm = document.createElement("button");
      rm.type = "button";
      rm.className = "require-chip-remove";
      rm.setAttribute("data-testid", "require-remove-" + id);
      rm.title = "Retirer des requires";
      rm.setAttribute("aria-label", "Retirer " + label);
      rm.textContent = "×";
      rm.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (typeof options.onRemove === "function") {
          options.onRemove(id);
        } else {
          removeRequire(id);
        }
      });
      wrap.appendChild(rm);
    }
    host.appendChild(wrap);
  });
}

/**
 * Mode view Requires (F0095): chips des required uniquement, pas de checkboxes.
 * Le picker legacy reste cache; edition via popup (openRequiresEditor).
 */
export function renderRequiresPicker(selected) {
  const selectedList = Array.isArray(selected)
    ? selected.slice()
    : splitRequires(selected);
  setRequiresMirror(selectedList);
  renderRequiresSelected(selectedList);
  // F0095: panneau config = view only (pas de liste a cocher)
  if (el.cfgRequiresPicker) {
    el.cfgRequiresPicker.innerHTML = "";
    el.cfgRequiresPicker.hidden = true;
  }
  if (el.requiresEmpty) {
    el.requiresEmpty.hidden = selectedList.length > 0;
    if (!selectedList.length) el.requiresEmpty.textContent = "—";
  }
}

/** Ajoute un step id aux requires (YAML = id, pas label / SQL). */
export function addRequire(stepId) {
  if (!stepId || stepId === state.selected) return getSelectedRequires();
  const reqs = getSelectedRequires();
  if (reqs.indexOf(stepId) >= 0) return reqs;
  reqs.push(stepId);
  setRequiresMirror(reqs);
  renderRequiresSelected(reqs);
  formToYamlEditor();
  previewRequireSource(stepId);
  return reqs;
}

/** Retire un require par id. */
export function removeRequire(stepId) {
  const reqs = getSelectedRequires().filter(function (id) {
    return id !== stepId;
  });
  setRequiresMirror(reqs);
  renderRequiresSelected(reqs);
  formToYamlEditor();
  return reqs;
}

/**
 * Compat F0019: toggle require (ex-checkbox).
 * @param {string} stepId
 * @param {boolean} checked
 */
export function onRequireCheckboxChange(stepId, checked) {
  if (checked) addRequire(stepId);
  else removeRequire(stepId);
}

/**
 * Affiche le resultat d une source prerequis dans la zone DataView (F0019).
 */
export async function previewRequireSource(name) {
  if (!name) return;
  state.dataviewSource = name;
  state.dataviewIsPrereq = true;
  await loadDataView(name, false, { asPrereq: true });
}

/** Liste des zones (onglets) pour le select du dialog. */
export function listRequireZones() {
  const tabs = state.tabs && state.tabs.length
    ? state.tabs
    : [{ id: "default", label: "default" }];
  const seen = {};
  const out = [];
  tabs.forEach(function (t) {
    const id = t && (t.id || t);
    if (!id || seen[id]) return;
    seen[id] = true;
    out.push({
      id: String(id),
      label: String((t && t.label) || id),
    });
  });
  // zones presentes dans le catalog mais pas encore en onglet ouvert
  (state.allSteps || []).forEach(function (n) {
    if (!n || n.type !== "zone") return;
    const zid = n.zone_path || n.id;
    if (!zid || seen[zid]) return;
    seen[zid] = true;
    out.push({ id: String(zid), label: String(n.label || zid) });
  });
  return out;
}

/**
 * F0095: ouvre le dialog d edition Requires (graphe zone non editable).
 */
export async function openRequiresEditor() {
  const dlg = el.requiresEditDialog;
  if (!dlg || typeof dlg.showModal !== "function") {
    toast("Dialog Requires indisponible", "error");
    return;
  }
  _requiresEditSnapshot = getSelectedRequires().slice();
  _requiresEditList = _requiresEditSnapshot.slice();
  _requiresEditZone = state.activeTab || "default";
  fillRequiresZoneSelect();
  renderRequiresEditSelected();
  await loadRequiresEditZone(_requiresEditZone);
  try {
    dlg.showModal();
  } catch (e) {
    toast("Requires: " + e.message, "error");
  }
}

function fillRequiresZoneSelect() {
  const sel = el.requiresZoneSelect;
  if (!sel) return;
  const zones = listRequireZones();
  sel.innerHTML = zones
    .map(function (z) {
      return (
        '<option value="' +
        escapeHtml(z.id) +
        '">' +
        escapeHtml(z.label) +
        "</option>"
      );
    })
    .join("");
  if (!zones.some(function (z) { return z.id === _requiresEditZone; })) {
    _requiresEditZone = zones[0] ? zones[0].id : "default";
  }
  sel.value = _requiresEditZone;
}

function renderRequiresEditSelected() {
  if (!el.requiresEditSelected) return;
  renderRequiresSelected(_requiresEditList, {
    container: el.requiresEditSelected,
    removable: true,
    onRemove: function (id) {
      _requiresEditList = _requiresEditList.filter(function (x) {
        return x !== id;
      });
      renderRequiresEditSelected();
      // re-style nodes in canvas
      markRequiresEditNodes();
    },
  });
}

async function loadRequiresEditZone(zoneId) {
  const zid = String(zoneId || "default");
  _requiresEditZone = zid;
  const canvas = el.requiresEditCanvas;
  if (!canvas) return;
  canvas.innerHTML =
    '<p class="empty-msg compact">Chargement…</p>';
  try {
    // import dynamique: evite cycle graph.js ↔ requires.js
    const graphMod = await import("../graph.js");
    const q = "?tab=" + encodeURIComponent(zid);
    const g = await api("/gui/graph" + q);
    if (g.catalog && g.catalog.length) {
      state.allSteps = g.catalog;
    }
    const nodes = (g.nodes || []).filter(function (n) {
      return n && n.id && n.id !== state.selected && !n.external;
    });
    const edges = (g.edges || []).filter(function (e) {
      const from = e.from || e.from_;
      return (
        nodes.some(function (n) { return n.id === from; }) &&
        nodes.some(function (n) { return n.id === e.to; })
      );
    });
    renderRequiresEditGraph(nodes, edges, graphMod);
  } catch (e) {
    canvas.innerHTML =
      '<p class="empty-msg compact">Erreur: ' +
      escapeHtml(e.message || String(e)) +
      "</p>";
  }
}

/**
 * Graphe lecture seule dans le dialog (meme look que Flux, non editable).
 * Double-clic → ajoute l id aux requires (stocke id YAML).
 */
function renderRequiresEditGraph(nodes, edges, graphMod) {
  const canvas = el.requiresEditCanvas;
  if (!canvas) return;
  if (!nodes.length) {
    canvas.innerHTML =
      '<p class="empty-msg compact">Aucun composant dans cette zone</p>';
    return;
  }
  const layoutNodes = graphMod.layoutNodes;
  const truncateNodeText = graphMod.truncateNodeText;
  const pos = layoutNodes(nodes, edges);
  const nodeW = 148;
  const nodeH = 40;
  const textX = 42;
  const textMaxW = nodeW - textX - 8;
  const labelY = Math.round(nodeH / 2 + 4);
  let maxX = 220, maxY = 140;
  nodes.forEach(function (n) {
    const p = pos[n.id] || { x: 40, y: 40 };
    maxX = Math.max(maxX, p.x + nodeW + 24);
    maxY = Math.max(maxY, p.y + nodeH + 24);
  });
  const selectedSet = {};
  _requiresEditList.forEach(function (id) {
    selectedSet[id] = true;
  });
  let svg =
    '<svg class="graph-svg requires-edit-svg" width="' +
    maxX +
    '" height="' +
    maxY +
    '"><defs>' +
    '<marker id="req-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">' +
    '<path d="M0,0 L6,3 L0,6 Z" fill="#4b5d78"/></marker>' +
    "</defs>";
  edges.forEach(function (e) {
    const from = e.from || e.from_;
    const a = pos[from], b = pos[e.to];
    if (!a || !b) return;
    const x1 = a.x + nodeW, y1 = a.y + nodeH / 2;
    const x2 = b.x, y2 = b.y + nodeH / 2;
    svg +=
      '<path class="edge" d="M' +
      x1 +
      "," +
      y1 +
      " C" +
      (x1 + 36) +
      "," +
      y1 +
      " " +
      (x2 - 36) +
      "," +
      y2 +
      " " +
      x2 +
      "," +
      y2 +
      '"/>';
  });
  nodes.forEach(function (n) {
    const p = pos[n.id] || { x: 40, y: 40 };
    const type = n.type || "table";
    const c = typeColor(type);
    const fill = typeFill(type);
    const fullName = n.label || n.id || "";
    const shortName = truncateNodeText(fullName, textMaxW, 12);
    const isReq = !!selectedSet[n.id];
    const iconY = Math.round((nodeH - 28) / 2);
    // stocke l id step (pas le label) — F0040
    const stepId = n.id;
    svg +=
      '<g class="node node-' +
      escapeHtml(type) +
      (isReq ? " is-required" : "") +
      ' require-pick-node" data-id="' +
      escapeHtml(stepId) +
      '" data-testid="require-pick-' +
      escapeHtml(stepId) +
      '" transform="translate(' +
      p.x +
      "," +
      p.y +
      ')">' +
      "<title>" +
      escapeHtml(
        fullName +
          " — double-clic pour " +
          (isReq ? "retirer" : "ajouter") +
          " (id " +
          stepId +
          ")"
      ) +
      "</title>" +
      '<rect class="node-bg" width="' +
      nodeW +
      '" height="' +
      nodeH +
      '" style="stroke:' +
      c +
      ";fill:" +
      fill +
      '"/>' +
      '<rect class="node-icon-bg" x="6" y="' +
      iconY +
      '" width="28" height="28" rx="6" style="fill:' +
      c +
      ';opacity:0.18"/>' +
      typeIconSvgGroup(type, 9, iconY + 3, 0.8) +
      '<text class="nname" x="' +
      textX +
      '" y="' +
      labelY +
      '">' +
      escapeHtml(shortName) +
      "</text></g>";
  });
  svg += "</svg>";
  canvas.innerHTML = svg;
  canvas.querySelectorAll(".require-pick-node").forEach(function (g) {
    const icon = g.querySelector(".node-icon");
    const id = g.getAttribute("data-id");
    const node = nodes.find(function (n) { return n.id === id; });
    if (icon && node) {
      icon.style.color = typeColor(node.type);
      icon.setAttribute("stroke", typeColor(node.type));
    }
    g.addEventListener("dblclick", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      toggleRequireInEditor(id);
    });
  });
}

function toggleRequireInEditor(stepId) {
  if (!stepId || stepId === state.selected) return;
  const idx = _requiresEditList.indexOf(stepId);
  if (idx >= 0) {
    _requiresEditList.splice(idx, 1);
  } else {
    // stocke l id YAML (pas le label)
    _requiresEditList.push(stepId);
  }
  renderRequiresEditSelected();
  markRequiresEditNodes();
}

function markRequiresEditNodes() {
  const canvas = el.requiresEditCanvas;
  if (!canvas) return;
  const set = {};
  _requiresEditList.forEach(function (id) {
    set[id] = true;
  });
  canvas.querySelectorAll(".require-pick-node").forEach(function (g) {
    const id = g.getAttribute("data-id");
    g.classList.toggle("is-required", !!set[id]);
  });
}

/** Intent OK/cancel avant close (method=dialog returnValue parfois vide). */
let _requiresEditIntent = null;

/**
 * Commit ou annule le dialog Requires.
 * A0013: await persist + refreshGraph pour mettre a jour les aretes Flux.
 * @param {"ok"|"cancel"} result
 */
export async function closeRequiresEditor(result) {
  const dlg = el.requiresEditDialog;
  // eviter double commit si close event re-entre
  if (_requiresEditSnapshot == null) {
    return;
  }
  const snap = _requiresEditSnapshot;
  const listOk = _requiresEditList.slice();
  _requiresEditSnapshot = null;
  _requiresEditIntent = null;

  if (result === "ok") {
    setRequiresMirror(listOk);
    renderRequiresSelected(listOk);
    formToYamlEditor();
    try {
      // cancel debounce + PUT immediat (requires du miroir)
      const { persistCurrentStep } = await import("./step-crud.js");
      await persistCurrentStep({
        silent: true,
        stepId: state.selected,
        refreshGraph: true,
      });
      if (listOk.length) {
        previewRequireSource(listOk[listOk.length - 1]);
      }
    } catch (e) {
      toast("Requires: " + (e && e.message ? e.message : e), "error");
    }
  } else {
    // restaurer snapshot
    setRequiresMirror(snap || []);
    renderRequiresSelected(snap || []);
    formToYamlEditor();
  }
  if (dlg && dlg.open) {
    try {
      dlg.close();
    } catch (_) {}
  }
}

/** Wire select zone + form submit (appele au bootstrap). */
export function wireRequiresEditor() {
  if (el.requiresZoneSelect) {
    el.requiresZoneSelect.addEventListener("change", function () {
      loadRequiresEditZone(el.requiresZoneSelect.value);
    });
  }
  if (el.requiresEditForm) {
    el.requiresEditForm.addEventListener("submit", function (ev) {
      const submitter = ev.submitter;
      _requiresEditIntent =
        submitter && submitter.value ? submitter.value : "ok";
    });
  }
  if (el.requiresEditDialog) {
    el.requiresEditDialog.addEventListener("close", function () {
      const rv =
        _requiresEditIntent ||
        el.requiresEditDialog.returnValue ||
        "cancel";
      _requiresEditIntent = null;
      if (_requiresEditSnapshot != null) {
        // fire-and-follow: async close
        closeRequiresEditor(rv === "ok" ? "ok" : "cancel");
      }
    });
  }
}

/**
 * Dependances inverses (F0041): qui a ce step dans requires.
 * Lecture seule, non stocke — clic = ouvrir le composant dependant.
 */
export function renderDependents(list) {
  if (!el.cfgDependents) return;
  const items = Array.isArray(list) ? list : [];
  el.cfgDependents.innerHTML = "";
  if (el.fieldDependents) el.fieldDependents.hidden = false;
  if (el.dependentsEmpty) {
    el.dependentsEmpty.hidden = items.length > 0;
  }
  if (!items.length) return;
  items.forEach(function (d) {
    const id = d.id || d;
    const label = d.label || id;
    const type = d.type || "";
    const tab = d.tab || "";
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "require-chip dependent-chip";
    chip.setAttribute("data-testid", "dependent-chip-" + id);
    chip.setAttribute("data-dependent-id", id);
    chip.title =
      "Ouvrir " +
      id +
      (type ? " (" + type + ")" : "") +
      (tab ? " · " + tab : "") +
      " — pour modifier le require, editez ce composant";
    chip.innerHTML =
      '<span class="require-chip-label">' +
      escapeHtml(label) +
      "</span>" +
      (label !== id
        ? '<span class="require-chip-id">' + escapeHtml(id) + "</span>"
        : "") +
      (type
        ? '<span class="require-chip-type">' +
          escapeHtml(type) +
          "</span>"
        : "") +
      (tab
        ? '<span class="require-tab other">' + escapeHtml(tab) + "</span>"
        : "");
    chip.addEventListener("click", function (ev) {
      ev.preventDefault();
      openRequireComponent(id);
    });
    el.cfgDependents.appendChild(chip);
  });
}

/**
 * F0057/F0059: zones d appartenance (calculees).
 * - Clic simple: selectionne le chip (affiche croix retirer si membership)
 * - Double-clic: ouvre l onglet graphique de la zone
 * - Croix: retire l objet courant de zone.objects (pas pour home/main)
 *
 * @param {Array<{id:string,label?:string,zone_path?:string,kind?:string}>} list
 */
/**
 * F0093: formatte une duree en secondes pour l UI.
 * @param {number|null|undefined} sec
 * @returns {string}
 */
export function formatRenatusTime(sec) {
  if (sec == null || !isFinite(Number(sec))) return "—";
  const s = Number(sec);
  if (s < 0.001) return "< 1 ms";
  if (s < 1) return Math.round(s * 1000) + " ms";
  if (s < 60) return s.toFixed(3) + " s";
  const m = Math.floor(s / 60);
  const r = s - m * 60;
  return m + " min " + r.toFixed(1) + " s";
}

/**
 * F0093: affiche renatus_time (tous composants).
 * @param {number|null|undefined} sec
 */
export function renderRenatusTime(sec) {
  if (!el.cfgRenatusTime) return;
  if (el.fieldRenatusTime) el.fieldRenatusTime.hidden = false;
  el.cfgRenatusTime.textContent = formatRenatusTime(sec);
  el.cfgRenatusTime.title =
    sec != null && isFinite(Number(sec))
      ? Number(sec).toFixed(6) + " s (dernier Renatus)"
      : "Disponible apres un Renatus";
}

/**
 * F0092: shape [rows, cols] calcule pour datasets.
 * @param {Array<number>|null|undefined} shape
 * @param {string} [stepType]
 */
export function renderShape(shape, stepType) {
  if (!el.fieldShape && !el.cfgShape) return;
  const dataset =
    stepType === "dataframe" ||
    stepType === "table" ||
    stepType === "view";
  if (el.fieldShape) el.fieldShape.hidden = !dataset;
  if (!dataset || !el.cfgShape) return;
  if (Array.isArray(shape) && shape.length >= 2) {
    el.cfgShape.textContent =
      "[" + String(shape[0]) + ", " + String(shape[1]) + "]";
    el.cfgShape.title = "rows × cols (apres Renatus)";
  } else {
    el.cfgShape.textContent = "—";
    el.cfgShape.title = "Disponible apres un Renatus reussi";
  }
}

/**
 * F0091: schema dataset calcule (colonnes name + type).
 * @param {Array<{name:string,type:string}>|null} list
 * @param {string} [stepType]
 */
export function renderSchema(list, stepType) {
  if (!el.cfgSchema && !el.fieldSchema) return;
  const dataset =
    stepType === "dataframe" ||
    stepType === "table" ||
    stepType === "view";
  if (el.fieldSchema) {
    el.fieldSchema.hidden = !dataset;
  }
  if (!dataset || !el.cfgSchema) return;
  const items = Array.isArray(list) ? list : [];
  el.cfgSchema.innerHTML = "";
  if (el.schemaEmpty) {
    el.schemaEmpty.hidden = items.length > 0;
    el.schemaEmpty.textContent = items.length
      ? ""
      : "— (Renatus pour materialiser)";
  }
  items.forEach(function (col) {
    const name = (col && col.name) || "";
    const typ = (col && col.type) || "";
    if (!name) return;
    const row = document.createElement("div");
    row.className = "schema-row";
    row.setAttribute("data-testid", "schema-row");
    row.innerHTML =
      '<span class="schema-col-name mono">' +
      escapeHtml(name) +
      '</span><span class="schema-col-type muted">' +
      escapeHtml(typ) +
      "</span>";
    el.cfgSchema.appendChild(row);
  });
}

export function renderZones(list) {
  if (!el.cfgZones) return;
  const items = Array.isArray(list) ? list : [];
  el.cfgZones.innerHTML = "";
  if (el.fieldZones) el.fieldZones.hidden = false;
  if (el.zonesEmpty) {
    el.zonesEmpty.hidden = items.length > 0;
    if (!items.length) {
      el.zonesEmpty.textContent = "—";
    }
  }
  if (!items.length) return;

  const objectId = state.selected;
  import("../graph.js").then(function (mod) {
    const openZone = mod.openZoneTab;
    items.forEach(function (z) {
      const id = z.id || z;
      const label = z.label || id;
      const zpath = z.zone_path || id;
      const kind = z.kind || "";
      // F0060: retirable seulement si multi-copie (can_remove du serveur)
      const canRemove =
        objectId &&
        (z.can_remove === true ||
          (z.can_remove !== false &&
            z.copies != null &&
            Number(z.copies) > 1));

      const wrap = document.createElement("div");
      wrap.className = "zone-chip-wrap";
      wrap.setAttribute("data-testid", "zone-chip-wrap-" + id);
      wrap.setAttribute("data-zone-id", id);

      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "require-chip zone-chip";
      if (kind === "home") chip.classList.add("zone-home");
      chip.setAttribute("data-testid", "zone-chip-" + id);
      chip.setAttribute("data-zone-id", id);
      chip.setAttribute("data-zone-path", zpath);
      chip.title = canRemove
        ? "Clic: selectionner / retirer · Double-clic: ouvrir la zone « " +
          label +
          " »"
        : "Double-clic: ouvrir la zone « " +
          label +
          " » (emplacement fichier — non retirable)";
      chip.innerHTML =
        '<span class="require-chip-label">' +
        escapeHtml(label) +
        "</span>" +
        (label !== id && id !== "default"
          ? '<span class="require-chip-id">' + escapeHtml(id) + "</span>"
          : "") +
        (kind === "home"
          ? '<span class="require-chip-type">home</span>'
          : '<span class="require-chip-type">zone</span>');

      let clickTimer = null;
      chip.addEventListener("click", function (ev) {
        ev.preventDefault();
        // différer pour distinguer du double-clic
        if (clickTimer) {
          clearTimeout(clickTimer);
          clickTimer = null;
          return;
        }
        clickTimer = setTimeout(function () {
          clickTimer = null;
          // selection exclusive
          el.cfgZones
            .querySelectorAll(".zone-chip-wrap.is-selected")
            .forEach(function (w) {
              w.classList.remove("is-selected");
            });
          wrap.classList.add("is-selected");
        }, 220);
      });
      chip.addEventListener("dblclick", function (ev) {
        ev.preventDefault();
        if (clickTimer) {
          clearTimeout(clickTimer);
          clickTimer = null;
        }
        if (typeof openZone === "function") {
          openZone(zpath);
        }
      });

      wrap.appendChild(chip);

      if (canRemove) {
        const rm = document.createElement("button");
        rm.type = "button";
        rm.className = "zone-chip-remove";
        rm.setAttribute("data-testid", "zone-chip-remove-" + id);
        rm.setAttribute("aria-label", "Retirer de la zone " + label);
        rm.title = "Retirer cet objet de la zone « " + label + " »";
        rm.textContent = "×";
        rm.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          removeObjectFromZone(id, objectId, label, zpath);
        });
        wrap.appendChild(rm);
      }

      el.cfgZones.appendChild(wrap);
    });
  });
}

/**
 * Retire objectId de zone.objects puis rafraichit la liste zones.
 * @param {string} zoneId id step zone
 * @param {string} objectId id objet courant
 * @param {string} [zoneLabel]
 */
export async function removeObjectFromZone(zoneId, objectId, zoneLabel, zoneTab) {
  if (!zoneId || !objectId) return;
  const lab = zoneLabel || zoneId;
  const tab = zoneTab || zoneId;
  // F0114: dialog stylé renatus (plus de window.confirm)
  const ok = await confirmDialog({
    title: "Retirer de la zone",
    message:
      "Retirer « " +
      objectId +
      " » de la zone « " +
      lab +
      " » ?\n\n" +
      "Supprime la copie YAML dans ce dossier (refuse si c'est la seule).",
    confirmLabel: "Retirer",
    cancelLabel: "Annuler",
    danger: true,
    variant: "warn",
    focusCancel: true,
  });
  if (!ok) return;
  try {
    // F0060: unshare = detach copie FS (pas seulement objects dict)
    await api(
      "/gui/step/" + encodeURIComponent(objectId) + "/unshare-zone",
      {
        method: "POST",
        body: JSON.stringify({ zone_tab: tab }),
      }
    );
    toast("Retire de la zone « " + lab + " »", "success");
    const cur = await api(
      "/gui/step/" + encodeURIComponent(objectId)
    );
    renderZones(cur.zones || []);
    try {
      const { refreshGraph } = await import("../graph.js");
      if (typeof refreshGraph === "function") await refreshGraph();
    } catch (_) {}
  } catch (e) {
    toast("Retirer zone: " + e.message, "error");
  }
}
