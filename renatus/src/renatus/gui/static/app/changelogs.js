/**
 * Changelogs / Track (F0035 / F0053-S2 / F0054-S2 / F0115).
 * F0115: timeline filtree par composant selectionne (zone = recursif).
 * ChangelogPanel : facade OO autour timeline / apply / bottom tabs.
 */
import { state, el } from "./state.js";
import { api, toast } from "./api.js";
import { selectStep } from "./config.js";
import { confirmDialog } from "./confirm-dialog.js";
import { refreshGraph } from "./graph.js";
import { refreshTabs } from "./tabs.js";
import { UiController } from "./ui-base.js";
import { escapeHtml } from "./util.js";

/**
 * Controleur panneau changelogs (F0054-S2).
 */
export class ChangelogPanel extends UiController {
  constructor(root) {
    super(root || (el && el.panelChangelogs) || null);
  }

  switchBottomTab(tabId) {
    return switchBottomTab(tabId);
  }

  open() {
    return openGlobalChangelogs();
  }

  load() {
    return loadGlobalChangelog();
  }

  selectCommit(commit) {
    return selectChangelogCommit(commit);
  }

  selectFile(path) {
    return selectChangelogFile(path);
  }

  apply(mode) {
    return applyChangelog(mode);
  }

  reset() {
    return resetChangelogUi();
  }

  render() {
    if (state.bottomTab === "changelogs") {
      renderChangelogTimeline(state.changelogEntries || []);
    }
    return this;
  }
}

/** Instance module partagee. */
export const changelogPanel = new ChangelogPanel();

/* ---------- Changelogs globaux (F0035) ---------- */

/**
 * Onglets bas F0071:
 * - view (data-preview): Renatus — pas d Apply
 * - track (changelogs): Apply file / Apply all — pas de Renatus
 *
 * Aliases acceptes: "view" | "data-preview" | "track" | "changelogs"
 */
export function switchBottomTab(tabId) {
  const raw = String(tabId || "").toLowerCase();
  const isTrack =
    raw === "changelogs" || raw === "track" || raw === "changelog";
  const id = isTrack ? "changelogs" : "data-preview";
  state.bottomTab = id;
  if (el.tabDataPreview) {
    el.tabDataPreview.classList.toggle("active", !isTrack);
    el.tabDataPreview.setAttribute(
      "aria-selected",
      !isTrack ? "true" : "false"
    );
  }
  if (el.tabChangelogs) {
    el.tabChangelogs.classList.toggle("active", isTrack);
    el.tabChangelogs.setAttribute(
      "aria-selected",
      isTrack ? "true" : "false"
    );
  }
  if (el.panelDataPreview) el.panelDataPreview.hidden = isTrack;
  if (el.panelChangelogs) el.panelChangelogs.hidden = !isTrack;
  // Actions exclusives: View vs Track (F0071)
  if (el.dataviewActions) el.dataviewActions.hidden = isTrack;
  if (el.changelogActions) el.changelogActions.hidden = !isTrack;
  if (el.btnGlobalChangelogs) {
    el.btnGlobalChangelogs.classList.toggle("active", isTrack);
  }
  if (isTrack) {
    loadStepChangelog(state.selected || null);
  }
}

export function openGlobalChangelogs() {
  switchBottomTab("changelogs");
}

/** Recharge Track si l onglet est actif (apres selection composant). */
export function refreshTrackIfActive() {
  if (state.bottomTab === "changelogs") {
    loadStepChangelog(state.selected || null);
  }
}

export function setChangelogApplyEnabled(enabled) {
  const ro = !!(state.workspace && state.workspace.read_only);
  const on = !!enabled && !ro;
  if (el.btnChangelogApplyFile) el.btnChangelogApplyFile.disabled = !on;
  if (el.btnChangelogApplyAll) el.btnChangelogApplyAll.disabled = !on;
}

export function resetChangelogUi() {
  state.changelogEntries = [];
  state.changelogCommit = null;
  state.changelogPath = null;
  state.changelogFiles = [];
  if (el.changelogList) el.changelogList.innerHTML = "";
  if (el.changelogFiles) el.changelogFiles.innerHTML = "";
  if (el.changelogEmpty) {
    el.changelogEmpty.hidden = true;
    el.changelogEmpty.textContent = "—";
  }
  if (el.changelogDiff) el.changelogDiff.innerHTML = "";
  if (el.changelogDiffMeta) el.changelogDiffMeta.textContent = "";
  setChangelogApplyEnabled(false);
}

export function formatChangelogDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso).slice(0, 16);
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch (_) {
    return String(iso).slice(0, 16);
  }
}

export function basenamePath(p) {
  if (!p) return "";
  const parts = String(p).split("/");
  return parts[parts.length - 1] || p;
}

export function renderChangelogTimeline(entries) {
  if (!el.changelogList) return;
  el.changelogList.innerHTML = "";
  if (!entries || !entries.length) {
    if (el.changelogEmpty) {
      el.changelogEmpty.hidden = false;
      el.changelogEmpty.textContent =
        "—";
    }
    return;
  }
  if (el.changelogEmpty) el.changelogEmpty.hidden = true;
  entries.forEach(function (entry, idx) {
    const li = document.createElement("li");
    li.className =
      "changelog-item" +
      (idx === 0 ? " latest" : "") +
      (state.changelogCommit === entry.commit ? " active" : "");
    li.setAttribute("data-commit", entry.commit);
    li.setAttribute("data-testid", "changelog-item-" + entry.short);
    const nFiles =
      entry.file_count != null
        ? entry.file_count
        : (entry.files && entry.files.length) || 0;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "changelog-dot-btn";
    btn.setAttribute("data-testid", "changelog-select-" + entry.short);
    btn.innerHTML =
      '<span class="cl-subject">' +
      escapeHtml(entry.subject || entry.short) +
      '</span><span class="cl-meta"><span class="cl-short">' +
      escapeHtml(entry.short || entry.commit.slice(0, 8)) +
      '</span><span class="cl-date">' +
      escapeHtml(formatChangelogDate(entry.date)) +
      '</span><span class="cl-files-count">' +
      nFiles +
      " f.</span></span>";
    btn.addEventListener("click", function () {
      selectChangelogCommit(entry.commit);
    });
    li.appendChild(btn);
    el.changelogList.appendChild(li);
  });
}

export function renderChangelogFiles(files, activePath) {
  if (!el.changelogFiles) return;
  el.changelogFiles.innerHTML = "";
  (files || []).forEach(function (f) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className =
      "changelog-file-btn" + (f === activePath ? " active" : "");
    btn.setAttribute("data-path", f);
    btn.setAttribute("data-testid", "changelog-file");
    btn.title = f;
    btn.textContent = basenamePath(f);
    btn.addEventListener("click", function () {
      selectChangelogFile(f);
    });
    li.appendChild(btn);
    el.changelogFiles.appendChild(li);
  });
}

export function colorizeUnifiedDiff(diffText) {
  if (!diffText) {
    return '<span class="diff-empty">Pas de diff pour ce commit.</span>';
  }
  const lines = String(diffText).split("\n");
  return lines
    .map(function (line) {
      let cls = "diff-line";
      if (line.startsWith("+++") || line.startsWith("---")) {
        cls += " diff-meta";
      } else if (line.startsWith("@@")) {
        cls += " diff-hunk";
      } else if (line.startsWith("+")) {
        cls += " diff-add";
      } else if (line.startsWith("-")) {
        cls += " diff-del";
      }
      return '<span class="' + cls + '">' + escapeHtml(line) + "</span>";
    })
    .join("\n");
}

/**
 * F0115: charge l historique Track du composant (ou vide si pas de selection).
 * Zone → commits de la zone + tous les membres recursifs.
 */
export async function loadStepChangelog(stepId) {
  if (!el.changelogList) return;
  resetChangelogUi();
  const sid = stepId ? String(stepId).trim() : "";
  if (!sid) {
    if (el.changelogEmpty) {
      el.changelogEmpty.hidden = false;
      el.changelogEmpty.textContent =
        "Sélectionnez un composant pour voir son historique Track";
    }
    if (el.changelogDiff) {
      el.changelogDiff.innerHTML =
        '<span class="diff-empty">Sélectionnez un composant (dataset, zone…)</span>';
    }
    if (el.changelogDiffMeta) {
      el.changelogDiffMeta.textContent = "Track · aucun composant";
    }
    return;
  }
  if (el.changelogEmpty) {
    el.changelogEmpty.hidden = false;
    el.changelogEmpty.textContent = "Chargement…";
  }
  if (el.changelogDiffMeta) {
    el.changelogDiffMeta.textContent = "Track · " + sid;
  }
  try {
    const data = await api(
      "/gui/changelog?limit=80&step_id=" + encodeURIComponent(sid)
    );
    state.changelogEntries = data.entries || [];
    state.changelogScope = {
      step_id: data.step_id || sid,
      paths: data.paths || [],
    };
    renderChangelogTimeline(state.changelogEntries);
    if (state.changelogEntries.length) {
      await selectChangelogCommit(state.changelogEntries[0].commit);
    } else {
      if (el.changelogEmpty) {
        el.changelogEmpty.hidden = false;
        el.changelogEmpty.textContent =
          "Aucun commit pour « " + sid + " » (zone = historique récursif)";
      }
      if (el.changelogDiff) {
        el.changelogDiff.innerHTML =
          '<span class="diff-empty">Aucun historique pour ce composant</span>';
      }
    }
  } catch (e) {
    state.changelogEntries = [];
    renderChangelogTimeline([]);
    if (el.changelogEmpty) {
      el.changelogEmpty.hidden = false;
      el.changelogEmpty.textContent = e.message || "Changelogs indisponibles";
    }
    if (el.changelogDiff) {
      el.changelogDiff.innerHTML =
        '<span class="diff-empty">' +
        escapeHtml(e.message || "Changelogs indisponibles") +
        "</span>";
    }
  }
}

/** @deprecated alias F0115 — Track n est plus global */
export async function loadGlobalChangelog() {
  return loadStepChangelog(state.selected || null);
}

export async function selectChangelogCommit(commit) {
  if (!commit) return;
  state.changelogCommit = commit;
  if (el.changelogList) {
    Array.prototype.forEach.call(
      el.changelogList.querySelectorAll(".changelog-item"),
      function (li) {
        li.classList.toggle(
          "active",
          li.getAttribute("data-commit") === commit
        );
      }
    );
  }
  const entry =
    state.changelogEntries.find(function (e) {
      return e.commit === commit;
    }) || null;
  if (el.changelogDiffMeta) {
    el.changelogDiffMeta.textContent = entry
      ? (entry.short || commit.slice(0, 8)) +
        " · " +
        formatChangelogDate(entry.date) +
        (entry.subject ? " · " + entry.subject : "")
      : commit.slice(0, 8);
  }
  if (el.changelogDiff) {
    el.changelogDiff.innerHTML =
      '<span class="diff-empty">Chargement…</span>';
  }
  if (el.changelogFiles) el.changelogFiles.innerHTML = "";
  setChangelogApplyEnabled(false);
  try {
    const data = await api(
      "/gui/changelog/" + encodeURIComponent(commit)
    );
    state.changelogFiles = data.files || [];
    state.changelogPath = data.path || null;
    state.changelogCommit = data.commit || commit;
    renderChangelogFiles(state.changelogFiles, state.changelogPath);
    if (el.changelogDiff) {
      el.changelogDiff.innerHTML = colorizeUnifiedDiff(data.diff || "");
    }
    if (el.changelogDiffMeta) {
      const focus = state.changelogPath
        ? " · " + state.changelogPath
        : "";
      el.changelogDiffMeta.textContent =
        (data.short || commit.slice(0, 8)) +
        " · " +
        formatChangelogDate(data.date || (entry && entry.date)) +
        (data.subject ? " · " + data.subject : "") +
        focus;
    }
    setChangelogApplyEnabled(!!state.changelogCommit);
    // charge auto le composant si le fichier est un step YAML
    if (data.step_id && data.step_id !== state.selected) {
      try {
        await selectStep(data.step_id);
        // rester sur l onglet changelogs
        if (state.bottomTab !== "changelogs") {
          switchBottomTab("changelogs");
        } else {
          // selectStep ne doit pas quitter changelogs — re-affirmer UI
          if (el.panelChangelogs) el.panelChangelogs.hidden = false;
          if (el.panelDataPreview) el.panelDataPreview.hidden = true;
        }
      } catch (_) {
        /* step peut ne plus exister a HEAD */
      }
    }
  } catch (e) {
    if (el.changelogDiff) {
      el.changelogDiff.innerHTML =
        '<span class="diff-empty">' + escapeHtml(e.message) + "</span>";
    }
  }
}

export async function selectChangelogFile(path) {
  if (!state.changelogCommit || !path) return;
  state.changelogPath = path;
  renderChangelogFiles(state.changelogFiles, path);
  if (el.changelogDiff) {
    el.changelogDiff.innerHTML =
      '<span class="diff-empty">Chargement…</span>';
  }
  try {
    const q = "?path=" + encodeURIComponent(path);
    const data = await api(
      "/gui/changelog/" +
        encodeURIComponent(state.changelogCommit) +
        q
    );
    if (el.changelogDiff) {
      el.changelogDiff.innerHTML = colorizeUnifiedDiff(data.diff || "");
    }
    if (el.changelogDiffMeta) {
      el.changelogDiffMeta.textContent =
        (data.short || state.changelogCommit.slice(0, 8)) +
        (data.subject ? " · " + data.subject : "") +
        " · " +
        path;
    }
    if (data.step_id && data.step_id !== state.selected) {
      try {
        await selectStep(data.step_id);
        if (el.panelChangelogs) el.panelChangelogs.hidden = false;
        if (el.panelDataPreview) el.panelDataPreview.hidden = true;
        state.bottomTab = "changelogs";
      } catch (_) {}
    }
  } catch (e) {
    if (el.changelogDiff) {
      el.changelogDiff.innerHTML =
        '<span class="diff-empty">' + escapeHtml(e.message) + "</span>";
    }
  }
}

export async function applyChangelog(mode) {
  if (!state.changelogCommit) return;
  if (state.workspace && state.workspace.read_only) {
    toast("Lecture seule", "error");
    return;
  }
  const short = state.changelogCommit.slice(0, 8);
  const isFile = mode === "file";
  if (isFile && !state.changelogPath) {
    toast("Aucun fichier selectionne", "error");
    return;
  }
  // F0114: dialog stylé renatus (plus de window.confirm natif)
  const ok = await confirmDialog({
    title: isFile ? "Apply file — restaurer un fichier" : "Apply all — restaurer l'état",
    message: isFile
      ? "Restaurer uniquement le fichier\n  " +
        state.changelogPath +
        "\ndepuis " +
        short +
        " ?\n\nNouveau commit (forward-only, historique conservé)."
      : "Restaurer TOUS les fichiers à l'état de " +
        short +
        " ?\n\nSnapshot complet en un nouveau commit (forward-only).",
    confirmLabel: isFile ? "Restaurer le fichier" : "Restaurer tout",
    cancelLabel: "Annuler",
    danger: !isFile,
    variant: "restore",
    focusCancel: true,
  });
  if (!ok) return;
  setChangelogApplyEnabled(false);
  try {
    const body = {
      commit: state.changelogCommit,
      mode: isFile ? "file" : "all",
    };
    if (isFile) body.path = state.changelogPath;
    const res = await api("/gui/changelog/apply", {
      method: "POST",
      body: JSON.stringify(body),
    });
    toast(res.message || "Etat reapplique", "success");
    if (res.step_id) {
      await selectStep(res.step_id);
    } else if (state.selected) {
      try {
        await selectStep(state.selected);
      } catch (_) {
        state.selected = null;
      }
    }
    await refreshTabs();
    await refreshGraph();
    switchBottomTab("changelogs");
  } catch (e) {
    toast("Apply: " + e.message, "error");
    setChangelogApplyEnabled(true);
  }
}
