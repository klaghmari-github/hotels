/**
 * Front-end admin Accor Data and Model Studio (IIFE).
 *
 * Vue table:
 *   onglets datasets, table editable, dirty map, Ctrl+S / Enregistrer
 *   Recharger = POST reload, Reconstruire = POST rebuild selon l onglet
 *   pagination et filtre via GET /api/datasets/<id>
 *
 * Model Build:
 *   hyperparams + nom, POST /api/model/build vers models/design/<nom>/
 *
 * Model Explore:
 *   liste design, perfs, importances, arbres SVG, Deploy vers models/deploy/
 *
 * Etat principal: state (onglet, page, dirty, explore).
 * Helpers: api, fetchPage, renderTable, loadExploreModel, showLoading.
 * Doc detaillee des boutons et routes: README.md.
 */
(() => {
  // -------------------------------------------------------------------------
  // État applicatif
  // -------------------------------------------------------------------------
  const state = {
    datasets: [], // métadonnées des onglets (GET /api/datasets)
    currentId: null, // id de l'onglet actif (brand, hotel, …)
    page: 1, // page courante (1-based)
    pageSize: 25, // lignes par page
    q: "", // filtre texte
    payload: null, // dernière réponse page (colonnes + rows)
    dirty: new Map(), // Map<_index, rowPartielle> — lignes à sauver
    selected: new Set(), // _index cochés pour suppression
    panel: "table", // "table" | "model-build" | "model-explore"
    modelConfig: null, // payload /api/model/config
    explore: {
      models: [],
      overview: null,
      treeMetrics: null,
      impScope: "global", // "global" | "target"
    },
  };

  // -------------------------------------------------------------------------
  // Références DOM
  // -------------------------------------------------------------------------
  const $ = (sel) => document.querySelector(sel);
  const nav = $("#nav-tabs");
  const navPinnedTop = $("#nav-pinned-top");
  // Zone All : parc global (marques, hôtels, proximité, holidays, weather — pas seulement pilotes)
  const PINNED_TOP_IDS = ["brand", "hotel", "proximity", "holidays", "weather"];
  const title = $("#panel-title");
  const desc = $("#panel-desc");
  const chipFile = $("#chip-file");
  const chipStats = $("#chip-stats");
  const chipDirty = $("#chip-dirty");
  const statusMsg = $("#status-msg");
  const thead = $("#table-head");
  const tbody = $("#table-body");
  const pagerInfo = $("#pager-info");
  const btnSave = $("#btn-save");
  const btnDelete = $("#btn-delete");
  const btnRebuild = $("#btn-rebuild");
  const searchInput = $("#search-input");
  const pageSizeSel = $("#page-size");

  // Icônes des onglets (clés = schema.icon)
  const ICONS = {
    building: "🏛",
    hotel: "🛎",
    cloud: "☁",
    map: "📍",
    chart: "📈",
    calendar: "📅",
    table: "▦",
  };

  const viewTable = $("#view-table");
  const viewModelBuild = $("#view-model-build");
  const viewModelExplore = $("#view-model-explore");
  const navModelBuild = $("#nav-model-build");
  const navModelExplore = $("#nav-model-explore");

  // -------------------------------------------------------------------------
  // Utilitaires UI
  // -------------------------------------------------------------------------

  /** Toast bas-droite (auto-disparition ~3 s). */
  function toast(message, type = "ok") {
    const host = $("#toast-host");
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = message;
    host.appendChild(el);
    setTimeout(() => el.remove(), 3200);
  }

  /** Active/désactive le bouton Enregistrer + chip « non enregistré ». */
  function setDirtyUI() {
    const n = state.dirty.size;
    btnSave.disabled = n === 0;
    chipDirty.classList.toggle("hidden", n === 0);
    chipDirty.textContent =
      n === 0 ? "" : `${n} ligne${n > 1 ? "s" : ""} modifiée${n > 1 ? "s" : ""}`;
  }

  function setStatus(msg) {
    statusMsg.textContent = msg || "";
  }

  // ---- Overlay de chargement (onglets lourds : sales_raw, all_data, …) ----
  let _loadingDepth = 0;
  let _loadingHideTimer = null;

  function showLoading(title, sub) {
    const overlay = $("#loading-overlay");
    if (!overlay) return;
    _loadingDepth += 1;
    if (_loadingHideTimer) {
      clearTimeout(_loadingHideTimer);
      _loadingHideTimer = null;
    }
    const t = $("#loading-title");
    const s = $("#loading-sub");
    if (t) t.textContent = title || "Chargement…";
    if (s) s.textContent = sub || "Préparation des données";
    overlay.classList.remove("hidden", "is-leaving");
    overlay.setAttribute("aria-busy", "true");
    document.body.classList.add("is-loading");
  }

  function hideLoading() {
    const overlay = $("#loading-overlay");
    if (!overlay) return;
    _loadingDepth = Math.max(0, _loadingDepth - 1);
    if (_loadingDepth > 0) return;
    overlay.classList.add("is-leaving");
    overlay.setAttribute("aria-busy", "false");
    document.body.classList.remove("is-loading");
    _loadingHideTimer = setTimeout(() => {
      if (_loadingDepth === 0) {
        overlay.classList.add("hidden");
        overlay.classList.remove("is-leaving");
      }
      _loadingHideTimer = null;
    }, 200);
  }

  /** Libellé lisible pour l'overlay selon l'onglet. */
  function loadingLabelsFor(datasetId) {
    const ds = state.datasets.find((d) => d.id === datasetId);
    const name = (ds && ds.label) || datasetId || "données";
    const heavy = {
      sales_raw: "Fichier ventes brutes volumineux — un instant…",
      sales: "Agrégats ventes — un instant…",
      all_data: "Table jointure complète — un instant…",
      model_data: "Jeu d'entraînement — un instant…",
      hotel: "Parc hôtelier — un instant…",
      proximity: "Indicateurs de proximité — un instant…",
      holidays: "Calendriers hôtels — un instant…",
      weather: "Séries météo — un instant…",
      brand: "Marques — un instant…",
      concept_pilote: "Indicateurs pilotes — un instant…",
    };
    return {
      title: `Chargement · ${name}`,
      sub: heavy[datasetId] || "Récupération de la page…",
    };
  }

  /**
   * Appel API JSON.
   * @throws Error si HTTP non-2xx (message = body.error si présent)
   */
  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || res.statusText);
    return data;
  }

  // -------------------------------------------------------------------------
  // Navigation onglets
  // -------------------------------------------------------------------------

  /** Charge la liste des datasets et ouvre le premier. */
  async function loadDatasets() {
    const data = await api("/api/datasets");
    state.datasets = data.datasets || [];
    renderNav();
    if (state.datasets.length) {
      await selectDataset(state.datasets[0].id);
    }
  }

  /** Crée un bouton d'onglet dataset. */
  function makeNavButton(ds) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "nav-item" + (ds.id === state.currentId ? " active" : "");
    btn.dataset.id = ds.id;
    btn.innerHTML = `
      <span class="nav-icon">${ICONS[ds.icon] || ICONS.table}</span>
      <span>
        <span class="nav-label">${escapeHtml(ds.label)}</span>
        <span class="nav-desc">${escapeHtml(ds.description || "")}</span>
      </span>`;
    btn.addEventListener("click", () => selectDataset(ds.id));
    return btn;
  }

  /**
   * Peint la barre latérale (logo fixe ; une scrollbar sur .sidebar-scroll) :
   * - All : brand + hotel + proximity + holidays + weather (parc global)
   * - Pilotes : sales, all_data, concept, model_data, …
   * - Modèles : Model Build / Explore (HTML)
   */
  function renderNav() {
    if (navPinnedTop) navPinnedTop.innerHTML = "";
    if (nav) nav.innerHTML = "";

    const pinned = [];
    const middle = [];
    state.datasets.forEach((ds) => {
      if (PINNED_TOP_IDS.includes(ds.id)) pinned.push(ds);
      else middle.push(ds);
    });
    // ordre All : brand → hotel → proximity → holidays → weather
    pinned.sort(
      (a, b) => PINNED_TOP_IDS.indexOf(a.id) - PINNED_TOP_IDS.indexOf(b.id)
    );

    pinned.forEach((ds) => {
      if (navPinnedTop) navPinnedTop.appendChild(makeNavButton(ds));
    });
    middle.forEach((ds) => {
      if (nav) nav.appendChild(makeNavButton(ds));
    });
  }

  /**
   * Change d'onglet (avec confirmation si modifications non sauvées).
   * Réinitialise page / filtre / dirty / sélection.
   */
  async function selectDataset(id, { keepPage = false } = {}) {
    if (state.dirty.size && state.currentId && state.currentId !== id) {
      const ok = confirm(
        "Des modifications non enregistrées seront perdues. Continuer ?"
      );
      if (!ok) return;
    }
    showTablePanel();
    if (state.currentId !== id) {
      state.dirty.clear();
      state.selected.clear();
      if (!keepPage) state.page = 1;
      state.q = "";
      searchInput.value = "";
    }
    state.currentId = id;
    // Bouton Reconstruire : sales, weather, proximity, holidays, all_data, model_data
    if (btnRebuild) {
      const rebuildTabs = new Set([
        "sales",
        "weather",
        "proximity",
        "holidays",
        "all_data",
        "data",
        "model_data",
        "concept_pilote",
      ]);
      btnRebuild.classList.toggle("hidden", !rebuildTabs.has(id));
      const titles = {
        sales:
          "Reconstruire hotel_sales_data depuis hotel_sales_raw_data (agrégats + mix %)",
        weather:
          "Recalculer météo (hôtels × années de ventes × mois terminés) → hotel_weather_data.xlsx",
        proximity:
          "Recalculer proximité Overpass pour chaque hôtel → hotel_proximity_data.xlsx",
        holidays:
          "Recalculer fériés + weekend + vacances (union exclusive) × hôtels × mois terminés",
        model_data: "Reconstruire model_data depuis all_data",
        concept_pilote:
          "Recalculer concept_pilote (hôtel × année : clients, CA moyen, mix produits)",
        all_data:
          "Jointure hôtels avec ventes (sales) + holidays/weather/brand/proximity → all_data.xlsx",
        data:
          "Jointure hôtels avec ventes (sales) + holidays/weather/brand/proximity → all_data.xlsx",
      };
      btnRebuild.title = titles[id] || "Reconstruire";
    }
    // Lecture seule (sales, model_data, concept_pilote) : masquer add/save/delete
    const ro =
      state.datasets.find((d) => d.id === id)?.readonly ||
      id === "sales" ||
      id === "concept_pilote";
    if ($("#btn-add")) $("#btn-add").classList.toggle("hidden", !!ro);
    if ($("#btn-save")) $("#btn-save").classList.toggle("hidden", !!ro);
    if ($("#btn-delete")) $("#btn-delete").classList.toggle("hidden", !!ro);
    renderNav();
    setModelNavActive(null);
    await fetchPage();
  }

  function setModelNavActive(which) {
    if (navModelBuild) navModelBuild.classList.toggle("active", which === "build");
    if (navModelExplore) navModelExplore.classList.toggle("active", which === "explore");
  }

  function hideAllViews() {
    if (viewTable) viewTable.classList.add("hidden");
    if (viewModelBuild) viewModelBuild.classList.add("hidden");
    if (viewModelExplore) viewModelExplore.classList.add("hidden");
  }

  function showTablePanel() {
    state.panel = "table";
    hideAllViews();
    if (viewTable) viewTable.classList.remove("hidden");
  }

  /** Retire l'état active de tous les onglets datasets (haut + milieu). */
  function clearDatasetNavActive() {
    document
      .querySelectorAll(".sidebar .nav-item[data-id]")
      .forEach((el) => el.classList.remove("active"));
  }

  function showModelBuildPanel() {
    state.panel = "model-build";
    hideAllViews();
    if (viewModelBuild) viewModelBuild.classList.remove("hidden");
    clearDatasetNavActive();
    setModelNavActive("build");
  }

  function showModelExplorePanel() {
    state.panel = "model-explore";
    hideAllViews();
    if (viewModelExplore) viewModelExplore.classList.remove("hidden");
    clearDatasetNavActive();
    setModelNavActive("explore");
  }

  // -------------------------------------------------------------------------
  // Chargement d'une page + rendu table
  // -------------------------------------------------------------------------

  /** GET page courante et met à jour titre, chips, table, pager. */
  async function fetchPage({ silent = false } = {}) {
    if (!state.currentId) return;
    const labels = loadingLabelsFor(state.currentId);
    if (!silent) {
      showLoading(labels.title, labels.sub);
      // feedback immédiat dans le tableau
      if (tbody) {
        tbody.innerHTML = `<tr><td class="empty-state empty-loading">Chargement de <strong>${escapeHtml(
          labels.title.replace(/^Chargement · /, "")
        )}</strong>…</td></tr>`;
      }
    }
    setStatus("Chargement…");
    try {
      const qs = new URLSearchParams({
        page: String(state.page),
        page_size: String(state.pageSize),
      });
      if (state.q) qs.set("q", state.q);
      const payload = await api(`/api/datasets/${state.currentId}?${qs}`);
      state.payload = payload;
      title.textContent = payload.label;
      desc.textContent = payload.description || "";
      chipFile.textContent = payload.filename;
      chipStats.textContent = `${payload.total_rows} lignes · page ${payload.page}/${payload.total_pages}`;
      renderTable(payload);
      pagerInfo.textContent = `Page ${payload.page} / ${payload.total_pages} · ${payload.total_rows} lignes`;
      setStatus("");
      setDirtyUI();
      updateDeleteBtn();
    } catch (err) {
      tbody.innerHTML = `<tr><td class="empty-state">Erreur : ${escapeHtml(err.message)}</td></tr>`;
      setStatus(err.message);
      toast(err.message, "err");
    } finally {
      if (!silent) hideLoading();
    }
  }

  /**
   * Construit l'en-tête + le corps de la table.
   * Chaque cellule = <input> lié à row._index + nom de colonne.
   * Les valeurs dirty locales ont priorité sur le payload serveur.
   */
  function renderModelDataStats(payload) {
    const host = $("#model-data-stats");
    if (!host) return;
    const st = payload.model_stats || {};
    if (payload.dataset_id !== "model_data" || !st.n_target) {
      host.classList.add("hidden");
      host.innerHTML = "";
      return;
    }
    host.classList.remove("hidden");
    host.innerHTML = `
      <span class="stat-chip id">ID / détail · ${st.n_id_detail ?? "—"}</span>
      <span class="stat-chip desc">Descriptives · ${st.n_descriptive ?? "—"}</span>
      <span class="stat-chip target">Cibles · ${st.n_target ?? "—"}</span>
      <span class="stat-chip train">Train · ${st.n_train ?? "—"} lignes</span>
      <span class="stat-chip eval">Éval ${st.eval_year ?? ""} · ${st.n_eval ?? "—"} lignes</span>
      <span class="stat-chip">Cible principale · ${escapeHtml(st.main_target || "montant_ventes")}</span>
    `;
  }

  function logoUrlFromPath(relpath) {
    if (!relpath) return "";
    let s = String(relpath).trim().replace(/\\/g, "/");
    if (!s || s === "nan" || s === "None" || s === "null") return "";
    // déjà une URL
    if (/^https?:\/\//i.test(s) || s.startsWith("/api/")) return s;
    // normalise préfixes éventuels (Excel / sync)
    s = s.replace(/^\/+/, "");
    s = s.replace(/^\.\/+/, "");
    s = s.replace(/^data\/marques\//i, "");
    s = s.replace(/^marques\//i, "");
    // encode chaque segment (espaces, accents) — garde les /
    const encoded = s
      .split("/")
      .filter(Boolean)
      .map((seg) => encodeURIComponent(seg))
      .join("/");
    // relatif à l'origine de run_admin (même host:port)
    return `/api/marques/logos/${encoded}`;
  }

  function renderTable(payload) {
    const cols = payload.columns || [];
    const keys = new Set(payload.key_columns || []);
    const bools = new Set(payload.boolean_columns || []);
    const arrays = new Set(payload.array_columns || []);
    const images = new Set(payload.image_columns || []);
    const roles = payload.column_roles || {};
    const readonly = !!payload.readonly;

    renderModelDataStats(payload);

    // --- En-tête ---
    thead.innerHTML = "";
    const hr = document.createElement("tr");
    hr.innerHTML = `<th class="cell-check"><input type="checkbox" id="check-all" title="Tout sélectionner (page)" /></th>`;
    cols.forEach((c) => {
      const th = document.createElement("th");
      if (keys.has(c)) th.classList.add("key-col");
      const role = roles[c];
      if (role === "id_detail") th.classList.add("col-id-detail", "key-col");
      else if (role === "target") th.classList.add("col-target");
      else if (role === "descriptive") th.classList.add("col-descriptive");
      // UI : logo_path → libellé « Logo » (le fichier Excel garde logo_path)
      const label = images.has(c) && (c === "logo_path" || c.endsWith("_path"))
        ? "Logo"
        : c;
      th.innerHTML = `<span class="col-label" title="${escapeHtml(c)}">${escapeHtml(label)}</span>`;
      hr.appendChild(th);
    });
    thead.appendChild(hr);

    // Case « tout sélectionner » = uniquement les lignes de la page visible
    const checkAll = thead.querySelector("#check-all");
    if (checkAll) {
      checkAll.addEventListener("change", () => {
        payload.rows.forEach((r) => {
          if (checkAll.checked) state.selected.add(r._index);
          else state.selected.delete(r._index);
        });
        renderTable(payload);
        updateDeleteBtn();
      });
    }

    // --- Corps ---
    tbody.innerHTML = "";
    if (!payload.rows.length) {
      tbody.innerHTML = `<tr><td class="empty-state" colspan="${cols.length + 1}">Aucune ligne sur cette page.</td></tr>`;
      return;
    }

    payload.rows.forEach((row) => {
      const tr = document.createElement("tr");
      // Overlay des modifications locales non encore sauvées
      const dirtyRow = state.dirty.get(row._index);
      const data = dirtyRow || row;
      if (dirtyRow) tr.classList.add("dirty");
      if (state.selected.has(row._index)) tr.classList.add("selected");
      if (row._is_eval) tr.classList.add("eval-row");

      // Checkbox de sélection (suppression en lot)
      const tdCheck = document.createElement("td");
      tdCheck.className = "cell-check";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = state.selected.has(row._index);
      cb.addEventListener("change", () => {
        if (cb.checked) state.selected.add(row._index);
        else state.selected.delete(row._index);
        tr.classList.toggle("selected", cb.checked);
        updateDeleteBtn();
      });
      tdCheck.appendChild(cb);
      tr.appendChild(tdCheck);

      // Une cellule éditable par colonne
      cols.forEach((col) => {
        const td = document.createElement("td");
        let val = data[col];
        if (Array.isArray(val)) val = JSON.stringify(val);
        if (val === null || val === undefined) val = "";

        // Colonnes image : afficher uniquement le logo (chemin gardé en data, pas en UI)
        if (images.has(col)) {
          td.className = "cell-logo";
          const wrap = document.createElement("div");
          wrap.className = "logo-cell";
          wrap.dataset.index = String(row._index);
          wrap.dataset.col = col;
          wrap.dataset.logoPath = String(val); // chemin Excel, non affiché
          const brandName = String(data.Marque || data.marque || "");
          const src = logoUrlFromPath(val);
          if (src) {
            const img = document.createElement("img");
            img.className = "brand-logo-thumb";
            img.src = src;
            img.alt = brandName || "logo";
            img.title = brandName || "Logo";
            img.loading = "lazy";
            img.onerror = () => {
              img.remove();
              const miss = document.createElement("span");
              miss.className = "logo-missing";
              miss.textContent = "—";
              miss.title = "Logo introuvable";
              wrap.appendChild(miss);
            };
            wrap.appendChild(img);
          } else {
            const miss = document.createElement("span");
            miss.className = "logo-missing";
            miss.textContent = "—";
            miss.title = "Pas de logo";
            wrap.appendChild(miss);
          }
          td.appendChild(wrap);
          tr.appendChild(td);
          return;
        }

        const input = document.createElement("input");
        input.className = "cell-input";
        if (keys.has(col)) input.classList.add("key");
        if (bools.has(col)) input.classList.add("bool");
        if (arrays.has(col)) input.classList.add("array");

        input.value = String(val);
        input.dataset.index = String(row._index);
        input.dataset.col = col;
        input.title = col;

        // Booléens : 0 ou 1 uniquement
        if (bools.has(col)) {
          input.type = "number";
          input.min = "0";
          input.max = "1";
          input.step = "1";
          input.placeholder = "0/1";
        }

        if (readonly) {
          input.readOnly = true;
          input.classList.add("readonly");
        } else {
          input.addEventListener("input", () => onCellEdit(row, col, input.value, payload));
          input.addEventListener("change", () => onCellEdit(row, col, input.value, payload));
        }
        td.appendChild(input);
        tr.appendChild(td);
      });

      tbody.appendChild(tr);
    });
  }

  /**
   * Enregistre une modification locale dans state.dirty.
   * On seed toute la ligne (valeurs page) pour que le PUT envoie un snapshot cohérent.
   */
  function onCellEdit(baseRow, col, value, payload) {
    const idx = baseRow._index;
    let row = state.dirty.get(idx);
    if (!row) {
      row = { _index: idx };
      // Copie des valeurs actuelles de la page comme base
      payload.columns.forEach((c) => {
        row[c] = baseRow[c];
      });
      state.dirty.set(idx, row);
    }
    // Typage léger côté client (le serveur re-coerce aussi)
    if ((payload.boolean_columns || []).includes(col)) {
      const n = Number(value);
      row[col] = Number.isFinite(n) ? n : value;
    } else if ((payload.array_columns || []).includes(col)) {
      row[col] = value; // JSON string ou liste libre
    } else if (
      value !== "" &&
      !Number.isNaN(Number(value)) &&
      String(Number(value)) === String(value).trim()
    ) {
      row[col] = Number(value);
    } else {
      row[col] = value === "" ? null : value;
    }
    setDirtyUI();
    // Marque visuelle de la ligne
    const inputs = tbody.querySelectorAll(`input[data-index="${idx}"]`);
    inputs.forEach((el) => el.closest("tr")?.classList.add("dirty"));
  }

  function updateDeleteBtn() {
    btnDelete.disabled = state.selected.size === 0;
  }

  // -------------------------------------------------------------------------
  // Actions (save / add / delete / reload)
  // -------------------------------------------------------------------------

  /** Envoie toutes les lignes dirty au serveur (PUT) puis recharge la page. */
  async function saveDirty() {
    if (!state.dirty.size) return;
    const rows = Array.from(state.dirty.values());
    setStatus("Enregistrement…");
    btnSave.disabled = true;
    try {
      const res = await api(`/api/datasets/${state.currentId}/rows`, {
        method: "PUT",
        body: JSON.stringify({ rows }),
      });
      state.dirty.clear();
      setDirtyUI();
      toast(`Enregistré · ${res.updated} ligne(s) → ${res.saved_to.split("/").pop()}`);
      await fetchPage();
    } catch (err) {
      toast(err.message, "err");
      setDirtyUI();
    }
  }

  /** Ajoute une ligne vide et se place sur la dernière page. */
  async function addRow() {
    try {
      await api(`/api/datasets/${state.currentId}/rows`, {
        method: "POST",
        body: JSON.stringify({ values: {} }),
      });
      toast("Ligne ajoutée");
      if (state.payload) {
        const total = (state.payload.total_rows || 0) + 1;
        state.page = Math.max(1, Math.ceil(total / state.pageSize));
      }
      await fetchPage();
    } catch (err) {
      toast(err.message, "err");
    }
  }

  /** Supprime les lignes cochées (indices DataFrame). */
  async function deleteSelected() {
    if (!state.selected.size) return;
    if (!confirm(`Supprimer ${state.selected.size} ligne(s) ?`)) return;
    try {
      await api(`/api/datasets/${state.currentId}/rows`, {
        method: "DELETE",
        body: JSON.stringify({ indices: Array.from(state.selected) }),
      });
      state.selected.clear();
      state.dirty.clear();
      toast("Lignes supprimées");
      await fetchPage();
    } catch (err) {
      toast(err.message, "err");
    }
  }

  /** Recharge le fichier Excel depuis le disque (invalide le cache serveur). */
  async function reload() {
    if (state.dirty.size && !confirm("Recharger et perdre les modifications ?")) return;
    showLoading("Rechargement…", "Lecture du fichier Excel depuis le disque");
    try {
      await api(`/api/datasets/${state.currentId}/reload`, { method: "POST" });
      state.dirty.clear();
      state.selected.clear();
      toast("Fichier Excel rechargé");
      await fetchPage({ silent: true });
    } catch (err) {
      toast(err.message, "err");
    } finally {
      hideLoading();
    }
  }

  /**
   * Reconstruire All Data (jointure) ou Model Data (filtre ML).
   */
  async function rebuildJoin() {
    if (state.dirty.size && !confirm("Les modifications non sauvées seront perdues. Continuer ?")) {
      return;
    }
    const id = state.currentId;
    const rebuildMap = {
      sales: {
        url: "/api/datasets/sales/rebuild",
        body: {},
        msg: "Agrégation ventes brutes → hotel_sales_data…",
      },
      weather: {
        url: "/api/datasets/weather/rebuild",
        body: {},
        msg: "Calcul météo (peut prendre 1–2 min)…",
      },
      proximity: {
        url: "/api/datasets/proximity/rebuild",
        body: {},
        msg: "Calcul proximité Overpass (peut prendre 1–2 min)…",
      },
      holidays: {
        url: "/api/datasets/holidays/rebuild",
        body: {},
        msg: "Calcul holidays (weekend ∪ fériés ∪ vacances)…",
      },
      model_data: {
        url: "/api/datasets/model_data/rebuild",
        body: {},
        msg: "Reconstruction model_data…",
      },
      concept_pilote: {
        url: "/api/datasets/concept_pilote/rebuild",
        body: {},
        msg: "Calcul concept_pilote (clients, CA, mix produits)…",
      },
      all_data: {
        url: "/api/datasets/all_data/rebuild",
        body: { fill_weather: false, fill_proximity: false },
        msg: "Reconstruction all_data…",
      },
      data: {
        url: "/api/datasets/all_data/rebuild",
        body: { fill_weather: false, fill_proximity: false },
        msg: "Reconstruction all_data…",
      },
    };
    const cfg = rebuildMap[id];
    if (!cfg) {
      toast("Reconstruire non disponible sur cet onglet", "err");
      return;
    }
    setStatus(cfg.msg);
    if (btnRebuild) btnRebuild.disabled = true;
    showLoading("Reconstruction…", cfg.msg);
    try {
      const res = await api(cfg.url, {
        method: "POST",
        body: JSON.stringify(cfg.body || {}),
      });
      state.dirty.clear();
      state.selected.clear();
      toast(
        `Reconstruit · ${res.rows} lignes · ${
          res.n_columns || (res.columns || []).length
        } colonnes`
      );
      state.page = 1;
      // Recharge le Excel fraîchement écrit dans l'UI
      await api(`/api/datasets/${id}/reload`, { method: "POST" });
      await fetchPage({ silent: true }); // overlay déjà affiché
      setStatus("");
    } catch (err) {
      toast(err.message, "err");
      setStatus(err.message);
    } finally {
      hideLoading();
      if (btnRebuild) btnRebuild.disabled = false;
    }
  }

  /** Échappe le HTML pour éviter l'injection dans les labels / erreurs. */
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // -------------------------------------------------------------------------
  // Écouteurs UI
  // -------------------------------------------------------------------------
  $("#btn-save").addEventListener("click", saveDirty);
  $("#btn-add").addEventListener("click", addRow);
  $("#btn-delete").addEventListener("click", deleteSelected);
  $("#btn-reload").addEventListener("click", reload);
  if (btnRebuild) btnRebuild.addEventListener("click", rebuildJoin);

  // Pagination
  $("#btn-first").addEventListener("click", () => {
    state.page = 1;
    fetchPage();
  });
  $("#btn-prev").addEventListener("click", () => {
    state.page = Math.max(1, state.page - 1);
    fetchPage();
  });
  $("#btn-next").addEventListener("click", () => {
    if (!state.payload) return;
    state.page = Math.min(state.payload.total_pages, state.page + 1);
    fetchPage();
  });
  $("#btn-last").addEventListener("click", () => {
    if (!state.payload) return;
    state.page = state.payload.total_pages;
    fetchPage();
  });
  pageSizeSel.addEventListener("change", () => {
    state.pageSize = Number(pageSizeSel.value) || 25;
    state.page = 1;
    fetchPage();
  });

  // Recherche avec debounce (évite un GET à chaque frappe)
  let searchTimer;
  searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.q = searchInput.value.trim();
      state.page = 1;
      fetchPage();
    }, 280);
  });

  // Raccourci clavier : Ctrl/Cmd + S → enregistrer
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      if (state.panel === "table" && !btnSave.disabled) saveDirty();
    }
  });

  // -------------------------------------------------------------------------

  // -------------------------------------------------------------------------
  // Panneau Model Build (hyperparams + build&save design)
  // -------------------------------------------------------------------------

  async function openModelBuildPanel() {
    if (state.dirty.size) {
      const ok = confirm("Des modifications non enregistrées seront perdues. Continuer ?");
      if (!ok) return;
    }
    showModelBuildPanel();
    await loadModelConfig();
  }

  async function loadModelConfig() {
    const status = $("#model-status");
    if (status) status.textContent = "Chargement…";
    try {
      const cfg = await api("/api/model/config");
      state.modelConfig = cfg;
      renderModelConfig(cfg);
      if (status) status.textContent = "";
    } catch (err) {
      if (status) status.textContent = err.message;
      toast(err.message, "err");
    }
  }

  function renderModelConfig(cfg) {
    const chipSrc = $("#model-chip-source");
    const chipStats = $("#model-chip-stats");
    if (chipSrc) chipSrc.textContent = "source · model_data";
    if (chipStats) {
      chipStats.textContent = `train ${cfg.n_train ?? "—"} · éval ${cfg.n_eval ?? "—"} · ${cfg.n_features ?? "—"} feat · ${cfg.n_targets ?? "—"} cibles`;
    }
    const nameEl = $("#model-name");
    if (nameEl && cfg.model_name) nameEl.value = cfg.model_name;

    const pHost = $("#model-params");
    if (pHost) {
      pHost.innerHTML = "";
      const params = cfg.xgb_params || {};
      (cfg.param_schema || []).forEach((spec) => {
        const field = document.createElement("label");
        field.className = "field";
        const val = params[spec.name] != null ? params[spec.name] : "";
        field.innerHTML = `
          <span>${escapeHtml(spec.label || spec.name)}</span>
          <input type="number" data-param="${escapeHtml(spec.name)}"
            value="${escapeHtml(String(val))}"
            min="${spec.min != null ? spec.min : ""}"
            max="${spec.max != null ? spec.max : ""}"
            step="${spec.step != null ? spec.step : "any"}" />`;
        pHost.appendChild(field);
      });
    }
  }

  function getXgbParams() {
    const out = {};
    document.querySelectorAll("#model-params input[data-param]").forEach((el) => {
      const n = Number(el.value);
      out[el.dataset.param] = Number.isFinite(n) ? n : el.value;
    });
    return out;
  }

  async function buildModel() {
    const btn = $("#btn-model-build");
    const status = $("#model-status");
    const body = {
      model_name: ($("#model-name") && $("#model-name").value) || "xgb_sales",
      xgb_params: getXgbParams(),
    };
    if (btn) btn.disabled = true;
    if (status) status.textContent = "Apprentissage + sauvegarde design…";
    try {
      const res = await api("/api/model/build", {
        method: "POST",
        body: JSON.stringify(body),
      });
      const r2 =
        res.metrics_eval && res.metrics_eval.mean_r2 != null
          ? Number(res.metrics_eval.mean_r2).toFixed(3)
          : "—";
      toast(`Build OK · ${res.name} · R² éval ${r2} → design/${res.name}`);
      if (status) {
        status.textContent = `Sauvé · design/${res.name} · train ${res.n_train}/éval ${res.n_eval} · R² ${r2}`;
      }
      // recharger la config (nom + params du dernier modèle)
      await loadModelConfig();
    } catch (err) {
      toast(err.message, "err");
      if (status) status.textContent = err.message;
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  if (navModelBuild) navModelBuild.addEventListener("click", openModelBuildPanel);
  const btnModelBuild = $("#btn-model-build");
  if (btnModelBuild) btnModelBuild.addEventListener("click", buildModel);

  // -------------------------------------------------------------------------
  // Panneau Model Explore
  // -------------------------------------------------------------------------

  async function openModelExplorePanel() {
    if (state.dirty.size) {
      const ok = confirm("Des modifications non enregistrées seront perdues. Continuer ?");
      if (!ok) return;
    }
    showModelExplorePanel();
    await loadExploreModels();
  }

  async function loadExploreModels() {
    const status = $("#explore-status");
    if (status) status.textContent = "Chargement…";
    try {
      const data = await api("/api/model/list");
      state.explore.models = data.models || [];
      fillExploreModelSelect(state.explore.models, data.top_model);
      updateExploreBanner(data.last_trained, data.top_model);
      if (state.explore.models.length) {
        const sel = $("#explore-model-select");
        const id = (sel && sel.value) || state.explore.models[0].id;
        await loadExploreModel(id);
      } else {
        clearExploreUI();
        if (status) status.textContent = "Aucun modèle design — utilisez Model Build.";
      }
    } catch (err) {
      if (status) status.textContent = err.message;
      toast(err.message, "err");
    }
  }

  function updateExploreBanner(last, top) {
    const elL = $("#explore-chip-last");
    const elT = $("#explore-chip-top");
    if (elL) {
      elL.textContent = last
        ? `Dernier entraîné : ${last.name || last.id}`
        : "Dernier entraîné : —";
    }
    if (elT) {
      elT.textContent = top
        ? `Top model : #${top.rank} ${top.name || top.id}`
        : "Top model : —";
    }
  }

  function fillExploreModelSelect(models, top) {
    const sel = $("#explore-model-select");
    if (!sel) return;
    sel.innerHTML = "";
    if (!models.length) {
      sel.innerHTML = `<option value="">— aucun —</option>`;
      return;
    }
    models.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m.id || m.name;
      const r2 = m.score_r2 != null ? Number(m.score_r2).toFixed(3) : "—";
      opt.textContent = `#${m.rank} · ${m.name || m.id} · R² ${r2}`;
      sel.appendChild(opt);
    });
    if (top && (top.id || top.name)) {
      sel.value = top.id || top.name;
    }
  }

  function clearExploreUI() {
    ["explore-importance", "explore-tree-view", "explore-trees-table", "explore-main-metrics", "explore-global-metrics"].forEach((id) => {
      const el = $("#" + id);
      if (!el) return;
      el.innerHTML = "—";
      el.classList.add("empty");
    });
  }

  async function loadExploreModel(modelId) {
    if (!modelId) return;
    const status = $("#explore-status");
    if (status) status.textContent = `Chargement ${modelId}…`;
    // Reset immédiat de toutes les zones (évite d'afficher l'ancien modèle)
    clearExploreUI();
    state.explore.overview = null;
    state.explore.treeMetrics = null;
    try {
      const [overview, trees] = await Promise.all([
        api(`/api/model/${encodeURIComponent(modelId)}/explore`),
        api(`/api/model/${encodeURIComponent(modelId)}/trees`),
      ]);
      state.explore.overview = overview;
      state.explore.treeMetrics = trees;
      state.explore.currentId = modelId;

      updateExploreBanner(overview.last_trained, overview.top_model);
      const chipS = $("#explore-chip-stats");
      if (chipS) {
        chipS.textContent = `${overview.n_features} feat · ${overview.n_trees} arbres · rank #${overview.rank || "—"}`;
      }
      // 1) perf globale + cible principale
      renderMainMetrics(overview);
      // 2) feature importance
      renderImportanceBars(overview.global_feature_importance || []);
      // 3) table des arbres
      renderTreesTable(trees);
      // 4) slider + visualisation arbre #0 du modèle sélectionné
      const nTrees = Math.max(1, overview.n_trees || trees.n_trees || 1);
      const slider = $("#explore-tree-slider");
      if (slider) {
        slider.max = String(Math.max(0, nTrees - 1));
        slider.value = "0";
      }
      const lab = $("#explore-tree-label");
      if (lab) lab.textContent = "0";
      await loadExploreTreeOnly(modelId, 0);
      if (status) status.textContent = "";
    } catch (err) {
      if (status) status.textContent = err.message;
      toast(err.message, "err");
      clearExploreUI();
    }
  }

  function renderMainMetrics(ov) {
    const host = $("#explore-main-metrics");
    const label = $("#explore-main-target-label");
    if (label) label.textContent = `${ov.main_target || "montant_ventes"} (évaluation)`;
    if (!host) return;
    const m = ov.main_target_metrics || {};
    const g = ov.metrics_eval || {};
    host.innerHTML = `
      <div class="metric-box good"><span class="m-label">R² ${escapeHtml(ov.main_target || "")}</span><span class="m-value">${fmt(m.r2)}</span></div>
      <div class="metric-box"><span class="m-label">RMSE</span><span class="m-value">${fmt(m.rmse)}</span></div>
      <div class="metric-box"><span class="m-label">MAE</span><span class="m-value">${fmt(m.mae)}</span></div>
      <div class="metric-box"><span class="m-label">R² moy. multi-cibles</span><span class="m-value">${fmt(g.mean_r2)}</span></div>
    `;
    const gm = $("#explore-global-metrics");
    if (gm) {
      gm.innerHTML = `
        <div class="metric-box"><span class="m-label">Train lignes</span><span class="m-value">${ov.n_train ?? "—"}</span></div>
        <div class="metric-box"><span class="m-label">Éval lignes</span><span class="m-value">${ov.n_eval ?? "—"}</span></div>
        <div class="metric-box"><span class="m-label">Année éval</span><span class="m-value">${ov.eval_year ?? "—"}</span></div>
      `;
    }
  }

  function renderImportanceBars(items) {
    const host = $("#explore-importance");
    if (!host) return;
    if (!items || !items.length) {
      host.className = "imp-bars empty";
      host.textContent = "Pas d’importance disponible.";
      return;
    }
    const max = Math.max(...items.map((x) => Number(x.importance) || 0), 1e-12);
    host.className = "imp-bars";
    host.innerHTML = items
      .slice(0, 30)
      .map((x) => {
        const v = Number(x.importance) || 0;
        const pct = Math.max(2, (v / max) * 100);
        return `<div class="imp-row">
          <span class="imp-name" title="${escapeHtml(x.feature)}">${escapeHtml(x.feature)}</span>
          <span class="imp-val">${v.toFixed(4)}</span>
          <div class="imp-bar-track"><div class="imp-bar-fill" style="width:${pct}%"></div></div>
        </div>`;
      })
      .join("");
  }

  function renderTreesTable(data) {
    const host = $("#explore-trees-table");
    const note = $("#explore-trees-note");
    if (note && data.note) note.textContent = data.note;
    if (!host) return;
    const rows = data.trees || [];
    if (!rows.length) {
      host.innerHTML = `<div class="empty">${escapeHtml(data.note || "Aucun arbre")}</div>`;
      return;
    }
    host.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Arbre</th><th>Profondeur</th><th>n features</th>
            <th>R² cumulé</th><th>RMSE cumulé</th><th>MAE</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (s) => `<tr data-tree="${s.tree_index}">
                <td>#${s.tree_index}</td>
                <td>${s.depth}</td>
                <td>${s.n_features}</td>
                <td>${fmt(s.r2_cumulative)}</td>
                <td>${fmt(s.rmse_cumulative)}</td>
                <td>${fmt(s.mae_cumulative)}</td>
              </tr>`
            )
            .join("")}
          ${
            data.global
              ? `<tr><td><strong>Global</strong></td><td colspan="2">${data.n_trees} arbres</td>
              <td><strong>${fmt(data.global.r2)}</strong></td>
              <td><strong>${fmt(data.global.rmse)}</strong></td>
              <td><strong>${fmt(data.global.mae)}</strong></td></tr>`
              : ""
          }
        </tbody>
      </table>`;
    host.querySelectorAll("tr[data-tree]").forEach((tr) => {
      tr.addEventListener("click", () => {
        const slider = $("#explore-tree-slider");
        if (slider) {
          slider.value = tr.dataset.tree;
          loadExploreTreeOnly();
        }
      });
    });
  }

  async function loadExploreTreeOnly(forceModelId, forceTreeIdx) {
    const modelId =
      forceModelId ||
      (state.explore && state.explore.currentId) ||
      ($("#explore-model-select") && $("#explore-model-select").value);
    const slider = $("#explore-tree-slider");
    if (!modelId) return;
    const treeIdx =
      forceTreeIdx != null
        ? Number(forceTreeIdx)
        : Number((slider && slider.value) || 0);
    const lab = $("#explore-tree-label");
    if (lab) lab.textContent = String(treeIdx);
    if (slider && String(slider.value) !== String(treeIdx)) {
      slider.value = String(treeIdx);
    }
    const host = $("#explore-tree-view");
    if (host) {
      host.className = "tree-view empty";
      host.textContent = `Chargement arbre #${treeIdx}…`;
    }
    try {
      const tree = await api(
        `/api/model/${encodeURIComponent(modelId)}/tree?tree=${treeIdx}`
      );
      // garde-fou : ignorer si l'utilisateur a changé de modèle entre-temps
      if (state.explore.currentId && state.explore.currentId !== modelId) return;
      renderTreeView(tree);
      const meta = $("#explore-tree-meta");
      if (meta) {
        const rows = (state.explore.treeMetrics && state.explore.treeMetrics.trees) || [];
        let best = null;
        rows.forEach((r) => {
          if (r.tree_index <= treeIdx) best = r;
        });
        meta.textContent = best
          ? `Modèle ${modelId} · arbre #${treeIdx} · profondeur ${tree.depth} · ${tree.n_features} features · R² cumulé ${fmt(
              best.r2_cumulative
            )} · RMSE ${fmt(best.rmse_cumulative)} (cible ${tree.target_name})`
          : `Modèle ${modelId} · arbre #${treeIdx} · profondeur ${tree.depth} · ${tree.n_features} features · cible ${tree.target_name}`;
      }
      document.querySelectorAll("#explore-trees-table tr[data-tree]").forEach((tr) => {
        tr.classList.toggle("active", Number(tr.dataset.tree) === treeIdx);
      });
    } catch (err) {
      if (host) {
        host.className = "tree-view empty";
        host.textContent = err.message;
      }
      toast(err.message, "err");
    }
  }

  function layoutTree(node, depth = 0, xCounter = { n: 0 }) {
    if (!node) return null;
    if (node.is_leaf) {
      const x = xCounter.n++;
      return { ...node, x, y: depth, width: 1 };
    }
    const left = layoutTree(node.left, depth + 1, xCounter);
    const right = layoutTree(node.right, depth + 1, xCounter);
    const x =
      left && right ? (left.x + right.x) / 2 : left ? left.x : right ? right.x : xCounter.n++;
    return { ...node, x, y: depth, left, right };
  }

  function renderTreeView(payload) {
    const host = $("#explore-tree-view");
    if (!host) return;
    const laid = layoutTree(payload.tree);
    if (!laid) {
      host.className = "tree-view empty";
      host.textContent = "Arbre vide.";
      return;
    }
    const nodeW = 148;
    const nodeH = 42;
    const gapX = 24;
    const gapY = 70;
    let maxX = 0;
    let maxY = 0;
    function walk(n) {
      if (!n) return;
      maxX = Math.max(maxX, n.x);
      maxY = Math.max(maxY, n.y);
      walk(n.left);
      walk(n.right);
    }
    walk(laid);
    const width = Math.max(400, (maxX + 1) * (nodeW + gapX) + 40);
    const height = Math.max(200, (maxY + 1) * gapY + 60);
    function pos(n) {
      return {
        cx: 20 + n.x * (nodeW + gapX) + nodeW / 2,
        cy: 24 + n.y * gapY,
      };
    }
    const edges = [];
    const nodes = [];
    function collect(n, parent = null, side = null) {
      if (!n) return;
      const p = pos(n);
      if (parent) {
        const pp = pos(parent);
        edges.push({
          x1: pp.cx,
          y1: pp.cy + nodeH / 2,
          x2: p.cx,
          y2: p.cy - nodeH / 2,
          label: side,
        });
      }
      nodes.push({ n, p });
      collect(n.left, n, "oui (<)");
      collect(n.right, n, "non (≥)");
    }
    collect(laid);
    const edgeSvg = edges
      .map((e) => {
        const mx = (e.x1 + e.x2) / 2;
        const my = (e.y1 + e.y2) / 2;
        return `<path class="tree-edge" d="M${e.x1},${e.y1} C${e.x1},${my} ${e.x2},${my} ${e.x2},${e.y2}"/>
          <text class="tree-edge-label" x="${mx}" y="${my - 2}" text-anchor="middle">${escapeHtml(e.label || "")}</text>`;
      })
      .join("");
    const nodeSvg = nodes
      .map(({ n, p }) => {
        const cls = n.is_leaf ? "tree-node tree-node-leaf" : "tree-node tree-node-split";
        const label = n.is_leaf
          ? `leaf ${Number(n.value).toFixed(3)}`
          : truncate(n.feature || n.label || "?", 22);
        const sub = n.is_leaf
          ? n.cover != null
            ? `cover ${Number(n.cover).toFixed(0)}`
            : ""
          : `< ${Number(n.threshold).toFixed(4)}`;
        return `<g class="${cls}" transform="translate(${p.cx - nodeW / 2},${p.cy - nodeH / 2})">
          <rect width="${nodeW}" height="${nodeH}" rx="8"/>
          <text x="8" y="17">${escapeHtml(label)}</text>
          <text class="sub" x="8" y="33">${escapeHtml(sub)}</text>
        </g>`;
      })
      .join("");
    host.className = "tree-view";
    host.innerHTML = `<svg class="tree-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${edgeSvg}${nodeSvg}</svg>`;
  }

  function truncate(s, n) {
    const t = String(s);
    return t.length > n ? t.slice(0, n - 1) + "…" : t;
  }

  function fmt(v) {
    if (v == null || Number.isNaN(Number(v))) return "—";
    return Number(v).toFixed(3);
  }

  async function deployCurrentModel() {
    const sel = $("#explore-model-select");
    const name = sel && sel.value;
    if (!name) {
      toast("Aucun modèle sélectionné", "err");
      return;
    }
    try {
      const res = await api("/api/model/deploy", {
        method: "POST",
        body: JSON.stringify({ model_name: name }),
      });
      toast(`Deploy OK · ${res.deployed_from} → deploy/model`);
    } catch (err) {
      toast(err.message, "err");
    }
  }

  if (navModelExplore) navModelExplore.addEventListener("click", openModelExplorePanel);
  const btnExploreRefresh = $("#btn-explore-refresh");
  if (btnExploreRefresh) btnExploreRefresh.addEventListener("click", loadExploreModels);
  const btnExploreDeploy = $("#btn-explore-deploy");
  if (btnExploreDeploy) btnExploreDeploy.addEventListener("click", deployCurrentModel);
  const exploreModelSel = $("#explore-model-select");
  if (exploreModelSel) {
    exploreModelSel.addEventListener("change", () => {
      const id = exploreModelSel.value;
      // forcer le rechargement complet de toutes les zones
      loadExploreModel(id);
    });
  }
  const exploreSlider = $("#explore-tree-slider");
  if (exploreSlider) {
    exploreSlider.addEventListener("input", () => {
      const lab = $("#explore-tree-label");
      if (lab) lab.textContent = exploreSlider.value;
    });
    exploreSlider.addEventListener("change", () => loadExploreTreeOnly());
  }

  // Démarrage
  loadDatasets().catch((err) => toast(err.message, "err"));
})();
