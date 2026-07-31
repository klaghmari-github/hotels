/**
 * Bouton géocode : POST /api/geocode (BAN → Accor → Nominatim).
 * Remplit lat/lon dans le formulaire si ok.
 */

import { $, fieldStr } from "../../../shared/js/dom.js";
import { api } from "../../../shared/js/api.js";
import { toast } from "../../../shared/js/toast.js";

export class GeocodePanel {
  setWaiting(on) {
    const btn = $("#btn-geocode");
    const status = $("#geocode-status");
    const hint = $("#geocode-hint");
    if (btn) {
      btn.classList.toggle("busy", !!on);
      btn.disabled = !!on;
      const label = btn.querySelector(".btn-label");
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

  async run() {
    const street = fieldStr("hotel_adresse_postale_1");
    const postal = fieldStr("hotel_code_postal");
    const city = fieldStr("hotel_city");
    const hotelName = fieldStr("hotel_name");
    const complement = fieldStr("hotel_adresse_postale_2");
    const hotelCode = fieldStr("hotel_code");
    const hint = $("#geocode-hint");

    const hasAccorHint =
      /all\.accor\.com\/hotel\//i.test(hotelCode) ||
      /^[Hh]?\d{3,5}$/.test(hotelCode);

    if (!street && !city && !hotelName && !postal && !hasAccorHint) {
      if (hint) {
        hint.textContent =
          "Renseignez une adresse, une ville, un nom d’hôtel, ou un code Accor (ex. 1545).";
        hint.style.color = "#991b1b";
      }
      toast.show("Adresse insuffisante pour localiser");
      return;
    }

    const body = {
      street: street || complement,
      postal_code: postal,
      city,
      hotel_name: hotelName,
      hotel_code: hotelCode,
      q: [street, complement, postal, city, hotelName, hotelCode]
        .filter(Boolean)
        .join(", "),
      accor_url: /all\.accor\.com/i.test(hotelCode) ? hotelCode : "",
    };

    this.setWaiting(true);
    toast.show("Veuillez patienter — localisation en cours…");

    try {
      const data = await api.post("/api/geocode", body);
      if (!data.ok) {
        throw new Error(data.error || "Aucun résultat pour cette adresse");
      }
      const latEl = $("#hotel_lat");
      const lonEl = $("#hotel_lon");
      if (latEl) latEl.value = Number(data.lat).toFixed(6);
      if (lonEl) lonEl.value = Number(data.lon).toFixed(6);
      if (data.address && !street) {
        const parts = String(data.address).split(",");
        if (parts[0] && $("#hotel_adresse_postale_1")) {
          $("#hotel_adresse_postale_1").value = parts[0].trim();
        }
      }
      if (data.hotel_name && !hotelName && $("#hotel_name")) {
        $("#hotel_name").value = data.hotel_name;
      }
      if (hint) {
        hint.style.color = "#14532d";
        const src = data.source ? " [" + data.source + "]" : "";
        hint.textContent =
          "✓ Position trouvée" +
          src +
          " : " +
          (data.display_name || data.lat + ", " + data.lon);
      }
      toast.show("Coordonnées trouvées");
    } catch (e) {
      if (hint) {
        hint.style.color = "#991b1b";
        hint.textContent = "✗ " + (e.message || String(e));
      }
      toast.show("Échec de la localisation");
    } finally {
      this.setWaiting(false);
    }
  }
}
