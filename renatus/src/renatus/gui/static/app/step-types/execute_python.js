/**
 * ExecutePythonStepType — script Python (F0055 / F0068).
 * Type distinct de execute (SQL).
 * Defaut: python local ; venv renseigne = env selectionne.
 */
import { StepType, readSelectedRequires } from "./base.js";

export class ExecutePythonStepType extends StepType {
  constructor() {
    super("execute_python");
  }

  defaultConfig(name) {
    const label = name || this.type;
    return {
      type: "execute_python",
      label: label,
      requires: [],
      script: 'print("hello from renatus")\n',
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
    const config = { type: "execute_python" };
    const label = form.cfgName ? form.cfgName.value.trim() : "";
    if (label) config.label = label;
    config.requires = readSelectedRequires(form);
    config.script = form.cfgScript ? form.cfgScript.value : "";
    const venv = form.cfgVenv ? form.cfgVenv.value.trim() : "";
    // F0068: venv vide = python local (moteur) — omis du YAML
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
