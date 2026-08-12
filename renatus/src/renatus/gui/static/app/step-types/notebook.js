/**
 * NotebookStepType — cellule Python interactive (F0137).
 * Meme session persistante que execute_python ; edition script = dialog Jupyter-like.
 */
import { StepType, readSelectedRequires } from "./base.js";

export class NotebookStepType extends StepType {
  constructor() {
    super("notebook");
  }

  defaultConfig(name) {
    const label = name || this.type;
    return {
      type: "notebook",
      label: label,
      requires: [],
      script:
        "# Notebook renatus — session Python partagee\n" +
        "# Les variables survivent d une execution a l autre.\n" +
        'print("notebook ready")\n',
      venv: "",
    };
  }

  fieldVisibility() {
    return {
      file: false,
      mode: false,
      relationName: false,
      requires: true,
      sql: false,
      iter: false,
      script: true,
      venv: true,
    };
  }

  toConfig(form, ctx) {
    const config = { type: "notebook" };
    const label = form.cfgName ? form.cfgName.value.trim() : "";
    if (label) config.label = label;
    config.requires = readSelectedRequires(form);
    config.script = form.cfgScript ? form.cfgScript.value : "";
    const venv = form.cfgVenv ? form.cfgVenv.value.trim() : "";
    if (venv) config.venv = venv;
    return config;
  }

  fromConfig(config, form) {
    super.fromConfig(config, form);
    const cfg = config || {};
    if (form.cfgScript) {
      form.cfgScript.value =
        cfg.script != null ? String(cfg.script) : "";
    }
    if (form.cfgVenv) {
      form.cfgVenv.value =
        cfg.venv != null && String(cfg.venv).trim()
          ? String(cfg.venv).trim()
          : "";
    }
  }
}
