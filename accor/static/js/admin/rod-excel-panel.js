/**
 * Simulateur Excel ROD — 3 onglets SIMPLY / LIBERTY / CONNECTED.
 *
 * Layout Excel :
 *   gauche = moyenne pilotes de la solution
 *   droite = projection hôtel désigné
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

const CONCEPTS = ["SIMPLY", "LIBERTY", "CONNECTED"];

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
    const pct = Number($("#rx-mix-fb")?.value || 70);
    const el = $("#rx-mix-nf-label");
    if (el) el.textContent = `N-F&B = ${100 - pct} %`;
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
    if (this._simBusy) return;
    this._simBusy = true;
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
      this._activateConceptTab();
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
    }
  }

  _activateConceptTab() {
    $$("#rx-concept-tabs .rod-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.rxConcept === this.concept);
    });
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
      kpiBar.innerHTML = `
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

    const steps = block.steps || [];
    host.innerHTML = `
      <div class="rx-dual-head">
        <div class="rx-col-head left">
          <div class="rx-col-title">MOYENNE RESULTATS PILOTES</div>
          <div class="rx-col-sub">${escapeHtml(block.label || this.concept)}</div>
        </div>
        <div class="rx-col-head right">
          <div class="rx-col-title">SIMULATEUR</div>
          <div class="rx-col-sub">${escapeHtml(
            this.result.hotel_code || ""
          )} · hôtel désigné</div>
        </div>
      </div>
      ${steps
        .map((st) => {
          const hl = st.highlight ? " is-highlight" : "";
          return `
        <section class="rx-step${hl}" data-step="${escapeHtml(st.id)}">
          <header class="rx-step-head">
            <h3>${escapeHtml(st.title || st.id)}</h3>
          </header>
          ${
            st.comment
              ? `<div class="rx-comment">${escapeHtml(st.comment).replace(
                  /\n/g,
                  "<br>"
                )}</div>`
              : ""
          }
          <div class="rx-dual-grid">
            <div class="rx-col left">${this._rowsHtml(st.left_rows)}</div>
            <div class="rx-col right">${this._rowsHtml(st.right_rows)}</div>
          </div>
        </section>`;
        })
        .join("")}
      <p class="muted small rx-method">${escapeHtml(block.method || "")}</p>
    `;
  }

  _rowsHtml(rows) {
    if (!rows || !rows.length) return `<div class="rx-row empty">—</div>`;
    return rows
      .map((r) => {
        const v = r.value;
        let display;
        if (v == null || v === "—") display = "—";
        else if (typeof v === "number") display = fmt(v, 4);
        else display = String(v);
        // euro-ish labels
        if (
          typeof v === "number" &&
          /CA|Marge|coût|Cout|Capex|TOTAL/i.test(r.label || "")
        ) {
          display = euro(v);
        }
        return `
        <div class="rx-row">
          <span class="rx-label">${escapeHtml(r.label || "")}</span>
          <span class="rx-value">${escapeHtml(display)}</span>
          ${
            r.hint
              ? `<span class="rx-hint">${escapeHtml(r.hint)}</span>`
              : ""
          }
        </div>`;
      })
      .join("");
  }
}
