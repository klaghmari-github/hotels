/**
 * Panneaux collapsables (F0076).
 * - sidebar Composant a gauche
 * - config a droite
 * - View/Track en bas
 * Persist localStorage ; plus d espace pour le flux / onglets.
 */
import { el, state } from "./state.js";

const STORAGE_KEY = "renatus.gui.layout.v1";

const DEFAULTS = {
  sidebar: true, // true = open
  config: true,
  bottom: true,
};

function loadPrefs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return Object.assign({}, DEFAULTS);
    const parsed = JSON.parse(raw);
    return {
      sidebar: parsed.sidebar !== false,
      config: parsed.config !== false,
      bottom: parsed.bottom !== false,
    };
  } catch (_) {
    return Object.assign({}, DEFAULTS);
  }
}

function savePrefs(prefs) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch (_) {
    /* ignore quota / private mode */
  }
}

function getGui() {
  return el.guiLayout || document.getElementById("gui-layout");
}

function getCenter() {
  return el.centerLayout || document.getElementById("center-layout");
}

/**
 * Applique les classes + aria + rails.
 * @param {{sidebar?:boolean, config?: boolean, bottom?: boolean}} prefs
 */
export function applyLayout(prefs) {
  const p = Object.assign({}, DEFAULTS, prefs || {});
  state.layout = p;
  const gui = getGui();
  const center = getCenter();
  if (gui) {
    gui.classList.toggle("sidebar-collapsed", !p.sidebar);
    gui.classList.toggle("bottom-collapsed", !p.bottom);
  }
  if (center) {
    center.classList.toggle("config-collapsed", !p.config);
  }

  // Sidebar
  if (el.btnCollapseSidebar) {
    el.btnCollapseSidebar.setAttribute(
      "aria-expanded",
      p.sidebar ? "true" : "false"
    );
    el.btnCollapseSidebar.textContent = p.sidebar ? "‹" : "›";
    el.btnCollapseSidebar.title = p.sidebar
      ? "Replier Composant"
      : "Ouvrir Composant";
  }
  if (el.railSidebar) el.railSidebar.hidden = p.sidebar;
  if (el.sidebar) {
    el.sidebar.setAttribute("aria-hidden", p.sidebar ? "false" : "true");
  }

  // Config
  if (el.btnCollapseConfig) {
    el.btnCollapseConfig.setAttribute(
      "aria-expanded",
      p.config ? "true" : "false"
    );
    el.btnCollapseConfig.textContent = p.config ? "›" : "‹";
    el.btnCollapseConfig.title = p.config
      ? "Replier la config"
      : "Ouvrir la config";
  }
  if (el.railConfig) el.railConfig.hidden = p.config;
  if (el.configZone) {
    el.configZone.setAttribute("aria-hidden", p.config ? "false" : "true");
  }

  // Bottom View/Track
  if (el.btnCollapseBottom) {
    el.btnCollapseBottom.setAttribute(
      "aria-expanded",
      p.bottom ? "true" : "false"
    );
    el.btnCollapseBottom.textContent = p.bottom ? "▾" : "▴";
    el.btnCollapseBottom.title = p.bottom
      ? "Replier View/Track"
      : "Ouvrir View/Track";
  }
  if (el.railBottom) el.railBottom.hidden = p.bottom;
  if (el.dataviewZone) {
    el.dataviewZone.setAttribute("aria-hidden", p.bottom ? "false" : "true");
  }

  savePrefs(p);
  // laisser le layout se stabiliser puis notifier le graphe
  try {
    window.dispatchEvent(new Event("resize"));
  } catch (_) {
    /* ignore */
  }
}

export function togglePanel(which) {
  const p = Object.assign({}, state.layout || loadPrefs());
  if (which === "sidebar") p.sidebar = !p.sidebar;
  else if (which === "config") p.config = !p.config;
  else if (which === "bottom") p.bottom = !p.bottom;
  applyLayout(p);
  return p;
}

export function openPanel(which) {
  const p = Object.assign({}, state.layout || loadPrefs());
  if (which === "sidebar") p.sidebar = true;
  else if (which === "config") p.config = true;
  else if (which === "bottom") p.bottom = true;
  applyLayout(p);
  return p;
}

export function wireLayout() {
  state.layout = loadPrefs();
  applyLayout(state.layout);

  if (el.btnCollapseSidebar) {
    el.btnCollapseSidebar.addEventListener("click", function () {
      togglePanel("sidebar");
    });
  }
  if (el.railSidebar) {
    el.railSidebar.addEventListener("click", function () {
      openPanel("sidebar");
    });
  }
  if (el.btnCollapseConfig) {
    el.btnCollapseConfig.addEventListener("click", function () {
      togglePanel("config");
    });
  }
  if (el.railConfig) {
    el.railConfig.addEventListener("click", function () {
      openPanel("config");
    });
  }
  if (el.btnCollapseBottom) {
    el.btnCollapseBottom.addEventListener("click", function () {
      togglePanel("bottom");
    });
  }
  if (el.railBottom) {
    el.railBottom.addEventListener("click", function () {
      openPanel("bottom");
    });
  }
}
