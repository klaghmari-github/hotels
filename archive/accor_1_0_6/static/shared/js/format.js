/**
 * Formatage nombres / monnaies / pourcentages (locale fr-FR).
 *
 * Format.euro, Format.pct, Format.num — tolère null/NaN → "—".
 */

export class Format {
  static euro(n) {
    const x = Number(n);
    if (!Number.isFinite(x)) return "—";
    try {
      return x.toLocaleString("fr-FR", {
        style: "currency",
        currency: "EUR",
        maximumFractionDigits: 0,
      });
    } catch {
      return `${Math.round(x)} €`;
    }
  }

  /** Affiche un taux 0–1 ou 0–100 en « N % ». */
  static pct(x) {
    if (x == null || Number.isNaN(Number(x))) return "—";
    let v = Number(x);
    if (v <= 1) v *= 100;
    return `${Math.round(v)} %`;
  }

  /** TO saisi en % (65) ou fraction (0.65) → fraction 0–1. */
  static toRate(raw, fallback = 0.65) {
    let to = Number(raw);
    if (!Number.isFinite(to) || to < 0) return fallback;
    if (to > 1) to = to / 100;
    if (to > 1) to = 1;
    return to;
  }

  static fixed(v, digits = 3) {
    if (v == null || Number.isNaN(Number(v))) return "—";
    return Number(v).toFixed(digits);
  }

  static truncate(s, n) {
    const t = String(s ?? "");
    return t.length > n ? `${t.slice(0, n - 1)}…` : t;
  }

  static locale(n, opts = {}) {
    const x = Number(n);
    if (!Number.isFinite(x)) return "—";
    try {
      return x.toLocaleString("fr-FR", opts);
    } catch {
      return String(x);
    }
  }
}
