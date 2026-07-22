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
    if (state.currentId !== id) {
      state.dirty.clear();
      state.selected.clear();
      if (!keepPage) state.page = 1;
      state.q = "";
      searchInput.value = "";
    }
    state.currentId = id;
    // Bouton rebuild visible uniquement sur l'onglet All Data
    if (btnRebuild) {
      btnRebuild.classList.toggle("hidden", id !== "data");
    }
    renderNav();
    await fetchPage();
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
      chipStats.textContent = `${payload.total_rows} lignes · page ${payload.page}/${payload.total_pages} · ${payload.columns.length} colonnes saisissables`;
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
   * Recalcule data.xlsx = All Data
   * grille hotel×année×mois + fill weather/proximity via lat/lon.
   */
  async function rebuildJoin() {
    if (state.dirty.size && !confirm("Les modifications non sauvées seront perdues. Continuer ?")) {
      return;
    }
    setStatus("Rebuild All Data (météo + proximité)…");
    try {
      const res = await api("/api/datasets/data/rebuild", { method: "POST" });
      state.dirty.clear();
      state.selected.clear();
      toast(`All Data OK · ${res.rows} lignes · ${res.n_columns} colonnes`);
      state.page = 1;
      await fetchPage();
    } catch (err) {
      toast(err.message, "err");
      setStatus(err.message);
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
      if (!btnSave.disabled) saveDirty();
    }
  });

  // Démarrage
  loadDatasets().catch((err) => toast(err.message, "err"));
})();
