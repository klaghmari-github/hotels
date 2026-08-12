/**
 * IterateStepType — boucle scenarios (F0053-S4 / F0067 / F0093 rename iterate).
 * Fichier conserve le nom iteration.js pour imports stables; type YAML = iterate.
 */
import { StepType, readSelectedRequires } from "./base.js";

export class IterationStepType extends StepType {
  constructor() {
    super("iterate");
  }

  defaultConfig(name) {
    return {
      type: "iterate",
      requires: [],
      target: "t_source",
      scenarios: "t_scenarios",
      step_view: "v_step",
      script: "SELECT * FROM v_step",
    };
  }

  fieldVisibility() {
    return {
      file: false,
      mode: false,
      relationName: false,
      requires: true,
      script: true,
      iter: true,
    };
  }

  toConfig(form, ctx) {
    const config = { type: "iterate" };
    const label = form.cfgName ? form.cfgName.value.trim() : "";
    if (label) config.label = label;
    config.requires = readSelectedRequires(form);
    config.target = form.cfgTarget ? form.cfgTarget.value.trim() : "";
    config.scenarios = form.cfgScenarios ? form.cfgScenarios.value.trim() : "";
    config.step_view = form.cfgStepView ? form.cfgStepView.value.trim() : "";
    config.script = form.cfgScript
      ? form.cfgScript.value
      : form.cfgSql
        ? form.cfgSql.value
        : "";
    return config;
  }
}

// alias export
export { IterationStepType as IterateStepType };
