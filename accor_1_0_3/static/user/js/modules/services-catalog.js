/**
 * Catalogue des services hôtel (flags alignés hotel_data).
 * Groupes F&B et non-F&B pour cases à cocher du wizard.
 */

export const SERVICES = {
  fb: [
    { id: "bar", label: "Bar" },
    { id: "restaurant", label: "Restaurant" },
    { id: "room_service", label: "Room service" },
    { id: "minibar", label: "Minibar" },
  ],
  nfb: [
    { id: "meeting_rooms", label: "Salles de reunion" },
    { id: "gym", label: "Salle de sport" },
    { id: "spa", label: "Spa" },
    { id: "pool", label: "Piscine" },
  ],
  comfort: [
    { id: "parking", label: "Parking" },
    { id: "wifi", label: "Wifi" },
    { id: "clim", label: "Climatisation" },
    { id: "breakfast", label: "Petit-dejeuner" },
    { id: "accessible", label: "Accessible PMR" },
    { id: "pets", label: "Animaux acceptes" },
    { id: "non_smoking", label: "Non-fumeur" },
    { id: "shuttle", label: "Navette" },
  ],
  lobby: [
    { id: "lobby_fridge", label: "Vitrine / frigo" },
    { id: "lobby_microwave", label: "Micro-ondes" },
    { id: "lobby_water", label: "Fontaine a eau" },
    { id: "lobby_coffee", label: "Machine a cafe" },
    { id: "lobby_kettle", label: "Bouilloire" },
    { id: "lobby_seating", label: "Assises" },
  ],
  corner: [
    { id: "corner_fb_caisse", label: "F&B · caisse code-barres" },
    { id: "corner_fb_distributeur", label: "F&B · distributeur auto" },
    { id: "corner_fb_frigo", label: "F&B · frigo connecte" },
    { id: "corner_fb_reception", label: "F&B · reception" },
    { id: "corner_fb_snacking", label: "F&B · snacking comptoir" },
    { id: "corner_nfb_armoire", label: "Non-F&B · armoire connectee" },
    { id: "corner_nfb_caisse", label: "Non-F&B · caisse code-barres" },
    { id: "corner_nfb_distributeur", label: "Non-F&B · distributeur auto" },
    { id: "corner_nfb_reception", label: "Non-F&B · reception" },
  ],
};

export function allServiceDefs() {
  return []
    .concat(SERVICES.fb)
    .concat(SERVICES.nfb)
    .concat(SERVICES.comfort)
    .concat(SERVICES.lobby)
    .concat(SERVICES.corner);
}

export class ServiceToggles {
  /**
   * @param {() => string} getHotelSource
   */
  constructor(getHotelSource) {
    this.getHotelSource = getHotelSource;
  }

  renderGroup(containerId, items, defaults = {}) {
    const root = document.getElementById(containerId);
    if (!root) return;
    root.innerHTML = items
      .map((it) => {
        let on = defaults[it.id] === true || defaults[it.id] === 1;
        if (defaults[it.id] === undefined && defaults.__defaultOn) on = true;
        return (
          '<label class="toggle-item"><span>' +
          escape(it.label) +
          '</span><span class="switch"><input type="checkbox" id="' +
          it.id +
          '" ' +
          (on ? "checked" : "") +
          " /><span></span></span></label>"
        );
      })
      .join("");
  }

  renderAll(serviceDefaults = {}) {
    this.renderGroup("svc-fb", SERVICES.fb, serviceDefaults);
    this.renderGroup("svc-nfb", SERVICES.nfb, serviceDefaults);
    this.renderGroup("svc-comfort", SERVICES.comfort, serviceDefaults);
    this.renderGroup("svc-lobby", SERVICES.lobby, serviceDefaults);
    this.renderGroup("svc-corner", SERVICES.corner, serviceDefaults);
    const hint = document.getElementById("svc-presource-hint");
    if (hint) {
      const src = this.getHotelSource();
      if (src) {
        hint.textContent =
          "Presaisie chargee pour " +
          src +
          " — cochez / decochez pour valider.";
      } else {
        hint.textContent =
          "Aucun hotel charge depuis la base : valeurs a saisir manuellement.";
      }
    }
  }
}

function escape(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
