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
    $("#btn-run-sim")?.addEventListener("click", () => this.runSim(true));
    $("#btn-run-sim-manual")?.addEventListener("click", () => this.runSim(false));

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
      this.setMix($("#mix_fb")?.value || $("#mix_slider")?.value);
    };
    $("#mix_slider")?.addEventListener("input", () => {
      $("#mix_fb").value = $("#mix_slider").value;
      syncMix();
    });
    $("#mix_fb")?.addEventListener("input", () => {
      $("#mix_slider").value = $("#mix_fb").value;
      syncMix();
    });

    $("#needs-all-on")?.addEventListener("click", () => this.setAllNeeds(true));
    $("#needs-all-off")?.addEventListener("click", () => this.setAllNeeds(false));

    // Onglets résultats
    $$("[data-result-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        this.setResultTab(btn.dataset.resultTab);
      });
    });
  }

  /**
   * Construit le formulaire paramètres de base (toutes variables hotel_data utiles).
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
              .map((f) => {
                const min =
                  f.min != null ? ` min="${f.min}"` : "";
                const max =
                  f.max != null ? ` max="${f.max}"` : "";
                const step =
                  f.step != null ? ` step="${f.step}"` : ' step="any"';
                return `<label class="field field-float" data-field="${escapeHtml(
                  f.id
                )}">
                <span>${escapeHtml(f.label)}${
                  f.hint
                    ? ` <em class="field-hint" title="${escapeHtml(
                        f.hint
                      )}">?</em>`
                    : ""
                }</span>
                <input type="number" data-hp="${escapeHtml(
                  f.id
                )}" data-kind="${escapeHtml(f.kind)}"${min}${max}${step} />
              </label>`;
              })
              .join("")}</div>`
          : "";
        const boolHtml = bools.length
          ? `<div class="toggle-grid hotel-params-toggles">${bools
              .map(
                (f) => `<button type="button" class="toggle-row" role="switch"
                aria-checked="false" data-hp-bool="${escapeHtml(f.id)}"
                title="${escapeHtml(f.hint || f.label)}">
                <span class="toggle-icon" aria-hidden="true">●</span>
                <span class="toggle-copy">
                  <strong>${escapeHtml(f.label)}</strong>
                  ${
                    f.hint
                      ? `<em>${escapeHtml(f.hint)}</em>`
                      : ""
                  }
                </span>
                <span class="toggle-track" aria-hidden="true"><span class="toggle-thumb"></span></span>
              </button>`
              )
              .join("")}</div>`
          : "";
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
    this.hideAc();
    this.setStatus("Chargement de la fiche…");
    try {
      // persist=0 : jamais d'écriture hotel_data depuis l'UI user
      const ctx = await api.get(`/api/hotels/${encodeURIComponent(code)}/context`, {
        fetch: 1,
        persist: 0,
      });
      if (!ctx.ok && !ctx.identity && !ctx.hotel) {
        throw new Error(ctx.error || "Hôtel introuvable");
      }
      this.context = ctx;
      const id = ctx.identity || ctx.hotel || {};
      const op = ctx.operating || {};
      const services = ctx.services || {};
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
      this.fillStep2();
      this.fillStep3FromHotel();
      $("#btn-step1-next").disabled = false;
      this.setStatus("");
      if (ctx.session_only) {
        toast.show("Hôtel chargé", "ok");
      }
      this.goStep(2);
    } catch (err) {
      this.setStatus(err.message);
      toast.show(err.message, "err");
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
          <button type="button" class="share-toggle" role="switch"
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
    // Entiers uniquement (pas de virgule / demi-mètre)
    let n = Math.round(Number(v));
    if (!Number.isFinite(n) || n < 1) n = 6;
    n = Math.min(40, Math.max(1, n));
    if ($("#m_lin_slider")) $("#m_lin_slider").value = String(n);
    if ($("#m_lin")) $("#m_lin").value = String(n);
    if ($("#m-lin-val")) $("#m-lin-val").textContent = String(n);
  }

  setMix(pct) {
    const p = Math.min(100, Math.max(0, Number(pct) || 0));
    if ($("#mix_slider")) $("#mix_slider").value = String(p);
    if ($("#mix_fb")) $("#mix_fb").value = String(p);
    if ($("#mix-val")) $("#mix-val").textContent = String(Math.round(p));
    if ($("#mix-nf-val")) $("#mix-nf-val").textContent = String(100 - Math.round(p));
    const bar = $("#mix-bar-fb");
    if (bar) bar.style.width = `${Math.round(p)}%`;
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

  collectBody(optimize = true) {
    const hotel_params = this.collectHotelParams();
    const shares = this.collectShares();
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
      m_lin: Math.round(Number($("#m_lin")?.value)) || 6,
      mix_fb: (Number($("#mix_fb")?.value) || 70) / 100,
      client_needs: this.collectNeeds(),
      category_shares: shares,
      shares_fb: shares.fb,
      shares_nfb: shares.nfb,
      optimize_repartition: !!optimize,
    };
  }

  async runSim(optimize = true) {
    const body = this.collectBody(optimize);
    if (!body.hotel_code) {
      toast.show("Choisissez d'abord un hôtel", "err");
      this.goStep(1);
      return;
    }
    this.goStep(4);
    $("#dir-loading")?.classList.remove("hidden");
    $("#dir-results")?.classList.add("hidden");
    this.setStatus(
      optimize ? "Optimisation de la répartition…" : "Calcul avec votre répartition…"
    );
    try {
      const data = await api.post("/api/rod/simulate", body);
      if (!data.ok) throw new Error(data.error || "La simulation n'a pas abouti");
      this.result = data;
      // Appliquer la répartition retenue (optimisée ou normalisée) dans l'UI
      if (data.category_shares) this.applyCategoryShares(data.category_shares);
      if (data.hotel?.mix_fb != null) {
        let m = Number(data.hotel.mix_fb);
        if (m <= 1) m *= 100;
        this.setMix(Math.round(m));
      }
      this.renderResults(data);
      $("#dir-loading")?.classList.add("hidden");
      $("#dir-results")?.classList.remove("hidden");
      this.setStatus(
        `${data.hotel?.hotel_code || body.hotel_code} · ${data.recommended_solution || "—"}`
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
    const caDisplay = ca == null ? emptyCa || "—" : euro(ca);
    const marge = block?.marge_nette_mensuelle;
    return `
      <div class="big-metric primary">
        <span class="bm-icon" aria-hidden="true">◆</span>
        <span class="bm-label">${caLabel}</span>
        <span class="bm-value">${caDisplay}</span>
        <span class="bm-sub">par mois</span>
      </div>
      <div class="big-metric">
        <span class="bm-icon" aria-hidden="true">◇</span>
        <span class="bm-label">Coûts / mois</span>
        <span class="bm-value">${euro(block?.cout_mensuel)}</span>
        <span class="bm-sub">capex ${euro(block?.capex)}</span>
      </div>
      <div class="big-metric">
        <span class="bm-icon" aria-hidden="true">▣</span>
        <span class="bm-label">Marge nette / mois</span>
        <span class="bm-value ${
          marge == null ? "" : Number(marge) >= 0 ? "pos" : "neg"
        }">${marge == null ? "—" : euro(marge)}</span>
        <span class="bm-sub">${
          block?.marge_nette_annuelle == null
            ? "—"
            : euro(block.marge_nette_annuelle) + " / an"
        }</span>
      </div>
      <div class="big-metric">
        <span class="bm-icon" aria-hidden="true">○</span>
        <span class="bm-label">Marge produit / mois</span>
        <span class="bm-value">${euro(block?.marge_produit_mensuelle)}</span>
        <span class="bm-sub">avant coûts corner</span>
      </div>`;
  }

  _cardsHtml(bySolution, reco) {
    return ["SIMPLY", "LIBERTY", "CONNECTED"]
      .map((c) => {
        const b = (bySolution || {})[c] || {};
        const isReco = c === reco;
        const marge = b.marge_nette_mensuelle;
        return `
          <article class="concept-card ${isReco ? "recommended" : ""}">
            <header>
              <h3>${c}</h3>
              ${
                isReco
                  ? `<span class="badge-reco">Recommandée</span>`
                  : ""
              }
            </header>
            <div class="cc-row"><span>CA / mois</span><strong>${
              b.ca_mensuel == null ? "—" : euro(b.ca_mensuel)
            }</strong></div>
            <div class="cc-row"><span>Coût / mois</span><strong>${euro(
              b.cout_mensuel
            )}</strong></div>
            <div class="cc-row"><span>Marge nette / mois</span><strong class="${
              marge == null ? "" : Number(marge) >= 0 ? "pos" : "neg"
            }">${marge == null ? "—" : euro(marge)}</strong></div>
            <div class="cc-row"><span>Capex</span><strong>${euro(
              b.capex
            )}</strong></div>
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
        }) pour maximiser le CA. Parts relatives à chaque canal (somme 100 %).`;
      } else {
        note.textContent =
          "Répartition saisie normalisée (somme forcée à 100 % par canal F&B et Non F&B).";
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

    const sim = data.simulator || {};
    const ai = data.ai || {};
    const simBy = sim.by_solution || {};
    const aiBy = ai.by_solution || {};

    const simBlock = simBy[reco] || {};
    const aiBlock = aiBy[reco] || {};

    const hostSim = $("#dir-metrics-sim");
    if (hostSim) {
      hostSim.innerHTML = this._metricsHtml(simBlock, {
        caLabel: "CA estimé / mois",
      });
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
