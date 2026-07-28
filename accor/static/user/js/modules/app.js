/**
 * Simulateur hôtel (interface directeur).
 *
 * Parcours en 4 étapes : hôtel → établissement → offre corner → résultats.
 * Les réglages restent en session : rien n'est enregistré en base.
 */

import { $, $$, escapeHtml, debounce } from "../../../shared/js/dom.js";
import { api } from "../../../shared/js/api.js";
import { toast } from "../../../shared/js/toast.js";

function fmt(v, d = 1) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("fr-FR", {
    maximumFractionDigits: d,
    minimumFractionDigits: 0,
  });
}

function euro(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return (
    Number(v).toLocaleString("fr-FR", {
      maximumFractionDigits: 0,
      minimumFractionDigits: 0,
    }) + " €"
  );
}

class DirectorApp {
  constructor() {
    this.meta = null;
    this.result = null;
    this.step = 1;
    this.hotel = null;
    this._searchTimer = null;
  }

  async init() {
    try {
      this.meta = await api.get("/api/rod/meta");
      this.renderNeeds(this.meta);
      const d = this.meta.defaults || {};
      this.setMLin(d.m_lin ?? 6);
      this.setMix(Math.round((d.mix_fb ?? 0.7) * 100));
    } catch (err) {
      toast.show(err.message, "err");
    }
    this.wire();
    this.goStep(1);
  }

  setStatus(msg) {
    const el = $("#dir-status");
    if (el) el.textContent = msg || "";
  }

  goStep(n) {
    this.step = n;
    $$(".wiz-panel").forEach((p) => {
      p.classList.toggle("is-active", Number(p.dataset.panel) === n);
    });
    $$(".wiz-step").forEach((btn) => {
      const s = Number(btn.dataset.step);
      btn.classList.toggle("is-active", s === n);
      btn.classList.toggle("is-done", s < n);
      // débloquer les étapes déjà atteintes
      if (s <= n || (s === 2 && this.hotel) || (s >= 3 && this.hotel)) {
        btn.disabled = s > 1 && !this.hotel && s !== 1;
      }
      if (s === 1) btn.disabled = false;
      if (s >= 2) btn.disabled = !this.hotel;
      if (s === 4) btn.disabled = !this.result;
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  wire() {
    const search = $("#hotel_search");
    search?.addEventListener(
      "input",
      debounce(() => this.onSearch(), 220)
    );
    search?.addEventListener("keydown", (e) => {
      if (e.key === "Escape") this.hideAc();
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".ac-wrap")) this.hideAc();
    });

    $("#btn-step1-next")?.addEventListener("click", () => {
      if (this.hotel) this.goStep(2);
    });
    $("#btn-step2-next")?.addEventListener("click", () => this.goStep(3));
    $("#btn-run-sim")?.addEventListener("click", () => this.runSim());

    $$("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const s = Number(btn.dataset.goto);
        if (s >= 1 && s <= 4) this.goStep(s);
      });
    });

    $$(".wiz-step").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.disabled) return;
        this.goStep(Number(btn.dataset.step));
      });
    });

    const syncM = () => {
      this.setMLin($("#m_lin")?.value || $("#m_lin_slider")?.value);
    };
    $("#m_lin_slider")?.addEventListener("input", () => {
      $("#m_lin").value = $("#m_lin_slider").value;
      syncM();
    });
    $("#m_lin")?.addEventListener("input", () => {
      $("#m_lin_slider").value = $("#m_lin").value;
      syncM();
    });

    const syncMix = () => {
      this.setMix($("#mix_fb")?.value || $("#mix_slider")?.value);
    };
    $("#mix_slider")?.addEventListener("input", () => {
      $("#mix_fb").value = $("#mix_slider").value;
      syncMix();
    });
    $("#mix_fb")?.addEventListener("input", () => {
      $("#mix_slider").value = $("#mix_fb").value;
      syncMix();
    });

    $("#needs-all-on")?.addEventListener("click", () => this.setAllNeeds(true));
    $("#needs-all-off")?.addEventListener("click", () => this.setAllNeeds(false));
  }

  async onSearch() {
    const q = ($("#hotel_search")?.value || "").trim();
    const list = $("#ac-hotels");
    if (!list) return;
    if (q.length < 2) {
      this.hideAc();
      return;
    }
    try {
      const res = await api.get("/api/hotels/search", { q, limit: 12 });
      const hotels = res.hotels || [];
      if (!hotels.length) {
        list.innerHTML = `<li class="ac-empty">Aucun hôtel trouvé</li>`;
        list.classList.remove("hidden");
        return;
      }
      list.innerHTML = hotels
        .map(
          (h) => `
        <li role="option" class="ac-item" data-code="${escapeHtml(h.hotel_code || "")}">
          <strong>${escapeHtml(h.hotel_code || "")}</strong>
          <span>${escapeHtml(h.hotel_name || "")}</span>
          <em>${escapeHtml(h.hotel_brand || h.hotel_city || "")}</em>
        </li>`
        )
        .join("");
      list.classList.remove("hidden");
      list.querySelectorAll(".ac-item").forEach((el) => {
        el.addEventListener("click", () => this.selectHotel(el.dataset.code));
      });
    } catch (err) {
      toast.show(err.message, "err");
    }
  }

  hideAc() {
    $("#ac-hotels")?.classList.add("hidden");
  }

  async selectHotel(code) {
    if (!code) return;
    this.hideAc();
    this.setStatus("Chargement de la fiche…");
    try {
      const ctx = await api.get(`/api/hotels/${encodeURIComponent(code)}/context`, {
        fetch: 1,
      });
      if (!ctx.ok && !ctx.identity && !ctx.hotel) {
        throw new Error(ctx.error || "Hôtel introuvable");
      }
      const id = ctx.identity || ctx.hotel || {};
      const op = ctx.operating || {};
      const services = ctx.services || {};
      this.hotel = {
        hotel_code: code,
        hotel_name: id.hotel_name || id.name || "",
        hotel_brand: id.hotel_brand || id.brand || "",
        hotel_city: id.hotel_city || id.city || "",
        nb_chambres: op.nb_chambres ?? id.hotel_nb_chambres,
        taux_occupation: op.taux_occupation ?? id.hotel_to_annuel,
        guests_per_chambre: op.guests_per_chambre ?? 1.7,
        has_vitrine: !!(
          services.lobby_fridge ||
          services.has_vitrine ||
          id.hotel_dispo_dans_lobby_vitrine_refrigeree
        ),
      };
      $("#hotel_code").value = code;
      $("#hotel_search").value = `${code} · ${this.hotel.hotel_name || ""}`.trim();
      this.fillHotelSummary();
      this.fillStep2();
      $("#btn-step1-next").disabled = false;
      this.setStatus("");
      this.goStep(2);
    } catch (err) {
      this.setStatus(err.message);
      toast.show(err.message, "err");
    }
  }

  fillHotelSummary() {
    const el = $("#hotel-summary");
    if (!el || !this.hotel) return;
    el.classList.remove("empty");
    el.innerHTML = `
      <strong>${escapeHtml(this.hotel.hotel_code)}</strong>
      ${escapeHtml(this.hotel.hotel_name || "")}
      <span class="muted">${escapeHtml(
        [this.hotel.hotel_brand, this.hotel.hotel_city].filter(Boolean).join(" · ")
      )}</span>`;
  }

  fillStep2() {
    if (!this.hotel) return;
    const line = $("#step2-hotel-line");
    if (line) {
      line.textContent = [
        this.hotel.hotel_code,
        this.hotel.hotel_name,
        this.hotel.hotel_brand,
      ]
        .filter(Boolean)
        .join(" · ");
    }
    if (this.hotel.nb_chambres != null)
      $("#nb_chambres").value = String(Math.round(Number(this.hotel.nb_chambres)));
    if (this.hotel.taux_occupation != null) {
      let to = Number(this.hotel.taux_occupation);
      if (to <= 1) to *= 100;
      $("#taux_occupation").value = String(Math.round(to * 10) / 10);
    }
    if (this.hotel.guests_per_chambre != null)
      $("#guests_per_chambre").value = String(
        Number(this.hotel.guests_per_chambre).toFixed(1)
      );
    $("#has_vitrine").checked = !!this.hotel.has_vitrine;
  }

  renderNeeds(meta) {
    const fill = (hostId, items) => {
      const host = $("#" + hostId);
      if (!host) return;
      host.innerHTML = (items || [])
        .map(
          (it) => `
        <label class="need-item">
          <span>${escapeHtml(it.label || it.id)}</span>
          <input type="checkbox" data-need="${escapeHtml(it.id)}" ${
            it.default !== false ? "checked" : ""
          } />
        </label>`
        )
        .join("");
    };
    fill("needs-fb", meta.client_needs_fb);
    fill("needs-nfb", meta.client_needs_nfb);
  }

  setAllNeeds(on) {
    $$("#needs-fb input[data-need], #needs-nfb input[data-need]").forEach((el) => {
      el.checked = !!on;
    });
  }

  setMLin(v) {
    const n = Number(v) || 6;
    if ($("#m_lin_slider")) $("#m_lin_slider").value = String(n);
    if ($("#m_lin")) $("#m_lin").value = String(n);
    if ($("#m-lin-val")) $("#m-lin-val").textContent = fmt(n, 1);
  }

  setMix(pct) {
    const p = Math.min(100, Math.max(0, Number(pct) || 0));
    if ($("#mix_slider")) $("#mix_slider").value = String(p);
    if ($("#mix_fb")) $("#mix_fb").value = String(p);
    if ($("#mix-val")) $("#mix-val").textContent = String(Math.round(p));
    if ($("#mix-nf-val")) $("#mix-nf-val").textContent = String(100 - Math.round(p));
  }

  collectNeeds() {
    const needs = {};
    $$("#needs-fb input[data-need], #needs-nfb input[data-need]").forEach((el) => {
      needs[el.dataset.need] = !!el.checked;
    });
    return needs;
  }

  collectBody() {
    const toRaw = $("#taux_occupation")?.value;
    let to = toRaw === "" || toRaw == null ? null : Number(toRaw);
    if (to != null && to > 1) to = to / 100;
    return {
      hotel_code: ($("#hotel_code")?.value || this.hotel?.hotel_code || "").trim(),
      hotel_name: this.hotel?.hotel_name || "",
      hotel_brand: this.hotel?.hotel_brand || "",
      nb_chambres: Number($("#nb_chambres")?.value) || null,
      taux_occupation: to,
      guests_per_chambre: Number($("#guests_per_chambre")?.value) || null,
      m_lin: Number($("#m_lin")?.value) || 6,
      mix_fb: (Number($("#mix_fb")?.value) || 70) / 100,
      has_vitrine: !!$("#has_vitrine")?.checked,
      client_needs: this.collectNeeds(),
    };
  }

  async runSim() {
    const body = this.collectBody();
    if (!body.hotel_code) {
      toast.show("Choisissez d'abord un hôtel", "err");
      this.goStep(1);
      return;
    }
    this.goStep(4);
    $("#dir-loading")?.classList.remove("hidden");
    $("#dir-results")?.classList.add("hidden");
    this.setStatus("Calcul en cours…");
    try {
      const data = await api.post("/api/rod/simulate", body);
      if (!data.ok) throw new Error(data.error || "La simulation n'a pas abouti");
      this.result = data;
      this.renderResults(data);
      $("#dir-loading")?.classList.add("hidden");
      $("#dir-results")?.classList.remove("hidden");
      this.setStatus(
        `${data.hotel?.hotel_code || body.hotel_code} · ${data.recommended_solution || "—"}`
      );
      // débloquer l'étape résultats dans le fil d'ariane
      const s4 = document.querySelector('.wiz-step[data-step="4"]');
      if (s4) s4.disabled = false;
    } catch (err) {
      this.setStatus(err.message);
      toast.show(err.message, "err");
      $("#dir-loading")?.classList.add("hidden");
    }
  }

  renderResults(data) {
    const reco = data.recommended_solution || "—";
    if ($("#dir-reco-name")) $("#dir-reco-name").textContent = reco;
    const h = data.hotel || {};
    if ($("#dir-hotel-line")) {
      $("#dir-hotel-line").textContent = [
        h.hotel_code,
        h.hotel_name,
        h.hotel_brand,
      ]
        .filter(Boolean)
        .join(" · ");
    }
    const reasons = (data.recommendation_reasons || []).join(" ");
    if ($("#dir-reco-why")) $("#dir-reco-why").textContent = reasons;

    const block = (data.by_solution || {})[reco] || {};
    const host = $("#dir-big-metrics");
    if (host) {
      host.innerHTML = `
        <div class="big-metric primary">
          <span class="bm-label">CA simulé / mois</span>
          <span class="bm-value">${euro(block.ca_simule_mensuel)}</span>
          <span class="bm-sub">estimation règles métier</span>
        </div>
        <div class="big-metric">
          <span class="bm-label">CA estimé par le modèle / mois</span>
          <span class="bm-value">${euro(block.ca_predit_mensuel)}</span>
          <span class="bm-sub">si un modèle est disponible</span>
        </div>
        <div class="big-metric">
          <span class="bm-label">Coûts / mois</span>
          <span class="bm-value">${euro(block.cout_mensuel)}</span>
          <span class="bm-sub">capex ${euro(block.capex)}</span>
        </div>
        <div class="big-metric">
          <span class="bm-label">Marge nette / mois</span>
          <span class="bm-value ${
            Number(block.marge_nette_mensuelle) >= 0 ? "pos" : "neg"
          }">${euro(block.marge_nette_mensuelle)}</span>
          <span class="bm-sub">${euro(block.marge_nette_annuelle)} / an</span>
        </div>`;
    }

    if ($("#dir-ai-note")) $("#dir-ai-note").textContent = data.ai_note || "";
    if ($("#dir-disclaimer"))
      $("#dir-disclaimer").textContent = data.disclaimer || "";

    const cards = $("#dir-concept-cards");
    if (cards) {
      cards.innerHTML = ["SIMPLY", "LIBERTY", "CONNECTED"]
        .map((c) => {
          const b = (data.by_solution || {})[c] || {};
          const isReco = c === reco;
          return `
          <article class="concept-card ${isReco ? "recommended" : ""}">
            <header>
              <h3>${c}${isReco ? " · recommandée" : ""}</h3>
            </header>
            <div class="cc-row"><span>CA simulé / mois</span><strong>${euro(
              b.ca_simule_mensuel
            )}</strong></div>
            <div class="cc-row"><span>CA modèle / mois</span><strong>${euro(
              b.ca_predit_mensuel
            )}</strong></div>
            <div class="cc-row"><span>Coût / mois</span><strong>${euro(
              b.cout_mensuel
            )}</strong></div>
            <div class="cc-row"><span>Marge nette / mois</span><strong class="${
              Number(b.marge_nette_mensuelle) >= 0 ? "pos" : "neg"
            }">${euro(b.marge_nette_mensuelle)}</strong></div>
            <div class="cc-row"><span>Capex</span><strong>${euro(
              b.capex
            )}</strong></div>
          </article>`;
        })
        .join("");
    }
  }
}

const app = new DirectorApp();
app.init();
