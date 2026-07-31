/**
 * Simulateur ROD — admin (pilotes + éval temporelle).
 *
 * Recalcul auto dès qu'un paramètre change (pas de bouton Simuler).
 * Split temporel : ref hors 2026, éval 2026. Pas d'exclusion d'hôtel.
 *
 * Onglets :
 *   - CA (règles)     : étapes ROD
 *   - Coûts & marge   : étude économique
 *   - Écart réel/sim  : validation vs ventes réelles (séparé)
 *   - Batch           : MAE sur tous les pilotes
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

export class RodSimPanel {
  constructor(state, nav) {
    this.state = state;
    this.nav = nav;
    this.pilots = null;
    this.meta = null;
    this.trace = null;
    this.evalResult = null;
    this.concept = "SIMPLY";
    this.tab = "ca";
    this._simBusy = false;
    this._simQueued = false;
    this._evalBusy = false;
    this._paramsTouched = false;
    this._simSeq = 0;
    this._progressTimer = null;
    this._progressPct = 0;
    this._openBusy = false;
  }

  async open() {
    // Re-clic pendant chargement → ignoré
    if (this._openBusy) return;
    // Déjà ouvert et chargé → afficher seulement (pas de rechargement)
    if (this.state.panel === "rod-sim" && this.meta != null && this.pilots != null) {
      this.nav.showRodSimPanel();
      return;
    }
    if (!this.state.confirmLeaveDirty()) return;
    this._openBusy = true;
    this.nav.setNavBusy("rod", true);
    try {
      this.nav.showRodSimPanel();
      await this.loadMeta();
      await this.loadPilots();
    } finally {
      this._openBusy = false;
      this.nav.setNavBusy("rod", false);
    }
  }

  year() {
    return Number($("#rod-year")?.value || 2026);
  }

  setStatus(msg) {
    const status = $("#rod-status");
    if (status) status.textContent = msg || "";
  }

  /**
   * Barre de progression type Model Build (visible, animée).
   * Indéterminée côté API → on simule l'avancement par phases.
   */
  _stopProgressTick() {
    if (this._progressTimer) {
      clearInterval(this._progressTimer);
      this._progressTimer = null;
    }
  }

  /**
   * @param {"sim"|"batch"|"load"} mode
   * @param {string} [detail]
   */
  startProgress(mode = "sim", detail = "") {
    const card = $("#rod-progress-card");
    const wrap = $("#rod-progress");
    const fill = $("#rod-progress-fill");
    const pctEl = $("#rod-progress-pct");
    const phaseEl = $("#rod-progress-phase");
    const textEl = $("#rod-progress-text");
    const detailEl = $("#rod-progress-detail");
    const bar = $("#rod-progress-bar");
    const layout = document.querySelector(".rod-layout");

    if (card) card.classList.remove("hidden");
    if (card) card.classList.add("is-active");
    if (wrap) {
      wrap.classList.remove("is-done", "is-error");
      wrap.classList.add("is-running");
    }
    if (layout) layout.classList.add("is-calculating");

    const phases =
      mode === "batch"
        ? [
            { until: 15, label: "Pilotes", text: "Chargement des hôtels pilotes…" },
            { until: 40, label: "Ref catégorie", text: "Moyennes catégorie (train)…" },
            { until: 75, label: "Simulation", text: "Règles ROD · tous les pilotes…" },
            { until: 92, label: "Métriques", text: "MAE · écarts · reco…" },
          ]
        : mode === "load"
          ? [
              { until: 30, label: "Données", text: "Chargement pilotes…" },
              { until: 70, label: "Liste", text: "Préparation de la liste…" },
              { until: 90, label: "Prêt", text: "Finalisation…" },
            ]
          : [
              { until: 12, label: "Prépare", text: "Lecture contexte hôtel désigné…" },
              { until: 28, label: "Référence", text: "Moyenne catégorie (années train)…" },
              { until: 55, label: "CA", text: "Règles ROD · CA HT…" },
              { until: 78, label: "Coûts", text: "Coûts · marges · 3 solutions…" },
              { until: 92, label: "Reco", text: "Recommandation concept…" },
            ];

    this._progressPct = 0;
    this._progressPhases = phases;
    if (phaseEl) {
      phaseEl.textContent = phases[0].label;
      phaseEl.dataset.phase = "prepare";
    }
    if (textEl) textEl.textContent = phases[0].text;
    if (detailEl) detailEl.textContent = detail || "";
    if (pctEl) pctEl.innerHTML = "0&nbsp;%";
    if (fill) fill.style.width = "0%";
    if (bar) bar.setAttribute("aria-valuenow", "0");
    this.setStatus(mode === "batch" ? "Batch en cours…" : "Calcul en cours…");

    this._stopProgressTick();
    this._progressTimer = setInterval(() => {
      // asymptote vers 92 % tant que la requête n'est pas finie
      const cap = 92;
      const step = this._progressPct < 40 ? 2.2 : this._progressPct < 70 ? 1.1 : 0.45;
      this._progressPct = Math.min(cap, this._progressPct + step);
      const pct = Math.round(this._progressPct);
      if (pctEl) pctEl.innerHTML = `${pct}&nbsp;%`;
      if (fill) fill.style.width = `${this._progressPct}%`;
      if (bar) bar.setAttribute("aria-valuenow", String(pct));
      const ph = (this._progressPhases || []).find((p) => this._progressPct <= p.until)
        || (this._progressPhases || []).slice(-1)[0];
      if (ph) {
        if (phaseEl) phaseEl.textContent = ph.label;
        if (textEl) textEl.textContent = ph.text;
      }
    }, 180);
  }

  /**
   * @param {"done"|"error"} state
   * @param {string} [message]
   * @param {string} [detail]
   */
  finishProgress(state = "done", message = "", detail = "") {
    this._stopProgressTick();
    const card = $("#rod-progress-card");
    const wrap = $("#rod-progress");
    const fill = $("#rod-progress-fill");
    const pctEl = $("#rod-progress-pct");
    const phaseEl = $("#rod-progress-phase");
    const textEl = $("#rod-progress-text");
    const detailEl = $("#rod-progress-detail");
    const bar = $("#rod-progress-bar");
    const layout = document.querySelector(".rod-layout");

    if (layout) layout.classList.remove("is-calculating");
    if (wrap) {
      wrap.classList.remove("is-running");
      wrap.classList.toggle("is-done", state === "done");
      wrap.classList.toggle("is-error", state === "error");
    }
    if (fill) fill.style.width = "100%";
    if (pctEl) pctEl.innerHTML = state === "done" ? "100&nbsp;%" : "—";
    if (bar) bar.setAttribute("aria-valuenow", state === "done" ? "100" : "0");
    if (phaseEl) {
      phaseEl.textContent = state === "done" ? "Terminé" : "Erreur";
      phaseEl.dataset.phase = state === "done" ? "done" : "error";
    }
    if (textEl) textEl.textContent = message || (state === "done" ? "Simulation terminée" : "Échec");
    if (detailEl) detailEl.textContent = detail || "";

    // masquer la barre après un court délai si succès
    if (state === "done") {
      setTimeout(() => {
        if (this._simBusy || this._evalBusy) return;
        if (card) {
          card.classList.add("hidden");
          card.classList.remove("is-active");
        }
        if (wrap) wrap.classList.remove("is-done", "is-error");
      }, 900);
    } else {
      // garder visible en erreur jusqu'au prochain calcul
      if (card) card.classList.add("is-active");
    }
  }

  async loadMeta() {
    try {
      this.meta = await api.get("/api/rod/meta");
      this.renderNeedsToggles(this.meta);
      const d = this.meta.defaults || {};
      if (!$("#rod-m-lin")?.value) {
        this.setMLin(d.m_lin ?? 6);
      }
      if (!$("#rod-mix-fb")?.value) {
        this.setMix(Math.round((d.mix_fb ?? 0.7) * 100));
      }
    } catch (err) {
      console.error(err);
      toast.show(err.message, "err");
    }
  }

  renderNeedsToggles(meta) {
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
          <span class="switch" title="${on ? "Désactiver" : "Activer"}">
            <input type="checkbox" role="switch" data-need="${escapeHtml(it.id)}"
              aria-label="${escapeHtml(it.label || it.id)}"
              ${on ? "checked" : ""} />
            <span aria-hidden="true"></span>
          </span>
        </label>`;
        })
        .join("");
      host.querySelectorAll(".rod-need-item").forEach((item) => {
        const input = item.querySelector("input[data-need]");
        if (!input) return;
        input.addEventListener("change", () => {
          syncState(item);
          const sw = item.querySelector(".switch");
          if (sw) sw.title = input.checked ? "Désactiver" : "Activer";
          this._paramsTouched = true;
          this.scheduleSim();
        });
      });
    };
    fill("rod-needs-fb", meta.client_needs_fb);
    fill("rod-needs-nfb", meta.client_needs_nfb);
  }

  setNeedsAll(on) {
    $$("#rod-needs-fb input[data-need], #rod-needs-nfb input[data-need]").forEach(
      (el) => {
        el.checked = !!on;
        const item = el.closest(".rod-need-item");
        if (item) {
          item.classList.toggle("is-on", !!on);
          item.classList.toggle("is-off", !on);
          const st = item.querySelector(".rod-need-state");
          if (st) st.textContent = on ? "Autorisé" : "Interdit";
          const sw = item.querySelector(".switch");
          if (sw) sw.title = on ? "Désactiver" : "Activer";
        }
      }
    );
    this._paramsTouched = true;
    this.scheduleSim();
  }

  collectNeeds() {
    const needs = {};
    $$("#rod-needs-fb input[data-need], #rod-needs-nfb input[data-need]").forEach(
      (el) => {
        needs[el.dataset.need] = !!el.checked;
      }
    );
    return needs;
  }

  setMLin(v) {
    const n = Number(v);
    const slider = $("#rod-m-lin-slider");
    const input = $("#rod-m-lin");
    if (slider) slider.value = String(n);
    if (input) input.value = String(n);
  }

  setMix(pct) {
    const p = Math.min(100, Math.max(0, Number(pct)));
    const slider = $("#rod-mix-slider");
    const input = $("#rod-mix-fb");
    if (slider) slider.value = String(p);
    if (input) input.value = String(p);
    const nf = $("#rod-mix-nf-label");
    if (nf) nf.textContent = `N-F&B = ${100 - p} %`;
  }

  collectParams() {
    const mixPct = Number($("#rod-mix-fb")?.value ?? 70);
    const mLin = Number($("#rod-m-lin")?.value ?? 6);
    const toRaw = $("#rod-to")?.value;
    const nRaw = $("#rod-nb-chambres")?.value;
    const gRaw = $("#rod-guests")?.value;
    return {
      year: this.year(),
      m_lin: mLin,
      mix_fb: mixPct / 100,
      client_needs: this.collectNeeds(),
      nb_chambres: nRaw === "" || nRaw == null ? null : Number(nRaw),
      taux_occupation: toRaw === "" || toRaw == null ? null : Number(toRaw),
      guests_per_chambre: gRaw === "" || gRaw == null ? null : Number(gRaw),
    };
  }

  async loadPilots() {
    this.startProgress("load", `Année éval ${this.year()}`);
    try {
      const year = this.year();
      const data = await api.get("/api/rod/pilots", { year });
      this.pilots = data;
      const chipY = $("#rod-chip-year");
      if (chipY) {
        const train = (data.train_years || []).join(", ") || "—";
        chipY.textContent = `Apprend ${train} · éval ${data.eval_year || year}`;
      }
      const chipN = $("#rod-chip-n");
      if (chipN) chipN.textContent = `${data.n || 0} pilote(s)`;
      this.fillHotels(data.hotels || []);
      this.finishProgress("done", `${data.n || 0} pilote(s) chargés`);
      this.setStatus("");
    } catch (err) {
      this.finishProgress("error", err.message);
      this.setStatus(err.message);
      toast.show(err.message, "err");
    }
  }

  fillHotels(hotels) {
    const sel = $("#rod-hotel-select");
    if (!sel) return;
    const prev = sel.value;
    sel.innerHTML = "";
    if (!hotels.length) {
      sel.innerHTML = `<option value="">— aucun —</option>`;
      return;
    }
    hotels.forEach((h) => {
      const opt = document.createElement("option");
      opt.value = h.hotel_code;
      const realPart = h.has_holdout
        ? `réel ${fmt(h.avg_monthly_true, 0)} €/mois`
        : "pas de réel éval";
      opt.textContent = `${h.hotel_code} · ${h.hotel_name || "—"} · ${
        h.category || "?"
      } · ${realPart}`;
      sel.appendChild(opt);
    });
    if (prev && hotels.some((h) => h.hotel_code === prev)) sel.value = prev;
    this.renderHotelMeta();
    if (sel.value) this.scheduleSim();
  }

  renderHotelMeta() {
    const host = $("#rod-hotel-meta");
    if (!host || !this.pilots) return;
    const code = $("#rod-hotel-select")?.value;
    const h = (this.pilots.hotels || []).find((x) => x.hotel_code === code);
    if (!h) {
      host.className = "metrics-grid empty";
      host.textContent = "—";
      return;
    }
    host.className = "metrics-grid";
    host.innerHTML = `
      <div class="metric-box"><span class="m-label">Marque</span><span class="m-value">${escapeHtml(h.hotel_brand || "—")}</span></div>
      <div class="metric-box"><span class="m-label">Catégorie</span><span class="m-value">${escapeHtml(h.category || "—")}</span></div>
      <div class="metric-box"><span class="m-label">Nom</span><span class="m-value">${escapeHtml(h.hotel_name || "—")}</span></div>
    `;
  }

  /**
   * Zone 2 — hôtels pilotes même catégorie de marque (années de modélisation).
   * CA réel = avg mensuelle multi-années train ; TO / clients = fiche hôtel.
   */
  renderPilots() {
    const sumHost = $("#rod-pilots-summary");
    const tableHost = $("#rod-pilots-table");
    if (!sumHost || !tableHost) return;

    if (!this.trace) {
      sumHost.className = "metrics-grid empty";
      sumHost.textContent = "—";
      tableHost.className = "perf-table-wrap empty";
      tableHost.textContent = "—";
      return;
    }

    const r = this.trace.category_reference || {};
    const train = (this.trace.train_years || r.train_years || []).join(", ");
    const pilots =
      this.trace.category_pilots ||
      this.trace.category_reference_hotels ||
      [];

    sumHost.className = "metrics-grid";
    sumHost.innerHTML = `
      <div class="metric-box"><span class="m-label">Années de modélisation</span><span class="m-value">${escapeHtml(train || "—")}</span></div>
      <div class="metric-box"><span class="m-label">Catégorie</span><span class="m-value">${escapeHtml(r.category || this.trace.category || "—")}</span></div>
      <div class="metric-box"><span class="m-label">n pilotes</span><span class="m-value">${pilots.length || r.n_hotels || 0}</span></div>
      <div class="metric-box good"><span class="m-label">CA réel moyen / mois</span><span class="m-value">${euro(r.ca_monthly_ref)}</span></div>
      <div class="metric-box"><span class="m-label">Clients / mois (moy.)</span><span class="m-value">${fmt(r.clients_mois_ref, 1)}</span></div>
      <div class="metric-box"><span class="m-label">TO réel moyen</span><span class="m-value">${r.taux_occupation_ref != null ? fmt(Number(r.taux_occupation_ref) * 100, 1) + " %" : "—"}</span></div>
    `;

    if (!pilots.length) {
      tableHost.className = "perf-table-wrap empty";
      tableHost.textContent = "Aucun pilote pour cette catégorie";
      return;
    }

    const target = this.trace.hotel_code;
    tableHost.className = "perf-table-wrap";
    tableHost.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Code</th>
            <th>Hôtel</th>
            <th>Années</th>
            <th>CA réel / mois</th>
            <th>Clients / mois</th>
            <th>TO réel</th>
          </tr>
        </thead>
        <tbody>
          ${pilots
            .map((p) => {
              const years = (p.train_years || Object.keys(p.by_year || {}))
                .map(String)
                .join(", ");
              const ca = p.ca_monthly_ref ?? p.reference_monthly;
              const to =
                p.taux_occupation != null
                  ? fmt(Number(p.taux_occupation) * 100, 1) + " %"
                  : "—";
              const isTarget = p.hotel_code === target;
              return `<tr${isTarget ? ' class="is-target"' : ""}>
                <td>${escapeHtml(p.hotel_code || "")}${isTarget ? " ·" : ""}</td>
                <td>${escapeHtml(p.hotel_name || "—")}</td>
                <td>${escapeHtml(years || "—")}</td>
                <td>${euro(ca)}</td>
                <td>${fmt(p.clients_mois, 1)}</td>
                <td>${to}</td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>
    `;
  }

  scheduleSim() {
    if (this._simDebounced) this._simDebounced();
  }

  /**
   * Recalcule la simu hôtel courant (auto à chaque changement).
   * Ne lance PAS le batch — le batch est sur l'onglet dédié.
   */
  async runSim() {
    const code = $("#rod-hotel-select")?.value;
    if (!code) {
      this.setStatus("Choisissez un hôtel pour la simulation");
      return;
    }

    if (this._simBusy) {
      this._simQueued = true;
      return;
    }
    this._simBusy = true;
    const seq = ++this._simSeq;
    this.startProgress("sim", code);

    try {
      const params = this.collectParams();
      const data = await api.post(
        `/api/rod/hotel/${encodeURIComponent(code)}/trace`,
        params
      );
      // réponse obsolète (nouvelle demande en file) → ignorer
      if (seq !== this._simSeq && this._simQueued) {
        // ne pas finishProgress : le run suivant reprend la barre
        return;
      }
      if (!data.ok) throw new Error(data.error || "Simulation échouée");
      this.trace = data;

      const p = data.params || {};
      if (!this._paramsTouched) {
        if (p.m_lin != null) this.setMLin(p.m_lin);
        if (p.mix_fb != null) this.setMix(Math.round(Number(p.mix_fb) * 100));
        if (p.nb_chambres != null && $("#rod-nb-chambres"))
          $("#rod-nb-chambres").value = String(Math.round(p.nb_chambres));
        if (p.taux_occupation != null && $("#rod-to")) {
          let to = Number(p.taux_occupation);
          if (to <= 1) to *= 100;
          $("#rod-to").value = String(Math.round(to * 10) / 10);
        }
        if (p.guests_per_chambre != null && $("#rod-guests"))
          $("#rod-guests").value = String(Number(p.guests_per_chambre).toFixed(1));
        const needs = p.client_needs || data.client_needs || {};
        Object.keys(needs).forEach((id) => {
          const el = document.querySelector(`input[data-need="${id}"]`);
          if (!el) return;
          const on = !!needs[id];
          el.checked = on;
          const item = el.closest(".rod-need-item");
          if (item) {
            item.classList.toggle("is-on", on);
            item.classList.toggle("is-off", !on);
            const st = item.querySelector(".rod-need-state");
            if (st) st.textContent = on ? "Autorisé" : "Interdit";
            const sw = item.querySelector(".switch");
            if (sw) sw.title = on ? "Désactiver" : "Activer";
          }
        });
      }

      const reco = data.recommendation?.recommended_concept;
      if (reco) this.concept = reco;
      $$(".rod-concept").forEach((el) => {
        el.classList.toggle("active", el.dataset.concept === this.concept);
      });
      this.renderTrace();
      const mixFb = Math.round((p.mix_fb ?? params.mix_fb) * 100);
      const summary = `${code} · solution ${reco || "—"} · ${fmt(p.m_lin ?? params.m_lin, 1)} m lin. · mix F&B ${mixFb} %`;
      this.finishProgress("done", "Simulation terminée", summary);
      this.setStatus(summary);
    } catch (err) {
      this.finishProgress("error", err.message);
      this.setStatus(err.message);
      toast.show(err.message, "err");
    } finally {
      this._simBusy = false;
      if (this._simQueued) {
        this._simQueued = false;
        this.scheduleSim();
      }
    }
  }

  async runEvalBatch() {
    if (this._evalBusy) return;
    this._evalBusy = true;
    this.startProgress("batch", `Année ${this.year()}`);
    try {
      const year = this.year();
      const data = await api.get("/api/rod/eval", { year });
      if (!data.ok) throw new Error(data.error || "Éval échouée");
      this.evalResult = data;
      this.renderEval(data);
      const nScored = data.metrics?.n ?? "—";
      const summary = `Batch ${data.eval_year} · ${data.n_hotels} pilote(s) · MAE n=${nScored}`;
      this.finishProgress("done", "Batch terminé", summary);
      this.setStatus(summary);
    } catch (err) {
      this.finishProgress("error", err.message);
      this.setStatus(err.message);
      toast.show(err.message, "err");
    } finally {
      this._evalBusy = false;
    }
  }

  setTab(tab) {
    this.tab = tab;
    $$(".rod-tab").forEach((el) => {
      el.classList.toggle("active", el.dataset.rodTab === tab);
    });
    $$(".rod-panel").forEach((el) => {
      el.classList.toggle("hidden", el.dataset.rodPanel !== tab);
    });
    // Batch : lancer à l'entrée de l'onglet
    if (tab === "eval" && !this.evalResult) {
      this.runEvalBatch();
    }
    // Re-render panneaux si trace déjà là
    if (this.trace && tab !== "eval") {
      this.renderTrace();
    }
  }

  setConcept(c) {
    this.concept = c;
    $$(".rod-concept").forEach((el) => {
      el.classList.toggle("active", el.dataset.concept === c);
    });
    this.renderTrace();
  }

  renderTrace() {
    if (!this.trace) return;
    this.renderPilots();
    this.renderRecoBanner();
    this.renderConceptKpi();
    this.renderSalesSteps(
      (this.trace.by_concept?.[this.concept] || {}).sales?.steps || []
    );
    this.renderMarginAll();
    this.renderCostLines(
      (this.trace.by_concept?.[this.concept] || {}).costs?.cost_lines || []
    );
    this.renderGapKpi();
    this.renderGapDetail();
  }

  /** KPI solution : CA / marges seulement (pas d'écart ici). */
  renderConceptKpi() {
    const kpi = $("#rod-concept-kpi");
    if (!kpi) return;
    const block = this.trace?.by_concept?.[this.concept];
    if (!block || block.ok === false || block.error) {
      kpi.className = "metrics-grid empty";
      kpi.textContent = block?.error || "—";
      return;
    }
    const sales = block.sales || {};
    const margin = block.margin || {};
    kpi.className = "metrics-grid";
    kpi.innerHTML = `
      <div class="metric-box good"><span class="m-label">CA sim / mois</span><span class="m-value">${euro(sales.ca_ht_mensuel)}</span></div>
      <div class="metric-box"><span class="m-label">Marge produit</span><span class="m-value">${euro(margin.marge_produit_mensuelle)}</span></div>
      <div class="metric-box good"><span class="m-label">Marge nette</span><span class="m-value">${euro(margin.marge_nette_mensuelle)}</span></div>
      <div class="metric-box"><span class="m-label">Coût / mois</span><span class="m-value">${euro(margin.cout_mensuel)}</span></div>
    `;
  }

  renderRecoBanner() {
    const host = $("#rod-reco-banner");
    if (!host || !this.trace) return;
    const rec = this.trace.recommendation || {};
    if (!rec.recommended_concept) {
      host.classList.add("hidden");
      return;
    }
    host.classList.remove("hidden");
    host.innerHTML = `
      <div class="tag">Reco</div>
      <h2>${escapeHtml(rec.recommended_concept)}</h2>
    `;
  }

  /** KPI dédiés écart réel vs sim (solution affichée). */
  renderGapKpi() {
    const host = $("#rod-gap-kpi");
    if (!host || !this.trace) return;
    const c = this.concept;
    const gap = (this.trace.gaps || {})[c] || {};
    const real = this.trace.real_holdout || {};
    const hasHold = !!(this.trace.has_holdout || real.available);
    const ca =
      gap.ca_sim_mensuel ??
      this.trace.by_concept?.[c]?.sales?.ca_ht_mensuel;
    const avgTrue = gap.avg_monthly_true ?? real.avg_monthly_true;
    const gapCls =
      hasHold && gap.gap != null
        ? (gap.gap || 0) >= 0
          ? "good"
          : "warn"
        : "";

    host.className = "metrics-grid rod-gap-kpi";
    if (!hasHold) {
      host.innerHTML = `
        <div class="metric-box"><span class="m-label">Solution</span><span class="m-value">${escapeHtml(c)}</span></div>
        <div class="metric-box good"><span class="m-label">CA simulé / mois</span><span class="m-value">${euro(ca)}</span></div>
        <div class="metric-box"><span class="m-label">Réel éval</span><span class="m-value">—</span></div>
        <div class="metric-box"><span class="m-label">Écart</span><span class="m-value">—</span></div>
      `;
      return;
    }
    host.innerHTML = `
      <div class="metric-box"><span class="m-label">Solution</span><span class="m-value">${escapeHtml(c)}</span></div>
      <div class="metric-box good"><span class="m-label">CA simulé / mois</span><span class="m-value">${euro(ca)}</span></div>
      <div class="metric-box"><span class="m-label">Réel ${real.year || ""} Σ/12</span><span class="m-value">${euro(avgTrue)}</span></div>
      <div class="metric-box ${gapCls}"><span class="m-label">Écart (sim − réel)</span><span class="m-value">${euro(gap.gap)}${gap.gap_pct != null ? " · " + fmt(gap.gap_pct, 1) + " %" : ""}</span></div>
    `;
  }

  renderGapDetail() {
    const host = $("#rod-gap-table");
    if (!host || !this.trace) return;
    const gaps = this.trace.gaps || {};
    const real = this.trace.real_holdout || {};
    const reco = this.trace.recommendation?.recommended_concept;
    const hasHold = !!(this.trace.has_holdout || real.available);
    host.className = "perf-table-wrap";
    host.innerHTML = `
      <table id="rod-gap-table-inner">
        <thead>
          <tr>
            <th>Solution</th>
            <th>CA simulé / mois</th>
            <th>Réel ${real.year || ""} Σ/12</th>
            <th>Écart (sim − réel)</th>
            <th>%</th>
          </tr>
        </thead>
        <tbody>
          ${["SIMPLY", "LIBERTY", "CONNECTED"]
            .map((c) => {
              const g = gaps[c] || {};
              const ca =
                g.ca_sim_mensuel ??
                this.trace.by_concept?.[c]?.sales?.ca_ht_mensuel;
              const cls =
                g.gap != null ? ((g.gap || 0) >= 0 ? "pos" : "neg") : "";
              return `<tr class="${c === reco || c === this.concept ? "is-best" : ""}">
                <td><strong>${c}</strong>${c === reco ? " ★" : ""}</td>
                <td>${euro(ca)}</td>
                <td>${hasHold ? euro(g.avg_monthly_true ?? real.avg_monthly_true) : "—"}</td>
                <td class="${cls}">${hasHold ? euro(g.gap) : "—"}</td>
                <td class="${cls}">${hasHold && g.gap_pct != null ? fmt(g.gap_pct, 1) + " %" : "—"}</td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>`;
  }

  renderSalesSteps(steps) {
    const host = $("#rod-sales-steps");
    if (!host) return;
    if (!steps.length) {
      host.className = "rod-steps empty";
      host.textContent = "—";
      return;
    }
    host.className = "rod-steps";
    host.innerHTML = steps
      .map((s, i) => {
        const vals = s.values || {};
        const grid = Object.keys(vals)
          .map((k) => {
            let val = vals[k];
            if (Array.isArray(val)) val = val.join(", ");
            return `<div class="rod-kv"><span>${escapeHtml(k)}</span><strong>${escapeHtml(
              String(val ?? "—")
            )}</strong></div>`;
          })
          .join("");
        const caBlock =
          s.ca_ht != null
            ? `<div class="rod-step-ca"><span class="muted">CA HT</span><strong>${euro(
                s.ca_ht
              )}</strong></div>`
            : "";
        return `
        <article class="rod-step">
          <header>
            <span class="rod-step-n">${i + 1}</span>
            <div>
              <h3>${escapeHtml(s.title || s.id)}</h3>
              <p class="rod-rule">${escapeHtml(s.rule || "")}</p>
            </div>
            ${caBlock}
          </header>
          <p class="rod-formula">${escapeHtml(s.formula || "")}</p>
          <div class="rod-kv-grid">${grid}</div>
          ${
            s.ca_fb != null
              ? `<div class="rod-step-split"><span>F&amp;B ${euro(
                  s.ca_fb
                )}</span><span>N-F&amp;B ${euro(s.ca_nf)}</span></div>`
              : ""
          }
        </article>`;
      })
      .join("");
  }

  renderMarginAll() {
    const host = $("#rod-margin-table");
    if (!host || !this.trace) return;
    const by = this.trace.by_concept || {};
    const reco = this.trace.recommendation?.recommended_concept;
    host.className = "perf-table-wrap";
    host.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Solution</th>
            <th>CA HT</th>
            <th>Marge produit</th>
            <th>Techno</th>
            <th>Annexes</th>
            <th>Agencement</th>
            <th>Coût total</th>
            <th>Marge nette</th>
            <th>Capex</th>
          </tr>
        </thead>
        <tbody>
          ${["SIMPLY", "LIBERTY", "CONNECTED"]
            .map((c) => {
              const b = by[c] || {};
              const s = b.sales || {};
              const m = b.margin || {};
              const co = b.costs || {};
              return `<tr class="${c === reco || c === this.concept ? "is-best" : ""}">
                <td><strong>${c}</strong>${c === reco ? " ★" : ""}</td>
                <td>${euro(s.ca_ht_mensuel)}</td>
                <td>${euro(m.marge_produit_mensuelle)}</td>
                <td>${euro(co.techno_monthly)}</td>
                <td>${euro(co.annexes_monthly)}</td>
                <td>${euro(co.agencement_monthly)}</td>
                <td>${euro(co.monthly_cost)}</td>
                <td>${euro(m.marge_nette_mensuelle)}</td>
                <td>${euro(co.capex)}</td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>`;
  }

  renderCostLines(lines) {
    const host = $("#rod-cost-lines");
    if (!host) return;
    if (!lines.length) {
      host.className = "perf-table-wrap empty";
      host.textContent = "—";
      return;
    }
    host.className = "perf-table-wrap";
    host.innerHTML = `
      <table>
        <thead>
          <tr><th>Id</th><th>Libellé</th><th>Groupe</th><th>Qté</th><th>Mensuel</th><th>Capex</th></tr>
        </thead>
        <tbody>
          ${lines
            .map(
              (l) => `<tr>
              <td>${escapeHtml(l.id || "")}</td>
              <td>${escapeHtml(l.label || "")}</td>
              <td>${escapeHtml(l.group || "")}</td>
              <td>${fmt(l.qty, 2)}</td>
              <td>${euro(l.monthly)}</td>
              <td>${euro(l.capex)}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  }

  renderEval(data) {
    const m = data.metrics || {};
    const trainY = (data.train_years || []).join(", ") || "—";
    const mh = $("#rod-eval-metrics");
    if (mh) {
      mh.className = "metrics-grid";
      mh.innerHTML = `
        <div class="metric-box"><span class="m-label">n pilotes</span><span class="m-value">${m.n_predicted ?? data.n_hotels ?? "—"}</span></div>
        <div class="metric-box"><span class="m-label">Années modél.</span><span class="m-value">${escapeHtml(trainY)}</span></div>
        <div class="metric-box"><span class="m-label">n éval (réel)</span><span class="m-value">${m.n ?? "—"}</span></div>
        <div class="metric-box"><span class="m-label">MAE CA</span><span class="m-value">${euro(m.mae)}</span></div>
        <div class="metric-box"><span class="m-label">RMSE</span><span class="m-value">${euro(m.rmse)}</span></div>
        <div class="metric-box"><span class="m-label">Biais</span><span class="m-value">${euro(m.bias)}</span></div>
        <div class="metric-box"><span class="m-label">MAPE %</span><span class="m-value">${fmt(m.mape, 1)}</span></div>
        <div class="metric-box good"><span class="m-label">Moy. sim reco</span><span class="m-value">${euro(m.mean_sim ?? m.mean_sim_all)}</span></div>
        <div class="metric-box"><span class="m-label">Moy. réel éval</span><span class="m-value">${euro(m.mean_true)}</span></div>
        <div class="metric-box"><span class="m-label">Moy. coût (installée)</span><span class="m-value">${euro(m.mean_cout_installee)}</span></div>
        <div class="metric-box good"><span class="m-label">Moy. marge nette (installée)</span><span class="m-value">${euro(m.mean_marge_nette_installee)}</span></div>
        <div class="metric-box"><span class="m-label">Moy. marge produit (installée)</span><span class="m-value">${euro(m.mean_marge_produit_installee)}</span></div>
      `;
    }
    const host = $("#rod-eval-table");
    const rows = data.hotels || [];
    if (!host) return;
    host.className = "perf-table-wrap";
    host.innerHTML = `
      <p class="card-hint" style="margin-bottom:0.65rem">
        <strong>Solution installée</strong> = dispositif pilote (Simply / Liberty / Connected).
        Coût et marge nette mensuels sont ceux de cette solution (barème ROD).
        CA train = réel période de modélisation ; réel éval = hold-out (ex. 2026) Σ/12.
      </p>
      <table>
        <thead>
          <tr>
            <th>Hôtel</th>
            <th>Catégorie</th>
            <th>Sol. installée</th>
            <th>CA train / mois</th>
            <th>CA sim installée</th>
            <th>Coût / mois</th>
            <th>Marge produit</th>
            <th>Marge nette</th>
            <th>Réel éval Σ/12</th>
            <th>Reco</th>
            <th>CA sim reco</th>
            <th>Écart</th>
            <th>%</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map((r) => {
              if (r.error)
                return `<tr><td>${escapeHtml(r.hotel_code)}</td><td colspan="12">${escapeHtml(
                  r.error
                )}</td></tr>`;
              const hasH = !!r.has_holdout;
              const gapCls =
                r.gap_reco != null ? ((r.gap_reco || 0) >= 0 ? "pos" : "neg") : "";
              const inst = r.installed_solution || "—";
              const mInst = r.marge_nette_installee;
              const mCls =
                mInst != null ? (Number(mInst) >= 0 ? "pos" : "neg") : "";
              return `<tr>
                <td>${escapeHtml(r.hotel_code)}<br><small>${escapeHtml(
                  r.hotel_name || ""
                )}</small></td>
                <td>${escapeHtml(r.category || "—")}</td>
                <td><strong>${escapeHtml(inst)}</strong></td>
                <td>${euro(r.avg_monthly_train ?? r.reference_monthly)}</td>
                <td>${euro(r.ca_sim_installee)}</td>
                <td>${euro(r.cout_mensuel_installee)}</td>
                <td>${euro(r.marge_produit_installee)}</td>
                <td class="${mCls}">${euro(r.marge_nette_installee)}</td>
                <td>${hasH ? euro(r.avg_monthly_true) : "—"}</td>
                <td><strong>${escapeHtml(r.recommended_concept || "—")}</strong></td>
                <td>${euro(r.ca_sim_reco)}</td>
                <td class="${gapCls}">${hasH ? euro(r.gap_reco) : "—"}</td>
                <td class="${gapCls}">${hasH && r.gap_pct_reco != null ? fmt(r.gap_pct_reco, 1) + " %" : "—"}</td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>`;
  }

  wire() {
    // Auto-recalc (pas de bouton Simuler)
    this._simDebounced = debounce(() => this.runSim(), 400);

    $("#rod-hotel-select")?.addEventListener("change", () => {
      this._paramsTouched = false;
      this.evalResult = null;
      this.renderHotelMeta();
      this.scheduleSim();
    });
    $("#rod-year")?.addEventListener("change", async () => {
      this._paramsTouched = false;
      this.evalResult = null;
      await this.loadPilots();
      if (this.tab === "eval") this.runEvalBatch();
    });

    const linkM = (sliderId, inputId) => {
      const s = $("#" + sliderId);
      const i = $("#" + inputId);
      if (s && i) {
        s.addEventListener("input", () => {
          i.value = s.value;
          if (inputId === "rod-mix-fb") this.setMix(s.value);
          this._paramsTouched = true;
          this.scheduleSim();
        });
        i.addEventListener("change", () => {
          if (inputId === "rod-mix-fb") this.setMix(i.value);
          else this.setMLin(i.value);
          this._paramsTouched = true;
          this.scheduleSim();
        });
        i.addEventListener("input", () => {
          this._paramsTouched = true;
          this.scheduleSim();
        });
      }
    };
    linkM("rod-m-lin-slider", "rod-m-lin");
    linkM("rod-mix-slider", "rod-mix-fb");

    ["rod-nb-chambres", "rod-to", "rod-guests"].forEach((id) => {
      const el = $("#" + id);
      if (!el) return;
      el.addEventListener("change", () => {
        this._paramsTouched = true;
        this.scheduleSim();
      });
      el.addEventListener("input", () => {
        this._paramsTouched = true;
        this.scheduleSim();
      });
    });

    $("#rod-needs-all-on")?.addEventListener("click", () => this.setNeedsAll(true));
    $("#rod-needs-all-off")?.addEventListener("click", () => this.setNeedsAll(false));

    $$(".rod-tab").forEach((el) => {
      el.addEventListener("click", () => this.setTab(el.dataset.rodTab));
    });
    $$(".rod-concept").forEach((el) => {
      el.addEventListener("click", () => this.setConcept(el.dataset.concept));
    });
  }
}
