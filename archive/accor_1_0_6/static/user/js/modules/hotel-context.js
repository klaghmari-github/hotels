/**
 * Charge le contexte hôtel (GET /api/hotels/<code>/context) et les
 * moyennes marque (concept_pilote). Préremplit les champs exploitation
 * du wizard ; gère le flag scraped après fetch Accor.
 */

import {
  $,
  fieldChecked,
  fieldNum,
  fieldStr,
  setField,
  setText,
  escapeHtml,
} from "../../../shared/js/dom.js";
import { api } from "../../../shared/js/api.js";
import { toast } from "../../../shared/js/toast.js";
import { Format } from "../../../shared/js/format.js";
import { allServiceDefs } from "./services-catalog.js";

export class BrandSelect {
  /**
   * @param {object} state app state { brands, hotels }
   */
  constructor(state) {
    this.state = state;
  }

  brandName(b) {
    if (b == null) return "";
    if (typeof b === "string") return b.trim();
    return String(b.brand || b.Marque || b.marque || b.hotel_brand || "").trim();
  }

  setValue(name) {
    const sel = $("#hotel_brand");
    if (!sel) return;
    if (name == null || name === "") {
      sel.value = "";
      return;
    }
    const target = String(name).trim();
    const options = Array.from(sel.options);
    let match = options.find((o) => o.value === target);
    if (!match) {
      match = options.find(
        (o) => o.value.toUpperCase() === target.toUpperCase()
      );
    }
    if (!match && target) {
      match = document.createElement("option");
      match.value = target;
      match.textContent = target;
      sel.appendChild(match);
    }
    if (match) sel.value = match.value;
  }

  fill(brands) {
    const sel = $("#hotel_brand");
    if (!sel) return;
    const names = [];
    const seen = {};
    const add = (n) => {
      n = String(n || "").trim();
      if (!n) return;
      const key = n.toUpperCase();
      if (seen[key]) return;
      seen[key] = true;
      names.push(n);
    };
    (brands || []).forEach((b) => add(this.brandName(b)));
    (this.state.hotels || []).forEach((h) => add(h && h.hotel_brand));
    names.sort((a, b) => a.localeCompare(b, "fr", { sensitivity: "base" }));

    const current = sel.value;
    let html = '<option value="">— Choisir une marque —</option>';
    names.forEach((n) => {
      html += `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`;
    });
    sel.innerHTML = html;
    if (current) this.setValue(current);
  }
}

export class HotelContextLoader {
  /**
   * @param {object} deps
   * @param {object} deps.state
   * @param {BrandSelect} deps.brands
   * @param {import('./services-catalog.js').ServiceToggles} deps.services
   * @param {() => void} deps.onDerived
   * @param {(data: object|null) => void} deps.onRule1
   */
  constructor({ state, brands, services, onDerived, onRule1 }) {
    this.state = state;
    this.brands = brands;
    this.services = services;
    this.onDerived = onDerived;
    this.onRule1 = onRule1;
  }

  async loadContext(code) {
    const data = await api.get(
      `/api/hotels/${encodeURIComponent(code)}/context`
    );
    if (data.ok === false) throw new Error(data.error || "Contexte indisponible");
    return data;
  }

  applyContext(ctx) {
    if (!ctx) return;
    this._lastContext = ctx;
    const id = ctx.identity || {};
    const op = ctx.operating || {};
    const corner = ctx.corner || {};
    const services = ctx.services || {};
    const profile = ctx.client_profile || {};
    const needs = profile.client_needs || {};
    this._pendingNeeds = needs;

    setField("hotel_code", id.hotel_code);
    setField("hotel_name", id.hotel_name);
    setField("hotel_adresse_postale_1", id.hotel_adresse_postale_1);
    setField("hotel_adresse_postale_2", id.hotel_adresse_postale_2);
    setField("hotel_code_postal", id.hotel_code_postal);
    setField("hotel_city", id.hotel_city);
    setField("hotel_lat", id.hotel_lat);
    setField("hotel_lon", id.hotel_lon);
    if (id.hotel_brand) this.brands.setValue(id.hotel_brand);

    // Priorité aux valeurs hôtel (base admin), pas aux moyennes marque
    if (op.nb_chambres != null && Number(op.nb_chambres) > 0) {
      setField("nb_chambres", Math.round(Number(op.nb_chambres)));
    }
    if (op.taux_occupation != null && op.taux_occupation !== "") {
      let to = Number(op.taux_occupation);
      if (Number.isFinite(to)) {
        if (to <= 1) to *= 100;
        setField("taux_occupation", Math.round(to * 10) / 10);
      }
    }
    if (op.guests_per_chambre != null && Number(op.guests_per_chambre) > 0) {
      setField(
        "guests_per_chambre",
        Number(op.guests_per_chambre).toFixed(2)
      );
    }

    this.state.lastHotelSource =
      (id.hotel_code || "") + (id.hotel_name ? " — " + id.hotel_name : "");
    this.services.renderAll(services);

    const hasCorner = $("#has_corner");
    if (hasCorner) hasCorner.checked = !!corner.has_corner;
    if (corner.m_lin != null && corner.m_lin !== "") {
      setField("m_lin", corner.m_lin);
    } else {
      // laisser vide → défaut pilote concept côté moteur
      setField("m_lin", "");
    }
    if (corner.mix_fb != null) {
      let m = Number(corner.mix_fb);
      if (Number.isFinite(m)) {
        if (m <= 1) m *= 100;
        setField("mix_fb", Math.round(m));
      }
    } else {
      setField("mix_fb", "");
    }

    const pctField = (fieldId, v) => {
      if (v == null) return;
      let p = Number(v);
      if (!Number.isFinite(p)) return;
      if (p <= 1) p *= 100;
      setField(fieldId, Math.round(p));
    };
    pctField("loisirs_pct", profile.loisirs_pct);
    pctField("affaires_pct", profile.affaires_pct);
    pctField("national_pct", profile.national_pct);
    pctField("international_pct", profile.international_pct);

    this.applyClientNeeds(needs);

    this.onDerived();
    // Boîte « moyennes marque » en info seule — ne pas écraser chambres/TO hôtel
    if (id.hotel_brand) {
      this.loadBrandPilotAverages(id.hotel_brand, { fillForm: false });
    }
    toast.show("Profil " + (id.hotel_code || "") + " chargé");
  }

  /** Coche les besoins Règle 3 (ids fb_* / nfb_*). */
  applyClientNeeds(needs) {
    if (!needs || typeof needs !== "object") return;
    Object.keys(needs).forEach((nid) => {
      const el = $("#" + nid);
      if (el) el.checked = !!needs[nid];
    });
  }

  /** Réapplique les needs d’un contexte déjà chargé (après render meta). */
  reapplyPendingNeeds() {
    if (this._pendingNeeds) this.applyClientNeeds(this._pendingNeeds);
  }

  /**
   * Affiche les moyennes marque (concept_pilote).
   * @param {object} data
   * @param {{ fillForm?: boolean }} [opts]
   *   fillForm=true  : écrit aussi chambres / TO / guests (choix marque seule)
   *   fillForm=false : boîte info seulement — ne pas écraser un hôtel déjà chargé
   */
  applyBrandPilotAverages(data, { fillForm = true } = {}) {
    const box = $("#brand-pilot-box");
    if (!box) return;
    if (!data || !data.ok || !data.averages) {
      box.classList.add("hidden");
      return;
    }
    const a = data.averages;
    box.classList.remove("hidden");
    setText("brand-pilot-name", data.brand || "");
    const meta = $("#brand-pilot-meta");
    if (meta) {
      const src =
        data.strategy === "neighbors" && data.source_brands
          ? " · voisins : " + (data.source_brands || []).join(" + ")
          : "";
      meta.textContent =
        (data.n_hotels || 0) +
        " hôtel(s) · " +
        (data.n_rows || 0) +
        " ligne(s) · années " +
        ((data.years_used || []).join(", ") || "—") +
        " · année " +
        (data.excluded_year || "—") +
        " exclue" +
        src;
    }
    const hint = $("#brand-pilot-hint");
    if (hint) {
      hint.textContent = fillForm
        ? data.note ||
          "Valeurs préremplies dans les champs d’exploitation — vous pouvez les ajuster."
        : "Référence marque (info) — les champs d’exploitation viennent de l’hôtel sélectionné.";
    }

    setText(
      "bp-chambres",
      a.nb_chambres != null ? Math.round(a.nb_chambres) : "—"
    );
    setText(
      "bp-to",
      a.taux_occupation != null ? Format.pct(a.taux_occupation) : "—"
    );
    setText(
      "bp-guests",
      a.guests_per_chambre != null
        ? Number(a.guests_per_chambre).toFixed(2)
        : "—"
    );
    setText(
      "bp-clients-j",
      a.clients_jour != null
        ? Format.locale(a.clients_jour, { maximumFractionDigits: 1 })
        : "—"
    );
    setText(
      "bp-clients-m",
      a.clients_mois != null
        ? Format.locale(a.clients_mois, { maximumFractionDigits: 1 })
        : "—"
    );
    setText(
      "bp-ca",
      a.ca_mensuel_moyen != null ? Format.euro(a.ca_mensuel_moyen) : "—"
    );

    if (fillForm) {
      if (a.nb_chambres != null) setField("nb_chambres", Math.round(a.nb_chambres));
      if (a.taux_occupation != null) {
        let toPct = Number(a.taux_occupation);
        if (toPct <= 1) toPct *= 100;
        setField("taux_occupation", Math.round(toPct * 10) / 10);
      }
      if (a.guests_per_chambre != null) {
        setField("guests_per_chambre", Number(a.guests_per_chambre).toFixed(2));
      }
      this.onDerived();
      if (data.rule1 && data.rule1.ok) this.onRule1(data.rule1);
    }
  }

  /**
   * @param {string} brand
   * @param {{ fillForm?: boolean }} [opts]
   */
  async loadBrandPilotAverages(brand, { fillForm = true } = {}) {
    brand = String(brand || "").trim();
    const box = $("#brand-pilot-box");
    if (!brand) {
      if (box) box.classList.add("hidden");
      return null;
    }
    try {
      const data = await api.get(
        `/api/concept_pilote/brand/${encodeURIComponent(brand)}`
      );
      if (!data.ok) {
        if (box) box.classList.add("hidden");
        return null;
      }
      this.applyBrandPilotAverages(data, { fillForm });
      return data;
    } catch (e) {
      console.error("[ROD] brand pilot", e);
      if (box) box.classList.add("hidden");
      return null;
    }
  }

  collectPayload(meta) {
    const services = {};
    allServiceDefs().forEach((s) => {
      services[s.id] = fieldChecked(s.id);
    });
    // Besoins clients : toujours tous les ids ROD (R3), valeur = checkbox ou defaut meta
    const client_needs = Object.assign({}, meta?.client_needs_defaults || {});
    (meta?.client_needs_fb || []).forEach((n) => {
      const el = $("#" + n.id);
      if (el) client_needs[n.id] = !!el.checked;
      else if (typeof n.default === "boolean") client_needs[n.id] = n.default;
    });
    (meta?.client_needs_nfb || []).forEach((n) => {
      const el = $("#" + n.id);
      if (el) client_needs[n.id] = !!el.checked;
      else if (typeof n.default === "boolean") client_needs[n.id] = n.default;
    });
    const to = Format.toRate(fieldNum("taux_occupation", 65));
    const mLinRaw = $("#m_lin") ? $("#m_lin").value : "";
    const mixFbRaw = $("#mix_fb") ? $("#mix_fb").value : "";
    // mix UI en % (70) → fraction ; si deja fraction <=1 on garde
    let mixFb = null;
    if (mixFbRaw !== "") {
      let m = fieldNum("mix_fb");
      if (m > 1) m = m / 100;
      mixFb = Math.min(Math.max(m, 0), 1);
    }

    return {
      identity: {
        hotel_code: fieldStr("hotel_code"),
        hotel_name: fieldStr("hotel_name"),
        hotel_brand: fieldStr("hotel_brand"),
        hotel_lat:
          $("#hotel_lat") && $("#hotel_lat").value === ""
            ? null
            : fieldNum("hotel_lat"),
        hotel_lon:
          $("#hotel_lon") && $("#hotel_lon").value === ""
            ? null
            : fieldNum("hotel_lon"),
        hotel_adresse_postale_1: fieldStr("hotel_adresse_postale_1"),
        hotel_adresse_postale_2: fieldStr("hotel_adresse_postale_2"),
        hotel_code_postal: fieldStr("hotel_code_postal"),
        hotel_city: fieldStr("hotel_city"),
      },
      operating: {
        nb_chambres: fieldNum("nb_chambres", 80),
        taux_occupation: to,
        guests_per_chambre: fieldNum("guests_per_chambre", 1.7),
      },
      services,
      client_profile: {
        loisirs_pct: fieldNum("loisirs_pct", 30) / 100,
        affaires_pct: fieldNum("affaires_pct", 70) / 100,
        national_pct: fieldNum("national_pct", 60) / 100,
        international_pct: fieldNum("international_pct", 40) / 100,
        client_needs,
      },
      corner: {
        has_corner: fieldChecked("has_corner"),
        m_lin: mLinRaw === "" ? null : fieldNum("m_lin"),
        mix_fb: mixFb,
      },
      light_enrich: true,
    };
  }
}
