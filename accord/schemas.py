"""
Schémas des jeux de données Accord.

Principe
--------
Chaque onglet de l'UI correspond à un fichier Excel sous ``accord/data/``.
On n'expose **que les colonnes saisissables** (``editable_columns``) :
les colonnes calculées (pourcentages, one-hot, agrégats dérivés, etc.)
restent dans le fichier mais ne sont ni affichées ni écrasées par l'UI
(le DataFrame complet est rechargé/sauvegardé côté ``store.py``).

Ajouter un onglet
-----------------
1. Placer le ``.xlsx`` dans ``data/``.
2. Déclarer un ``DatasetSchema`` dans ``DATASETS``.
3. Lister les colonnes éditables (et booléens / arrays si besoin).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Répertoire des Excel sources / cibles de sauvegarde
DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class DatasetSchema:
    """
    Description d'un onglet + fichier associé.

    Attributes
    ----------
    id :
        Identifiant URL / API (``brand``, ``hotel``, …).
    label / description :
        Textes affichés dans la barre latérale.
    filename / sheet :
        Fichier Excel et nom (ou index) de la feuille éditée.
    editable_columns :
        Ordre des colonnes dans la table UI (sous-ensemble du fichier).
    key_columns :
        Clés métier mises en avant (style doré dans l'UI).
    boolean_columns :
        Champs 0/1 (saisie numérique bornée côté front).
    array_columns :
        Listes (ex. dates ISO) sérialisées en JSON dans Excel.
    page_size :
        Taille de page par défaut pour la pagination.
    """

    id: str
    label: str
    description: str
    filename: str
    sheet: str | int = 0
    editable_columns: list[str] = field(default_factory=list)
    key_columns: list[str] = field(default_factory=list)
    boolean_columns: list[str] = field(default_factory=list)
    array_columns: list[str] = field(default_factory=list)
    icon: str = "table"
    page_size: int = 25

    @property
    def path(self) -> Path:
        """Chemin absolu du fichier Excel."""
        return DATA_DIR / self.filename


# =============================================================================
# Listes de colonnes éditables par dataset
# =============================================================================

# --- Brand : effectifs saisis ; les Pct_* du fichier sont calculés ailleurs ---
_BRAND_EDITABLE = [
    "Marque",
    "Nb_Hotels",
    "Nb_Ch_0_49",
    "Nb_Ch_50_99",
    "Nb_Ch_100_149",
    "Nb_Ch_150_199",
    "Nb_Ch_200_249",
    "Nb_Ch_250_299",
    "Nb_Ch_300_Plus",
    "Nb_Resto_0",
    "Nb_Resto_1",
    "Nb_Resto_2",
    "Nb_Resto_3",
    "Nb_Resto_Total",
    "Nb_Bar_0",
    "Nb_Bar_1",
    "Nb_Bar_2",
    "Nb_Bar_3",
    "Nb_Bar_Total",
]

# --- Hotel data : fiche directeur (one-hot brand exclus = dérivés de hotel_brand) ---
_HOTEL_EDITABLE = [
    "hotel_code",
    "hotel_name",
    "hotel_brand",
    "hotel_adresse_postale_1",
    "hotel_adresse_postale_2",
    "hotel_code_postal",
    "hotel_city",
    "hotel_lat",
    "hotel_lon",
    "hotel_contrat_signe_annee",
    "hotel_derniere_reno",
    "hotel_lobby_derniere_reno",
    "hotel_nb_chambres",
    "hotel_to_annuel",
    "hotel_to_le_plus_bas_taux",
    "hotel_to_le_plus_haut_taux",
    "hotel_dispo_dans_lobby_assises",
    "hotel_dispo_dans_lobby_bouilloire",
    "hotel_dispo_dans_lobby_fontaine_a_eau",
    "hotel_dispo_dans_lobby_machine_a_cafe",
    "hotel_dispo_dans_lobby_micro_ondes",
    "hotel_dispo_dans_lobby_vitrine_refrigeree",
    "hotel_f_b_bar",
    "hotel_f_b_minibar",
    "hotel_f_b_restaurant",
    "hotel_f_b_room_service",
    "hotel_non_f_b_piscine",
    "hotel_non_f_b_salle_de_sport",
    "hotel_non_f_b_salles_de_reunion",
    "hotel_non_f_b_spa",
    "hotel_affaires_pct",
    "hotel_loisirs_pct",
    "hotel_loisirs_top_1_amis",
    "hotel_loisirs_top_1_couples",
    "hotel_loisirs_top_1_familles",
    "hotel_international_pct",
    "hotel_national_pct",
    "hotel_corner_actuel_existe_deja",
    "hotel_corner_de_vente_actuel_metres_lineaires",
    "hotel_corner_actuel_offre_f_b_caisse_code_barres",
    "hotel_corner_actuel_offre_f_b_distributeur_auto",
    "hotel_corner_actuel_offre_f_b_frigo_connecte",
    "hotel_corner_actuel_offre_f_b_reception",
    "hotel_corner_actuel_offre_f_b_snacking_comptoir",
    "hotel_corner_actuel_offre_non_f_b_armoire_connectee",
    "hotel_corner_actuel_offre_non_f_b_caisse_code_barres",
    "hotel_corner_actuel_offre_non_f_b_distributeur_auto",
    "hotel_corner_actuel_offre_non_f_b_reception",
    "hotel_metres_lineaires_dedies_corner",
    "hotel_contrat_type_franchise",
    "hotel_contrat_type_manage",
]

# Champs binaires (0/1) — l'UI propose un input numérique 0–1
_HOTEL_BOOL = [
    "hotel_dispo_dans_lobby_assises",
    "hotel_dispo_dans_lobby_bouilloire",
    "hotel_dispo_dans_lobby_fontaine_a_eau",
    "hotel_dispo_dans_lobby_machine_a_cafe",
    "hotel_dispo_dans_lobby_micro_ondes",
    "hotel_dispo_dans_lobby_vitrine_refrigeree",
    "hotel_f_b_bar",
    "hotel_f_b_minibar",
    "hotel_f_b_restaurant",
    "hotel_f_b_room_service",
    "hotel_non_f_b_piscine",
    "hotel_non_f_b_salle_de_sport",
    "hotel_non_f_b_spa",
    "hotel_loisirs_top_1_amis",
    "hotel_loisirs_top_1_couples",
    "hotel_loisirs_top_1_familles",
    "hotel_corner_actuel_existe_deja",
    "hotel_corner_actuel_offre_f_b_caisse_code_barres",
    "hotel_corner_actuel_offre_f_b_distributeur_auto",
    "hotel_corner_actuel_offre_f_b_frigo_connecte",
    "hotel_corner_actuel_offre_f_b_reception",
    "hotel_corner_actuel_offre_f_b_snacking_comptoir",
    "hotel_corner_actuel_offre_non_f_b_armoire_connectee",
    "hotel_corner_actuel_offre_non_f_b_caisse_code_barres",
    "hotel_corner_actuel_offre_non_f_b_distributeur_auto",
    "hotel_corner_actuel_offre_non_f_b_reception",
    "hotel_contrat_type_franchise",
    "hotel_contrat_type_manage",
]

# --- Weather : clés + métriques météo (correction manuelle possible) ---
_WEATHER_EDITABLE = [
    "hotel_code",
    "hotel_name",
    "annee",
    "mois",
    "hotel_lat",
    "hotel_lon",
    "meteo_temperature_c_mean",
    "meteo_temperature_c_min",
    "meteo_temperature_c_max",
    "meteo_point_rosee_c_mean",
    "meteo_point_rosee_c_min",
    "meteo_point_rosee_c_max",
    "meteo_humidite_pct_mean",
    "meteo_humidite_pct_min",
    "meteo_humidite_pct_max",
    "meteo_precipitations_mm_mean",
    "meteo_precipitations_mm_min",
    "meteo_precipitations_mm_max",
    "meteo_neige_mm_mean",
    "meteo_neige_mm_min",
    "meteo_neige_mm_max",
    "meteo_vent_kmh_mean",
    "meteo_vent_kmh_min",
    "meteo_vent_kmh_max",
    "meteo_pression_hpa_mean",
    "meteo_pression_hpa_min",
    "meteo_pression_hpa_max",
    "meteo_ensoleillement_min_mean",
    "meteo_ensoleillement_min_min",
    "meteo_ensoleillement_min_max",
]

# --- Sales : uniquement la base mensuelle (pas cat_/heure_/weekend_ dérivés) ---
_SALES_EDITABLE = [
    "hotel_code",
    "nom_hotel",
    "annee",
    "mois",
    "nombre_ventes",
    "montant_ventes",
    "nombre_paniers",
    "nombre_produits",
]

# --- Holidays : compteurs + listes de jours (feuille resume_annuel non éditée) ---
_HOLIDAYS_EDITABLE = [
    "hotel_code",
    "hotel_name",
    "annee",
    "mois",
    "zone_scolaire",
    "departement",
    "commune",
    "nb_jours_feries",
    "nb_jours_vacances_scolaires",
    "nb_jours_vacances_hors_feries",
    "jours_feries",
    "jours_vacances_scolaires",
    "jours_vacances_hors_feries",
]


# =============================================================================
# Registre des onglets (ordre d'affichage = ordre d'insertion)
# =============================================================================

DATASETS: dict[str, DatasetSchema] = {
    "brand": DatasetSchema(
        id="brand",
        label="Hotel Brand Data",
        description="Parc par marque — effectifs par tranche de chambres, restos et bars",
        filename="hotel_brand_data.xlsx",
        sheet="Sheet1",
        editable_columns=_BRAND_EDITABLE,
        key_columns=["Marque"],
        icon="building",
        page_size=20,
    ),
    "hotel": DatasetSchema(
        id="hotel",
        label="Hotel Data",
        description="Fiche hôtel — identité, équipements, profil clients, corner",
        filename="hotel_data.xlsx",
        sheet="Sheet1",
        editable_columns=_HOTEL_EDITABLE,
        key_columns=["hotel_code", "hotel_name", "hotel_brand"],
        boolean_columns=_HOTEL_BOOL,
        icon="hotel",
        page_size=15,
    ),
    "weather": DatasetSchema(
        id="weather",
        label="Hotel Weather Data",
        description="Météo mensuelle par hôtel — température, pluie, vent…",
        filename="hotel_weather_data.xlsx",
        sheet="Sheet1",
        editable_columns=_WEATHER_EDITABLE,
        key_columns=["hotel_code", "annee", "mois"],
        icon="cloud",
        page_size=25,
    ),
    "sales": DatasetSchema(
        id="sales",
        label="Hotel Sales Data",
        description="Ventes mensuelles — quantités, montants, paniers (saisie base)",
        filename="hotel_sales_data.xlsx",
        sheet="hotel_sales",
        editable_columns=_SALES_EDITABLE,
        key_columns=["hotel_code", "nom_hotel", "annee", "mois"],
        icon="chart",
        page_size=25,
    ),
    "holidays": DatasetSchema(
        id="holidays",
        label="Hotel Holidays Data",
        description="Jours fériés & vacances scolaires par hôtel × mois",
        filename="hotel_holidays_data.xlsx",
        sheet="holidays_monthly",
        editable_columns=_HOLIDAYS_EDITABLE,
        key_columns=["hotel_code", "annee", "mois"],
        array_columns=[
            "jours_feries",
            "jours_vacances_scolaires",
            "jours_vacances_hors_feries",
        ],
        icon="calendar",
        page_size=25,
    ),
    # All Data : jointure complète (grille parfaite + fill météo/proximité)
    # id conservé "data" pour l'API / data.xlsx ; label UI = "All Data"
    "data": DatasetSchema(
        id="data",
        label="All Data",
        description=(
            "Jointure complète hotel × année × mois — "
            "identité + brand + weather + proximity + holidays + sales "
            "(seules les ventes peuvent rester vides)"
        ),
        filename="data.xlsx",
        sheet="data",
        editable_columns=[],  # toutes les colonnes du fichier
        key_columns=["hotel_code", "annee", "mois"],
        array_columns=[
            "jours_feries",
            "jours_vacances_scolaires",
            "jours_vacances_hors_feries",
        ],
        icon="table",
        page_size=25,
    ),
}




def list_datasets() -> list[dict[str, Any]]:
    """Sérialise tous les schémas pour l'API ``GET /api/datasets``."""
    return [
        {
            "id": d.id,
            "label": d.label,
            "description": d.description,
            "icon": d.icon,
            "filename": d.filename,
            "page_size": d.page_size,
            "editable_columns": d.editable_columns,
            "key_columns": d.key_columns,
            "boolean_columns": d.boolean_columns,
            "array_columns": d.array_columns,
        }
        for d in DATASETS.values()
    ]


def get_schema(dataset_id: str) -> DatasetSchema:
    """Retourne le schéma ou lève ``KeyError`` si l'id est inconnu."""
    if dataset_id not in DATASETS:
        raise KeyError(f"Dataset inconnu: {dataset_id}")
    return DATASETS[dataset_id]
