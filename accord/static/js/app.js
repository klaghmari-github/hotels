/**
 * Accord Data Studio — front-end
 * ==============================
 * Tables éditables paginées : les cellules modifiées sont gardées en mémoire
 * (state.dirty) puis envoyées au serveur (PUT) pour réécriture Excel.
 *
 * Architecture
 * ------------
 * - state     : état global UI (onglet, page, filtre, dirty, sélection)
 * - api()     : wrapper fetch JSON
 * - fetchPage : charge une page depuis /api/datasets/<id>
 * - renderTable : construit thead/tbody avec inputs WYSIWYG
 * - saveDirty : envoie toutes les lignes modifiées
 *
 * IIFE pour ne pas polluer le scope global.
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

  /** Peint la barre latérale (un bouton par dataset). */
  function renderNav() {
    nav.innerHTML = "";
    state.datasets.forEach((ds) => {
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
      nav.appendChild(btn);
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
    // Bouton Reconstruire visible uniquement sur l'onglet All Data
    if (btnRebuild) {
      btnRebuild.classList.toggle("hidden", id !== "all_data" && id !== "data");
    }
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

  function showModelBuildPanel() {
    state.panel = "model-build";
    hideAllViews();
    if (viewModelBuild) viewModelBuild.classList.remove("hidden");
    nav.querySelectorAll(".nav-item").forEach((el) => el.classList.remove("active"));
    setModelNavActive("build");
  }

  function showModelExplorePanel() {
    state.panel = "model-explore";
    hideAllViews();
    if (viewModelExplore) viewModelExplore.classList.remove("hidden");
    nav.querySelectorAll(".nav-item").forEach((el) => el.classList.remove("active"));
    setModelNavActive("explore");
  }

  // -------------------------------------------------------------------------
  // Chargement d'une page + rendu table
  // -------------------------------------------------------------------------

  /** GET page courante et met à jour titre, chips, table, pager. */
  async function fetchPage() {
    if (!state.currentId) return;
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
    }
  }

  /**
   * Construit l'en-tête + le corps de la table.
   * Chaque cellule = <input> lié à row._index + nom de colonne.
   * Les valeurs dirty locales ont priorité sur le payload serveur.
   */
  function renderTable(payload) {
    const cols = payload.columns || [];
    const keys = new Set(payload.key_columns || []);
    const bools = new Set(payload.boolean_columns || []);
    const arrays = new Set(payload.array_columns || []);

    // --- En-tête ---
    thead.innerHTML = "";
    const hr = document.createElement("tr");
    hr.innerHTML = `<th class="cell-check"><input type="checkbox" id="check-all" title="Tout sélectionner (page)" /></th>`;
    cols.forEach((c) => {
      const th = document.createElement("th");
      if (keys.has(c)) th.classList.add("key-col");
      th.innerHTML = `<span class="col-label" title="${escapeHtml(c)}">${escapeHtml(c)}</span>`;
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
        const input = document.createElement("input");
        input.className = "cell-input";
        if (keys.has(col)) input.classList.add("key");
        if (bools.has(col)) input.classList.add("bool");
        if (arrays.has(col)) input.classList.add("array");

        let val = data[col];
        // Arrays affichés en JSON pour l'édition libre
        if (Array.isArray(val)) val = JSON.stringify(val);
        if (val === null || val === undefined) val = "";
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

        input.addEventListener("input", () => onCellEdit(row, col, input.value, payload));
        input.addEventListener("change", () => onCellEdit(row, col, input.value, payload));
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
    try {
      await api(`/api/datasets/${state.currentId}/reload`, { method: "POST" });
      state.dirty.clear();
      state.selected.clear();
      toast("Fichier Excel rechargé");
      await fetchPage();
    } catch (err) {
      toast(err.message, "err");
    }
  }

  /**
   * Reconstruire : jointure de tous les onglets → all_data.xlsx → recharge UI.
   * Distinct de « Recharger » qui lit seulement le fichier existant.
   */
  async function rebuildJoin() {
    if (state.dirty.size && !confirm("Les modifications non sauvées seront perdues. Continuer ?")) {
      return;
    }
    setStatus("Reconstruction de la jointure (all_data.xlsx)…");
    if (btnRebuild) btnRebuild.disabled = true;
    try {
      const res = await api("/api/datasets/all_data/rebuild", {
        method: "POST",
        body: JSON.stringify({ fill_weather: false, fill_proximity: false }),
      });
      state.dirty.clear();
      state.selected.clear();
      toast(
        `Reconstruit · ${res.rows} lignes · ${res.n_columns} colonnes → ${
          (res.filename || "all_data.xlsx")
        }`
      );
      state.page = 1;
      // Recharger explicitement depuis le fichier fraîchement écrit
      await api(`/api/datasets/${state.currentId}/reload`, { method: "POST" });
      await fetchPage();
      setStatus("");
    } catch (err) {
      toast(err.message, "err");
      setStatus(err.message);
    } finally {
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
  // Panneau Model Build
  // -------------------------------------------------------------------------

  async function openModelBuildPanel() {
    if (state.dirty.size) {
      const ok = confirm(
        "Des modifications non enregistrées seront perdues. Continuer ?"
      );
      if (!ok) return;
    }
    showModelBuildPanel();
    await loadModelConfig();
  }

  async function loadModelConfig() {
    const source = ($("#model-source") && $("#model-source").value) || "data";
    const status = $("#model-status");
    if (status) status.textContent = "Chargement config…";
    try {
      const cfg = await api(`/api/model/config?source=${encodeURIComponent(source)}`);
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
    if (chipSrc) chipSrc.textContent = `source · ${cfg.source}`;
    if (chipStats) {
      chipStats.textContent = `${cfg.n_rows} lignes · ${cfg.n_columns} colonnes`;
    }

    // Feature groups
    const fgHost = $("#model-feature-groups");
    if (fgHost) {
      fgHost.innerHTML = "";
      Object.entries(cfg.feature_groups || {}).forEach(([key, g]) => {
        const label = document.createElement("label");
        label.className = "check-item";
        label.innerHTML = `
          <input type="checkbox" data-fg="${escapeHtml(key)}" ${g.default ? "checked" : ""} />
          <span>
            <span class="ci-label">${escapeHtml(g.label)}</span>
            <span class="ci-meta">${escapeHtml(g.description || "")} · ${g.n_columns || 0} cols</span>
          </span>`;
        fgHost.appendChild(label);
      });
    }

    // Targets
    renderTargetChecks(cfg.default_targets || [], cfg.targets || []);

    // Params
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

    // Models list
    renderModelList(cfg.models || []);
  }

  function renderTargetChecks(selected, allTargets) {
    const host = $("#model-targets");
    if (!host) return;
    const sel = new Set(selected);
    // Priorité : défaut d'abord, puis volumes simples, puis le reste
    const preferred = ["nombre_ventes", "montant_ventes", "nombre_paniers", "nombre_produits"];
    const ordered = [
      ...preferred.filter((t) => allTargets.includes(t)),
      ...allTargets.filter((t) => !preferred.includes(t)),
    ];
    // Limite affichage pour ne pas saturer (les volumes dérivés sont nombreux)
    const show = ordered.slice(0, 80);
    host.innerHTML = "";
    show.forEach((t) => {
      const label = document.createElement("label");
      label.className = "check-item";
      label.innerHTML = `
        <input type="checkbox" data-target="${escapeHtml(t)}" ${sel.has(t) ? "checked" : ""} />
        <span class="ci-label">${escapeHtml(t)}</span>`;
      host.appendChild(label);
    });
    if (ordered.length > show.length) {
      const more = document.createElement("div");
      more.className = "ci-meta";
      more.style.padding = "0.35rem 0.55rem";
      more.textContent = `… et ${ordered.length - show.length} autres non listés (utilisez « Tous volumes » pour les cibles par défaut + cat_*)`;
      host.appendChild(more);
    }
    host.dataset.allTargets = JSON.stringify(ordered);
  }

  function getSelectedTargets() {
    return Array.from(document.querySelectorAll("#model-targets input[data-target]:checked")).map(
      (el) => el.dataset.target
    );
  }

  function getFeatureGroups() {
    const out = {};
    document.querySelectorAll("#model-feature-groups input[data-fg]").forEach((el) => {
      out[el.dataset.fg] = el.checked;
    });
    return out;
  }

  function getXgbParams() {
    const out = {};
    document.querySelectorAll("#model-params input[data-param]").forEach((el) => {
      const name = el.dataset.param;
      const raw = el.value;
      const n = Number(raw);
      out[name] = Number.isFinite(n) ? n : raw;
    });
    return out;
  }

  function renderModelList(models) {
    const host = $("#model-list");
    if (!host) return;
    if (!models.length) {
      host.className = "model-list empty";
      host.textContent = "Aucun modèle pour l’instant.";
      return;
    }
    host.className = "model-list";
    host.innerHTML = models
      .map((m) => {
        const r2 =
          m.metrics_test && m.metrics_test.mean_r2 != null
            ? Number(m.metrics_test.mean_r2).toFixed(3)
            : "—";
        const rmse =
          m.metrics_test && m.metrics_test.mean_rmse != null
            ? Number(m.metrics_test.mean_rmse).toFixed(2)
            : "—";
        return `<div class="model-card">
          <div class="mc-id">${escapeHtml(m.id || "")}</div>
          <div class="mc-meta">
            ${escapeHtml(m.created_at || "")} ·
            ${m.n_features || "?"} feat · ${m.n_targets || "?"} targets ·
            test R² ${r2} · RMSE ${rmse}
          </div>
        </div>`;
      })
      .join("");
  }

  function renderBuildResult(res) {
    const host = $("#model-result");
    if (!host) return;
    host.className = "model-result";
    const mt = res.metrics_test || {};
    const r2 = mt.mean_r2 != null ? Number(mt.mean_r2).toFixed(4) : "—";
    const rmse = mt.mean_rmse != null ? Number(mt.mean_rmse).toFixed(3) : "—";
    const mae = mt.mean_mae != null ? Number(mt.mean_mae).toFixed(3) : "—";
    const r2n = Number(mt.mean_r2);
    const r2Class = Number.isFinite(r2n) ? (r2n >= 0.5 ? "good" : r2n >= 0.2 ? "warn" : "") : "";

    const per = mt.per_target || {};
    const perRows = Object.entries(per)
      .map(
        ([name, m]) =>
          `<tr><td>${escapeHtml(name)}</td><td>${fmt(m.r2)}</td><td>${fmt(m.rmse)}</td><td>${fmt(m.mae)}</td></tr>`
      )
      .join("");

    const imp = (res.top_feature_importance || [])
      .map(
        (x) =>
          `<li><span>${escapeHtml(x.feature)}</span><span>${Number(x.importance).toFixed(4)}</span></li>`
      )
      .join("");

    host.innerHTML = `
      <div><strong>Modèle</strong> · <code>${escapeHtml(res.id)}</code></div>
      <div class="ci-meta" style="margin-top:0.25rem">
        ${res.n_rows_used} lignes · train ${res.n_train} / test ${res.n_test} ·
        ${res.n_features} features · ${res.n_targets} targets<br/>
        Sauvegardé : <code>${escapeHtml(res.path || "")}</code>
      </div>
      <div class="metrics-grid">
        <div class="metric-box ${r2Class}"><span class="m-label">R² test (moy.)</span><span class="m-value">${r2}</span></div>
        <div class="metric-box"><span class="m-label">RMSE test</span><span class="m-value">${rmse}</span></div>
        <div class="metric-box"><span class="m-label">MAE test</span><span class="m-value">${mae}</span></div>
      </div>
      <div style="overflow:auto;max-height:180px">
        <table class="data-table" style="min-width:100%;width:100%;font-size:0.78rem">
          <thead><tr><th>Target</th><th>R²</th><th>RMSE</th><th>MAE</th></tr></thead>
          <tbody>${perRows || "<tr><td colspan=4 class='empty-state'>—</td></tr>"}</tbody>
        </table>
      </div>
      <div style="margin-top:0.65rem;font-weight:600;font-size:0.8rem;color:var(--text-muted)">Top importances</div>
      <ul class="imp-list">${imp || "<li>—</li>"}</ul>
    `;
  }

  function fmt(v) {
    if (v == null || Number.isNaN(Number(v))) return "—";
    return Number(v).toFixed(3);
  }

  async function buildModel() {
    const btn = $("#btn-model-build");
    const status = $("#model-status");
    const body = {
      source: ($("#model-source") && $("#model-source").value) || "data",
      feature_groups: getFeatureGroups(),
      targets: getSelectedTargets(),
      xgb_params: getXgbParams(),
      test_size: Number(($("#model-test-size") && $("#model-test-size").value) || 0.2),
      model_name: ($("#model-name") && $("#model-name").value) || "xgb_sales",
    };
    if (!body.targets.length) {
      toast("Sélectionnez au moins une target", "err");
      return;
    }
    if (btn) btn.disabled = true;
    if (status) status.textContent = "Apprentissage en cours…";
    try {
      const res = await api("/api/model/build", {
        method: "POST",
        body: JSON.stringify(body),
      });
      renderBuildResult(res);
      toast(`Modèle OK · R² test ${(res.metrics_test && res.metrics_test.mean_r2 != null) ? Number(res.metrics_test.mean_r2).toFixed(3) : "—"}`);
      // Refresh list
      const list = await api("/api/model/list");
      renderModelList(list.models || []);
      if (status) status.textContent = `Sauvegardé · ${res.id}`;
    } catch (err) {
      toast(err.message, "err");
      if (status) status.textContent = err.message;
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  if (navModelBuild) navModelBuild.addEventListener("click", openModelBuildPanel);
  const btnModelRefresh = $("#btn-model-refresh");
  if (btnModelRefresh) btnModelRefresh.addEventListener("click", loadModelConfig);
  const btnModelBuild = $("#btn-model-build");
  if (btnModelBuild) btnModelBuild.addEventListener("click", buildModel);
  const modelSource = $("#model-source");
  if (modelSource) {
    modelSource.addEventListener("change", loadModelConfig);
  }
  const btnTDef = $("#btn-targets-default");
  if (btnTDef) {
    btnTDef.addEventListener("click", () => {
      const cfg = state.modelConfig;
      if (!cfg) return;
      renderTargetChecks(cfg.default_targets || [], cfg.targets || []);
    });
  }
  const btnTAll = $("#btn-targets-all");
  if (btnTAll) {
    btnTAll.addEventListener("click", () => {
      const cfg = state.modelConfig;
      if (!cfg) return;
      const all = (cfg.targets || []).filter(
        (t) =>
          ["nombre_ventes", "montant_ventes", "nombre_paniers", "nombre_produits"].includes(t) ||
          t.startsWith("cat_") ||
          t.startsWith("sous_cat_")
      );
      renderTargetChecks(all.slice(0, 40), cfg.targets || []);
    });
  }
  const btnTNone = $("#btn-targets-none");
  if (btnTNone) {
    btnTNone.addEventListener("click", () => {
      document.querySelectorAll("#model-targets input[data-target]").forEach((el) => {
        el.checked = false;
      });
    });
  }

  // -------------------------------------------------------------------------
  // Panneau Model Explore
  // -------------------------------------------------------------------------

  async function openModelExplorePanel() {
    if (state.dirty.size) {
      const ok = confirm(
        "Des modifications non enregistrées seront perdues. Continuer ?"
      );
      if (!ok) return;
    }
    showModelExplorePanel();
    await loadExploreModels();
  }

  async function loadExploreModels() {
    const status = $("#explore-status");
    if (status) status.textContent = "Chargement des modèles…";
    try {
      const data = await api("/api/model/list");
      state.explore.models = data.models || [];
      fillExploreModelSelect(state.explore.models);
      if (state.explore.models.length) {
        const sel = $("#explore-model-select");
        const id = (sel && sel.value) || state.explore.models[0].id;
        await loadExploreModel(id);
      } else {
        clearExploreUI();
        if (status) status.textContent = "Aucun modèle — utilisez Model Build d’abord.";
      }
    } catch (err) {
      if (status) status.textContent = err.message;
      toast(err.message, "err");
    }
  }

  function fillExploreModelSelect(models) {
    const sel = $("#explore-model-select");
    if (!sel) return;
    const prev = sel.value;
    sel.innerHTML = "";
    if (!models.length) {
      sel.innerHTML = `<option value="">— aucun —</option>`;
      return;
    }
    models.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m.id;
      const r2 =
        m.metrics_test && m.metrics_test.mean_r2 != null
          ? Number(m.metrics_test.mean_r2).toFixed(3)
          : "—";
      opt.textContent = `${m.id}  (R² ${r2})`;
      sel.appendChild(opt);
    });
    if (prev && models.some((m) => m.id === prev)) sel.value = prev;
  }

  function clearExploreUI() {
    const imp = $("#explore-importance");
    if (imp) {
      imp.className = "imp-bars empty";
      imp.textContent = "Aucun modèle…";
    }
    const tree = $("#explore-tree-view");
    if (tree) {
      tree.className = "tree-view empty";
      tree.textContent = "Aucun arbre à afficher.";
    }
    const chart = $("#explore-perf-chart");
    if (chart) {
      chart.className = "perf-chart empty";
      chart.textContent = "—";
    }
    const tbl = $("#explore-perf-table");
    if (tbl) tbl.innerHTML = "";
    const gm = $("#explore-global-metrics");
    if (gm) gm.innerHTML = "";
  }

  async function loadExploreModel(modelId) {
    if (!modelId) return;
    const status = $("#explore-status");
    if (status) status.textContent = "Analyse du modèle…";
    try {
      const overview = await api(`/api/model/${encodeURIComponent(modelId)}/explore`);
      state.explore.overview = overview;
      const chipM = $("#explore-chip-model");
      const chipS = $("#explore-chip-stats");
      if (chipM) chipM.textContent = overview.id;
      if (chipS) {
        chipS.textContent = `${overview.n_features} feat · ${overview.n_targets} targets · ${overview.n_train || "?"} train`;
      }
      fillExploreTargets(overview.targets || []);
      renderExploreGlobalMetrics(overview);
      renderImportanceBars(
        state.explore.impScope === "target"
          ? (overview.targets[0] && overview.targets[0].feature_importance) || []
          : overview.global_feature_importance || []
      );
      await refreshExploreTarget();
      if (status) status.textContent = "";
    } catch (err) {
      if (status) status.textContent = err.message;
      toast(err.message, "err");
    }
  }

  function fillExploreTargets(targets) {
    const sel = $("#explore-target-select");
    if (!sel) return;
    sel.innerHTML = "";
    targets.forEach((t) => {
      const opt = document.createElement("option");
      opt.value = String(t.index);
      opt.textContent = `${t.name}  (${t.n_trees} arbres)`;
      opt.dataset.nTrees = String(t.n_trees);
      sel.appendChild(opt);
    });
  }

  function renderExploreGlobalMetrics(overview) {
    const host = $("#explore-global-metrics");
    if (!host) return;
    const mt = overview.metrics_test || {};
    const boxes = [
      { label: "R² test", value: mt.mean_r2, cls: "good" },
      { label: "RMSE test", value: mt.mean_rmse, cls: "" },
      { label: "MAE test", value: mt.mean_mae, cls: "" },
    ];
    host.innerHTML = boxes
      .map((b) => {
        const v = b.value != null && Number.isFinite(Number(b.value)) ? Number(b.value).toFixed(3) : "—";
        return `<div class="metric-box ${b.cls}"><span class="m-label">${b.label}</span><span class="m-value">${v}</span></div>`;
      })
      .join("");
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

  async function refreshExploreTarget() {
    const modelId = $("#explore-model-select") && $("#explore-model-select").value;
    const targetSel = $("#explore-target-select");
    if (!modelId || !targetSel || !targetSel.value) return;
    const target = Number(targetSel.value) || 0;
    const opt = targetSel.selectedOptions[0];
    const nTrees = Number((opt && opt.dataset.nTrees) || 0);
    const slider = $("#explore-tree-slider");
    if (slider) {
      slider.max = String(Math.max(0, nTrees - 1));
      if (Number(slider.value) > nTrees - 1) slider.value = "0";
      const lab = $("#explore-tree-label");
      if (lab) lab.textContent = slider.value;
    }

    // Importance par target si mode target
    if (state.explore.impScope === "target" && state.explore.overview) {
      const t = (state.explore.overview.targets || []).find((x) => x.index === target);
      if (t) renderImportanceBars(t.feature_importance || []);
    }

    const status = $("#explore-status");
    if (status) status.textContent = "Calcul perfs arbres…";
    try {
      const [metrics, tree] = await Promise.all([
        api(
          `/api/model/${encodeURIComponent(modelId)}/tree-metrics?target=${target}`
        ),
        api(
          `/api/model/${encodeURIComponent(modelId)}/tree?target=${target}&tree=${
            (slider && slider.value) || 0
          }`
        ),
      ]);
      state.explore.treeMetrics = metrics;
      renderPerfChart(metrics);
      renderPerfTable(metrics, Number((slider && slider.value) || 0));
      renderTreeView(tree);
      if (status) status.textContent = "";
    } catch (err) {
      if (status) status.textContent = err.message;
      toast(err.message, "err");
    }
  }

  async function loadExploreTreeOnly() {
    const modelId = $("#explore-model-select") && $("#explore-model-select").value;
    const targetSel = $("#explore-target-select");
    const slider = $("#explore-tree-slider");
    if (!modelId || !targetSel) return;
    const target = Number(targetSel.value) || 0;
    const treeIdx = Number((slider && slider.value) || 0);
    const lab = $("#explore-tree-label");
    if (lab) lab.textContent = String(treeIdx);
    try {
      const tree = await api(
        `/api/model/${encodeURIComponent(modelId)}/tree?target=${target}&tree=${treeIdx}`
      );
      renderTreeView(tree);
      if (state.explore.treeMetrics) {
        renderPerfTable(state.explore.treeMetrics, treeIdx);
      }
    } catch (err) {
      toast(err.message, "err");
    }
  }

  function renderPerfChart(metrics) {
    const host = $("#explore-perf-chart");
    if (!host) return;
    const series = metrics.series || [];
    if (!series.length) {
      host.className = "perf-chart empty";
      host.textContent = "Pas de série de performance.";
      return;
    }
    host.className = "perf-chart";
    const w = 560;
    const h = 180;
    const pad = { t: 16, r: 16, b: 28, l: 44 };
    const iw = w - pad.l - pad.r;
    const ih = h - pad.t - pad.b;
    const xs = series.map((s) => s.n_trees_used);
    const r2s = series.map((s) => s.r2);
    const rmses = series.map((s) => s.rmse);
    const gR2 = metrics.global && metrics.global.r2;
    const gRmse = metrics.global && metrics.global.rmse;

    const xMin = Math.min(...xs);
    const xMax = Math.max(...xs);
    const r2Min = Math.min(...r2s, gR2 != null ? gR2 : 0, 0);
    const r2Max = Math.max(...r2s, gR2 != null ? gR2 : 1, 0.01);
    const rmseMin = Math.min(...rmses, gRmse != null ? gRmse : 0);
    const rmseMax = Math.max(...rmses, gRmse != null ? gRmse : 1, 0.01);

    const xScale = (x) => pad.l + ((x - xMin) / Math.max(xMax - xMin, 1)) * iw;
    const yR2 = (v) => pad.t + ih - ((v - r2Min) / Math.max(r2Max - r2Min, 1e-9)) * ih;
    const yRmse = (v) => pad.t + ih - ((v - rmseMin) / Math.max(rmseMax - rmseMin, 1e-9)) * ih;

    const pathR2 = series
      .map((s, i) => `${i === 0 ? "M" : "L"}${xScale(s.n_trees_used).toFixed(1)},${yR2(s.r2).toFixed(1)}`)
      .join(" ");
    const pathRmse = series
      .map(
        (s, i) =>
          `${i === 0 ? "M" : "L"}${xScale(s.n_trees_used).toFixed(1)},${yRmse(s.rmse).toFixed(1)}`
      )
      .join(" ");

    let globalLines = "";
    if (gR2 != null) {
      const y = yR2(gR2);
      globalLines += `<line x1="${pad.l}" y1="${y}" x2="${w - pad.r}" y2="${y}" stroke="#3ecf8e" stroke-dasharray="4 3" stroke-width="1.2"/>`;
    }
    if (gRmse != null) {
      const y = yRmse(gRmse);
      globalLines += `<line x1="${pad.l}" y1="${y}" x2="${w - pad.r}" y2="${y}" stroke="#f0b429" stroke-dasharray="2 3" stroke-width="1"/>`;
    }

    host.innerHTML = `
      <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
        <line x1="${pad.l}" y1="${pad.t}" x2="${pad.l}" y2="${h - pad.b}" stroke="rgba(255,255,255,0.1)"/>
        <line x1="${pad.l}" y1="${h - pad.b}" x2="${w - pad.r}" y2="${h - pad.b}" stroke="rgba(255,255,255,0.1)"/>
        ${globalLines}
        <path d="${pathRmse}" fill="none" stroke="#f0b429" stroke-width="1.5" opacity="0.7"/>
        <path d="${pathR2}" fill="none" stroke="#3d7eff" stroke-width="2"/>
        <text x="${pad.l}" y="12" fill="#8b97a8" font-size="10">R² ↑  /  RMSE ↓</text>
        <text x="${w - pad.r}" y="${h - 8}" fill="#8b97a8" font-size="10" text-anchor="end"># arbres</text>
      </svg>
      <div class="perf-legend">
        <span><i style="background:#3d7eff"></i> R² cumulé</span>
        <span><i style="background:#f0b429"></i> RMSE cumulé</span>
        <span><i style="background:#3ecf8e"></i> R² global</span>
        <span>global R² ${gR2 != null ? Number(gR2).toFixed(3) : "—"} · RMSE ${gRmse != null ? Number(gRmse).toFixed(2) : "—"}</span>
      </div>`;
  }

  function renderPerfTable(metrics, activeTree) {
    const host = $("#explore-perf-table");
    if (!host) return;
    const series = metrics.series || [];
    const g = metrics.global || {};
    // Show subset: first, last, and around active + every N
    const rows = series.filter((s, i) => {
      if (i === 0 || i === series.length - 1) return true;
      if (s.tree_index === activeTree) return true;
      return i % Math.max(1, Math.floor(series.length / 12)) === 0;
    });
    host.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Arbre</th><th>n</th><th>R²</th><th>RMSE</th><th>Δ R²→global</th><th>R²/global</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map((s) => {
              const act = s.tree_index === activeTree ? "active" : "";
              return `<tr class="${act}" data-tree="${s.tree_index}">
                <td>#${s.tree_index}</td>
                <td>${s.n_trees_used}</td>
                <td>${fmt(s.r2)}</td>
                <td>${fmt(s.rmse)}</td>
                <td>${fmt(s.r2_gap_to_global)}</td>
                <td>${s.r2_vs_global != null ? fmt(s.r2_vs_global) : "—"}</td>
              </tr>`;
            })
            .join("")}
          <tr>
            <td><strong>Global</strong></td>
            <td>${metrics.n_trees || "—"}</td>
            <td><strong>${fmt(g.r2)}</strong></td>
            <td><strong>${fmt(g.rmse)}</strong></td>
            <td>0</td>
            <td>1</td>
          </tr>
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

  /** Layout récursif d'un arbre JSON → positions pour SVG. */
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
    const title = $("#explore-tree-title");
    if (!host) return;
    if (title) {
      title.textContent = `· ${payload.target_name} · arbre #${payload.tree_index} / ${payload.n_trees - 1}`;
    }
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
      .map(
        (e) => {
          const mx = (e.x1 + e.x2) / 2;
          const my = (e.y1 + e.y2) / 2;
          return `<path class="tree-edge" d="M${e.x1},${e.y1} C${e.x1},${my} ${e.x2},${my} ${e.x2},${e.y2}"/>
            <text class="tree-edge-label" x="${mx}" y="${my - 2}" text-anchor="middle">${escapeHtml(e.label || "")}</text>`;
        }
      )
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

  if (navModelExplore) navModelExplore.addEventListener("click", openModelExplorePanel);
  const btnExploreRefresh = $("#btn-explore-refresh");
  if (btnExploreRefresh) btnExploreRefresh.addEventListener("click", loadExploreModels);

  const exploreModelSel = $("#explore-model-select");
  if (exploreModelSel) {
    exploreModelSel.addEventListener("change", () => loadExploreModel(exploreModelSel.value));
  }
  const exploreTargetSel = $("#explore-target-select");
  if (exploreTargetSel) {
    exploreTargetSel.addEventListener("change", refreshExploreTarget);
  }
  const exploreSlider = $("#explore-tree-slider");
  if (exploreSlider) {
    exploreSlider.addEventListener("input", () => {
      const lab = $("#explore-tree-label");
      if (lab) lab.textContent = exploreSlider.value;
    });
    exploreSlider.addEventListener("change", loadExploreTreeOnly);
  }
  const btnImpGlobal = $("#btn-imp-global");
  if (btnImpGlobal) {
    btnImpGlobal.addEventListener("click", () => {
      state.explore.impScope = "global";
      const ov = state.explore.overview;
      if (ov) renderImportanceBars(ov.global_feature_importance || []);
    });
  }
  const btnImpTarget = $("#btn-imp-target");
  if (btnImpTarget) {
    btnImpTarget.addEventListener("click", () => {
      state.explore.impScope = "target";
      const ov = state.explore.overview;
      const targetSel = $("#explore-target-select");
      if (!ov || !targetSel) return;
      const idx = Number(targetSel.value) || 0;
      const t = (ov.targets || []).find((x) => x.index === idx);
      renderImportanceBars((t && t.feature_importance) || []);
    });
  }

  // Démarrage
  loadDatasets().catch((err) => toast(err.message, "err"));
})();
