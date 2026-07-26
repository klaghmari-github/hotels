/** Constantes UI admin. */

export const PINNED_TOP_IDS = ["brand", "hotel", "proximity", "holidays", "weather"];

export const ICONS = {
  building: "🏛",
  hotel: "🛎",
  cloud: "☁",
  map: "📍",
  chart: "📈",
  calendar: "📅",
  table: "▦",
};

/**
 * Prod : boutons Reconstruire masques (logique API conservee).
 * Pour reafficher en admin avance, remettre les ids ici.
 */
export const REBUILD_TABS = new Set([]);
// Logique serveur intacte : sales, weather, proximity, holidays,
// all_data, model_data, concept_pilote via POST /api/datasets/<id>/rebuild

export const REBUILD_TITLES = {
  sales: "Reconstruire hotel_sales_data depuis hotel_sales_raw_data (agrégats + mix %)",
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
    "Base = mois de vente (sales), left join holidays/weather/hotel/proximity/brand → all_data.xlsx",
  data:
    "Base = mois de vente (sales), left join holidays/weather/hotel/proximity/brand → all_data.xlsx",
};

export const REBUILD_MAP = {
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

export const HEAVY_LOAD_SUB = {
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
