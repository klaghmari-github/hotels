/**
 * Point d'entrée user — simulateur ROD directeur.
 *
 * Compose stepper, autocomplete, hotel-context, rule1, geocode,
 * simulation. HTML : templates/user/index.html
 * API : docs/API_USER.md  |  Front : docs/FRONT.md
 * Debug : window.RODUser
 */

import { $, $$, escapeHtml, fieldStr } from "../../../shared/js/dom.js";
import { api } from "../../../shared/js/api.js";
import { toast } from "../../../shared/js/toast.js";
import { ServiceToggles } from "./services-catalog.js";
import { Stepper } from "./stepper.js";
import { HotelAutocomplete } from "./autocomplete.js";
import { BrandSelect, HotelContextLoader } from "./hotel-context.js";
import { Rule1Panel } from "./rule1-panel.js";
import { SimulationPanel } from "./simulation-panel.js";
import { GeocodePanel } from "./geocode-panel.js";

export class UserApp {
  constructor() {
    this.state = {
      meta: null,
      hotels: [],
      brands: [],
      ready: false,
      lastHotelSource: "",
    };

    this.rule1 = new Rule1Panel();
    this.services = new ServiceToggles(() => this.state.lastHotelSource);
    this.brands = new BrandSelect(this.state);
    this.geocode = new GeocodePanel();

    this.hotel = new HotelContextLoader({
      state: this.state,
      brands: this.brands,
      services: this.services,
      onDerived: () => this.rule1.updateDerived(),
      onRule1: (data) => this.rule1.render(data),
    });

    this.simulation = new SimulationPanel(() =>
      this.hotel.collectPayload(this.state.meta)
    );

    this.stepper = new Stepper({
      maxStep: 5,
      onEnter: (step) => {
        if (step === 5) {
          const cards = $("#sim-cards");
          if (cards && !cards.children.length) this.simulation.run();
        }
      },
    });

    this.autocomplete = new HotelAutocomplete(async (h) => {
      this.autocomplete.hideAll();
      if (!h || !h.hotel_code) return;
      const codeEl = $("#hotel_code");
      const nameEl = $("#hotel_name");
      if (codeEl) codeEl.value = h.hotel_code;
      if (nameEl && h.hotel_name) nameEl.value = h.hotel_name;
      await this.loadHotelByCode(h.hotel_code, h.hotel_name);
    });
  }

  /**
   * Charge le contexte hotel (base locale, ou scrape Accor si nouveau code).
   */
  async loadHotelByCode(code, nameHint) {
    const hint = $("#hotel-lookup-hint");
    if (hint) {
      hint.textContent =
        "Chargement du profil " + code + " (base locale ou Accor)…";
    }
    try {
      const ctx = await this.hotel.loadContext(code);
      if (ctx) this.hotel.applyContext(ctx);
      const scraped = !!(ctx && (ctx.scraped || (ctx.sources && ctx.sources.scrape)));
      if (hint) {
        if (scraped) {
          hint.textContent =
            "Hotel " +
            (ctx.identity?.hotel_code || code) +
            " recupere depuis all.accor.com et ajoute a la base. Verifiez les services.";
          toast.show("Hotel recupere depuis Accor");
        } else {
          hint.textContent =
            "Hotel charge depuis hotel_data : " +
            (ctx.identity?.hotel_code || code) +
            (nameHint || ctx.identity?.hotel_name
              ? " — " + (nameHint || ctx.identity.hotel_name)
              : "") +
            ". Verifiez les services a l etape 2.";
        }
      }
    } catch (e) {
      if (hint) {
        hint.textContent =
          "Hotel introuvable en base et sur Accor : " + (e.message || e);
      }
      toast.show(e.message || "Hotel introuvable", "err");
    }
  }

  async loadBrands() {
    try {
      const brandsRes = await api.get("/api/brands");
      let list = brandsRes.brands || brandsRes || [];
      if (!Array.isArray(list)) list = [];
      this.state.brands = list;
      this.brands.fill(list);
      if (!list.length) toast.show("Aucune marque disponible");
    } catch (e) {
      console.error("[ROD] brands", e);
      this.brands.fill([]);
      toast.show("Impossible de charger les marques");
    }
  }

  async loadHotels() {
    try {
      const hotelsRes = await api.get("/api/hotels");
      this.state.hotels = hotelsRes.hotels || [];
    } catch (e) {
      console.error("[ROD] hotels", e);
      this.state.hotels = [];
    }
  }

  async loadMeta() {
    try {
      const meta = await api.get("/api/meta");
      this.state.meta = meta;
      const renderNeeds = (containerId, items, defaults) => {
        const root = $("#" + containerId);
        if (!root) return;
        root.innerHTML = items
          .map((it) => {
            const on = defaults[it.id] === true || defaults[it.id] === 1;
            return (
              '<label class="toggle-item"><span>' +
              escapeHtml(it.label) +
              '</span><span class="switch"><input type="checkbox" id="' +
              it.id +
              '" ' +
              (on ? "checked" : "") +
              " /><span></span></span></label>"
            );
          })
          .join("");
      };
      // Defauts alignees DEFAULT_CLIENT_NEEDS backend (Règle 3 ROD)
      const defaults = meta.client_needs_defaults || {};
      const fbDefs = {};
      (meta.client_needs_fb || []).forEach((n) => {
        if (typeof n.default === "boolean") fbDefs[n.id] = n.default;
        else if (n.id in defaults) fbDefs[n.id] = !!defaults[n.id];
        else fbDefs[n.id] = true;
      });
      renderNeeds(
        "needs-fb",
        (meta.client_needs_fb || []).map((n) => ({ id: n.id, label: n.label })),
        fbDefs
      );
      const nfbDefs = {};
      (meta.client_needs_nfb || []).forEach((n) => {
        if (typeof n.default === "boolean") nfbDefs[n.id] = n.default;
        else if (n.id in defaults) nfbDefs[n.id] = !!defaults[n.id];
        else nfbDefs[n.id] = n.id !== "nfb_hygiene";
      });
      renderNeeds(
        "needs-nfb",
        (meta.client_needs_nfb || []).map((n) => ({ id: n.id, label: n.label })),
        nfbDefs
      );
    } catch (e) {
      console.error("[ROD] meta", e);
    }
  }

  wireEvents() {
    this.autocomplete.wire();
    this.stepper.wire();

    const hotelCodeInput = $("#hotel_code");
    if (hotelCodeInput) {
      let codeTimer = null;
      const tryLoadByCode = () => {
        const code = (hotelCodeInput.value || "").trim();
        if (!code || code.length < 3) return;
        clearTimeout(codeTimer);
        codeTimer = setTimeout(() => {
          this.loadHotelByCode(code);
        }, 450);
      };
      hotelCodeInput.addEventListener("change", tryLoadByCode);
    }

    const brandSel = $("#hotel_brand");
    if (brandSel) {
      brandSel.addEventListener("change", () => {
        // Si un code hôtel est déjà saisi, ne pas écraser chambres/TO
        // par les moyennes marque (info seule).
        const hasHotel = !!(fieldStr("hotel_code") || "").trim();
        this.hotel.loadBrandPilotAverages(brandSel.value, {
          fillForm: !hasHotel,
        });
      });
    }

    ["nb_chambres", "taux_occupation", "guests_per_chambre"].forEach((id) => {
      const el = $("#" + id);
      if (el) {
        el.addEventListener("input", () => this.rule1.updateDerived());
        el.addEventListener("change", () => this.rule1.updateDerived());
      }
    });

    const btnGeo = $("#btn-geocode");
    if (btnGeo) {
      btnGeo.addEventListener("click", (ev) => {
        ev.preventDefault();
        this.geocode.run();
      });
    }

    $("#btn-next")?.addEventListener("click", () => {
      if (this.stepper.step === this.stepper.maxStep) this.simulation.run();
      else this.stepper.setStep(this.stepper.step + 1);
    });
    $("#btn-simulate")?.addEventListener("click", () => this.simulation.run());
  }

  async init() {
    if (this.state.ready) return;
    this.state.ready = true;
    console.info("[ROD] init user UI (modules)");

    this.services.renderAll({});
    this.rule1.updateDerived();
    this.stepper.setStep(1);

    // Meta (besoins R3) + marques avant les handlers : le préremplissage
    // hôtel doit trouver les checkboxes déjà rendues.
    await this.loadBrands();
    await this.loadHotels();
    this.brands.fill(this.state.brands);
    await this.loadMeta();
    this.hotel.reapplyPendingNeeds();

    this.wireEvents();
  }
}

const app = new UserApp();
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => app.init());
} else {
  app.init();
}

window.RODUser = app;
