/**
 * API fetch + toast (F0053-S2 / F0053-S4).
 * ApiClient classe OO; api() et toast() restent des wrappers de compat.
 */
import { el } from "./state.js";

export class ApiClient {
  /**
   * @param {object} [options]
   * @param {Record<string,string>} [options.headers] headers par defaut
   */
  constructor(options) {
    const opts = options || {};
    this.defaultHeaders = Object.assign(
      {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      opts.headers || {}
    );
    this._toastTimer = null;
  }

  /**
   * Requete HTTP JSON vers le backend GUI.
   * @param {string} path
   * @param {RequestInit} [opts]
   * @returns {Promise<any>}
   */
  async request(path, opts) {
    const options = opts || {};
    const headers = Object.assign({}, this.defaultHeaders, options.headers || {});
    const res = await fetch(path, {
      ...options,
      headers: headers,
    });
    let data = null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) data = await res.json();
    else data = { detail: await res.text() };
    if (!res.ok) {
      const msg = (data && (data.error || data.detail)) || res.statusText;
      const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      err.status = res.status;
      throw err;
    }
    return data;
  }

  /**
   * Affiche un toast UI (message + kind success|error|…).
   * @param {string} message
   * @param {string} [kind]
   */
  toast(message, kind) {
    if (!el.toast) return;
    el.toast.textContent = message;
    el.toast.className = "toast " + (kind || "");
    el.toast.classList.remove("hidden");
    clearTimeout(this._toastTimer);
    const self = this;
    this._toastTimer = setTimeout(function () {
      el.toast.classList.add("hidden");
    }, 3800);
  }
}

/** Instance partagee. */
export const apiClient = new ApiClient();

/** Wrapper compat — meme signature que monolithe / S2. */
export function toast(message, kind) {
  apiClient.toast(message, kind);
}

/** Wrapper compat — delegue a ApiClient.request. */
export async function api(path, options) {
  return apiClient.request(path, options);
}
