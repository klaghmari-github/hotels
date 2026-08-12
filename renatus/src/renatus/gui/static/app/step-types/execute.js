/**
 * ExecuteSqlStepType — script SQL sans relation (F0053-S4 / F0078).
 * Type YAML: execute_sql (legacy execute accepte cote serveur).
 */
import { StepType, readSelectedRequires } from "./base.js";

export class ExecuteStepType extends StepType {
  constructor() {
    super("execute_sql");
  }

  defaultConfig(name) {
    return {
      type: "execute_sql",
      requires: [],
      script: "SELECT 1",
    };
  }

  fieldVisibility() {
    return {
      file: false,
      mode: false,
      relationName: false,
      requires: true,
      script: true,
      iter: false,
    };
  }

  toConfig(form, ctx) {
    const config = { type: "execute_sql" };
    const label = form.cfgName ? form.cfgName.value.trim() : "";
    if (label) config.label = label;
    config.requires = readSelectedRequires(form);
    config.script = form.cfgScript
      ? form.cfgScript.value
      : form.cfgSql
        ? form.cfgSql.value
        : "";
    return config;
  }
}
