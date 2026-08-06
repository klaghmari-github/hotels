/**
 * Point d'entree User — ROD Simulateur directeur.
 *
 * Modules :
 *   shared/               dom, api, toast, format
 *   user/js/modules/      stepper, autocomplete, hotel, rule1, sim, geocode
 *
 * HTML : templates/user/index.html
 * API  : /api/hotels/*, /api/simulate, /api/geocode, /api/rule1, …
 * Doc  : README.md (Architecture front + Interface user)
 *
 * Debug console : window.RODUser
 */

import { $, $$, escapeHtml } from "../../../shared/js/dom.js";
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
      const hint = $("#hotel-lookup-hint");
      if (hint) hint.textContent = "Chargement du profil " + h.hotel_code + "…";
      try {
        const ctx = await this.hotel.loadContext(h.hotel_code);
        if (ctx) this.hotel.applyContext(ctx);
        if (hint) {
          hint.textContent =
            "Hotel charge depuis hotel_data : " +
            (h.hotel_code || "") +
            (h.hotel_name ? " — " + h.hotel_name : "") +
            ". Verifiez les services a l etape 2.";
        }
      } catch (e) {
        if (hint) {
          hint.textContent =
            "Hotel propose mais contexte incomplet : " + (e.message || e);
        }
      }
    });
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
      const fbDefs = {};
      (meta.client_needs_fb || []).forEach((n) => {
        fbDefs[n.id] = true;
      });
      renderNeeds(
        "needs-fb",
        (meta.client_needs_fb || []).map((n) => ({ id: n.id, label: n.label })),
        fbDefs
      );
      const nfbDefs = {};
      (meta.client_needs_nfb || []).forEach((n) => {
        nfbDefs[n.id] = n.id !== "nfb_hygiene";
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
        codeTimer = setTimeout(async () => {
          try {
            const ctx = await this.hotel.loadContext(code);
            if (ctx) this.hotel.applyContext(ctx);
          } catch {
            /* saisie libre */
          }
        }, 450);
      };
      hotelCodeInput.addEventListener("change", tryLoadByCode);
    }

    const brandSel = $("#hotel_brand");
    if (brandSel) {
      brandSel.addEventListener("change", () => {
        this.hotel.loadBrandPilotAverages(brandSel.value);
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
    this.wireEvents();
    this.rule1.updateDerived();
    this.stepper.setStep(1);

    await this.loadBrands();
    await this.loadHotels();
    this.brands.fill(this.state.brands);
    await this.loadMeta();
  }
}

const app = new UserApp();
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => app.init());
} else {
  app.init();
}

window.RODUser = app;
