/**
 * Rendu table éditable + sélection lignes + marquage dirty.
 *
 * Colonnes image (logo), booléens 0/1, clés métier en style fort.
 * onEdit(row, col, value, payload) notifie DatasetController.
 */

import { $, escapeHtml } from "../../shared/js/dom.js";

export class TableRenderer {
  /**
   * @param {import('./state.js').AdminState} state
   * @param {object} els
   * @param {(baseRow: object, col: string, value: string, payload: object) => void} onEdit
   * @param {() => void} onSelectionChange
   */
  constructor(state, els, { onEdit, onSelectionChange }) {
    this.state = state;
    this.els = els;
    this.onEdit = onEdit;
    this.onSelectionChange = onSelectionChange;
  }

  logoUrlFromPath(relpath) {
    if (!relpath) return "";
    let s = String(relpath).trim().replace(/\\/g, "/");
    if (!s || s === "nan" || s === "None" || s === "null") return "";
    if (/^https?:\/\//i.test(s) || s.startsWith("/api/")) return s;
    s = s.replace(/^\/+/, "").replace(/^\.\/+/, "");
    s = s.replace(/^data\/marques\//i, "").replace(/^marques\//i, "");
    const encoded = s
      .split("/")
      .filter(Boolean)
      .map((seg) => encodeURIComponent(seg))
      .join("/");
    return `/api/marques/logos/${encoded}`;
  }

  renderModelDataStats(payload) {
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

  render(payload) {
    const { thead, tbody } = this.els;
    const cols = payload.columns || [];
    const keys = new Set(payload.key_columns || []);
    const bools = new Set(payload.boolean_columns || []);
    const arrays = new Set(payload.array_columns || []);
    const images = new Set(payload.image_columns || []);
    const roles = payload.column_roles || {};
    const readonly = !!payload.readonly;

    this.renderModelDataStats(payload);

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
      const label =
        images.has(c) && (c === "logo_path" || c.endsWith("_path")) ? "Logo" : c;
      th.innerHTML = `<span class="col-label" title="${escapeHtml(c)}">${escapeHtml(label)}</span>`;
      hr.appendChild(th);
    });
    thead.appendChild(hr);

    const checkAll = thead.querySelector("#check-all");
    if (checkAll) {
      checkAll.addEventListener("change", () => {
        payload.rows.forEach((r) => {
          if (checkAll.checked) this.state.selected.add(r._index);
          else this.state.selected.delete(r._index);
        });
        this.render(payload);
        this.onSelectionChange();
      });
    }

    tbody.innerHTML = "";
    if (!payload.rows.length) {
      tbody.innerHTML = `<tr><td class="empty-state" colspan="${cols.length + 1}">Aucune ligne sur cette page.</td></tr>`;
      return;
    }

    payload.rows.forEach((row) => {
      const tr = document.createElement("tr");
      const dirtyRow = this.state.dirty.get(row._index);
      const data = dirtyRow || row;
      if (dirtyRow) tr.classList.add("dirty");
      if (this.state.selected.has(row._index)) tr.classList.add("selected");
      if (row._is_eval) tr.classList.add("eval-row");

      const tdCheck = document.createElement("td");
      tdCheck.className = "cell-check";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = this.state.selected.has(row._index);
      cb.addEventListener("change", () => {
        if (cb.checked) this.state.selected.add(row._index);
        else this.state.selected.delete(row._index);
        tr.classList.toggle("selected", cb.checked);
        this.onSelectionChange();
      });
      tdCheck.appendChild(cb);
      tr.appendChild(tdCheck);

      cols.forEach((col) => {
        const td = document.createElement("td");
        let val = data[col];
        if (Array.isArray(val)) val = JSON.stringify(val);
        if (val === null || val === undefined) val = "";

        if (images.has(col)) {
          td.className = "cell-logo";
          const wrap = document.createElement("div");
          wrap.className = "logo-cell";
          wrap.dataset.index = String(row._index);
          wrap.dataset.col = col;
          wrap.dataset.logoPath = String(val);
          const brandName = String(data.Marque || data.marque || "");
          const src = this.logoUrlFromPath(val);
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
          const edit = () => this.onEdit(row, col, input.value, payload);
          input.addEventListener("input", edit);
          input.addEventListener("change", edit);
        }
        td.appendChild(input);
        tr.appendChild(td);
      });

      tbody.appendChild(tr);
    });
  }

  markRowDirty(idx) {
    const { tbody } = this.els;
    tbody
      .querySelectorAll(`input[data-index="${idx}"]`)
      .forEach((el) => el.closest("tr")?.classList.add("dirty"));
  }
}
