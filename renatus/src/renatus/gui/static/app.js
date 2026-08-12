/**
 * Renatus GUI — entry historique monolithe (F0053-S2).
 *
 * Le runtime charge desormais les modules ES :
 *   <script type="module" src="/gui/static/app/main.js"></script>
 *
 * Ce fichier reste servi pour compat (tests HTTP /gui/static/app.js)
 * et reexporte les symboles critiques. Voir static/app/*.js pour le code.
 *
 * Pictos: data-testid="icon-{type}" (typeIconSvg dans app/icons.js).
 * YAML highlight: highlightYaml / formToYamlEditor (app/config.js).
 * Tabs: refreshTabs / switchTab / activeTab (app/tabs.js + state).
 */

export {
  typeIconPaths,
  typeIconSvg,
  typeIconSvgGroup,
  typeColor,
  typeFill,
} from "./app/icons.js";

export { escapeHtml, pad2, $ } from "./app/util.js";
export { state, el } from "./app/state.js";
export { toast, api } from "./app/api.js";

export {
  renderGraph,
  layoutNodes,
  truncateNodeText,
  openZoneTab,
  refreshGraph,
} from "./app/graph.js";

export {
  formToYamlEditor,
  yamlEditorToForm,
  configToYaml,
  yamlToConfig,
  yamlLib,
  highlightYaml,
  highlightYamlLine,
  updateYamlHighlight,
  enterConfigPresentation,
  startEditField,
  cancelEditField,
  selectStep,
  saveStep,
  buildStep,
  deleteStep,
  ensureSelection,
  zoneIdFromTab,
} from "./app/config.js";

export { bootstrap, startGui, wireGui } from "./app/bootstrap.js";

export {
  closePipelineTab,
  openNewTabDialog,
  renderPipelineTabs,
  refreshTabs,
  switchTab,
  createPipelineTab,
  addPipelineTab,
} from "./app/tabs.js";

export {
  defaultConfig,
  timestampStepName,
  renderToolbox,
  openNewStep,
} from "./app/toolbox.js";

export {
  switchBottomTab,
  openGlobalChangelogs,
  loadGlobalChangelog,
  applyChangelog,
} from "./app/changelogs.js";

export {
  showTable,
  clearTable,
  loadDataView,
  switchProcessSubTab,
  setDataViewTitle,
} from "./app/dataview.js";

export {
  setWorkspace,
  openProjectSaveDialog,
  openProjectOpenDialog,
  openProps,
} from "./app/project.js";

export {
  applyLayout,
  togglePanel,
  openPanel,
  wireLayout,
} from "./app/layout.js";
