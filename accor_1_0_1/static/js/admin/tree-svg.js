/**
 * Layout récursif + rendu SVG d'un arbre XGBoost (JSON model_explore).
 *
 * Nœuds internes : feature / seuil ; feuilles : valeur. Zoom basique via CSS.
 */

import { escapeHtml } from "../../shared/js/dom.js";
import { Format } from "../../shared/js/format.js";

export class TreeSvgRenderer {
  layout(node, depth = 0, xCounter = { n: 0 }) {
    if (!node) return null;
    if (node.is_leaf) {
      const x = xCounter.n++;
      return { ...node, x, y: depth, width: 1 };
    }
    const left = this.layout(node.left, depth + 1, xCounter);
    const right = this.layout(node.right, depth + 1, xCounter);
    const x =
      left && right
        ? (left.x + right.x) / 2
        : left
          ? left.x
          : right
            ? right.x
            : xCounter.n++;
    return { ...node, x, y: depth, left, right };
  }

  render(host, payload) {
    if (!host) return;
    const laid = this.layout(payload.tree);
    if (!laid) {
      host.className = "tree-view empty";
      host.textContent = "Arbre vide.";
      return;
    }
    const nodeW = 148;
    const nodeH = 42;
    const gapX = 24;
    const gapY = 70;
    let maxX = 0;
    let maxY = 0;
    const walk = (n) => {
      if (!n) return;
      maxX = Math.max(maxX, n.x);
      maxY = Math.max(maxY, n.y);
      walk(n.left);
      walk(n.right);
    };
    walk(laid);
    const width = Math.max(400, (maxX + 1) * (nodeW + gapX) + 40);
    const height = Math.max(200, (maxY + 1) * gapY + 60);
    const pos = (n) => ({
      cx: 20 + n.x * (nodeW + gapX) + nodeW / 2,
      cy: 24 + n.y * gapY,
    });
    const edges = [];
    const nodes = [];
    const collect = (n, parent = null, side = null) => {
      if (!n) return;
      const p = pos(n);
      if (parent) {
        const pp = pos(parent);
        edges.push({
          x1: pp.cx,
          y1: pp.cy + nodeH / 2,
          x2: p.cx,
          y2: p.cy - nodeH / 2,
          label: side,
        });
      }
      nodes.push({ n, p });
      collect(n.left, n, "oui (<)");
      collect(n.right, n, "non (≥)");
    };
    collect(laid);

    const edgeSvg = edges
      .map((e) => {
        const mx = (e.x1 + e.x2) / 2;
        const my = (e.y1 + e.y2) / 2;
        return `<path class="tree-edge" d="M${e.x1},${e.y1} C${e.x1},${my} ${e.x2},${my} ${e.x2},${e.y2}"/>
          <text class="tree-edge-label" x="${mx}" y="${my - 2}" text-anchor="middle">${escapeHtml(e.label || "")}</text>`;
      })
      .join("");
    const nodeSvg = nodes
      .map(({ n, p }) => {
        const cls = n.is_leaf
          ? "tree-node tree-node-leaf"
          : "tree-node tree-node-split";
        const label = n.is_leaf
          ? `leaf ${Number(n.value).toFixed(3)}`
          : Format.truncate(n.feature || n.label || "?", 22);
        const sub = n.is_leaf
          ? n.cover != null
            ? `cover ${Number(n.cover).toFixed(0)}`
            : ""
          : `< ${Number(n.threshold).toFixed(4)}`;
        return `<g class="${cls}" transform="translate(${p.cx - nodeW / 2},${p.cy - nodeH / 2})">
          <rect width="${nodeW}" height="${nodeH}" rx="8"/>
          <text x="8" y="17">${escapeHtml(label)}</text>
          <text class="sub" x="8" y="33">${escapeHtml(sub)}</text>
        </g>`;
      })
      .join("");
    host.className = "tree-view";
    host.innerHTML = `<svg class="tree-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${edgeSvg}${nodeSvg}</svg>`;
  }
}
