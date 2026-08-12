/**
 * F0137 — Dialog notebook style Jupyter Lab.
 * Edition du script + Run dans la session Python + inspecteur de variables.
 */
import { state, el } from "./state.js";
import { api, toast } from "./api.js";
import { formToYamlEditor } from "./config/form-sync.js";
import { refreshFieldDisplays } from "./config/pencil.js";
import { flushAutoSave } from "./config/step-crud.js";

let _wired = false;
let _busy = false;

function $(id) {
  return document.getElementById(id);
}

function currentVenv() {
  return el.cfgVenv && el.cfgVenv.value ? el.cfgVenv.value.trim() : "";
}

function setBusy(on) {
  _busy = !!on;
  const run = $("nb-btn-run");
  const runSave = $("nb-btn-run-save");
  if (run) run.disabled = _busy;
  if (runSave) runSave.disabled = _busy;
  const dialog = $("notebook-dialog");
  if (dialog) dialog.setAttribute("aria-busy", _busy ? "true" : "false");
}

function renderVars(vars) {
  const list = $("nb-vars-list");
  const empty = $("nb-vars-empty");
  const count = $("nb-vars-count");
  if (!list) return;
  const items = Array.isArray(vars) ? vars : [];
  if (count) count.textContent = String(items.length);
  list.innerHTML = "";
  if (!items.length) {
    if (empty) empty.hidden = false;
    return;
  }
  if (empty) empty.hidden = true;
  items.forEach(function (v) {
    const li = document.createElement("li");
    li.className = "nb-var-item";
    li.setAttribute("data-testid", "nb-var-" + (v.name || ""));
    li.title = (v.type_full || v.type || "") + " — " + (v.preview || "");
    li.innerHTML =
      '<span class="nb-var-name">' +
      escapeHtml(v.name || "?") +
      '</span><span class="nb-var-type">' +
      escapeHtml(v.type || "") +
      '</span><span class="nb-var-preview">' +
      escapeHtml(v.preview || "") +
      "</span>";
    // clic = inserer le nom dans l editeur
    li.addEventListener("click", function () {
      const code = $("nb-code");
      if (!code || !v.name) return;
      insertAtCursor(code, v.name);
      code.focus();
    });
    list.appendChild(li);
  });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function insertAtCursor(textarea, text) {
  const start = textarea.selectionStart || 0;
  const end = textarea.selectionEnd || 0;
  const val = textarea.value || "";
  textarea.value = val.slice(0, start) + text + val.slice(end);
  const pos = start + text.length;
  textarea.selectionStart = pos;
  textarea.selectionEnd = pos;
}

function showOutput(stdout, stderr, rc) {
  const out = $("nb-stdout");
  const err = $("nb-stderr");
  const meta = $("nb-run-meta");
  if (out) out.textContent = stdout || "";
  if (err) {
    err.textContent = stderr || "";
    err.hidden = !stderr;
  }
  if (meta) {
    meta.textContent =
      rc == null
        ? ""
        : "exit " + rc + (rc === 0 ? " · ok" : " · erreur");
    meta.classList.toggle("is-error", rc != null && rc !== 0);
  }
}

export async function refreshNotebookVars() {
  const stepId = state.selected || null;
  const venv = currentVenv();
  try {
    let q = "/gui/python/session/vars";
    const params = [];
    if (stepId) params.push("step_id=" + encodeURIComponent(stepId));
    if (venv) params.push("venv=" + encodeURIComponent(venv));
    if (params.length) q += "?" + params.join("&");
    const data = await api(q);
    renderVars(data.vars || []);
    return data;
  } catch (e) {
    renderVars([]);
    toast("Variables session: " + e.message, "error");
    return null;
  }
}

export async function runNotebookCode(opts) {
  const o = opts || {};
  const codeEl = $("nb-code");
  const code = codeEl ? codeEl.value : "";
  if (!String(code).trim()) {
    toast("Cellule vide", "error");
    return null;
  }
  setBusy(true);
  showOutput("…", "", null);
  try {
    const body = {
      code: code,
      step_id: state.selected || null,
      venv: currentVenv() || null,
      timeout: 120,
    };
    const res = await api("/gui/python/session/exec", {
      method: "POST",
      body: JSON.stringify(body),
    });
    showOutput(res.stdout || "", res.stderr || "", res.returncode);
    renderVars(res.vars || []);
    if (res.returncode === 0) {
      toast("Cellule exécutée (session)", "success");
    } else {
      toast("Erreur d’exécution (exit " + res.returncode + ")", "error");
    }
    if (o.applyToForm && el.cfgScript) {
      el.cfgScript.value = code;
      refreshFieldDisplays();
      formToYamlEditor();
    }
    if (o.save) {
      if (el.cfgScript) el.cfgScript.value = code;
      refreshFieldDisplays();
      formToYamlEditor();
      await flushAutoSave();
    }
    return res;
  } catch (e) {
    showOutput("", String(e.message || e), 1);
    toast("Run: " + e.message, "error");
    return null;
  } finally {
    setBusy(false);
  }
}

/**
 * Ouvre le dialog notebook pour le step selectionne.
 * @param {{ script?: string }} [opts]
 */
export function openNotebookDialog(opts) {
  const dialog = $("notebook-dialog");
  const codeEl = $("nb-code");
  const title = $("notebook-title");
  if (!dialog || !codeEl) {
    toast("Dialog notebook indisponible", "error");
    return;
  }
  const o = opts || {};
  const script =
    o.script != null
      ? String(o.script)
      : el.cfgScript
        ? el.cfgScript.value
        : "";
  codeEl.value = script;
  if (title) {
    title.textContent =
      "Notebook · " + (state.selected || "session") + " · Python session";
  }
  showOutput("", "", null);
  try {
    if (typeof dialog.showModal === "function") {
      if (dialog.open) dialog.close();
      dialog.showModal();
    }
  } catch (e) {
    toast("Notebook: " + e.message, "error");
    return;
  }
  refreshNotebookVars();
  setTimeout(function () {
    try {
      codeEl.focus();
    } catch (_) {}
  }, 40);
}

export function closeNotebookDialog(apply) {
  const dialog = $("notebook-dialog");
  const codeEl = $("nb-code");
  if (apply && codeEl && el.cfgScript) {
    el.cfgScript.value = codeEl.value;
    refreshFieldDisplays();
    formToYamlEditor();
    flushAutoSave();
  }
  if (dialog && dialog.open) {
    try {
      dialog.close();
    } catch (_) {}
  }
}

export function wireNotebookDialog() {
  if (_wired) return;
  _wired = true;
  const run = $("nb-btn-run");
  const runSave = $("nb-btn-run-save");
  const refresh = $("nb-btn-refresh-vars");
  const apply = $("nb-btn-apply");
  const cancel = $("nb-btn-cancel");
  const codeEl = $("nb-code");

  if (run) {
    run.addEventListener("click", function () {
      runNotebookCode({ applyToForm: false, save: false });
    });
  }
  if (runSave) {
    runSave.addEventListener("click", function () {
      runNotebookCode({ applyToForm: true, save: true });
    });
  }
  if (refresh) {
    refresh.addEventListener("click", function () {
      refreshNotebookVars();
    });
  }
  if (apply) {
    apply.addEventListener("click", function () {
      closeNotebookDialog(true);
      toast("Script mis à jour", "success");
    });
  }
  if (cancel) {
    cancel.addEventListener("click", function () {
      closeNotebookDialog(false);
    });
  }
  // Ctrl+Enter = run
  if (codeEl) {
    codeEl.addEventListener("keydown", function (ev) {
      if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") {
        ev.preventDefault();
        runNotebookCode({ applyToForm: false, save: false });
      }
    });
  }
}
