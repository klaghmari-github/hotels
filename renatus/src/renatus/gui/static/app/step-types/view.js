/**
 * ViewStepType — script SQL → vue (F0053-S4 / F0067).
 */
import { StepType, readSelectedRequires } from "./base.js";

export class ViewStepType extends StepType {
  constructor() {
    super("view");
  }

  defaultConfig(name) {
    const label = name || this.type;
    return {
      type: "view",
      label: label,
      name: label,
      mode: "create_or_replace",
      requires: [],
      script: "SELECT 1 AS id",
    };
  }

  fieldVisibility() {
    return {
      file: false,
      mode: true,
      relationName: true,
      requires: true,
      script: true,
      iter: false,
    };
  }

  toConfig(form, ctx) {
    const config = { type: "view" };
    const label = form.cfgName ? form.cfgName.value.trim() : "";
    if (label) config.label = label;
    const rel = form.cfgRelationName
      ? form.cfgRelationName.value.trim()
      : "";
    if (rel) {
      config.name = rel;
    } else if (label) {
      config.name = label;
    }
    config.mode = form.cfgMode ? form.cfgMode.value : "create_or_replace";
    config.requires = readSelectedRequires(form);
    config.script = form.cfgScript
      ? form.cfgScript.value
      : form.cfgSql
        ? form.cfgSql.value
        : "";
    return config;
  }
}
