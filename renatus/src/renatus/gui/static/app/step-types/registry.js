/**
 * StepTypeRegistry — type YAML string → StepType (F0053-S4).
 * Parallele front de pipeline.steps.factory.REGISTRY.
 */
import { StepType } from "./base.js";
import { DataframeStepType } from "./dataframe.js";
import { TableStepType } from "./table.js";
import { ViewStepType } from "./view.js";
import { ExecuteStepType } from "./execute.js";
import { ExecutePythonStepType } from "./execute_python.js";
import { NotebookStepType } from "./notebook.js";
import { ExecuteShellStepType } from "./execute_shell.js";
import { IterationStepType } from "./iteration.js";
import { ZoneStepType } from "./zone.js";
import {
  AllZoneStepType,
  BackZoneStepType,
  BidZoneStepType,
  FlatZoneStepType,
  ForZoneStepType,
} from "./auto_zone.js";

export class StepTypeRegistry {
  constructor() {
    /** @type {Map<string, StepType>} */
    this._types = new Map();
  }

  /**
   * Enregistre une instance (ou classe) StepType.
   * @param {StepType|Function} stepType
   * @returns {this}
   */
  register(stepType) {
    const inst =
      typeof stepType === "function" ? new stepType() : stepType;
    if (!inst || !inst.type) {
      throw new Error("StepTypeRegistry.register: type manquant");
    }
    this._types.set(inst.type, inst);
    return this;
  }

  /**
   * @param {string} type
   * @returns {StepType|undefined}
   */
  get(type) {
    return this._types.get(type);
  }

  /**
   * @param {string} type
   * @returns {boolean}
   */
  has(type) {
    return this._types.has(type);
  }

  /**
   * Types enregistres (ordre d insertion).
   * @returns {string[]}
   */
  types() {
    return Array.from(this._types.keys());
  }

  /**
   * @returns {StepType[]}
   */
  all() {
    return Array.from(this._types.values());
  }

  /**
   * Config par defaut pour un type (fallback { type } si inconnu).
   * @param {string} type
   * @param {string} [name]
   * @returns {object}
   */
  defaultConfig(type, name) {
    const st = this.get(type);
    if (st) return st.defaultConfig(name);
    return { type: type };
  }

  /**
   * Visibilite formulaire.
   * @param {string} type
   * @param {object} formEls
   */
  applyVisibility(type, formEls) {
    const st = this.get(type);
    if (st) st.applyVisibility(formEls);
  }

  /**
   * Config depuis formulaire.
   * @param {string} type
   * @param {object} form
   * @param {object} [ctx]
   * @returns {object}
   */
  toConfig(type, form, ctx) {
    const st = this.get(type);
    if (st) return st.toConfig(form, ctx);
    const config = { type: type };
    const label = form && form.cfgName ? form.cfgName.value.trim() : "";
    if (label) config.label = label;
    return config;
  }

  /**
   * Remplit le formulaire depuis config.
   * @param {object} config
   * @param {object} form
   */
  fromConfig(config, form) {
    const type = (config && config.type) || "table";
    const st = this.get(type) || this.get("table");
    if (st) st.fromConfig(config, form);
  }
}

/**
 * Construit le registry avec les types GUI (F0055 + F0075 shell).
 * @returns {StepTypeRegistry}
 */
export function createDefaultRegistry() {
  const reg = new StepTypeRegistry();
  reg
    .register(new DataframeStepType())
    .register(new TableStepType())
    .register(new ViewStepType())
    .register(new ExecuteStepType())
    .register(new ExecutePythonStepType())
    .register(new NotebookStepType())
    .register(new ExecuteShellStepType())
    .register(new IterationStepType())
    .register(new ZoneStepType())
    .register(new FlatZoneStepType())
    .register(new AllZoneStepType())
    .register(new BackZoneStepType())
    .register(new ForZoneStepType())
    .register(new BidZoneStepType());
  return reg;
}

/** Instance partagee (singleton app). */
export const stepTypeRegistry = createDefaultRegistry();

export {
  StepType,
  DataframeStepType,
  TableStepType,
  ViewStepType,
  ExecuteStepType,
  ExecutePythonStepType,
  ExecuteShellStepType,
  IterationStepType,
  ZoneStepType,
  AllZoneStepType,
  BackZoneStepType,
  ForZoneStepType,
  BidZoneStepType,
};
