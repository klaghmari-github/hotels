/**
 * Form ↔ YAML sync + visibility (F0054-S2).
 * syncFormVisibility / configFromForm deleguent au StepTypeRegistry.
 */
import { state, el } from "../state.js";
import { stepTypeRegistry } from "../step-types/registry.js";
import {
  refreshStepNamesDatalist,
  renderRequiresPicker,
  splitRequires,
} from "./requires.js";
import {
  getSelectedZoneObjects,
  renderZoneObjectsPicker,
} from "./zone-objects.js";
import {
  configToYaml,
  formatYamlError,
  setYamlStatus,
  updateYamlHighlight,
  yamlToConfig,
} from "./yaml-editor.js";
import { enterConfigPresentation } from "./pencil.js";
import { scheduleAutoSave } from "./step-crud.js";

/**
 * Visibilite des champs config selon le type — registry StepType (F0053-S4).
 * Signature exportee conservee pour tests / bootstrap.
 */
export function syncFormVisibility(type) {
  const t = String(type || "").trim() || "table";
  // CSS data-step-type (zone: pas de Mode / file / name…)
  if (el.configForm) {
    el.configForm.setAttribute("data-step-type", t);
  }
  stepTypeRegistry.applyVisibility(t, el);
  if (el.fieldDependents) {
    // dependents utiles pour tous sauf pure zone vide ok
    el.fieldDependents.hidden = false;
  }
  // F0067: champ unifie Script (SQL ou Python selon le type)
  if (el.cfgScriptLabel) {
    el.cfgScriptLabel.textContent = "Script";
  }
  if (el.cfgSqlLabel) {
    el.cfgSqlLabel.textContent = "Script";
  }
  if (el.fieldRequires && !el.fieldRequires.hidden) {
    // Miroir hidden = source de verite a l'ouverture / sync YAML
    // (evite de relire d anciennes checkboxes du picker).
    renderRequiresPicker(
      splitRequires(el.cfgRequires ? el.cfgRequires.value : "")
    );
  }
  if (el.fieldZoneObjects && !el.fieldZoneObjects.hidden) {
    renderZoneObjectsPicker(getSelectedZoneObjects());
  }
  refreshStepNamesDatalist();
}

/**
 * Config YAML depuis le formulaire — delegue au StepType (F0053-S4).
 * Signature exportee conservee pour tests / saveStep.
 */
export function configFromForm() {
  const type = el.cfgType.value;
  return stepTypeRegistry.toConfig(type, el, { selected: state.selected });
}

export function formToYamlEditor() {
  if (state.syncing || !el.editor) return;
  let ok = false;
  try {
    state.syncing = true;
    const config = configFromForm();
    el.editor.value = configToYaml(config);
    updateYamlHighlight();
    setYamlStatus("", "ok");
    ok = true;
  } catch (e) {
    setYamlStatus(e.message, "err");
  } finally {
    state.syncing = false;
  }
  // F0083: toute edition formulaire → YAML → autosave
  if (ok) scheduleAutoSave();
}

export function yamlEditorToForm() {
  if (state.syncing || !el.editor) return;
  updateYamlHighlight();
  let ok = false;
  try {
    state.syncing = true;
    const config = yamlToConfig(el.editor.value);
    applyConfigToFormFields(config);
    setYamlStatus("", "ok");
    ok = true;
  } catch (e) {
    setYamlStatus(formatYamlError(e), "err");
  } finally {
    state.syncing = false;
  }
  // F0083: YAML valide → autosave
  if (ok) scheduleAutoSave();
}

export function applyConfigToFormFields(config) {
  const type = (config && config.type) || "table";
  el.cfgType.value = type;
  // F0053-S4: remplissage champs via StepType.fromConfig
  stepTypeRegistry.fromConfig(config || {}, el);
  // Visibility + picker depuis le miroir requires (deja renseigne)
  syncFormVisibility(type);
}

export function fillForm(name, config, meta) {
  state.syncing = true;
  try {
    const info = meta || {};
    // F0031: id immutable (readonly) ; label editable
    if (el.cfgId) {
      el.cfgId.value = info.id || name;
      el.cfgId.readOnly = true;
    }
    el.cfgName.value =
      info.label ||
      (config && config.label) ||
      name;
    el.cfgName.readOnly = false;
    applyConfigToFormFields(config);
    // A0011: YAML editeur = config type-safe (toConfig), pas le dict brut
    // (evite d afficher file: sur une zone si YAML disque pollue)
    let cfgShow;
    try {
      cfgShow = configFromForm();
    } catch (_) {
      cfgShow = Object.assign({}, config || {});
    }
    if (el.cfgName.value) cfgShow.label = el.cfgName.value;
    el.editor.value = configToYaml(cfgShow);
    updateYamlHighlight();
    setYamlStatus("", "ok");
  } catch (e) {
    el.editor.value = String(config && config.type ? "type: " + config.type : "");
    updateYamlHighlight();
    setYamlStatus(e.message, "err");
  } finally {
    state.syncing = false;
    // F0047: mode presentation apres chargement d une step existante
    enterConfigPresentation();
  }
}
