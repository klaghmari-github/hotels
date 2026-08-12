/**
 * Pictogrammes SVG par type de step (F0022 / F0053-S2).
 */
import { escapeHtml } from "./util.js";

/**
 * Pictogrammes SVG par type de step (F0022).
 * viewBox 24x24, stroke currentColor — reutilisable palette / graphe / requires.
 */
export function typeIconPaths(type) {
  // Chemins simples, lisibles a petite taille
  const paths = {
    // Fichier + grille (import dataframe)
    dataframe:
      '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>' +
      '<polyline points="14 2 14 8 20 8"/>' +
      '<path d="M8 13h8M8 17h5M8 9h2"/>',
    // Table grille 2x2
    table:
      '<rect x="3" y="4" width="18" height="16" rx="2"/>' +
      '<path d="M3 10h18M3 16h18M9 4v16M15 4v16"/>',
    // Oeil (vue)
    view:
      '<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/>' +
      '<circle cx="12" cy="12" r="3"/>',
    // Terminal / execution SQL (execute_sql + alias execute)
    execute:
      '<polyline points="4 17 10 11 4 5"/>' +
      '<line x1="12" y1="19" x2="20" y2="19"/>',
    execute_sql:
      '<polyline points="4 17 10 11 4 5"/>' +
      '<line x1="12" y1="19" x2="20" y2="19"/>',
    // Python (serpent stylise + chevrons)
    execute_python:
      '<path d="M12 2c-2 0-3 1-3 3v2h6V5c0-2-1-3-3-3z"/>' +
      '<path d="M9 7H7c-2 0-3 1.5-3 3.5S5 14 7 14h2"/>' +
      '<path d="M15 17h2c2 0 3-1.5 3-3.5S19 10 17 10h-2"/>' +
      '<circle cx="10.5" cy="4.5" r="0.7" fill="currentColor"/>' +
      '<circle cx="13.5" cy="19.5" r="0.7" fill="currentColor"/>' +
      '<path d="M9 17c0 2 1 3 3 3s3-1 3-3v-2H9v2z"/>',
    // F0137: notebook (grille cellules)
    notebook:
      '<rect x="3" y="3" width="18" height="18" rx="2"/>' +
      '<line x1="3" y1="9" x2="21" y2="9"/>' +
      '<line x1="3" y1="15" x2="21" y2="15"/>' +
      '<line x1="9" y1="3" x2="9" y2="21"/>',
    // Shell / terminal
    execute_shell:
      '<rect x="3" y="4" width="18" height="16" rx="2"/>' +
      '<polyline points="7 9 10 12 7 15"/>' +
      '<line x1="12" y1="15" x2="17" y2="15"/>',
    // Boucle iterate (alias legacy iteration)
    iterate:
      '<polyline points="23 4 23 10 17 10"/>' +
      '<polyline points="1 20 1 14 7 14"/>' +
      '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
    iteration:
      '<polyline points="23 4 23 10 17 10"/>' +
      '<polyline points="1 20 1 14 7 14"/>' +
      '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
    // Dossier zone (F0052)
    zone:
      '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
    // F0139: templates auto (meme icone zone)
    flatzone:
      '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>' +
      '<line x1="8" y1="14" x2="16" y2="14"/>',
    allzone:
      '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
    backzone:
      '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>' +
      '<polyline points="14 12 10 12 12 10"/>' +
      '<polyline points="10 12 12 14"/>',
    forzone:
      '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>' +
      '<polyline points="10 12 14 12 12 10"/>' +
      '<polyline points="14 12 12 14"/>',
    bidzone:
      '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>' +
      '<polyline points="9 12 15 12"/>' +
      '<polyline points="11 10 9 12 11 14"/>' +
      '<polyline points="13 10 15 12 13 14"/>',
  };
  return paths[type] || paths.table;
}

export function typeIconSvg(type, opts) {
  const o = opts || {};
  const size = o.size || 20;
  const extra = o.className ? " " + o.className : "";
  const stroke = o.strokeWidth || 1.75;
  return (
    '<svg class="type-icon type-icon-' +
    escapeHtml(type || "table") +
    extra +
    '" width="' +
    size +
    '" height="' +
    size +
    '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="' +
    stroke +
    '" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" data-testid="icon-' +
    escapeHtml(type || "table") +
    '">' +
    typeIconPaths(type) +
    "</svg>"
  );
}

/** Icones SVG natives pour le graphe (meme chemins, groupe transforme). */
export function typeIconSvgGroup(type, x, y, scale) {
  const s = scale || 0.75;
  return (
    '<g class="node-icon type-icon-' +
    escapeHtml(type || "table") +
    '" transform="translate(' +
    x +
    "," +
    y +
    ") scale(" +
    s +
    ')" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">' +
    typeIconPaths(type) +
    "</g>"
  );
}

export function typeColor(type) {
  return (
    {
      table: "#3d8bfd",
      view: "#2dd4bf",
      dataframe: "#a78bfa",
      execute: "#fbbf24",
      execute_sql: "#fbbf24",
      execute_python: "#3776ab",
      notebook: "#f59e0b",
      execute_shell: "#34d399",
      iterate: "#f472b6",
      iteration: "#f472b6",
      zone: "#94a3b8",
      flatzone: "#38bdf8",
      allzone: "#38bdf8",
      backzone: "#a78bfa",
      forzone: "#34d399",
      bidzone: "#f472b6",
    }[type] || "#8b9bb0"
  );
}

export function typeFill(type) {
  return (
    {
      table: "rgba(61,139,253,0.12)",
      view: "rgba(45,212,191,0.12)",
      dataframe: "rgba(167,139,250,0.12)",
      execute: "rgba(251,191,36,0.12)",
      execute_sql: "rgba(251,191,36,0.12)",
      execute_python: "rgba(55,118,171,0.14)",
      notebook: "rgba(245,158,11,0.14)",
      execute_shell: "rgba(52,211,153,0.14)",
      iterate: "rgba(244,114,182,0.12)",
      iteration: "rgba(244,114,182,0.12)",
      zone: "rgba(148,163,184,0.14)",
      flatzone: "rgba(56,189,248,0.14)",
      allzone: "rgba(56,189,248,0.14)",
      backzone: "rgba(167,139,250,0.14)",
      forzone: "rgba(52,211,153,0.14)",
      bidzone: "rgba(244,114,182,0.14)",
    }[type] || "rgba(139,155,176,0.08)"
  );
}
