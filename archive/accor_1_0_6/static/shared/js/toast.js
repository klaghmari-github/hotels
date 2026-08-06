/**
 * Toasts bas-droite (admin: #toast-host multi; user: #toast single).
 */

import { $ } from "./dom.js";

export class ToastHost {
  /**
   * @param {object} [opts]
   * @param {string} [opts.hostSel] conteneur multi-toast (admin)
   * @param {string} [opts.singleSel] element unique (user)
   * @param {number} [opts.ttlMs]
   */
  constructor({ hostSel = "#toast-host", singleSel = "#toast", ttlMs = 3200 } = {}) {
    this.hostSel = hostSel;
    this.singleSel = singleSel;
    this.ttlMs = ttlMs;
    this._timer = null;
  }

  show(message, type = "ok") {
    const host = $(this.hostSel);
    if (host) {
      const el = document.createElement("div");
      el.className = `toast ${type}`;
      el.textContent = message;
      host.appendChild(el);
      setTimeout(() => el.remove(), this.ttlMs);
      return;
    }
    const single = $(this.singleSel);
    if (!single) return;
    single.textContent = message;
    single.classList.remove("hidden");
    if (type === "err") single.classList.add("err");
    else single.classList.remove("err");
    clearTimeout(this._timer);
    this._timer = setTimeout(() => single.classList.add("hidden"), this.ttlMs);
  }
}

/** Instance par defaut (detecte host admin ou user). */
export const toast = new ToastHost();
