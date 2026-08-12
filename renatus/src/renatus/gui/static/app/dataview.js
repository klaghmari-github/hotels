/**
 * DataView / View — apercu tabular + process.
 *
 * Datasets (dataframe/table/view) : pagination serveur (limit+page),
 * pageSize 3..100 (F0123/F0124). Jamais de dump table entiere.
 * execute_python / shell : sous-onglets Output / Error (F0073).
 */
import { state, el } from "./state.js";
import { api } from "./api.js";
import { UiController } from "./ui-base.js";
import { escapeHtml } from "./util.js";

/** F0123: taille de page par defaut (3 premieres lignes). */
export const DATAVIEW_DEFAULT_PAGE_SIZE = 3;
/** F0124: plafond aligne sur GET /gui/preview limit le=100 */
export const DATAVIEW_MAX_PAGE_SIZE = 100;
/** Tailles proposees dans le select View */
export const DATAVIEW_PAGE_SIZE_OPTIONS = [3, 10, 25, 50, 100];

/**
 * F0124: normalise un pageSize (entier 1..100, defaut 3).
 */
export function clampDataViewPageSize(raw) {
  const n = Math.floor(Number(raw));
  if (!isFinite(n) || n < 1) return DATAVIEW_DEFAULT_PAGE_SIZE;
  return Math.min(DATAVIEW_MAX_PAGE_SIZE, n);
}

/** Sync le <select> lignes/page avec l etat. */
export function syncDataViewPageSizeSelect(pageSize) {
  const sel = el.dataviewPageSizeSelect;
  if (!sel) return;
  const v = String(clampDataViewPageSize(pageSize));
  // si valeur non dans la liste (ex. futur), on la selectionne quand meme
  let found = false;
  for (let i = 0; i < sel.options.length; i++) {
    if (sel.options[i].value === v) {
      found = true;
      break;
    }
  }
  if (!found) {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    sel.appendChild(opt);
  }
  sel.value = v;
}

/**
 * Controleur DataView (F0054-S2).
 */
export class DataViewPanel extends UiController {
  constructor(root) {
    super(root || (el && el.panelDataPreview) || null);
  }

  show(data) {
    return showTable(data);
  }

  clear() {
    return clearTable();
  }

  load(name, build, options) {
    return loadDataView(name, build, options);
  }

  setTitle(name, asPrereq) {
    return setDataViewTitle(name, asPrereq);
  }

  render() {
    return this;
  }
}

/** Instance module partagee. */
export const dataViewPanel = new DataViewPanel();

function isProcessPayload(data) {
  if (!data) return false;
  if (
    data.action === "execute_python" ||
    data.action === "execute_shell"
  ) {
    return true;
  }
  if (data.stdout != null || data.stderr != null) return true;
  const cols = data.columns || [];
  return (
    cols.length === 2 &&
    String(cols[0]).toLowerCase() === "stream" &&
    String(cols[1]).toLowerCase() === "content"
  );
}

function extractProcessStreams(data) {
  let stdout =
    data.stdout != null ? String(data.stdout) : "";
  let stderr =
    data.stderr != null ? String(data.stderr) : "";
  // fallback rows stream|content
  if (!stdout && !stderr && Array.isArray(data.rows)) {
    data.rows.forEach(function (r) {
      if (!r || r.length < 2) return;
      const k = String(r[0] || "").toLowerCase();
      const v = r[1] === null || r[1] === undefined ? "" : String(r[1]);
      if (k === "stdout") stdout = v === "(vide)" ? "" : v;
      if (k === "stderr") stderr = v === "(vide)" ? "" : v;
    });
  }
  return { stdout: stdout, stderr: stderr };
}

/**
 * F0073: bascule Output / Error pour sorties python.
 * @param {"output"|"error"} tabId
 */
export function switchProcessSubTab(tabId) {
  const id = tabId === "error" ? "error" : "output";
  state.processSubTab = id;
  const isErr = id === "error";
  if (el.tabProcessOutput) {
    el.tabProcessOutput.classList.toggle("active", !isErr);
    el.tabProcessOutput.setAttribute(
      "aria-selected",
      !isErr ? "true" : "false"
    );
  }
  if (el.tabProcessError) {
    el.tabProcessError.classList.toggle("active", isErr);
    el.tabProcessError.setAttribute(
      "aria-selected",
      isErr ? "true" : "false"
    );
  }
  if (el.processOutStdout) el.processOutStdout.hidden = isErr;
  if (el.processOutStderr) el.processOutStderr.hidden = !isErr;
}

function setProcessMode(on) {
  if (el.processView) el.processView.hidden = !on;
  if (el.tableWrap) el.tableWrap.hidden = !!on;
  if (el.resultTable) {
    el.resultTable.classList.toggle("process-output", !!on);
  }
}

function showProcessOutput(data) {
  setProcessMode(true);
  const streams = extractProcessStreams(data);
  const stdoutText = streams.stdout || "(vide)";
  const stderrText = streams.stderr || "(vide)";
  if (el.processOutStdout) {
    el.processOutStdout.textContent = stdoutText;
  }
  if (el.processOutStderr) {
    el.processOutStderr.textContent = stderrText;
  }
  // clear table (unused in process mode)
  if (el.resultHead) el.resultHead.innerHTML = "";
  if (el.resultBody) el.resultBody.innerHTML = "";
  // default Output; auto-open Error if only stderr has content
  const preferError =
    !streams.stdout.trim() && !!streams.stderr.trim();
  switchProcessSubTab(preferError ? "error" : "output");
  // badge error tab if stderr non vide
  if (el.tabProcessError) {
    el.tabProcessError.classList.toggle(
      "has-content",
      !!streams.stderr.trim()
    );
  }
  if (el.tabProcessOutput) {
    el.tabProcessOutput.classList.toggle(
      "has-content",
      !!streams.stdout.trim()
    );
  }
}

/**
 * F0123: met a jour barre de pagination + etat.
 * Cachee pour process (python/shell) ou dataset vide non materialise.
 */
export function updateDataViewPager(data, opts) {
  const o = opts || {};
  const pager = el.dataviewPager;
  if (!pager) return;
  if (o.hide || !data || isProcessPayload(data) || data.exists === false) {
    pager.hidden = true;
    if (el.btnDvPagePrev) el.btnDvPagePrev.disabled = true;
    if (el.btnDvPageNext) el.btnDvPageNext.disabled = true;
    if (el.dataviewPagerLabel) el.dataviewPagerLabel.textContent = "—";
    return;
  }
  const pageSize =
    Number(data.page_size || data.limit || state.dataviewPageSize) ||
    DATAVIEW_DEFAULT_PAGE_SIZE;
  const offset = Number(data.offset || 0) || 0;
  const rows = data.rows || [];
  const page =
    Number(data.page) ||
    Math.floor(offset / pageSize) + 1 ||
    1;
  const totalRows =
    data.total_rows != null ? Number(data.total_rows) : null;
  const totalPages =
    data.total_pages != null
      ? Number(data.total_pages)
      : totalRows != null && pageSize
        ? Math.max(1, Math.ceil(totalRows / pageSize))
        : null;
  const hasPrev =
    data.has_prev != null ? !!data.has_prev : offset > 0;
  const hasNext =
    data.has_next != null
      ? !!data.has_next
      : !!data.truncated ||
        (totalPages != null && page < totalPages);

  state.dataviewPage = page;
  state.dataviewPageSize = pageSize;
  state.dataviewTotalRows = totalRows;
  state.dataviewTotalPages = totalPages;
  state.dataviewHasPrev = hasPrev;
  state.dataviewHasNext = hasNext;
  syncDataViewPageSizeSelect(pageSize);

  // afficher le pager des qu on a une table (meme 1 page)
  pager.hidden = false;
  if (el.btnDvPagePrev) el.btnDvPagePrev.disabled = !hasPrev;
  if (el.btnDvPageNext) el.btnDvPageNext.disabled = !hasNext;
  if (el.dataviewPageSizeSelect) el.dataviewPageSizeSelect.disabled = false;

  const from = rows.length ? offset + 1 : 0;
  const to = offset + rows.length;
  let label;
  if (totalRows != null) {
    label =
      from +
      "–" +
      to +
      " / " +
      totalRows +
      " · p." +
      page +
      (totalPages != null ? "/" + totalPages : "");
  } else {
    label =
      from +
      "–" +
      to +
      " · p." +
      page +
      (hasNext ? "+" : "");
  }
  if (el.dataviewPagerLabel) el.dataviewPagerLabel.textContent = label;
}

export function showTable(data) {
  if (isProcessPayload(data)) {
    showProcessOutput(data);
    updateDataViewPager(data, { hide: true });
    return;
  }
  setProcessMode(false);
  const cols = data.columns || [];
  const rows = data.rows || [];
  // F0123: ne jamais afficher plus que page_size (garde-fou client)
  const pageSize =
    Number(data.page_size || data.limit || state.dataviewPageSize) ||
    DATAVIEW_DEFAULT_PAGE_SIZE;
  const displayRows = rows.slice(0, pageSize);
  el.resultHead.innerHTML =
    "<tr>" +
    cols.map(function (c) {
      return "<th>" + escapeHtml(c) + "</th>";
    }).join("") +
    "</tr>";
  el.resultBody.innerHTML = displayRows
    .map(function (r) {
      return (
        "<tr>" +
        r
          .map(function (cell) {
            const text =
              cell === null || cell === undefined ? "NULL" : String(cell);
            return "<td>" + escapeHtml(text) + "</td>";
          })
          .join("") +
        "</tr>"
      );
    })
    .join("");
  updateDataViewPager(
    Object.assign({}, data, { rows: displayRows })
  );
}

export function clearTable() {
  el.resultHead.innerHTML = "";
  el.resultBody.innerHTML = "";
  el.dvName.textContent = "";
  el.dvMeta.textContent = "";
  el.btnDvBuild.disabled = true;
  if (el.btnDvReload) el.btnDvReload.disabled = true;
  state.dataviewSource = null;
  state.dataviewIsPrereq = false;
  state.dataviewPage = 1;
  state.dataviewTotalRows = null;
  state.dataviewTotalPages = null;
  state.dataviewHasNext = false;
  state.dataviewHasPrev = false;
  if (el.processOutStdout) el.processOutStdout.textContent = "";
  if (el.processOutStderr) el.processOutStderr.textContent = "";
  setProcessMode(false);
  switchProcessSubTab("output");
  updateDataViewPager(null, { hide: true });
}

export function setDataViewTitle(name, asPrereq) {
  if (!el.dvName) return;
  if (asPrereq) {
    el.dvName.innerHTML =
      escapeHtml(name) +
      ' <span class="dataview-source prereq" data-testid="dataview-prereq-badge">(prerequis)</span>';
  } else {
    el.dvName.textContent = name || "";
  }
}

/**
 * A0014: apres Renatus / materialisation, maj schema / shape / renatus_time
 * dans Config (sans recharger tout le formulaire).
 * @param {string} stepId
 * @param {object} [previewRes] reponse preview/build (optionnel)
 */
export async function refreshCalculatedConfigFields(stepId, previewRes) {
  if (!stepId || stepId !== state.selected) return;
  try {
    const data = await api("/gui/step/" + encodeURIComponent(stepId));
    const stepType = (data.config && data.config.type) || "";
    const {
      renderRenatusTime,
      renderShape,
      renderSchema,
    } = await import("./config/requires.js");
    // preferer renatus_time de la reponse build si present
    let rt = data.renatus_time;
    if (
      previewRes &&
      previewRes.renatus_time != null &&
      isFinite(Number(previewRes.renatus_time))
    ) {
      rt = previewRes.renatus_time;
    }
    renderRenatusTime(rt);
    renderShape(data.shape, stepType);
    renderSchema(data.schema || [], stepType);
  } catch (_) {
    /* ignore: config peut etre deconnectee */
  }
}

/**
 * Charge la DataView pour `name` (page courante).
 * options.asPrereq: true si on affiche une source requires (F0019).
 * options.page: page 1-based (F0123).
 * options.pageSize: defaut 3.
 * options.resetPage: true → repart a la page 1.
 */
export async function loadDataView(name, build, options) {
  const opts = options || {};
  const asPrereq = !!opts.asPrereq;
  // F0124: pageSize depuis opts, select UI, ou etat (jamais de dump complet)
  let rawSize =
    opts.pageSize != null
      ? opts.pageSize
      : el.dataviewPageSizeSelect && el.dataviewPageSizeSelect.value
        ? el.dataviewPageSizeSelect.value
        : state.dataviewPageSize || DATAVIEW_DEFAULT_PAGE_SIZE;
  const pageSize = clampDataViewPageSize(rawSize);
  if (opts.resetPage || name !== state.dataviewSource) {
    state.dataviewPage = 1;
  }
  if (opts.page != null) {
    state.dataviewPage = Math.max(1, Number(opts.page) || 1);
  }
  state.dataviewPageSize = pageSize;
  syncDataViewPageSizeSelect(pageSize);
  state.dataviewSource = name;
  state.dataviewIsPrereq = asPrereq;
  setDataViewTitle(name, asPrereq);
  const page = state.dataviewPage || 1;
  try {
    // Une seule page: limit=pageSize & page=N (offset serveur)
    let q =
      "?limit=" +
      encodeURIComponent(String(pageSize)) +
      "&page=" +
      encodeURIComponent(String(page));
    if (build) q += "&build=true";
    const res = await api(
      "/gui/preview/" + encodeURIComponent(name) + q
    );
    if (res.exists === false && !res.built) {
      clearTableSoft();
      setDataViewTitle(name, asPrereq);
      el.dvMeta.textContent = res.message || "—";
      el.btnDvBuild.disabled = false;
      if (el.btnDvReload) el.btnDvReload.disabled = true;
      updateDataViewPager(res, { hide: true });
      return;
    }
    showTable(res);
    if (isProcessPayload(res)) {
      const rc = res.returncode;
      const py = res.python || "";
      el.dvMeta.textContent =
        (rc != null ? "exit " + rc : "process") +
        (py ? " · " + py : "");
    } else {
      el.dvMeta.textContent =
        res.message ||
        (res.total_rows != null
          ? res.total_rows + " ligne(s) total"
          : res.row_count != null
            ? res.row_count + " ligne(s)"
            : "");
    }
    el.btnDvBuild.disabled = true;
    if (el.btnDvReload) el.btnDvReload.disabled = false;
    // A0014: Renatus View → rafraichir champs calculees Config
    if (build || res.built || res.renatus_time != null) {
      await refreshCalculatedConfigFields(name, res);
    }
  } catch (e) {
    el.dvMeta.textContent = e.message;
    el.btnDvBuild.disabled = false;
    if (el.btnDvReload) el.btnDvReload.disabled = true;
    clearTableSoft();
    setDataViewTitle(name, asPrereq);
    updateDataViewPager(null, { hide: true });
  }
}

/** F0123: page suivante / precedente (recharge uniquement cette page). */
export async function loadDataViewPage(delta) {
  const name = state.dataviewSource;
  if (!name) return;
  const cur = state.dataviewPage || 1;
  const next = Math.max(1, cur + (delta || 0));
  if (delta > 0 && !state.dataviewHasNext) return;
  if (delta < 0 && !state.dataviewHasPrev) return;
  await loadDataView(name, false, {
    asPrereq: state.dataviewIsPrereq,
    page: next,
    pageSize: state.dataviewPageSize,
  });
}

/**
 * F0124: change le nombre de lignes/page → recharge page 1 seulement.
 * N envoie jamais le dataset entier: limit=pageSize sur /gui/preview.
 */
export async function setDataViewPageSize(size) {
  const pageSize = clampDataViewPageSize(size);
  state.dataviewPageSize = pageSize;
  syncDataViewPageSizeSelect(pageSize);
  const name = state.dataviewSource;
  if (!name) return;
  await loadDataView(name, false, {
    asPrereq: state.dataviewIsPrereq,
    pageSize: pageSize,
    resetPage: true,
    page: 1,
  });
}

export function clearTableSoft() {
  el.resultHead.innerHTML = "";
  el.resultBody.innerHTML = "";
  if (el.processOutStdout) el.processOutStdout.textContent = "";
  if (el.processOutStderr) el.processOutStderr.textContent = "";
  setProcessMode(false);
  updateDataViewPager(null, { hide: true });
}

/** F0123/F0124: branche boutons pager + select pageSize (idempotent). */
let _dvPagerWired = false;
export function wireDataViewPager() {
  if (_dvPagerWired) return;
  _dvPagerWired = true;
  if (el.btnDvPagePrev) {
    el.btnDvPagePrev.addEventListener("click", function (ev) {
      ev.preventDefault();
      loadDataViewPage(-1);
    });
  }
  if (el.btnDvPageNext) {
    el.btnDvPageNext.addEventListener("click", function (ev) {
      ev.preventDefault();
      loadDataViewPage(1);
    });
  }
  if (el.dataviewPageSizeSelect) {
    syncDataViewPageSizeSelect(
      state.dataviewPageSize || DATAVIEW_DEFAULT_PAGE_SIZE
    );
    el.dataviewPageSizeSelect.addEventListener("change", function () {
      const v = el.dataviewPageSizeSelect.value;
      setDataViewPageSize(v);
    });
  }
}
