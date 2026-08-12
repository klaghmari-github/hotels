/**
 * Utilitaires DOM / strings (F0053-S2 / F0053-S4).
 */

export const $ = (id) => document.getElementById(id);

export function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function pad2(n) {
  return String(n).padStart(2, "0");
}

// Re-export UiController pour import unique depuis util si besoin
export { UiController } from "./ui-base.js";
