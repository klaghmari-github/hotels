/**
 * Simulateur Excel ROD — 3 onglets SIMPLY / LIBERTY / CONNECTED.
 *
 * Layout Excel (table.rx-sheet) :
 *   Indicateur | MOYENNE RESULTATS PILOTES | SIMULATEUR · hôtel
 * Commentaires métier Excel affichés à chaque étape.
 *
 * API : /api/rod/excel/*
 */

import { $, $$, escapeHtml, debounce } from "../../shared/js/dom.js";
import { api } from "../../shared/js/api.js";
import { toast } from "../../shared/js/toast.js";

function fmt(v, d = 2) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("fr-FR", {
    maximumFractionDigits: d,
    minimumFractionDigits: 0,
  });
}

function euro(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return (
    Number(v).toLocaleString("fr-FR", {
      maximumFractionDigits: 0,
      minimumFractionDigits: 0,
    }) + " €"
  );
}

function pct(v, d = 1) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return (
    (Number(v) * 100).toLocaleString("fr-FR", {
      maximumFractionDigits: d,
      minimumFractionDigits: 0,
    }) + " %"
  );
}

const CONCEPTS = ["SIMPLY", "LIBERTY", "CONNECTED"];

/** Money-like row labels (CA, Marge, coûts, Capex, TOTAL…). */
const MONEY_RE = /CA|Marge|co[uû]t|Cout|Capex|TOTAL/i;
/** TO (taux d'occupation) labels. */
const TO_RE = /\bTO\b|taux\s*d['']?occupation|taux_occupation/i;
/** Mix F&B / N-F&B labels. */
const MIX_RE = /mix/i;
/** Generic rate labels (0–1 → %). */
const RATE_RE = /^Taux\b/i;

export class RodExcelPanel {
  constructor(state, nav) {
    this.state = state;
    this.nav = nav;
    this.meta = null;
    this.pilots = null;
    this.result = null;
    this.concept = "SIMPLY";
    this._openBusy = false;
    this._simBusy = false;
    this._pending = false;
    this._didAutoReco = false;
    this._progressTimer = null;
    this._progressPct = 0;
  }

  async open() {
    if (this._openBusy) return;
    if (this.state.panel === "rod-excel" && this.meta && this.result) {
      this.nav.showRodExcelPanel();
      return;
    }
    if (!this.state.confirmLeaveDirty()) return;
    this._openBusy = true;
    this.nav.setNavBusy("excel", true);
    try {
      this.nav.showRodExcelPanel();
      await this.loadMeta();
      await this.loadHotelList();
      await this.simulate();
    } finally {
      this._openBusy = false;
      this.nav.setNavBusy("excel", false);
    }
  }

  wire() {
    $("#rx-hotel-select")?.addEventListener("change", () => this.simulate());
    const bindRange = (sliderId, inputId, onChange) => {
      const sl = $("#" + sliderId);
      const inp = $("#" + inputId);
      if (!sl || !inp) return;
      sl.addEventListener("input", () => {
        inp.value = sl.value;
        onChange();
      });
      inp.addEventListener("input", () => {
        sl.value = inp.value;
        onChange();
      });
    };
    const sched = debounce(() => this.simulate(), 320);
    bindRange("rx-m-lin-slider", "rx-m-lin", sched);
    bindRange("rx-mix-slider", "rx-mix-fb", () => {
      this._syncMixLabel();
      sched();
    });
    ["rx-nb-chambres", "rx-to", "rx-guests"].forEach((id) => {
      $("#" + id)?.addEventListener("change", sched);
    });
    $("#rx-needs-all-on")?.addEventListener("click", () => {
      this._setAllNeeds(true);
      this.simulate();
    });
    $("#rx-needs-all-off")?.addEventListener("click", () => {
      this._setAllNeeds(false);
      this.simulate();
    });
    $$("#rx-concept-tabs .rod-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        const c = btn.dataset.rxConcept;
        if (!c || c === this.concept) return;
        this.concept = c;
        this._activateConceptTab();
        this.renderConcept();
      });
    });
  }

  _syncMixLabel() {
    const pctVal = Number($("#rx-mix-fb")?.value || 70);
    const el = $("#rx-mix-nf-label");
    if (el) el.textContent = `N-F&B = ${100 - pctVal} %`;
  }

  _setAllNeeds(on) {
    $$("#rx-needs-fb input[data-need], #rx-needs-nfb input[data-need]").forEach(
      (inp) => {
        inp.checked = !!on;
        const item = inp.closest(".rod-need-item");
        if (item) {
          item.classList.toggle("is-on", on);
          item.classList.toggle("is-off", !on);
          const st = item.querySelector(".rod-need-state");
          if (st) st.textContent = on ? "Autorisé" : "Interdit";
        }
      }
    );
  }

  _collectNeeds() {
    const out = {};
    $$("#rx-needs-fb input[data-need], #rx-needs-nfb input[data-need]").forEach(
      (inp) => {
        out[inp.dataset.need] = !!inp.checked;
      }
    );
    return out;
  }

  _collectParams() {
    const mixPct = Number($("#rx-mix-fb")?.value || 70);
    const toRaw = $("#rx-to")?.value;
    const nRaw = $("#rx-nb-chambres")?.value;
    const gRaw = $("#rx-guests")?.value;
    let to = toRaw === "" || toRaw == null ? null : Number(toRaw);
    if (to != null && to > 1) to = to / 100;
    return {
      hotel_code: $("#rx-hotel-select")?.value || "",
      m_lin: Number($("#rx-m-lin")?.value || 6),
      mix_fb: mixPct / 100,
      client_needs: this._collectNeeds(),
      nb_chambres: nRaw === "" || nRaw == null ? null : Number(nRaw),
      taux_occupation: to,
      guests_per_chambre: gRaw === "" || gRaw == null ? null : Number(gRaw),
    };
  }

  setStatus(msg) {
    const el = $("#rx-status");
    if (el) el.textContent = msg || "";
  }

  startProgress(detail = "") {
    const card = $("#rx-progress-card");
    const wrap = $("#rx-progress");
    const fill = $("#rx-progress-fill");
    const pctEl = $("#rx-progress-pct");
    const phaseEl = $("#rx-progress-phase");
    const textEl = $("#rx-progress-text");
    const detailEl = $("#rx-progress-detail");
    if (card) {
      card.classList.remove("hidden");
      card.classList.add("is-active");
    }
    if (wrap) {
      wrap.classList.add("is-running");
      wrap.classList.remove("is-done", "is-error");
    }
    this._progressPct = 0;
    if (pctEl) pctEl.innerHTML = "0&nbsp;%";
    if (fill) fill.style.width = "0%";
    if (phaseEl) phaseEl.textContent = "Simulation";
    if (textEl) textEl.textContent = "Calcul des 3 solutions…";
    if (detailEl) detailEl.textContent = detail || "";
    if (this._progressTimer) clearInterval(this._progressTimer);
    this._progressTimer = setInterval(() => {
      this._progressPct = Math.min(90, this._progressPct + 3);
      if (pctEl) pctEl.innerHTML = `${Math.round(this._progressPct)}&nbsp;%`;
      if (fill) fill.style.width = `${this._progressPct}%`;
    }, 120);
  }

  finishProgress(ok = true, msg = "") {
    if (this._progressTimer) {
      clearInterval(this._progressTimer);
      this._progressTimer = null;
    }
    const card = $("#rx-progress-card");
    const wrap = $("#rx-progress");
    const fill = $("#rx-progress-fill");
    const pctEl = $("#rx-progress-pct");
    const textEl = $("#rx-progress-text");
    if (wrap) {
      wrap.classList.remove("is-running");
      wrap.classList.toggle("is-done", ok);
      wrap.classList.toggle("is-error", !ok);
    }
    if (fill) fill.style.width = "100%";
    if (pctEl) pctEl.innerHTML = ok ? "100&nbsp;%" : "—";
    if (textEl) textEl.textContent = msg || (ok ? "Terminé" : "Erreur");
    if (ok) {
      setTimeout(() => {
        if (this._simBusy) return;
        if (card) {
          card.classList.add("hidden");
          card.classList.remove("is-active");
        }
      }, 700);
    }
  }

  async loadMeta() {
    this.meta = await api.get("/api/rod/excel/meta");
    this.renderNeeds(this.meta);
    const d = this.meta.defaults || {};
    if ($("#rx-m-lin") && !$("#rx-m-lin").dataset.touched) {
      const ml = d.m_lin ?? 6;
      $("#rx-m-lin").value = ml;
      if ($("#rx-m-lin-slider")) $("#rx-m-lin-slider").value = ml;
    }
    if ($("#rx-mix-fb") && !$("#rx-mix-fb").dataset.touched) {
      const mix = Math.round((d.mix_fb ?? 0.7) * 100);
      $("#rx-mix-fb").value = mix;
      if ($("#rx-mix-slider")) $("#rx-mix-slider").value = mix;
      this._syncMixLabel();
    }
  }

  renderNeeds(meta) {
    const syncState = (item) => {
      const on = !!item.querySelector("input[data-need]")?.checked;
      const st = item.querySelector(".rod-need-state");
      if (st) st.textContent = on ? "Autorisé" : "Interdit";
      item.classList.toggle("is-on", on);
      item.classList.toggle("is-off", !on);
    };
    const fill = (hostId, items) => {
      const host = $("#" + hostId);
      if (!host) return;
      host.innerHTML = (items || [])
        .map((it) => {
          const on = it.default !== false;
          return `
        <label class="rod-need-item ${on ? "is-on" : "is-off"}">
          <span class="rod-need-label">
            <strong>${escapeHtml(it.label || it.id)}</strong>
            <span class="rod-need-state">${on ? "Autorisé" : "Interdit"}</span>
          </span>
          <span class="switch">
            <input type="checkbox" role="switch" data-need="${escapeHtml(it.id)}"
              ${on ? "checked" : ""} />
            <span aria-hidden="true"></span>
          </span>
        </label>`;
        })
        .join("");
      host.querySelectorAll(".rod-need-item").forEach((item) => {
        const input = item.querySelector("input[data-need]");
        input?.addEventListener("change", () => {
          syncState(item);
          this.simulate();
        });
      });
    };
    fill("rx-needs-fb", meta.client_needs_fb);
    fill("rx-needs-nfb", meta.client_needs_nfb);
  }

  async loadHotelList() {
    // Réutilise la liste des pilotes admin (train) + mapping Excel
    const data = await api.get("/api/rod/pilots", { year: 2026 });
    const sel = $("#rx-hotel-select");
    if (!sel) return;
    const hotels = data.hotels || [];
    const prev = sel.value;
    sel.innerHTML = "";
    if (!hotels.length) {
      sel.innerHTML = `<option value="">— aucun hôtel —</option>`;
      return;
    }
    hotels.forEach((h) => {
      const opt = document.createElement("option");
      opt.value = h.hotel_code;
      opt.textContent = `${h.hotel_code} · ${h.hotel_name || "—"} · ${
        h.category || "?"
      }`;
      sel.appendChild(opt);
    });
    if (prev && hotels.some((h) => h.hotel_code === prev)) sel.value = prev;
    // Prefill operating from first hotel when empty
    const h0 = hotels.find((x) => x.hotel_code === sel.value) || hotels[0];
    if (h0) {
      if ($("#rx-nb-chambres") && !$("#rx-nb-chambres").value && h0.nb_chambres) {
        $("#rx-nb-chambres").value = h0.nb_chambres;
      }
    }
    // chip pilots map
    try {
      this.pilots = await api.get("/api/rod/excel/pilots");
      const chip = $("#rx-chip-pilots");
      if (chip && this.pilots?.by_concept) {
        const parts = CONCEPTS.map((c) => {
          const n = this.pilots.by_concept[c]?.n_pilots ?? 0;
          return `${c}:${n}`;
        });
        chip.textContent = `Pilotes ${parts.join(" · ")}`;
      }
    } catch {
      /* ignore */
    }
  }

  async simulate() {
    const p = this._collectParams();
    if (!p.hotel_code) {
      this.setStatus("Choisissez un hôtel désigné");
      return;
    }
    // Coalesce concurrent requests: re-run once when the in-flight call finishes.
    if (this._simBusy) {
      this._pending = true;
      return;
    }
    this._simBusy = true;
    this._pending = false;
    this.startProgress(p.hotel_code);
    this.setStatus("Calcul…");
    try {
      this.result = await api.post("/api/rod/excel/simulate", p);
      if (!this.result?.ok) {
        throw new Error(this.result?.error || "Échec simulation");
      }
      // fill params if empty from response
      const rp = this.result.params || {};
      if ($("#rx-nb-chambres") && !$("#rx-nb-chambres").value && rp.nb_chambres) {
        $("#rx-nb-chambres").value = rp.nb_chambres;
      }
      if ($("#rx-to") && !$("#rx-to").value && rp.taux_occupation != null) {
        $("#rx-to").value = Math.round(Number(rp.taux_occupation) * 1000) / 10;
      }
      if ($("#rx-guests") && !$("#rx-guests").value && rp.guests_per_chambre) {
        $("#rx-guests").value = rp.guests_per_chambre;
      }
      const chip = $("#rx-chip-hotel");
      if (chip) {
        chip.textContent = `${this.result.hotel_code} · ${
          this.result.hotel_name || ""
        }`.trim();
      }
      this._syncConceptTabs();
      this.renderConcept();
      this.finishProgress(true, "3 solutions calculées");
      this.setStatus("");
    } catch (err) {
      console.error(err);
      this.finishProgress(false, err.message);
      this.setStatus(err.message);
      toast.show(err.message, "err");
    } finally {
      this._simBusy = false;
      if (this._pending) {
        this._pending = false;
        this.simulate();
      }
    }
  }

  /**
   * Reorder / relabel concept tabs from result.concept_order.
   * Auto-select recommended_concept only on first successful load.
   */
  _syncConceptTabs() {
    const tabs = $("#rx-concept-tabs");
    if (!tabs || !this.result?.ok) return;

    const order =
      Array.isArray(this.result.concept_order) && this.result.concept_order.length
        ? this.result.concept_order.map((c) => String(c).toUpperCase())
        : CONCEPTS.slice();

    const byConcept = new Map();
    tabs.querySelectorAll(".rod-tab[data-rx-concept]").forEach((btn) => {
      byConcept.set(btn.dataset.rxConcept, btn);
    });
    order.forEach((c) => {
      const btn = byConcept.get(c);
      if (btn) {
        btn.textContent = `SIMULATEUR ${c}`;
        tabs.appendChild(btn);
      }
    });
    // Any leftover tabs (unknown concepts) keep order after known ones
    byConcept.forEach((btn, c) => {
      if (!order.includes(c)) {
        btn.textContent = `SIMULATEUR ${c}`;
        tabs.appendChild(btn);
      }
    });

    const reco = this.result.recommended_concept
      ? String(this.result.recommended_concept).toUpperCase()
      : null;
    if (!this._didAutoReco && reco && byConcept.has(reco)) {
      this.concept = reco;
      this._didAutoReco = true;
    } else if (!byConcept.has(this.concept) && order.length) {
      this.concept = order[0];
    }

    this._activateConceptTab();
  }

  _activateConceptTab() {
    $$("#rx-concept-tabs .rod-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.rxConcept === this.concept);
    });
  }

  /**
   * Align left_rows / right_rows by label (union, left-first then right-only).
   * Duplicate labels keep parallel slots (e.g. Amortissement mois / ans).
   */
  _alignRows(leftRows, rightRows) {
    const left = leftRows || [];
    const right = rightRows || [];
    const leftBuckets = new Map();
    const rightBuckets = new Map();
    for (const r of left) {
      const k = r.label || "";
      if (!leftBuckets.has(k)) leftBuckets.set(k, []);
      leftBuckets.get(k).push(r);
    }
    for (const r of right) {
      const k = r.label || "";
      if (!rightBuckets.has(k)) rightBuckets.set(k, []);
      rightBuckets.get(k).push(r);
    }
    const seen = new Set();
    const out = [];
    for (const r of left) {
      const k = r.label || "";
      if (seen.has(k)) continue;
      seen.add(k);
      const L = leftBuckets.get(k) || [];
      const R = rightBuckets.get(k) || [];
      const n = Math.max(L.length, R.length);
      for (let i = 0; i < n; i++) {
        out.push({ label: k, left: L[i] || null, right: R[i] || null });
      }
    }
    for (const r of right) {
      const k = r.label || "";
      if (seen.has(k)) continue;
      seen.add(k);
      for (const item of rightBuckets.get(k) || []) {
        out.push({ label: k, left: null, right: item });
      }
    }
    return out;
  }

  /**
   * Format a single cell value according to its label.
   * @returns {{ text: string, cls: string }}
   */
  _formatValue(row, label) {
    if (row == null || row.value == null || row.value === "—") {
      return { text: "—", cls: "" };
    }
    const v = row.value;
    if (v === "Not profitable") {
      return { text: "Not profitable", cls: "is-not-profitable" };
    }
    if (typeof v === "string") {
      return { text: v, cls: "" };
    }
    if (typeof v === "number") {
      const lab = label || row.label || "";
      if (MONEY_RE.test(lab)) {
        return { text: euro(v), cls: /TOTAL/i.test(lab) ? "is-total" : "" };
      }
      if (TO_RE.test(lab) && v >= 0 && v <= 1) {
        return { text: pct(v), cls: "" };
      }
      if (MIX_RE.test(lab) && v >= 0 && v <= 1) {
        return { text: pct(v), cls: "" };
      }
      if (RATE_RE.test(lab) && v >= 0 && v <= 1) {
        return { text: pct(v), cls: "" };
      }
      return { text: fmt(v, 4), cls: "" };
    }
    return { text: String(v), cls: "" };
  }

  _displayLabel(pair) {
    const base = pair.label || "";
    const hint =
      (pair.left && pair.left.hint) || (pair.right && pair.right.hint) || "";
    // Disambiguate duplicate labels (Amortissement mois / ans)
    if (hint && /amort/i.test(base)) {
      return `${base} (${hint})`;
    }
    return base;
  }

  renderConcept() {
    const host = $("#rx-panels");
    const kpiBar = $("#rx-kpi-bar");
    if (!host || !this.result?.ok) return;
    const block = this.result.concepts?.[this.concept];
    if (!block) {
      host.innerHTML = `<p class="empty-state">Pas de données pour ${escapeHtml(
        this.concept
      )}</p>`;
      return;
    }

    if (kpiBar) {
      const k = block.kpi || {};
      const pilots = (block.pilots || [])
        .map((p) => p.label || p.hotel_code)
        .join(", ");
      const reco = this.result.recommended_concept
        ? String(this.result.recommended_concept).toUpperCase()
        : "";
      const recoHtml = reco
        ? `<div class="rx-kpi-item rx-kpi-reco"><span>Recommandé</span><strong>${escapeHtml(
            reco
          )}</strong></div>`
        : "";
      kpiBar.innerHTML = `
        ${recoHtml}
        <div class="rx-kpi-item"><span>Solution</span><strong>${escapeHtml(
          block.label || this.concept
        )}</strong></div>
        <div class="rx-kpi-item"><span>Pilotes (${block.n_pilots || 0})</span><strong>${escapeHtml(
          pilots || "—"
        )}</strong></div>
        <div class="rx-kpi-item"><span>CA pilotes</span><strong>${euro(
          k.left_ca_ht
        )}</strong></div>
        <div class="rx-kpi-item"><span>CA projeté</span><strong>${euro(
          k.right_ca_ht
        )}</strong></div>
        <div class="rx-kpi-item"><span>Marge nette proj.</span><strong>${euro(
          k.right_marge_nette
        )}</strong></div>
        <div class="rx-kpi-item"><span>Amort. proj.</span><strong>${
          k.right_amort_mois != null ? fmt(k.right_amort_mois, 0) + " mois" : "—"
        }</strong></div>
      `;
    }

    const hotelLabel = [
      this.result.hotel_code || "",
      this.result.hotel_name || "",
    ]
      .filter(Boolean)
      .join(" · ");
    const rightHead = hotelLabel
      ? `SIMULATEUR · ${hotelLabel}`
      : "SIMULATEUR · hôtel désigné";

    const steps = block.steps || [];
    const bodyRows = steps
      .map((st) => {
        const hl = st.highlight ? " is-highlight" : "";
        const banner = `
        <tr class="rx-banner${hl}" data-step="${escapeHtml(st.id || "")}">
          <th colspan="3">${escapeHtml(st.title || st.id || "")}</th>
        </tr>`;
        const comment = st.comment
          ? `
        <tr class="rx-comment-row">
          <td colspan="3">${escapeHtml(st.comment).replace(/\n/g, "<br>")}</td>
        </tr>`
          : "";
        const aligned = this._alignRows(st.left_rows, st.right_rows);
        const metrics =
          aligned.length === 0
            ? `
        <tr class="rx-metric-row">
          <th class="rx-ind">—</th>
          <td class="rx-left">—</td>
          <td class="rx-right">—</td>
        </tr>`
            : aligned
                .map((pair) => {
                  const lab = this._displayLabel(pair);
                  const L = this._formatValue(pair.left, pair.label);
                  const R = this._formatValue(pair.right, pair.label);
                  const isTotal = /TOTAL/i.test(pair.label || "");
                  const rowCls = ["rx-metric-row", isTotal ? "is-total" : ""]
                    .filter(Boolean)
                    .join(" ");
                  const lCls = ["rx-left", L.cls].filter(Boolean).join(" ");
                  const rCls = ["rx-right", R.cls].filter(Boolean).join(" ");
                  return `
        <tr class="${rowCls}">
          <th class="rx-ind" scope="row">${escapeHtml(lab)}</th>
          <td class="${lCls}">${escapeHtml(L.text)}</td>
          <td class="${rCls}">${escapeHtml(R.text)}</td>
        </tr>`;
                })
                .join("");
        return banner + comment + metrics;
      })
      .join("");

    host.innerHTML = `
      <div class="rx-sheet-wrap">
        <table class="rx-sheet">
          <thead>
            <tr>
              <th class="rx-th-ind">Indicateur</th>
              <th class="rx-th-left">MOYENNE RESULTATS PILOTES</th>
              <th class="rx-th-right">${escapeHtml(rightHead)}</th>
            </tr>
          </thead>
          <tbody>
            ${bodyRows}
          </tbody>
        </table>
      </div>
      <p class="muted small rx-method">${escapeHtml(block.method || "")}</p>
    `;
  }
}
