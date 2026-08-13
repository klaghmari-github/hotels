/**
 * F0137 / F0146 — Dialog notebook multi-cellules (style Jupyter) + editeur .py.
 *
 * - type notebook → .ipynb multi-cellules (add / run / split)
 * - type execute_python → editeur monofichier .py
 * Session Python partagee + inspecteur de variables.
 */
import { state, el } from "./state.js";
import { api, toast } from "./api.js";
import { formToYamlEditor } from "./config/form-sync.js";
import { refreshFieldDisplays } from "./config/pencil.js";
import { flushAutoSave } from "./config/step-crud.js";

let _wired = false;
let _busy = false;
/** @type {"notebook"|"execute_python"} */
let _mode = "notebook";
/** @type {Array<{id:string, source:string, stdout:string, stderr:string, rc:number|null}>} */
let _cells = [];
let _activeCellId = null;

function $(id) {
  return document.getElementById(id);
}

function currentVenv() {
  return el.cfgVenv && el.cfgVenv.value ? el.cfgVenv.value.trim() : "";
}

function currentStepType() {
  if (el.cfgType && el.cfgType.value) return el.cfgType.value;
  const nodes = (state.graph && state.graph.nodes) || [];
  const n = nodes.find(function (x) {
    return x && x.id === state.selected;
  });
  return (n && n.type) || "";
}

function setBusy(on) {
  _busy = !!on;
  ["nb-btn-run", "nb-btn-run-all", "nb-btn-run-save", "nb-btn-add-cell"].forEach(
    function (id) {
      const b = $(id);
      if (b) b.disabled = _busy;
    }
  );
  const dialog = $("notebook-dialog");
  if (dialog) dialog.setAttribute("aria-busy", _busy ? "true" : "false");
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function uid() {
  return "c" + Math.random().toString(36).slice(2, 10);
}

function cellsToScript() {
  if (_mode === "execute_python") {
    const codeEl = $("nb-code");
    return codeEl ? codeEl.value : "";
  }
  return _cells
    .map(function (c) {
      return String(c.source || "").trimEnd();
    })
    .filter(Boolean)
    .join("\n\n") + (_cells.length ? "\n" : "");
}

function cellsToNotebook() {
  return {
    nbformat: 4,
    nbformat_minor: 5,
    metadata: {
      kernelspec: {
        display_name: "Python 3",
        language: "python",
        name: "python3",
      },
      language_info: { name: "python" },
    },
    cells: _cells.map(function (c) {
      const src = String(c.source || "");
      const lines = src.length ? src.split(/(?<=\n)/) : [];
      // ensure array of lines with newlines preserved
      const source =
        lines.length > 0
          ? lines
          : src
            ? [src]
            : [];
      return {
        cell_type: "code",
        execution_count: null,
        metadata: {},
        outputs: [],
        source: source,
      };
    }),
  };
}

function loadCellsFromNotebook(nb) {
  _cells = [];
  const cells = (nb && nb.cells) || [];
  if (!cells.length) {
    _cells.push({
      id: uid(),
      source:
        "# Notebook renatus — session Python partagee\n" +
        'print("notebook ready")\n',
      stdout: "",
      stderr: "",
      rc: null,
    });
  } else {
    cells.forEach(function (cell) {
      if (!cell || cell.cell_type === "markdown") {
        // markdown → code commentee simple
        if (cell && cell.cell_type === "markdown") {
          let src = cell.source;
          if (Array.isArray(src)) src = src.join("");
          _cells.push({
            id: uid(),
            source: "# " + String(src || "").replace(/\n/g, "\n# ") + "\n",
            stdout: "",
            stderr: "",
            rc: null,
          });
        }
        return;
      }
      if (cell.cell_type !== "code") return;
      let src = cell.source;
      if (Array.isArray(src)) src = src.join("");
      _cells.push({
        id: uid(),
        source: String(src || ""),
        stdout: "",
        stderr: "",
        rc: null,
      });
    });
  }
  if (!_cells.length) {
    _cells.push({
      id: uid(),
      source: "",
      stdout: "",
      stderr: "",
      rc: null,
    });
  }
  _activeCellId = _cells[0].id;
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
    li.addEventListener("click", function () {
      insertIntoActive(v.name || "");
    });
    list.appendChild(li);
  });
}

function insertIntoActive(text) {
  if (!text) return;
  if (_mode === "execute_python") {
    const code = $("nb-code");
    if (!code) return;
    const start = code.selectionStart || 0;
    const end = code.selectionEnd || 0;
    const val = code.value || "";
    code.value = val.slice(0, start) + text + val.slice(end);
    const pos = start + text.length;
    code.selectionStart = pos;
    code.selectionEnd = pos;
    code.focus();
    return;
  }
  const ta = document.querySelector(
    '.nb-cell[data-cell-id="' + _activeCellId + '"] textarea'
  );
  if (!ta) return;
  const start = ta.selectionStart || 0;
  const end = ta.selectionEnd || 0;
  const val = ta.value || "";
  ta.value = val.slice(0, start) + text + val.slice(end);
  syncCellFromDom(_activeCellId);
  ta.focus();
}

function syncCellFromDom(cellId) {
  const ta = document.querySelector(
    '.nb-cell[data-cell-id="' + cellId + '"] textarea'
  );
  const cell = _cells.find(function (c) {
    return c.id === cellId;
  });
  if (cell && ta) cell.source = ta.value;
}

function syncAllCellsFromDom() {
  _cells.forEach(function (c) {
    syncCellFromDom(c.id);
  });
}

function renderCells() {
  const host = $("nb-cells");
  const pyWrap = $("nb-py-wrap");
  const cellsWrap = $("nb-cells-wrap");
  if (_mode === "execute_python") {
    if (cellsWrap) cellsWrap.hidden = true;
    if (pyWrap) pyWrap.hidden = false;
    return;
  }
  if (pyWrap) pyWrap.hidden = true;
  if (cellsWrap) cellsWrap.hidden = false;
  if (!host) return;
  host.innerHTML = "";
  _cells.forEach(function (cell, idx) {
    const wrap = document.createElement("div");
    wrap.className =
      "nb-cell" + (cell.id === _activeCellId ? " is-active" : "");
    wrap.setAttribute("data-cell-id", cell.id);
    wrap.setAttribute("data-testid", "nb-cell-" + idx);
    const head = document.createElement("div");
    head.className = "nb-cell-head";
    head.innerHTML =
      '<span class="nb-cell-label">In [' +
      (idx + 1) +
      "]</span>" +
      '<span class="nb-cell-actions">' +
      '<button type="button" class="btn ghost nb-cell-run" data-act="run" title="Run cellule">▶</button>' +
      '<button type="button" class="btn ghost nb-cell-add" data-act="add" title="Ajouter en dessous">+</button>' +
      '<button type="button" class="btn ghost nb-cell-del" data-act="del" title="Supprimer">×</button>' +
      "</span>";
    const ta = document.createElement("textarea");
    ta.className = "nb-code mono nb-cell-code";
    ta.setAttribute("spellcheck", "false");
    ta.rows = Math.min(16, Math.max(4, (cell.source || "").split("\n").length + 1));
    ta.value = cell.source || "";
    if (idx === 0) ta.setAttribute("data-testid", "nb-code");
    ta.addEventListener("focus", function () {
      _activeCellId = cell.id;
      host.querySelectorAll(".nb-cell").forEach(function (el) {
        el.classList.toggle(
          "is-active",
          el.getAttribute("data-cell-id") === cell.id
        );
      });
    });
    ta.addEventListener("input", function () {
      cell.source = ta.value;
    });
    ta.addEventListener("keydown", function (ev) {
      if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") {
        ev.preventDefault();
        runCell(cell.id);
      }
    });
    const out = document.createElement("div");
    out.className = "nb-cell-output";
    if (cell.stdout) {
      const pre = document.createElement("pre");
      pre.className = "nb-stdout";
      pre.textContent = cell.stdout;
      out.appendChild(pre);
    }
    if (cell.stderr) {
      const pre = document.createElement("pre");
      pre.className = "nb-stderr";
      pre.textContent = cell.stderr;
      out.appendChild(pre);
    }
    if (cell.rc != null && cell.rc !== 0) {
      const meta = document.createElement("div");
      meta.className = "nb-run-meta is-error";
      meta.textContent = "exit " + cell.rc;
      out.appendChild(meta);
    }
    wrap.appendChild(head);
    wrap.appendChild(ta);
    wrap.appendChild(out);
    head.addEventListener("click", function (ev) {
      const btn = ev.target.closest("[data-act]");
      if (!btn) return;
      const act = btn.getAttribute("data-act");
      if (act === "run") runCell(cell.id);
      if (act === "add") addCellAfter(cell.id);
      if (act === "del") deleteCell(cell.id);
    });
    host.appendChild(wrap);
  });
}

function addCellAfter(cellId) {
  syncAllCellsFromDom();
  const idx = _cells.findIndex(function (c) {
    return c.id === cellId;
  });
  const neu = {
    id: uid(),
    source: "",
    stdout: "",
    stderr: "",
    rc: null,
  };
  if (idx < 0) _cells.push(neu);
  else _cells.splice(idx + 1, 0, neu);
  _activeCellId = neu.id;
  renderCells();
}

function deleteCell(cellId) {
  if (_cells.length <= 1) {
    toast("Au moins une cellule requise", "error");
    return;
  }
  syncAllCellsFromDom();
  _cells = _cells.filter(function (c) {
    return c.id !== cellId;
  });
  _activeCellId = _cells[0].id;
  renderCells();
}

function showGlobalOutput(stdout, stderr, rc) {
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

async function execCode(code) {
  const body = {
    code: code,
    step_id: state.selected || null,
    venv: currentVenv() || null,
    timeout: 120,
  };
  return api("/gui/python/session/exec", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function runCell(cellId) {
  syncAllCellsFromDom();
  const cell = _cells.find(function (c) {
    return c.id === cellId;
  });
  if (!cell) return null;
  const code = String(cell.source || "");
  if (!code.trim()) {
    toast("Cellule vide", "error");
    return null;
  }
  setBusy(true);
  try {
    const res = await execCode(code);
    cell.stdout = res.stdout || "";
    cell.stderr = res.stderr || "";
    cell.rc = res.returncode;
    renderVars(res.vars || []);
    renderCells();
    if (res.returncode === 0) toast("Cellule exécutée", "success");
    else toast("Erreur (exit " + res.returncode + ")", "error");
    return res;
  } catch (e) {
    cell.stderr = String(e.message || e);
    cell.rc = 1;
    renderCells();
    toast("Run: " + e.message, "error");
    return null;
  } finally {
    setBusy(false);
  }
}

export async function runNotebookCode(opts) {
  const o = opts || {};
  if (_mode === "execute_python") {
    const codeEl = $("nb-code");
    const code = codeEl ? codeEl.value : "";
    if (!String(code).trim()) {
      toast("Script vide", "error");
      return null;
    }
    setBusy(true);
    showGlobalOutput("…", "", null);
    try {
      const res = await execCode(code);
      showGlobalOutput(res.stdout || "", res.stderr || "", res.returncode);
      renderVars(res.vars || []);
      if (res.returncode === 0) toast("Exécuté (session)", "success");
      else toast("Erreur (exit " + res.returncode + ")", "error");
      if (o.applyToForm || o.save) {
        applyToForm();
        if (o.save) await flushAutoSave();
      }
      return res;
    } catch (e) {
      showGlobalOutput("", String(e.message || e), 1);
      toast("Run: " + e.message, "error");
      return null;
    } finally {
      setBusy(false);
    }
  }
  // notebook: run all cells sequentially
  syncAllCellsFromDom();
  setBusy(true);
  try {
    for (let i = 0; i < _cells.length; i++) {
      const cell = _cells[i];
      const code = String(cell.source || "").trim();
      if (!code) continue;
      const res = await execCode(cell.source);
      cell.stdout = res.stdout || "";
      cell.stderr = res.stderr || "";
      cell.rc = res.returncode;
      renderVars(res.vars || []);
      if (res.returncode !== 0) {
        renderCells();
        toast("Erreur cellule " + (i + 1), "error");
        if (o.applyToForm || o.save) {
          applyToForm();
          if (o.save) await flushAutoSave();
        }
        return res;
      }
    }
    renderCells();
    toast("Notebook exécuté (session)", "success");
    if (o.applyToForm || o.save) {
      applyToForm();
      if (o.save) await flushAutoSave();
    }
    return { returncode: 0 };
  } catch (e) {
    toast("Run: " + e.message, "error");
    return null;
  } finally {
    setBusy(false);
  }
}

function applyToForm() {
  syncAllCellsFromDom();
  const script = cellsToScript();
  if (el.cfgScript) el.cfgScript.value = script;
  // stash notebook structure for put_step
  if (_mode === "notebook") {
    state._pendingNotebook = cellsToNotebook();
  } else {
    state._pendingNotebook = null;
  }
  refreshFieldDisplays();
  formToYamlEditor();
}

/**
 * Ouvre le dialog.
 * @param {{ script?: string, notebook?: object, mode?: string }} [opts]
 */
export function openNotebookDialog(opts) {
  const dialog = $("notebook-dialog");
  const title = $("notebook-title");
  if (!dialog) {
    toast("Dialog notebook indisponible", "error");
    return;
  }
  const o = opts || {};
  const stype = o.mode || currentStepType() || "notebook";
  _mode = stype === "execute_python" ? "execute_python" : "notebook";

  const script =
    o.script != null
      ? String(o.script)
      : el.cfgScript
        ? el.cfgScript.value
        : "";

  if (_mode === "execute_python") {
    const codeEl = $("nb-code");
    if (codeEl) codeEl.value = script;
    showGlobalOutput("", "", null);
  } else {
    if (o.notebook && typeof o.notebook === "object") {
      loadCellsFromNotebook(o.notebook);
    } else {
      loadCellsFromNotebook({
        cells: [
          {
            cell_type: "code",
            source: script || 'print("notebook ready")\n',
          },
        ],
      });
    }
    renderCells();
  }

  // toolbar labels
  const addBtn = $("nb-btn-add-cell");
  const runAll = $("nb-btn-run-all");
  if (addBtn) addBtn.hidden = _mode !== "notebook";
  if (runAll) runAll.hidden = _mode !== "notebook";

  if (title) {
    title.textContent =
      (_mode === "notebook" ? "Notebook · " : "Python · ") +
      (state.selected || "session") +
      " · " +
      (_mode === "notebook" ? ".ipynb" : ".py");
  }
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
  // mode py/nb layout
  renderCells();
  setTimeout(function () {
    try {
      if (_mode === "execute_python") {
        const codeEl = $("nb-code");
        if (codeEl) codeEl.focus();
      } else {
        const ta = document.querySelector(".nb-cell.is-active textarea");
        if (ta) ta.focus();
      }
    } catch (_) {}
  }, 40);
}

export function closeNotebookDialog(apply) {
  const dialog = $("notebook-dialog");
  if (apply) {
    applyToForm();
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
  const runAll = $("nb-btn-run-all");
  const runSave = $("nb-btn-run-save");
  const refresh = $("nb-btn-refresh-vars");
  const apply = $("nb-btn-apply");
  const cancel = $("nb-btn-cancel");
  const addCell = $("nb-btn-add-cell");
  const codeEl = $("nb-code");

  if (run) {
    run.addEventListener("click", function () {
      if (_mode === "notebook" && _activeCellId) {
        runCell(_activeCellId);
      } else {
        runNotebookCode({ applyToForm: false, save: false });
      }
    });
  }
  if (runAll) {
    runAll.addEventListener("click", function () {
      runNotebookCode({ applyToForm: false, save: false });
    });
  }
  if (runSave) {
    runSave.addEventListener("click", function () {
      runNotebookCode({ applyToForm: true, save: true });
    });
  }
  if (addCell) {
    addCell.addEventListener("click", function () {
      addCellAfter(_activeCellId || (_cells[0] && _cells[0].id));
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
      toast(
        _mode === "notebook" ? "Notebook enregistré" : "Script enregistré",
        "success"
      );
    });
  }
  if (cancel) {
    cancel.addEventListener("click", function () {
      closeNotebookDialog(false);
    });
  }
  if (codeEl) {
    codeEl.addEventListener("keydown", function (ev) {
      if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") {
        ev.preventDefault();
        runNotebookCode({ applyToForm: false, save: false });
      }
    });
  }
}
