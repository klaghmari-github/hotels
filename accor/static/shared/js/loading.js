/**
 * Overlay de chargement (admin) avec compteur d'appels imbriqués.
 */

import { $ } from "./dom.js";

export class LoadingOverlay {
  /**
   * @param {object} [opts]
   * @param {string} [opts.rootSel]
   * @param {string} [opts.titleSel]
   * @param {string} [opts.subSel]
   */
  constructor({
    rootSel = "#loading-overlay",
    titleSel = "#loading-title",
    subSel = "#loading-sub",
  } = {}) {
    this.rootSel = rootSel;
    this.titleSel = titleSel;
    this.subSel = subSel;
    this._depth = 0;
    this._hideTimer = null;
  }

  show(title, sub) {
    const overlay = $(this.rootSel);
    if (!overlay) return;
    this._depth += 1;
    if (this._hideTimer) {
      clearTimeout(this._hideTimer);
      this._hideTimer = null;
    }
    const t = $(this.titleSel);
    const s = $(this.subSel);
    if (t) t.textContent = title || "Chargement…";
    if (s) s.textContent = sub || "Préparation des données";
    overlay.classList.remove("hidden", "is-leaving");
    overlay.setAttribute("aria-busy", "true");
    document.body.classList.add("is-loading");
  }

  hide() {
    const overlay = $(this.rootSel);
    if (!overlay) return;
    this._depth = Math.max(0, this._depth - 1);
    if (this._depth > 0) return;
    overlay.classList.add("is-leaving");
    overlay.setAttribute("aria-busy", "false");
    document.body.classList.remove("is-loading");
    this._hideTimer = setTimeout(() => {
      if (this._depth === 0) {
        overlay.classList.add("hidden");
        overlay.classList.remove("is-leaving");
      }
      this._hideTimer = null;
    }, 200);
  }
}

export const loading = new LoadingOverlay();
