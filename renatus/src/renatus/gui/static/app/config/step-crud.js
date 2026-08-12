/**
 * Step select / save / build / delete (F0054-S2).
 */
import { state, el } from "../state.js";
import { api, toast } from "../api.js";
import { confirmDialog } from "../confirm-dialog.js";
import { clearTable, loadDataView, showTable } from "../dataview.js";
import {
  clearZoneBuildProgress,
  refreshGraph,
  renderGraph,
  setZoneBuildDone,
  setZoneBuildRunning,
  startZoneBuildProgress,
} from "../graph.js";
import { refreshTabs, renderPipelineTabs } from "../tabs.js";
import {
  applyConfigToFormFields,
  configFromForm,
  fillForm,
  formToYamlEditor,
} from "./form-sync.js";
import {
  getSelectedRequires,
  renderDependents,
  renderRequiresPicker,
  renderSchema,
  renderShape,
  renderRenatusTime,
  renderZones,
} from "./requires.js";
import { getSelectedZoneObjects } from "./zone-objects.js";
import { yamlToConfig } from "./yaml-editor.js";

/**
 * F0081: id de zone pour un onglet (dernier segment du path).
 * default / * → null (zone racine F0144).
 * Preferer currentZoneStepId() (F0099).
 */
export function zoneIdFromTab(tabId) {
  const t = String(tabId || "default").trim() || "default";
  if (
    t === "default" ||
    t === "main" ||
    t === "*" ||
    t === "_all" ||
    t === "all"
  ) {
    return null;
  }
  const parts = t.split("/").filter(Boolean);
  return parts.length ? parts[parts.length - 1] : null;
}

/**
 * F0099: id du composant zone qui contient les objets de l onglet actif.
 * - tab default → "default" (zone protegee F0144)
 * - tab zone_path → dernier segment (id de la zone)
 * - tab all → null (vue calculee F0104, pas de zone unique)
 */
export function currentZoneStepId(tabId) {
  const t = String(tabId || state.activeTab || "default").trim() || "default";
  if (t === "all" || t === "*" || t === "_all") return null;
  if (t === "default" || t === "main") return "default";
  const parts = t.split("/").filter(Boolean);
  return parts.length ? parts[parts.length - 1] : "default";
}

function stepExistsInState(id) {
  if (!id) return false;
  const nodes = (state.graph && state.graph.nodes) || [];
  if (nodes.some(function (n) { return n && n.id === id; })) return true;
  const all = state.allSteps || [];
  return all.some(function (n) { return n && n.id === id; });
}

function rememberSelection(name, stepType) {
  const tab = state.activeTab || "default";
  if (!state.lastSelectedByTab) state.lastSelectedByTab = {};
  state.lastSelectedByTab[tab] = name;
  if (stepType === "zone") {
    state.lastManipulatedZone = name;
  }
  const zid = currentZoneStepId(tab);
  if (zid) state.lastManipulatedZone = zid;
}

/**
 * F0099: selectionne la zone courante (config Objects de la zone).
 * Utilise au clic fond du canvas Flux et comme fallback par defaut.
 */
export async function selectCurrentZone() {
  const tab = state.activeTab || "default";
  // F0104: vue all = pas de zone config unique
  if (tab === "all" || tab === "*" || tab === "_all") {
    return state.selected || null;
  }
  const zid = currentZoneStepId(tab);
  if (!zid) return null;
  try {
    await selectStep(zid);
    return state.selected === zid ? zid : null;
  } catch (e) {
    // zone absente du pipeline: tenter ensureSelection sans forcer un objet
    return null;
  }
}

/** Profondeur ensureSelection — evite recursion infinie selectStep↔ensure. */
let _ensureSelectionDepth = 0;

/**
 * F0081 / F0099: toujours une selection pour afficher la Config.
 * Priorite:
 * 1. selection courante encore valide (si !force)
 * 2. zone courante de l onglet (pas le dernier objet modifie)
 * 3. derniere zone manipulee
 * 4. 1er noeud type zone du graphe, sinon 1er noeud
 *
 * @param {{ force?: boolean, skipDataView?: boolean }} [options]
 */
export async function ensureSelection(options) {
  const opts = options || {};
  const force = !!opts.force;
  // F0133: garde anti-recursion (selectStep catch → ensure → select…)
  if (_ensureSelectionDepth > 2) {
    return state.selected || null;
  }
  _ensureSelectionDepth += 1;
  try {
    if (
      !force &&
      state.selected &&
      stepExistsInState(state.selected)
    ) {
      if (el.configForm && el.configForm.hidden) {
        await selectStep(state.selected, {
          skipDataView: !!opts.skipDataView,
          skipEnsureFallback: true,
        });
      }
      return state.selected;
    }

    const tab = state.activeTab || "default";
    const candidates = [];
    const nodes = (state.graph && state.graph.nodes) || [];
    // F0104: vue all → premier composant non-zone du graphe
    if (tab === "all" || tab === "*" || tab === "_all") {
      nodes.forEach(function (n) {
        if (n && n.id && !n.external && n.type !== "zone") {
          candidates.push(n.id);
        }
      });
    } else {
      // F0099: zone courante en tete (pas lastSelected objet)
      const zid = currentZoneStepId(tab);
      if (zid) candidates.push(zid);
      if (state.lastManipulatedZone) {
        candidates.push(state.lastManipulatedZone);
      }
      const all = state.allSteps && state.allSteps.length
        ? state.allSteps
        : nodes;
      all.forEach(function (n) {
        if (n && n.id && n.type === "zone" && !n.external) {
          candidates.push(n.id);
        }
      });
      // dernier recours: un objet du graphe
      nodes.forEach(function (n) {
        if (n && n.id && !n.external) candidates.push(n.id);
      });
    }

    const seen = {};
    for (let i = 0; i < candidates.length; i++) {
      const id = candidates[i];
      if (!id || seen[id]) continue;
      seen[id] = true;
      if (!stepExistsInState(id)) continue;
      try {
        await selectStep(id, {
          skipDataView: !!opts.skipDataView,
          skipEnsureFallback: true,
        });
        if (state.selected === id) return id;
      } catch (_) {
        /* try next */
      }
    }

    // pipeline vide
    state.selected = null;
    if (el.configForm) el.configForm.hidden = true;
    if (el.configPlaceholder) el.configPlaceholder.hidden = false;
    if (el.selectedName) el.selectedName.textContent = "—";
    // F0086: boutons Config retires (refs optionnelles)
    if (el.btnSave) el.btnSave.disabled = true;
    if (el.btnBuild) el.btnBuild.disabled = true;
    if (el.btnDelete) el.btnDelete.disabled = true;
    return null;
  } finally {
    _ensureSelectionDepth -= 1;
  }
}

/** Debounce autosave (F0083). */
const AUTO_SAVE_MS = 450;
let _autoSaveTimer = null;
let _autoSaveInFlight = null;
/** last scheduled step id (flush uses form while still selected) */
let _pendingAutoSaveId = null;

/**
 * F0083: construit la config a persister depuis YAML (priorite) ou formulaire.
 * @param {{ requireFile?: boolean, stepId?: string }} opts
 * @returns {object}
 */
function buildConfigToPersist(opts) {
  const options = opts || {};
  const stepId = options.stepId || state.selected;
  if (!stepId) throw new Error("Aucune step selectionnee");
  let config;
  try {
    config = yamlToConfig(el.editor.value);
    // ne reapplique pas le form pendant un autosave silencieux (evite focus jump)
    if (!options.quiet) {
      applyConfigToFormFields(config);
    }
  } catch (_) {
    config = configFromForm();
    if (!options.quiet) {
      formToYamlEditor();
    }
  }
  if (!config || !config.type) {
    throw new Error("cle 'type' obligatoire");
  }
  const label =
    (el.cfgName && el.cfgName.value.trim()) ||
    config.label ||
    stepId;
  config.label = label;
  if (
    config.type === "dataframe" ||
    config.type === "table" ||
    config.type === "view"
  ) {
    const rel = el.cfgRelationName
      ? el.cfgRelationName.value.trim()
      : "";
    config.name = rel || config.name || label;
  }
  if (config.type === "dataframe") {
    delete config.sql;
    delete config.script;
    delete config.requires;
    delete config.mode;
    if (
      options.requireFile &&
      (!config.file || !String(config.file).trim())
    ) {
      throw new Error(
        "Fichier source vide — selectionnez un fichier avant Renatus"
      );
    }
  }
  if (config.sql != null && (config.script == null || config.script === "")) {
    config.script = config.sql;
  }
  delete config.sql;
  // A0013: miroir UI prioritaires (popup Requires / Objects)
  // sinon YAML editeur peut rester stale si formToYaml n a pas fini.
  const type = String(config.type || "");
  const withRequires = {
    table: 1,
    view: 1,
    execute_sql: 1,
    execute: 1,
    execute_python: 1,
    execute_shell: 1,
    iterate: 1,
    iteration: 1,
  };
  if (withRequires[type] && el.cfgRequires) {
    config.requires = getSelectedRequires();
  }
  if (type === "zone" && el.cfgZoneObjects) {
    config.objects = getSelectedZoneObjects();
  }
  if (config.id != null && String(config.id) !== stepId) {
    throw new Error("L id du composant n est pas modifiable");
  }
  delete config.id;
  // zones calculees (F0057) jamais persistees
  delete config.zones;
  delete config.dependents;
  delete config.required_by;
  return config;
}

function patchLabelsFromResponse(res) {
  if (!res || !res.label_changed || !res.id) return;
  const newLab = res.label_new || res.label || res.id;
  (state.allSteps || []).forEach(function (n) {
    if (n && n.id === res.id) n.label = newLab;
  });
  if (state.graph && state.graph.nodes) {
    (state.graph.nodes || []).forEach(function (n) {
      if (n && n.id === res.id) n.label = newLab;
    });
  }
  if (state.selected === res.id && el.selectedName) {
    el.selectedName.textContent = newLab;
  }
}

/**
 * Persiste la step courante (formulaire / YAML).
 * F0083: utilisee en autosave silencieux et avant Renatus.
 *
 * @param {{
 *   silent?: boolean,
 *   toastOk?: boolean,
 *   requireFile?: boolean,
 *   reload?: boolean,
 *   stepId?: string,
 * }} opts
 * @returns {Promise<boolean>}
 */
export async function persistCurrentStep(opts) {
  const options = opts || {};
  const stepId = options.stepId || state.selected;
  if (!stepId) return false;
  if (state.workspace && state.workspace.read_only) return false;
  // le formulaire ne represente que la selection courante
  if (state.selected && state.selected !== stepId) return false;

  let config;
  try {
    config = buildConfigToPersist({
      requireFile: !!options.requireFile,
      stepId: stepId,
      quiet: !!options.silent,
    });
  } catch (e) {
    if (!options.silent) {
      toast(
        (options.requireFile ? "Avant Renatus: " : "Config invalide: ") +
          e.message,
        "error"
      );
    }
    // autosave: YAML incomplet pendant la frappe → ignorer sans bruit
    return false;
  }

  try {
    const res = await api(
      "/gui/step/" + encodeURIComponent(stepId),
      {
        method: "PUT",
        body: JSON.stringify({ config: config }),
      }
    );
    if (options.toastOk) {
      toast(res.message || "Enregistre", "success");
    }
    patchLabelsFromResponse(res);
    if (res.file_origin && el.fileOrigin && state.selected === stepId) {
      el.fileOrigin.textContent = "YAML: " + res.file_origin;
    }
    if (options.reload && state.selected === stepId) {
      await refreshGraph();
      await selectStep(stepId);
      if (res.dependents) {
        renderDependents(res.dependents);
        if (res.zones) renderZones(res.zones);
      }
      if (res.requires && el.fieldRequires && !el.fieldRequires.hidden) {
        renderRequiresPicker(
          (res.requires || []).map(function (r) {
            return r.id || r;
          })
        );
      }
    } else if (options.refreshGraph) {
      // A0013: apres popup Requires/Objects — aretes Flux a jour
      await refreshGraph();
    } else if (res.label_changed) {
      // maj graphe locale sans recharger la selection (focus clavier)
      renderGraph();
    }
    return true;
  } catch (e) {
    toast(
      (options.silent ? "Sauvegarde auto: " : "Save: ") + e.message,
      "error"
    );
    return false;
  }
}

/**
 * F0083: planifie une sauvegarde auto apres edition formulaire / YAML.
 */
export function scheduleAutoSave() {
  if (!state.selected) return;
  if (state.workspace && state.workspace.read_only) return;
  if (state.syncing) return;
  _pendingAutoSaveId = state.selected;
  if (_autoSaveTimer) clearTimeout(_autoSaveTimer);
  _autoSaveTimer = setTimeout(function () {
    _autoSaveTimer = null;
    const id = _pendingAutoSaveId;
    _pendingAutoSaveId = null;
    if (!id || state.selected !== id) return;
    const p = persistCurrentStep({ silent: true, stepId: id });
    _autoSaveInFlight = p;
    p.finally(function () {
      if (_autoSaveInFlight === p) _autoSaveInFlight = null;
    });
  }, AUTO_SAVE_MS);
}

/**
 * F0083: annule le timer et force la persistance immediate (changement selection / Renatus).
 */
export async function flushAutoSave() {
  if (_autoSaveTimer) {
    clearTimeout(_autoSaveTimer);
    _autoSaveTimer = null;
  }
  const id = _pendingAutoSaveId || state.selected;
  _pendingAutoSaveId = null;
  if (_autoSaveInFlight) {
    try {
      await _autoSaveInFlight;
    } catch (_) {
      /* ignore */
    }
  }
  if (!id || !state.selected || state.selected !== id) return true;
  return persistCurrentStep({ silent: true, stepId: id });
}

/**
 * Charge la config d une step dans le panneau.
 * @param {string} name
 * @param {{ skipDataView?: boolean, skipEnsureFallback?: boolean, skipTrack?: boolean }} [options]
 */
export async function selectStep(name, options) {
  const opts = options || {};
  if (!name) {
    if (!opts.skipEnsureFallback) {
      await ensureSelection({ force: true, skipDataView: !!opts.skipDataView });
    }
    return;
  }
  // F0083: persister l edition en cours avant de changer de step
  if (state.selected && state.selected !== name) {
    await flushAutoSave();
  }
  try {
    const data = await api("/gui/step/" + encodeURIComponent(name));
    state.selected = name;
    state.dataviewSource = name;
    state.dataviewIsPrereq = false;
    const label = data.label || (data.config && data.config.label) || name;
    const stepType = (data.config && data.config.type) || "";
    rememberSelection(name, stepType);
    el.selectedName.textContent = label;
    el.configForm.hidden = false;
    el.configPlaceholder.hidden = true;
    fillForm(name, data.config || {}, {
      id: data.id || name,
      label: label,
    });
    // F0041: dependances inverses (calculees, hors config)
    renderDependents(data.dependents || []);
    // F0057: zones d appartenance (calculees, hors config)
    renderZones(data.zones || []);
    // masquer zones pour type zone / auto-zone (membership est dans objects)
    const isAuto =
      stepType === "allzone" ||
      stepType === "backzone" ||
      stepType === "forzone" ||
      stepType === "bidzone";
    if (el.fieldZones) {
      el.fieldZones.hidden = stepType === "zone" || isAuto;
    }
    // F0128: object ref auto-zone (display)
    if (el.cfgAutoObject) {
      el.cfgAutoObject.value =
        (data.config && data.config.object) || "";
    }
    const dispAuto = document.querySelector(
      '[data-display="cfg-auto-object"]'
    );
    if (dispAuto) {
      dispAuto.textContent =
        (data.config && data.config.object) || "—";
    }
    // objects effectifs pour auto-zones
    if (isAuto && data.config && data.config.objects) {
      try {
        const { setZoneObjectsMirror, renderZoneObjectsSelected } =
          await import("./zone-objects.js");
        setZoneObjectsMirror(data.config.objects);
        renderZoneObjectsSelected(data.config.objects);
      } catch (_) {
        /* ignore */
      }
    }
    // F0091 / F0092 / F0093: schema + shape + renatus_time calculees
    renderRenatusTime(data.renatus_time);
    renderShape(data.shape, stepType);
    renderSchema(data.schema || [], stepType);
    el.fileOrigin.textContent = data.file_origin
      ? "YAML: " + data.file_origin
      : "";
    // F0086: plus de boutons Config (Supprimer / Sauver / Renatus)
    if (el.btnSave) el.btnSave.disabled = true;
    if (el.btnBuild) el.btnBuild.disabled = false;
    if (el.btnDelete) {
      const ro = !!(state.workspace && state.workspace.read_only);
      el.btnDelete.disabled = ro || name === "default" || name === "main";
    }
    renderGraph();
    // F0115: Track suit le composant selectionne
    if (!opts.skipTrack) {
      try {
        const { refreshTrackIfActive } = await import("../changelogs.js");
        refreshTrackIfActive();
      } catch (_) {
        /* ignore */
      }
    }
    // F0133: skipDataView pendant import massif (preview peut etre long)
    if (!opts.skipDataView) {
      await loadDataView(name, false, { asPrereq: false });
    }
  } catch (e) {
    toast("Step: " + e.message, "error");
    // si step absente, retomber sur une selection valide
    if (state.selected === name) state.selected = null;
    // F0133: pas de recursion ensureSelection depuis ensureSelection
    if (!opts.skipEnsureFallback && _ensureSelectionDepth === 0) {
      await ensureSelection({ force: true, skipDataView: !!opts.skipDataView });
    }
  }
}

/**
 * Compat: sauvegarde immediate (ex. Ctrl+S legacy / API ConfigPanel).
 * F0083: silencieuse (pas de toast succes).
 */
export async function saveStep() {
  return persistCurrentStep({ silent: true, toastOk: false, reload: false });
}

/**
 * Persiste la config courante avant Renatus (A0005).
 * Evite de builder avec un file encore vide cote serveur.
 */
export async function saveStepSilent() {
  await flushAutoSave();
  return persistCurrentStep({
    silent: false,
    requireFile: true,
    reload: false,
  });
}

/**
 * F0118: affiche le resume textuel d un zone_build (apres orchestration).
 */
function applyBuildResultToDataView(res, isZoneBuild) {
  if (res.has_result) {
    showTable(res);
    if (
      res.action === "execute_python" ||
      res.action === "execute_shell" ||
      res.stdout != null
    ) {
      const rc = res.returncode;
      const py = res.python || "";
      el.dvMeta.textContent =
        (rc != null ? "exit " + rc : "process") +
        (py ? " · " + py : "");
    } else {
      el.dvMeta.textContent = res.message || "Renatus OK";
    }
  } else if (isZoneBuild && res.built && res.built.length) {
    const lines = (res.built || []).map(function (b) {
      const t =
        b.renatus_time != null && isFinite(Number(b.renatus_time))
          ? " · " + Number(b.renatus_time).toFixed(3) + "s"
          : "";
      return (
        (b.ok ? "OK" : "ERR") +
        " " +
        (b.label || b.id) +
        t +
        (b.message ? " — " + b.message : "")
      );
    });
    el.dvMeta.textContent =
      (res.message || "Zone build") + "\n" + lines.join("\n");
  } else {
    el.dvMeta.textContent = res.message || "Renatus OK";
  }
}

/**
 * F0118: Renatus zone orchestre — plan + jobs sequentiels + barre/etats.
 */
export async function buildZoneWithProgress(zoneId) {
  const plan = await api(
    "/gui/build/" + encodeURIComponent(zoneId) + "/plan"
  );
  const jobs = plan.jobs || [];
  startZoneBuildProgress(
    Object.assign({}, plan, { zone_id: plan.zone_id || zoneId })
  );
  // laisser le navigateur peindre l etat initial (gris / barre 0)
  await new Promise(function (r) {
    requestAnimationFrame(function () {
      requestAnimationFrame(r);
    });
  });

  const built = [];
  const errors = [];
  const t0 =
    typeof performance !== "undefined" && performance.now
      ? performance.now()
      : Date.now();

  for (let i = 0; i < jobs.length; i++) {
    const job = jobs[i] || {};
    const jid = job.id;
    if (!jid) continue;
    setZoneBuildRunning(jid, job.label || jid);
    await new Promise(function (r) {
      requestAnimationFrame(r);
    });
    try {
      const res = await api(
        "/gui/build/" + encodeURIComponent(jid) + "?limit=3",
        { method: "POST" }
      );
      const entry = {
        id: jid,
        ok: res.ok !== false,
        action: res.action,
        message: res.message,
        label: job.label || jid,
        line: job.line,
        renatus_time: res.renatus_time,
      };
      built.push(entry);
      if (!entry.ok) {
        errors.push({ id: jid, error: res.message || "echec" });
      }
    } catch (err) {
      const msg = (err && err.message) || String(err);
      built.push({
        id: jid,
        ok: false,
        action: "error",
        message: msg,
        label: job.label || jid,
        line: job.line,
        renatus_time: null,
      });
      errors.push({ id: jid, error: msg });
    }
    setZoneBuildDone(jid);
  }

  const t1 =
    typeof performance !== "undefined" && performance.now
      ? performance.now()
      : Date.now();
  const elapsed = Math.max(0, (t1 - t0) / 1000);

  let finalRes;
  try {
    finalRes = await api(
      "/gui/build/" + encodeURIComponent(zoneId) + "/complete",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          elapsed: elapsed,
          built: built,
          errors: errors,
        }),
      }
    );
  } catch (_) {
    // fallback local si complete indisponible
    const nOk = built.filter(function (b) {
      return b.ok;
    }).length;
    finalRes = {
      ok: errors.length === 0,
      action: "zone_build",
      name: zoneId,
      built: built,
      errors: errors,
      message:
        "Zone " +
        zoneId +
        ": " +
        nOk +
        "/" +
        built.length +
        " build OK",
      renatus_time: elapsed,
      member_renatus_times: {},
      has_result: false,
    };
  }

  clearZoneBuildProgress();
  return finalRes;
}

export async function buildStep() {
  if (!state.selected) return;
  if (state.zoneBuild) {
    toast("Renatus zone deja en cours", "error");
    return;
  }
  try {
    const ok = await saveStepSilent();
    if (!ok) return;

    // F0118: detecte zone → orchestration progressive
    let stepType = (el.cfgType && el.cfgType.value) || "";
    if (!stepType) {
      const n = (state.graph.nodes || []).find(function (x) {
        return x && x.id === state.selected;
      });
      if (n) stepType = n.type || "";
    }
    const isZone = stepType === "zone";

    let res;
    if (isZone) {
      if (el.btnDvBuild) el.btnDvBuild.disabled = true;
      if (el.btnBuild) el.btnBuild.disabled = true;
      try {
        res = await buildZoneWithProgress(state.selected);
      } finally {
        // re-enable handled below after dataview update
      }
    } else {
      res = await api(
        "/gui/build/" + encodeURIComponent(state.selected) + "?limit=3",
        { method: "POST" }
      );
    }

    // F0058: build zone = resume multi-objets
    const isZoneBuild = res.action === "zone_build" || isZone;
    const kind = res.ok === false ? "error" : "success";
    toast(res.message || "Renatus OK", kind);
    applyBuildResultToDataView(res, isZoneBuild);
    el.btnDvBuild.disabled = true;
    if (el.btnDvReload) el.btnDvReload.disabled = false;
    // s assurer que le graphe est sans classes build
    clearZoneBuildProgress();
    await refreshGraph();
    // A0014 / F0117: maj schema / shape / renatus_time (zone + membres)
    const sid = state.selected;
    if (sid) {
      try {
        const data = await api("/gui/step/" + encodeURIComponent(sid));
        const st = (data.config && data.config.type) || stepType || "";
        const rt =
          res.renatus_time != null ? res.renatus_time : data.renatus_time;
        renderRenatusTime(rt);
        renderShape(data.shape, st);
        renderSchema(data.schema || [], st);
        // F0117: membre_renatus_times deja en memoire serveur
        if (isZoneBuild && res.member_renatus_times) {
          state.lastMemberRenatusTimes = res.member_renatus_times;
        }
      } catch (_) {
        await selectStep(sid);
      }
    }
  } catch (e) {
    clearZoneBuildProgress();
    toast("Renatus: " + e.message, "error");
    el.dvMeta.textContent = e.message;
    if (el.btnDvBuild) el.btnDvBuild.disabled = false;
  }
}

export async function deleteStep() {
  if (!state.selected) return;
  if (state.workspace && state.workspace.read_only) {
    toast("Lecture seule", "error");
    return;
  }
  // F0082 / F0144: zone default protegee
  if (state.selected === "default" || state.selected === "main") {
    toast("Zone default protegee : suppression interdite", "error");
    return;
  }
  // F0083: annuler autosave en cours (step va disparaitre)
  if (_autoSaveTimer) {
    clearTimeout(_autoSaveTimer);
    _autoSaveTimer = null;
  }
  _pendingAutoSaveId = null;
  const id = state.selected;
  const label =
    (el.cfgName && el.cfgName.value.trim()) ||
    (el.selectedName && el.selectedName.textContent) ||
    id;
  const ok = await confirmDialog({
    title: "Supprimer le composant",
    message:
      "Supprimer « " +
      label +
      " » (id " +
      id +
      ") ?\nCette action retire le ou les fichiers YAML correspondants.",
    confirmLabel: "Supprimer",
    cancelLabel: "Annuler",
    danger: true,
  });
  if (!ok) return;
  try {
    const data = await api("/gui/step/" + encodeURIComponent(id), {
      method: "DELETE",
    });
    toast("Supprimee", "success");
    // nettoyer memo si on vient de supprimer la selection
    const tab = state.activeTab || "default";
    if (state.lastSelectedByTab && state.lastSelectedByTab[tab] === id) {
      delete state.lastSelectedByTab[tab];
    }
    if (state.lastManipulatedZone === id) {
      state.lastManipulatedZone = null;
    }
    state.selected = null;
    clearTable();
    // F0064: apres delete zone, fermer les onglets concernes (resync GUI)
    if (data && Array.isArray(data.tabs)) {
      state.tabs = data.tabs;
      if (data.active_tab) state.activeTab = data.active_tab;
      renderPipelineTabs();
    } else {
      await refreshTabs();
    }
    await refreshGraph();
    // F0081: reselection zone / dernier objet
    await ensureSelection({ force: true });
  } catch (e) {
    toast("Supprimer: " + e.message, "error");
  }
}
