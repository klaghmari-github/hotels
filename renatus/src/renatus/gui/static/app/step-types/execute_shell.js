/**
 * ExecuteShellStepType — commandes shell (F0075).
 * Type distinct de execute (SQL) et execute_python.
 */
import { StepType, readSelectedRequires } from "./base.js";

export class ExecuteShellStepType extends StepType {
  constructor() {
    super("execute_shell");
  }

  defaultConfig(name) {
    const label = name || this.type;
    return {
      type: "execute_shell",
      label: label,
      requires: [],
      script: 'echo "hello from renatus shell"\n',
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
      venv: false,
    };
  }

  toConfig(form, ctx) {
    const config = { type: "execute_shell" };
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
