/**
 * F0140 — Select custom Renatus (remplace le popup OS des <select>).
 *
 * Probleme: un <select> natif se referme des que le focus quitte (Print Screen,
 * outil capture, etc.) — impossible de capturer le menu deroule.
 *
 * Solution: bouton + panneau listbox en DOM (reste ouvert pendant PrintScreen).
 * La <select> reste la source de verite (valeur, change, options).
 */
import { $ } from "./util.js";

const OPEN_CLASS = "rs-open";
let _wired = false;
let _openPanel = null;
let _openSelect = null;
let _openBtn = null;

/** Touches / combos qui ne doivent PAS fermer un menu (captures d ecran). */
export function isScreenshotGesture(ev) {
  if (!ev) return false;
  const key = String(ev.key || "");
  const code = String(ev.code || "");
  // Print Screen (noms variables selon navigateur / OS)
  if (
    key === "PrintScreen" ||
    key === "Print" ||
    key === "Snapshot" ||
    code === "PrintScreen" ||
    code === "F13"
  ) {
    return true;
  }
  // Win+Shift+S / Cmd+Shift+S / Ctrl+Shift+S (outils capture systeme)
  // Meta = Super/Win ou Cmd
  if (
    ev.shiftKey &&
    (ev.metaKey || ev.ctrlKey) &&
    (key === "s" || key === "S" || code === "KeyS")
  ) {
    return true;
  }
  // Alt+PrintScreen (capture fenetre)
  if (ev.altKey && (key === "PrintScreen" || code === "PrintScreen")) {
    return true;
  }
  return false;
}

function wrapOf(sel) {
  // Uniquement le wrap dedie — pas le parent form (sinon pas de fleche)
  return (sel && sel.closest && sel.closest(".renatus-select-wrap")) || null;
}

/** Chevron SVG explicite (F0141) — plus fiable que le pseudo ::after seul. */
const CHEVRON_SVG =
  '<span class="rs-chevron" aria-hidden="true">' +
  '<svg width="12" height="12" viewBox="0 0 12 12" fill="none">' +
  '<path d="M2.5 4.5 L6 8 L9.5 4.5" stroke="currentColor" stroke-width="1.75" ' +
  'stroke-linecap="round" stroke-linejoin="round"/>' +
  "</svg></span>";

function syncTriggerLabel(sel, btn) {
  if (!sel || !btn) return;
  const opt = sel.options[sel.selectedIndex];
  const text = opt ? opt.textContent || opt.value : sel.value || "—";
  const label = btn.querySelector(".rs-trigger-label");
  if (label) {
    label.textContent = text;
  } else {
    btn.innerHTML =
      '<span class="rs-trigger-label"></span>' + CHEVRON_SVG;
    const lab = btn.querySelector(".rs-trigger-label");
    if (lab) lab.textContent = text;
  }
  btn.title = text + " — cliquer pour ouvrir la liste";
  btn.setAttribute("aria-label", text + " (liste deroulante)");
}

function rebuildPanel(sel, panel, btn) {
  if (!sel || !panel) return;
  panel.innerHTML = "";
  const opts = Array.prototype.slice.call(sel.options || []);
  opts.forEach(function (opt, idx) {
    if (opt.disabled && opt.hidden) return;
    const li = document.createElement("li");
    li.setAttribute("role", "option");
    li.className = "rs-option";
    li.tabIndex = opt.disabled ? -1 : 0;
    li.dataset.value = opt.value;
    li.dataset.index = String(idx);
    li.setAttribute("data-testid", "rs-option-" + (opt.value || idx));
    li.textContent = opt.textContent || opt.value;
    if (opt.disabled) {
      li.classList.add("is-disabled");
      li.setAttribute("aria-disabled", "true");
    }
    if (opt.selected || opt.value === sel.value) {
      li.classList.add("is-selected");
      li.setAttribute("aria-selected", "true");
    } else {
      li.setAttribute("aria-selected", "false");
    }
    if (!opt.disabled) {
      li.addEventListener("mousedown", function (ev) {
        // mousedown: evite blur avant click
        ev.preventDefault();
        ev.stopPropagation();
      });
      li.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (sel.value !== opt.value) {
          sel.value = opt.value;
          // declenche les listeners change existants
          sel.dispatchEvent(new Event("change", { bubbles: true }));
        }
        syncTriggerLabel(sel, btn);
        closeOpenPanel();
      });
    }
    panel.appendChild(li);
  });
  syncTriggerLabel(sel, btn);
}

function positionPanel(wrap, panel, btn) {
  if (!wrap || !panel || !btn) return;
  // panneau sous le bouton, largeur min = trigger
  panel.style.minWidth = Math.max(btn.offsetWidth, 120) + "px";
  panel.style.left = "0";
  panel.style.right = "auto";
  panel.style.top = "100%";
  // si debordement bas viewport: ouvrir vers le haut
  const rect = btn.getBoundingClientRect();
  const spaceBelow = window.innerHeight - rect.bottom;
  const estH = Math.min(280, (panel.children.length || 1) * 32 + 8);
  if (spaceBelow < estH && rect.top > spaceBelow) {
    panel.style.top = "auto";
    panel.style.bottom = "100%";
    panel.classList.add("rs-panel-up");
  } else {
    panel.style.bottom = "auto";
    panel.classList.remove("rs-panel-up");
  }
}

function closeOpenPanel() {
  if (_openPanel) {
    _openPanel.hidden = true;
    _openPanel.classList.remove(OPEN_CLASS);
  }
  if (_openBtn) {
    _openBtn.setAttribute("aria-expanded", "false");
  }
  if (_openSelect) {
    const w = wrapOf(_openSelect);
    if (w) w.classList.remove(OPEN_CLASS);
  }
  _openPanel = null;
  _openSelect = null;
  _openBtn = null;
}

function openPanel(sel, panel, btn) {
  if (_openSelect && _openSelect !== sel) {
    closeOpenPanel();
  }
  rebuildPanel(sel, panel, btn);
  const wrap = wrapOf(sel);
  panel.hidden = false;
  panel.classList.add(OPEN_CLASS);
  if (wrap) wrap.classList.add(OPEN_CLASS);
  btn.setAttribute("aria-expanded", "true");
  positionPanel(wrap, panel, btn);
  _openPanel = panel;
  _openSelect = sel;
  _openBtn = btn;
  // focus 1ere option selectionnee
  const selLi =
    panel.querySelector(".rs-option.is-selected") ||
    panel.querySelector(".rs-option:not(.is-disabled)");
  if (selLi) {
    try {
      selLi.focus({ preventScroll: true });
    } catch (_) {
      /* ignore */
    }
  }
}

function togglePanel(sel, panel, btn) {
  if (_openSelect === sel && _openPanel && !_openPanel.hidden) {
    closeOpenPanel();
  } else {
    openPanel(sel, panel, btn);
  }
}

/**
 * Ameliore un <select.renatus-select> en UI custom.
 * @param {HTMLSelectElement} sel
 */
export function enhanceRenatusSelect(sel) {
  if (!sel || sel.tagName !== "SELECT") return;
  if (sel.dataset.rsUi === "1") {
    // re-sync options apres mutation
    const wrap = wrapOf(sel);
    const panel = wrap && wrap.querySelector(".rs-panel");
    const btn = wrap && wrap.querySelector(".rs-trigger");
    if (panel && btn) rebuildPanel(sel, panel, btn);
    return;
  }
  // ignore selects hidden / mirror
  if (sel.hidden || sel.getAttribute("aria-hidden") === "true") return;
  if (sel.classList.contains("import-flow-conflict-mirror")) return;

  sel.dataset.rsUi = "1";
  let wrap = wrapOf(sel);
  if (!wrap) {
    wrap = document.createElement("div");
    wrap.className = "renatus-select-wrap";
    if (sel.parentNode) {
      sel.parentNode.insertBefore(wrap, sel);
    }
    wrap.appendChild(sel);
  }
  wrap.classList.add("rs-enhanced");

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "rs-trigger";
  btn.setAttribute("aria-haspopup", "listbox");
  btn.setAttribute("aria-expanded", "false");
  btn.innerHTML =
    '<span class="rs-trigger-label">—</span>' + CHEVRON_SVG;
  const tid = sel.getAttribute("data-testid") || sel.id || "select";
  btn.setAttribute("data-testid", tid + "-trigger");
  if (sel.disabled) btn.disabled = true;

  const panel = document.createElement("ul");
  panel.className = "rs-panel";
  panel.hidden = true;
  panel.setAttribute("role", "listbox");
  panel.setAttribute("data-testid", tid + "-panel");
  panel.tabIndex = -1;

  sel.classList.add("rs-native");
  // garde accessible pour lecteurs d ecran / tests value
  sel.setAttribute("aria-hidden", "false");
  sel.tabIndex = -1;

  wrap.insertBefore(btn, sel);
  wrap.appendChild(panel);
  rebuildPanel(sel, panel, btn);

  btn.addEventListener("click", function (ev) {
    ev.preventDefault();
    ev.stopPropagation();
    if (sel.disabled || btn.disabled) return;
    togglePanel(sel, panel, btn);
  });

  // Bloque le picker natif OS
  sel.addEventListener(
    "mousedown",
    function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      if (sel.disabled) return;
      try {
        btn.focus();
      } catch (_) {}
      togglePanel(sel, panel, btn);
    },
    true
  );

  sel.addEventListener("change", function () {
    rebuildPanel(sel, panel, btn);
  });

  // Mutation options (tabs.js recree les options)
  const mo = new MutationObserver(function () {
    rebuildPanel(sel, panel, btn);
  });
  mo.observe(sel, { childList: true, subtree: true, attributes: true });
  sel._rsMo = mo;
}

export function enhanceAllRenatusSelects(root) {
  const scope = root || document;
  // tous les select visibles de la GUI (pas les mirrors hidden)
  scope
    .querySelectorAll(
      "select.renatus-select, select:not([hidden]):not(.import-flow-conflict-mirror):not(.rs-native)"
    )
    .forEach(function (sel) {
      try {
        enhanceRenatusSelect(sel);
      } catch (e) {
        console.warn("renatus-select enhance", e);
      }
    });
}

export function closeAllRenatusSelects() {
  closeOpenPanel();
}

/**
 * Branche le comportement global (click dehors, clavier, mutations).
 */
export function wireRenatusSelects() {
  if (_wired) return;
  _wired = true;
  enhanceAllRenatusSelects(document);

  // click exterieur ferme (sauf pendant gesture capture — pas un click)
  document.addEventListener(
    "mousedown",
    function (ev) {
      if (!_openPanel) return;
      const t = ev.target;
      if (
        t &&
        (t.closest(".rs-panel") ||
          t.closest(".rs-trigger") ||
          t.closest(".rs-enhanced"))
      ) {
        return;
      }
      closeOpenPanel();
    },
    true
  );

  // F0140: ne PAS fermer sur Print Screen / raccourcis capture
  document.addEventListener(
    "keydown",
    function (ev) {
      if (isScreenshotGesture(ev)) {
        // laisse l OS capturer; ne ferme pas le panneau
        ev.stopPropagation();
        return;
      }
      if (!_openPanel) return;
      if (ev.key === "Escape") {
        ev.preventDefault();
        closeOpenPanel();
        if (_openBtn) {
          try {
            _openBtn.focus();
          } catch (_) {}
        }
        return;
      }
      // navigation fleches dans le panneau
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        const items = Array.prototype.slice.call(
          _openPanel.querySelectorAll(".rs-option:not(.is-disabled)")
        );
        if (!items.length) return;
        ev.preventDefault();
        let idx = items.indexOf(document.activeElement);
        if (idx < 0) {
          idx = items.findIndex(function (li) {
            return li.classList.contains("is-selected");
          });
        }
        if (ev.key === "ArrowDown") {
          idx = idx < 0 ? 0 : Math.min(items.length - 1, idx + 1);
        } else {
          idx = idx < 0 ? items.length - 1 : Math.max(0, idx - 1);
        }
        try {
          items[idx].focus();
        } catch (_) {
          items[idx].tabIndex = 0;
          items[idx].focus();
        }
        return;
      }
      if (ev.key === "Enter" && document.activeElement) {
        const li = document.activeElement.closest
          ? document.activeElement.closest(".rs-option")
          : null;
        if (li && _openPanel.contains(li) && !li.classList.contains("is-disabled")) {
          ev.preventDefault();
          li.click();
        }
      }
    },
    true
  );

  // focusout: ne ferme PAS pour PrintScreen (pas de focusout fiable),
  // seulement si focus sort vraiment hors wrap
  document.addEventListener(
    "focusin",
    function (ev) {
      if (!_openPanel || !_openSelect) return;
      const wrap = wrapOf(_openSelect);
      const t = ev.target;
      if (wrap && t && wrap.contains(t)) return;
      if (t && t.closest && t.closest(".rs-panel")) return;
      // ne ferme pas si c est un element ephemere
      closeOpenPanel();
    },
    true
  );

  // re-enhance apres mutations DOM (nouveaux selects)
  const mo = new MutationObserver(function (muts) {
    let need = false;
    for (let i = 0; i < muts.length; i++) {
      const m = muts[i];
      if (m.addedNodes && m.addedNodes.length) {
        need = true;
        break;
      }
    }
    if (need) enhanceAllRenatusSelects(document);
  });
  if (document.body) {
    mo.observe(document.body, { childList: true, subtree: true });
  }

  // re-sync quand la fenetre reprend le focus apres capture systeme
  window.addEventListener("focus", function () {
    // ne ferme pas volontairement — laisse le menu ouvert
  });
  window.addEventListener("blur", function () {
    // F0140: ne ferme PAS le menu quand la fenetre perd le focus
    // (souvent a cause de l outil de capture d ecran)
  });
}
