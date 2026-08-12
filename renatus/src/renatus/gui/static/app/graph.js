/**
 * Graphe SVG, layout, labels (F0053-S2 / F0053-S4 / F0054-S2 / F0106 / F0122).
 * GraphCanvas : methodes reelles; exports fonctionnels = wrappers.
 * F0106: selection → rectangle elargi + croix rouge supprimer.
 * F0122: zoom in/out (Ctrl+molette, boutons, Ctrl+0).
 */
import { state, el } from "./state.js";
import { api, toast } from "./api.js";
import {
  currentZoneStepId,
  getSelectedRequires,
  refreshStepNamesDatalist,
  renderRequiresPicker,
  selectCurrentZone,
  selectStep,
} from "./config.js";
import { typeColor, typeFill, typeIconSvgGroup } from "./icons.js";
import { renderPipelineTabs, switchTab } from "./tabs.js";
import { UiController } from "./ui-base.js";
import { escapeHtml } from "./util.js";

/** Largeur noeud standard (label + logo). */
const NODE_W = 156;
/** Extension droite pour la croix supprimer (F0106). */
const NODE_DEL_EXTRA = 24;
/** Hauteur noeud (F0094). */
const NODE_H = 44;
/** F0135: espacement layout (doit matcher layoutNodes). */
const LAYOUT_X0 = 40;
const LAYOUT_Y0 = 36;
const LAYOUT_DX = 200;
const LAYOUT_DY = 68;
/** Marge anti-collision liens / boites noeuds. */
const EDGE_PAD = 4;
/** Degagement min apres/avant un noeud pour un couloir vertical. */
const EDGE_EXIT = 14;

/** F0122: bornes zoom graphe Flux */
export const GRAPH_ZOOM_MIN = 0.25;
export const GRAPH_ZOOM_MAX = 3;
export const GRAPH_ZOOM_STEP = 0.1;
export const GRAPH_ZOOM_DEFAULT = 1;

/**
 * F0106: le noeud selectionne peut afficher la croix supprimer.
 * Pas pour main (protege), noeuds externes, lecture seule.
 */
function nodeCanShowDelete(n) {
  if (!n || !n.id) return false;
  if (n.external) return false;
  if (n.id === "default") return false;
  if (state.workspace && state.workspace.read_only) return false;
  return state.selected === n.id;
}

function nodeVisualWidth(n) {
  return nodeCanShowDelete(n) ? NODE_W + NODE_DEL_EXTRA : NODE_W;
}

/* ========== F0135: routage orthogonal (H/V, sans traverser les noeuds) ========== */

/**
 * Boites obstacle des noeuds (coordonnees canvas).
 * @returns {Array<{id:string,x:number,y:number,w:number,h:number}>}
 */
export function buildNodeBoxes(nodes, pos, byId) {
  const boxes = [];
  (nodes || []).forEach(function (n) {
    if (!n || !n.id) return;
    const p = pos[n.id];
    if (!p) return;
    const w = nodeVisualWidth(byId && byId[n.id] ? byId[n.id] : n);
    boxes.push({
      id: n.id,
      x: p.x,
      y: p.y,
      w: w,
      h: NODE_H,
    });
  });
  return boxes;
}

/**
 * Segment strictement horizontal ou vertical intersecte-t-il une boite ?
 * (padding EDGE_PAD). Extremites sur le bord du noeud source/cible ok.
 */
export function segmentHitsBox(x1, y1, x2, y2, box, pad) {
  const p = pad == null ? EDGE_PAD : pad;
  const left = box.x - p;
  const right = box.x + box.w + p;
  const top = box.y - p;
  const bottom = box.y + box.h + p;
  // horizontal
  if (Math.abs(y1 - y2) < 0.5) {
    const y = y1;
    if (y <= top || y >= bottom) return false;
    const minX = Math.min(x1, x2);
    const maxX = Math.max(x1, x2);
    return maxX > left && minX < right;
  }
  // vertical
  if (Math.abs(x1 - x2) < 0.5) {
    const x = x1;
    if (x <= left || x >= right) return false;
    const minY = Math.min(y1, y2);
    const maxY = Math.max(y1, y2);
    return maxY > top && minY < bottom;
  }
  // non ortho = invalide → considere collision
  return true;
}

/**
 * Un chemin (liste de points) traverse-t-il un noeud hors skipIds ?
 */
export function pathHitsNodes(points, boxes, skipIds) {
  const skip = skipIds || {};
  if (!points || points.length < 2) return false;
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i];
    const b = points[i + 1];
    for (let j = 0; j < (boxes || []).length; j++) {
      const box = boxes[j];
      if (!box || skip[box.id]) continue;
      // Ne pas compter un segment qui ne fait que quitter/entrer le bord
      // du noeud source/cible: skip deja. Les autres boites = collision.
      if (segmentHitsBox(a[0], a[1], b[0], b[1], box, EDGE_PAD)) {
        return true;
      }
    }
  }
  return false;
}

/** Simplifie colineaires et dedup points consecutifs. */
export function simplifyOrthoPoints(points) {
  if (!points || !points.length) return [];
  const out = [[points[0][0], points[0][1]]];
  for (let i = 1; i < points.length; i++) {
    const p = points[i];
    const prev = out[out.length - 1];
    if (Math.abs(p[0] - prev[0]) < 0.5 && Math.abs(p[1] - prev[1]) < 0.5) {
      continue;
    }
    out.push([p[0], p[1]]);
  }
  // fusion colineaire
  const flat = [out[0]];
  for (let i = 1; i < out.length - 1; i++) {
    const a = flat[flat.length - 1];
    const b = out[i];
    const c = out[i + 1];
    const colH =
      Math.abs(a[1] - b[1]) < 0.5 && Math.abs(b[1] - c[1]) < 0.5;
    const colV =
      Math.abs(a[0] - b[0]) < 0.5 && Math.abs(b[0] - c[0]) < 0.5;
    if (colH || colV) continue;
    flat.push(b);
  }
  if (out.length > 1) flat.push(out[out.length - 1]);
  return flat;
}

export function pointsToSvgPath(points) {
  const pts = simplifyOrthoPoints(points);
  if (!pts.length) return "";
  let d = "M" + pts[0][0] + "," + pts[0][1];
  for (let i = 1; i < pts.length; i++) {
    d += " L" + pts[i][0] + "," + pts[i][1];
  }
  return d;
}

/**
 * Couloirs X (gutters entre colonnes) a partir des boites.
 */
function verticalChannels(boxes) {
  const xs = {};
  (boxes || []).forEach(function (b) {
    // centre du gutter a droite de chaque colonne
    const right = b.x + b.w;
    const mid = right + (LAYOUT_DX - NODE_W) / 2;
    const key = String(Math.round(mid));
    xs[key] = mid;
    // gutter a gauche
    const leftMid = b.x - (LAYOUT_DX - NODE_W) / 2;
    if (leftMid > 8) xs[String(Math.round(leftMid))] = leftMid;
  });
  return Object.keys(xs)
    .map(Number)
    .sort(function (a, b) {
      return a - b;
    })
    .map(function (k) {
      return xs[String(k)];
    });
}

function horizontalLanes(boxes) {
  const ys = {};
  (boxes || []).forEach(function (b) {
    const mid = b.y + b.h / 2;
    ys[String(Math.round(mid))] = mid;
    // couloir au-dessus / en-dessous des rangees
    const above = b.y - Math.max(8, (LAYOUT_DY - NODE_H) / 2);
    const below = b.y + b.h + Math.max(8, (LAYOUT_DY - NODE_H) / 2);
    ys[String(Math.round(above))] = above;
    ys[String(Math.round(below))] = below;
  });
  return Object.keys(ys)
    .map(Number)
    .sort(function (a, b) {
      return a - b;
    })
    .map(function (k) {
      return ys[String(k)];
    });
}

/**
 * F0135: calcule un chemin orthogonal source → cible.
 * Segments uniquement horizontaux ou verticaux ; evite de traverser
 * les boites des autres composants.
 *
 * @returns {{ points: number[][], d: string }}
 */
export function routeOrthogonalEdge(opts) {
  const o = opts || {};
  const ax = o.ax;
  const ay = o.ay;
  const fromW = o.fromW != null ? o.fromW : NODE_W;
  const bx = o.bx;
  const by = o.by;
  const boxes = o.boxes || [];
  const fromId = o.fromId;
  const toId = o.toId;
  const skip = {};
  if (fromId) skip[fromId] = true;
  if (toId) skip[toId] = true;

  const sx = ax + fromW;
  const sy = ay + NODE_H / 2;
  const tx = bx;
  const ty = by + NODE_H / 2;

  const channelUse = o.channelUse || {};
  const edgeIndex = o.edgeIndex || 0;
  // demelage deterministe entre aretes (pas de conso a l essai)
  const fan = ((edgeIndex % 7) - 3) * 3;

  function tryPath(points) {
    const pts = simplifyOrthoPoints(points);
    if (pts.length < 2) return null;
    // segments non-ortho rejetes
    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i];
      const b = pts[i + 1];
      const ortho =
        Math.abs(a[0] - b[0]) < 0.5 || Math.abs(a[1] - b[1]) < 0.5;
      if (!ortho) return null;
    }
    if (pathHitsNodes(pts, boxes, skip)) return null;
    return pts;
  }

  const candidates = [];

  // 1) ligne droite horizontale (meme rangee)
  if (Math.abs(sy - ty) < 1) {
    candidates.push([
      [sx, sy],
      [tx, ty],
    ]);
  }

  // 2) H-V-H classique (couloir vertical entre source et cible)
  const midBase = (sx + tx) / 2;
  const midXs = [
    sx + EDGE_EXIT,
    midBase,
    tx - EDGE_EXIT,
    sx + (tx - sx) * 0.25,
    sx + (tx - sx) * 0.75,
  ];
  // gutters colonnes
  verticalChannels(boxes).forEach(function (cx) {
    if (cx > sx + 4 && cx < tx - 4) midXs.push(cx);
  });
  midXs.forEach(function (mx0) {
    const mx = mx0 + fan;
    candidates.push([
      [sx, sy],
      [mx, sy],
      [mx, ty],
      [tx, ty],
    ]);
  });

  // 3) contournement haut / bas (H-V-H-V-H)
  let minY = sy;
  let maxY = sy;
  boxes.forEach(function (b) {
    if (skip[b.id]) return;
    // ne considere que les boites entre sx et tx
    if (b.x + b.w < sx - 2 || b.x > tx + 2) return;
    minY = Math.min(minY, b.y);
    maxY = Math.max(maxY, b.y + b.h);
  });
  const topY = minY - 18;
  const botY = maxY + 18;
  [topY, botY].forEach(function (railY0) {
    const railY = railY0 + fan;
    const xOut = sx + EDGE_EXIT;
    const xIn = tx - EDGE_EXIT;
    candidates.push([
      [sx, sy],
      [xOut, sy],
      [xOut, railY],
      [xIn, railY],
      [xIn, ty],
      [tx, ty],
    ]);
  });

  // 4) lanes horizontales connues (entre rangees)
  horizontalLanes(boxes).forEach(function (hy) {
    if (Math.abs(hy - sy) < 2 || Math.abs(hy - ty) < 2) return;
    const xOut = sx + EDGE_EXIT;
    const xIn = Math.max(xOut + 8, tx - EDGE_EXIT);
    candidates.push([
      [sx, sy],
      [xOut, sy],
      [xOut, hy + fan],
      [xIn, hy + fan],
      [xIn, ty],
      [tx, ty],
    ]);
  });

  // 5) sortie longue puis rail (si cible a gauche — rare)
  if (tx <= sx) {
    const around = Math.max(sx, tx) + 40 + Math.abs(fan);
    candidates.push([
      [sx, sy],
      [around, sy],
      [around, ty],
      [tx, ty],
    ]);
  }

  for (let i = 0; i < candidates.length; i++) {
    const ok = tryPath(candidates[i]);
    if (ok) {
      // compteur optionnel (stats / debug)
      const key = "ok";
      channelUse[key] = (channelUse[key] || 0) + 1;
      return { points: ok, d: pointsToSvgPath(ok) };
    }
  }

  // Fallback: H-V-H simple meme si collision (mieux que courbe)
  const fb = simplifyOrthoPoints([
    [sx, sy],
    [(sx + tx) / 2, sy],
    [(sx + tx) / 2, ty],
    [tx, ty],
  ]);
  return { points: fb, d: pointsToSvgPath(fb) };
}

/**
 * Controleur graphe — layout + rendu SVG (F0054-S2 thick).
 */
export class GraphCanvas extends UiController {
  constructor(root) {
    super(root || (el && el.graphCanvas) || null);
  }

  /**
   * Layout DAG simple par profondeur de dependances.
   * @param {Array} nodes
   * @param {Array} edges
   * @returns {Object.<string,{x:number,y:number}>}
   */
  layoutNodes(nodes, edges) {
    const ids = new Set(nodes.map(function (n) { return n.id; }));
    const deps = {};
    nodes.forEach(function (n) { deps[n.id] = []; });
    edges.forEach(function (e) {
      const from = e.from || e.from_;
      const to = e.to;
      if (ids.has(to) && ids.has(from)) deps[to].push(from);
    });
    const depth = {};
    function d(id, stack) {
      if (depth[id] !== undefined) return depth[id];
      if (stack.has(id)) return 0;
      stack.add(id);
      let m = 0;
      (deps[id] || []).forEach(function (p) {
        m = Math.max(m, d(p, stack) + 1);
      });
      stack.delete(id);
      depth[id] = m;
      return m;
    }
    nodes.forEach(function (n) { d(n.id, new Set()); });
    const cols = {};
    nodes.forEach(function (n) {
      const k = depth[n.id] || 0;
      if (!cols[k]) cols[k] = [];
      cols[k].push(n.id);
    });
    const pos = {};
    // F0094 / F0135: grilles alignees pour routage orthogonal
    const x0 = LAYOUT_X0,
      y0 = LAYOUT_Y0,
      dx = LAYOUT_DX,
      dy = LAYOUT_DY;
    Object.keys(cols)
      .map(Number)
      .sort(function (a, b) { return a - b; })
      .forEach(function (k) {
        cols[k].forEach(function (id, i) {
          pos[id] = { x: x0 + k * dx, y: y0 + i * dy };
        });
      });
    return pos;
  }

  /**
   * Tronque un libelle pour tenir dans une largeur SVG (F0037).
   */
  truncateNodeText(text, maxPx, fontSize) {
    const s = String(text == null ? "" : text);
    if (!s) return "";
    const fs = fontSize || 11.5;
    const avg = fs * 0.56;
    const maxChars = Math.max(4, Math.floor(maxPx / avg));
    if (s.length <= maxChars) return s;
    if (maxChars <= 1) return "…";
    return s.slice(0, maxChars - 1) + "…";
  }

  /** Dessine le SVG du graphe courant. */
  renderGraph() {
    const nodes = state.graph.nodes || [];
    const edges = state.graph.edges || [];
    // A0009: plus de message "Pipeline vide" (le CSS display:flex
    // ecrasait [hidden] et restait visible par-dessus les noeuds).
    if (el.graphEmpty) el.graphEmpty.hidden = true;
    if (!nodes.length) {
      el.graphCanvas.innerHTML = "";
      return;
    }
    const pos = this.layoutNodes(nodes, edges);
    const nodeH = NODE_H;
    // zone texte: apres icone (x=46) jusqu'au bord utile (avant croix)
    const textX = 46;
    const textMaxW = NODE_W - textX - 10;
    // baseline verticale centree (font ~11.5px)
    const labelY = Math.round(nodeH / 2 + 4);
    const byId = {};
    nodes.forEach(function (n) {
      if (n && n.id) byId[n.id] = n;
    });
    // F0135: boites obstacle pour routage orthogonal
    const boxes = buildNodeBoxes(nodes, pos, byId);
    let maxX = 200, maxY = 160;
    nodes.forEach(function (n) {
      const p = pos[n.id] || { x: 40, y: 40 };
      maxX = Math.max(maxX, p.x + nodeVisualWidth(n) + 30);
      maxY = Math.max(maxY, p.y + nodeH + 30);
    });
    // Prefixe edges (chemins) pour etendre le canvas si contournement
    const edgePaths = [];
    const channelUse = {};
    edges.forEach(function (e, idx) {
      const from = e.from || e.from_;
      const to = e.to;
      const a = pos[from];
      const b = pos[to];
      if (!a || !b) return;
      const fromNode = byId[from];
      const toNode = byId[to];
      const fromW = fromNode ? nodeVisualWidth(fromNode) : NODE_W;
      const route = routeOrthogonalEdge({
        fromId: from,
        toId: to,
        ax: a.x,
        ay: a.y,
        fromW: fromW,
        bx: b.x,
        by: b.y,
        boxes: boxes,
        edgeIndex: idx,
        channelUse: channelUse,
      });
      edgePaths.push(route);
      route.points.forEach(function (pt) {
        maxX = Math.max(maxX, pt[0] + 24);
        maxY = Math.max(maxY, pt[1] + 24);
      });
    });
    // F0122: dimensions de base + zoom (viewBox fixe, size affichee * z)
    state.graphLayoutBase = { w: maxX, h: maxY };
    const z = clampGraphZoom(state.graphZoom);
    state.graphZoom = z;
    const dispW = Math.max(1, Math.round(maxX * z));
    const dispH = Math.max(1, Math.round(maxY * z));
    let svg =
      '<svg class="graph-svg" width="' +
      dispW +
      '" height="' +
      dispH +
      '" viewBox="0 0 ' +
      maxX +
      " " +
      maxY +
      '" data-base-w="' +
      maxX +
      '" data-base-h="' +
      maxY +
      '" data-zoom="' +
      z +
      '"><defs>' +
      '<marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">' +
      '<path d="M0,0 L6,3 L0,6 Z" fill="#4b5d78"/></marker>' +
      // clip: le texte ne depasse jamais la zone label (avant croix)
      '<clipPath id="node-text-clip">' +
      '<rect x="' +
      textX +
      '" y="2" width="' +
      textMaxW +
      '" height="' +
      (nodeH - 4) +
      '"/>' +
      "</clipPath>" +
      "</defs>";
    // F0135: liens orthogonaux (H/V uniquement), sous les noeuds
    edgePaths.forEach(function (route) {
      if (!route || !route.d) return;
      svg +=
        '<path class="edge" data-testid="edge-ortho" d="' + route.d + '"/>';
    });
    const self = this;
    nodes.forEach(function (n) {
      const p = pos[n.id] || { x: 40, y: 40 };
      const showDel = nodeCanShowDelete(n);
      const nodeW = nodeVisualWidth(n);
      const sel = state.selected === n.id ? " selected" : "";
      const isExt = !!n.external;
      const c = typeColor(n.type);
      const fill = typeFill(n.type);
      const type = n.type || "table";
      const fullName = n.label || n.id || "";
      // F0094: detail type/SQL seulement dans le tooltip (pas sous le label)
      const relSql = n.relation_name || "";
      const tipDetail =
        (relSql && relSql !== fullName ? "SQL " + relSql + " · " : "") +
        type +
        (n.mode ? " · " + n.mode : "") +
        (isExt && n.tab ? " · " + n.tab : "");
      const shortName = self.truncateNodeText(fullName, textMaxW, 12);
      // Picto a gauche + label seul (tronque + clip SVG)
      // external = require d un autre onglet (F0039)
      const iconY = Math.round((nodeH - 32) / 2);
      const iconGlyphY = iconY + 4;
      let delSvg = "";
      if (showDel) {
        // F0106: croix rouge dans l extension du rectangle
        const delBox = 20;
        const delX = NODE_W + Math.round((NODE_DEL_EXTRA - delBox) / 2) - 2;
        const delY = Math.round((nodeH - delBox) / 2);
        delSvg =
          '<g class="node-delete-hit" data-testid="node-delete-' +
          escapeHtml(n.id) +
          '" transform="translate(' +
          delX +
          "," +
          delY +
          ')">' +
          "<title>Supprimer</title>" +
          '<rect class="node-delete-bg" width="' +
          delBox +
          '" height="' +
          delBox +
          '" rx="5"/>' +
          '<path class="node-delete-x" d="M6 6 L14 14 M14 6 L6 14"/>' +
          "</g>";
      }
      svg +=
        '<g class="node node-' +
        escapeHtml(type) +
        sel +
        (showDel ? " has-delete" : "") +
        (isExt ? " node-external" : "") +
        '" data-id="' +
        escapeHtml(n.id) +
        '" data-external="' +
        (isExt ? "1" : "0") +
        '" data-testid="node-' +
        escapeHtml(n.id) +
        '" transform="translate(' +
        p.x +
        "," +
        p.y +
        ')">' +
        "<title>" +
        escapeHtml(
          fullName +
            (tipDetail ? " — " + tipDetail : "") +
            (isExt ? " (autre onglet — require)" : "")
        ) +
        "</title>" +
        '<rect class="node-bg" width="' +
        nodeW +
        '" height="' +
        nodeH +
        '" style="stroke:' +
        c +
        ";fill:" +
        fill +
        (isExt ? ";stroke-dasharray:4 3;opacity:0.85" : "") +
        '"/>' +
        '<rect class="node-icon-bg" x="6" y="' +
        iconY +
        '" width="32" height="32" rx="7" style="fill:' +
        c +
        ';opacity:0.18"/>' +
        typeIconSvgGroup(type, 10, iconGlyphY, 0.85) +
        '<g class="node-text" clip-path="url(#node-text-clip)">' +
        '<text class="nname" x="' +
        textX +
        '" y="' +
        labelY +
        '">' +
        escapeHtml(shortName) +
        "</text></g>" +
        delSvg +
        "</g>";
    });
    svg += "</svg>";
    el.graphCanvas.innerHTML = svg;
    // F0099: clic fond canvas (une seule fois) → zone courante
    wireGraphBackgroundSelect();
    // Couleur stroke des icones = couleur du type
    el.graphCanvas.querySelectorAll(".node").forEach(function (g) {
      const id = g.getAttribute("data-id");
      const node = nodes.find(function (n) { return n.id === id; });
      const icon = g.querySelector(".node-icon");
      if (icon && node) {
        icon.style.color = typeColor(node.type);
        icon.setAttribute("stroke", typeColor(node.type));
      }
      g.addEventListener("click", function (ev) {
        // ne pas propager au fond (sinon reselectionne la zone)
        ev.stopPropagation();
        // F0106: croix rouge → meme flux que Delete / btn supprimer
        const delHit =
          ev.target &&
          ev.target.closest &&
          ev.target.closest(".node-delete-hit");
        if (delHit) {
          ev.preventDefault();
          const sid = g.getAttribute("data-id");
          // import dynamique pour eviter cycle graph ↔ step-crud
          import("./config/step-crud.js").then(function (mod) {
            const run = function () {
              return mod.deleteStep();
            };
            if (sid && sid !== state.selected) {
              return selectStep(sid).then(run);
            }
            return run();
          });
          return;
        }
        selectStep(g.getAttribute("data-id"));
      });
      // F0052 / F0131: double-clic zone / auto-zone → ouvrir vue contenu
      g.addEventListener("dblclick", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (!node) return;
        const t = node.type || "";
        const isAuto =
          t === "allzone" ||
          t === "backzone" ||
          t === "forzone" ||
          t === "bidzone";
        if (t !== "zone" && !isAuto) return;
        // auto-zone: zone_path = id (vue logique, pas dossier auto/)
        const zpath = node.zone_path || node.id;
        openZoneTab(zpath);
      });
    });
    // F0118: re-applique les classes de progression apres redraw
    applyBuildProgressClasses();
    // F0127: grise hors lineage requires (si pas en build zone)
    applyLineageHighlight();
    // F0122: label zoom + listeners (idempotent)
    updateGraphZoomLabel();
    wireGraphZoom();
  }

  render() {
    this.renderGraph();
    return this;
  }

  async refresh() {
    return refreshGraph();
  }

  async openZone(zonePath) {
    return openZoneTab(zonePath);
  }
}

/** Instance module partagee (wrappers + GuiApp). */
export const graphCanvas = new GraphCanvas();

/** F0099: un seul listener fond (innerHTML re-render ne le detruit pas si sur parent). */
let _graphBgWired = false;

/**
 * Clic sur un endroit libre du canvas Flux → Config de la zone courante.
 */
export function wireGraphBackgroundSelect() {
  if (!el.graphCanvas || _graphBgWired) return;
  _graphBgWired = true;
  el.graphCanvas.addEventListener("click", function (ev) {
    // clic sur un noeud (ou enfant) ignore — stopPropagation sur .node
    const t = ev.target;
    if (t && t.closest && t.closest(".node")) return;
    // fond / svg / vide
    selectCurrentZone();
  });
}

export function layoutNodes(nodes, edges) {
  return graphCanvas.layoutNodes(nodes, edges);
}

/**
 * Tronque un libelle pour tenir dans une largeur SVG (F0037).
 * Approximation largeur caractere (font UI ~0.55em).
 */
export function truncateNodeText(text, maxPx, fontSize) {
  return graphCanvas.truncateNodeText(text, maxPx, fontSize);
}

export function renderGraph() {
  return graphCanvas.renderGraph();
}

/** F0122: borne le facteur de zoom. */
export function clampGraphZoom(z) {
  const n = Number(z);
  if (!isFinite(n) || n <= 0) return GRAPH_ZOOM_DEFAULT;
  return Math.min(GRAPH_ZOOM_MAX, Math.max(GRAPH_ZOOM_MIN, n));
}

/** F0122: affiche le % dans le bouton reset. */
export function updateGraphZoomLabel() {
  const z = clampGraphZoom(state.graphZoom);
  const pct = Math.round(z * 100) + "%";
  if (el.graphZoomLabel) el.graphZoomLabel.textContent = pct;
  if (el.btnGraphZoomReset) {
    el.btnGraphZoomReset.setAttribute("title", "Réinitialiser le zoom (" + pct + " → 100%, Ctrl+0)");
  }
  const svg = el.graphCanvas && el.graphCanvas.querySelector(".graph-svg");
  if (svg) svg.setAttribute("data-zoom", String(z));
}

/**
 * F0122: applique le zoom au SVG existant (sans re-layout complet).
 * @param {number} nextZoom
 * @param {{clientX?:number, clientY?:number}|null} [pivot] point ecran pour zoom vers curseur
 */
export function setGraphZoom(nextZoom, pivot) {
  const canvas = el.graphCanvas;
  const oldZ = clampGraphZoom(state.graphZoom);
  const z = clampGraphZoom(nextZoom);
  if (Math.abs(z - oldZ) < 0.0001) {
    updateGraphZoomLabel();
    return z;
  }

  let relX = 0;
  let relY = 0;
  let contentX = 0;
  let contentY = 0;
  if (canvas && pivot && pivot.clientX != null) {
    const rect = canvas.getBoundingClientRect();
    relX = pivot.clientX - rect.left;
    relY = pivot.clientY - rect.top;
    contentX = (canvas.scrollLeft + relX) / oldZ;
    contentY = (canvas.scrollTop + relY) / oldZ;
  }

  state.graphZoom = z;

  const svg = canvas && canvas.querySelector(".graph-svg");
  const base = state.graphLayoutBase;
  let baseW = base && base.w;
  let baseH = base && base.h;
  if (svg) {
    if (!baseW) baseW = Number(svg.getAttribute("data-base-w")) || 0;
    if (!baseH) baseH = Number(svg.getAttribute("data-base-h")) || 0;
  }
  if (svg && baseW > 0 && baseH > 0) {
    const dispW = Math.max(1, Math.round(baseW * z));
    const dispH = Math.max(1, Math.round(baseH * z));
    svg.setAttribute("width", String(dispW));
    svg.setAttribute("height", String(dispH));
    svg.setAttribute("viewBox", "0 0 " + baseW + " " + baseH);
    svg.setAttribute("data-base-w", String(baseW));
    svg.setAttribute("data-base-h", String(baseH));
    svg.setAttribute("data-zoom", String(z));
  }

  updateGraphZoomLabel();

  // garder le point sous le curseur stable
  if (canvas && pivot && pivot.clientX != null) {
    canvas.scrollLeft = Math.max(0, contentX * z - relX);
    canvas.scrollTop = Math.max(0, contentY * z - relY);
  }
  return z;
}

export function zoomGraphIn(step) {
  const s = step != null ? step : GRAPH_ZOOM_STEP;
  return setGraphZoom(clampGraphZoom(state.graphZoom) + s);
}

export function zoomGraphOut(step) {
  const s = step != null ? step : GRAPH_ZOOM_STEP;
  return setGraphZoom(clampGraphZoom(state.graphZoom) - s);
}

export function resetGraphZoom() {
  return setGraphZoom(GRAPH_ZOOM_DEFAULT);
}

let _graphZoomWired = false;

/**
 * F0122: molette Ctrl/Meta + boutons + raccourcis clavier.
 */
export function wireGraphZoom() {
  if (_graphZoomWired) return;
  _graphZoomWired = true;

  if (el.btnGraphZoomIn) {
    el.btnGraphZoomIn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      zoomGraphIn();
    });
  }
  if (el.btnGraphZoomOut) {
    el.btnGraphZoomOut.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      zoomGraphOut();
    });
  }
  if (el.btnGraphZoomReset) {
    el.btnGraphZoomReset.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      resetGraphZoom();
    });
  }

  if (el.graphCanvas) {
    el.graphCanvas.addEventListener(
      "wheel",
      function (ev) {
        // Ctrl (Windows/Linux) ou Meta (trackpad pinch souvent + Ctrl sur Chrome)
        if (!ev.ctrlKey && !ev.metaKey) return;
        ev.preventDefault();
        // deltaY > 0 = zoom out
        const direction = ev.deltaY > 0 ? -1 : 1;
        // pas plus fin avec deltaMode / trackpad
        const intensity =
          Math.abs(ev.deltaY) > 40 ? GRAPH_ZOOM_STEP * 1.5 : GRAPH_ZOOM_STEP;
        const next = clampGraphZoom(state.graphZoom) + direction * intensity;
        setGraphZoom(next, { clientX: ev.clientX, clientY: ev.clientY });
      },
      { passive: false }
    );
  }

  // Raccourcis globaux quand focus dans la page (pas dans input/textarea)
  document.addEventListener("keydown", function (ev) {
    const t = ev.target;
    if (
      t &&
      (t.tagName === "INPUT" ||
        t.tagName === "TEXTAREA" ||
        t.tagName === "SELECT" ||
        t.isContentEditable)
    ) {
      return;
    }
    if (!(ev.ctrlKey || ev.metaKey)) return;
    // Ctrl+0 reset ; Ctrl+= / Ctrl++ zoom in ; Ctrl+- zoom out
    if (ev.key === "0") {
      ev.preventDefault();
      resetGraphZoom();
      return;
    }
    if (ev.key === "=" || ev.key === "+") {
      ev.preventDefault();
      zoomGraphIn();
      return;
    }
    if (ev.key === "-" || ev.key === "_") {
      ev.preventDefault();
      zoomGraphOut();
    }
  });

  updateGraphZoomLabel();
}

/**
 * F0127 / F0134: type step pour un id (catalogue ou graphe).
 * @param {string} sid
 * @returns {string}
 */
function stepTypeOf(sid) {
  const id = String(sid || "");
  if (!id) return "";
  const lists = [
    (state.graph && state.graph.nodes) || [],
    state.allSteps || [],
  ];
  for (let i = 0; i < lists.length; i++) {
    const list = lists[i];
    for (let j = 0; j < list.length; j++) {
      const n = list[j];
      if (n && n.id === id && n.type) return String(n.type);
    }
  }
  return "";
}

/**
 * F0134: selection = zone / auto-zone → pas de grise lineage.
 * (La zone n est souvent pas un noeud du graphe de ses membres :
 *  computeLineageSet ne garde que l id zone → tous les membres grises.)
 * @param {string|null} selectedId
 * @returns {boolean}
 */
export function selectionIsZoneLike(selectedId) {
  const sid = selectedId != null ? String(selectedId) : "";
  if (!sid) return false;
  const t = stepTypeOf(sid);
  if (
    t === "zone" ||
    t === "allzone" ||
    t === "backzone" ||
    t === "forzone" ||
    t === "bidzone"
  ) {
    return true;
  }
  // zone courante de l onglet (meme absente du graphe / catalogue incomplet)
  try {
    if (currentZoneStepId(state.activeTab || "default") === sid) return true;
  } catch (_) {
    /* ignore */
  }
  // tab = id zone (auto-vue ou chemin se terminant par sid)
  const tab = String(state.activeTab || "");
  if (tab === sid) return true;
  if (tab.split("/").filter(Boolean).pop() === sid) return true;
  return false;
}

/**
 * F0127: ensemble lineage = selection + requires recursifs (amont).
 * Utilise state.graph.edges (from=dep, to=consumer) et requires des nodes.
 * @param {string|null} selectedId
 * @returns {Object.<string, boolean>} set-like
 */
export function computeLineageSet(selectedId) {
  const out = {};
  const sid = selectedId != null ? String(selectedId) : "";
  if (!sid) return out;
  // F0134: zone → tous les noeuds du graphe courant (membres actifs)
  if (selectionIsZoneLike(sid)) {
    const nodes = (state.graph && state.graph.nodes) || [];
    nodes.forEach(function (n) {
      if (n && n.id && !n.external) out[n.id] = true;
    });
    out[sid] = true;
    return out;
  }
  out[sid] = true;

  // index: consumer → [deps]
  const depsOf = {};
  const edges = (state.graph && state.graph.edges) || [];
  edges.forEach(function (e) {
    if (!e) return;
    const from = e.from || e.from_;
    const to = e.to;
    if (!from || !to) return;
    if (!depsOf[to]) depsOf[to] = [];
    depsOf[to].push(String(from));
  });
  // complete avec requires des nodes (catalogue / graphe)
  const nodes = (state.graph && state.graph.nodes) || [];
  const allSteps = state.allSteps || [];
  function addReqsFromList(list) {
    (list || []).forEach(function (n) {
      if (!n || !n.id) return;
      const reqs = n.requires;
      if (!Array.isArray(reqs) || !reqs.length) return;
      if (!depsOf[n.id]) depsOf[n.id] = [];
      reqs.forEach(function (r) {
        const id = String(r);
        if (depsOf[n.id].indexOf(id) < 0) depsOf[n.id].push(id);
      });
    });
  }
  addReqsFromList(nodes);
  addReqsFromList(allSteps);

  const stack = [sid];
  const seen = {};
  seen[sid] = true;
  while (stack.length) {
    const cur = stack.pop();
    const deps = depsOf[cur] || [];
    for (let i = 0; i < deps.length; i++) {
      const d = deps[i];
      if (seen[d]) continue;
      seen[d] = true;
      out[d] = true;
      stack.push(d);
    }
  }
  return out;
}

/**
 * F0127 / F0134: grise les noeuds / aretes hors lineage du composant selectionne.
 * Si la selection est une **zone** (ou auto-zone), tous les composants
 * affiches restent actifs (pas de grise).
 * Pendant un zoneBuild, laisse applyBuildProgressClasses prioritaire.
 */
export function applyLineageHighlight() {
  if (!el.graphCanvas) return;
  // ne pas combiner avec la progression Renatus zone
  if (state.zoneBuild) {
    el.graphCanvas.querySelectorAll(".node.lineage-dim").forEach(function (g) {
      g.classList.remove("lineage-dim", "lineage-focus");
    });
    el.graphCanvas.querySelectorAll(".edge.lineage-dim").forEach(function (e) {
      e.classList.remove("lineage-dim", "lineage-focus");
    });
    return;
  }
  const sid = state.selected;
  const nodes = el.graphCanvas.querySelectorAll(".node");
  const edges = el.graphCanvas.querySelectorAll(".edge");
  function clearAll() {
    nodes.forEach(function (g) {
      g.classList.remove("lineage-dim", "lineage-focus");
    });
    edges.forEach(function (e) {
      e.classList.remove("lineage-dim", "lineage-focus");
    });
  }
  if (!sid) {
    clearAll();
    return;
  }
  // F0134: zone selectionnee → tous les membres actifs (pas de dim)
  if (selectionIsZoneLike(sid)) {
    clearAll();
    return;
  }
  const lin = computeLineageSet(sid);
  nodes.forEach(function (g) {
    const id = g.getAttribute("data-id");
    g.classList.remove("lineage-dim", "lineage-focus");
    if (!id) return;
    if (lin[id]) {
      g.classList.add("lineage-focus");
    } else {
      g.classList.add("lineage-dim");
    }
  });
  // aretes: focus si les deux bouts sont dans le lineage
  // (edges SVG n ont pas data-from/to — recalcule depuis state)
  const edgeList = (state.graph && state.graph.edges) || [];
  const edgeEls = el.graphCanvas.querySelectorAll("path.edge");
  // ordre de rendu = ordre de state.graph.edges
  edgeEls.forEach(function (path, idx) {
    path.classList.remove("lineage-dim", "lineage-focus");
    const e = edgeList[idx];
    if (!e) {
      path.classList.add("lineage-dim");
      return;
    }
    const from = String(e.from || e.from_ || "");
    const to = String(e.to || "");
    if (lin[from] && lin[to]) {
      path.classList.add("lineage-focus");
    } else {
      path.classList.add("lineage-dim");
    }
  });
}

/**
 * F0118: classes CSS des noeuds pendant Renatus zone.
 * pending=gris, running=contour lumineux, done=actif lumineux,
 * idle=actif sans glow (hors plan).
 */
export function applyBuildProgressClasses() {
  if (!el.graphCanvas) return;
  const zb = state.zoneBuild;
  const nodes = el.graphCanvas.querySelectorAll(".node");
  if (!zb) {
    nodes.forEach(function (g) {
      g.classList.remove(
        "build-pending",
        "build-running",
        "build-done",
        "build-idle"
      );
    });
    return;
  }
  const jobSet = {};
  (zb.jobIds || []).forEach(function (id) {
    jobSet[id] = true;
  });
  const doneSet = {};
  (zb.done || []).forEach(function (id) {
    doneSet[id] = true;
  });
  const current = zb.current || null;
  nodes.forEach(function (g) {
    const id = g.getAttribute("data-id");
    g.classList.remove(
      "build-pending",
      "build-running",
      "build-done",
      "build-idle"
    );
    if (!id || !jobSet[id]) {
      g.classList.add("build-idle");
    } else if (current === id) {
      g.classList.add("build-running");
    } else if (doneSet[id]) {
      g.classList.add("build-done");
    } else {
      g.classList.add("build-pending");
    }
  });
}

/**
 * F0118: barre de progression globale (composants restants).
 */
export function updateBuildProgressBar() {
  const bar = el.buildProgress;
  const fill = el.buildProgressFill;
  const label = el.buildProgressLabel;
  if (!bar) return;
  const zb = state.zoneBuild;
  if (!zb) {
    bar.hidden = true;
    if (fill) fill.style.width = "0%";
    if (label) label.textContent = "";
    bar.setAttribute("aria-valuenow", "0");
    return;
  }
  const total = Math.max(0, Number(zb.total) || 0);
  const completed = Math.max(0, Number(zb.completed) || 0);
  const remaining = Math.max(0, total - completed);
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  bar.hidden = false;
  bar.setAttribute("aria-valuenow", String(pct));
  bar.setAttribute("aria-valuemax", "100");
  if (fill) fill.style.width = pct + "%";
  if (label) {
    const cur = zb.currentLabel || zb.current || "";
    label.textContent =
      completed +
      "/" +
      total +
      " · " +
      remaining +
      " restant" +
      (remaining > 1 ? "s" : "") +
      (cur ? " · " + cur : "");
  }
}

/** F0118: demarre l etat UI de progression zone. */
export function startZoneBuildProgress(plan) {
  const jobs = (plan && plan.jobs) || [];
  const jobIds = jobs.map(function (j) {
    return j.id;
  });
  state.zoneBuild = {
    zoneId: (plan && plan.zone_id) || null,
    jobIds: jobIds,
    done: [],
    current: null,
    currentLabel: null,
    total: jobs.length,
    completed: 0,
    members: (plan && plan.members) || [],
  };
  updateBuildProgressBar();
  applyBuildProgressClasses();
}

/** F0118: marque un job en cours. */
export function setZoneBuildRunning(jobId, label) {
  if (!state.zoneBuild) return;
  state.zoneBuild.current = jobId || null;
  state.zoneBuild.currentLabel = label || jobId || null;
  updateBuildProgressBar();
  applyBuildProgressClasses();
}

/** F0118: marque un job termine. */
export function setZoneBuildDone(jobId) {
  if (!state.zoneBuild) return;
  if (jobId && state.zoneBuild.done.indexOf(jobId) < 0) {
    state.zoneBuild.done.push(jobId);
  }
  state.zoneBuild.completed = state.zoneBuild.done.length;
  state.zoneBuild.current = null;
  state.zoneBuild.currentLabel = null;
  updateBuildProgressBar();
  applyBuildProgressClasses();
}

/** F0118: fin de progression — etat normal du graphe. */
export function clearZoneBuildProgress() {
  state.zoneBuild = null;
  updateBuildProgressBar();
  applyBuildProgressClasses();
}

/** Ouvre (ou active) l onglet d une zone (F0052). */
export async function openZoneTab(zonePath) {
  const tid = String(zonePath || "").trim();
  if (!tid) return;
  try {
    await switchTab(tid);
    toast("Zone ouverte : " + tid, "success");
  } catch (e) {
    toast("Zone: " + e.message, "error");
  }
}

/**
 * Recharge le graphe de l onglet actif.
 * @param {{ skipSelection?: boolean }} [options]
 *   skipSelection: ne pas appeler ensureSelection (F0133 import massif —
 *   evite hang sur selectStep/loadDataView pendant la pop progression).
 */
export async function refreshGraph(options) {
  const opts = options || {};
  try {
    const q =
      state.activeTab && state.activeTab !== "*"
        ? "?tab=" + encodeURIComponent(state.activeTab)
        : "";
    const g = await api("/gui/graph" + q);
    state.graph = { nodes: g.nodes || [], edges: g.edges || [] };
    // F0039: catalogue multi-onglets pour requires
    if (g.catalog && g.catalog.length) {
      state.allSteps = g.catalog;
    } else {
      // fallback si vieux serveur
      try {
        const all = await api("/gui/graph?tab=*");
        state.allSteps = all.nodes || [];
      } catch (_) {
        state.allSteps = g.nodes || [];
      }
    }
    if (g.tab) state.activeTab = g.tab;
    // compte total steps du workspace via health si dispo
    const nTab = state.graph.nodes.length;
    el.statusPill.textContent =
      nTab +
      " steps" +
      (state.activeTab ? " · " + state.activeTab : "") +
      " · " +
      (state.workspace && state.workspace.read_only ? "RO" : "RW");
    renderGraph();
    renderPipelineTabs();
    // Reconstruire le picker requires si une step est selectionnee
    if (state.selected && el.fieldRequires && !el.fieldRequires.hidden) {
      renderRequiresPicker(getSelectedRequires());
    }
    refreshStepNamesDatalist();
    // F0081: si selection invalide / absente → zone ou dernier objet
    // F0133: skip pendant import (selection differee apres fermeture pop)
    if (opts.skipSelection) {
      return;
    }
    try {
      const nodes = state.graph.nodes || [];
      const stillThere =
        state.selected &&
        (nodes.some(function (n) {
          return n && n.id === state.selected;
        }) ||
          (state.allSteps || []).some(function (n) {
            return n && n.id === state.selected;
          }));
      if (!stillThere) {
        const { ensureSelection } = await import("./config/step-crud.js");
        await ensureSelection({ force: true });
      }
    } catch (_) {
      /* ignore selection fallback errors */
    }
  } catch (e) {
    toast("Graphe: " + e.message, "error");
  }
}
