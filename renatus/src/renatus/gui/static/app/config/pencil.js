/**
 * Config presentation / edition champ crayon (F0047 / F0051 / F0054-S2).
 * F0084: Enter / blur sur champ monoligne → commit + save immediate.
 */
import { state, el } from "../state.js";
import { formToYamlEditor } from "./form-sync.js";
import { flushAutoSave } from "./step-crud.js";

export function fieldControlValue(id) {
  const node = document.getElementById(id);
  if (!node) return "";
  if (node.tagName === "SELECT") {
    const opt = node.options[node.selectedIndex];
    return opt ? opt.text || opt.value : node.value;
  }
  return node.value || "";
}

export function basenamePathUi(p) {
  if (!p) return "—";
  const s = String(p);
  const parts = s.split(/[/\\]/);
  return parts[parts.length - 1] || s;
}

export function refreshFieldDisplays() {
  document.querySelectorAll("[data-display]").forEach(function (disp) {
    const id = disp.getAttribute("data-display");
    if (!id) return;
    if (id === "cfg-iter") {
      const t = (el.cfgTarget && el.cfgTarget.value) || "—";
      const s = (el.cfgScenarios && el.cfgScenarios.value) || "—";
      const v = (el.cfgStepView && el.cfgStepView.value) || "—";
      disp.textContent = "target: " + t + " · scenarios: " + s + " · step_view: " + v;
      return;
    }
    if (id === "cfg-file") {
      const path = (el.cfgFile && el.cfgFile.value.trim()) || "";
      disp.textContent = path ? basenamePathUi(path) : "—";
      disp.title = path || "Aucun fichier source";
      return;
    }
    const val = fieldControlValue(id);
    if (disp.tagName === "PRE") {
      disp.textContent = val || "—";
    } else {
      disp.textContent = val || "—";
    }
    disp.title = val || "";
  });
  // resume fichier (view riche si path)
  const path = (el.cfgFile && el.cfgFile.value.trim()) || "";
  if (el.fileSummaryName) {
    el.fileSummaryName.textContent = path ? basenamePathUi(path) : "Aucun fichier";
  }
  if (el.fileSummaryPath) {
    el.fileSummaryPath.textContent = path || "—";
  }
  if (el.fileDropStatus && path) {
    el.fileDropStatus.textContent = "Fichier : " + path;
  }
}

export function fieldSnapshotKey(field) {
  if (!field) return "";
  return (
    field.getAttribute("data-edit-target") ||
    field.getAttribute("data-field") ||
    field.id ||
    ""
  );
}

export function resolveEditableField(editId) {
  if (!editId) return null;
  let field = document.querySelector(
    '.field-editable[data-edit-target="' + editId + '"]'
  );
  if (!field && editId === "cfg-target") {
    field = document.getElementById("field-iter");
  }
  if (!field && editId === "cfg-file") {
    field = el.fieldFile;
  }
  if (!field) {
    const btn = document.querySelector('.btn-pencil[data-edit="' + editId + '"]');
    field = btn && btn.closest(".field-editable");
  }
  return field || null;
}

/** Capture les valeurs des controles du champ (pour annulation F0051). */
export function snapshotFieldControls(field) {
  const snap = { values: {}, fileDropStatus: null };
  if (!field) return snap;
  field.querySelectorAll("input, select, textarea").forEach(function (node) {
    if (!node.id) return;
    if (node.type === "file" || node.type === "hidden") return;
    snap.values[node.id] = node.value;
  });
  if (field === el.fieldFile && el.fileDropStatus) {
    snap.fileDropStatus = el.fileDropStatus.textContent;
  }
  return snap;
}

export function restoreFieldControls(field, snap) {
  if (!field || !snap || !snap.values) return;
  Object.keys(snap.values).forEach(function (id) {
    const node = document.getElementById(id);
    if (node) node.value = snap.values[id];
  });
  if (field === el.fieldFile && el.fileDropStatus && snap.fileDropStatus != null) {
    el.fileDropStatus.textContent = snap.fileDropStatus;
  }
}

export function setPencilActive(field, active) {
  if (!field) return;
  const btn = field.querySelector(".btn-pencil");
  if (!btn) return;
  btn.setAttribute("aria-pressed", active ? "true" : "false");
  const idle = btn.getAttribute("data-title-idle") || btn.getAttribute("title") || "Modifier";
  if (!btn.getAttribute("data-title-idle")) {
    btn.setAttribute("data-title-idle", idle);
  }
  if (active) {
    btn.title = "Annuler et revenir a la presentation";
    btn.setAttribute("aria-label", "Annuler et revenir a la presentation");
  } else {
    const t = btn.getAttribute("data-title-idle") || "Modifier";
    btn.title = t;
    btn.setAttribute("aria-label", t);
  }
}

export function enterConfigPresentation() {
  if (!el.configForm) return;
  el.configForm.classList.add("is-presentation");
  el.configForm.classList.remove("is-editing-all");
  state.fieldSnapshots = {};
  document.querySelectorAll(".field-editable.is-editing").forEach(function (f) {
    f.classList.remove("is-editing");
    setPencilActive(f, false);
  });
  document.querySelectorAll(".btn-pencil").forEach(function (btn) {
    btn.setAttribute("aria-pressed", "false");
  });
  refreshFieldDisplays();
  updateFileFieldMode();
}

export function updateFileFieldMode() {
  const field = el.fieldFile;
  if (!field || field.hidden) return;
  const path = (el.cfgFile && el.cfgFile.value.trim()) || "";
  const editing = field.classList.contains("is-editing");
  const empty = !path;
  if (empty) {
    field.classList.add("file-empty");
    field.classList.remove("file-filled");
  } else {
    field.classList.remove("file-empty");
    field.classList.add("file-filled");
  }
  // F0100: dropzone / chemin UNIQUEMENT en edition (crayon).
  // View: field-value (— ou chemin) ; resume optionnel si fichier present.
  field.classList.toggle("show-file-editor", editing);
  if (el.fileSummary) {
    // resume riche en view si fichier ; sinon field-value affiche "—"
    el.fileSummary.hidden = empty || editing;
  }
}

/**
 * F0051: desactive le crayon, restaure le snapshot, repasse en presentation.
 * N annule pas les champs deja sauvegardes (uniquement l edition en cours).
 */
export function cancelEditField(field) {
  if (!field) return;
  const key = fieldSnapshotKey(field);
  const snap = key && state.fieldSnapshots ? state.fieldSnapshots[key] : null;
  if (snap) {
    restoreFieldControls(field, snap);
    delete state.fieldSnapshots[key];
  }
  field.classList.remove("is-editing");
  setPencilActive(field, false);
  // garder le formulaire en presentation (autres champs non ouverts)
  if (el.configForm) el.configForm.classList.add("is-presentation");
  refreshFieldDisplays();
  updateFileFieldMode();
  formToYamlEditor();
}

/**
 * Champ monoligne (input text / select) — pas textarea multi-ligne.
 * F0084
 */
export function isSingleLineControl(node) {
  if (!node || !node.tagName) return false;
  const tag = node.tagName.toUpperCase();
  if (tag === "SELECT") return true;
  if (tag === "INPUT") {
    const t = String(node.type || "text").toLowerCase();
    return (
      t === "text" ||
      t === "search" ||
      t === "url" ||
      t === "number" ||
      t === "email" ||
      t === "password" ||
      t === ""
    );
  }
  return false;
}

/**
 * Champ multi-ligne (textarea) — Enter = newline ; Ctrl+Enter = commit.
 * F0085
 */
export function isMultiLineControl(node) {
  if (!node || !node.tagName) return false;
  return node.tagName.toUpperCase() === "TEXTAREA";
}

/** Controles editables (mono ou multi) dans un field-editable. */
export function isFieldEditControl(node) {
  return isSingleLineControl(node) || isMultiLineControl(node);
}

/**
 * F0084: valide l edition en cours (garde les valeurs), presentation + save immediate.
 * Contrairement a cancelEditField, ne restaure pas le snapshot.
 */
export function commitEditField(field) {
  if (!field || !field.classList.contains("is-editing")) return false;
  const key = fieldSnapshotKey(field);
  if (key && state.fieldSnapshots) {
    delete state.fieldSnapshots[key];
  }
  field.classList.remove("is-editing");
  setPencilActive(field, false);
  if (el.configForm) el.configForm.classList.add("is-presentation");
  refreshFieldDisplays();
  updateFileFieldMode();
  formToYamlEditor();
  // save immediate (debounce annule + PUT)
  flushAutoSave();
  return true;
}

/**
 * Active l edition du champ, ou la desactive (toggle) si deja en edition.
 * Un re-click annule les changements non sauvegardes de ce champ.
 */
export function startEditField(editId) {
  if (!el.configForm || !editId) return;
  const field = resolveEditableField(editId);
  if (!field) return;

  // F0095: Requires → popup graphe zone (pas d edition inline)
  if (editId === "cfg-requires" || field === el.fieldRequires) {
    import("./requires.js").then(function (mod) {
      if (mod && typeof mod.openRequiresEditor === "function") {
        mod.openRequiresEditor();
      }
    });
    return;
  }

  // F0097: Objects de zone → popup graphe (dblclick pour copier)
  if (editId === "cfg-zone-objects" || field === el.fieldZoneObjects) {
    import("./zone-objects.js").then(function (mod) {
      if (mod && typeof mod.openZoneObjectsEditor === "function") {
        mod.openZoneObjectsEditor();
      }
    });
    return;
  }

  // F0137 / F0146: notebook multi-cellules (.ipynb) ou Python (.py)
  if (editId === "cfg-script" || field === el.fieldScript) {
    const stype =
      (el.cfgType && el.cfgType.value) ||
      (state.graph &&
        state.graph.nodes &&
        (state.graph.nodes.find(function (n) {
          return n && n.id === state.selected;
        }) || {}).type) ||
      "";
    if (stype === "notebook" || stype === "execute_python") {
      import("../notebook-dialog.js").then(function (mod) {
        if (mod && typeof mod.openNotebookDialog === "function") {
          mod.openNotebookDialog({
            mode: stype,
            script: el.cfgScript ? el.cfgScript.value : "",
            notebook: state._stepNotebook || null,
          });
        }
      });
      return;
    }
  }

  // Toggle off = annuler et revenir en presentation
  if (field.classList.contains("is-editing")) {
    cancelEditField(field);
    return;
  }

  // F0084: commiter un autre champ encore ouvert avant d en editer un nouveau
  document.querySelectorAll(".field-editable.is-editing").forEach(function (f) {
    if (f !== field) commitEditField(f);
  });

  const key = fieldSnapshotKey(field) || editId;
  if (!state.fieldSnapshots) state.fieldSnapshots = {};
  state.fieldSnapshots[key] = snapshotFieldControls(field);

  field.classList.add("is-editing");
  // Le formulaire reste en presentation: seul ce champ passe en edition
  el.configForm.classList.add("is-presentation");
  el.configForm.classList.remove("is-editing-all");
  setPencilActive(field, true);
  updateFileFieldMode();

  const control = document.getElementById(editId);
  if (control) {
    try {
      control.focus();
      if (control.select) control.select();
    } catch (_) {}
  }
}

/** Flag: blur ne doit pas commit si on annule via crayon (mousedown). */
let _suppressBlurCommit = false;

export function wireConfigPresentation() {
  if (!el.configForm) return;
  // etat initial des crayons
  el.configForm.querySelectorAll(".btn-pencil").forEach(function (btn) {
    if (!btn.getAttribute("data-title-idle")) {
      btn.setAttribute("data-title-idle", btn.getAttribute("title") || "Modifier");
    }
    btn.setAttribute("aria-pressed", "false");
    // F0084: mousedown preventDefault → pas de blur avant le click cancel
    btn.addEventListener("mousedown", function (ev) {
      _suppressBlurCommit = true;
      ev.preventDefault();
    });
  });
  el.configForm.addEventListener("click", function (ev) {
    const btn = ev.target.closest && ev.target.closest(".btn-pencil");
    if (!btn) return;
    ev.preventDefault();
    _suppressBlurCommit = false;
    const editId = btn.getAttribute("data-edit");
    startEditField(editId);
  });

  // F0084 / F0085: raccourcis commit
  // - monoligne: Enter
  // - multi-ligne (textarea): Ctrl+Enter (ou Cmd+Enter)
  // - Enter seul dans textarea = nouvelle ligne
  el.configForm.addEventListener("keydown", function (ev) {
    if (ev.key !== "Enter" || ev.isComposing) return;
    const t = ev.target;
    const field = t.closest && t.closest(".field-editable");
    if (!field || !field.classList.contains("is-editing")) return;

    if (isMultiLineControl(t)) {
      // Ctrl/Cmd+Enter → commit ; Enter seul → newline
      const mod = ev.ctrlKey || ev.metaKey;
      if (!mod || ev.shiftKey) return;
      ev.preventDefault();
      commitEditField(field);
      try {
        t.blur();
      } catch (_) {}
      return;
    }

    if (!isSingleLineControl(t)) return;
    if (ev.shiftKey) return;
    // select: Enter peut ouvrir la liste — commit via change/blur
    if (t.tagName === "SELECT") return;
    ev.preventDefault();
    commitEditField(field);
    try {
      t.blur();
    } catch (_) {}
  });

  // F0084 / F0085: blur (click dehors / tab) → commit mono et multi-ligne
  el.configForm.addEventListener(
    "focusout",
    function (ev) {
      const t = ev.target;
      if (!isFieldEditControl(t)) return;
      const field = t.closest && t.closest(".field-editable");
      if (!field || !field.classList.contains("is-editing")) return;
      // relatedTarget encore dans le meme champ (ex. autre input iteration)
      const next = ev.relatedTarget;
      if (next && field.contains(next)) return;
      // crayon / cancel en cours
      if (_suppressBlurCommit) {
        _suppressBlurCommit = false;
        return;
      }
      // defer: laisser le click crayon / autre handler s executer
      setTimeout(function () {
        if (_suppressBlurCommit) {
          _suppressBlurCommit = false;
          return;
        }
        if (!field.classList.contains("is-editing")) return;
        // focus encore dans le champ ?
        const active = document.activeElement;
        if (active && field.contains(active)) return;
        commitEditField(field);
      }, 0);
    },
    true
  );

  // select: change = choix fait → commit (monoligne)
  el.configForm.addEventListener("change", function (ev) {
    const t = ev.target;
    if (!t || t.tagName !== "SELECT") return;
    if (!isSingleLineControl(t)) return;
    const field = t.closest && t.closest(".field-editable");
    if (!field || !field.classList.contains("is-editing")) return;
    // petit defer pour laisser formToYamlEditor (input/change bootstrap) tourner
    setTimeout(function () {
      if (field.classList.contains("is-editing")) {
        commitEditField(field);
      }
    }, 0);
  });

  // maj resume fichier quand chemin change
  if (el.cfgFile) {
    el.cfgFile.addEventListener("input", function () {
      refreshFieldDisplays();
      updateFileFieldMode();
    });
    el.cfgFile.addEventListener("change", function () {
      refreshFieldDisplays();
      updateFileFieldMode();
    });
  }
}
