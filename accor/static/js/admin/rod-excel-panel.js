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
    /** Overrides colonne pilote par solution { SIMPLY: {ca_fb:…}, … } */
    this.pilotOverrides = { SIMPLY: {}, LIBERTY: {}, CONNECTED: {} };
    this._openBusy = false;
    this._simBusy = false;
    this._pending = false;
    this._didAutoReco = false;
    this._progressTimer = null;
    this._progressPct = 0;
  }

  /**
   * @param {"SIMPLY"|"LIBERTY"|"CONNECTED"} [concept]
   */
  async open(concept = "SIMPLY") {
    const c = String(concept || "SIMPLY").toUpperCase();
    const navKey =
      c === "LIBERTY"
        ? "excel-liberty"
        : c === "CONNECTED"
          ? "excel-connected"
          : "excel-simply";
    const panelId = `rod-excel-${c.toLowerCase()}`;

    // Déjà sur ce concept avec données → juste afficher
    if (
      this.state.panel === panelId &&
      this.meta &&
      this.result &&
      this.concept === c
    ) {
      this.nav.showRodExcelPanel(c);
      this._syncConceptPill();
      this.renderConcept();
      return;
    }

    // Changement d'onglet sidebar avec résultats déjà calculés
    if (this.meta && this.result && this.concept !== c) {
      this.concept = c;
      this.nav.showRodExcelPanel(c);
      this._syncConceptPill();
      this.renderConcept();
      return;
    }

    if (this._openBusy) return;
    if (!this.state.confirmLeaveDirty()) return;
    this._openBusy = true;
    this.concept = c;
    this.nav.setNavBusy(navKey, true);
    try {
      this.nav.showRodExcelPanel(c);
      this._syncConceptPill();
      this._showPlaceholder(
        `Chargement simulateur ${c}…`,
        "Calcul des colonnes pilotes + hôtel désigné (règles 1→4, coûts, marge)."
      );
      await this.loadMeta();
      await this.loadHotelList();
      await this.simulate();
      // Sécurité : si simulate n’a rien rendu, message d’erreur
      const host = $("#rx-panels");
      if (host && !host.querySelector(".xl-sheet")) {
        this._showPlaceholder(
          "La feuille Excel ne s’est pas affichée",
          this.result?.error ||
            "Vérifiez la console (F12) et que /api/rod/excel/simulate répond."
        );
      }
    } finally {
      this._openBusy = false;
      this.nav.setNavBusy(navKey, false);
    }
  }

  _syncConceptPill() {
    const el = $("#rx-concept-name");
    if (el) el.textContent = this.concept;
    const pill = $("#rx-concept-pill");
    if (pill) pill.dataset.concept = this.concept;
    const titles = {
      SIMPLY: "Simulateur Simply",
      LIBERTY: "Simulateur Liberty",
      CONNECTED: "Simulateur Connected",
    };
    const h1 = $("#rx-page-title");
    if (h1) h1.textContent = titles[this.concept] || `Simulateur ${this.concept}`;
  }

  _showPlaceholder(msg, detail = "") {
    const host = $("#rx-panels");
    if (!host) return;
    host.innerHTML = `
      <div class="xl-placeholder">
        <p><strong>${escapeHtml(msg || "…")}</strong></p>
        ${
          detail
            ? `<p class="muted">${escapeHtml(detail)}</p>`
            : ""
        }
      </div>`;
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
    // Sous-catégories : scroll de la zone haute (sticky) pour ne jamais
    // bloquer le retour vers hôtel / params.
    const needsDetails = document.querySelector("#view-rod-excel .rx-needs-details");
    const sticky = document.querySelector("#view-rod-excel .rod-excel-sticky");
    needsDetails?.addEventListener("toggle", () => {
      if (!sticky) return;
      if (needsDetails.open) {
        // Amener le summary en vue en haut de la zone scrollable
        requestAnimationFrame(() => {
          const sum = needsDetails.querySelector("summary");
          if (sum) {
            const top =
              sum.offsetTop - sticky.offsetTop - 8;
            sticky.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
          }
        });
      } else {
        sticky.scrollTo({ top: 0, behavior: "smooth" });
      }
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
    // N'envoyer que les concepts avec au moins un override
    const pov = {};
    for (const c of CONCEPTS) {
      const o = this.pilotOverrides[c];
      if (o && Object.keys(o).length) pov[c] = { ...o };
    }
    return {
      hotel_code: $("#rx-hotel-select")?.value || "",
      m_lin: Number($("#rx-m-lin")?.value || 6),
      mix_fb: mixPct / 100,
      client_needs: this._collectNeeds(),
      nb_chambres: nRaw === "" || nRaw == null ? null : Number(nRaw),
      taux_occupation: to,
      guests_per_chambre: gRaw === "" || gRaw == null ? null : Number(gRaw),
      pilot_overrides: Object.keys(pov).length ? pov : undefined,
    };
  }

  /** Valeur effective d'un champ pilote (override ou base Excel). */
  _pilotVal(key, excelBase, side, fallback = null) {
    const ov = this.pilotOverrides[this.concept] || {};
    if (ov[key] != null && ov[key] !== "") return Number(ov[key]);
    if (excelBase && excelBase[key] != null) return Number(excelBase[key]);
    if (side) {
      const v = this._sideVal(side, key);
      if (v != null) return Number(v);
    }
    return fallback;
  }

  /** Input numérique éditable (colonne pilote). */
  _editInput(key, value, { step = "1", min = null, max = null, unit = "", d = 2 } = {}) {
    let v = "";
    if (value != null && !Number.isNaN(Number(value))) {
      const n = Number(value);
      v = d === 0 ? String(Math.round(n)) : String(Number(n.toFixed(d)));
    }
    const dirty = (this.pilotOverrides[this.concept] || {})[key] != null;
    const minA = min != null ? ` min="${min}"` : "";
    const maxA = max != null ? ` max="${max}"` : "";
    return `<span class="xl-edit-wrap">
      <input type="number" class="xl-edit${dirty ? " is-dirty" : ""}" data-pilot-key="${escapeHtml(key)}"
        value="${escapeHtml(v)}" step="${step}"${minA}${maxA}
        title="Modifier la réf. pilote — impact cascade sur la colonne hôtel" />
      ${unit ? `<span class="xl-edit-unit">${escapeHtml(unit)}</span>` : ""}
    </span>`;
  }

  /** Mix F&B en % éditable. */
  _editPctInput(key, ratio, { step = "1" } = {}) {
    const pctVal =
      ratio == null || Number.isNaN(Number(ratio))
        ? ""
        : String(Math.round(Number(ratio) * 1000) / 10);
    const dirty = (this.pilotOverrides[this.concept] || {})[key] != null;
    return `<span class="xl-edit-wrap">
      <input type="number" class="xl-edit${dirty ? " is-dirty" : ""}" data-pilot-key="${escapeHtml(key)}"
        data-as-pct="1"
        value="${escapeHtml(pctVal)}" step="${step}" min="0" max="100"
        title="Modifier le mix pilote (%)" />
      <span class="xl-edit-unit">%</span>
    </span>`;
  }

  resetPilotOverrides(concept = null) {
    const c = concept || this.concept;
    this.pilotOverrides[c] = {};
    this.simulate();
  }

  _wirePilotEdits(host) {
    if (!host) return;
    const sched = debounce(() => this.simulate(), 380);
    host.querySelectorAll("input.xl-edit[data-pilot-key]").forEach((inp) => {
      inp.addEventListener("change", () => {
        const key = inp.dataset.pilotKey;
        if (!key) return;
        let raw = inp.value;
        if (raw === "" || raw == null) {
          delete this.pilotOverrides[this.concept][key];
          if (key === "mix_fb") delete this.pilotOverrides[this.concept].mix_nf;
          sched();
          return;
        }
        let n = Number(String(raw).replace(",", "."));
        if (!Number.isFinite(n)) return;
        if (inp.dataset.asPct === "1") n = n / 100;
        if (!this.pilotOverrides[this.concept]) {
          this.pilotOverrides[this.concept] = {};
        }
        this.pilotOverrides[this.concept][key] = n;
        if (key === "mix_fb") {
          this.pilotOverrides[this.concept].mix_nf = Math.max(0, 1 - n);
        }
        // Feedback visuel immédiat
        inp.classList.add("is-dirty");
        sched();
      });
      inp.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          inp.blur();
        }
      });
    });
    host.querySelector("#rx-reset-pilot")?.addEventListener("click", () => {
      this.resetPilotOverrides(this.concept);
    });
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
      // Concept = entrée sidebar choisie (pas d'auto-switch vers la reco)
      this._syncConceptPill();
      this.renderConcept();
      this.finishProgress(true, `Simulateur ${this.concept} prêt`);
      this.setStatus("");
      // Scroller vers la feuille Excel (pas seulement les contrôles)
      requestAnimationFrame(() => {
        const sheet = document.querySelector("#rx-panels .xl-sheet");
        const scroller = $("#rx-scroll-body");
        if (sheet && scroller) {
          scroller.scrollTop = 0;
          sheet.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }
      });
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

  /** TVA approx. Excel (F&B ~10 %, N-F&B ~20 %). */
  _ttcFb(ht) {
    if (ht == null || Number.isNaN(Number(ht))) return null;
    return Number(ht) * 1.1;
  }
  _ttcNf(ht) {
    if (ht == null || Number.isNaN(Number(ht))) return null;
    return Number(ht) * 1.2;
  }

  _num(v) {
    if (v == null || v === "—" || v === "Not profitable") return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  _sideVal(side, key) {
    if (!side) return null;
    if (key in side) return side[key];
    const p = side.params || {};
    if (key in p) return p[key];
    return null;
  }

  _stepRow(steps, stepId, label) {
    const st = (steps || []).find((s) => s.id === stepId);
    if (!st) return { left: null, right: null };
    const rows = st.rows || [];
    if (rows.length) {
      const r = rows.find((x) => (x.label || "") === label);
      if (r) return { left: r.left, right: r.right };
    }
    const L = (st.left_rows || []).find((x) => (x.label || "") === label);
    const R = (st.right_rows || []).find((x) => (x.label || "") === label);
    return { left: L?.value ?? null, right: R?.value ?? null };
  }

  _moneyCell(v, { total = false, np = false } = {}) {
    if (np || v === "Not profitable") {
      return `<span class="xl-np">Not profitable</span>`;
    }
    if (v == null || Number.isNaN(Number(v))) return `<span class="xl-empty">—</span>`;
    return `<span class="xl-money${total ? " is-total" : ""}">${escapeHtml(
      euro(v)
    )}</span>`;
  }

  _pctCell(v, d = 0) {
    if (v == null || Number.isNaN(Number(v))) return `<span class="xl-empty">—</span>`;
    const x = Number(v);
    const shown = x > 1 ? x : x * 100;
    return `<span class="xl-pct">${escapeHtml(
      shown.toLocaleString("fr-FR", {
        maximumFractionDigits: d,
        minimumFractionDigits: d,
      }) + " %"
    )}</span>`;
  }

  _numCell(v, d = 2) {
    if (v == null || Number.isNaN(Number(v))) return `<span class="xl-empty">—</span>`;
    return `<span class="xl-num">${escapeHtml(fmt(v, d))}</span>`;
  }

  _kv(label, valueHtml, hint = "") {
    return `<div class="xl-kv">
      <span class="xl-k">${escapeHtml(label)}</span>
      <span class="xl-v">${valueHtml}</span>
      ${hint ? `<span class="xl-hint">${escapeHtml(hint)}</span>` : ""}
    </div>`;
  }

  /** Bloc paramètres type Excel (3 mini-zones). Colonne gauche = éditable. */
  _paramsBlock(side, concept, isLeft, excelBase = null) {
    const src = isLeft && excelBase ? excelBase : side;
    const n = this._num(
      isLeft
        ? this._pilotVal("nb_chambres", excelBase, side)
        : this._sideVal(src, "nb_chambres") ?? this._sideVal(side, "nb_chambres")
    );
    const g = this._num(
      isLeft
        ? this._pilotVal("guests_per_chambre", excelBase, side)
        : this._sideVal(src, "guests_per_chambre") ??
            this._sideVal(side, "guests_per_chambre")
    );
    const to = this._num(
      isLeft
        ? this._pilotVal("taux_occupation", excelBase, side)
        : this._sideVal(src, "taux_occupation") ??
            this._sideVal(side, "taux_occupation")
    );
    const ml = this._num(
      isLeft
        ? this._pilotVal("m_lin", excelBase, side)
        : this._sideVal(src, "m_lin") ?? this._sideVal(side, "m_lin")
    );
    const mixFb = this._num(
      isLeft
        ? this._pilotVal("mix_fb", excelBase, side)
        : this._sideVal(src, "mix_fb") ?? this._sideVal(side, "mix_fb")
    );
    const mixNf = this._num(
      isLeft
        ? this._pilotVal("mix_nf", excelBase, side, mixFb != null ? 1 - mixFb : null)
        : this._sideVal(src, "mix_nf") ?? this._sideVal(side, "mix_nf")
    );
    let mFb = this._num(
      isLeft ? this._pilotVal("margin_fb", excelBase, side, 2.6) : excelBase?.margin_fb
    );
    if (mFb == null) mFb = 2.6;
    let mNf = this._num(
      isLeft ? this._pilotVal("margin_nf", excelBase, side) : excelBase?.margin_nf
    );
    if (mNf == null) {
      mNf = 1.45;
      if (concept === "LIBERTY") mNf = 2.0;
      else if (concept === "CONNECTED") mNf = 1.8;
    }
    const pond =
      mixFb != null && mixNf != null
        ? (mFb * mixFb + mNf * mixNf) / (mixFb + mixNf || 1)
        : null;

    const frigo =
      concept === "CONNECTED" && isLeft
        ? this._kv("Nb. FC", this._numCell(3, 0))
        : "";

    if (isLeft) {
      const dirty = Object.keys(this.pilotOverrides[concept] || {}).length > 0;
      return `
      <div class="xl-pilot-edit-bar">
        <span class="xl-pilot-edit-label${dirty ? " is-dirty" : ""}">
          ${dirty ? "✎ Pilote modifié — impact cascade" : "✎ Valeurs pilote éditables"}
        </span>
        <button type="button" class="btn btn-ghost btn-xs" id="rx-reset-pilot"
          ${dirty ? "" : "disabled"} title="Revenir aux pivots Excel">
          Réinitialiser
        </button>
      </div>
      <div class="xl-params-grid">
        <div class="xl-mini">
          <div class="xl-mini-h">PARAMETRES HOTEL</div>
          ${this._kv("Nb. de ch.", this._editInput("nb_chambres", n, { step: "1", min: 1, d: 0 }))}
          ${this._kv("Nb. gu / ch", this._editInput("guests_per_chambre", g, { step: "0.1", min: 0.5, d: 1 }))}
          ${this._kv("TO (YTD)", this._editPctInput("taux_occupation", to))}
        </div>
        <div class="xl-mini">
          <div class="xl-mini-h">RETAIL SPACE</div>
          ${this._kv("M. lin.", this._editInput("m_lin", ml, { step: "0.5", min: 0, d: 1 }))}
          ${frigo}
        </div>
        <div class="xl-mini">
          <div class="xl-mini-h">MIX + MARGE PDTS</div>
          ${this._kv("F&B mix", this._editPctInput("mix_fb", mixFb))}
          ${this._kv("F&B marge", this._editInput("margin_fb", mFb, { step: "0.05", min: 1, d: 2 }))}
          ${this._kv("N-F&B mix", this._pctCell(mixNf, 0))}
          ${this._kv("N-F&B marge", this._editInput("margin_nf", mNf, { step: "0.05", min: 1, d: 2 }))}
          ${this._kv("Marge pondérée", this._numCell(pond, 2))}
        </div>
      </div>`;
    }

    return `
      <div class="xl-params-grid">
        <div class="xl-mini">
          <div class="xl-mini-h">PARAMETRES HOTEL</div>
          ${this._kv("Nb. de ch.", this._numCell(n, 0))}
          ${this._kv("Nb. gu / ch", this._numCell(g, 1))}
          ${this._kv("TO (YTD)", this._pctCell(to, 0))}
        </div>
        <div class="xl-mini">
          <div class="xl-mini-h">RETAIL SPACE</div>
          ${this._kv("M. lin.", this._numCell(ml, 0))}
          ${frigo}
        </div>
        <div class="xl-mini">
          <div class="xl-mini-h">MIX + MARGE PDTS</div>
          ${this._kv("F&B", this._pctCell(mixFb, 0) + " · " + this._numCell(mFb, 2))}
          ${this._kv("N-F&B", this._pctCell(mixNf, 0) + " · " + this._numCell(mNf, 2))}
          ${this._kv("Marge pondérée", this._numCell(pond, 2))}
        </div>
      </div>`;
  }

  _moyenneBlock(side, isLeft, excelBase = null) {
    const src = isLeft && excelBase ? excelBase : side;
    const n = this._num(
      isLeft
        ? this._pilotVal("nb_chambres", excelBase, side)
        : this._sideVal(src, "nb_chambres") ?? this._sideVal(side, "nb_chambres")
    );
    const to = this._num(
      isLeft
        ? this._pilotVal("taux_occupation", excelBase, side)
        : this._sideVal(src, "taux_occupation") ??
            this._sideVal(side, "taux_occupation")
    );
    const g = this._num(
      isLeft
        ? this._pilotVal("guests_per_chambre", excelBase, side)
        : this._sideVal(src, "guests_per_chambre") ??
            this._sideVal(side, "guests_per_chambre")
    );
    const cj =
      this._num(this._sideVal(src, "clients_jour")) ??
      this._num(this._sideVal(side, "clients_jour")) ??
      (n != null && to != null && g != null ? n * to * g : null);
    const cm =
      this._num(this._sideVal(src, "clients_mois")) ??
      this._num(this._sideVal(side, "clients_mois")) ??
      (cj != null ? cj * 30.5 : null);
    const chOcc = n != null && to != null ? n * to : null;
    const ventes = this._num(
      isLeft
        ? this._pilotVal("nb_ventes", excelBase, side)
        : excelBase?.nb_ventes ?? side.nbr_ventes
    );
    const taux = cm && ventes != null && cm > 0 ? ventes / cm : null;
    return `
      <div class="xl-section-label">MOYENNE</div>
      ${this._kv("Ch. occ.", this._numCell(chOcc, 0), "chambres occupées")}
      ${this._kv("Cl. héb. / jour", this._numCell(cj, 0), "clients hébergés / jour")}
      ${this._kv("Cl. héb. / mois", this._numCell(cm, 0), "clients hébergés / mois")}
      ${this._kv(
        "Nb. ventes",
        isLeft
          ? this._editInput("nb_ventes", ventes, { step: "1", min: 0, d: 0 })
          : this._numCell(ventes, 0),
        isLeft ? "ventes mensuelles (résultat pilotes) — éditable" : "ventes mensuelles"
      )}
      ${
        isLeft
          ? this._kv(
              "Taux acheteurs",
              this._pctCell(taux, 2),
              "de clients acheteurs / mois"
            )
          : ""
      }
    `;
  }

  /** Table CA F&B / N-F&B, optionnellement éditable (colonne pilote). */
  _caTable(fb, nf, { ttc = false, total = false, np = false, editable = false } = {}) {
    if (np) {
      return `<div class="xl-ca-table"><div class="xl-np">Not profitable</div></div>`;
    }
    const fbN = this._num(fb);
    const nfN = this._num(nf);
    const tot = fbN != null && nfN != null ? fbN + nfN : null;
    const cellFb = editable
      ? this._editInput("ca_fb", fbN, { step: "1", min: 0, d: 0, unit: "€" })
      : this._moneyCell(fbN);
    const cellNf = editable
      ? this._editInput("ca_nf", nfN, { step: "1", min: 0, d: 0, unit: "€" })
      : this._moneyCell(nfN);
    let html = `<table class="xl-ca"><thead><tr><th></th><th>CA HT</th>${
      ttc ? "<th>CA TTC</th>" : ""
    }</tr></thead><tbody>`;
    html += `<tr><td class="xl-tag">F&B</td><td>${cellFb}</td>${
      ttc ? `<td>${this._moneyCell(this._ttcFb(fbN))}</td>` : ""
    }</tr>`;
    html += `<tr><td class="xl-tag">N-F&B</td><td>${cellNf}</td>${
      ttc ? `<td>${this._moneyCell(this._ttcNf(nfN))}</td>` : ""
    }</tr>`;
    if (total) {
      html += `<tr class="is-total"><td>TOTAL</td><td>${this._moneyCell(tot, {
        total: true,
      })}</td>${
        ttc
          ? `<td>${this._moneyCell(
              fbN != null && nfN != null
                ? this._ttcFb(fbN) + this._ttcNf(nfN)
                : null,
              { total: true }
            )}</td>`
          : ""
      }</tr>`;
    }
    html += `</tbody></table>`;
    return html;
  }

  _costLinesHtml(side) {
    const lines = side?.cost_lines || [];
    if (!lines.length) {
      return this._kv("TOTAL coûts / mois", this._moneyCell(side?.cout_mensuel, { total: true }));
    }
    const byGroup = { techno: [], annexes: [], agencement: [], other: [] };
    lines.forEach((ln) => {
      const g = (ln.group || "other").toLowerCase();
      if (byGroup[g]) byGroup[g].push(ln);
      else byGroup.other.push(ln);
    });
    const titles = {
      techno: "COUTS TECHNO",
      annexes: "COUTS ANNEXES",
      agencement: "COUTS AGENCEMENT",
      other: "AUTRES",
    };
    let html = "";
    for (const [g, arr] of Object.entries(byGroup)) {
      if (!arr.length) continue;
      html += `<div class="xl-cost-group"><div class="xl-cost-h">${titles[g]}</div>`;
      arr.forEach((ln) => {
        html += this._kv(
          ln.label || ln.id || "—",
          this._moneyCell(ln.monthly) +
            (ln.capex != null
              ? ` <span class="xl-hint">capex ${escapeHtml(euro(ln.capex))}</span>`
              : "")
        );
      });
      html += `</div>`;
    }
    html += this._kv(
      "TOTAL coûts / mois",
      this._moneyCell(side?.cout_mensuel, { total: true })
    );
    html += this._kv("Capex total", this._moneyCell(side?.capex));
    return html;
  }

  _ruleBanner(num, title, color) {
    return `
      <div class="xl-rule-banner xl-${color}">
        <div class="xl-rule-num">REGLE N°${num}</div>
        <div class="xl-rule-title">${escapeHtml(title)}</div>
      </div>`;
  }

  _sectionBanner(title, color) {
    return `<div class="xl-section-banner xl-${color}">${escapeHtml(title)}</div>`;
  }

  /** Feuille Excel REVENUS ► MIX PRODUITS (par concept). */
  _renderMixSheet(concept, data) {
    if (!data) return "";
    const pilots = data.pilots || [];
    const moy = data.moyenne || {};
    const pilotRows = pilots
      .map((p) => {
        const pond =
          p.margin_affichee != null ? p.margin_affichee : p.margin_ponderee;
        return `
        <tr>
          <td class="xl-pilot-lab">${escapeHtml(p.label || p.hotel_code || "")}</td>
          <td>${this._pctCell(p.mix_fb, 0)}</td>
          <td>${this._pctCell(p.mix_nf, 0)}</td>
          <td class="xl-strong">100 %</td>
          <td>${this._numCell(p.margin_fb, 2)}</td>
          <td class="xl-hi">${
            p.margin_nf == null ? "—" : this._numCell(p.margin_nf, 2)
          }</td>
          <td class="xl-strong">${this._numCell(
            p.margin_ponderee != null
              ? p.margin_ponderee
              : p.margin_fb != null && p.mix_fb != null
                ? p.margin_fb * p.mix_fb +
                  (p.margin_nf || 0) * (p.mix_nf || 0)
                : null,
            2
          )}</td>
          <td class="xl-red-cell">${this._numCell(pond, 2)}</td>
        </tr>`;
      })
      .join("");
    return `
      <details class="xl-ref-sheet" open>
        <summary>REVENUS ► MIX PRODUITS · ${escapeHtml(concept)} STORE</summary>
        <p class="xl-ref-note">Tous les pilotes de la solution (moyenne train à poids égaux).
          Source : <em>simulateur_data</em> / ventes live.
          Le mix ci-dessous alimente la colonne gauche et la règle 2.</p>
        <table class="xl-ref-table">
          <thead>
            <tr>
              <th>Pilote</th>
              <th>MIX F&amp;B</th><th>MIX N-F&amp;B</th><th>TOTAL</th>
              <th>MARGE F&amp;B</th><th>MARGE N-F&amp;B</th><th>PONDÉRÉE</th>
              <th>AFFICHÉE</th>
            </tr>
          </thead>
          <tbody>
            ${pilotRows}
            <tr class="is-moy">
              <td><strong>MOYENNE</strong></td>
              <td>${this._pctCell(moy.mix_fb, 0)}</td>
              <td>${this._pctCell(moy.mix_nf, 0)}</td>
              <td class="xl-strong">100 %</td>
              <td>${this._numCell(moy.margin_fb, 2)}</td>
              <td class="xl-hi">${this._numCell(moy.margin_nf, 2)}</td>
              <td class="xl-strong">${this._numCell(moy.margin_ponderee, 2)}</td>
              <td class="xl-red-cell">${this._numCell(moy.margin_ponderee, 2)}</td>
            </tr>
          </tbody>
        </table>
      </details>`;
  }

  /** Feuille Excel REVENUS ► IMPACT TO (par concept). */
  _renderImpactSheet(concept, data) {
    if (!data) return "";
    const pilots = data.pilots || [];
    const moy = data.moyenne || {};
    const imp = data.impact_1pct || {};
    const pilotRows = pilots
      .map(
        (p) => `
        <tr>
          <td class="xl-pilot-lab">${escapeHtml(p.label || "")}</td>
          <td class="xl-red-cell">${this._pctCell(p.to, 0)}</td>
          <td>${this._moneyCell(p.ca_ht_fb)}</td>
          <td>${this._moneyCell(p.ca_ht_nf)}</td>
          <td class="xl-red-cell">${this._moneyCell(p.ca_ht_total, {
            total: true,
          })}</td>
          <td>${this._moneyCell(p.ca_ttc_fb)}</td>
          <td>${this._moneyCell(p.ca_ttc_nf)}</td>
          <td class="xl-red-cell">${this._moneyCell(p.ca_ttc_total, {
            total: true,
          })}</td>
        </tr>`
      )
      .join("");
    const showMoy = pilots.length > 1;
    return `
      <details class="xl-ref-sheet" open>
        <summary>REVENUS ► TAUX D'OCCUPATION · ${escapeHtml(
          concept
        )} STORE</summary>
        <p class="xl-ref-note">CA pilotes et impact +1 point de TO
          (feuille Excel <em>REVENUS - IMPACT TO</em>).
          Sert à calibrer l'impact TO avant Règle 1.</p>
        <table class="xl-ref-table">
          <thead>
            <tr>
              <th rowspan="2">Pilote</th>
              <th rowspan="2">TO MOYEN</th>
              <th colspan="3">CA HT</th>
              <th colspan="3">CA TTC</th>
            </tr>
            <tr>
              <th>F&amp;B</th><th>N-F&amp;B</th><th>TOTAL</th>
              <th>F&amp;B</th><th>N-F&amp;B</th><th>TOTAL</th>
            </tr>
          </thead>
          <tbody>
            ${pilotRows}
            ${
              showMoy
                ? `<tr class="is-moy">
              <td><strong>MOYENNE</strong></td>
              <td class="xl-red-cell">${this._pctCell(moy.to, 0)}</td>
              <td>${this._moneyCell(moy.ca_ht_fb)}</td>
              <td>${this._moneyCell(moy.ca_ht_nf)}</td>
              <td class="xl-red-cell">${this._moneyCell(moy.ca_ht_total, {
                total: true,
              })}</td>
              <td>${this._moneyCell(moy.ca_ttc_fb)}</td>
              <td>${this._moneyCell(moy.ca_ttc_nf)}</td>
              <td class="xl-red-cell">${this._moneyCell(moy.ca_ttc_total, {
                total: true,
              })}</td>
            </tr>`
                : ""
            }
            <tr class="is-impact">
              <td><strong>IMPACT</strong></td>
              <td class="xl-hi"><strong>1 %</strong></td>
              <td class="xl-hi">${this._moneyCell(imp.ca_ht_fb)}</td>
              <td class="xl-hi">${this._moneyCell(imp.ca_ht_nf)}</td>
              <td class="xl-hi">${this._moneyCell(imp.ca_ht_total, {
                total: true,
              })}</td>
              <td class="xl-hi">${this._moneyCell(imp.ca_ttc_fb)}</td>
              <td class="xl-hi">${this._moneyCell(imp.ca_ttc_nf)}</td>
              <td class="xl-hi">${this._moneyCell(imp.ca_ttc_total, {
                total: true,
              })}</td>
            </tr>
          </tbody>
        </table>
      </details>`;
  }

  renderConcept() {
    const host = $("#rx-panels");
    const kpiBar = $("#rx-kpi-bar");
    if (!host) return;
    if (!this.result?.ok) {
      this._showPlaceholder(
        "Simulation indisponible",
        this.result?.error || "Lancez le calcul (hôtel désigné requis)."
      );
      return;
    }
    const block = this.result.concepts?.[this.concept];
    if (!block) {
      this._showPlaceholder(
        `Pas de données pour ${this.concept}`,
        `Concepts reçus : ${Object.keys(this.result.concepts || {}).join(", ") || "aucun"}`
      );
      return;
    }

    const concept = this.concept;
    const left = block.left || {};
    const right = block.right || {};
    const steps = block.steps || [];
    const excel = block.excel_base || {};
    const np = !!right.not_profitable;

    // KPI strip
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
      const warns = (this.result.validation_warnings || [])
        .map((w) => `<div class="rx-kpi-item rx-kpi-warn"><span>⚠</span><strong>${escapeHtml(
          w
        )}</strong></div>`)
        .join("");
      const src =
        block.baseline_source ||
        block.source ||
        excel.baseline_source ||
        "";
      const srcLabel = String(src).startsWith("simulateur_data")
        ? "simulateur_data.xlsx"
        : src
          ? String(src)
          : "rod_reference";
      // Bandeau contextuel uniquement (pas le résultat final CA/marge —
      // ceux-ci apparaissent en bas de feuille après R1→R4).
      kpiBar.innerHTML = `
        ${recoHtml}${warns}
        <div class="rx-kpi-item"><span>Source pilote</span><strong title="${escapeHtml(
          src
        )}">${escapeHtml(srcLabel)}</strong></div>
        <div class="rx-kpi-item"><span>Pilotes</span><strong>${escapeHtml(
          pilots || "—"
        )}</strong></div>
        <div class="rx-kpi-item"><span>CA base pilotes</span><strong>${euro(
          k.left_ca_ht
        )}</strong></div>
      `;
    }

    // Left pilot CA base (Excel E34/E35) — éditables via pilot_overrides
    const lFb =
      this._num(this._pilotVal("ca_fb", excel, left)) ?? this._num(left.ca_fb);
    const lNf =
      this._num(this._pilotVal("ca_nf", excel, left)) ?? this._num(left.ca_nf);
    const lVentes =
      this._num(this._pilotVal("nb_ventes", excel, left)) ??
      this._num(left.nbr_ventes);
    const rFb = this._num(right.ca_fb);
    const rNf = this._num(right.ca_nf);
    // R1 intermediate (clients pilote — recalculés si override n/TO/g)
    const lCm =
      this._num(excel.clients_mois) ??
      this._num(this._sideVal(left, "clients_mois"));
    const rCm = this._num(this._sideVal(right, "clients_mois"));
    const tauxAch =
      lCm && lVentes != null && lCm > 0 ? lVentes / lCm : null;
    const r1BuyL = lVentes;
    const r1BuyR =
      rCm != null && tauxAch != null ? rCm * tauxAch : this._num(right.nbr_ventes);
    const r1Factor =
      lCm && rCm && lCm > 0 ? rCm / lCm : 1;
    const r1Fb = lFb != null ? lFb * r1Factor : null;
    const r1Nf = lNf != null ? lNf * r1Factor : null;
    const pilotMixFb =
      this._num(this._pilotVal("mix_fb", excel, left)) ??
      this._num(this._sideVal(left, "mix_fb")) ??
      0.4;
    const pilotMixNf =
      this._num(this._pilotVal("mix_nf", excel, left)) ??
      this._num(this._sideVal(left, "mix_nf")) ??
      1 - pilotMixFb;

    // Categories from meta for R3 display
    const needs = this.result.params?.client_needs || {};
    const fbCats = (this.meta?.client_needs_fb || [])
      .map((c) => {
        const on = needs[c.id] !== false;
        return `<tr class="${on ? "is-on" : "is-off"}">
          <td>${escapeHtml(c.label || c.id)}</td>
          <td class="xl-coef">${this._pctCell(c.coef, 0)}</td>
          <td class="xl-coef">${this._numCell(c.coef, 2)}</td>
          <td>${on ? "✓" : "—"}</td>
        </tr>`;
      })
      .join("");
    const nfCats = (this.meta?.client_needs_nfb || [])
      .map((c) => {
        const on = needs[c.id] !== false;
        const life = [
          "nfb_cosmetics",
          "nfb_kids",
          "nfb_apparel",
          "nfb_accessories",
          "nfb_souvenirs",
        ].includes(c.id);
        return `<tr class="${on ? "is-on" : "is-off"}${life ? " is-life" : ""}">
          <td>${escapeHtml(c.label || c.id)}</td>
          <td class="xl-coef">${this._pctCell(c.coef, 0)}</td>
          <td class="xl-coef">${this._numCell(c.coef, 2)}</td>
          <td>${on ? "✓" : "—"}</td>
        </tr>`;
      })
      .join("");

    const mlL =
      this._num(this._pilotVal("m_lin", excel, left)) ??
      this._num(this._sideVal(left, "m_lin"));
    const mlR = this._num(this._sideVal(right, "m_lin"));
    const diffMl =
      mlL != null && mlR != null ? mlR - mlL : this._num(this._stepRow(steps, "r4", "Diff. ML").right);

    const storeName = `${concept} STORE`;
    const pilotList = (block.pilots || [])
      .map((p) => p.label || p.hotel_code)
      .filter(Boolean);
    const nPilots = pilotList.length || block.n_pilots || 0;
    const leftHead =
      nPilots > 1
        ? `MOYENNE RESULTATS PILOTES (${nPilots} hôtels · ${pilotList.join(" + ")})`
        : nPilots === 1
          ? `MOYENNE RESULTATS PILOTE (${pilotList[0] || "—"})`
          : "MOYENNE RESULTATS PILOTES";

    const mixData =
      block.sheet_mix ||
      this.result.sheets?.mix_products?.[concept] ||
      this.meta?.sheets?.mix_products?.[concept];
    const impactData =
      block.sheet_impact_to ||
      this.result.sheets?.impact_to?.[concept] ||
      this.meta?.sheets?.impact_to?.[concept];

    host.innerHTML = `
<div class="xl-sheet" data-concept="${escapeHtml(concept)}">
  <div class="xl-main-title">SIMULATEUR ROD : REVENUS / MARGE NETTE / AMORTISSEMENT</div>
  <div class="xl-store-bar">${escapeHtml(storeName)}</div>

  <!-- Feuilles Excel annexe (captures MIX + IMPACT TO) -->
  <div class="xl-ref-block">
    ${this._renderMixSheet(concept, mixData)}
    ${this._renderImpactSheet(concept, impactData)}
  </div>

  <div class="xl-col-heads">
    <div class="xl-col-h left">${escapeHtml(leftHead)}</div>
    <div class="xl-col-h right">SIMULATEUR</div>
  </div>

  <!-- PARAMS -->
  <div class="xl-dual">
    <div class="xl-pane left">${this._paramsBlock(left, concept, true, excel)}</div>
    <div class="xl-pane right">${this._paramsBlock(right, concept, false, null)}</div>
  </div>
  <div class="xl-dual">
    <div class="xl-pane left">${this._moyenneBlock(left, true, excel)}</div>
    <div class="xl-pane right">${this._moyenneBlock(right, false, null)}</div>
  </div>

  ${this._ruleBanner(1, "REVENUS CALCULES EN FONCTION DU NB. DE CLIENTS ACHETEURS", "pink")}
  <div class="xl-dual">
    <div class="xl-pane left">
      <p class="xl-comment"><strong>REGLE 1 =</strong> Chaque client acheteur génère du CA.<br>
      Les montants de CA ci-dessous sont basés sur le résultat des pilotes <strong>${escapeHtml(
        concept
      )}</strong>.</p>
      ${this._kv("Clients acheteurs / mois", this._numCell(r1BuyL, 0))}
      ${this._caTable(lFb, lNf, { ttc: true, editable: true })}
    </div>
    <div class="xl-pane right">
      ${this._kv("Clients acheteurs / mois", this._numCell(r1BuyR, 0))}
      ${this._caTable(r1Fb, r1Nf, { ttc: false })}
    </div>
  </div>

  ${this._ruleBanner(2, "REVENUS POUR 10% (DE PLUS OU DE MOINS) DE MIX PRODUITS", "pink")}
  <div class="xl-dual">
    <div class="xl-pane left">
      <p class="xl-comment"><strong>REGLE 2 =</strong> Chaque 10% de MIX PDT en plus ou en moins impacte le CA.<br>
      Cette règle impacte le CA F&B et le CA N-F&B, aussi bien en « bonus » qu'en « malus »
      pour chaque 10% de plus ou de moins par rapport au <strong>MIX PDT DE REFERENCE</strong>
      du ${escapeHtml(concept)} STORE.</p>
      <div class="xl-muted">Unités d'impact (réf. pilote / 10 % de mix)</div>
      ${this._caTable(
        lFb != null && pilotMixFb ? (lFb * 0.1) / pilotMixFb : null,
        lNf != null && pilotMixNf ? (lNf * 0.1) / pilotMixNf : null
      )}
    </div>
    <div class="xl-pane right">
      ${this._kv(
        "Diff. F&B",
        this._pctCell(
          (this._num(this._sideVal(right, "mix_fb")) || 0) - (pilotMixFb || 0),
          0
        )
      )}
      ${this._kv(
        "Nb. de × 10%",
        this._numCell(
          ((this._num(this._sideVal(right, "mix_fb")) || 0) - (pilotMixFb || 0)) *
            10,
          1
        )
      )}
      ${this._kv(
        "Steps mix (R2)",
        this._numCell(this._stepRow(steps, "r2", "Steps ×10% F&B").right, 2) +
          " / " +
          this._numCell(this._stepRow(steps, "r2", "Steps ×10% N-F&B").right, 2)
      )}
    </div>
  </div>

  ${this._ruleBanner(3, "INFLUENCE DES CATEGORIES DE PRODUITS SELECTIONNEES PAR L'HOTEL", "pink")}
  <div class="xl-r3-wrap">
    <p class="xl-comment"><strong>REGLE 3 =</strong>
      Si la catégorie est cochée <strong>+X%</strong> sur le CA ·
      Si la catégorie n'est pas cochée <strong>−X%</strong> sur le CA
    </p>
    <p class="xl-comment xl-note">* Pour les hôtels de <strong>≥ 50 chambres</strong> : si
      <strong>au moins 1 des 5 catégories</strong> lifestyle N-F&B est cochée
      (Cosmétiques, Articles enfants, Prêt-à-porter, Accessoires, Souvenirs)
      → solution recommandée = <strong>LIBERTY</strong>.
      Les 3 solutions restent toujours calculées (P&amp;L informatif).
      Les % Excel sont des exemples de parts sur le <em>total</em> des ventes ;
      en modélisation, mix = nb_ventes(sous-cat) / nb_ventes(total) → somme ≈ 100&nbsp;%.</p>
    <div class="xl-cats-grid">
      <div>
        <div class="xl-cats-h">CATEGORIES F&amp;B</div>
        <table class="xl-cats"><thead><tr><th>Catégorie</th><th>%</th><th>Coef</th><th>ON</th></tr></thead>
        <tbody>${fbCats}</tbody></table>
      </div>
      <div>
        <div class="xl-cats-h">CATEGORIES NON-F&amp;B</div>
        <table class="xl-cats"><thead><tr><th>Catégorie</th><th>%</th><th>Coef</th><th>ON</th></tr></thead>
        <tbody>${nfCats}</tbody></table>
      </div>
    </div>
    <div class="xl-dual" style="margin-top:.75rem">
      <div class="xl-pane left">
        ${this._kv("Cumul F&B max", this._pctCell(0.48, 0) + " · " + this._numCell(0.48, 2))}
        ${this._kv("Cumul N-F&B (HTML)", this._pctCell(0.19, 0) + " · " + this._numCell(0.19, 2))}
      </div>
      <div class="xl-pane right">
        <div class="xl-section-label">APPLICATION DE LA REGLE 3</div>
        <p class="xl-comment">Δ F&B = ${this._numCell(
          this._stepRow(steps, "r3", "Δ F&B vs baseline").right,
          3
        )} ·
        Δ N-F&B = ${this._numCell(
          this._stepRow(steps, "r3", "Δ N-F&B vs baseline").right,
          3
        )}</p>
        <p class="xl-comment xl-warn">Attention : si le CA de l'étape précédente est négatif,
        sélectionner de nombreuses catégories permet de « réduire » la perte de CA.</p>
      </div>
    </div>
  </div>

  ${this._ruleBanner(4, "REVENUS POUR 1 METRE LINEAIRE (DE PLUS OU DE MOINS)", "pink")}
  <div class="xl-dual">
    <div class="xl-pane left">
      <p class="xl-comment"><strong>REGLE 4 =</strong> Chaque mètre linéaire en plus ou en moins impacte le CA.<br>
      Référence <strong>${escapeHtml(String(mlL ?? 6))} mètres lin.</strong> (${escapeHtml(
        concept
      )}).</p>
      ${this._caTable(
        lFb != null && mlL ? lFb / mlL : null,
        lNf != null && mlL ? lNf / mlL : null
      )}
      <div class="xl-muted">CA HT par mètre linéaire (réf. pilote)</div>
    </div>
    <div class="xl-pane right">
      <p class="xl-comment xl-warn">Si le nb. de mètres lin. est supérieur à la référence,
      la formule ajoute du CA (sinon retire du CA).<br>
      >> Plus l'hôtel augmente le nb. de ML, plus le CA augmente.</p>
      ${this._kv("Diff. ML", this._numCell(diffMl, 0))}
      ${this._kv("|Diff. ML|", this._numCell(diffMl != null ? Math.abs(diffMl) : null, 0))}
      ${this._kv("M. lin. hôtel", this._numCell(mlR, 0))}
      ${this._kv("M. lin. ref", this._numCell(mlL, 0))}
    </div>
  </div>

  ${this._sectionBanner("REVENUS", "green")}
  <div class="xl-dual">
    <div class="xl-pane left">
      ${this._kv("REVENUS POUR", this._numCell(r1BuyL, 0) + " ACHETEURS / MOIS")}
      ${this._caTable(lFb, lNf, { ttc: true, total: true })}
    </div>
    <div class="xl-pane right">
      ${this._kv("REVENUS POUR", this._numCell(r1BuyR, 0) + " ACHETEURS / MOIS")}
      ${this._caTable(rFb, rNf, { ttc: false, total: true, np })}
    </div>
  </div>

  ${this._sectionBanner("MARGE PRODUITS MENSUELLE", "green")}
  <div class="xl-dual">
    <div class="xl-pane left">
      <p class="xl-comment">Marge = CA − CA/coef (coefs marge F&B / N-F&B)</p>
      ${this._kv("Marge produit / mois", this._moneyCell(left.marge_produit, { total: true }))}
    </div>
    <div class="xl-pane right">
      ${this._kv(
        "Marge produit / mois",
        this._moneyCell(right.marge_produit, { total: true, np })
      )}
    </div>
  </div>

  ${this._sectionBanner("COUTS MENSUELS", "yellow")}
  <div class="xl-dual">
    <div class="xl-pane left">${this._costLinesHtml(left)}</div>
    <div class="xl-pane right">${this._costLinesHtml(right)}</div>
  </div>

  ${this._sectionBanner("MARGE NETTE MENSUELLE", "pink")}
  <div class="xl-dual">
    <div class="xl-pane left">
      <p class="xl-comment">Formule = (marge produits mensuelle − coûts mensuels)</p>
      ${this._kv("TOTAL HT", this._moneyCell(left.marge_nette, { total: true }))}
      ${this._kv(
        "TAUX",
        this._pctCell(
          this._num(left.marge_nette) != null &&
            this._num(left.ca_ht) > 0
            ? this._num(left.marge_nette) / this._num(left.ca_ht)
            : null,
          0
        )
      )}
    </div>
    <div class="xl-pane right">
      ${this._kv(
        "TOTAL HT",
        this._moneyCell(right.marge_nette_num ?? right.marge_nette, {
          total: true,
          np,
        })
      )}
      ${this._kv(
        "TAUX",
        np
          ? `<span class="xl-np">N/A</span>`
          : this._pctCell(
              this._num(right.marge_nette_num ?? right.marge_nette) != null &&
                this._num(right.ca_ht_num ?? right.ca_ht) > 0
                ? this._num(right.marge_nette_num ?? right.marge_nette) /
                  this._num(right.ca_ht_num ?? right.ca_ht)
                : null,
              0
            )
      )}
    </div>
  </div>

  ${this._sectionBanner("AMORTISSEMENT", "blue")}
  <div class="xl-dual">
    <div class="xl-pane left">
      <p class="xl-comment">Formule = (coût total / marge nette mensuelle)</p>
      ${this._kv("TOTAL", this._numCell(left.amort_mois, 0), "mois")}
      ${this._kv("", this._numCell(left.amort_ans, 1), "ans")}
    </div>
    <div class="xl-pane right">
      ${this._kv(
        "TOTAL",
        np ? `<span class="xl-np">N/A</span>` : this._numCell(right.amort_mois, 0),
        "mois"
      )}
      ${this._kv(
        "",
        np ? `<span class="xl-np">N/A</span>` : this._numCell(right.amort_ans, 1),
        "ans"
      )}
    </div>
  </div>

  <p class="xl-method">${escapeHtml(block.method || "")}</p>
  ${(this.result.recommendation_reasons || [])
    .map((r) => `<p class="xl-reco-reason">→ ${escapeHtml(r)}</p>`)
    .join("")}
</div>`;
    this._wirePilotEdits(host);
  }
}
