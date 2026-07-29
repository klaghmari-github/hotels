/**
 * Stepper numérique premium — remplace les flèches natives du navigateur.
 *
 * Structure :
 *   [ − ]  valeur  [ + ]
 *
 * Capsule glass + or Accor, hold-to-repeat, variants compact / dense.
 */

const SVG_MINUS = `<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
  <path d="M3.25 8h9.5" fill="none" stroke="currentColor" stroke-width="1.85" stroke-linecap="round"/>
</svg>`;

const SVG_PLUS = `<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
  <path d="M8 3.25v9.5M3.25 8h9.5" fill="none" stroke="currentColor" stroke-width="1.85" stroke-linecap="round"/>
</svg>`;

function parseBound(v, fallback) {
  if (v == null || v === "") return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function decimalsFromStep(step) {
  if (!Number.isFinite(step) || step <= 0) return 0;
  const s = String(step);
  if (s.includes("e") || s.includes("E")) {
    // step like 1e-2
    const m = /e-(\d+)/i.exec(s);
    return m ? Number(m[1]) : 0;
  }
  const i = s.indexOf(".");
  return i < 0 ? 0 : s.length - i - 1;
}

function formatValue(n, step) {
  if (!Number.isFinite(n)) return "";
  const d = decimalsFromStep(step);
  if (d <= 0) return String(Math.round(n));
  return n.toFixed(d);
}

function stepValue(input, dir) {
  if (input.disabled || input.readOnly) return;
  const step = parseBound(input.step, 1);
  const min = parseBound(input.min, -Infinity);
  const max = parseBound(input.max, Infinity);
  let cur = parseBound(input.value, 0);
  if (!Number.isFinite(cur)) cur = 0;
  // Align on step grid when possible
  let next = cur + dir * (Number.isFinite(step) && step > 0 ? step : 1);
  if (Number.isFinite(step) && step > 0 && Number.isFinite(min) && min !== -Infinity) {
    const k = Math.round((next - min) / step);
    next = min + k * step;
  }
  next = Math.min(max, Math.max(min, next));
  const d = decimalsFromStep(step);
  if (d > 0) next = Number(next.toFixed(d));
  else next = Math.round(next);

  const prev = input.value;
  input.value = formatValue(next, step);
  if (input.value !== prev) {
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }
}

function bindHold(btn, fn) {
  let delayTimer = null;
  let repeatTimer = null;
  const clear = () => {
    if (delayTimer) clearTimeout(delayTimer);
    if (repeatTimer) clearInterval(repeatTimer);
    delayTimer = null;
    repeatTimer = null;
  };
  const start = (e) => {
    if (e.button != null && e.button !== 0) return;
    e.preventDefault();
    fn();
    delayTimer = setTimeout(() => {
      repeatTimer = setInterval(fn, 55);
    }, 380);
  };
  btn.addEventListener("pointerdown", start);
  btn.addEventListener("pointerup", clear);
  btn.addEventListener("pointerleave", clear);
  btn.addEventListener("pointercancel", clear);
  btn.addEventListener("blur", clear);
}

/**
 * Transforme tous les input[type=number] d'un conteneur en steppers.
 * Idempotent : ignore les inputs déjà encapsulés.
 */
export function enhanceNumSteps(root = document) {
  if (!root || !root.querySelectorAll) return;
  root.querySelectorAll('input[type="number"]').forEach((input) => {
    if (input.closest(".num-step")) return;
    if (input.dataset.numStep === "off") return;

    const wrap = document.createElement("div");
    wrap.className = "num-step";
    if (
      input.closest(".share-pct") ||
      input.closest(".slider-row") ||
      input.classList.contains("num-step-compact")
    ) {
      wrap.classList.add("num-step--compact");
    }
    if (input.closest(".equip-grid")) {
      wrap.classList.add("num-step--equip");
    }

    const parent = input.parentNode;
    if (!parent) return;
    parent.insertBefore(wrap, input);

    const dec = document.createElement("button");
    dec.type = "button";
    dec.className = "num-step-btn num-step-dec";
    dec.setAttribute("aria-label", "Diminuer");
    dec.tabIndex = -1;
    dec.innerHTML = SVG_MINUS;

    const inc = document.createElement("button");
    inc.type = "button";
    inc.className = "num-step-btn num-step-inc";
    inc.setAttribute("aria-label", "Augmenter");
    inc.tabIndex = -1;
    inc.innerHTML = SVG_PLUS;

    wrap.appendChild(dec);
    wrap.appendChild(input);
    wrap.appendChild(inc);

    input.classList.add("num-step-input");
    input.setAttribute("inputmode", input.step && Number(input.step) % 1 !== 0 ? "decimal" : "numeric");

    const syncDisabled = () => {
      const off = !!input.disabled;
      wrap.classList.toggle("is-disabled", off);
      dec.disabled = off;
      inc.disabled = off;
    };
    syncDisabled();

    // Observer disabled changes (toggles catégories)
    const mo = new MutationObserver(syncDisabled);
    mo.observe(input, { attributes: true, attributeFilter: ["disabled"] });

    bindHold(dec, () => stepValue(input, -1));
    bindHold(inc, () => stepValue(input, +1));

    // Clavier ↑↓ déjà natif ; pas besoin de plus
  });
}
