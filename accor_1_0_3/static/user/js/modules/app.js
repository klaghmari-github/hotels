/**
 * Simulateur hôtel (interface directeur).
 *
 * Parcours en 4 étapes : hôtel → établissement → offre corner → résultats.
 * Tous les champs sont collectés avant le calcul (sim + IA) ; le directeur
 * ne distingue pas quels champs alimentent quelle source.
 * Les réglages restent en session : rien n'est enregistré en base.
 */

import { $, $$, escapeHtml } from "../../../shared/js/dom.js";
import { api } from "../../../shared/js/api.js";
import { toast } from "../../../shared/js/toast.js";
import { enhanceNumSteps } from "./num-step.js";

function fmt(v, d = 1) {
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

class DirectorApp {
  constructor() {
    this.meta = null;
    this.result = null;
    this.step = 1;
    this.hotel = null;
    this.context = null;
    this.resultTab = "sim";
    /** Index hôtels base (chargé une fois) + hôtels session (scrape sans écriture). */
    this.hotelIndex = [];
    this.sessionHotels = [];
    this._acHighlight = -1;
    /** Valeurs hotel_params (saisie / préremplissage) */
    this.hotelParams = {};
    this.hotelParamsDefaults = {};
    this._hotelFormBuilt = false;
  }

  async init() {
    try {
      this.meta = await api.get("/api/rod/meta");
      this.renderNeeds(this.meta);
      this.hotelParamsDefaults = this.meta.hotel_params_defaults || {};
      this.renderHotelParamsForm(this.meta.hotel_form);
      const d = this.meta.defaults || {};
      this.setMLin(d.m_lin ?? 6);
      this.setMix(Math.round((d.mix_fb ?? 0.7) * 100));
    } catch (err) {
      toast.show(err.message, "err");
    }
    // Index hotels en parallèle (non bloquant pour le wire)
    this.loadHotelIndex().catch((err) => {
      console.warn("index hotels", err);
    });
    this.wire();
    enhanceNumSteps(document);
    this.goStep(1);
  }

  async loadHotelIndex() {
    this.setStatus("Chargement de la liste des hôtels…");
    try {
      const res = await api.get("/api/hotels/index");
      this.hotelIndex = res.hotels || [];
      this.setStatus(
        this.hotelIndex.length
          ? `${this.hotelIndex.length.toLocaleString("fr-FR")} hôtels disponibles`
          : ""
      );
    } catch (err) {
      // fallback : aperçu via search vide
      try {
        const res = await api.get("/api/hotels/search", { q: "", limit: 80 });
        this.hotelIndex = res.hotels || [];
      } catch (_) {
        this.hotelIndex = [];
      }
      this.setStatus("");
      throw err;
    }
  }

  /** Base + hôtels créés en session (scrape mémoire). */
  allHotelsForSearch() {
    const seen = new Set();
    const out = [];
    for (const h of [...this.sessionHotels, ...this.hotelIndex]) {
      const code = String(h.hotel_code || "").toUpperCase();
      if (!code || seen.has(code)) continue;
      seen.add(code);
      out.push(h);
    }
    return out;
  }

  /**
   * Filtre local instantané (pas d'attente réseau à chaque frappe).
   * q vide → premiers hôtels triés par nom.
   */
  filterHotelsLocal(q, limit = 40) {
    const query = String(q || "").trim().toLowerCase();
    const qCompact = query.replace(/\s+/g, "");
    const hotels = this.allHotelsForSearch();
    if (!query) {
      return [...hotels]
        .sort((a, b) =>
          String(a.hotel_name || "").localeCompare(String(b.hotel_name || ""), "fr")
        )
        .slice(0, limit);
    }
    const scored = [];
    for (const h of hotels) {
      const code = String(h.hotel_code || "").trim();
      const name = String(h.hotel_name || "").trim();
      const city = String(h.hotel_city || "").trim();
      const brand = String(h.hotel_brand || "").trim();
      const codeL = code.toLowerCase();
      const nameL = name.toLowerCase();
      const cityL = city.toLowerCase();
      const brandL = brand.toLowerCase();
      let score = 0;
      if (codeL === query || codeL === qCompact) score = 100;
      else if (codeL.startsWith(query) || codeL.startsWith(qCompact)) score = 90;
      else if (codeL.includes(query)) score = 70;
      else if (nameL.startsWith(query)) score = 80;
      else if (nameL.includes(query)) score = 60;
      else if (cityL.includes(query)) score = 40;
      else if (brandL.includes(query)) score = 30;
      else {
        const tokens = query.split(/\s+/).filter(Boolean);
        if (
          tokens.length &&
          tokens.every((t) => nameL.includes(t) || cityL.includes(t) || brandL.includes(t))
        ) {
          score = 55;
        } else continue;
      }
      scored.push({ score, h });
    }
    scored.sort(
      (a, b) =>
        b.score - a.score ||
        String(a.h.hotel_name || "").localeCompare(String(b.h.hotel_name || ""), "fr")
    );
    return scored.slice(0, limit).map((x) => x.h);
  }

  looksLikeHotelCode(q) {
    const s = String(q || "").trim().toUpperCase();
    if (!s) return false;
    // H0373, 0373, HB6A3, codes alphanum 3–8
    return /^H?[A-Z0-9]{3,8}$/.test(s.replace(/\s+/g, ""));
  }

  setStatus(msg) {
    const el = $("#dir-status");
    if (el) el.textContent = msg || "Prêt";
  }

  /**
   * Overlay de chargement fiche hôtel (étape 1).
   * @param {string} code
   * @param {string} [label]
   */
  showHotelLoading(code, label) {
    const box = $("#hotel-loading");
    if (!box) return;
    box.classList.remove("hidden");
    box.setAttribute("aria-busy", "true");
    document.body.classList.add("is-hotel-loading");
    const title = label
      ? `Chargement de ${label}…`
      : `Chargement de l’hôtel ${code || ""}…`;
    if ($("#hotel-loading-title")) $("#hotel-loading-title").textContent = title.trim();
    if ($("#hotel-loading-sub")) {
      $("#hotel-loading-sub").textContent =
        "Récupération de la fiche et des paramètres — veuillez patienter.";
    }
    this.setHotelLoadProgress(8, 1);
    // Progression « indéterminée » tant que l’API n’a pas répondu
    this._clearHotelLoadTimer();
    this._hotelLoadPct = 8;
    this._hotelLoadTimer = setInterval(() => {
      // monte doucement jusqu’à ~70 % en attendant le réseau
      if (this._hotelLoadPct < 68) {
        this._hotelLoadPct = Math.min(68, this._hotelLoadPct + 2 + Math.random() * 4);
        this.setHotelLoadProgress(this._hotelLoadPct, this._hotelLoadStep || 2);
      }
    }, 280);
  }

  /**
   * @param {number} pct 0–100
   * @param {number} step 1–4
   * @param {string} [sub]
   */
  setHotelLoadProgress(pct, step, sub) {
    const p = Math.max(0, Math.min(100, Math.round(Number(pct) || 0)));
    this._hotelLoadPct = p;
    this._hotelLoadStep = step || this._hotelLoadStep || 1;
    const fill = $("#hotel-loading-fill");
    const bar = $("#hotel-loading-bar");
    const pctEl = $("#hotel-loading-pct");
    if (fill) fill.style.width = `${p}%`;
    if (bar) bar.setAttribute("aria-valuenow", String(p));
    if (pctEl) pctEl.innerHTML = `${p}&nbsp;%`;
    if (sub && $("#hotel-loading-sub")) {
      $("#hotel-loading-sub").textContent = sub;
    }
    $$("#hotel-loading-steps [data-load-step]").forEach((li) => {
      const s = Number(li.dataset.loadStep);
      li.classList.toggle("is-done", s < this._hotelLoadStep);
      li.classList.toggle("is-active", s === this._hotelLoadStep);
    });
  }

  _clearHotelLoadTimer() {
    if (this._hotelLoadTimer) {
      clearInterval(this._hotelLoadTimer);
      this._hotelLoadTimer = null;
    }
  }

  hideHotelLoading() {
    this._clearHotelLoadTimer();
    const box = $("#hotel-loading");
    if (box) {
      box.classList.add("hidden");
      box.setAttribute("aria-busy", "false");
    }
    document.body.classList.remove("is-hotel-loading");
  }

  goStep(n) {
    this.step = n;
    document.body.dataset.step = String(n);
    $$(".wiz-panel").forEach((p) => {
      p.classList.toggle("is-active", Number(p.dataset.panel) === n);
    });
    $$(".wiz-step").forEach((btn) => {
      const s = Number(btn.dataset.step);
      btn.classList.toggle("is-active", s === n);
      btn.classList.toggle("is-done", s < n);
      if (s === 1) btn.disabled = false;
      if (s >= 2) btn.disabled = !this.hotel;
      if (s === 4) btn.disabled = !this.result;
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  wire() {
    const search = $("#hotel_search");
    // Filtre local immédiat à chaque frappe (pas besoin d'Entrée)
    search?.addEventListener("input", () => {
      this._acHighlight = -1;
      this.onSearch();
    });
    search?.addEventListener("focus", () => {
      this.onSearch();
    });
    search?.addEventListener("keydown", (e) => {
      const list = $("#ac-hotels");
      const items = list ? Array.from(list.querySelectorAll(".ac-item")) : [];
      if (e.key === "Escape") {
        this.hideAc();
        return;
      }
      if (e.key === "ArrowDown" && items.length) {
        e.preventDefault();
        this._acHighlight = Math.min(this._acHighlight + 1, items.length - 1);
        this._paintAcHighlight(items);
        return;
      }
      if (e.key === "ArrowUp" && items.length) {
        e.preventDefault();
        this._acHighlight = Math.max(this._acHighlight - 1, 0);
        this._paintAcHighlight(items);
        return;
      }
      if (e.key === "Enter") {
        // sélection clavier éventuelle — sinon laisser le filtre
        if (this._acHighlight >= 0 && items[this._acHighlight]) {
          e.preventDefault();
          const el = items[this._acHighlight];
          if (el.dataset.action === "fetch") {
            this.selectHotel(el.dataset.code, { forceFetch: true });
          } else {
            this.selectHotel(el.dataset.code);
          }
        }
      }
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".ac-wrap")) this.hideAc();
    });

    $("#btn-step1-next")?.addEventListener("click", () => {
      if (this.hotel) this.goStep(2);
    });
    $("#btn-step2-next")?.addEventListener("click", () => this.goStep(3));
    // Simuler = choix user (+ signal « optimisation possible »)
    $("#btn-run-sim")?.addEventListener("click", () => this.runSim(false));
    // Optimiser = grille mix F&B × sous-catégories, applique le meilleur
    $("#btn-run-optimize")?.addEventListener("click", () => this.runSim(true));

    $$("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const s = Number(btn.dataset.goto);
        if (s >= 1 && s <= 4) this.goStep(s);
      });
    });

    $$(".wiz-step").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.disabled) return;
        this.goStep(Number(btn.dataset.step));
      });
    });

    const syncM = () => {
      this.setMLin($("#m_lin")?.value || $("#m_lin_slider")?.value);
    };
    $("#m_lin_slider")?.addEventListener("input", () => {
      $("#m_lin").value = $("#m_lin_slider").value;
      syncM();
    });
    $("#m_lin")?.addEventListener("input", () => {
      $("#m_lin_slider").value = $("#m_lin").value;
      syncM();
    });

    const syncMix = () => {
      this.setMix($("#mix_slider")?.value || $("#mix_fb")?.value);
      this._syncFrigoVisibility();
    };
    $("#mix_slider")?.addEventListener("input", () => {
      syncMix();
    });

    $("#needs-all-on")?.addEventListener("click", () => this.setAllNeeds(true));
    $("#needs-all-off")?.addEventListener("click", () => this.setAllNeeds(false));
    this._syncFrigoVisibility();

    // Onglets résultats
    $$("[data-result-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        this.setResultTab(btn.dataset.resultTab);
      });
    });
  }

  _toggleBtnHtml(f) {
    return `<button type="button" class="toggle-row" role="switch"
      aria-checked="false" data-hp-bool="${escapeHtml(f.id)}"
      title="${escapeHtml(f.hint || f.label)}">
      <span class="toggle-icon" aria-hidden="true">●</span>
      <span class="toggle-copy">
        <strong>${escapeHtml(f.label)}</strong>
        ${f.hint ? `<em>${escapeHtml(f.hint)}</em>` : ""}
      </span>
      <span class="toggle-track" aria-hidden="true"><span class="toggle-thumb"></span></span>
    </button>`;
  }

  _numFieldHtml(f) {
    const min = f.min != null ? ` min="${f.min}"` : "";
    const max = f.max != null ? ` max="${f.max}"` : "";
    const step = f.step != null ? ` step="${f.step}"` : ' step="any"';
    return `<label class="field field-float" data-field="${escapeHtml(f.id)}">
      <span>${escapeHtml(f.label)}${
        f.hint
          ? ` <em class="field-hint" title="${escapeHtml(f.hint)}">?</em>`
          : ""
      }</span>
      <input type="number" data-hp="${escapeHtml(f.id)}" data-kind="${escapeHtml(
        f.kind
      )}"${min}${max}${step} />
    </label>`;
  }

  /**
   * Construit le formulaire paramètres de base (toutes variables hotel_data utiles).
   * Section « Corner » : F&B / Non F&B séparés en deux colonnes.
   */
  renderHotelParamsForm(formMeta) {
    const host = $("#hotel-params-form");
    if (!host) return;
    const sections = (formMeta && formMeta.sections) || [];
    if (!sections.length) {
      host.innerHTML =
        '<p class="muted">Schéma paramètres indisponible — rechargez la page.</p>';
      return;
    }
    host.innerHTML = sections
      .map((sec) => {
        const fields = sec.fields || [];
        const bools = fields.filter((f) => f.kind === "bool");
        const nums = fields.filter((f) => f.kind !== "bool");
        const numHtml = nums.length
          ? `<div class="wiz-grid-3">${nums
              .map((f) => this._numFieldHtml(f))
              .join("")}</div>`
          : "";

        let boolHtml = "";
        if (sec.id === "corner" && bools.length) {
          // Formulaire simplifié : présence + frigo/vitrine (plus les 9 modes de vente)
          boolHtml = `
            <div class="toggle-grid hotel-params-toggles corner-general">
              ${bools.map((f) => this._toggleBtnHtml(f)).join("")}
            </div>
            <p class="corner-data-note">
              Infos issues de la fiche ROD (hotel_data), pas du scrap Accor.
              Seuls la présence, les ML et le frigo/vitrine impactent la simulation.
            </p>`;
        } else if (bools.length) {
          boolHtml = `<div class="toggle-grid hotel-params-toggles">${bools
            .map((f) => this._toggleBtnHtml(f))
            .join("")}</div>`;
        }

        return `<section class="form-block" data-section="${escapeHtml(
          sec.id
        )}">
          <header class="form-block-head">
            <h2 class="wiz-section-title">${escapeHtml(sec.label)}</h2>
          </header>
          ${numHtml}
          ${boolHtml}
        </section>`;
      })
      .join("");

    host.querySelectorAll("[data-hp-bool]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const on = btn.getAttribute("aria-checked") !== "true";
        this._setHpBool(btn.dataset.hpBool, on, btn);
        // Contrat franchise / managé mutuellement exclusifs
        if (on && btn.dataset.hpBool === "hotel_contrat_type_franchise") {
          this._setHpBool("hotel_contrat_type_manage", false);
        }
        if (on && btn.dataset.hpBool === "hotel_contrat_type_manage") {
          this._setHpBool("hotel_contrat_type_franchise", false);
        }
      });
    });
    enhanceNumSteps(host);
    this._hotelFormBuilt = true;
  }

  _setHpBool(id, on, btnEl) {
    const btn =
      btnEl || document.querySelector(`[data-hp-bool="${id}"]`);
    if (!btn) return;
    btn.classList.toggle("is-on", !!on);
    btn.setAttribute("aria-checked", on ? "true" : "false");
    this.hotelParams[id] = !!on;
  }

  /**
   * Préremplit le formulaire : valeur hôtel si présente, sinon défaut
   * (majorité bool / moyenne num). Rates affichés en %.
   */
  applyHotelParams(rawParams, defaults) {
    const raw = rawParams || {};
    const def = defaults || this.hotelParamsDefaults || {};
    this.hotelParams = {};
    const fields = (this.meta?.hotel_form?.fields || []);
    for (const f of fields) {
      let v = raw[f.id];
      const fromHotel = v != null && v !== "";
      if (!fromHotel) v = def[f.id];
      if (f.kind === "bool") {
        const on = !!v;
        this._setHpBool(f.id, on);
        const btn = document.querySelector(`[data-hp-bool="${f.id}"]`);
        if (btn) btn.classList.toggle("is-default", !fromHotel);
        continue;
      }
      const input = document.querySelector(`[data-hp="${f.id}"]`);
      if (!input) continue;
      let display = v;
      if (f.kind === "rate" && display != null && display !== "") {
        let n = Number(display);
        if (!Number.isNaN(n) && n <= 1) n *= 100;
        display = Math.round(n * 10) / 10;
      } else if (f.kind === "int" && display != null && display !== "") {
        display = Math.round(Number(display));
      } else if (f.kind === "float" && display != null && display !== "") {
        display = Number(display);
      }
      input.value =
        display == null || display === "" || Number.isNaN(Number(display))
          ? ""
          : String(display);
      input.classList.toggle("is-default", !fromHotel);
      this.hotelParams[f.id] = fromHotel ? raw[f.id] : def[f.id];
    }
  }

  collectHotelParams() {
    const out = {};
    const fields = (this.meta?.hotel_form?.fields || []);
    for (const f of fields) {
      if (f.kind === "bool") {
        const btn = document.querySelector(`[data-hp-bool="${f.id}"]`);
        out[f.id] = btn
          ? btn.getAttribute("aria-checked") === "true"
          : !!this.hotelParams[f.id];
        continue;
      }
      const input = document.querySelector(`[data-hp="${f.id}"]`);
      if (!input) continue;
      const raw = input.value;
      if (raw === "" || raw == null) {
        // laisse le backend appliquer majorité / moyenne
        continue;
      }
      let n = Number(raw);
      if (Number.isNaN(n)) continue;
      if (f.kind === "rate") {
        if (n > 1) n = n / 100;
        out[f.id] = n;
      } else if (f.kind === "int") {
        out[f.id] = Math.round(n);
      } else {
        out[f.id] = n;
      }
    }
    return out;
  }

  onSearch() {
    const raw = $("#hotel_search")?.value || "";
    const q = raw.trim();
    const list = $("#ac-hotels");
    if (!list) return;

    // Si l'index n'est pas encore là, tenter un fetch serveur (debounce léger)
    if (!this.hotelIndex.length && !this._indexLoading) {
      this._indexLoading = true;
      this.loadHotelIndex()
        .catch(() => {})
        .finally(() => {
          this._indexLoading = false;
          this.onSearch();
        });
      list.innerHTML = `<li class="ac-empty">Chargement de la liste…</li>`;
      list.classList.remove("hidden");
      return;
    }

    const hotels = this.filterHotelsLocal(q, 40);
    const parts = [];

    if (hotels.length) {
      for (const h of hotels) {
        const sessionBadge = h.session_only
          ? `<em class="ac-session">session</em>`
          : "";
        parts.push(`
        <li role="option" class="ac-item" data-code="${escapeHtml(h.hotel_code || "")}">
          <strong>${escapeHtml(h.hotel_code || "")}</strong>
          <span>${escapeHtml(h.hotel_name || "")}</span>
          <em>${escapeHtml(
            [h.hotel_brand, h.hotel_city].filter(Boolean).join(" · ")
          )}</em>
          ${sessionBadge}
        </li>`);
      }
    } else if (q) {
      parts.push(
        `<li class="ac-empty">Aucun hôtel ne correspond à « ${escapeHtml(q)} »</li>`
      );
    } else {
      parts.push(`<li class="ac-empty">Tapez un code ou un nom pour filtrer…</li>`);
    }

    // Code saisi absent de la base → proposer récupération Accor (session only)
    if (q && this.looksLikeHotelCode(q)) {
      const codeUp = q.replace(/\s+/g, "").toUpperCase();
      const known = this.allHotelsForSearch().some(
        (h) => String(h.hotel_code || "").toUpperCase() === codeUp
      );
      if (!known) {
        parts.push(`
        <li role="option" class="ac-item ac-item-fetch" data-code="${escapeHtml(
          codeUp
        )}" data-action="fetch">
          <strong>${escapeHtml(codeUp)}</strong>
          <span>Récupérer depuis Accor</span>
        </li>`);
      }
    }

    list.innerHTML = parts.join("");
    list.classList.remove("hidden");
    list.querySelectorAll(".ac-item").forEach((el) => {
      el.addEventListener("mousedown", (e) => {
        // mousedown avant blur du champ → sélection fiable
        e.preventDefault();
        if (el.dataset.action === "fetch") {
          this.selectHotel(el.dataset.code, { forceFetch: true });
        } else {
          this.selectHotel(el.dataset.code);
        }
      });
    });
  }

  _paintAcHighlight(items) {
    items.forEach((el, i) => {
      el.classList.toggle("is-active", i === this._acHighlight);
      if (i === this._acHighlight) el.scrollIntoView({ block: "nearest" });
    });
  }

  hideAc() {
    $("#ac-hotels")?.classList.add("hidden");
    this._acHighlight = -1;
  }

  async selectHotel(code, { forceFetch = false } = {}) {
    if (!code) return;
    if (this._hotelLoading) return;
    this._hotelLoading = true;
    this.hideAc();

    // Label provisoire depuis la liste autocomplete si dispo
    const fromIndex = this.allHotelsForSearch().find(
      (h) => String(h.hotel_code || "").toUpperCase() === String(code).toUpperCase()
    );
    const provisional =
      fromIndex &&
      [fromIndex.hotel_code, fromIndex.hotel_name].filter(Boolean).join(" · ");

    this.showHotelLoading(code, provisional || code);
    this.setStatus("Chargement de la fiche…");
    this.setHotelLoadProgress(15, 2, "Lecture de la fiche hôtel…");

    try {
      // persist=0 : jamais d'écriture hotel_data depuis l'UI user
      const ctx = await api.get(`/api/hotels/${encodeURIComponent(code)}/context`, {
        fetch: 1,
        persist: 0,
      });
      if (!ctx.ok && !ctx.identity && !ctx.hotel) {
        throw new Error(ctx.error || "Hôtel introuvable");
      }

      this._clearHotelLoadTimer();
      this.setHotelLoadProgress(
        78,
        3,
        "Préparation des paramètres d’exploitation…"
      );

      this.context = ctx;
      const id = ctx.identity || ctx.hotel || {};
      const ind = ctx.indicators || {};
      const corner = ctx.corner || {};
      const profile = ctx.client_profile || {};
      const resolvedCode = String(
        id.hotel_code || ctx.hotel_code || code
      ).trim();

      this.hotel = {
        hotel_code: resolvedCode,
        hotel_name: id.hotel_name || id.name || "",
        hotel_brand: id.hotel_brand || id.brand || "",
        hotel_city: id.hotel_city || id.city || "",
        hotel_params: ctx.hotel_params || {},
        hotel_params_defaults:
          ctx.hotel_params_defaults || this.hotelParamsDefaults || {},
        m_lin: ind.m_lin ?? corner.m_lin ?? null,
        mix_fb: ind.mix_fb ?? corner.mix_fb ?? null,
        client_needs: profile.client_needs || ind.client_needs || null,
        session_only: !!(ctx.session_only || forceFetch),
      };

      // Hôtel scrapé / hors base → garder en mémoire pour l'autocomplete de la session
      if (ctx.session_only || ctx.scraped || forceFetch) {
        this.rememberSessionHotel({
          hotel_code: this.hotel.hotel_code,
          hotel_name: this.hotel.hotel_name,
          hotel_brand: this.hotel.hotel_brand,
          hotel_city: this.hotel.hotel_city,
          session_only: true,
        });
      }

      $("#hotel_code").value = this.hotel.hotel_code;
      $("#hotel_search").value =
        `${this.hotel.hotel_code} · ${this.hotel.hotel_name || ""}`.trim();
      this.fillHotelSummary();

      // yield UI pour peindre la barre avant le rendu formulaire (peut être lourd)
      await new Promise((r) => requestAnimationFrame(() => r()));
      this.setHotelLoadProgress(90, 3, "Remplissage du formulaire…");
      this.fillStep2();
      this.fillStep3FromHotel();
      $("#btn-step1-next").disabled = false;

      this.setHotelLoadProgress(100, 4, "Fiche prête.");
      await new Promise((r) => setTimeout(r, 220));

      this.hideHotelLoading();
      this.setStatus("");
      if (ctx.session_only) {
        toast.show("Hôtel chargé", "ok");
      }
      this.goStep(2);
    } catch (err) {
      this.hideHotelLoading();
      this.setStatus(err.message);
      toast.show(err.message, "err");
    } finally {
      this._hotelLoading = false;
    }
  }

  rememberSessionHotel(h) {
    if (!h?.hotel_code) return;
    const code = String(h.hotel_code).toUpperCase();
    this.sessionHotels = this.sessionHotels.filter(
      (x) => String(x.hotel_code || "").toUpperCase() !== code
    );
    this.sessionHotels.unshift({ ...h, hotel_code: h.hotel_code });
  }

  fillHotelSummary() {
    const el = $("#hotel-summary");
    if (!el || !this.hotel) return;
    el.classList.remove("empty");
    el.hidden = false;
    const meta = [this.hotel.hotel_brand, this.hotel.hotel_city]
      .filter(Boolean)
      .join(" · ");
    el.innerHTML = `
      <div class="hs-row">
        <strong>${escapeHtml(this.hotel.hotel_code)}</strong>
        <span class="hs-name">${escapeHtml(this.hotel.hotel_name || "")}</span>
      </div>
      ${meta ? `<div class="hs-brand">${escapeHtml(meta)}</div>` : ""}`;
  }

  fillStep2() {
    if (!this.hotel) return;
    const line = $("#step2-hotel-line");
    if (line) {
      const meta = [this.hotel.hotel_brand, this.hotel.hotel_city]
        .filter(Boolean)
        .join(" · ");
      line.innerHTML = `
        <span class="hl-code">${escapeHtml(this.hotel.hotel_code || "")}</span>
        <span class="hl-name">${escapeHtml(this.hotel.hotel_name || "")}</span>
        ${meta ? `<span class="hl-meta">${escapeHtml(meta)}</span>` : ""}`;
    }
    if (!this._hotelFormBuilt && this.meta?.hotel_form) {
      this.renderHotelParamsForm(this.meta.hotel_form);
    }
    this.applyHotelParams(
      this.hotel.hotel_params || {},
      this.hotel.hotel_params_defaults || this.hotelParamsDefaults
    );
  }

  fillStep3FromHotel() {
    if (!this.hotel) return;
    if (this.hotel.m_lin != null && Number(this.hotel.m_lin) > 0) {
      this.setMLin(this.hotel.m_lin);
    }
    if (this.hotel.mix_fb != null) {
      let m = Number(this.hotel.mix_fb);
      if (m <= 1) m *= 100;
      this.setMix(Math.round(m));
    }
    if (this.hotel.client_needs && typeof this.hotel.client_needs === "object") {
      this.applyNeeds(this.hotel.client_needs);
    }
  }

  renderNeeds(meta) {
    const fill = (hostId, items, channel) => {
      const host = $("#" + hostId);
      if (!host) return;
      const list = items || [];
      const active = list.filter((it) => it.default !== false);
      const eq = active.length ? Math.round(1000 / active.length) / 10 : 0;
      host.innerHTML = list
        .map((it) => {
          const on = it.default !== false;
          const pct = on ? eq : 0;
          return `
        <div class="share-row ${on ? "is-on" : "is-off"}" data-need="${escapeHtml(
          it.id
        )}" data-channel="${channel}">
          <button type="button" class="share-toggle ${on ? "is-on" : ""}" role="switch"
            aria-checked="${on ? "true" : "false"}" data-need-toggle="${escapeHtml(it.id)}">
            <span class="need-toggle-lab">${escapeHtml(it.label || it.id)}</span>
            <span class="toggle-track" aria-hidden="true"><span class="toggle-thumb"></span></span>
          </button>
          <label class="share-pct">
            <input type="number" min="0" max="100" step="1"
              data-share="${escapeHtml(it.id)}" data-channel="${channel}"
              value="${pct}" ${on ? "" : "disabled"} />
            <span>%</span>
          </label>
        </div>`;
        })
        .join("");
      host.querySelectorAll("[data-need-toggle]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const row = btn.closest(".share-row");
          const next = btn.getAttribute("aria-checked") !== "true";
          btn.setAttribute("aria-checked", next ? "true" : "false");
          btn.classList.toggle("is-on", next);
          if (row) {
            row.classList.toggle("is-on", next);
            row.classList.toggle("is-off", !next);
            const inp = row.querySelector("[data-share]");
            if (inp) {
              inp.disabled = !next;
              if (!next) inp.value = "0";
              else this._redistributeEqual(channel);
            }
          }
          this._updateShareSums();
        });
      });
      enhanceNumSteps(host);
      host.querySelectorAll("[data-share]").forEach((inp) => {
        inp.addEventListener("input", () => this._updateShareSums());
        inp.addEventListener("change", () => this._updateShareSums());
      });
    };
    fill("needs-fb", meta.client_needs_fb, "fb");
    fill("needs-nfb", meta.client_needs_nfb, "nfb");
    this._updateShareSums();
  }

  _redistributeEqual(channel) {
    const rows = $$(`.share-row[data-channel="${channel}"].is-on [data-share]`);
    if (!rows.length) return;
    const eq = Math.floor(1000 / rows.length) / 10;
    let acc = 0;
    rows.forEach((inp, i) => {
      if (i === rows.length - 1) inp.value = String(Math.round((100 - acc) * 10) / 10);
      else {
        inp.value = String(eq);
        acc += eq;
      }
    });
  }

  _updateShareSums() {
    const sum = (channel) => {
      let s = 0;
      $$(`[data-share][data-channel="${channel}"]`).forEach((inp) => {
        if (inp.disabled) return;
        s += Number(inp.value) || 0;
      });
      return s;
    };
    const fb = sum("fb");
    const nfb = sum("nfb");
    const elFb = $("#sum-fb");
    const elNfb = $("#sum-nfb");
    if (elFb) {
      elFb.textContent = `${Math.round(fb * 10) / 10} %`;
      elFb.classList.toggle("is-ok", Math.abs(fb - 100) < 0.6);
      elFb.classList.toggle("is-bad", Math.abs(fb - 100) >= 0.6);
    }
    if (elNfb) {
      elNfb.textContent = `${Math.round(nfb * 10) / 10} %`;
      elNfb.classList.toggle("is-ok", Math.abs(nfb - 100) < 0.6);
      elNfb.classList.toggle("is-bad", Math.abs(nfb - 100) >= 0.6);
    }
  }

  applyNeeds(map) {
    Object.keys(map || {}).forEach((id) => {
      const on = !!map[id];
      const btn = document.querySelector(`[data-need-toggle="${id}"]`);
      const row = document.querySelector(`.share-row[data-need="${id}"]`);
      if (btn) {
        btn.setAttribute("aria-checked", on ? "true" : "false");
        btn.classList.toggle("is-on", on);
      }
      if (row) {
        row.classList.toggle("is-on", on);
        row.classList.toggle("is-off", !on);
        const inp = row.querySelector("[data-share]");
        if (inp) {
          inp.disabled = !on;
          if (!on) inp.value = "0";
        }
      }
    });
    // égaliser chaque canal
    this._redistributeEqual("fb");
    this._redistributeEqual("nfb");
    this._updateShareSums();
  }

  applyCategoryShares(cat) {
    if (!cat) return;
    const applyList = (list, channel) => {
      (list || []).forEach((row) => {
        const id = row.id;
        const on = row.enabled !== false && (row.share || 0) > 0;
        const btn = document.querySelector(`[data-need-toggle="${id}"]`);
        const rowEl = document.querySelector(`.share-row[data-need="${id}"]`);
        if (btn) {
          btn.setAttribute("aria-checked", on ? "true" : "false");
          btn.classList.toggle("is-on", on);
        }
        if (rowEl) {
          rowEl.classList.toggle("is-on", on);
          rowEl.classList.toggle("is-off", !on);
          const inp = rowEl.querySelector("[data-share]");
          if (inp) {
            inp.disabled = !on;
            inp.value = on ? String(Math.round((row.pct ?? row.share * 100) * 10) / 10) : "0";
          }
        }
      });
    };
    applyList(cat.fb, "fb");
    applyList(cat.nfb, "nfb");
    this._updateShareSums();
  }

  setAllNeeds(on) {
    $$(".share-row").forEach((row) => {
      const btn = row.querySelector("[data-need-toggle]");
      const inp = row.querySelector("[data-share]");
      if (btn) {
        btn.setAttribute("aria-checked", on ? "true" : "false");
        btn.classList.toggle("is-on", !!on);
      }
      row.classList.toggle("is-on", !!on);
      row.classList.toggle("is-off", !on);
      if (inp) {
        inp.disabled = !on;
        if (!on) inp.value = "0";
      }
    });
    if (on) {
      this._redistributeEqual("fb");
      this._redistributeEqual("nfb");
    }
    this._updateShareSums();
  }

  setMLin(v) {
    // Entiers uniquement — minimum métier 2 m linéaires
    let n = Math.round(Number(v));
    if (!Number.isFinite(n) || n < 2) n = Math.max(2, n || 6);
    n = Math.min(40, Math.max(2, n));
    if ($("#m_lin_slider")) $("#m_lin_slider").value = String(n);
    if ($("#m_lin")) $("#m_lin").value = String(n);
    if ($("#m-lin-val")) $("#m-lin-val").textContent = String(n);
  }

  setMix(pct) {
    const p = Math.min(100, Math.max(0, Number(pct) || 0));
    const r = Math.round(p);
    if ($("#mix_slider")) {
      $("#mix_slider").value = String(r);
      $("#mix_slider").setAttribute("aria-valuenow", String(r));
    }
    if ($("#mix_fb")) $("#mix_fb").value = String(r);
    if ($("#mix-val")) $("#mix-val").textContent = String(r);
    if ($("#mix-nf-val")) $("#mix-nf-val").textContent = String(100 - r);
  }

  collectNeeds() {
    const needs = {};
    $$(".share-row[data-need]").forEach((row) => {
      needs[row.dataset.need] = row.classList.contains("is-on");
    });
    return needs;
  }

  collectShares() {
    const fb = {};
    const nfb = {};
    $$("[data-share]").forEach((inp) => {
      const id = inp.dataset.share;
      const ch = inp.dataset.channel;
      const on = !inp.disabled;
      let pct = on ? Number(inp.value) || 0 : 0;
      if (pct < 0) pct = 0;
      const share = pct / 100;
      if (ch === "fb") fb[id] = share;
      else nfb[id] = share;
    });
    return { fb, nfb };
  }

  _syncFrigoVisibility() {
    const mix =
      (Number($("#mix_slider")?.value ?? $("#mix_fb")?.value) || 0) / 100;
    const ff = $("#field-frigos-froid");
    const fa = $("#field-frigos-ambiant");
    if (ff) ff.classList.toggle("is-dimmed", mix < 0.1);
    if (fa) fa.classList.toggle("is-dimmed", mix > 0.9);
  }

  /**
   * Redistribue l'écart pour que les parts actives d'un canal = 100 %.
   * Écart proportionnel aux parts actuelles (si somme 0 → égalitaire).
   * @returns {{ adjusted: boolean, sumBefore: number, sumAfter: number, n: number }}
   */
  _normalizeChannelPct(channel) {
    const inputs = [];
    $$(`[data-share][data-channel="${channel}"]`).forEach((inp) => {
      if (inp.disabled) return;
      let v = Number(inp.value);
      if (!Number.isFinite(v) || v < 0) v = 0;
      inputs.push({ inp, v });
    });
    const n = inputs.length;
    if (n === 0) return { adjusted: false, sumBefore: 0, sumAfter: 0, n: 0 };

    let sum = inputs.reduce((a, x) => a + x.v, 0);
    const sumBefore = sum;
    if (Math.abs(sum - 100) < 0.05) {
      return { adjusted: false, sumBefore, sumAfter: sum, n };
    }

    if (sum <= 1e-9) {
      // Toutes à 0 → parts égales
      const eq = Math.floor((1000 / n)) / 10;
      let acc = 0;
      inputs.forEach((x, i) => {
        if (i === n - 1) x.inp.value = String(Math.round((100 - acc) * 10) / 10);
        else {
          x.inp.value = String(eq);
          acc += eq;
        }
      });
    } else {
      // Redistribue l'écart proportionnellement (scale pour somme = 100)
      const coef = 100 / sum;
      let acc = 0;
      inputs.forEach((x, i) => {
        if (i === n - 1) {
          x.inp.value = String(Math.round((100 - acc) * 10) / 10);
        } else {
          const nv = Math.round(x.v * coef * 10) / 10;
          x.inp.value = String(nv);
          acc += nv;
        }
      });
    }
    sum = 0;
    inputs.forEach((x) => {
      sum += Number(x.inp.value) || 0;
    });
    return {
      adjusted: Math.abs(sumBefore - 100) >= 0.05,
      sumBefore,
      sumAfter: sum,
      n,
    };
  }

  /**
   * Normalise F&B et N-F&B sans bloquer. Ne refuse que s'il n'y a aucune catégorie.
   * @returns {{ ok: boolean, message?: string, renormalized: boolean }}
   */
  ensureSharesReady() {
    const nOn = $$(".share-row.is-on").length;
    if (nOn === 0) {
      return {
        ok: false,
        message: "Activez au moins une sous-catégorie produit.",
        renormalized: false,
      };
    }
    const fb = this._normalizeChannelPct("fb");
    const nfb = this._normalizeChannelPct("nfb");
    this._updateShareSums();
    const renormalized = fb.adjusted || nfb.adjusted;
    return { ok: true, renormalized, fb, nfb };
  }

  collectBody(optimize = false) {
    const hotel_params = this.collectHotelParams();
    const shares = this.collectShares();
    let mLin = Math.round(Number($("#m_lin")?.value)) || 6;
    if (mLin < 2) mLin = 2;
    return {
      hotel_code: ($("#hotel_code")?.value || this.hotel?.hotel_code || "").trim(),
      hotel_name: this.hotel?.hotel_name || "",
      hotel_brand: this.hotel?.hotel_brand || "",
      hotel_params,
      nb_chambres: hotel_params.hotel_nb_chambres ?? null,
      taux_occupation: hotel_params.hotel_to_annuel ?? null,
      guests_per_chambre: hotel_params.guests_per_chambre ?? null,
      derniere_reno: hotel_params.hotel_derniere_reno ?? null,
      nb_restaurants: hotel_params.hotel_f_b_restaurant ?? null,
      has_pool: !!hotel_params.hotel_non_f_b_piscine,
      has_vitrine: !!hotel_params.hotel_dispo_dans_lobby_vitrine_refrigeree,
      m_lin: mLin,
      mix_fb: (Number($("#mix_slider")?.value ?? $("#mix_fb")?.value) || 70) / 100,
      client_needs: this.collectNeeds(),
      category_shares: shares,
      shares_fb: shares.fb,
      shares_nfb: shares.nfb,
      contract: ($("#contract")?.value || "BUY").toUpperCase(),
      agencement: ($("#agencement")?.value || "CLASSIC").toUpperCase(),
      nb_scanners: Math.max(0, Math.round(Number($("#nb_scanners")?.value) || 1)),
      nb_caisses: Math.max(0, Math.round(Number($("#nb_caisses")?.value) || 1)),
      nb_vitrines: Math.max(0, Math.round(Number($("#nb_vitrines")?.value) || 1)),
      nb_frigos_froid: Math.max(0, Math.round(Number($("#nb_frigos_froid")?.value) || 0)),
      nb_frigos_ambiant: Math.max(0, Math.round(Number($("#nb_frigos_ambiant")?.value) || 0)),
      optimize_repartition: !!optimize,
      mode: optimize ? "optimize" : "simulate",
      suggest_optimization: true,
    };
  }

  async runSim(optimize = false) {
    // Ne bloque pas si ≠ 100 % : on redistribue l'écart sur les catégories actives
    const prep = this.ensureSharesReady();
    if (!prep.ok) {
      toast.show(prep.message || "Parts invalides", "err");
      return;
    }
    if (prep.renormalized && !optimize) {
      toast.show(
        "Parts réajustées à 100 % (écart réparti sur les sous-catégories actives).",
        "ok"
      );
    }
    const body = this.collectBody(optimize);
    if (!body.hotel_code) {
      toast.show("Choisissez d'abord un hôtel", "err");
      this.goStep(1);
      return;
    }
    this.goStep(4);
    $("#dir-loading")?.classList.remove("hidden");
    $("#dir-results")?.classList.add("hidden");
    const loadTitle = $("#dir-loading .dir-empty-title");
    const loadSub = $("#dir-loading .dir-empty-sub");
    if (loadTitle) {
      loadTitle.textContent = optimize
        ? "Optimisation en cours…"
        : "Simulation en cours…";
    }
    if (loadSub) {
      loadSub.textContent = optimize
        ? "Exploration des mix F&B et des sous-catégories selon les règles ROD."
        : "Calcul avec votre répartition, puis détection d’une meilleure option.";
    }
    this.setStatus(
      optimize
        ? "Optimisation mix F&B × sous-catégories…"
        : "Simulation avec votre répartition…"
    );
    try {
      const data = await api.post("/api/rod/simulate", body);
      if (!data.ok) throw new Error(data.error || "La simulation n'a pas abouti");
      this.result = data;
      const ass = data.assortment || {};
      // N'applique mix / parts optimisés que si le mode optimise a été demandé
      if (ass.optimized) {
        if (data.category_shares) this.applyCategoryShares(data.category_shares);
        if (data.hotel?.mix_fb != null) {
          let m = Number(data.hotel.mix_fb);
          if (m <= 1) m *= 100;
          this.setMix(Math.round(m));
        }
      }
      this.renderResults(data);
      $("#dir-loading")?.classList.add("hidden");
      $("#dir-results")?.classList.remove("hidden");
      const tag = ass.optimized ? "optimisé" : "simulé";
      this.setStatus(
        `${data.hotel?.hotel_code || body.hotel_code} · ${
          data.recommended_solution || "—"
        } · ${tag}`
      );
      const s4 = document.querySelector('.wiz-step[data-step="4"]');
      if (s4) s4.disabled = false;
    } catch (err) {
      this.setStatus(err.message);
      toast.show(err.message, "err");
      $("#dir-loading")?.classList.add("hidden");
    }
  }

  setResultTab(tab) {
    this.resultTab = tab === "ai" ? "ai" : "sim";
    $$("[data-result-tab]").forEach((btn) => {
      const on = btn.dataset.resultTab === this.resultTab;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    $$("[data-result-pane]").forEach((pane) => {
      const on = pane.dataset.resultPane === this.resultTab;
      pane.classList.toggle("is-active", on);
      if (on) pane.removeAttribute("hidden");
      else pane.setAttribute("hidden", "");
    });
  }

  _metricsHtml(block, { caLabel, emptyCa }) {
    const ca = block?.ca_mensuel;
    const notProf = block?.not_profitable || block?.status === "not_profitable";
    const caDisplay =
      ca == null ? emptyCa || "—" : notProf && Number(ca) < 0 ? "Not profitable" : euro(ca);
    const mp = block?.marge_produit_mensuelle;
    const marge = block?.marge_nette_mensuelle;
    const margeDisplay = notProf ? "Not profitable" : marge == null ? "—" : euro(marge);
    const amort =
      notProf || block?.amort_months == null
        ? "—"
        : `${Number(block.amort_months).toFixed(1)} mois` +
          (block.amort_years != null ? ` · ${Number(block.amort_years).toFixed(1)} ans` : "");
    return `
      <div class="big-metric primary ${notProf ? "is-np" : ""}">
        <span class="bm-icon" aria-hidden="true">◆</span>
        <span class="bm-label">${caLabel}</span>
        <span class="bm-value">${caDisplay}</span>
        <span class="bm-sub">HT / mois · F&amp;B ${
          block?.ca_fb_mensuel == null ? "—" : euro(block.ca_fb_mensuel)
        } · N-F&amp;B ${
          block?.ca_nfb_mensuel == null ? "—" : euro(block.ca_nfb_mensuel)
        }</span>
      </div>
      <div class="big-metric">
        <span class="bm-icon" aria-hidden="true">◈</span>
        <span class="bm-label">Marge produits / mois</span>
        <span class="bm-value">${mp == null ? "—" : euro(mp)}</span>
        <span class="bm-sub">CA − CA/coeff (2,6 F&amp;B · 1,45 N-F&amp;B)</span>
      </div>
      <div class="big-metric">
        <span class="bm-icon" aria-hidden="true">◇</span>
        <span class="bm-label">Coûts / mois</span>
        <span class="bm-value">${euro(block?.cout_mensuel)}</span>
        <span class="bm-sub">techno ${euro(block?.techno_monthly)} · annexes ${euro(
          block?.annexes_monthly
        )} · agenc. ${euro(block?.agencement_monthly)}</span>
      </div>
      <div class="big-metric ${notProf ? "is-np" : ""}">
        <span class="bm-icon" aria-hidden="true">▣</span>
        <span class="bm-label">Bénéfice (marge nette) / mois</span>
        <span class="bm-value ${
          notProf ? "neg" : marge == null ? "" : Number(marge) >= 0 ? "pos" : "neg"
        }">${margeDisplay}</span>
        <span class="bm-sub">${
          notProf
            ? "Marge produits − coûts &lt; 0"
            : `Marge produits − coûts` +
              (block?.marge_nette_annuelle == null
                ? ""
                : ` · ${euro(block.marge_nette_annuelle)}/an`) +
              (block.taux_marge != null
                ? ` · ${(Number(block.taux_marge) * 100).toFixed(1)} % du CA`
                : "")
        }</span>
      </div>
      <div class="big-metric">
        <span class="bm-icon" aria-hidden="true">○</span>
        <span class="bm-label">Amortissement</span>
        <span class="bm-value ${notProf ? "neg" : ""}">${
          notProf ? "—" : amort === "—" ? "—" : amort.split(" · ")[0]
        }</span>
        <span class="bm-sub">${
          notProf
            ? "Non calculé si non rentable"
            : amort === "—"
              ? "coût 60 mois ÷ marge nette"
              : `coût 60 mois ${euro(block?.cost_over_60m)} ÷ marge nette` +
                (block?.amort_years != null
                  ? ` · ${Number(block.amort_years).toFixed(1)} ans`
                  : "")
        }</span>
      </div>`;
  }

  _pnlDetailHtml(block) {
    if (!block || block.ca_mensuel == null) return "";
    const lines = Array.isArray(block.cost_lines) ? block.cost_lines : [];
    const byGroup = { techno: [], annexes: [], agencement: [] };
    lines.forEach((l) => {
      const g = l.group || "techno";
      if (!byGroup[g]) byGroup[g] = [];
      byGroup[g].push(l);
    });
    const renderGroup = (title, rows) => {
      if (!rows.length) return "";
      return `
        <div class="pnl-group">
          <h4>${title}</h4>
          ${rows
            .map(
              (r) => `
            <div class="pnl-line">
              <span>${escapeHtml(r.label || r.id)}${
                r.qty && r.qty !== 1 ? ` ×${r.qty}` : ""
              }</span>
              <strong>${euro(r.monthly)}/mois</strong>
            </div>`
            )
            .join("")}
        </div>`;
    };
    const bd = block.breakdown || {};
    return `
      <div class="pnl-detail-grid">
        <div class="pnl-card">
          <h3 class="dir-subh">CA HT (cascade règles)</h3>
          <div class="pnl-line"><span>R1 · clients acheteurs</span><strong>${euro(
            (bd.ca_r1_fb || 0) + (bd.ca_r1_nfb || 0)
          )}</strong></div>
          <div class="pnl-line"><span>R2 · après mix</span><strong>${euro(
            (bd.ca_r2_fb || 0) + (bd.ca_r2_nfb || 0)
          )}</strong></div>
          <div class="pnl-line"><span>R3 · catégories</span><strong>${euro(
            (bd.ca_r3_fb || 0) + (bd.ca_r3_nfb || 0)
          )}</strong></div>
          <div class="pnl-line pnl-total"><span>R4 · CA final F&amp;B</span><strong>${euro(
            block.ca_fb_mensuel
          )}</strong></div>
          <div class="pnl-line pnl-total"><span>R4 · CA final N-F&amp;B</span><strong>${euro(
            block.ca_nfb_mensuel
          )}</strong></div>
          <div class="pnl-line"><span>Marge produits (CA − CA/coeff)</span><strong class="pos">${euro(
            block.marge_produit_mensuelle
          )}</strong></div>
          <div class="pnl-line pnl-total"><span>Bénéfice = marge prod. − coûts</span><strong class="${
            block.not_profitable || (block.marge_nette_mensuelle || 0) < 0 ? "neg" : "pos"
          }">${
            block.not_profitable
              ? "Not profitable"
              : euro(block.marge_nette_mensuelle)
          }</strong></div>
          <div class="pnl-line"><span>Amortissement (coût 60 m / bénéfice)</span><strong>${
            block.not_profitable || block.amort_months == null
              ? "—"
              : Number(block.amort_months).toFixed(1) + " mois"
          }</strong></div>
        </div>
        <div class="pnl-card">
          <h3 class="dir-subh">Coûts mensuels</h3>
          ${renderGroup("Techno", byGroup.techno || [])}
          ${renderGroup("Annexes", byGroup.annexes || [])}
          ${renderGroup("Agencement", byGroup.agencement || [])}
          <div class="pnl-line pnl-total"><span>Total coûts</span><strong>${euro(
            block.cout_mensuel
          )}</strong></div>
          <div class="pnl-line"><span>Capex initial (achat)</span><strong>${euro(
            block.capex
          )}</strong></div>
          <div class="pnl-line"><span>Coût total sur 60 mois</span><strong>${euro(
            block.cost_over_60m
          )}</strong></div>
        </div>
      </div>`;
  }

  _cardsHtml(bySolution, reco) {
    return ["SIMPLY", "LIBERTY", "CONNECTED"]
      .map((c) => {
        const b = (bySolution || {})[c] || {};
        const isReco = c === reco;
        const notProf = b.not_profitable || b.status === "not_profitable";
        const marge = b.marge_nette_mensuelle;
        return `
          <article class="concept-card ${isReco ? "recommended" : ""} ${
            notProf ? "is-np" : ""
          }">
            <header>
              <h3>${c}</h3>
              <div class="cc-badges">
              ${isReco ? `<span class="badge-reco">Recommandée</span>` : ""}
              ${notProf ? `<span class="badge-np">Not profitable</span>` : ""}
              </div>
            </header>
            <div class="cc-row"><span>CA F&amp;B / mois</span><strong>${
              b.ca_fb_mensuel == null ? "—" : euro(b.ca_fb_mensuel)
            }</strong></div>
            <div class="cc-row"><span>CA N-F&amp;B / mois</span><strong>${
              b.ca_nfb_mensuel == null ? "—" : euro(b.ca_nfb_mensuel)
            }</strong></div>
            <div class="cc-row"><span>CA total / mois</span><strong>${
              b.ca_mensuel == null ? "—" : euro(b.ca_mensuel)
            }</strong></div>
            <div class="cc-row"><span>Marge produits</span><strong>${
              b.marge_produit_mensuelle == null ? "—" : euro(b.marge_produit_mensuelle)
            }</strong></div>
            <div class="cc-row"><span>Coût / mois</span><strong>${euro(
              b.cout_mensuel
            )}</strong></div>
            <div class="cc-row"><span>Bénéfice (marge nette)</span><strong class="${
              notProf ? "neg" : marge == null ? "" : Number(marge) >= 0 ? "pos" : "neg"
            }">${
              notProf ? "Not profitable" : marge == null ? "—" : euro(marge)
            }</strong></div>
            <div class="cc-row"><span>Amort. (÷ bénéfice)</span><strong>${
              notProf || b.amort_months == null
                ? "—"
                : Number(b.amort_months).toFixed(1) + " mois"
            }</strong></div>
            <div class="cc-row"><span>Capex</span><strong>${euro(b.capex)}</strong></div>
          </article>`;
      })
      .join("");
  }

  renderAssortment(data) {
    const cat = data.category_shares || {};
    const ass = data.assortment || {};
    const h = data.hotel || {};
    const note = $("#dir-assortment-note");
    if (note) {
      if (ass.optimized) {
        note.textContent = `Répartition optimisée (${ass.strategy || "—"}${
          ass.trials ? ` · ${ass.trials} essais` : ""
        }) — meilleur mix F&B et sous-catégories selon les règles ROD.`;
      } else {
        note.textContent =
          "Répartition saisie (parts = 100 % par canal F&B et Non F&B).";
      }
    }
    let mixFb = Number(h.mix_fb);
    if (Number.isFinite(mixFb)) {
      if (mixFb <= 1) mixFb *= 100;
      if ($("#dir-mix-fb")) $("#dir-mix-fb").textContent = `${Math.round(mixFb)} % du mix`;
      if ($("#dir-mix-nfb"))
        $("#dir-mix-nfb").textContent = `${Math.round(100 - mixFb)} % du mix`;
    }
    const paint = (hostId, rows) => {
      const host = $("#" + hostId);
      if (!host) return;
      const list = (rows || []).filter((r) => r.enabled && (r.share || 0) > 0);
      if (!list.length) {
        host.innerHTML = `<p class="muted">Aucun produit actif</p>`;
        return;
      }
      host.innerHTML = list
        .map(
          (r) => `
        <div class="assort-bar-row">
          <span class="assort-lab">${escapeHtml(r.label || r.id)}</span>
          <span class="assort-track"><i style="width:${Math.min(
            100,
            Math.round((r.pct || r.share * 100) * 10) / 10
          )}%"></i></span>
          <span class="assort-pct">${Math.round((r.pct || r.share * 100) * 10) / 10} %</span>
        </div>`
        )
        .join("");
    };
    paint("dir-shares-fb", cat.fb);
    paint("dir-shares-nfb", cat.nfb);
  }

  /**
   * Bannière « Optimisation possible » après une simulation user.
   */
  renderOptBanner(data) {
    const host = $("#dir-opt-banner");
    if (!host) return;
    const ass = data.assortment || {};
    const sug = ass.suggestion || {};

    if (ass.optimized) {
      host.classList.remove("hidden");
      host.className = "opt-banner is-applied";
      const mixPct = Math.round(Number(data.hotel?.mix_fb ?? 0) * (Number(data.hotel?.mix_fb) <= 1 ? 100 : 1));
      host.innerHTML = `
        <div class="opt-banner-body">
          <strong>Répartition optimisée appliquée</strong>
          <p>Mix F&amp;B ${mixPct}&nbsp;% · stratégie ${escapeHtml(
            ass.strategy || "—"
          )} · ${ass.trials || 0} essais.</p>
        </div>`;
      return;
    }

    if (ass.improvement_possible && sug.available) {
      const dM = Number(sug.delta_marge) || 0;
      const dC = Number(sug.delta_ca) || 0;
      const mixPct = Math.round((Number(sug.mix_fb) || 0) * 100);
      host.classList.remove("hidden");
      host.className = "opt-banner is-suggest";
      host.innerHTML = `
        <div class="opt-banner-body">
          <strong>Optimisation possible</strong>
          <p>
            Une meilleure répartition a été trouvée
            (mix F&amp;B ${mixPct}&nbsp;% · +${euro(dM)}/mois de marge nette
            · +${euro(dC)}/mois de CA sur la solution recommandée,
            ${sug.trials || 0} essais).
          </p>
        </div>
        <button type="button" class="btn btn-primary btn-sm" id="btn-apply-opt">
          Appliquer l’optimisation
        </button>`;
      $("#btn-apply-opt")?.addEventListener("click", () => this.runSim(true));
      return;
    }

    host.classList.add("hidden");
    host.innerHTML = "";
  }

  renderResults(data) {
    const reco = data.recommended_solution || "—";
    if ($("#dir-reco-name")) $("#dir-reco-name").textContent = reco;
    const h = data.hotel || {};
    if ($("#dir-hotel-line")) {
      $("#dir-hotel-line").textContent = [
        h.hotel_code,
        h.hotel_name,
        h.hotel_brand,
      ]
        .filter(Boolean)
        .join(" · ");
    }
    const reasons = (data.recommendation_reasons || []).join(" ");
    if ($("#dir-reco-why")) $("#dir-reco-why").textContent = reasons;
    this.renderAssortment(data);
    this.renderOptBanner(data);

    const sim = data.simulator || {};
    const ai = data.ai || {};
    const simBy = sim.by_solution || {};
    const aiBy = ai.by_solution || {};

    const simBlock = simBy[reco] || {};
    const aiBlock = aiBy[reco] || {};

    const banner = $("#dir-status-banner");
    if (banner) {
      if (simBlock.not_profitable || simBlock.status === "not_profitable") {
        banner.classList.remove("hidden");
        banner.className = "status-banner is-np";
        banner.textContent =
          "Not profitable — la marge nette de la solution recommandée est négative (ou le CA l’est).";
      } else if (h.m_lin_forced_min) {
        banner.classList.remove("hidden");
        banner.className = "status-banner is-warn";
        banner.textContent =
          "Mètres linéaires forcés au minimum métier de 2 m (paramètre système).";
      } else {
        banner.classList.add("hidden");
        banner.textContent = "";
      }
    }

    const hostSim = $("#dir-metrics-sim");
    if (hostSim) {
      hostSim.innerHTML = this._metricsHtml(simBlock, {
        caLabel: "CA HT / mois",
      });
    }
    const hostPnl = $("#dir-pnl-detail-sim");
    if (hostPnl) {
      hostPnl.innerHTML = this._pnlDetailHtml(simBlock);
    }
    const hostAi = $("#dir-metrics-ai");
    if (hostAi) {
      hostAi.innerHTML = this._metricsHtml(aiBlock, {
        caLabel: "CA estimé par le modèle / mois",
        emptyCa: "Indisponible",
      });
    }

    if ($("#dir-cards-sim")) {
      $("#dir-cards-sim").innerHTML = this._cardsHtml(simBy, reco);
    }
    if ($("#dir-cards-ai")) {
      $("#dir-cards-ai").innerHTML = this._cardsHtml(aiBy, reco);
    }

    if ($("#dir-ai-note")) {
      $("#dir-ai-note").textContent =
        ai.note ||
        data.ai_note ||
        "Estimation du CA par le modèle, avec les mêmes coûts et une marge recalculée.";
    }

    // Onglet IA un peu grisé si indispo
    const tabAi = $("#tab-ai");
    if (tabAi) {
      tabAi.classList.toggle("is-disabled-soft", ai.available === false);
      tabAi.title =
        ai.available === false
          ? "Modèle indisponible pour le moment"
          : "Voir l'estimation du modèle";
    }

    this.setResultTab("sim");
  }
}

const app = new DirectorApp();
app.init();
