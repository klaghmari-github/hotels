/**
 * Event wiring + demarrage GUI (F0053-S2).
 */
import { state, el } from "./state.js";
import { api, toast } from "./api.js";
import { applyChangelog, openGlobalChangelogs, switchBottomTab } from "./changelogs.js";
import { buildStep, deleteStep, ensureSelection, flushAutoSave, formToYamlEditor, refreshFieldDisplays, saveStepSilent, selectStep, syncFormVisibility, syncYamlScroll, updateYamlHighlight, wireConfigPresentation, wireFileDropzone, wireRequiresEditor, wireZoneObjectsEditor, yamlEditorToForm } from "./config.js";
import {
  loadDataView,
  switchProcessSubTab,
  wireDataViewPager,
} from "./dataview.js";
import { refreshGraph, wireGraphZoom } from "./graph.js";
import { handlePendingBranch, inspectProjectPathNow, openProjectOpenDialog, openProjectSaveDialog, openProps, scheduleProjectInspect, setWorkspace } from "./project.js";
import { addPipelineTab, createPipelineTab, openNewTabDialog, refreshTabs } from "./tabs.js";
import { wireLayout } from "./layout.js";
import { defaultConfig, openNewStep, renderToolbox, timestampStepName } from "./toolbox.js";
import { wireImportFlow } from "./import-flow.js";
import { wireNotebookDialog } from "./notebook-dialog.js";
import { wireRenatusSelects } from "./renatus-select.js";

export async function bootstrap() {
  try {
    const info = await api("/health");
    if (info && info.db_path) {
      setWorkspace(info);
      await refreshTabs();
      await refreshGraph();
      // F0081: selection par defaut (zone / dernier objet)
      await ensureSelection({ force: true });
      toast("Workspace pret · " + (info.step_count || 0) + " steps", "success");
    }
  } catch (e) {
    toast("Bootstrap: " + e.message, "error");
  }
  try {
    const tools = await api("/gui/tools");
    if (tools.tools) {
      state.tools = tools.tools;
      renderToolbox();
    }
  } catch (_) {
    renderToolbox();
  }
}


/**
 * Branche tous les listeners DOM (ex top-level de l IIFE monolithe).
 */
export function wireGui() {
  // F0076: panneaux collapsables (outils / config / view)
  wireLayout();

  // --- side-effect (after openProjectOpenDialog) ---
  if (el.projectPath) {
    el.projectPath.addEventListener("input", scheduleProjectInspect);
    el.projectPath.addEventListener("change", inspectProjectPathNow);
    el.projectPath.addEventListener("blur", inspectProjectPathNow);
  }

  if (el.projectForm) {
    el.projectForm.addEventListener("close", async function () {
      if (!el.projectDialog || el.projectDialog.returnValue !== "ok") return;
      try {
        if (state.projectMode === "save") {
          const path =
            (el.projectPathSave && el.projectPathSave.value.trim()) || "";
          if (!path) {
            toast("Chemin projet requis", "error");
            return;
          }
          const name = el.projectName ? el.projectName.value.trim() : "";
          const res = await api("/gui/project/save", {
            method: "POST",
            body: JSON.stringify({ path: path, name: name || null }),
          });
          if (state.workspace) {
            state.workspace.project_file = res.path;
            state.workspace.project_name = res.name;
          }
          if (el.chipProjectLabel) {
            el.chipProjectLabel.textContent = res.name || "—";
            el.chipProjectLabel.title = res.path || "";
          }
          if (res.ok === false) {
            toast(res.message || "Merge git echoue", "error");
          } else {
            toast(res.message || "Projet enregistre (merge main)", "success");
          }
          return;
        }

        const path = (el.projectPath && el.projectPath.value.trim()) || "";
        if (!path) {
          toast("Chemin projet requis", "error");
          return;
        }

        if (!state.projectInspect) {
          await inspectProjectPathNow();
        }
        const kind =
          (state.projectInspect && state.projectInspect.kind) ||
          state.projectMode;

        if (kind === "create" || kind === "new") {
          const body = {
            path: path,
            name: el.projectCreateName
              ? el.projectCreateName.value.trim() || null
              : null,
            db_path: el.projectDbPath
              ? el.projectDbPath.value.trim() || null
              : null,
            pipeline_path: el.projectPipePath
              ? el.projectPipePath.value.trim() || null
              : null,
          };
          const info = await api("/gui/project/create", {
            method: "POST",
            body: JSON.stringify(body),
          });
          setWorkspace(info);
          state.activeTab = "default";
          await refreshTabs();
          await refreshGraph();
          toast(info.message || "Projet cree", "success");
          return;
        }

        const openPath =
          (state.projectInspect && state.projectInspect.project_file) || path;
        const info = await api("/gui/project/open", {
          method: "POST",
          body: JSON.stringify({ path: openPath }),
        });
        setWorkspace(info);
        state.activeTab = "default";
        await refreshTabs();
        await refreshGraph();
        toast(info.message || "Projet ouvert", "success");
        await handlePendingBranch(info);
      } catch (e) {
        toast("Projet: " + e.message, "error");
      }
    });
  }

  if (el.btnProjectSave) {
    el.btnProjectSave.addEventListener("click", openProjectSaveDialog);
  }
  if (el.btnProjectOpen) {
    el.btnProjectOpen.addEventListener("click", openProjectOpenDialog);
  }

  // --- side-effect (after openNewStep) ---
  if (el.newStepForm) {
    el.newStepForm.addEventListener("close", async function () {
      if (el.newStepDialog.returnValue !== "create") {
        state.pendingTool = null;
        return;
      }
      const tool = state.pendingTool;
      state.pendingTool = null;
      if (!tool) return;
      const name = el.newStepName.value.trim() || timestampStepName(tool.type);
      const config = defaultConfig(tool.type, name);
      try {
        await api("/gui/steps", {
          method: "POST",
          body: JSON.stringify({ name: name, config: config }),
        });
        toast("Step " + name + " creee", "success");
        await refreshGraph();
        await selectStep(name);
      } catch (e) {
        toast("Create: " + e.message, "error");
      }
    });
  }

  // --- side-effect (after wireFileDropzone) ---
  el.cfgType.addEventListener("change", function () {
    syncFormVisibility(el.cfgType.value);
    refreshFieldDisplays();
  });
  wireConfigPresentation();
  wireRequiresEditor();
  wireZoneObjectsEditor();
  wireImportFlow();
  // F0137: dialog notebook Jupyter-like
  wireNotebookDialog();
  // F0140: selects custom — menus restent ouverts pendant Print Screen
  wireRenatusSelects();

  // --- side-effect (after addPipelineTab) ---
  if (el.newTabForm) {
    el.newTabForm.addEventListener("close", function () {
      if (!el.newTabDialog || el.newTabDialog.returnValue !== "create") return;
      const name = el.newTabName ? el.newTabName.value.trim() : "";
      if (!name) {
        toast("Nom d'onglet requis", "error");
        return;
      }
      createPipelineTab(name);
    });
  }
  if (el.newTabName) {
    el.newTabName.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        // laisse le submit natif du form method=dialog
        return;
      }
    });
  }

  // --- side-effect (after bootstrap) ---
  // F0122: zoom graphe (boutons + Ctrl+molette) — aussi re-wire dans renderGraph
  wireGraphZoom();
  // F0123: pagination View datasets
  wireDataViewPager();
  // F0128: convertir auto-zone → zone physique
  if (el.btnAutoConvert) {
    el.btnAutoConvert.addEventListener("click", async function () {
      if (!state.selected) return;
      try {
        const res = await api(
          "/gui/auto-zone/" + encodeURIComponent(state.selected) + "/convert",
          { method: "POST", body: JSON.stringify({}) }
        );
        toast(res.message || "Zone convertie", "success");
        const { refreshTabs } = await import("./tabs.js");
        const { refreshGraph } = await import("./graph.js");
        await refreshTabs();
        if (res.id || res.zone_id) {
          const { switchTab } = await import("./tabs.js");
          await switchTab(res.id || res.zone_id);
          await selectStep(res.id || res.zone_id);
        } else {
          await refreshGraph();
        }
      } catch (e) {
        toast("Convertir: " + e.message, "error");
      }
    });
  }
  // F0080: + / refresh retires de Flux (zones via palette Composant)
  if (el.btnRefresh) {
    el.btnRefresh.addEventListener("click", refreshGraph);
  }
  if (el.btnTabAdd) {
    el.btnTabAdd.addEventListener("click", openNewTabDialog);
  }
  // F0086: plus de boutons Supprimer / Sauver / Renatus dans Config
  // (Suppr clavier, autosave, Renatus View / Ctrl+B)
  if (el.btnSave) {
    el.btnSave.hidden = true;
    el.btnSave.disabled = true;
  }
  if (el.btnBuild) el.btnBuild.addEventListener("click", buildStep);
  if (el.btnDelete) el.btnDelete.addEventListener("click", deleteStep);
  el.btnDvBuild.addEventListener("click", async function () {
    const target = state.dataviewSource || state.selected;
    if (!target) return;
    // Renatus de la step selectionnee (config) ou du prerequis affiche
    if (!state.dataviewIsPrereq || target === state.selected) {
      // A0005: sauver config (fichier choisi) avant build/preview
      const ok = await saveStepSilent();
      if (!ok) return;
      await refreshGraph();
    }
    await loadDataView(target, true, {
      asPrereq: state.dataviewIsPrereq && target !== state.selected,
    });
  });
  if (el.tabDataPreview) {
    el.tabDataPreview.addEventListener("click", function () {
      switchBottomTab("data-preview");
    });
  }
  if (el.tabChangelogs) {
    el.tabChangelogs.addEventListener("click", function () {
      switchBottomTab("changelogs");
    });
  }
  // F0073: sous-onglets Output / Error (execute_python)
  if (el.tabProcessOutput) {
    el.tabProcessOutput.addEventListener("click", function () {
      switchProcessSubTab("output");
    });
  }
  if (el.tabProcessError) {
    el.tabProcessError.addEventListener("click", function () {
      switchProcessSubTab("error");
    });
  }
  if (el.btnGlobalChangelogs) {
    el.btnGlobalChangelogs.addEventListener("click", openGlobalChangelogs);
  }
  if (el.btnChangelogApplyFile) {
    el.btnChangelogApplyFile.addEventListener("click", function () {
      applyChangelog("file");
    });
  }
  if (el.btnChangelogApplyAll) {
    el.btnChangelogApplyAll.addEventListener("click", function () {
      applyChangelog("all");
    });
  }
  el.chipDb.addEventListener("click", function () { openProps("db"); });
  el.chipPipe.addEventListener("click", function () { openProps("pipe"); });
  wireFileDropzone();

  // Formulaire → YAML + autosave (requires gere via picker + formToYamlEditor)
  [
    "cfg-name",
    "cfg-file",
    "cfg-mode",
    "cfg-relation-name",
    "cfg-script",
    "cfg-venv",
    "cfg-type",
    "cfg-target",
    "cfg-scenarios",
    "cfg-step-view",
    "cfg-zone-workers",
    "cfg-zone-renatus-mode",
  ].forEach(
    function (id) {
      const node = document.getElementById(id);
      if (node) {
        node.addEventListener("change", formToYamlEditor);
        node.addEventListener("input", formToYamlEditor);
      }
    }
  );

  // YAML → formulaire (debounce) + recoloration live (F0020)
  if (el.editor) {
    el.editor.addEventListener("input", function () {
      updateYamlHighlight();
      if (state.syncing) return;
      clearTimeout(state.yamlTimer);
      state.yamlTimer = setTimeout(yamlEditorToForm, 280);
    });
    el.editor.addEventListener("scroll", syncYamlScroll);
    // Tab insere 2 espaces (confort edition YAML)
    el.editor.addEventListener("keydown", function (ev) {
      if (ev.key !== "Tab") return;
      ev.preventDefault();
      const start = el.editor.selectionStart;
      const end = el.editor.selectionEnd;
      const v = el.editor.value;
      el.editor.value = v.slice(0, start) + "  " + v.slice(end);
      el.editor.selectionStart = el.editor.selectionEnd = start + 2;
      updateYamlHighlight();
      clearTimeout(state.yamlTimer);
      state.yamlTimer = setTimeout(yamlEditorToForm, 280);
    });
  }

  /* Raccourcis clavier UX (F0029 / F0063) */
  document.addEventListener("keydown", function (ev) {
    const mod = ev.ctrlKey || ev.metaKey;
    const tag = (ev.target && ev.target.tagName) || "";
    const inField =
      tag === "INPUT" ||
      tag === "TEXTAREA" ||
      tag === "SELECT" ||
      (ev.target && ev.target.isContentEditable);
    const dialogOpen =
      document.querySelector("dialog[open]") != null;

    // F0063 / F0086: Delete / Suppr → supprimer composant selectionne
    // (pas dans un champ de saisie ni dialogue ouvert; default protegee)
    if (
      !mod &&
      !dialogOpen &&
      !inField &&
      (ev.key === "Delete" || ev.key === "Del")
    ) {
      if (
        state.selected &&
        state.selected !== "default" &&
        !(state.workspace && state.workspace.read_only)
      ) {
        ev.preventDefault();
        deleteStep();
      }
      return;
    }

    if (!mod) return;
    // F0083: Ctrl+S = flush autosave (evite save navigateur)
    if (mod && !ev.shiftKey && (ev.key === "s" || ev.key === "S")) {
      if (state.selected && !(state.workspace && state.workspace.read_only)) {
        ev.preventDefault();
        flushAutoSave();
      }
      return;
    }
    // F0086: Ctrl+B → Renatus (plus de bouton Config; View a aussi Renatus)
    if (mod && !ev.shiftKey && (ev.key === "b" || ev.key === "B")) {
      if (state.selected && !(state.workspace && state.workspace.read_only)) {
        if (!inField || tag === "TEXTAREA" || tag === "INPUT") {
          ev.preventDefault();
          buildStep();
        }
      }
      return;
    }
    // Ctrl+Shift+S : sauver projet
    if (mod && ev.shiftKey && (ev.key === "s" || ev.key === "S")) {
      if (el.btnProjectSave && !el.btnProjectSave.disabled) {
        ev.preventDefault();
        el.btnProjectSave.click();
      }
    }
  });
}

export function startGui() {
  wireGui();
  bootstrap();
}
