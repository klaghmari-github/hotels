/**
 * DataframeStepType — fichier → dataframe (F0053-S4 / F0119 mode).
 */
import { StepType } from "./base.js";

export class DataframeStepType extends StepType {
  constructor() {
    super("dataframe");
  }

  defaultConfig(name) {
    // F0048: label = composant UI ; name = relation physique (defaut = label)
    // F0119: mode create_if_not_exists par defaut (reuse session)
    const label = name || this.type;
    return {
      type: "dataframe",
      file: "",
      label: label,
      name: label,
      mode: "create_if_not_exists",
    };
  }

  fieldVisibility() {
    return {
      file: true,
      mode: true,
      relationName: true,
      requires: false,
      sql: false,
      iter: false,
    };
  }

  toConfig(form, ctx) {
    const config = { type: "dataframe" };
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
    config.file = form.cfgFile ? form.cfgFile.value.trim() : "";
    // F0119: defaut create_if_not_exists (pas create_or_replace des tables)
    config.mode = form.cfgMode
      ? form.cfgMode.value || "create_if_not_exists"
      : "create_if_not_exists";
    return config;
  }

  fromConfig(config, form) {
    super.fromConfig(config, form);
    if (form && form.cfgMode) {
      form.cfgMode.value =
        (config && config.mode) || "create_if_not_exists";
    }
  }
}
