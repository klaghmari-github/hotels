/**
 * ROD User Simulator — wizard interactif (5 étapes).
 * Cache-bust: v=20260725b
 */
(function () {
  "use strict";

  var state = {
    step: 1,
    maxStep: 5,
    meta: null,
    hotels: [],
    brands: [],
    ready: false,
  };

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }
  function $$(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  var SERVICES = {
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
    var el = $("#toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.remove("hidden");
    clearTimeout(toast._t);
    toast._t = setTimeout(function () {
      el.classList.add("hidden");
    }, 3200);
  }

  function num(id, fallback) {
    if (fallback === undefined) fallback = 0;
    var el = $(id.charAt(0) === "#" ? id : "#" + id);
    if (!el) return fallback;
    var v = parseFloat(el.value);
    return isFinite(v) ? v : fallback;
  }

  function str(id) {
    var el = $("#" + id);
    return el ? String(el.value || "").trim() : "";
  }

  function checked(id) {
    var el = $("#" + id);
    return !!(el && el.checked);
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function pctLabel(x) {
    if (x == null || isNaN(Number(x))) return "—";
    var v = Number(x);
    if (v <= 1) v *= 100;
    return Math.round(v) + " %";
  }

  function euro(n) {
    var x = Number(n);
    if (!isFinite(x)) return "—";
    try {
      return x.toLocaleString("fr-FR", {
        style: "currency",
        currency: "EUR",
        maximumFractionDigits: 0,
      });
    } catch (e) {
      return Math.round(x) + " €";
    }
  }

  /** TO saisi en % (65) ou en fraction (0.65) → fraction 0–1 */
  function toRate(raw) {
    var to = Number(raw);
    if (!isFinite(to) || to < 0) return 0.65;
    if (to > 1) to = to / 100;
    if (to > 1) to = 1;
    return to;
  }

  var rule1Timer = null;

  function updateDerived() {
    var nEl = $("#nb_chambres");
    var toEl = $("#taux_occupation");
    var gEl = $("#guests_per_chambre");
    var outJ = $("#out-clients-jour");
    var outM = $("#out-clients-mois");
    var formula = $("#clients-formula");

    var n = nEl ? parseFloat(nEl.value) : 80;
    if (!isFinite(n) || n < 0) n = 0;
    var to = toRate(toEl ? toEl.value : 65);
    var g = gEl ? parseFloat(gEl.value) : 1.7;
    if (!isFinite(g) || g < 0) g = 0;

    var jour = n * to * g;
    var mois = jour * 30.5;
    var fmt = function (x) {
      try {
        return x.toLocaleString("fr-FR", {
          maximumFractionDigits: 1,
          minimumFractionDigits: 0,
        });
      } catch (e) {
        return String(Math.round(x * 10) / 10);
      }
    };

    if (outJ) outJ.textContent = fmt(jour);
    if (outM) outM.textContent = fmt(mois);
    if (formula) {
      var toPct = Math.round(to * 1000) / 10;
      formula.innerHTML =
        "<div>" +
        n +
        " ch × " +
        toPct +
        " % TO × " +
        g +
        " guests/ch = <strong>" +
        fmt(jour) +
        " clients/jour</strong></div>" +
        "<div>" +
        fmt(jour) +
        " clients/jour × 30,5 = <strong>" +
        fmt(mois) +
        " clients/mois</strong></div>";
    }

    // Recalcule le CA Règle 1 (debounce)
    clearTimeout(rule1Timer);
    rule1Timer = setTimeout(function () {
      fetchRule1(n, to, g);
    }, 200);
  }

  function renderRule1(data) {
    var detail = $("#rule1-detail");
    var meta = $("#rule1-meta");
    if (!data || !data.ok || !data.by_concept) {
      ["SIMPLY", "LIBERTY", "CONNECTED"].forEach(function (c) {
        var caEl = $("#r1-ca-" + c);
        var subEl = $("#r1-sub-" + c);
        if (caEl) caEl.textContent = "—";
        if (subEl) subEl.textContent = "";
        var card = document.querySelector('.rule1-card[data-concept="' + c + '"]');
        if (card) card.classList.remove("best");
      });
      if (detail) detail.textContent = "";
      return;
    }

    if (meta) {
      meta.textContent =
        "Vos clients / mois : " +
        Number(data.clients_mois).toLocaleString("fr-FR", {
          maximumFractionDigits: 1,
        }) +
        " — CA = (CA pilote + impact TO) × (clients hôtel ÷ clients pilote)";
    }

    var best = null;
    var bestCa = -Infinity;
    ["SIMPLY", "LIBERTY", "CONNECTED"].forEach(function (c) {
      var row = data.by_concept[c] || {};
      var ca = Number(row.ca_ht_mensuel);
      if (isFinite(ca) && ca > bestCa) {
        bestCa = ca;
        best = c;
      }
      var caEl = $("#r1-ca-" + c);
      var subEl = $("#r1-sub-" + c);
      if (caEl) caEl.textContent = isFinite(ca) ? euro(ca) : "—";
      if (subEl) {
        subEl.innerHTML =
          "pilote " +
          euro(row.ca_ht_pilote) +
          "<br>facteur ×" +
          (row.client_factor != null
            ? Number(row.client_factor).toFixed(2)
            : "—");
      }
      var card = document.querySelector('.rule1-card[data-concept="' + c + '"]');
      if (card) card.classList.toggle("best", c === best);
    });

    if (detail && best) {
      var b = data.by_concept[best];
      detail.textContent =
        "Meilleur CA Règle 1 : " +
        best +
        " (" +
        euro(b.ca_ht_mensuel) +
        "/mois) — clients pilote " +
        Number(b.clients_pilote).toLocaleString("fr-FR", {
          maximumFractionDigits: 0,
        }) +
        ", facteur " +
        Number(b.client_factor).toFixed(3) +
        ". (R2 mix, R3 catégories et R4 m lin. viennent ensuite.)";
    }
  }

  function fetchRule1(n, to, g) {
    return fetch("/api/rule1", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nb_chambres: n,
        taux_occupation: to,
        guests_per_chambre: g,
      }),
    })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        renderRule1(data);
        return data;
      })
      .catch(function (e) {
        console.error("[ROD] rule1", e);
        renderRule1(null);
      });
  }

  function setStep(n) {
    state.step = Math.min(Math.max(n, 1), state.maxStep);
    $$(".panel").forEach(function (p) {
      p.classList.toggle("hidden", Number(p.dataset.panel) !== state.step);
    });
    $$(".step").forEach(function (s) {
      var i = Number(s.dataset.step);
      s.classList.toggle("active", i === state.step);
      s.classList.toggle("done", i < state.step);
    });
    var prev = $("#btn-prev");
    var next = $("#btn-next");
    var label = $("#step-label");
    if (prev) prev.disabled = state.step === 1;
    if (next) {
      next.textContent = state.step === state.maxStep ? "Relancer" : "Valider";
    }
    if (label) label.textContent = "Étape " + state.step + " / " + state.maxStep;
    if (state.step === 5) {
      var cards = $("#sim-cards");
      if (cards && !cards.children.length) runSimulation();
    }
  }

  function brandName(b) {
    if (b == null) return "";
    if (typeof b === "string") return b.trim();
    return String(
      b.brand || b.Marque || b.marque || b.hotel_brand || ""
    ).trim();
  }

  function fillBrands(brands) {
    var sel = $("#hotel_brand");
    if (!sel) {
      console.warn("[ROD] #hotel_brand introuvable");
      return;
    }
    var names = [];
    var seen = {};
    function add(n) {
      n = String(n || "").trim();
      if (!n) return;
      var key = n.toUpperCase();
      if (seen[key]) return;
      seen[key] = true;
      names.push(n);
    }
    (brands || []).forEach(function (b) {
      add(brandName(b));
    });
    (state.hotels || []).forEach(function (h) {
      add(h && h.hotel_brand);
    });
    names.sort(function (a, b) {
      return a.localeCompare(b, "fr", { sensitivity: "base" });
    });

    var current = sel.value;
    var html = '<option value="">— Choisir une marque —</option>';
    names.forEach(function (n) {
      // value sans entités HTML (sinon select.value ne matche pas)
      html +=
        '<option value="' +
        escapeHtml(n) +
        '">' +
        escapeHtml(n) +
        "</option>";
    });
    sel.innerHTML = html;
    if (current) setBrandValue(current);
    console.info("[ROD] marques chargées:", names.length, names);
  }

  function setBrandValue(name) {
    var sel = $("#hotel_brand");
    if (!sel) return;
    if (name == null || name === "") {
      sel.value = "";
      return;
    }
    var target = String(name).trim();
    var options = Array.prototype.slice.call(sel.options);
    var match = null;
    for (var i = 0; i < options.length; i++) {
      if (options[i].value === target) {
        match = options[i];
        break;
      }
    }
    if (!match) {
      for (var j = 0; j < options.length; j++) {
        if (options[j].value.toUpperCase() === target.toUpperCase()) {
          match = options[j];
          break;
        }
      }
    }
    if (!match && target) {
      match = document.createElement("option");
      match.value = target;
      match.textContent = target;
      sel.appendChild(match);
    }
    if (match) sel.value = match.value;
  }

  function renderToggles(containerId, items, defaults) {
    defaults = defaults || {};
    var root = $("#" + containerId);
    if (!root) return;
    root.innerHTML = items
      .map(function (it) {
        var on = defaults[it.id] !== false && defaults[it.id] !== 0;
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
  }

  /**
   * Étape 1 — moyennes concept_pilote pour la marque (hors année la plus récente).
   * Préremplit chambres / TO / guests. Pas de mix F_B (onglet suivant).
   */
  function applyBrandPilotAverages(data) {
    var box = $("#brand-pilot-box");
    if (!box) return;
    if (!data || !data.ok || !data.averages) {
      box.classList.add("hidden");
      return;
    }
    var a = data.averages;
    box.classList.remove("hidden");

    var nameEl = $("#brand-pilot-name");
    if (nameEl) nameEl.textContent = data.brand || "";

    var meta = $("#brand-pilot-meta");
    if (meta) {
      var src =
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
    var hint = $("#brand-pilot-hint");
    if (hint) {
      if (data.note) {
        hint.textContent = data.note;
      } else {
        hint.textContent =
          "Valeurs préremplies dans les champs d’exploitation — vous pouvez les ajuster.";
      }
    }

    function setText(id, text) {
      var el = $("#" + id);
      if (el) el.textContent = text;
    }
    setText(
      "bp-chambres",
      a.nb_chambres != null ? Math.round(a.nb_chambres) : "—"
    );
    setText(
      "bp-to",
      a.taux_occupation != null ? pctLabel(a.taux_occupation) : "—"
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
        ? Number(a.clients_jour).toLocaleString("fr-FR", {
            maximumFractionDigits: 1,
          })
        : "—"
    );
    setText(
      "bp-clients-m",
      a.clients_mois != null
        ? Number(a.clients_mois).toLocaleString("fr-FR", {
            maximumFractionDigits: 1,
          })
        : "—"
    );
    setText(
      "bp-ca",
      a.ca_mensuel_moyen != null ? euro(a.ca_mensuel_moyen) : "—"
    );

    // Préremplir les champs d'exploitation (modifiables ensuite)
    if (a.nb_chambres != null) {
      var ch = $("#nb_chambres");
      if (ch) ch.value = Math.round(a.nb_chambres);
    }
    if (a.taux_occupation != null) {
      var toEl = $("#taux_occupation");
      if (toEl) {
        var toPct = Number(a.taux_occupation);
        if (toPct <= 1) toPct *= 100;
        toEl.value = Math.round(toPct * 10) / 10;
      }
    }
    if (a.guests_per_chambre != null) {
      var gEl = $("#guests_per_chambre");
      if (gEl) gEl.value = Number(a.guests_per_chambre).toFixed(2);
    }
    updateDerived();
    // Si le backend a déjà calculé rule1 sur les moyennes, l'afficher tout de suite
    if (data.rule1 && data.rule1.ok) {
      renderRule1(data.rule1);
    }
  }

  function loadBrandPilotAverages(brand) {
    brand = String(brand || "").trim();
    var box = $("#brand-pilot-box");
    if (!brand) {
      if (box) box.classList.add("hidden");
      return Promise.resolve(null);
    }
    return fetch(
      "/api/concept_pilote/brand/" + encodeURIComponent(brand)
    )
      .then(function (res) {
        return res.json().then(function (data) {
          if (!data.ok) {
            if (box) box.classList.add("hidden");
            console.warn("[ROD] concept_pilote marque:", data.error);
            return null;
          }
          applyBrandPilotAverages(data);
          return data;
        });
      })
      .catch(function (e) {
        console.error("[ROD] brand pilot", e);
        if (box) box.classList.add("hidden");
        return null;
      });
  }

  function loadHotelContext(code) {
    return fetch("/api/hotels/" + encodeURIComponent(code) + "/context").then(
      function (res) {
        return res.json().then(function (data) {
          if (!res.ok || data.ok === false) {
            throw new Error(data.error || "Contexte indisponible");
          }
          return data;
        });
      }
    );
  }

  function applyContext(ctx) {
    if (!ctx) return;
    var id = ctx.identity || {};
    var op = ctx.operating || {};
    var corner = ctx.corner || {};
    var services = ctx.services || {};
    var profile = ctx.client_profile || {};
    var needs = profile.client_needs || {};

    function setVal(fieldId, v) {
      var el = $("#" + fieldId);
      if (el && v != null && v !== "") el.value = v;
    }

    setVal("hotel_code", id.hotel_code);
    setVal("hotel_name", id.hotel_name);
    setVal("hotel_adresse_postale_1", id.hotel_adresse_postale_1);
    setVal("hotel_adresse_postale_2", id.hotel_adresse_postale_2);
    setVal("hotel_code_postal", id.hotel_code_postal);
    setVal("hotel_city", id.hotel_city);
    setVal("hotel_lat", id.hotel_lat);
    setVal("hotel_lon", id.hotel_lon);
    if (id.hotel_brand) setBrandValue(id.hotel_brand);

    if (op.nb_chambres) setVal("nb_chambres", op.nb_chambres);
    if (op.taux_occupation != null) {
      var to = Number(op.taux_occupation);
      if (to <= 1) to *= 100;
      setVal("taux_occupation", Math.round(to * 10) / 10);
    }
    if (op.guests_per_chambre) {
      setVal(
        "guests_per_chambre",
        Number(op.guests_per_chambre).toFixed(1)
      );
    }

    Object.keys(services).forEach(function (sid) {
      var el = $("#" + sid);
      if (el) el.checked = !!services[sid];
    });

    var hasCorner = $("#has_corner");
    if (hasCorner) hasCorner.checked = !!corner.has_corner;
    if (corner.m_lin != null && corner.m_lin !== "") {
      setVal("m_lin", corner.m_lin);
    }
    if (corner.mix_fb != null) {
      var m = Number(corner.mix_fb);
      if (m <= 1) m *= 100;
      setVal("mix_fb", Math.round(m));
    }

    function pctField(fieldId, v) {
      if (v == null) return;
      var p = Number(v);
      if (p <= 1) p *= 100;
      setVal(fieldId, Math.round(p));
    }
    pctField("loisirs_pct", profile.loisirs_pct);
    pctField("affaires_pct", profile.affaires_pct);
    pctField("national_pct", profile.national_pct);
    pctField("international_pct", profile.international_pct);

    Object.keys(needs).forEach(function (nid) {
      var el = $("#" + nid);
      if (el) el.checked = !!needs[nid];
    });

    updateDerived();
    // Après profil hôtel : moyennes marque (concept_pilote, hors dernière année)
    if (id.hotel_brand) {
      loadBrandPilotAverages(id.hotel_brand);
    }
    toast("Profil " + (id.hotel_code || "") + " chargé");
  }

  function collectPayload() {
    var services = {};
    SERVICES.fb
      .concat(SERVICES.nfb)
      .concat(SERVICES.lobby)
      .forEach(function (s) {
        services[s.id] = checked(s.id);
      });

    var client_needs = {};
    ((state.meta && state.meta.client_needs_fb) || []).forEach(function (n) {
      client_needs[n.id] = checked(n.id);
    });
    ((state.meta && state.meta.client_needs_nfb) || []).forEach(function (n) {
      client_needs[n.id] = checked(n.id);
    });

    var to = toRate(num("taux_occupation", 65));
    var mLinRaw = $("#m_lin") ? $("#m_lin").value : "";
    var mixFbRaw = $("#mix_fb") ? $("#mix_fb").value : "";

    return {
      identity: {
        hotel_code: str("hotel_code"),
        hotel_name: str("hotel_name"),
        hotel_brand: str("hotel_brand"),
        hotel_lat: $("#hotel_lat") && $("#hotel_lat").value === "" ? null : num("hotel_lat"),
        hotel_lon: $("#hotel_lon") && $("#hotel_lon").value === "" ? null : num("hotel_lon"),
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
      services: services,
      client_profile: {
        loisirs_pct: num("loisirs_pct", 30) / 100,
        affaires_pct: num("affaires_pct", 70) / 100,
        national_pct: num("national_pct", 60) / 100,
        international_pct: num("international_pct", 40) / 100,
        client_needs: client_needs,
      },
      corner: {
        has_corner: checked("has_corner"),
        m_lin: mLinRaw === "" ? null : num("m_lin"),
        mix_fb: mixFbRaw === "" ? null : num("mix_fb") / 100,
      },
      light_enrich: true,
    };
  }

  function renderResults(data) {
    var reco = data.recommended_concept;
    var banner = $("#sim-reco");
    if (banner) {
      banner.classList.remove("hidden");
      banner.innerHTML =
        '<div class="tag">Recommandation</div><h2>' +
        escapeHtml(reco) +
        "</h2><p>" +
        escapeHtml(data.recommendation_reason || "") +
        "</p>";
    }

    var calc = $("#sim-calc");
    var ind = (data.enriched && data.enriched.indicators) || {};
    var sum = data.calc_summary || {};
    var recoRev =
      (data.by_concept &&
        data.by_concept[reco] &&
        data.by_concept[reco].revenue &&
        data.by_concept[reco].revenue.breakdown) ||
      {};
    var items = [
      ["Chambres", ind.nb_chambres != null ? ind.nb_chambres : recoRev.nb_chambres],
      ["TO", pctLabel(ind.taux_occupation != null ? ind.taux_occupation : recoRev.taux_occupation)],
      ["Guests/ch", ind.guests_per_chambre != null ? ind.guests_per_chambre : recoRev.guests_per_chambre],
      ["Clients / mois", Math.round(ind.clients_mois || recoRev.clients_hotel || 0)],
      ["Clients pilote", Math.round(recoRev.clients_pilote || 0)],
      [
        "Facteur clients (R1)",
        recoRev.client_factor != null
          ? Number(recoRev.client_factor).toFixed(3)
          : "—",
      ],
      ["CA pilote concept", euro(recoRev.ca_ht_ref_pilote)],
      [
        "CA projeté / mois",
        euro(
          sum.ca_ht_mensuel ||
            (data.by_concept && data.by_concept[reco]
              ? data.by_concept[reco].ca_mensuel
              : null)
        ),
      ],
      [
        "CA historique",
        ind.ca_historique_mensuel != null
          ? euro(ind.ca_historique_mensuel)
          : "—",
      ],
      ["Mix F&B effectif", pctLabel(recoRev.mix_fb_effective)],
      ["m lin.", recoRev.m_lin],
    ];
    if (calc) {
      calc.classList.remove("hidden");
      calc.innerHTML =
        '<h2 class="card-title">Détail calcul revenus (ROD · ' +
        escapeHtml(reco || "") +
        ')</h2><div class="calc-grid">' +
        items
          .map(function (pair) {
            return (
              '<div class="calc-item"><span class="k">' +
              escapeHtml(pair[0]) +
              '</span><span class="v">' +
              escapeHtml(pair[1]) +
              "</span></div>"
            );
          })
          .join("") +
        '</div><p class="hint" style="margin-top:.75rem">' +
        "Règle 1 = CA pilote × (clients hôtel / clients pilote). " +
        "Puis règles 2–4 (mix, catégories, m lin.) et impact TO." +
        "</p>";
    }

    var allowed = {};
    (data.allowed_concepts || []).forEach(function (c) {
      allowed[c] = true;
    });
    var grid = $("#sim-cards");
    if (!grid) return;
    grid.innerHTML = "";
    ["SIMPLY", "LIBERTY", "CONNECTED"].forEach(function (name) {
      var c = (data.by_concept || {})[name];
      if (!c) return;
      var isReco = name === reco;
      var isAllowed = !!allowed[name];
      var card = document.createElement("article");
      card.className = "concept-card" + (isReco ? " recommended" : "");
      var mn = Number(c.marge_nette_annuelle) || 0;
      var caM = Number(c.ca_mensuel);
      var caA = Number(c.ca_annuel);
      card.innerHTML =
        "<h3>" +
        escapeHtml(name) +
        "</h3>" +
        (!isAllowed
          ? '<div class="blocked">Non autorisé par les règles reco</div>'
          : "") +
        '<div class="metric"><span class="metric-label">CA HT / mois</span><span class="v">' +
        euro(caM) +
        "</span></div>" +
        '<div class="metric"><span class="metric-label">CA HT / an</span><span class="v">' +
        euro(caA) +
        "</span></div>" +
        '<div class="metric"><span class="metric-label">Marge produit / an</span><span class="v">' +
        euro(c.marge_produit_annuelle) +
        "</span></div>" +
        '<div class="metric"><span class="metric-label">Coûts / an</span><span class="v">' +
        euro(c.cout_annuel) +
        "</span></div>" +
        '<div class="metric"><span class="metric-label">Marge nette / an</span><span class="v ' +
        (mn >= 0 ? "pos" : "neg") +
        '">' +
        euro(mn) +
        "</span></div>" +
        '<div class="metric"><span class="metric-label">Capex</span><span class="v">' +
        euro(c.capex) +
        "</span></div>" +
        '<div class="metric"><span class="metric-label">ROI</span><span class="v">' +
        (c.roi_months != null ? Math.round(c.roi_months) + " mois" : "—") +
        "</span></div>" +
        '<div class="metric"><span class="metric-label">m lin.</span><span class="v">' +
        ((c.store && c.store.m_lin) || "—") +
        "</span></div>";
      grid.appendChild(card);
    });

    var en = data.enriched || {};
    var body = $("#enrich-body");
    var enrichItems = [];
    if (en.lat != null) enrichItems.push(["Latitude", en.lat]);
    if (en.lon != null) enrichItems.push(["Longitude", en.lon]);
    if (en.holidays) {
      enrichItems.push(["Zone scolaire", en.holidays.zone || "—"]);
      enrichItems.push([
        "% jours holidays",
        ((en.holidays.pct_jours_holidays || 0) * 100).toFixed(1) + " %",
      ]);
    }
    if (en.weather && en.weather.meteo_temperature_c_mean != null) {
      enrichItems.push([
        "Temp. moy.",
        Number(en.weather.meteo_temperature_c_mean).toFixed(1) + " °C",
      ]);
    }
    if (en.proximity) {
      var p = en.proximity;
      if (p.commerce_fb_500m != null)
        enrichItems.push(["F&B 500 m", p.commerce_fb_500m]);
      if (p.plage_distance_km != null)
        enrichItems.push([
          "Plage (km)",
          Number(p.plage_distance_km).toFixed(1),
        ]);
    }
    var simEnrich = $("#sim-enrich");
    if (enrichItems.length && body && simEnrich) {
      simEnrich.classList.remove("hidden");
      body.innerHTML = enrichItems
        .map(function (pair) {
          return (
            '<div class="enrich-item"><span class="k">' +
            escapeHtml(pair[0]) +
            '</span><span class="v">' +
            escapeHtml(pair[1]) +
            "</span></div>"
          );
        })
        .join("");
    }

    var warns = data.warnings || [];
    var wbox = $("#sim-warnings");
    if (wbox) {
      if (warns.length) {
        wbox.classList.remove("hidden");
        wbox.innerHTML =
          '<div class="warn-list"><strong>Avertissements</strong><ul>' +
          warns
            .map(function (w) {
              return "<li>" + escapeHtml(w) + "</li>";
            })
            .join("") +
          "</ul></div>";
      } else {
        wbox.classList.add("hidden");
      }
    }
  }

  function runSimulation() {
    var load = $("#sim-loading");
    var err = $("#sim-error");
    var btnSim = $("#btn-simulate");
    var btnNext = $("#btn-next");
    if (load) load.classList.remove("hidden");
    if (err) err.classList.add("hidden");
    var reco = $("#sim-reco");
    if (reco) reco.classList.add("hidden");
    var calc = $("#sim-calc");
    if (calc) calc.classList.add("hidden");
    var cards = $("#sim-cards");
    if (cards) cards.innerHTML = "";
    if (btnSim) {
      btnSim.disabled = true;
      btnSim.classList.add("busy");
    }
    if (btnNext) {
      btnNext.disabled = true;
      btnNext.classList.add("busy");
    }
    toast("Veuillez patienter — simulation en cours…");

    var payload = collectPayload();
    fetch("/api/simulate?light=1", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) {
            throw new Error(data.error || "Échec simulation");
          }
          return data;
        });
      })
      .then(function (data) {
        renderResults(data);
        toast("Simulation terminée");
      })
      .catch(function (e) {
        if (err) {
          err.classList.remove("hidden");
          err.textContent = e.message || String(e);
        }
      })
      .then(function () {
        if (load) load.classList.add("hidden");
        if (btnSim) {
          btnSim.disabled = false;
          btnSim.classList.remove("busy");
        }
        if (btnNext) {
          btnNext.disabled = false;
          btnNext.classList.remove("busy");
        }
      });
  }

  function setGeocodeWaiting(on) {
    var btn = $("#btn-geocode");
    var status = $("#geocode-status");
    var hint = $("#geocode-hint");
    if (btn) {
      btn.classList.toggle("busy", !!on);
      btn.disabled = !!on;
      var label = btn.querySelector(".btn-label");
      if (label) {
        label.textContent = on
          ? "Localisation en cours…"
          : "Localiser depuis l’adresse";
      }
    }
    if (status) {
      if (on) status.classList.remove("hidden");
      else status.classList.add("hidden");
      status.classList.remove("ok", "err");
    }
    if (on && hint) {
      hint.textContent = "Veuillez patienter pendant la recherche…";
      hint.style.color = "";
    }
  }

  function geocode() {
    var street = str("hotel_adresse_postale_1");
    var postal = str("hotel_code_postal");
    var city = str("hotel_city");
    var hotelName = str("hotel_name");
    var complement = str("hotel_adresse_postale_2");
    var hotelCode = str("hotel_code");
    var hint = $("#geocode-hint");

    var hasAccorHint =
      /all\.accor\.com\/hotel\//i.test(hotelCode) ||
      /^[Hh]?\d{3,5}$/.test(hotelCode);

    if (!street && !city && !hotelName && !postal && !hasAccorHint) {
      if (hint) {
        hint.textContent =
          "Renseignez une adresse, une ville, un nom d’hôtel, ou un code Accor (ex. 1545).";
        hint.style.color = "#991b1b";
      }
      toast("Adresse insuffisante pour localiser");
      return;
    }

    var body = {
      street: street || complement,
      postal_code: postal,
      city: city,
      hotel_name: hotelName,
      hotel_code: hotelCode,
      q: [street, complement, postal, city, hotelName, hotelCode]
        .filter(Boolean)
        .join(", "),
      accor_url: /all\.accor\.com/i.test(hotelCode) ? hotelCode : "",
    };

    setGeocodeWaiting(true);
    toast("Veuillez patienter — localisation en cours…");

    fetch("/api/geocode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!data.ok) {
            throw new Error(
              data.error || "Aucun résultat pour cette adresse"
            );
          }
          return data;
        });
      })
      .then(function (data) {
        var latEl = $("#hotel_lat");
        var lonEl = $("#hotel_lon");
        if (latEl) latEl.value = Number(data.lat).toFixed(6);
        if (lonEl) lonEl.value = Number(data.lon).toFixed(6);
        // Préremplir adresse si venue de la fiche Accor
        if (data.address && !street) {
          var parts = String(data.address).split(",");
          if (parts[0] && $("#hotel_adresse_postale_1")) {
            $("#hotel_adresse_postale_1").value = parts[0].trim();
          }
        }
        if (data.hotel_name && !hotelName && $("#hotel_name")) {
          $("#hotel_name").value = data.hotel_name;
        }
        if (hint) {
          hint.style.color = "#14532d";
          var src = data.source ? " [" + data.source + "]" : "";
          hint.textContent =
            "✓ Position trouvée" +
            src +
            " : " +
            (data.display_name || data.lat + ", " + data.lon);
        }
        toast("Coordonnées trouvées");
      })
      .catch(function (e) {
        if (hint) {
          hint.style.color = "#991b1b";
          hint.textContent = "✗ " + (e.message || String(e));
        }
        toast("Échec de la localisation");
      })
      .then(function () {
        setGeocodeWaiting(false);
      });
  }

  function wireEvents() {
    var hotelCodeInput = $("#hotel_code");
    if (hotelCodeInput) {
      var codeTimer = null;
      var tryLoadByCode = function () {
        var code = str("hotel_code");
        if (!code) return;
        clearTimeout(codeTimer);
        codeTimer = setTimeout(function () {
          loadHotelContext(code)
            .then(function (ctx) {
              if (ctx) applyContext(ctx);
            })
            .catch(function () {
              /* saisie libre */
            });
        }, 400);
      };
      hotelCodeInput.addEventListener("change", tryLoadByCode);
      hotelCodeInput.addEventListener("blur", tryLoadByCode);
    }

    // Marque → moyennes concept_pilote (étape 1)
    var brandSel = $("#hotel_brand");
    if (brandSel) {
      brandSel.addEventListener("change", function () {
        loadBrandPilotAverages(brandSel.value);
      });
    }

    ["nb_chambres", "taux_occupation", "guests_per_chambre"].forEach(
      function (id) {
        var el = $("#" + id);
        if (el) {
          el.addEventListener("input", updateDerived);
          el.addEventListener("change", updateDerived);
        }
      }
    );

    var btnGeo = $("#btn-geocode");
    if (btnGeo) {
      btnGeo.addEventListener("click", function (ev) {
        ev.preventDefault();
        geocode();
      });
    } else {
      console.error("[ROD] #btn-geocode introuvable");
    }

    var btnPrev = $("#btn-prev");
    if (btnPrev) {
      btnPrev.addEventListener("click", function () {
        setStep(state.step - 1);
      });
    }
    var btnNext = $("#btn-next");
    if (btnNext) {
      btnNext.addEventListener("click", function () {
        if (state.step === state.maxStep) runSimulation();
        else setStep(state.step + 1);
      });
    }
    var btnSim = $("#btn-simulate");
    if (btnSim) {
      btnSim.addEventListener("click", runSimulation);
    }
    $$(".step").forEach(function (s) {
      var go = function () {
        setStep(Number(s.dataset.step));
      };
      s.addEventListener("click", go);
      s.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          go();
        }
      });
    });
  }

  function loadBrands() {
    return fetch("/api/brands")
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (brandsRes) {
        var list = brandsRes.brands || brandsRes || [];
        if (!Array.isArray(list)) list = [];
        state.brands = list;
        fillBrands(list);
        if (!list.length) toast("Aucune marque disponible");
      })
      .catch(function (e) {
        console.error("[ROD] brands", e);
        fillBrands([]);
        toast("Impossible de charger les marques");
      });
  }

  function loadHotels() {
    return fetch("/api/hotels")
      .then(function (r) {
        return r.json();
      })
      .then(function (hotelsRes) {
        state.hotels = hotelsRes.hotels || [];
      })
      .catch(function (e) {
        console.error("[ROD] hotels", e);
        state.hotels = [];
      });
  }

  function loadMeta() {
    return fetch("/api/meta")
      .then(function (r) {
        return r.json();
      })
      .then(function (meta) {
        state.meta = meta;
        renderToggles(
          "needs-fb",
          (meta.client_needs_fb || []).map(function (n) {
            return { id: n.id, label: n.label };
          }),
          (function () {
            var d = {};
            (meta.client_needs_fb || []).forEach(function (n) {
              d[n.id] = true;
            });
            return d;
          })()
        );
        var nfbDefaults = {};
        (meta.client_needs_nfb || []).forEach(function (n) {
          nfbDefaults[n.id] = n.id !== "nfb_hygiene";
        });
        renderToggles(
          "needs-nfb",
          (meta.client_needs_nfb || []).map(function (n) {
            return { id: n.id, label: n.label };
          }),
          nfbDefaults
        );
      })
      .catch(function (e) {
        console.error("[ROD] meta", e);
      });
  }

  function init() {
    if (state.ready) return;
    state.ready = true;
    console.info("[ROD] init user UI");

    renderToggles("svc-fb", SERVICES.fb, { bar: true, restaurant: true });
    renderToggles("svc-nfb", SERVICES.nfb, {
      meeting_rooms: true,
      gym: true,
      spa: true,
      pool: true,
    });
    renderToggles("svc-lobby", SERVICES.lobby, {});

    wireEvents();
    updateDerived();
    setStep(1);

    // Marques d'abord (critique UI), puis hotels (complète la liste), puis meta
    loadBrands()
      .then(function () {
        return loadHotels();
      })
      .then(function () {
        // re-remplit avec union hotels
        fillBrands(state.brands);
        return loadMeta();
      });
  }

  // Init fiable : DOMContentLoaded ou document déjà prêt (script en bas de page / cache)
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Expose pour debug console
  window.RODUser = {
    updateDerived: updateDerived,
    geocode: geocode,
    fillBrands: fillBrands,
    loadBrandPilotAverages: loadBrandPilotAverages,
    state: state,
  };
})();
