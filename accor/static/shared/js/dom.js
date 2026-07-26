/**
 * Helpers DOM partagés (admin + user).
 *
 * $, $$, on, escapeHtml, debounce, fieldStr/Num/Checked, setField, setText…
 */

export function $(sel, root = document) {
  return root.querySelector(sel);
}

export function $$(sel, root = document) {
  return Array.from((root || document).querySelectorAll(sel));
}

export function on(el, event, handler, opts) {
  if (!el) return () => {};
  el.addEventListener(event, handler, opts);
  return () => el.removeEventListener(event, handler, opts);
}

export function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Debounce generique. */
export function debounce(fn, ms = 280) {
  let timer = null;
  function wrapped(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), ms);
  }
  wrapped.cancel = () => {
    clearTimeout(timer);
    timer = null;
  };
  return wrapped;
}

/** Valeur d'input #id (texte). */
export function fieldStr(id) {
  const el = $(id.startsWith("#") ? id : `#${id}`);
  return el ? String(el.value || "").trim() : "";
}

/** Valeur numerique d'input #id. */
export function fieldNum(id, fallback = 0) {
  const el = $(id.startsWith("#") ? id : `#${id}`);
  if (!el) return fallback;
  const v = parseFloat(el.value);
  return Number.isFinite(v) ? v : fallback;
}

/** Checkbox #id. */
export function fieldChecked(id) {
  const el = $(id.startsWith("#") ? id : `#${id}`);
  return !!(el && el.checked);
}

/** Affecte value si element present. */
export function setField(id, value) {
  const el = $(id.startsWith("#") ? id : `#${id}`);
  if (el && value != null && value !== "") el.value = value;
  return el;
}

/** Texte d'un element (pas input). */
export function setText(id, text) {
  const el = $(id.startsWith("#") ? id : `#${id}`);
  if (el) el.textContent = text;
  return el;
}
