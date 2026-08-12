/**
 * Projet open/save/create + workspace chips (F0053-S2 / F0054-S2).
 * ProjectDialogs : facade OO autour open/save/inspect.
 */
import { state, el } from "./state.js";
import { api, toast } from "./api.js";
import { confirmDialog } from "./confirm-dialog.js";
import { refreshGraph } from "./graph.js";
import { refreshTabs } from "./tabs.js";
import { renderToolbox } from "./toolbox.js";
import { UiController } from "./ui-base.js";

/**
 * Controleur dialogues projet (F0054-S2).
 */
export class ProjectDialogs extends UiController {
  constructor(root) {
    super(root || (el && el.projectDialog) || null);
  }

  open() {
    return openProjectOpenDialog();
  }

  save() {
    return openProjectSaveDialog();
  }

  inspect() {
    return inspectProjectPathNow();
  }

  scheduleInspect() {
    return scheduleProjectInspect();
  }

  setWorkspace(info) {
    return setWorkspace(info);
  }

  openProps(kind) {
    return openProps(kind);
  }

  render() {
    return this;
  }
}

/** Instance module partagee. */
export const projectDialogs = new ProjectDialogs();

export function setWorkspace(info) {
  state.connected = true;
  state.workspace = info;
  state.tools = info.tools || state.tools || [];
  el.chipDbLabel.textContent = info.db_label || "—";
  el.chipPipeLabel.textContent = info.pipeline_label || "—";
  if (el.chipProjectLabel) {
    el.chipProjectLabel.textContent =
      info.project_name || info.db_label || "—";
    el.chipProjectLabel.title = info.project_file || "";
  }
  if (el.btnProjectSave) {
    el.btnProjectSave.disabled = !!(info.read_only);
  }
  el.statusPill.textContent =
    (info.step_count || 0) + " steps · " + (info.read_only ? "RO" : "RW");
  el.statusPill.className = "pill ok";
  renderToolbox();
}

export function setProjectHint(text, kind) {
  if (!el.projectDialogHint) return;
  if (!text) {
    el.projectDialogHint.hidden = true;
    el.projectDialogHint.textContent = "";
    return;
  }
  el.projectDialogHint.hidden = false;
  el.projectDialogHint.textContent = text;
  el.projectDialogHint.className =
    "project-hint" + (kind ? " " + kind : "");
}

export function setPathZoneState(zone, stateName) {
  if (!zone) return;
  zone.classList.remove("path-zone-ok", "path-zone-new", "path-zone-err");
  if (stateName) zone.classList.add("path-zone-" + stateName);
}

export function resetProjectOpenPanels() {
  state.projectInspect = null;
  if (el.projectExistingPanel) el.projectExistingPanel.hidden = true;
  if (el.projectNewPanel) el.projectNewPanel.hidden = true;
  setPathZoneState(el.projectPathZone, null);
  if (el.projectPathStatus) {
    el.projectPathStatus.textContent = "Saisissez un chemin puis patientez…";
  }
  setProjectHint("");
  if (el.projectDialogConfirm) {
    el.projectDialogConfirm.disabled = true;
    el.projectDialogConfirm.textContent = "Ouvrir / Creer";
  }
}

export function applyProjectInspect(data) {
  state.projectInspect = data;
  if (!data || data.ok === false) {
    if (el.projectExistingPanel) el.projectExistingPanel.hidden = true;
    if (el.projectNewPanel) el.projectNewPanel.hidden = true;
    setPathZoneState(el.projectPathZone, "err");
    if (el.projectPathStatus) {
      el.projectPathStatus.textContent =
        (data && data.message) || "Chemin invalide";
    }
    setProjectHint((data && data.message) || "Chemin invalide", "err");
    if (el.projectDialogConfirm) {
      el.projectDialogConfirm.disabled = true;
      el.projectDialogConfirm.textContent = "Ouvrir / Creer";
    }
    return;
  }
  if (data.kind === "existing") {
    if (el.projectExistingPanel) el.projectExistingPanel.hidden = false;
    if (el.projectNewPanel) el.projectNewPanel.hidden = true;
    if (el.projectMetaName) el.projectMetaName.textContent = data.name || "—";
    if (el.projectMetaDb) el.projectMetaDb.textContent = data.db_path || "—";
    if (el.projectMetaPipe) {
      el.projectMetaPipe.textContent = data.pipeline_path || "—";
    }
    setPathZoneState(el.projectPathZone, "ok");
    if (el.projectPathStatus) {
      el.projectPathStatus.textContent =
        data.project_file || data.path || "Projet trouve";
    }
    setProjectHint(data.message || "Projet existant — pret a ouvrir");
    if (el.projectDialogConfirm) {
      el.projectDialogConfirm.disabled = false;
      el.projectDialogConfirm.textContent = "Ouvrir le projet";
    }
    state.projectMode = "open";
    return;
  }
  if (data.kind === "new") {
    if (el.projectExistingPanel) el.projectExistingPanel.hidden = true;
    if (el.projectNewPanel) el.projectNewPanel.hidden = false;
    if (el.projectCreateName) {
      el.projectCreateName.value =
        data.suggested_name || data.name || "";
    }
    if (el.projectDbPath) {
      el.projectDbPath.value =
        data.suggested_db_path || data.db_path || "";
    }
    if (el.projectPipePath) {
      el.projectPipePath.value =
        data.suggested_pipeline_path || data.pipeline_path || "";
    }
    setPathZoneState(el.projectPathZone, "new");
    if (el.projectPathStatus) {
      el.projectPathStatus.textContent =
        "Nouveau · " + (data.project_file || data.project_root || "");
    }
    setProjectHint(
      data.message ||
        "Nouveau projet — choisissez la base DuckDB et le dossier flow (flux)"
    );
    if (el.projectDialogConfirm) {
      el.projectDialogConfirm.disabled = false;
      el.projectDialogConfirm.textContent = "Creer le projet";
    }
    state.projectMode = "create";
    return;
  }
  resetProjectOpenPanels();
}

export async function inspectProjectPathNow() {
  const path = (el.projectPath && el.projectPath.value.trim()) || "";
  if (!path) {
    resetProjectOpenPanels();
    return;
  }
  if (el.projectPathStatus) {
    el.projectPathStatus.textContent = "Analyse du chemin…";
  }
  try {
    const data = await api("/gui/project/inspect", {
      method: "POST",
      body: JSON.stringify({ path: path }),
    });
    applyProjectInspect(data);
  } catch (e) {
    applyProjectInspect({
      ok: false,
      kind: "invalid",
      message: e.message || "Inspection impossible",
    });
  }
}

export function scheduleProjectInspect() {
  clearTimeout(state.projectInspectTimer);
  state.projectInspectTimer = setTimeout(inspectProjectPathNow, 320);
}

export async function handlePendingBranch(info) {
  if (!(info && info.pending_branch && info.pending_branch.name)) return;
  const pb = info.pending_branch;
  // F0114: dialog stylé renatus
  const ok = await confirmDialog({
    title: "Branche de travail en attente",
    message:
      "Des modifications non fusionnées existent sur « " +
      pb.name +
      " » (" +
      (pb.ahead || "?") +
      " commit(s)).\n\nCharger cette branche de travail ?",
    confirmLabel: "Charger la branche",
    cancelLabel: "Ignorer",
    danger: false,
    variant: "info",
    focusCancel: true,
  });
  if (!ok) return;
  try {
    const resumed = await api("/gui/project/resume", {
      method: "POST",
      body: JSON.stringify({ branch: pb.name }),
    });
    setWorkspace(resumed);
    await refreshTabs();
    await refreshGraph();
    toast(resumed.message || "Branche chargee", "success");
  } catch (e2) {
    toast("Branche: " + e2.message, "error");
  }
}

export async function openProjectSaveDialog() {
  if (!state.connected) {
    toast("Workspace non connecte", "error");
    return;
  }
  state.projectMode = "save";
  state.projectInspect = null;
  if (el.projectDialogTitle) {
    el.projectDialogTitle.textContent = "Sauver projet";
  }
  if (el.projectDialogConfirm) {
    el.projectDialogConfirm.disabled = false;
    el.projectDialogConfirm.textContent = "Enregistrer";
  }
  if (el.projectSaveFields) el.projectSaveFields.hidden = false;
  if (el.projectOpenFields) el.projectOpenFields.hidden = true;
  setProjectHint(
    "Enregistre db + flow dans le fichier projet (merge main)."
  );
  try {
    const info = await api("/gui/project");
    if (el.projectName) el.projectName.value = info.name || "";
    if (el.projectPathSave) {
      el.projectPathSave.value =
        info.project_file || info.suggested_path || "";
    }
    if (el.projectDialog) el.projectDialog.showModal();
  } catch (e) {
    toast("Projet: " + e.message, "error");
  }
}

export async function openProjectOpenDialog() {
  state.projectMode = "open";
  if (el.projectDialogTitle) {
    el.projectDialogTitle.textContent = "Ouvrir ou creer un projet";
  }
  if (el.projectSaveFields) el.projectSaveFields.hidden = true;
  if (el.projectOpenFields) el.projectOpenFields.hidden = false;
  resetProjectOpenPanels();
  if (el.projectPath) {
    el.projectPath.value =
      (state.workspace && state.workspace.project_file) || "";
  }
  if (el.projectDialog) el.projectDialog.showModal();
  if (el.projectPath && el.projectPath.value.trim()) {
    await inspectProjectPathNow();
  } else if (el.projectPath) {
    el.projectPath.focus();
  }
}

export function openProps(kind) {
  if (!state.workspace) return;
  if (kind === "db") {
    el.propsTitle.textContent = "Base DuckDB";
    el.propsLabel.textContent = "Chemin complet";
    el.propsPath.value = state.workspace.db_path || "";
  } else {
    el.propsTitle.textContent = "Dossier flow";
    el.propsLabel.textContent = "Chemin complet";
    el.propsPath.value = state.workspace.pipeline_path || "";
  }
  el.propsDialog.showModal();
}
