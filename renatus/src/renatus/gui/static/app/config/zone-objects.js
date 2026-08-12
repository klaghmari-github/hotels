/**
 * Objects d une zone (F0056 / F0097 / F0105).
 * View: chips des membres. Edit: popup graphe zone (dropdown + dblclick).
 * F0105: retrait d un membre → noeud grisé (will-remove) dans le canvas.
 * YAML objects = dict { id: {} } (ids immutables).
 */
import { state, el } from "../state.js";
import { api, toast } from "../api.js";
import { typeColor, typeFill, typeIconSvg, typeIconSvgGroup } from "../icons.js";
import { escapeHtml } from "../util.js";
import { formToYamlEditor } from "./form-sync.js";
import { listRequireZones, openRequireComponent } from "./requires.js";

/** Snapshot a l ouverture du dialog (Annuler). */
let _zoEditSnapshot = null;
/** Selection en cours dans le dialog {id: {}}. */
let _zoEditObj = {};
/** Zone parcourue dans le dialog. */
let _zoEditZone = "default";

/** Parse objects hidden: "id1,id2" ou JSON dict. */
export function parseZoneObjectsValue(raw) {
  const s = String(raw || "").trim();
  if (!s) return {};
  if (s.charAt(0) === "{") {
    try {
      const obj = JSON.parse(s);
      if (obj && typeof obj === "object" && !Array.isArray(obj)) {
        const out = {};
        Object.keys(obj).forEach(function (k) {
          const id = String(k).trim();
          if (id) out[id] = obj[k] && typeof obj[k] === "object" ? obj[k] : {};
        });
        return out;
      }
    } catch (_) {}
  }
  const out = {};
  s.split(",")
    .map(function (x) {
      return x.trim();
    })
    .filter(Boolean)
    .forEach(function (id) {
      out[id] = {};
    });
  return out;
}

/** Serialise dict objects → hidden value (liste d ids ordonnee). */
export function serializeZoneObjects(obj) {
  const ids = Object.keys(obj || {}).sort();
  return ids.join(", ");
}

/**
 * Objects selectionnes — source de verite = miroir hidden (F0097).
 * Plus de checkboxes dans le panneau Config.
 */
export function getSelectedZoneObjects() {
  return parseZoneObjectsValue(
    el.cfgZoneObjects ? el.cfgZoneObjects.value : ""
  );
}

export function setZoneObjectsMirror(objOrList) {
  let obj = {};
  if (typeof objOrList === "string") {
    obj = parseZoneObjectsValue(objOrList);
  } else if (Array.isArray(objOrList)) {
    objOrList.forEach(function (id) {
      if (id) obj[String(id)] = {};
    });
  } else if (objOrList && typeof objOrList === "object") {
    Object.keys(objOrList).forEach(function (k) {
      const id = String(k).trim();
      if (!id) return;
      const v = objOrList[k];
      obj[id] = v && typeof v === "object" && !Array.isArray(v) ? v : {};
    });
  }
  // ne pas s inclure soi-meme
  if (state.selected && obj[state.selected]) {
    delete obj[state.selected];
  }
  if (el.cfgZoneObjects) {
    el.cfgZoneObjects.value = serializeZoneObjects(obj);
  }
  return obj;
}

/** Compat F0056: toggle ex-checkbox. */
export function onZoneObjectCheckboxChange() {
  const obj = getSelectedZoneObjects();
  setZoneObjectsMirror(obj);
  renderZoneObjectsSelected(obj);
  formToYamlEditor();
}

/**
 * Chips des objects (view).
 * @param {object|string[]|string} obj
 * @param {{container?: HTMLElement, removable?: boolean, onRemove?: function}|undefined} opts
 */
export function renderZoneObjectsSelected(obj, opts) {
  const options = opts || {};
  const host = options.container || el.cfgZoneObjectsSelected;
  if (!host) return;
  let selectedObj = {};
  if (typeof obj === "string" || Array.isArray(obj)) {
    selectedObj = setZoneObjectsMirror(obj);
  } else if (obj && typeof obj === "object") {
    selectedObj = obj;
  } else {
    selectedObj = getSelectedZoneObjects();
  }
  const ids = Object.keys(selectedObj || {}).sort();
  host.innerHTML = "";
  const isMainView = host === el.cfgZoneObjectsSelected;
  if (!ids.length) {
    if (isMainView) {
      host.hidden = true;
      if (el.zoneObjectsEmpty) {
        el.zoneObjectsEmpty.hidden = false;
        el.zoneObjectsEmpty.textContent = "—";
      }
    }
    return;
  }
  if (isMainView) {
    host.hidden = false;
    if (el.zoneObjectsEmpty) el.zoneObjectsEmpty.hidden = true;
  }
  const catalog = state.allSteps.length
    ? state.allSteps
    : state.graph.nodes || [];
  const byId = {};
  catalog.forEach(function (n) {
    if (n && n.id) byId[n.id] = n;
  });
  ids.forEach(function (id) {
    const n = byId[id] || { id: id, label: id, type: "?" };
    const wrap = document.createElement("span");
    wrap.className = "require-chip-wrap";
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "require-chip";
    chip.setAttribute("data-testid", "zone-object-chip-" + id);
    chip.setAttribute("data-zone-object-id", id);
    chip.title = "Ouvrir " + id + " (id immutable)";
    chip.innerHTML =
      typeIconSvg(n.type || "table", {
        size: 12,
        className: "require-chip-icon",
        strokeWidth: 2,
      }) +
      '<span class="require-chip-label">' +
      escapeHtml(n.label || id) +
      "</span>" +
      (n.type
        ? '<span class="require-chip-type">' + escapeHtml(n.type) + "</span>"
        : "");
    chip.addEventListener("click", function (ev) {
      ev.preventDefault();
      if (options.removable) return;
      openRequireComponent(id);
    });
    wrap.appendChild(chip);
    if (options.removable) {
      const rm = document.createElement("button");
      rm.type = "button";
      rm.className = "require-chip-remove";
      rm.setAttribute("data-testid", "zone-object-remove-" + id);
      rm.title = "Retirer des objects";
      rm.setAttribute("aria-label", "Retirer " + (n.label || id));
      rm.textContent = "×";
      rm.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (typeof options.onRemove === "function") {
          options.onRemove(id);
        } else {
          removeZoneObject(id);
        }
      });
      wrap.appendChild(rm);
    }
    host.appendChild(wrap);
  });
}

/**
 * Mode view Objects (F0097): chips uniquement, pas de checkboxes.
 */
export function renderZoneObjectsPicker(selected) {
  let selectedObj = {};
  if (typeof selected === "string" || Array.isArray(selected)) {
    selectedObj = setZoneObjectsMirror(selected);
  } else if (selected && typeof selected === "object") {
    selectedObj = setZoneObjectsMirror(selected);
  } else {
    selectedObj = getSelectedZoneObjects();
    setZoneObjectsMirror(selectedObj);
  }
  renderZoneObjectsSelected(selectedObj);
  if (el.cfgZoneObjectsPicker) {
    el.cfgZoneObjectsPicker.innerHTML = "";
    el.cfgZoneObjectsPicker.hidden = true;
  }
  if (el.zoneObjectsEmpty) {
    const n = Object.keys(selectedObj).length;
    el.zoneObjectsEmpty.hidden = n > 0;
    if (!n) el.zoneObjectsEmpty.textContent = "—";
  }
}

export function addZoneObject(stepId) {
  if (!stepId || stepId === state.selected) return getSelectedZoneObjects();
  const obj = getSelectedZoneObjects();
  if (obj[stepId]) return obj;
  obj[stepId] = {};
  setZoneObjectsMirror(obj);
  renderZoneObjectsSelected(obj);
  formToYamlEditor();
  return obj;
}

export function removeZoneObject(stepId) {
  const obj = getSelectedZoneObjects();
  delete obj[stepId];
  setZoneObjectsMirror(obj);
  renderZoneObjectsSelected(obj);
  formToYamlEditor();
  return obj;
}

/**
 * F0097: ouvre le dialog d edition Objects (graphe zone non editable).
 */
export async function openZoneObjectsEditor() {
  const dlg = el.zoneObjectsEditDialog;
  if (!dlg || typeof dlg.showModal !== "function") {
    toast("Dialog Objects indisponible", "error");
    return;
  }
  _zoEditSnapshot = Object.assign({}, getSelectedZoneObjects());
  _zoEditObj = Object.assign({}, _zoEditSnapshot);
  _zoEditZone = state.activeTab || "default";
  fillZoZoneSelect();
  renderZoEditSelected();
  await loadZoEditZone(_zoEditZone);
  try {
    dlg.showModal();
  } catch (e) {
    toast("Objects: " + e.message, "error");
  }
}

function fillZoZoneSelect() {
  const sel = el.zoneObjectsZoneSelect;
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
  if (!zones.some(function (z) { return z.id === _zoEditZone; })) {
    _zoEditZone = zones[0] ? zones[0].id : "default";
  }
  sel.value = _zoEditZone;
}

function renderZoEditSelected() {
  if (!el.zoneObjectsEditSelected) return;
  renderZoneObjectsSelected(_zoEditObj, {
    container: el.zoneObjectsEditSelected,
    removable: true,
    onRemove: function (id) {
      delete _zoEditObj[id];
      renderZoEditSelected();
      markZoEditNodes();
    },
  });
}

async function loadZoEditZone(zoneId) {
  const zid = String(zoneId || "default");
  _zoEditZone = zid;
  const canvas = el.zoneObjectsEditCanvas;
  if (!canvas) return;
  canvas.innerHTML = '<p class="empty-msg compact">Chargement…</p>';
  try {
    const graphMod = await import("../graph.js");
    const q = "?tab=" + encodeURIComponent(zid);
    const g = await api("/gui/graph" + q);
    if (g.catalog && g.catalog.length) {
      state.allSteps = g.catalog;
    }
    // candidats = composants de la zone parcourue, hors zone editee
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
    renderZoEditGraph(nodes, edges, graphMod);
  } catch (e) {
    canvas.innerHTML =
      '<p class="empty-msg compact">Erreur: ' +
      escapeHtml(e.message || String(e)) +
      "</p>";
  }
}

function renderZoEditGraph(nodes, edges, graphMod) {
  const canvas = el.zoneObjectsEditCanvas;
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
  let svg =
    '<svg class="graph-svg requires-edit-svg" width="' +
    maxX +
    '" height="' +
    maxY +
    '"><defs>' +
    '<marker id="zo-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">' +
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
    const isMem = !!_zoEditObj[n.id];
    const wasMem = !!(
      _zoEditSnapshot && Object.prototype.hasOwnProperty.call(_zoEditSnapshot, n.id)
    );
    // F0105: membre retire → grisé (va disparaitre a OK)
    const willRemove = !isMem && wasMem;
    const iconY = Math.round((nodeH - 28) / 2);
    const stepId = n.id;
    const cls =
      "node node-" +
      escapeHtml(type) +
      (isMem ? " is-required" : "") +
      (willRemove ? " will-remove" : "") +
      " zone-object-pick-node";
    svg +=
      '<g class="' +
      cls +
      '" data-id="' +
      escapeHtml(stepId) +
      '" data-testid="zone-object-pick-' +
      escapeHtml(stepId) +
      '" transform="translate(' +
      p.x +
      "," +
      p.y +
      ')">' +
      "<title>" +
      escapeHtml(zoNodeTitle(fullName, stepId, isMem, willRemove)) +
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
  canvas.querySelectorAll(".zone-object-pick-node").forEach(function (g) {
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
      toggleZoInEditor(id);
    });
  });
  // marker edges
  canvas.querySelectorAll(".edge").forEach(function (path) {
    path.setAttribute("marker-end", "url(#zo-arrow)");
  });
  markZoEditNodes();
}

/** Libelle title SVG selon etat selection / retrait. */
function zoNodeTitle(fullName, stepId, isMem, willRemove) {
  if (willRemove) {
    return (
      fullName +
      " — sera retire de la zone (double-clic pour re-ajouter, id " +
      stepId +
      ")"
    );
  }
  return (
    fullName +
    " — double-clic pour " +
    (isMem ? "retirer" : "ajouter") +
    " (id " +
    stepId +
    ")"
  );
}

function toggleZoInEditor(stepId) {
  if (!stepId || stepId === state.selected) return;
  if (_zoEditObj[stepId]) {
    delete _zoEditObj[stepId];
  } else {
    // copie id dans objects de la zone editee
    _zoEditObj[stepId] = {};
  }
  renderZoEditSelected();
  markZoEditNodes();
}

/**
 * F0105: synchronise classes canvas avec la selection.
 * - is-required : encore membre (selection)
 * - will-remove : etait membre a l ouverture, retire → grisé (va disparaitre)
 */
function markZoEditNodes() {
  const canvas = el.zoneObjectsEditCanvas;
  if (!canvas) return;
  canvas.querySelectorAll(".zone-object-pick-node").forEach(function (g) {
    const id = g.getAttribute("data-id");
    const isMem = !!_zoEditObj[id];
    const wasMem = !!(
      _zoEditSnapshot &&
      Object.prototype.hasOwnProperty.call(_zoEditSnapshot, id)
    );
    const willRemove = !isMem && wasMem;
    g.classList.toggle("is-required", isMem);
    g.classList.toggle("will-remove", willRemove);
    g.setAttribute("data-will-remove", willRemove ? "1" : "0");
    g.setAttribute("data-is-member", isMem ? "1" : "0");
    const title = g.querySelector("title");
    if (title) {
      const fullName =
        (title.textContent || "").split(" — ")[0] || id;
      title.textContent = zoNodeTitle(fullName, id, isMem, willRemove);
    }
  });
}

/** Intent OK/cancel avant close. */
let _zoEditIntent = null;

/**
 * Commit ou annule le dialog Objects.
 * A0013: await persist + refreshGraph.
 * @param {"ok"|"cancel"} result
 */
export async function closeZoneObjectsEditor(result) {
  const dlg = el.zoneObjectsEditDialog;
  if (_zoEditSnapshot == null) {
    return;
  }
  const snap = _zoEditSnapshot;
  const objOk = Object.assign({}, _zoEditObj);
  _zoEditSnapshot = null;
  _zoEditIntent = null;

  if (result === "ok") {
    setZoneObjectsMirror(objOk);
    renderZoneObjectsSelected(objOk);
    formToYamlEditor();
    try {
      const { persistCurrentStep } = await import("./step-crud.js");
      await persistCurrentStep({
        silent: true,
        stepId: state.selected,
        refreshGraph: true,
      });
    } catch (e) {
      toast("Objects: " + (e && e.message ? e.message : e), "error");
    }
  } else {
    setZoneObjectsMirror(snap || {});
    renderZoneObjectsSelected(snap || {});
    formToYamlEditor();
  }
  if (dlg && dlg.open) {
    try {
      dlg.close();
    } catch (_) {}
  }
}

/** Wire select + close dialog (bootstrap). */
export function wireZoneObjectsEditor() {
  if (el.zoneObjectsZoneSelect) {
    el.zoneObjectsZoneSelect.addEventListener("change", function () {
      loadZoEditZone(el.zoneObjectsZoneSelect.value);
    });
  }
  if (el.zoneObjectsEditForm) {
    el.zoneObjectsEditForm.addEventListener("submit", function (ev) {
      const submitter = ev.submitter;
      _zoEditIntent = submitter && submitter.value ? submitter.value : "ok";
    });
  }
  if (el.zoneObjectsEditDialog) {
    el.zoneObjectsEditDialog.addEventListener("close", function () {
      const rv =
        _zoEditIntent ||
        el.zoneObjectsEditDialog.returnValue ||
        "cancel";
      _zoEditIntent = null;
      if (_zoEditSnapshot != null) {
        closeZoneObjectsEditor(rv === "ok" ? "ok" : "cancel");
      }
    });
  }
}
