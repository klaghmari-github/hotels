/**
 * F0132 — Dialogue bloquant « traitement en cours » + barre de progression.
 *
 * Affiche une modale non fermable (ESC / backdrop) pendant une action longue
 * (import flux, upload dossier, etc.). Progression determinate (current/total
 * ou percent) ou indeterminate (pulse).
 */
import { $ } from "./util.js";

/** @type {HTMLDialogElement|null} */
let _dialog = null;
/** @type {{ total: number, current: number, percent: number, title: string }|null} */
let _state = null;
/** @type {((e: Event) => void)|null} */
let _onCancel = null;

function els() {
  return {
    dialog: $("progress-dialog") || _dialog,
    title: $("progress-dialog-title"),
    message: $("progress-dialog-message"),
    fill: $("progress-dialog-fill"),
    label: $("progress-dialog-label"),
    track: $("progress-dialog-track"),
  };
}

function clampPct(n) {
  const x = Number(n);
  if (!Number.isFinite(x)) return 0;
  if (x < 0) return 0;
  if (x > 100) return 100;
  return x;
}

/**
 * Affiche le % reel (arrondi) — F0133: plus d arrondi par pas de 10
 * qui masquait le hang a ~90 % (85–99 affiches comme 80/90).
 * @param {number} pct
 */
function displayPct(pct) {
  return Math.round(clampPct(pct));
}

function render() {
  const e = els();
  if (!_state || !e.dialog) return;
  if (e.title) e.title.textContent = _state.title || "Traitement en cours";
  if (e.message) e.message.textContent = _state.message || "";
  const det = _state.total > 0 || _state.mode === "percent";
  const pct = clampPct(_state.percent);
  if (e.fill) {
    e.fill.classList.toggle("is-indeterminate", !det && _state.mode === "indeterminate");
    if (det || _state.mode === "percent") {
      e.fill.style.width = pct + "%";
      e.fill.classList.remove("is-indeterminate");
    } else {
      e.fill.style.width = "40%";
    }
  }
  if (e.label) {
    if (_state.total > 0) {
      e.label.textContent =
        _state.current +
        " / " +
        _state.total +
        " · " +
        displayPct(pct) +
        " %";
    } else if (_state.mode === "percent") {
      e.label.textContent = displayPct(pct) + " %";
    } else {
      e.label.textContent = "…";
    }
  }
  if (e.dialog) {
    e.dialog.setAttribute("aria-busy", "true");
    e.dialog.setAttribute(
      "data-progress",
      String(Math.round(pct))
    );
  }
  if (e.track) {
    e.track.setAttribute("aria-valuenow", String(Math.round(pct)));
  }
}

/**
 * Ouvre (ou reutilise) la pop bloquante.
 *
 * @param {object} [opts]
 * @param {string} [opts.title]
 * @param {string} [opts.message]
 * @param {number} [opts.total]  si > 0 : mode compteur (current/total)
 * @param {number} [opts.current]
 * @param {number} [opts.percent]
 * @param {"auto"|"percent"|"indeterminate"} [opts.mode]
 * @returns {{ set: Function, setMessage: Function, setTitle: Function, tick: Function, close: Function, done: Function }}
 */
export function openProgressDialog(opts) {
  const o = opts || {};
  const e = els();
  _dialog = e.dialog;
  _state = {
    title: o.title || "Traitement en cours",
    message: o.message || "Veuillez patienter…",
    total: Math.max(0, Number(o.total) || 0),
    current: Math.max(0, Number(o.current) || 0),
    percent: clampPct(o.percent != null ? o.percent : 0),
    mode:
      o.mode ||
      (o.total > 0 ? "auto" : o.percent != null ? "percent" : "indeterminate"),
  };
  if (_state.total > 0 && o.percent == null) {
    _state.percent = (_state.current / _state.total) * 100;
    _state.mode = "auto";
  }
  render();

  if (e.dialog && typeof e.dialog.showModal === "function") {
    // Bloque ESC / cancel pendant le traitement
    if (_onCancel) {
      e.dialog.removeEventListener("cancel", _onCancel);
    }
    _onCancel = function (ev) {
      try {
        ev.preventDefault();
      } catch (_) {
        /* ignore */
      }
    };
    e.dialog.addEventListener("cancel", _onCancel);
    try {
      if (!e.dialog.open) e.dialog.showModal();
    } catch (_) {
      /* deja ouvert / non supporté */
    }
  }

  return {
    set: function (patch) {
      updateProgress(patch);
    },
    setMessage: function (msg) {
      updateProgress({ message: msg });
    },
    setTitle: function (t) {
      updateProgress({ title: t });
    },
    /** Avance d un cran (current++) si total connu. */
    tick: function (message) {
      const cur = (_state && _state.current) || 0;
      const tot = (_state && _state.total) || 0;
      updateProgress({
        current: cur + 1,
        message: message,
      });
      if (tot > 0) {
        updateProgress({ percent: ((cur + 1) / tot) * 100 });
      }
    },
    done: function (message) {
      updateProgress({
        percent: 100,
        current: _state && _state.total > 0 ? _state.total : _state && _state.current,
        message: message || "Terminé",
        mode: _state && _state.total > 0 ? "auto" : "percent",
      });
    },
    close: function () {
      closeProgressDialog();
    },
  };
}

/**
 * @param {object} [patch]
 * @param {string} [patch.title]
 * @param {string} [patch.message]
 * @param {number} [patch.current]
 * @param {number} [patch.total]
 * @param {number} [patch.percent]
 * @param {"auto"|"percent"|"indeterminate"} [patch.mode]
 */
export function updateProgress(patch) {
  if (!_state) return;
  const p = patch || {};
  if (p.title != null) _state.title = String(p.title);
  if (p.message != null) _state.message = String(p.message);
  if (p.total != null) {
    _state.total = Math.max(0, Number(p.total) || 0);
    if (_state.total > 0 && p.mode == null && _state.mode === "indeterminate") {
      _state.mode = "auto";
    }
  }
  if (p.current != null) {
    _state.current = Math.max(0, Number(p.current) || 0);
  }
  if (p.mode != null) _state.mode = p.mode;
  if (p.percent != null) {
    _state.percent = clampPct(p.percent);
    if (_state.mode === "indeterminate") _state.mode = "percent";
  } else if (_state.total > 0 && (p.current != null || p.total != null)) {
    _state.percent = (_state.current / _state.total) * 100;
  }
  render();
}

export function closeProgressDialog() {
  const e = els();
  if (e.dialog) {
    if (_onCancel) {
      e.dialog.removeEventListener("cancel", _onCancel);
      _onCancel = null;
    }
    try {
      if (e.dialog.open) e.dialog.close();
    } catch (_) {
      /* ignore */
    }
    e.dialog.removeAttribute("aria-busy");
    e.dialog.removeAttribute("data-progress");
  }
  if (e.fill) {
    e.fill.classList.remove("is-indeterminate");
    e.fill.style.width = "0%";
  }
  _state = null;
}

/**
 * Execute une tache async sous pop bloquante.
 * @template T
 * @param {object} opts  openProgressDialog opts
 * @param {(ctl: ReturnType<typeof openProgressDialog>) => Promise<T>} work
 * @returns {Promise<T>}
 */
export async function withProgress(opts, work) {
  const ctl = openProgressDialog(opts);
  try {
    return await work(ctl);
  } finally {
    // laisse un frame pour peindre 100 % si done() vient d etre appele
    try {
      await new Promise(function (r) {
        setTimeout(r, 120);
      });
    } catch (_) {
      /* ignore */
    }
    ctl.close();
  }
}
