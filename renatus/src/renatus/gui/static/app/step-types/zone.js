/**
 * ZoneStepType — organisationnel + objects + workers / renatus_mode (F0116).
 */
import { StepType } from "./base.js";
import {
  getSelectedZoneObjects,
  setZoneObjectsMirror,
  renderZoneObjectsPicker,
} from "../config/zone-objects.js";

export class ZoneStepType extends StepType {
  constructor() {
    super("zone");
  }

  defaultConfig(name) {
    const label = name || this.type;
    return {
      type: "zone",
      label: label,
      objects: {},
      workers: "auto",
      renatus_mode: "required_for_leaves",
    };
  }

  fieldVisibility() {
    return {
      file: false,
      mode: false,
      relationName: false,
      requires: false,
      sql: false,
      iter: false,
      script: false,
      venv: false,
      zoneObjects: true,
      zoneWorkers: true,
      zoneRenatusMode: true,
    };
  }

  applyVisibility(formEls) {
    super.applyVisibility(formEls);
    // Zone organisationnelle: pas de Mode create_* —
    // Renatus sur une zone = build des membres (workers + renatus_mode).
    this.setFieldVisible(formEls.fieldFile, false);
    this.setFieldVisible(formEls.fieldRelationName, false);
    this.setFieldVisible(formEls.fieldMode, false);
    this.setFieldVisible(formEls.fieldScript, false);
    this.setFieldVisible(formEls.fieldRequires, false);
    this.setFieldVisible(formEls.fieldIter, false);
    this.setFieldVisible(formEls.fieldVenv, false);
    this.setFieldVisible(formEls.fieldZoneObjects, true);
    this.setFieldVisible(formEls.fieldZoneWorkers, true);
    this.setFieldVisible(formEls.fieldZoneRenatusMode, true);
  }

  toConfig(form, ctx) {
    const label = form.cfgName ? form.cfgName.value.trim() : "";
    const fallback = (ctx && ctx.selected) || "zone";
    const objects = getSelectedZoneObjects();
    if (ctx && ctx.selected && objects[ctx.selected]) {
      delete objects[ctx.selected];
    }
    const workers =
      (form.cfgZoneWorkers && form.cfgZoneWorkers.value) || "auto";
    const renatus_mode =
      (form.cfgZoneRenatusMode && form.cfgZoneRenatusMode.value) ||
      "required_for_leaves";
    return {
      type: "zone",
      label: label || fallback,
      objects: objects,
      workers: workers,
      renatus_mode: renatus_mode,
    };
  }

  fromConfig(config, form) {
    super.fromConfig(config, form);
    const cfg = config || {};
    let objects = cfg.objects;
    if (Array.isArray(objects)) {
      const o = {};
      objects.forEach(function (id) {
        if (id) o[String(id)] = {};
      });
      objects = o;
    } else if (!objects || typeof objects !== "object") {
      objects = {};
    }
    setZoneObjectsMirror(objects);
    renderZoneObjectsPicker(objects);
    if (form.cfgZoneWorkers) {
      form.cfgZoneWorkers.value = cfg.workers || "auto";
    }
    if (form.cfgZoneRenatusMode) {
      form.cfgZoneRenatusMode.value =
        cfg.renatus_mode || "required_for_leaves";
    }
  }
}
