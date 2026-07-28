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
    this._toggles = {
      has_pool: false,
      has_vitrine: false,
    };
  }

  async init() {
    try {
      this.meta = await api.get("/api/rod/meta");
      this.renderNeeds(this.meta);
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
    $("#btn-run-sim")?.addEventListener("click", () => this.runSim());

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

    // Toggles booléens (piscine / vitrine)
    $$("[data-toggle]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.toggle;
        this.setToggle(key, !this._toggles[key]);
      });
    });

    // Onglets résultats
    $$("[data-result-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        this.setResultTab(btn.dataset.resultTab);
      });
    });
  }

  setToggle(key, on) {
    this._toggles[key] = !!on;
    const btn = document.querySelector(`[data-toggle="${key}"]`);
    if (!btn) return;
    btn.classList.toggle("is-on", !!on);
    btn.setAttribute("aria-checked", on ? "true" : "false");
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
          <span>Récupérer depuis Accor (session uniquement)</span>
          <em>non enregistré en base</em>
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
        nb_chambres: op.nb_chambres ?? ind.nb_chambres ?? id.hotel_nb_chambres,
        taux_occupation:
          op.taux_occupation ?? ind.taux_occupation ?? id.hotel_to_annuel,
        guests_per_chambre:
          op.guests_per_chambre ?? ind.guests_per_chambre ?? 1.7,
        derniere_reno: op.derniere_reno ?? ind.derniere_reno ?? null,
        nb_restaurants:
          op.nb_restaurants ??
          ind.nb_restaurants ??
          services.nb_restaurants ??
          (services.restaurant ? 1 : 0),
        nb_bars:
          op.nb_bars ?? ind.nb_bars ?? services.nb_bars ?? (services.bar ? 1 : 0),
        has_pool: !!(op.has_pool ?? ind.has_pool ?? services.pool),
        has_vitrine: !!(
          op.has_vitrine ??
          ind.has_vitrine ??
          services.lobby_fridge ??
          services.has_vitrine
        ),
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
      if (ctx.session_only) {
        this.setStatus("Fiche session (non enregistrée en base)");
        toast.show("Hôtel chargé pour cette session uniquement", "ok");
      } else {
        this.setStatus("");
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
    if (this.hotel.nb_chambres != null)
      $("#nb_chambres").value = String(Math.round(Number(this.hotel.nb_chambres)));
    if (this.hotel.taux_occupation != null) {
      let to = Number(this.hotel.taux_occupation);
      if (to <= 1) to *= 100;
      $("#taux_occupation").value = String(Math.round(to * 10) / 10);
    }
    if (this.hotel.guests_per_chambre != null)
      $("#guests_per_chambre").value = String(
        Number(this.hotel.guests_per_chambre).toFixed(1)
      );

    if (this.hotel.derniere_reno != null && this.hotel.derniere_reno !== "")
      $("#derniere_reno").value = String(Math.round(Number(this.hotel.derniere_reno)));
    else if ($("#derniere_reno")) $("#derniere_reno").value = "";

    if (this.hotel.nb_restaurants != null)
      $("#nb_restaurants").value = String(
        Math.max(0, Math.round(Number(this.hotel.nb_restaurants)))
      );
    else if ($("#nb_restaurants")) $("#nb_restaurants").value = "0";

    if (this.hotel.nb_bars != null)
      $("#nb_bars").value = String(Math.max(0, Math.round(Number(this.hotel.nb_bars))));
    else if ($("#nb_bars")) $("#nb_bars").value = "0";

    this.setToggle("has_pool", !!this.hotel.has_pool);
    this.setToggle("has_vitrine", !!this.hotel.has_vitrine);
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
    const fill = (hostId, items) => {
      const host = $("#" + hostId);
      if (!host) return;
      host.innerHTML = (items || [])
        .map((it) => {
          const on = it.default !== false;
          return `
        <button
          type="button"
          class="need-toggle ${on ? "is-on" : ""}"
          role="switch"
          aria-checked="${on ? "true" : "false"}"
          data-need="${escapeHtml(it.id)}"
        >
          <span class="need-toggle-lab">${escapeHtml(it.label || it.id)}</span>
          <span class="toggle-track" aria-hidden="true"><span class="toggle-thumb"></span></span>
        </button>`;
        })
        .join("");
      host.querySelectorAll(".need-toggle").forEach((btn) => {
        btn.addEventListener("click", () => {
          const on = !btn.classList.contains("is-on");
          btn.classList.toggle("is-on", on);
          btn.setAttribute("aria-checked", on ? "true" : "false");
        });
      });
    };
    fill("needs-fb", meta.client_needs_fb);
    fill("needs-nfb", meta.client_needs_nfb);
  }

  applyNeeds(map) {
    $$(".need-toggle[data-need]").forEach((btn) => {
      const id = btn.dataset.need;
      if (!(id in map)) return;
      const on = !!map[id];
      btn.classList.toggle("is-on", on);
      btn.setAttribute("aria-checked", on ? "true" : "false");
    });
  }

  setAllNeeds(on) {
    $$(".need-toggle[data-need]").forEach((btn) => {
      btn.classList.toggle("is-on", !!on);
      btn.setAttribute("aria-checked", on ? "true" : "false");
    });
  }

  setMLin(v) {
    const n = Number(v) || 6;
    if ($("#m_lin_slider")) $("#m_lin_slider").value = String(n);
    if ($("#m_lin")) $("#m_lin").value = String(n);
    if ($("#m-lin-val")) $("#m-lin-val").textContent = fmt(n, 1);
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
    $$(".need-toggle[data-need]").forEach((btn) => {
      needs[btn.dataset.need] = btn.classList.contains("is-on");
    });
    return needs;
  }

  collectBody() {
    const toRaw = $("#taux_occupation")?.value;
    let to = toRaw === "" || toRaw == null ? null : Number(toRaw);
    if (to != null && to > 1) to = to / 100;
    const renoRaw = $("#derniere_reno")?.value;
    const derniere_reno =
      renoRaw === "" || renoRaw == null ? null : Number(renoRaw);
    return {
      hotel_code: ($("#hotel_code")?.value || this.hotel?.hotel_code || "").trim(),
      hotel_name: this.hotel?.hotel_name || "",
      hotel_brand: this.hotel?.hotel_brand || "",
      nb_chambres: Number($("#nb_chambres")?.value) || null,
      taux_occupation: to,
      guests_per_chambre: Number($("#guests_per_chambre")?.value) || null,
      derniere_reno:
        derniere_reno != null && !Number.isNaN(derniere_reno)
          ? Math.round(derniere_reno)
          : null,
      nb_restaurants: Math.max(0, Number($("#nb_restaurants")?.value) || 0),
      nb_bars: Math.max(0, Number($("#nb_bars")?.value) || 0),
      has_pool: !!this._toggles.has_pool,
      has_vitrine: !!this._toggles.has_vitrine,
      m_lin: Number($("#m_lin")?.value) || 6,
      mix_fb: (Number($("#mix_fb")?.value) || 70) / 100,
      client_needs: this.collectNeeds(),
    };
  }

  async runSim() {
    const body = this.collectBody();
    if (!body.hotel_code) {
      toast.show("Choisissez d'abord un hôtel", "err");
      this.goStep(1);
      return;
    }
    this.goStep(4);
    $("#dir-loading")?.classList.remove("hidden");
    $("#dir-results")?.classList.add("hidden");
    this.setStatus("Calcul en cours…");
    try {
      const data = await api.post("/api/rod/simulate", body);
      if (!data.ok) throw new Error(data.error || "La simulation n'a pas abouti");
      this.result = data;
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
    if ($("#dir-disclaimer"))
      $("#dir-disclaimer").textContent = data.disclaimer || "";

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
