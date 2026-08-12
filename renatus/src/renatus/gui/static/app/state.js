/**
 * Etat partage GUI + references DOM (F0053-S2 / F0053-S4).
 * GuiState encapsule l etat; `state` et `el` restent exportes pour compat.
 */
import { $ } from "./util.js";

/**
 * Etat mutable de l application GUI.
 * Acces direct `state.connected` conserve; get/set pour API OO.
 */
export class GuiState {
  constructor(initial) {
    const defaults = {
      connected: false,
      selected: null,
      graph: { nodes: [], edges: [] },
      /** Tous les steps du projet (tous onglets) pour requires (F0039). */
      allSteps: [],
      tools: [],
      workspace: null,
      pendingTool: null,
      drag: null,
      syncing: false,
      yamlTimer: null,
      /** Step affichee dans DataView (peut etre un prerequis, pas la step selectionnee). */
      dataviewSource: null,
      dataviewIsPrereq: false,
      /** F0073: sous-onglet process Output | Error */
      processSubTab: "output",
      /** Mode dialogue projet: save | open | create (F0026/F0036). */
      projectMode: "save",
      /** Resultat inspect chemin projet (F0036). */
      projectInspect: null,
      projectInspectTimer: null,
      /** Onglet pipeline actif (F0027). */
      activeTab: "default",
      tabs: [],
      /** Onglet bas: data-preview | changelogs (F0035 global). */
      bottomTab: "data-preview",
      /** Timeline git globale du projet. */
      changelogEntries: [],
      changelogCommit: null,
      changelogPath: null,
      changelogFiles: [],
      /** F0115: scope Track (step_id + paths) */
      changelogScope: null,
      /** F0117: derniers renatus_time par membre apres zone build */
      lastMemberRenatusTimes: null,
      /**
       * F0118: progression Renatus zone (null = inactif).
       * { zoneId, jobIds, done, current, total, completed, members }
       */
      zoneBuild: null,
      /**
       * F0122: facteur de zoom du graphe Flux (1 = 100%).
       * Dimensions de base du layout en graphLayoutBase.
       */
      graphZoom: 1,
      graphLayoutBase: null,
      /**
       * F0123: pagination View datasets (dataframe/table/view).
       * pageSize defaut 3 — ne charge jamais toute la table.
       */
      dataviewPage: 1,
      dataviewPageSize: 3,
      dataviewTotalRows: null,
      dataviewTotalPages: null,
      dataviewHasNext: false,
      dataviewHasPrev: false,
      /** F0051: snapshots des champs en edition (annulation sans save). */
      fieldSnapshots: {},
      /** F0076: panneaux ouverts (sidebar/config/bottom). */
      layout: { sidebar: true, config: true, bottom: true },
      /** F0081: derniere selection par onglet (id step). */
      lastSelectedByTab: {},
      /** F0081: derniere zone manipulee (id). */
      lastManipulatedZone: null,
    };
    Object.assign(this, defaults, initial || {});
  }

  get(key) {
    return this[key];
  }

  set(key, value) {
    this[key] = value;
    return this;
  }

  /** Fusionne un objet partiel dans l etat. */
  assign(partial) {
    if (partial && typeof partial === "object") {
      Object.assign(this, partial);
    }
    return this;
  }

  /** Remet les snapshots d edition a vide. */
  clearFieldSnapshots() {
    this.fieldSnapshots = {};
    return this;
  }
}

/** Instance partagee — meme surface que l ancien objet litteral. */
export const state = new GuiState();

export const el = {
  chipDb: $("chip-db"),
  chipPipe: $("chip-pipe"),
  chipDbLabel: $("chip-db-label"),
  chipPipeLabel: $("chip-pipe-label"),
  chipProjectLabel: $("chip-project-label"),
  btnProjectOpen: $("btn-project-open"),
  btnProjectSave: $("btn-project-save"),
  btnGlobalChangelogs: $("btn-global-changelogs"),
  projectDialog: $("project-dialog"),
  projectForm: $("project-form"),
  projectDialogTitle: $("project-dialog-title"),
  projectDialogHint: $("project-dialog-hint"),
  projectName: $("project-name"),
  projectPath: $("project-path"),
  projectPathSave: $("project-path-save"),
  projectPathZone: $("project-path-zone"),
  projectPathStatus: $("project-path-status"),
  projectSaveFields: $("project-save-fields"),
  projectOpenFields: $("project-open-fields"),
  projectExistingPanel: $("project-existing-panel"),
  projectNewPanel: $("project-new-panel"),
  projectMetaName: $("project-meta-name"),
  projectMetaDb: $("project-meta-db"),
  projectMetaPipe: $("project-meta-pipe"),
  projectCreateName: $("project-create-name"),
  projectDbPath: $("project-db-path"),
  projectPipePath: $("project-pipe-path"),
  projectDialogConfirm: $("project-dialog-confirm"),
  statusPill: $("status-pill"),
  guiLayout: $("gui-layout"),
  centerLayout: $("center-layout"),
  sidebar: $("sidebar"),
  configZone: $("config-zone"),
  dataviewZone: $("dataview-zone"),
  btnCollapseSidebar: $("btn-collapse-sidebar"),
  btnCollapseConfig: $("btn-collapse-config"),
  btnCollapseBottom: $("btn-collapse-bottom"),
  railSidebar: $("rail-sidebar"),
  railConfig: $("rail-config"),
  railBottom: $("rail-bottom"),
  toolbox: $("toolbox"),
  graphCanvas: $("graph-canvas"),
  graphEmpty: $("graph-empty"),
  // F0122: controles zoom graphe
  graphZoomControls: $("graph-zoom-controls"),
  btnGraphZoomIn: $("btn-graph-zoom-in"),
  btnGraphZoomOut: $("btn-graph-zoom-out"),
  btnGraphZoomReset: $("btn-graph-zoom-reset"),
  graphZoomLabel: $("graph-zoom-label"),
  pipelineTabs: $("pipeline-tabs"),
  flowZoneSelect: $("flow-zone-select"),
  flowZoneCount: $("flow-zone-count"),
  // F0126: flow-zone-close retire (navigation select uniquement)
  flowZoneClose: null,
  // F0118: barre progression Renatus zone
  buildProgress: $("build-progress"),
  buildProgressFill: $("build-progress-fill"),
  buildProgressLabel: $("build-progress-label"),
  // F0102 / F0107: import flux
  btnImportFlow: $("btn-import-flow"),
  importFlowDialog: $("import-flow-dialog"),
  importFlowForm: $("import-flow-form"),
  importFlowSource: $("import-flow-source"),
  importFlowPathStatus: $("import-flow-path-status"),
  importFlowTarget: $("import-flow-target"),
  importFlowConflict: $("import-flow-conflict"),
  importFlowPreview: $("import-flow-preview"),
  importFlowPreviewBtn: $("import-flow-preview-btn"),
  importFlowDropzone: $("import-flow-dropzone"),
  importFlowFilePicker: $("import-flow-file-picker"),
  importFlowDirPicker: $("import-flow-dir-picker"),
  importFlowBrowseFile: $("import-flow-browse-file"),
  importFlowBrowseDir: $("import-flow-browse-dir"),
  // F0132: traitement en cours bloquant
  progressDialog: $("progress-dialog"),
  progressDialogTitle: $("progress-dialog-title"),
  progressDialogMessage: $("progress-dialog-message"),
  progressDialogFill: $("progress-dialog-fill"),
  progressDialogLabel: $("progress-dialog-label"),
  progressDialogTrack: $("progress-dialog-track"),
  btnTabAdd: $("btn-tab-add"),
  btnRefresh: $("btn-refresh-graph"),
  selectedName: $("selected-name"),
  configForm: $("config-form"),
  configPlaceholder: $("config-placeholder"),
  fileOrigin: $("file-origin"),
  cfgId: $("cfg-id"),
  cfgName: $("cfg-name"),
  cfgType: $("cfg-type"),
  cfgFile: $("cfg-file"),
  cfgFilePicker: $("cfg-file-picker"),
  fileDropzone: $("file-dropzone"),
  fileDropStatus: $("file-drop-status"),
  fileSummary: $("file-summary"),
  fileSummaryName: $("file-summary-name"),
  fileSummaryPath: $("file-summary-path"),
  btnBrowseFile: $("btn-browse-file"),
  cfgMode: $("cfg-mode"),
  cfgRelationName: $("cfg-relation-name"),
  cfgRequires: $("cfg-requires"),
  cfgRequiresPicker: $("cfg-requires-picker"),
  cfgRequiresSelected: $("cfg-requires-selected"),
  requiresEmpty: $("requires-empty"),
  // F0095: dialog edition requires (graphe zone)
  requiresEditDialog: $("requires-edit-dialog"),
  requiresEditForm: $("requires-edit-form"),
  requiresZoneSelect: $("requires-zone-select"),
  requiresEditSelected: $("requires-edit-selected"),
  requiresEditCanvas: $("requires-edit-canvas"),
  fieldDependents: $("field-dependents"),
  cfgDependents: $("cfg-dependents"),
  dependentsEmpty: $("dependents-empty"),
  fieldZones: $("field-zones"),
  cfgZones: $("cfg-zones"),
  zonesEmpty: $("zones-empty"),
  // F0091 / F0092 / F0093: schema + shape + renatus_time calculees
  fieldRenatusTime: $("field-renatus-time"),
  cfgRenatusTime: $("cfg-renatus-time"),
  fieldShape: $("field-shape"),
  cfgShape: $("cfg-shape"),
  fieldSchema: $("field-schema"),
  cfgSchema: $("cfg-schema"),
  schemaEmpty: $("schema-empty"),
  // F0067: cfgSql aliases retirees — un seul cfg-script
  cfgSql: $("cfg-script"),
  cfgSqlLabel: $("cfg-script-label"),
  cfgScript: $("cfg-script"),
  cfgScriptLabel: $("cfg-script-label"),
  cfgVenv: $("cfg-venv"),
  cfgTarget: $("cfg-target"),
  cfgScenarios: $("cfg-scenarios"),
  cfgStepView: $("cfg-step-view"),
  stepNamesList: $("step-names-list"),
  fieldFile: $("field-file"),
  fieldMode: $("field-mode"),
  fieldRelationName: $("field-relation-name"),
  fieldRequires: $("field-requires"),
  fieldZoneObjects: $("field-zone-objects"),
  cfgZoneObjects: $("cfg-zone-objects"),
  cfgZoneObjectsPicker: $("cfg-zone-objects-picker"),
  cfgZoneObjectsSelected: $("cfg-zone-objects-selected"),
  zoneObjectsEmpty: $("zone-objects-empty"),
  // F0116: zone workers + renatus_mode
  fieldZoneWorkers: $("field-zone-workers"),
  cfgZoneWorkers: $("cfg-zone-workers"),
  fieldZoneRenatusMode: $("field-zone-renatus-mode"),
  cfgZoneRenatusMode: $("cfg-zone-renatus-mode"),
  // F0128: auto-zone
  fieldAutoObject: $("field-auto-object"),
  cfgAutoObject: $("cfg-auto-object"),
  fieldAutoConvert: $("field-auto-convert"),
  btnAutoConvert: $("btn-auto-convert"),
  // F0097: dialog edition objects de zone
  zoneObjectsEditDialog: $("zone-objects-edit-dialog"),
  zoneObjectsEditForm: $("zone-objects-edit-form"),
  zoneObjectsZoneSelect: $("zone-objects-zone-select"),
  zoneObjectsEditSelected: $("zone-objects-edit-selected"),
  zoneObjectsEditCanvas: $("zone-objects-edit-canvas"),
  fieldSql: $("field-script"),
  fieldScript: $("field-script"),
  fieldVenv: $("field-venv"),
  fieldIter: $("field-iter"),
  editor: $("config-editor"),
  yamlHighlight: $("yaml-highlight"),
  yamlEditor: $("yaml-editor"),
  yamlStatus: $("yaml-status"),
  btnSave: $("btn-save"),
  btnBuild: $("btn-build"),
  btnDelete: $("btn-delete"),
  dvName: $("dataview-name"),
  dvMeta: $("dataview-meta"),
  btnDvBuild: $("btn-dv-build"),
  // F0123/F0124: pagination View + lignes/page
  dataviewPager: $("dataview-pager"),
  dataviewPagerLabel: $("dataview-pager-label"),
  dataviewPageSizeSelect: $("dataview-page-size"),
  btnDvPagePrev: $("btn-dv-page-prev"),
  btnDvPageNext: $("btn-dv-page-next"),
  // F0074: Recharger retire — alias null-safe
  btnDvReload: null,
  tabDataPreview: $("tab-data-preview"),
  tabChangelogs: $("tab-changelogs"),
  panelDataPreview: $("panel-data-preview"),
  panelChangelogs: $("panel-changelogs"),
  dataviewActions: $("dataview-actions"),
  changelogActions: $("changelog-actions"),
  btnChangelogApplyFile: $("btn-changelog-apply-file"),
  btnChangelogApplyAll: $("btn-changelog-apply-all"),
  changelogList: $("changelog-list"),
  changelogEmpty: $("changelog-empty"),
  changelogFiles: $("changelog-files"),
  changelogDiff: $("changelog-diff"),
  changelogDiffMeta: $("changelog-diff-meta"),
  resultTable: $("result-table"),
  resultHead: document.querySelector("#result-table thead"),
  resultBody: document.querySelector("#result-table tbody"),
  tableWrap: $("table-wrap"),
  processView: $("process-view"),
  processSubtabs: $("process-subtabs"),
  tabProcessOutput: $("tab-process-output"),
  tabProcessError: $("tab-process-error"),
  processOutStdout: $("process-out-stdout"),
  processOutStderr: $("process-out-stderr"),
  toast: $("toast"),
  propsDialog: $("props-dialog"),
  propsTitle: $("props-title"),
  propsLabel: $("props-label"),
  propsPath: $("props-path"),
  newStepDialog: $("new-step-dialog"),
  newStepTitle: $("new-step-title"),
  newStepDesc: $("new-step-desc"),
  newStepName: $("new-step-name"),
  newStepForm: $("new-step-form"),
  newTabDialog: $("new-tab-dialog"),
  newTabForm: $("new-tab-form"),
  newTabName: $("new-tab-name"),
};
