/**
 * Autocomplete hotels (code / nom).
 */

import { $, $$, escapeHtml, debounce } from "../../../shared/js/dom.js";
import { api } from "../../../shared/js/api.js";

export class HotelAutocomplete {
  /**
   * @param {(hotel: object) => void} onPick
   */
  constructor(onPick) {
    this.onPick = onPick;
    this._active = { code: -1, name: -1 };
  }

  hide(listId) {
    const list = $("#" + listId);
    if (list) {
      list.classList.add("hidden");
      list.innerHTML = "";
    }
  }

  hideAll() {
    this.hide("ac-hotel-code");
    this.hide("ac-hotel-name");
  }

  async search(q) {
    q = String(q || "").trim();
    if (q.length < 1) return [];
    try {
      const data = await api.get("/api/hotels/search", { q, limit: 20 });
      return (data && data.hotels) || [];
    } catch {
      return [];
    }
  }

  renderList(listId, items, key) {
    const list = $("#" + listId);
    if (!list) return;
    if (!items || !items.length) {
      this.hide(listId);
      return;
    }
    list.classList.remove("hidden");
    list.innerHTML = items
      .map((h, i) => {
        const code = h.hotel_code || "";
        const name = h.hotel_name || "";
        const meta = [h.hotel_brand, h.hotel_city, h.hotel_code_postal]
          .filter(Boolean)
          .join(" · ");
        return (
          `<li role="option" data-idx="${i}"><span class="ac-code">${escapeHtml(code)}</span>` +
          escapeHtml(name) +
          (meta
            ? `<span class="ac-meta">${escapeHtml(meta)}</span>`
            : "") +
          "</li>"
        );
      })
      .join("");
    $$(`#${listId} li`).forEach((li) => {
      li.addEventListener("mousedown", (ev) => {
        ev.preventDefault();
        const idx = Number(li.getAttribute("data-idx"));
        if (items[idx]) this.onPick(items[idx]);
      });
    });
    this._active[key] = -1;
  }

  wireInput(inputId, listId, key) {
    const input = $("#" + inputId);
    if (!input) return;
    const runSearch = debounce(async () => {
      const q = input.value;
      if (!String(q || "").trim()) {
        this.hide(listId);
        return;
      }
      const items = await this.search(q);
      this.renderList(listId, items, key);
    }, 220);

    input.addEventListener("input", () => {
      if (!String(input.value || "").trim()) {
        this.hide(listId);
        return;
      }
      runSearch();
    });

    input.addEventListener("keydown", (ev) => {
      const list = $("#" + listId);
      if (!list || list.classList.contains("hidden")) return;
      const items = $$(`#${listId} li`);
      if (!items.length) return;
      if (ev.key === "ArrowDown") {
        ev.preventDefault();
        this._active[key] = Math.min(
          items.length - 1,
          (this._active[key] || -1) + 1
        );
        items.forEach((li, i) =>
          li.classList.toggle("active", i === this._active[key])
        );
      } else if (ev.key === "ArrowUp") {
        ev.preventDefault();
        this._active[key] = Math.max(0, (this._active[key] || 0) - 1);
        items.forEach((li, i) =>
          li.classList.toggle("active", i === this._active[key])
        );
      } else if (ev.key === "Enter" && this._active[key] >= 0) {
        ev.preventDefault();
        items[this._active[key]].dispatchEvent(new MouseEvent("mousedown"));
      } else if (ev.key === "Escape") {
        this.hide(listId);
      }
    });

    input.addEventListener("blur", () => {
      setTimeout(() => this.hide(listId), 180);
    });
  }

  wire() {
    this.wireInput("hotel_code", "ac-hotel-code", "code");
    this.wireInput("hotel_name", "ac-hotel-name", "name");
  }
}
