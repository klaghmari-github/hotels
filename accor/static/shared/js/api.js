/**
 * Client HTTP JSON partagé (admin + user).
 *
 * Instance : export const api = new ApiClient()
 * get / post / put / delete — parse JSON, lève Error(body.error) si non 2xx.
 * Doc : docs/FRONT.md
 */

/** Préfixe URL (ex. /studio) — meta[name=accor-base] ou window.ACCOR_BASE. */
export function appBase() {
  if (typeof window !== "undefined" && window.ACCOR_BASE != null) {
    return String(window.ACCOR_BASE).replace(/\/$/, "");
  }
  if (typeof document !== "undefined") {
    const m = document.querySelector('meta[name="accor-base"]');
    if (m && m.content) return String(m.content).replace(/\/$/, "");
  }
  return "";
}

export class ApiClient {
  /**
   * @param {object} [opts]
   * @param {string} [opts.base] prefixe optionnel (défaut : appBase())
   * @param {object} [opts.defaultHeaders]
   */
  constructor({ base, defaultHeaders = {} } = {}) {
    this.base = (base != null ? base : appBase()).replace(/\/$/, "");
    this.defaultHeaders = {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...defaultHeaders,
    };
  }

  /**
   * @param {string} path
   * @param {RequestInit} [options]
   * @returns {Promise<any>}
   */
  async request(path, options = {}) {
    const url = path.startsWith("http") ? path : `${this.base}${path}`;
    const headers = { ...this.defaultHeaders, ...(options.headers || {}) };
    // FormData / body non-JSON : ne pas forcer Content-Type
    if (options.body instanceof FormData) {
      delete headers["Content-Type"];
    }
    const res = await fetch(url, { ...options, headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(data.error || data.message || res.statusText || "Erreur API");
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  get(path, query) {
    let url = path;
    if (query && typeof query === "object") {
      const qs = new URLSearchParams();
      Object.entries(query).forEach(([k, v]) => {
        if (v != null && v !== "") qs.set(k, String(v));
      });
      const s = qs.toString();
      if (s) url += (url.includes("?") ? "&" : "?") + s;
    }
    return this.request(url, { method: "GET" });
  }

  post(path, body) {
    return this.request(path, {
      method: "POST",
      body: body == null ? undefined : JSON.stringify(body),
    });
  }

  put(path, body) {
    return this.request(path, {
      method: "PUT",
      body: body == null ? undefined : JSON.stringify(body),
    });
  }

  delete(path, body) {
    return this.request(path, {
      method: "DELETE",
      body: body == null ? undefined : JSON.stringify(body),
    });
  }
}

export const api = new ApiClient();
