/**
 * GuiApp — bootstrap OO de Renatus GUI (F0053-S4 / F0054-S2).
 *
 * Possede le demarrage (wire + bootstrap HTTP) et les controleurs UI.
 */
import { apiClient } from "./api.js";
import { bootstrap, startGui, wireGui } from "./bootstrap.js";
import { ChangelogPanel, changelogPanel } from "./changelogs.js";
import { ConfigPanel, configPanel } from "./config.js";
import { DataViewPanel, dataViewPanel } from "./dataview.js";
import { GraphCanvas, graphCanvas } from "./graph.js";
import { ProjectDialogs, projectDialogs } from "./project.js";
import { state, GuiState } from "./state.js";
import { stepTypeRegistry } from "./step-types/registry.js";
import { PipelineTabs, pipelineTabs } from "./tabs.js";
import { Toolbox, toolbox } from "./toolbox.js";

export class GuiApp {
  /**
   * @param {object} [options]
   * @param {GuiState} [options.state]
   * @param {import("./api.js").ApiClient} [options.api]
   * @param {import("./step-types/registry.js").StepTypeRegistry} [options.stepTypes]
   */
  constructor(options) {
    const opts = options || {};
    this.state = opts.state || state;
    this.api = opts.api || apiClient;
    this.stepTypes = opts.stepTypes || stepTypeRegistry;
    // Singletons module — free functions + app partagent les memes instances
    this.toolbox = opts.toolbox || toolbox;
    this.graph = opts.graph || graphCanvas;
    this.tabs = opts.tabs || pipelineTabs;
    this.config = opts.config || configPanel;
    this.project = opts.project || projectDialogs;
    this.changelogs = opts.changelogs || changelogPanel;
    this.dataview = opts.dataview || dataViewPanel;
    this._started = false;
  }

  /**
   * Branche les listeners DOM + charge le workspace.
   * @returns {this}
   */
  start() {
    if (this._started) return this;
    this._started = true;
    wireGui();
    bootstrap();
    return this;
  }

  /**
   * Alias de start() — meme comportement que l ancien startGui().
   */
  bootstrap() {
    return this.start();
  }
}

/** Instance paresseuse pour entry main. */
let _app = null;

/**
 * Retourne (ou cree) l instance GuiApp.
 * @param {object} [options]
 * @returns {GuiApp}
 */
export function getGuiApp(options) {
  if (!_app) {
    _app = new GuiApp(options);
  }
  return _app;
}

/**
 * Demarre le GUI (compat export fonctionnel).
 * @returns {GuiApp}
 */
export function startGuiApp() {
  const app = getGuiApp();
  app.start();
  return app;
}

// Re-export startGui du bootstrap pour import unique si besoin
export { startGui };

// Re-export classes pour imports externes / tests
export {
  ChangelogPanel,
  ConfigPanel,
  DataViewPanel,
  GraphCanvas,
  PipelineTabs,
  ProjectDialogs,
  Toolbox,
};
