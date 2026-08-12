/**
 * Dialogue de confirmation stylé — base commune renatus-gui.
 * F0063 / F0106 / F0114: remplace window.confirm partout.
 * F0106: focus defaut sur Annuler (evite fausses manips).
 * F0114: variantes d icone (danger / warn / restore / info) + theme unifie.
 */
import { $ } from "./util.js";

const ICONS = {
  danger:
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>' +
    '<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>' +
    '<path d="M10 11v6M14 11v6"/></svg>',
  warn:
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>' +
    '<path d="M12 9v4M12 17h.01"/></svg>',
  restore:
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 7v5l3 2"/></svg>',
  info:
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>',
};

/**
 * @param {object} opts
 * @param {string} opts.title
 * @param {string} opts.message
 * @param {string} [opts.confirmLabel]
 * @param {string} [opts.cancelLabel]
 * @param {boolean} [opts.danger] true = bouton OK rouge (defaut true)
 * @param {boolean} [opts.focusCancel] defaut true
 * @param {"danger"|"warn"|"restore"|"info"} [opts.variant] icone (defaut danger si danger, sinon warn)
 * @returns {Promise<boolean>}
 */
export function confirmDialog(opts) {
  const o = opts || {};
  const dialog = $("confirm-dialog");
  const form = $("confirm-form");
  const titleEl = $("confirm-title");
  const msgEl = $("confirm-message");
  const okBtn = $("confirm-ok");
  const iconHost =
    $("confirm-dialog-icon") ||
    (dialog && dialog.querySelector(".dialog-icon"));

  if (!dialog || !form || !titleEl || !msgEl || !okBtn) {
    return Promise.resolve(
      window.confirm(
        (o.title ? o.title + "\n\n" : "") + (o.message || "Confirmer ?")
      )
    );
  }

  const isDanger = o.danger !== false;
  const variant =
    o.variant ||
    (isDanger ? "danger" : "warn");

  titleEl.textContent = o.title || "Confirmer";
  // pre-wrap dans CSS : \n respectes
  msgEl.textContent = o.message || "";
  okBtn.textContent = o.confirmLabel || (isDanger ? "Confirmer" : "OK");
  okBtn.className = "btn " + (isDanger ? "danger" : "primary");

  if (iconHost) {
    const kind = ICONS[variant] ? variant : "warn";
    iconHost.className = "dialog-icon dialog-icon-" + kind;
    iconHost.innerHTML = ICONS[kind] || ICONS.warn;
    iconHost.setAttribute("data-variant", kind);
  }

  const cancelBtn =
    form.querySelector('[data-testid="confirm-cancel"]') ||
    form.querySelector('[value="cancel"]');
  if (cancelBtn) {
    cancelBtn.textContent = o.cancelLabel || "Annuler";
  }

  // F0106: Annuler = focus defaut
  const preferCancel = o.focusCancel !== false;
  if (cancelBtn) {
    if (preferCancel) {
      cancelBtn.setAttribute("autofocus", "");
      okBtn.removeAttribute("autofocus");
    } else {
      cancelBtn.removeAttribute("autofocus");
      okBtn.setAttribute("autofocus", "");
    }
  }

  // reset returnValue
  try {
    dialog.returnValue = "";
  } catch (_) {}

  return new Promise(function (resolve) {
    function onClose() {
      dialog.removeEventListener("close", onClose);
      resolve(dialog.returnValue === "ok");
    }
    dialog.addEventListener("close", onClose);
    if (typeof dialog.showModal === "function") {
      try {
        if (dialog.open) dialog.close();
      } catch (_) {}
      dialog.showModal();
      function focusSafe() {
        if (preferCancel && cancelBtn) {
          try {
            cancelBtn.focus();
          } catch (_) {}
        } else if (okBtn) {
          try {
            okBtn.focus();
          } catch (_) {}
        }
      }
      focusSafe();
      setTimeout(focusSafe, 0);
      setTimeout(focusSafe, 40);
    } else {
      resolve(
        window.confirm(
          (o.title ? o.title + "\n\n" : "") + (o.message || "Confirmer ?")
        )
      );
    }
  });
}
