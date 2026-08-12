/**
 * F0102 / F0107 / F0111 / F0120 / F0130 / F0132 — Importer flux (fichier ou dossier).
 *
 * F0130: eviter la popup Chromium non stylable
 * « Importer N fichiers sur ce site ? » declenchee par webkitdirectory.
 * Priorite:
 *  1) showDirectoryPicker (FSA) — pas de dialogue « Importer N fichiers »
 *  2) glisser-deposer dossier (pas de file-picker multi-fichiers)
 *  3) webkitdirectory en dernier recours + pre-dialog Renatus themé
 *
 * F0132: pendant upload / import / refresh graphe — pop bloquante
 * « Traitement en cours » + barre de progression (pas d ecran vide).
 */
import { state, el } from "./state.js";
import { api, toast } from "./api.js";
import { confirmDialog } from "./confirm-dialog.js";
import { withProgress } from "./progress-dialog.js";
import { refreshGraph } from "./graph.js";
import { refreshTabs } from "./tabs.js";
import { ensureSelection } from "./config/step-crud.js";

const IMPORT_SUBDIR = "import_flow";

function setSourcePath(path, statusText) {
  if (el.importFlowSource) {
    el.importFlowSource.value = path || "";
  }
  if (el.importFlowPathStatus) {
    el.importFlowPathStatus.textContent =
      statusText ||
      (path ? "Source : " + path : "Aucune source sélectionnée");
  }
  const zone = el.importFlowDropzone;
  if (zone) {
    zone.classList.toggle("has-source", !!path);
  }
}

function getConflictStrategy() {
  const cards = document.querySelector(
    'input[name="import-flow-conflict"]:checked'
  );
  if (cards && cards.value) return cards.value;
  if (el.importFlowConflict) return el.importFlowConflict.value || "keep_both";
  return "keep_both";
}

function syncConflictMirror(value) {
  const v = value || "keep_both";
  if (el.importFlowConflict) el.importFlowConflict.value = v;
  const radios = document.querySelectorAll(
    'input[name="import-flow-conflict"]'
  );
  radios.forEach(function (r) {
    r.checked = r.value === v;
  });
}

/** F0112: s assure que chaque carte conflit a bien son pictogramme visible. */
function ensureConflictIcons() {
  const cards = document.querySelectorAll(
    ".import-flow-conflict-card[data-conflict]"
  );
  const emojiBy = {
    keep_both: "📑",
    keep_existing: "🛡️",
    replace: "⬇️",
  };
  cards.forEach(function (card) {
    const key = card.getAttribute("data-conflict") || "";
    let icon = card.querySelector(".card-icon");
    if (!icon) {
      icon = document.createElement("span");
      icon.className = "card-icon";
      icon.setAttribute("data-testid", "conflict-icon-" + key);
      const radio = card.querySelector('input[type="radio"]');
      if (radio && radio.nextSibling) {
        card.insertBefore(icon, radio.nextSibling);
      } else {
        card.insertBefore(icon, card.firstChild);
      }
    }
    icon.hidden = false;
    icon.style.display = "flex";
    let emoji = icon.querySelector(".card-emoji");
    if (!emoji) {
      emoji = document.createElement("span");
      emoji.className = "card-emoji";
      emoji.setAttribute("aria-hidden", "true");
      icon.insertBefore(emoji, icon.firstChild);
    }
    if (!emoji.textContent || !emoji.textContent.trim()) {
      emoji.textContent = emojiBy[key] || "•";
    }
    emoji.style.fontSize = "1.55rem";
    emoji.style.lineHeight = "1";
  });
}

export function openImportFlowDialog() {
  if (!el.importFlowDialog) {
    toast("Dialog import indisponible", "error");
    return;
  }
  if (state.workspace && state.workspace.read_only) {
    toast("Lecture seule", "error");
    return;
  }
  fillImportZoneSelect();
  setSourcePath("", "Aucune source sélectionnée — fichier YAML ou dossier parent");
  syncConflictMirror("keep_both");
  ensureConflictIcons();
  if (el.importFlowPreview) {
    el.importFlowPreview.hidden = true;
    el.importFlowPreview.textContent = "";
  }
  // F0111: forcer mode dossier sur le picker (certains navigateurs l oublient)
  ensureDirPickerAttrs();
  try {
    el.importFlowDialog.showModal();
  } catch (e) {
    toast("Import: " + e.message, "error");
  }
}

function ensureDirPickerAttrs() {
  const dir = el.importFlowDirPicker;
  if (!dir) return;
  try {
    // Attributs + propriétés (Chromium / WebKit / Firefox)
    dir.setAttribute("webkitdirectory", "true");
    dir.setAttribute("directory", "true");
    dir.setAttribute("multiple", "");
    dir.multiple = true;
    try {
      dir.webkitdirectory = true;
    } catch (_) {
      /* ignore */
    }
    try {
      dir.directory = true;
    } catch (_) {
      /* ignore */
    }
  } catch (_) {
    /* ignore */
  }
}

/**
 * Ouvre le selecteur de DOSSIER (depuis un click utilisateur).
 *
 * F0130: preferer File System Access (showDirectoryPicker) pour eviter
 * la popup Chromium « Importer N fichiers sur ce site » (webkitdirectory).
 * Les dialogues navigateur restent non stylables ; on minimise leur usage
 * et on theming le pre-dialog Renatus pour le repli webkitdirectory.
 */
function openDirectoryPickerSync() {
  ensureDirPickerAttrs();
  // 1) Chromium / Edge : FSA — pas de dialogue « Importer N fichiers »
  if (typeof window.showDirectoryPicker === "function") {
    pickDirectoryModern()
      .then(function (files) {
        if (files === null) {
          // API absente en pratique → repli
          return openWebkitDirectoryFallback();
        }
        if (!files.length) return; // annulation
        return handleDirectoryFiles(files);
      })
      .catch(function (e) {
        console.warn("showDirectoryPicker", e);
        return openWebkitDirectoryFallback();
      });
    return;
  }
  // 2) Firefox / Safari : webkitdirectory (+ pre-dialog themé)
  openWebkitDirectoryFallback();
}

/**
 * F0130: repli webkitdirectory avec dialogue Renatus themé avant le picker.
 * Explique la confirmation systeme eventuelle (non stylable).
 */
async function openWebkitDirectoryFallback() {
  const dir = el.importFlowDirPicker;
  if (!dir) {
    toast(
      "Sélecteur de dossier indisponible — glissez le dossier dans la zone",
      "error"
    );
    return;
  }
  const ok = await confirmDialog({
    title: "Choisir un dossier de flux",
    message:
      "Sélectionnez le dossier parent contenant vos YAML.\n\n" +
      "Le navigateur peut afficher une confirmation système " +
      "(« Importer N fichiers sur ce site ») — ce dialogue n’est pas " +
      "personnalisable. Cliquez « Importer » pour continuer.\n\n" +
      "Astuce : glisser-déposer le dossier dans la zone évite souvent " +
      "cette étape.",
    confirmLabel: "Ouvrir le sélecteur",
    cancelLabel: "Annuler",
    danger: false,
    variant: "info",
    focusCancel: false,
  });
  if (!ok) return;
  ensureDirPickerAttrs();
  try {
    dir.value = "";
    dir.click();
  } catch (e) {
    toast(
      "Sélection dossier: " +
        (e && e.message ? e.message : String(e)) +
        " — glissez le dossier dans la zone",
      "error"
    );
  }
}

async function fillImportZoneSelect() {
  const sel = el.importFlowTarget;
  if (!sel) return;
  let zones = [];
  try {
    const data = await api("/gui/import/zones");
    zones = data.zones || [];
  } catch (_) {
    try {
      const t = await api("/gui/tabs");
      zones = (t.tabs || []).map(function (x) {
        return { id: x.id, label: x.label || x.id };
      });
    } catch (__) {
      zones = [{ id: "default", label: "default" }];
    }
  }
  const active = state.activeTab || "default";
  sel.innerHTML = zones
    .map(function (z) {
      const id = z.id || z;
      const lab = z.label || id;
      const selAttr = id === active ? " selected" : "";
      return (
        '<option value="' +
        String(id).replace(/"/g, "&quot;") +
        '"' +
        selAttr +
        ">" +
        String(lab) +
        (id !== lab ? " (" + id + ")" : "") +
        "</option>"
      );
    })
    .join("");
  if (!zones.length) {
    sel.innerHTML = '<option value="default">default</option>';
  }
}

async function uploadOneFile(file, relativePath) {
  const body = new FormData();
  body.append("file", file, file.name || "file.yaml");
  if (relativePath) {
    body.append("relative_path", relativePath);
  }
  const url =
    "/gui/upload?subdir=" + encodeURIComponent(IMPORT_SUBDIR);
  const res = await fetch(url, { method: "POST", body: body });
  let data = null;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) data = await res.json();
  else data = { detail: await res.text() };
  if (!res.ok) {
    const msg = (data && (data.error || data.detail)) || res.statusText;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

/** Attache webkitRelativePath si absent (File est souvent non extensible). */
function withRelativePath(file, relPath) {
  const rel = String(relPath || file.name || "file").replace(/\\/g, "/");
  try {
    Object.defineProperty(file, "webkitRelativePath", {
      value: rel,
      configurable: true,
    });
    return file;
  } catch (_) {
    // File non extensible: wrapper minimal
    return {
      name: file.name,
      size: file.size,
      type: file.type,
      lastModified: file.lastModified,
      webkitRelativePath: rel,
      slice: file.slice ? file.slice.bind(file) : undefined,
      arrayBuffer: file.arrayBuffer
        ? file.arrayBuffer.bind(file)
        : undefined,
      stream: file.stream ? file.stream.bind(file) : undefined,
      text: file.text ? file.text.bind(file) : undefined,
      _blob: file,
    };
  }
}

function asBlob(fileLike) {
  if (fileLike && fileLike._blob) return fileLike._blob;
  return fileLike;
}

/** Upload un seul YAML (drag ou parcourir fichier). */
async function handleYamlFile(file) {
  if (!file) return;
  const name = file.name || "";
  if (!/\.ya?ml$/i.test(name)) {
    toast("Fichier YAML attendu (.yaml / .yml)", "error");
    return;
  }
  if (el.importFlowPathStatus) {
    el.importFlowPathStatus.textContent = "Upload… " + name;
  }
  try {
    const data = await withProgress(
      {
        title: "Upload en cours",
        message: "Envoi de " + name + "…",
        mode: "indeterminate",
      },
      async function (prog) {
        const data = await uploadOneFile(asBlob(file), name);
        prog.done("Upload terminé");
        return data;
      }
    );
    const path = data.absolute || data.path || "";
    setSourcePath(
      path,
      "Fichier : " + (data.path || path) + " (" + (data.size || file.size) + " o)"
    );
    toast(data.message || "Upload OK", "success");
  } catch (e) {
    toast("Upload: " + e.message, "error");
    if (el.importFlowPathStatus) {
      el.importFlowPathStatus.textContent = e.message;
    }
  }
}

/**
 * Upload d un dossier : reconstitute l arbo sous import_flow/<bundle>/.
 * Source = chemin absolu du dossier racine uploade.
 * F0132: pop bloquante + progression fichier par fichier.
 */
async function handleDirectoryFiles(fileList) {
  const files = Array.prototype.slice.call(fileList || []);
  if (!files.length) {
    toast("Aucun fichier dans le dossier sélectionné", "error");
    return;
  }
  const yamlFiles = files.filter(function (f) {
    const rel = f.webkitRelativePath || f.name || "";
    return /\.ya?ml$/i.test(rel);
  });
  if (!yamlFiles.length) {
    toast(
      "Aucun fichier YAML (.yaml / .yml) dans ce dossier (y compris sous-dossiers)",
      "error"
    );
    return;
  }
  // racine = 1er segment de webkitRelativePath
  const firstRel = yamlFiles[0].webkitRelativePath || yamlFiles[0].name;
  const rootName =
    String(firstRel).split(/[/\\]/).filter(Boolean)[0] || "import_bundle";
  const stamp = new Date()
    .toISOString()
    .replace(/[:.]/g, "-")
    .slice(0, 19);
  const bundleRoot = rootName + "_" + stamp;
  const total = yamlFiles.length;

  if (el.importFlowPathStatus) {
    el.importFlowPathStatus.textContent =
      "Upload dossier… 0/" + total + " YAML";
  }
  try {
    const result = await withProgress(
      {
        title: "Upload du dossier",
        message:
          "Envoi de " + total + " fichier(s) YAML (« " + rootName + " »)…",
        total: total,
        current: 0,
      },
      async function (prog) {
        let last = null;
        let rootAbs = null;
        for (let i = 0; i < yamlFiles.length; i++) {
          const f = yamlFiles[i];
          const relOrig = String(f.webkitRelativePath || f.name).replace(
            /\\/g,
            "/"
          );
          const parts = relOrig.split("/").filter(Boolean);
          if (!parts.length) continue;
          parts[0] = bundleRoot;
          const rel = parts.join("/");
          const leaf = parts[parts.length - 1];
          const msg =
            "Upload " + (i + 1) + "/" + total + " · " + leaf;
          if (el.importFlowPathStatus) {
            el.importFlowPathStatus.textContent = "Upload dossier… " + msg;
          }
          prog.set({
            current: i,
            percent: (i / total) * 100,
            message: msg,
          });
          last = await uploadOneFile(asBlob(f), rel);
          prog.set({
            current: i + 1,
            percent: ((i + 1) / total) * 100,
            message: msg,
          });
          if (!rootAbs && last.absolute) {
            const abs = String(last.absolute).replace(/\\/g, "/");
            const marker = "/" + IMPORT_SUBDIR + "/" + bundleRoot;
            const idx = abs.indexOf(marker);
            if (idx >= 0) {
              rootAbs = abs.slice(0, idx + marker.length);
            } else {
              const segs = abs.split("/");
              const bi = segs.indexOf(bundleRoot);
              if (bi >= 0) {
                rootAbs = segs.slice(0, bi + 1).join("/");
              }
            }
          }
        }
        prog.done("Upload terminé · " + total + " YAML");
        return { last: last, rootAbs: rootAbs };
      }
    );
    const last = result.last;
    const rootAbs = result.rootAbs;
    const path =
      rootAbs ||
      (last && last.absolute
        ? String(last.absolute).replace(/[/\\][^/\\]+$/, "")
        : "");
    if (!path) {
      throw new Error("Impossible de déterminer le chemin du dossier uploadé");
    }
    setSourcePath(
      path,
      "Dossier : " +
        rootName +
        " → " +
        bundleRoot +
        " · " +
        total +
        " YAML (arborescence conservée)"
    );
    toast(
      "Dossier prêt · " + total + " fichier(s) YAML — cliquez Importer",
      "success"
    );
  } catch (e) {
    toast("Upload dossier: " + e.message, "error");
    if (el.importFlowPathStatus) {
      el.importFlowPathStatus.textContent = e.message;
    }
  }
}

/**
 * F0111: File System Access API — choix dossier moderne (Chrome/Edge).
 * @returns {Promise<File[]|null>}
 */
async function pickDirectoryModern() {
  if (typeof window.showDirectoryPicker !== "function") {
    return null;
  }
  try {
    const dirHandle = await window.showDirectoryPicker({
      id: "renatus-import-flow",
      mode: "read",
    });
    const files = await collectFilesFromDirHandle(
      dirHandle,
      dirHandle.name || "import_bundle"
    );
    return files;
  } catch (e) {
    // AbortError = utilisateur annule
    if (e && (e.name === "AbortError" || e.name === "NotAllowedError")) {
      return [];
    }
    throw e;
  }
}

async function collectFilesFromDirHandle(dirHandle, prefix) {
  const out = [];
  const pref = String(prefix || dirHandle.name || "dir").replace(/\\/g, "/");
  for await (const [name, handle] of dirHandle.entries()) {
    if (handle.kind === "file") {
      const file = await handle.getFile();
      out.push(withRelativePath(file, pref + "/" + name));
    } else if (handle.kind === "directory") {
      const nested = await collectFilesFromDirHandle(
        handle,
        pref + "/" + name
      );
      for (let i = 0; i < nested.length; i++) out.push(nested[i]);
    }
  }
  return out;
}

/** @deprecated use openDirectoryPickerSync from click handlers */
async function openDirectoryPicker() {
  openDirectoryPickerSync();
}

/**
 * Lit récursivement un FileSystemDirectoryEntry (drag-drop dossier).
 */
function readDirEntry(dirEntry, pathPrefix) {
  return new Promise(function (resolve, reject) {
    const reader = dirEntry.createReader();
    const acc = [];
    function readBatch() {
      reader.readEntries(function (entries) {
        if (!entries.length) {
          resolve(acc);
          return;
        }
        Promise.all(
          entries.map(function (entry) {
            const rel =
              (pathPrefix ? pathPrefix + "/" : "") + entry.name;
            if (entry.isDirectory) {
              return readDirEntry(entry, rel).then(function (sub) {
                acc.push.apply(acc, sub);
              });
            }
            if (entry.isFile) {
              return new Promise(function (res, rej) {
                entry.file(
                  function (file) {
                    acc.push(withRelativePath(file, rel));
                    res();
                  },
                  rej
                );
              });
            }
            return Promise.resolve();
          })
        )
          .then(readBatch)
          .catch(reject);
      }, reject);
    }
    readBatch();
  });
}

/**
 * Extrait fichiers depuis DataTransfer (drop fichier ou dossier).
 * @returns {Promise<{kind:'file'|'dir', files:File[]}>}
 */
async function filesFromDataTransfer(dt) {
  const items = dt.items ? Array.prototype.slice.call(dt.items) : [];
  const plain = dt.files ? Array.prototype.slice.call(dt.files) : [];

  // Entrées FS (dossier possible)
  const entryPromises = [];
  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (item.kind !== "file") continue;
    let entry = null;
    try {
      if (typeof item.webkitGetAsEntry === "function") {
        entry = item.webkitGetAsEntry();
      }
    } catch (_) {
      entry = null;
    }
    if (entry && entry.isDirectory) {
      entryPromises.push(
        readDirEntry(entry, entry.name).then(function (files) {
          return { kind: "dir", files: files };
        })
      );
    } else if (entry && entry.isFile) {
      entryPromises.push(
        new Promise(function (res, rej) {
          entry.file(
            function (file) {
              res({ kind: "file", files: [file] });
            },
            rej
          );
        })
      );
    }
  }

  if (entryPromises.length) {
    const parts = await Promise.all(entryPromises);
    const allFiles = [];
    let anyDir = false;
    parts.forEach(function (p) {
      if (p.kind === "dir") anyDir = true;
      p.files.forEach(function (f) {
        allFiles.push(f);
      });
    });
    return { kind: anyDir || allFiles.length > 1 ? "dir" : "file", files: allFiles };
  }

  // Fallback: liste plate (parfois relativePath déjà present)
  if (plain.length > 1) {
    return {
      kind: "dir",
      files: plain.map(function (f) {
        if (f.webkitRelativePath) return f;
        return withRelativePath(f, "dropped/" + f.name);
      }),
    };
  }
  if (plain.length === 1) {
    const f = plain[0];
    if (f.webkitRelativePath && f.webkitRelativePath.indexOf("/") >= 0) {
      return { kind: "dir", files: plain };
    }
    return { kind: "file", files: plain };
  }
  return { kind: "file", files: [] };
}

export async function previewImportFlow() {
  const source = el.importFlowSource
    ? el.importFlowSource.value.trim()
    : "";
  if (!source) {
    toast("Indiquez un fichier ou dossier source", "error");
    return;
  }
  const target =
    (el.importFlowTarget && el.importFlowTarget.value) ||
    state.activeTab ||
    "default";
  const conflict = getConflictStrategy();
  try {
    const plan = await api("/gui/import/flow", {
      method: "POST",
      body: JSON.stringify({
        source: source,
        target_tab: target,
        conflict: conflict,
        dry_run: true,
      }),
    });
    if (el.importFlowPathStatus) {
      el.importFlowPathStatus.textContent =
        (plan.source_kind || "") +
        " · " +
        (plan.count || 0) +
        " composant(s) · cible " +
        (plan.target_tab || target);
    }
    if (el.importFlowPreview) {
      const lines = [];
      lines.push("Plan d import (" + (plan.count || 0) + "):");
      (plan.items || []).forEach(function (it) {
        lines.push(
          "  " +
            (it.orig_id || "?") +
            (it.final_id && it.final_id !== it.orig_id
              ? " → " + it.final_id
              : "") +
            "  [" +
            (it.dest_tab || "") +
            "]"
        );
      });
      if (plan.conflicts && plan.conflicts.length) {
        lines.push("Conflits:");
        plan.conflicts.forEach(function (c) {
          lines.push(
            "  " +
              (c.id || "") +
              " → " +
              (c.action || "") +
              (c.final_id ? " (" + c.final_id + ")" : "")
          );
        });
      }
      if (plan.zone_tabs && plan.zone_tabs.length) {
        lines.push("Zones: " + plan.zone_tabs.join(", "));
      }
      el.importFlowPreview.textContent = lines.join("\n");
      el.importFlowPreview.hidden = false;
    }
    toast("Aperçu prêt · " + (plan.count || 0) + " item(s)", "success");
  } catch (e) {
    toast("Aperçu: " + e.message, "error");
    if (el.importFlowPathStatus) {
      el.importFlowPathStatus.textContent = e.message;
    }
  }
}

/** Laisse le navigateur peindre la barre de progression (F0133). */
function yieldUi() {
  return new Promise(function (resolve) {
    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(function () {
        setTimeout(resolve, 0);
      });
    } else {
      setTimeout(resolve, 0);
    }
  });
}

/**
 * Race avec timeout — ne laisse jamais la pop bloquee indefiniment (F0133).
 * @template T
 * @param {Promise<T>} promise
 * @param {number} ms
 * @param {string} label
 * @returns {Promise<T>}
 */
function withTimeout(promise, ms, label) {
  let timer = null;
  const timeoutP = new Promise(function (_, reject) {
    timer = setTimeout(function () {
      reject(
        new Error(
          (label || "Opération") + " trop longue (>" + Math.round(ms / 1000) + "s)"
        )
      );
    }, ms);
  });
  return Promise.race([promise, timeoutP]).finally(function () {
    if (timer) clearTimeout(timer);
  });
}

/**
 * F0132/F0133: import reel sous pop bloquante.
 * Phases :
 *  0–15 %   preparation
 * 15–70 %   import serveur (avance par pas de 10 % pendant l attente)
 * 70–82 %   activation zone + onglets
 * 82–96 %   graphe (sans selection lourde)
 * 96–100 %  terminer pop ; selection config en arriere-plan
 *
 * F0133 fix hang 90% : ne plus appeler switchTab+ensureSelection+loadDataView
 * sous la pop (selectStep / preview / Track peuvent bloquer longtemps sur
 * un gros import). Selection completee apres fermeture de la pop.
 */
export async function runImportFlow() {
  const source = el.importFlowSource
    ? el.importFlowSource.value.trim()
    : "";
  if (!source) {
    toast("Indiquez un fichier ou dossier source", "error");
    return false;
  }
  const target =
    (el.importFlowTarget && el.importFlowTarget.value) ||
    state.activeTab ||
    "default";
  const conflict = getConflictStrategy();

  // Estime depuis le libelle d upload (« · N YAML ») si present
  let hintCount = 0;
  try {
    const st =
      (el.importFlowPathStatus && el.importFlowPathStatus.textContent) || "";
    const m = st.match(/(\d+)\s*YAML/i);
    if (m) hintCount = parseInt(m[1], 10) || 0;
  } catch (_) {
    hintCount = 0;
  }

  try {
    return await withProgress(
      {
        title: "Import en cours",
        message:
          hintCount > 0
            ? "Import de " +
              hintCount +
              " fichier(s) vers « " +
              target +
              " »…"
            : "Préparation de l’import vers « " + target + " »…",
        mode: "percent",
        percent: 5,
      },
      async function (prog) {
        prog.set({
          percent: 15,
          message:
            hintCount > 0
              ? "Écriture de " + hintCount + " composant(s)…"
              : "Écriture des composants…",
        });
        await yieldUi();
        // Avance visuelle par pas de 10 % pendant l attente reseau
        let pulsePct = 15;
        const pulse = setInterval(function () {
          if (pulsePct < 65) {
            pulsePct = Math.min(65, pulsePct + 10);
            prog.set({
              percent: pulsePct,
              message:
                hintCount > 0
                  ? "Import de " +
                    hintCount +
                    " composant(s)… (" +
                    pulsePct +
                    " %)"
                  : "Import serveur… (" + pulsePct + " %)",
            });
          }
        }, 450);
        let res;
        try {
          res = await api("/gui/import/flow", {
            method: "POST",
            body: JSON.stringify({
              source: source,
              target_tab: target,
              conflict: conflict,
              dry_run: false,
            }),
          });
        } finally {
          clearInterval(pulse);
        }

        const count = Number(res.count) || hintCount || 0;
        prog.set({
          percent: 72,
          message:
            count > 0
              ? count + " composant(s) importé(s) — mise à jour des zones…"
              : "Mise à jour des zones…",
        });
        await yieldUi();

        if (res.tabs) state.tabs = res.tabs;
        // F0125: zone racine importee
        const focusTab =
          res.active_tab || res.root_import_tab || null;
        if (focusTab) {
          state.activeTab = focusTab;
        }
        state.selected = null;

        // Active l onglet cote serveur sans passer par switchTab
        // (switchTab → ensureSelection → selectStep → loadDataView = hang 90%)
        if (focusTab) {
          try {
            prog.set({
              percent: 78,
              message: "Activation de la zone « " + focusTab + " »…",
            });
            await yieldUi();
            const act = await withTimeout(
              api(
                "/gui/tabs/" + encodeURIComponent(focusTab) + "/activate",
                { method: "POST" }
              ),
              20000,
              "Activation zone"
            );
            if (act && act.active_tab) state.activeTab = act.active_tab;
            if (act && act.tabs) state.tabs = act.tabs;
          } catch (eAct) {
            console.warn("import activate tab", eAct);
          }
        }

        prog.set({
          percent: 82,
          message: "Rafraîchissement des zones…",
        });
        await yieldUi();
        try {
          await withTimeout(refreshTabs(), 15000, "Onglets");
        } catch (eTabs) {
          console.warn("import refreshTabs", eTabs);
        }

        prog.set({
          percent: 88,
          message:
            count > 0
              ? "Chargement du graphe (" + count + " nœuds)…"
              : "Chargement du graphe…",
        });
        await yieldUi();
        try {
          // skipSelection: ne pas bloquer sur ensureSelection/loadDataView
          await withTimeout(
            refreshGraph({ skipSelection: true }),
            45000,
            "Graphe"
          );
        } catch (eGraph) {
          console.warn("import refreshGraph", eGraph);
          toast(
            "Import OK, graphe partiel: " +
              (eGraph && eGraph.message ? eGraph.message : eGraph),
            "error"
          );
        }

        prog.set({
          percent: 96,
          message: "Finalisation…",
        });
        await yieldUi();
        prog.done(
          count > 0
            ? "Import terminé · " + count + " composant(s)"
            : "Import terminé"
        );
        toast(res.message || "Import OK", "success");

        // Selection config APRES fermeture pop (ne bloque plus a 90 %)
        setTimeout(function () {
          ensureSelection({ force: true }).catch(function (e) {
            console.warn("import ensureSelection deferred", e);
          });
        }, 200);

        return true;
      }
    );
  } catch (e) {
    toast("Import: " + e.message, "error");
    return false;
  }
}

function wireImportDropzone() {
  const zone = el.importFlowDropzone;
  if (!zone) return;
  ensureDirPickerAttrs();

  if (el.importFlowBrowseFile) {
    el.importFlowBrowseFile.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      if (el.importFlowFilePicker) {
        el.importFlowFilePicker.value = "";
        el.importFlowFilePicker.click();
      }
    });
  }
  if (el.importFlowBrowseDir) {
    // F0113: click SYNCHRONE → selecteur dossier (pas d await avant click)
    el.importFlowBrowseDir.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      openDirectoryPickerSync();
    });
  }

  // Clic zone vide → propose le dossier (pas le fichier seul)
  zone.addEventListener("click", function (ev) {
    if (
      ev.target &&
      (ev.target.closest("button") ||
        ev.target.closest("a") ||
        ev.target.closest("input"))
    ) {
      return;
    }
    openDirectoryPickerSync();
  });

  if (el.importFlowFilePicker) {
    el.importFlowFilePicker.addEventListener("change", function () {
      const f =
        el.importFlowFilePicker.files && el.importFlowFilePicker.files[0];
      if (f) handleYamlFile(f);
      el.importFlowFilePicker.value = "";
    });
  }
  if (el.importFlowDirPicker) {
    el.importFlowDirPicker.addEventListener("change", function () {
      const list = el.importFlowDirPicker.files;
      if (!list || !list.length) {
        toast("Aucun fichier sélectionné dans le dossier", "error");
        return;
      }
      // Log diagnostic: webkitRelativePath doit être rempli pour un vrai dossier
      const sample = list[0];
      const hasRel = !!(sample && sample.webkitRelativePath);
      if (!hasRel && list.length === 1) {
        // parfois le navigateur renvoie un seul fichier si webkitdirectory absent
        toast(
          "Le navigateur a renvoyé un fichier seul — réessayez « Dossier… » ou glissez le dossier",
          "error"
        );
      }
      handleDirectoryFiles(list);
      el.importFlowDirPicker.value = "";
    });
  }

  ["dragenter", "dragover"].forEach(function (evt) {
    zone.addEventListener(evt, function (e) {
      e.preventDefault();
      e.stopPropagation();
      zone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach(function (evt) {
    zone.addEventListener(evt, function (e) {
      e.preventDefault();
      e.stopPropagation();
      zone.classList.remove("dragover");
    });
  });
  zone.addEventListener("drop", function (e) {
    const dt = e.dataTransfer;
    if (!dt) return;
    filesFromDataTransfer(dt)
      .then(function (result) {
        if (!result.files.length) {
          toast(
            "Déposez un fichier YAML ou un dossier, ou utilisez « Dossier… »",
            "error"
          );
          return;
        }
        if (result.kind === "dir" || result.files.length > 1) {
          return handleDirectoryFiles(result.files);
        }
        return handleYamlFile(result.files[0]);
      })
      .catch(function (err) {
        toast(
          "Drop: " + (err && err.message ? err.message : String(err)),
          "error"
        );
      });
  });

  if (el.importFlowSource) {
    el.importFlowSource.addEventListener("input", function () {
      const v = el.importFlowSource.value.trim();
      if (el.importFlowPathStatus && v) {
        el.importFlowPathStatus.textContent = "Chemin : " + v;
      }
      if (el.importFlowDropzone) {
        el.importFlowDropzone.classList.toggle("has-source", !!v);
      }
    });
  }
}

function wireConflictCards() {
  const radios = document.querySelectorAll(
    'input[name="import-flow-conflict"]'
  );
  radios.forEach(function (r) {
    r.addEventListener("change", function () {
      if (r.checked) syncConflictMirror(r.value);
    });
  });
}

/** Evite double import (close + click). */
let _importRunning = false;

export function wireImportFlow() {
  if (el.btnImportFlow) {
    el.btnImportFlow.addEventListener("click", openImportFlowDialog);
  }
  if (el.importFlowPreviewBtn) {
    el.importFlowPreviewBtn.addEventListener("click", function (ev) {
      ev.preventDefault();
      previewImportFlow();
    });
  }
  // F0132: bouton Importer → progress d abord, puis fermeture dialog
  // (evite ecran vide pendant  le traitement long).
  const okBtn =
    (el.importFlowDialog &&
      el.importFlowDialog.querySelector('[data-testid="import-flow-ok"]')) ||
    null;
  if (okBtn) {
    okBtn.setAttribute("type", "button");
    okBtn.addEventListener("click", async function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      if (_importRunning) return;
      const source = el.importFlowSource
        ? el.importFlowSource.value.trim()
        : "";
      if (!source) {
        toast("Indiquez un fichier ou dossier source", "error");
        return;
      }
      _importRunning = true;
      try {
        // Ferme le dialog import puis pop progression (sync, pas d ecran vide)
        if (el.importFlowDialog && el.importFlowDialog.open) {
          try {
            el.importFlowDialog.returnValue = "cancel";
            el.importFlowDialog.close("cancel");
          } catch (_) {
            /* ignore */
          }
        }
        await runImportFlow();
      } finally {
        _importRunning = false;
      }
    });
  }
  // Repli: si un submit method=dialog atteint encore close(ok)
  if (el.importFlowDialog) {
    el.importFlowDialog.addEventListener("close", async function () {
      const rv = el.importFlowDialog.returnValue || "cancel";
      if (rv === "ok" && !_importRunning) {
        _importRunning = true;
        try {
          await runImportFlow();
        } finally {
          _importRunning = false;
        }
      }
    });
  }
  wireImportDropzone();
  wireConflictCards();
}
