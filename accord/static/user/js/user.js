/**
 * ROD User Simulator — wizard interactif (5 étapes).
 */
(function () {
  "use strict";

  const state = {
    step: 1,
    maxStep: 5,
    meta: null,
    hotels: [],
    brands: [],
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  const SERVICES = {
    fb: [
      { id: "bar", label: "Bar" },
      { id: "restaurant", label: "Restaurant" },
      { id: "room_service", label: "Room service" },
      { id: "minibar", label: "Minibar" },
    ],
    nfb: [
      { id: "meeting_rooms", label: "Salles de réunion" },
      { id: "gym", label: "Salle de sport" },
      { id: "spa", label: "Spa" },
      { id: "pool", label: "Piscine" },
    ],
    lobby: [
      { id: "lobby_fridge", label: "Vitrine / frigo" },
      { id: "lobby_microwave", label: "Micro-ondes" },
      { id: "lobby_water", label: "Fontaine à eau" },
      { id: "lobby_coffee", label: "Machine à café" },
      { id: "lobby_kettle", label: "Bouilloire" },
      { id: "lobby_seating", label: "Assises" },
    ],
  };

  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.add("hidden"), 3200);
  }

  function num(id, fallback = 0) {
    const el = $(id.startsWith("#") ? id : `#${id}`);
    if (!el) return fallback;
    const v = parseFloat(el.value);
    return Number.isFinite(v) ? v : fallback;
  }

  function str(id) {
    const el = $(`#${id}`);
    return el ? String(el.value || "").trim() : "";
  }

  function checked(id) {
    const el = $(`#${id}`);
    return !!(el && el.checked);
  }

  function renderToggles(containerId, items, defaults = {}) {
    const root = $(`#${containerId}`);
    if (!root) return;
    root.innerHTML = items
      .map((it) => {
        const on = defaults[it.id] !== false && defaults[it.id] !== 0;
        return `<label class="toggle-item">
          <span>${it.label}</span>
          <span class="switch"><input type="checkbox" id="${it.id}" ${on ? "checked" : ""} /><span></span></span>
        </label>`;
      })
      .join("");
  }

  function updateDerived() {
    const n = num("nb_chambres", 80);
    let to = num("taux_occupation", 65);
    if (to > 1) to /= 100;
    const g = num("guests_per_chambre", 1.7);
    const jour = n * to * g;
    const mois = jour * 30.5;
    const fmt = (x) =>
      x.toLocaleString("fr-FR", { maximumFractionDigits: 0 });
    $("#out-clients-jour").textContent = fmt(jour);
    $("#out-clients-mois").textContent = fmt(mois);
  }

  function setStep(n) {
    state.step = Math.min(Math.max(n, 1), state.maxStep);
    $$(".panel").forEach((p) => {
      p.classList.toggle("hidden", Number(p.dataset.panel) !== state.step);
    });
    $$(".step").forEach((s) => {
      const i = Number(s.dataset.step);
      s.classList.toggle("active", i === state.step);
      s.classList.toggle("done", i < state.step);
    });
    $("#btn-prev").disabled = state.step === 1;
    $("#btn-next").textContent =
      state.step === state.maxStep ? "Relancer" : "Valider";
    $("#step-label").textContent = `Étape ${state.step} / ${state.maxStep}`;
    if (state.step === 5) {
      // auto-sim on first enter if empty
      if (!$("#sim-cards").children.length) runSimulation();
    }
  }

  function fillBrands(brands) {
    const sel = $("#hotel_brand");
    const names = brands.map((b) => b.brand).filter(Boolean);
    const fallback = ["ibis", "ibis Styles", "ibis budget", "Novotel", "Mercure"];
    const list = names.length ? names : fallback;
    sel.innerHTML =
      `<option value="">—</option>` +
      list.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join("");
  }

  function fillHotels(hotels) {
    state.hotels = hotels;
    const sel = $("#hotel-select");
    sel.innerHTML =
      `<option value="">— Nouveau / saisie libre —</option>` +
      hotels
        .map((h) => {
          const code = h.hotel_code || "";
          const name = h.hotel_name || code;
          return `<option value="${escapeHtml(code)}">${escapeHtml(code)} — ${escapeHtml(name)}</option>`;
        })
        .join("");
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function pctLabel(x) {
    if (x == null || Number.isNaN(Number(x))) return "—";
    let v = Number(x);
    if (v <= 1) v *= 100;
    return `${Math.round(v)} %`;
  }

  function showHist(indicators, sources) {
    const box = $("#hist-box");
    if (!indicators) {
      box.classList.add("hidden");
      return;
    }
    box.classList.remove("hidden");
    const ca = indicators.ca_historique_mensuel;
    const nv = indicators.ventes_historiques_mensuelles;
    $("#hist-ca").textContent =
      ca != null
        ? Number(ca).toLocaleString("fr-FR", {
            style: "currency",
            currency: "EUR",
            maximumFractionDigits: 0,
          })
        : "—";
    $("#hist-ventes").textContent =
      nv != null ? Math.round(Number(nv)).toLocaleString("fr-FR") : "—";
    $("#hist-mix").textContent =
      indicators.mix_fb != null ? pctLabel(indicators.mix_fb) : "—";
    $("#hist-n").textContent = indicators.n_months_model_data || "—";
    if (sources) {
      $("#hist-sources").textContent =
        "Sources : " +
        Object.entries(sources)
          .map(([k, v]) => `${k}=${v}`)
          .join(" · ");
    }
  }

  async function loadHotelContext(code) {
    if (!code) return null;
    const res = await fetch(`/api/hotels/${encodeURIComponent(code)}/context`);
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "Contexte indisponible");
    return data;
  }

  function applyContext(ctx) {
    if (!ctx) return;
    const id = ctx.identity || {};
    const op = ctx.operating || {};
    const corner = ctx.corner || {};
    const services = ctx.services || {};
    const profile = ctx.client_profile || {};
    const needs = profile.client_needs || {};

    const map = {
      hotel_code: id.hotel_code,
      hotel_name: id.hotel_name,
      hotel_brand: id.hotel_brand,
      hotel_adresse_postale_1: id.hotel_adresse_postale_1,
      hotel_adresse_postale_2: id.hotel_adresse_postale_2,
      hotel_code_postal: id.hotel_code_postal,
      hotel_city: id.hotel_city,
      hotel_lat: id.hotel_lat,
      hotel_lon: id.hotel_lon,
    };
    Object.entries(map).forEach(([k, v]) => {
      const el = $(`#${k}`);
      if (el && v != null && v !== "") el.value = v;
    });

    if (op.nb_chambres) $("#nb_chambres").value = op.nb_chambres;
    if (op.taux_occupation != null) {
      let to = Number(op.taux_occupation);
      if (to <= 1) to *= 100;
      $("#taux_occupation").value = Math.round(to * 10) / 10;
    }
    if (op.guests_per_chambre) {
      $("#guests_per_chambre").value = Number(op.guests_per_chambre).toFixed(1);
    }

    Object.entries(services).forEach(([sid, val]) => {
      const el = $(`#${sid}`);
      if (el) el.checked = !!val;
    });

    $("#has_corner").checked = !!corner.has_corner;
    if (corner.m_lin != null && corner.m_lin !== "") {
      $("#m_lin").value = corner.m_lin;
    }
    if (corner.mix_fb != null) {
      let m = Number(corner.mix_fb);
      if (m <= 1) m *= 100;
      $("#mix_fb").value = Math.round(m);
    }

    if (profile.loisirs_pct != null) {
      $("#loisirs_pct").value = Math.round(
        (profile.loisirs_pct <= 1 ? profile.loisirs_pct * 100 : profile.loisirs_pct)
      );
    }
    if (profile.affaires_pct != null) {
      $("#affaires_pct").value = Math.round(
        (profile.affaires_pct <= 1
          ? profile.affaires_pct * 100
          : profile.affaires_pct)
      );
    }
    if (profile.national_pct != null) {
      $("#national_pct").value = Math.round(
        (profile.national_pct <= 1
          ? profile.national_pct * 100
          : profile.national_pct)
      );
    }
    if (profile.international_pct != null) {
      $("#international_pct").value = Math.round(
        (profile.international_pct <= 1
          ? profile.international_pct * 100
          : profile.international_pct)
      );
    }

    Object.entries(needs).forEach(([nid, val]) => {
      const el = $(`#${nid}`);
      if (el) el.checked = !!val;
    });

    showHist(ctx.indicators, ctx.sources);
    updateDerived();
    toast(`Contexte ${id.hotel_code || ""} chargé (hotel_data + model_data)`);
  }

  function applyHotel(h) {
    if (!h) return;
    // fallback synchrone si context API indisponible
    const map = {
      hotel_code: h.hotel_code,
      hotel_name: h.hotel_name,
      hotel_brand: h.hotel_brand,
      hotel_adresse_postale_1: h.hotel_adresse_postale_1,
      hotel_adresse_postale_2: h.hotel_adresse_postale_2,
      hotel_code_postal: h.hotel_code_postal,
      hotel_city: h.hotel_city,
      hotel_lat: h.hotel_lat,
      hotel_lon: h.hotel_lon,
    };
    Object.entries(map).forEach(([k, v]) => {
      const el = $(`#${k}`);
      if (el && v != null && v !== "") el.value = v;
    });
    if (h.hotel_nb_chambres) $("#nb_chambres").value = h.hotel_nb_chambres;
    if (h.hotel_to_annuel != null) {
      let to = Number(h.hotel_to_annuel);
      if (to <= 1) to *= 100;
      $("#taux_occupation").value = Math.round(to * 10) / 10;
    }
    updateDerived();
  }

  function collectPayload() {
    const services = {};
    [...SERVICES.fb, ...SERVICES.nfb, ...SERVICES.lobby].forEach((s) => {
      services[s.id] = checked(s.id);
    });

    const client_needs = {};
    (state.meta?.client_needs_fb || []).forEach((n) => {
      client_needs[n.id] = checked(n.id);
    });
    (state.meta?.client_needs_nfb || []).forEach((n) => {
      client_needs[n.id] = checked(n.id);
    });

    let to = num("taux_occupation", 65);
    if (to > 1) to /= 100;

    const mLinRaw = $("#m_lin").value;
    const mixFbRaw = $("#mix_fb").value;

    return {
      identity: {
        hotel_code: str("hotel_code"),
        hotel_name: str("hotel_name"),
        hotel_brand: str("hotel_brand"),
        hotel_lat: $("#hotel_lat").value === "" ? null : num("hotel_lat"),
        hotel_lon: $("#hotel_lon").value === "" ? null : num("hotel_lon"),
        hotel_adresse_postale_1: str("hotel_adresse_postale_1"),
        hotel_adresse_postale_2: str("hotel_adresse_postale_2"),
        hotel_code_postal: str("hotel_code_postal"),
        hotel_city: str("hotel_city"),
      },
      operating: {
        nb_chambres: num("nb_chambres", 80),
        taux_occupation: to,
        guests_per_chambre: num("guests_per_chambre", 1.7),
      },
      services,
      client_profile: {
        loisirs_pct: num("loisirs_pct", 30) / 100,
        affaires_pct: num("affaires_pct", 70) / 100,
        national_pct: num("national_pct", 60) / 100,
        international_pct: num("international_pct", 40) / 100,
        client_needs,
      },
      corner: {
        has_corner: checked("has_corner"),
        m_lin: mLinRaw === "" ? null : num("m_lin"),
        mix_fb: mixFbRaw === "" ? null : num("mix_fb") / 100,
      },
      light_enrich: true, // fast path by default for UX
    };
  }

  function euro(n) {
    const x = Number(n);
    if (!Number.isFinite(x)) return "—";
    return x.toLocaleString("fr-FR", {
      style: "currency",
      currency: "EUR",
      maximumFractionDigits: 0,
    });
  }

  function renderResults(data) {
    const reco = data.recommended_concept;
    const banner = $("#sim-reco");
    banner.classList.remove("hidden");
    banner.innerHTML = `
      <div class="tag">Recommandation</div>
      <h2>${escapeHtml(reco)}</h2>
      <p>${escapeHtml(data.recommendation_reason || "")}</p>
    `;

    // Détail du calcul (transparence Règle 1)
    const calc = $("#sim-calc");
    const ind = (data.enriched && data.enriched.indicators) || {};
    const sum = data.calc_summary || {};
    const recoRev =
      (data.by_concept &&
        data.by_concept[reco] &&
        data.by_concept[reco].revenue &&
        data.by_concept[reco].revenue.breakdown) ||
      {};
    const items = [
      ["Chambres", ind.nb_chambres ?? recoRev.nb_chambres],
      ["TO", pctLabel(ind.taux_occupation ?? recoRev.taux_occupation)],
      ["Guests/ch", ind.guests_per_chambre ?? recoRev.guests_per_chambre],
      ["Clients / mois", Math.round(ind.clients_mois || recoRev.clients_hotel || 0)],
      ["Clients pilote", Math.round(recoRev.clients_pilote || 0)],
      [
        "Facteur clients",
        recoRev.client_factor != null
          ? Number(recoRev.client_factor).toFixed(3)
          : "—",
      ],
      ["CA pilote concept", euro(recoRev.ca_ht_ref_pilote)],
      ["CA projeté / mois", euro(sum.ca_ht_mensuel || (data.by_concept[reco] || {}).ca_mensuel)],
      [
        "CA historique model_data",
        ind.ca_historique_mensuel != null
          ? euro(ind.ca_historique_mensuel)
          : "—",
      ],
      ["Mix F&B effectif", pctLabel(recoRev.mix_fb_effective)],
      ["m lin.", recoRev.m_lin],
    ];
    calc.classList.remove("hidden");
    calc.innerHTML = `
      <h2 class="card-title">Détail calcul revenus (ROD · ${escapeHtml(reco || "")})</h2>
      <div class="calc-grid">
        ${items
          .map(
            ([k, v]) =>
              `<div class="calc-item"><span class="k">${escapeHtml(k)}</span><span class="v">${escapeHtml(v)}</span></div>`
          )
          .join("")}
      </div>
      <p class="hint" style="margin-top:.75rem">
        CA projeté = pilote Excel du concept, ajusté par clients (R1), mix (R2),
        catégories (R3), m lin. (R4) et impact TO — pas une copie du CA historique.
      </p>
    `;

    const allowed = new Set(data.allowed_concepts || []);
    const grid = $("#sim-cards");
    grid.innerHTML = "";
    ["SIMPLY", "LIBERTY", "CONNECTED"].forEach((name) => {
      const c = (data.by_concept || {})[name];
      if (!c) return;
      const isReco = name === reco;
      const isAllowed = allowed.has(name);
      const card = document.createElement("article");
      card.className = "concept-card" + (isReco ? " recommended" : "");
      const mn = Number(c.marge_nette_annuelle) || 0;
      const caM = Number(c.ca_mensuel);
      const caA = Number(c.ca_annuel);
      card.innerHTML = `
        <h3>${escapeHtml(name)}</h3>
        ${!isAllowed ? `<div class="blocked">Non autorisé par les règles reco</div>` : ""}
        <div class="metric"><span class="metric-label">CA HT / mois</span><span class="v">${euro(caM)}</span></div>
        <div class="metric"><span class="metric-label">CA HT / an</span><span class="v">${euro(caA)}</span></div>
        <div class="metric"><span class="metric-label">Marge produit / an</span><span class="v">${euro(c.marge_produit_annuelle)}</span></div>
        <div class="metric"><span class="metric-label">Coûts / an</span><span class="v">${euro(c.cout_annuel)}</span></div>
        <div class="metric"><span class="metric-label">Marge nette / an</span><span class="v ${mn >= 0 ? "pos" : "neg"}">${euro(mn)}</span></div>
        <div class="metric"><span class="metric-label">Capex</span><span class="v">${euro(c.capex)}</span></div>
        <div class="metric"><span class="metric-label">ROI</span><span class="v">${c.roi_months != null ? Math.round(c.roi_months) + " mois" : "—"}</span></div>
        <div class="metric"><span class="metric-label">m lin.</span><span class="v">${(c.store && c.store.m_lin) || "—"}</span></div>
      `;
      grid.appendChild(card);
    });

    // enrich
    const en = data.enriched || {};
    const body = $("#enrich-body");
    const items = [];
    if (en.lat != null) items.push(["Latitude", en.lat]);
    if (en.lon != null) items.push(["Longitude", en.lon]);
    if (en.holidays) {
      items.push(["Zone scolaire", en.holidays.zone || "—"]);
      items.push(["% jours holidays", ((en.holidays.pct_jours_holidays || 0) * 100).toFixed(1) + " %"]);
    }
    if (en.weather) {
      if (en.weather.meteo_temperature_c_mean != null)
        items.push(["Temp. moy.", Number(en.weather.meteo_temperature_c_mean).toFixed(1) + " °C"]);
    }
    if (en.proximity) {
      const p = en.proximity;
      if (p.commerce_fb_500m != null) items.push(["F&B 500 m", p.commerce_fb_500m]);
      if (p.plage_distance_km != null) items.push(["Plage (km)", Number(p.plage_distance_km).toFixed(1)]);
    }
    if (items.length) {
      $("#sim-enrich").classList.remove("hidden");
      body.innerHTML = items
        .map(
          ([k, v]) =>
            `<div class="enrich-item"><span class="k">${escapeHtml(k)}</span><span class="v">${escapeHtml(v)}</span></div>`
        )
        .join("");
    }

    const warns = data.warnings || [];
    const wbox = $("#sim-warnings");
    if (warns.length) {
      wbox.classList.remove("hidden");
      wbox.innerHTML = `<div class="warn-list"><strong>Avertissements</strong><ul>${warns
        .map((w) => `<li>${escapeHtml(w)}</li>`)
        .join("")}</ul></div>`;
    } else {
      wbox.classList.add("hidden");
    }
  }

  async function runSimulation() {
    const load = $("#sim-loading");
    const err = $("#sim-error");
    load.classList.remove("hidden");
    err.classList.add("hidden");
    $("#sim-reco").classList.add("hidden");
    $("#sim-cards").innerHTML = "";
    try {
      const payload = collectPayload();
      const res = await fetch("/api/simulate?light=1", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Échec simulation");
      renderResults(data);
      toast("Simulation terminée");
    } catch (e) {
      err.classList.remove("hidden");
      err.textContent = e.message || String(e);
    } finally {
      load.classList.add("hidden");
    }
  }

  async function geocode() {
    const body = {
      street: str("hotel_adresse_postale_1"),
      postal_code: str("hotel_code_postal"),
      city: str("hotel_city"),
      q: [str("hotel_adresse_postale_1"), str("hotel_code_postal"), str("hotel_city")]
        .filter(Boolean)
        .join(", "),
    };
    $("#geocode-hint").textContent = "Recherche…";
    try {
      const res = await fetch("/api/geocode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "Échec");
      $("#hotel_lat").value = data.lat;
      $("#hotel_lon").value = data.lon;
      $("#geocode-hint").textContent = data.display_name || "OK";
      toast("Coordonnées trouvées");
    } catch (e) {
      $("#geocode-hint").textContent = e.message || String(e);
    }
  }

  async function init() {
    renderToggles("svc-fb", SERVICES.fb, { bar: true, restaurant: true });
    renderToggles("svc-nfb", SERVICES.nfb, {
      meeting_rooms: true,
      gym: true,
      spa: true,
      pool: true,
    });
    renderToggles("svc-lobby", SERVICES.lobby, {});

    try {
      const [meta, brands, hotels] = await Promise.all([
        fetch("/api/meta").then((r) => r.json()),
        fetch("/api/brands").then((r) => r.json()),
        fetch("/api/hotels").then((r) => r.json()),
      ]);
      state.meta = meta;
      state.brands = brands.brands || [];
      fillBrands(state.brands);
      fillHotels(hotels.hotels || []);

      renderToggles(
        "needs-fb",
        (meta.client_needs_fb || []).map((n) => ({ id: n.id, label: n.label })),
        Object.fromEntries((meta.client_needs_fb || []).map((n) => [n.id, true]))
      );
      // default nfb: cosmetics/kids/etc on, hygiene off — leave to defaults from server labels
      const nfbDefaults = {};
      (meta.client_needs_nfb || []).forEach((n) => {
        nfbDefaults[n.id] = n.id !== "nfb_hygiene";
      });
      renderToggles(
        "needs-nfb",
        (meta.client_needs_nfb || []).map((n) => ({ id: n.id, label: n.label })),
        nfbDefaults
      );
    } catch (e) {
      console.error(e);
      toast("Chargement partiel des données admin");
    }

    $("#hotel-select").addEventListener("change", async (e) => {
      const code = e.target.value;
      if (!code) {
        $("#hist-box").classList.add("hidden");
        return;
      }
      try {
        const ctx = await loadHotelContext(code);
        applyContext(ctx);
      } catch (err) {
        console.warn(err);
        const h = state.hotels.find((x) => String(x.hotel_code) === code);
        applyHotel(h);
        toast("Contexte partiel (hotel_data seul)");
      }
    });
    ["nb_chambres", "taux_occupation", "guests_per_chambre"].forEach((id) => {
      $(`#${id}`).addEventListener("input", updateDerived);
    });
    $("#btn-geocode").addEventListener("click", geocode);
    $("#btn-prev").addEventListener("click", () => setStep(state.step - 1));
    $("#btn-next").addEventListener("click", () => {
      if (state.step === state.maxStep) runSimulation();
      else setStep(state.step + 1);
    });
    $("#btn-simulate").addEventListener("click", runSimulation);
    $$(".step").forEach((s) =>
      s.addEventListener("click", () => setStep(Number(s.dataset.step)))
    );

    updateDerived();
    setStep(1);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
