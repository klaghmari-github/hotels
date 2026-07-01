"""
Simulateur de CA pour coin de vente (corner retail) dans les hôtels Accor.

Fonctionnalités principales :
- Prend en entrée le nombre de mètres linéaires choisis
- Permet de filtrer les catégories (GAMME) autorisées (ex: exclure ALCOOL)
- Intègre les données de ventes historiques
- Ajuste avec POI (commerces de proximité)
- Ajuste avec saisonnalité (proxy via historique + option météo)
- Retourne CA mensuel estimé + CA annuel

Usage simple :
    from simulateur_corner import simulate_corner

    result = simulate_corner(
        hotel_name="Ibis budget Nice",
        m_lin=5.0,
        exclude_gammes=["ALCOOL"]
    )
    print(result)
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Optional, Dict, Tuple

# Chemins par défaut (à adapter si besoin)
DEFAULT_DATA_DIR = Path(".")

class CornerSimulator:
    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR):
        self.data_dir = Path(data_dir)
        self._load_data()

    def _load_data(self):
        """Charge les données préparées nécessaires."""
        # Ventes mensuelles par hôtel
        self.trans = pd.read_excel(self.data_dir / "transaction_prepared_data.xlsx")

        # Paramètres ROD
        self.rod = pd.read_excel(self.data_dir / "rod_prepared_data.xlsx")

        # POI
        try:
            self.poi = pd.read_excel(self.data_dir / "poi_prepared_data.xlsx")
        except:
            self.poi = None

        # Weather (optionnel pour ajustements avancés)
        try:
            self.weather = pd.read_excel(self.data_dir / "weather_prepared_data.xlsx")
        except:
            self.weather = None

        # Colonnes de montant mensuel
        self.montant_cols = [c for c in self.trans.columns if c.startswith("m") and "__montant" in c]

        # Extraire GAMME
        self.all_gammes = sorted(
            set(c.split("__")[2] for c in self.montant_cols if len(c.split("__")) > 2)
        )

        # Préparer ventes par hôtel et par mois
        self._prepare_monthly_sales()

    def _prepare_monthly_sales(self):
        """Prépare un DataFrame de CA mensuel par hôtel et par GAMME."""
        id_cols = ["HOTEL_NAME"]
        long = self.trans.melt(
            id_vars=id_cols,
            value_vars=self.montant_cols,
            var_name="col",
            value_name="montant"
        )
        long["mois"] = long["col"].str.extract(r"m(\d\d)").astype(int)
        long["GAMME"] = long["col"].str.split("__").str[2]

        # Agrégation : CA par hôtel, mois, GAMME
        self.sales_by_hotel_gamme_month = (
            long.groupby(["HOTEL_NAME", "mois", "GAMME"])["montant"]
            .sum()
            .unstack(fill_value=0)
        )

        # Total par hôtel et mois (toutes GAMME)
        self.sales_by_hotel_month = (
            long.groupby(["HOTEL_NAME", "mois"])["montant"].sum().unstack(fill_value=0)
        )

    def get_hotel_params(self, hotel_name: str) -> Dict:
        """Récupère les paramètres de base de l'hôtel depuis ROD."""
        row = self.rod[self.rod["HOTEL_NAME"] == hotel_name]
        if len(row) == 0:
            # Fallback
            return {"nb_ch": 150, "to_ref": 0.70, "guests_per_ch": 1.7, "m_lin_ref": 5.0}

        nb_ch_col = [c for c in self.rod.columns if "nb_de_chambres" in c][0]
        nb_ch = float(row.iloc[0][nb_ch_col]) if pd.notna(row.iloc[0][nb_ch_col]) else 150

        # Valeurs par défaut raisonnables si pas dans les données préparées
        return {
            "nb_ch": int(nb_ch),
            "to_ref": 0.72,           # Taux d'occupation de référence
            "guests_per_ch": 1.7,
            "m_lin_ref": 5.0,         # Valeur de référence utilisée dans les simulations
        }

    def get_poi_factor(self, hotel_name: str) -> float:
        """Facteur d'ajustement basé sur les POI (densité commerces)."""
        if self.poi is None or hotel_name not in self.poi["HOTEL_NAME"].values:
            return 1.0

        p = self.poi[self.poi["HOTEL_NAME"] == hotel_name].iloc[0]
        # Exemple simple : plus il y a de commerces, plus la zone est attractive (ou concurrence ?)
        # On prend un score doux
        total_poi = p["fb_0_3km"] + p["not_fb_0_3km"]
        # Normalisation grossière
        factor = 1.0 + np.log1p(total_poi) * 0.03   # petit effet
        return min(max(factor, 0.85), 1.25)

    def get_seasonality(self, hotel_name: str) -> pd.Series:
        """Retourne un facteur de saisonnalité par mois (1.0 = moyenne)."""
        if hotel_name not in self.sales_by_hotel_month.index:
            # Saisonnalité moyenne simple
            factors = np.array([0.85, 0.80, 0.95, 1.05, 1.10, 1.15, 1.20, 1.15, 1.05, 1.00, 0.90, 1.00])
            return pd.Series(factors, index=range(1, 13))

        monthly = self.sales_by_hotel_month.loc[hotel_name]
        mean_ca = monthly.mean()
        if mean_ca == 0:
            return pd.Series(1.0, index=range(1, 13))
        factors = (monthly / mean_ca).clip(0.6, 1.5)
        return factors

    def simulate(
        self,
        hotel_name: str,
        m_lin: float,
        allowed_gammes: Optional[List[str]] = None,
        exclude_gammes: Optional[List[str]] = None,
        reference_m_lin: Optional[float] = None,
        extra_multiplier: float = 1.0,
    ) -> Tuple[pd.DataFrame, Dict]:
        """
        Simule le CA pour un coin de vente.

        Args:
            hotel_name: Nom exact de l'hôtel (ex: "Ibis budget Nice")
            m_lin: Nombre de mètres linéaires choisis par le directeur
            allowed_gammes: Liste des GAMME autorisées (si None = toutes)
            exclude_gammes: Liste des GAMME à exclure (ex: ["ALCOOL"])
            reference_m_lin: m_lin de référence (sinon valeur par défaut de l'hôtel)
            extra_multiplier: Facteur multiplicatif libre

        Returns:
            (df_mensuel, summary)
            df_mensuel : colonnes ["mois", "ca_estime", "part_f_b_estimee"]
            summary : dict avec ca_annuel, etc.
        """
        params = self.get_hotel_params(hotel_name)

        if reference_m_lin is None:
            reference_m_lin = params.get("m_lin_ref", 5.0)

        # Scaler m_lin
        mlin_scaler = m_lin / reference_m_lin

        # POI factor
        poi_factor = self.get_poi_factor(hotel_name)

        # Saisonnalité de base
        seasonality = self.get_seasonality(hotel_name)

        # === Répartition par GAMME ===
        if hotel_name in self.sales_by_hotel_gamme_month.index.get_level_values(0):
            # Utiliser l'historique de l'hôtel
            hotel_sales = self.sales_by_hotel_gamme_month.loc[hotel_name]
            gamme_totals = hotel_sales.sum(axis=0)
        else:
            # Moyenne sur tous les hôtels
            all_sales = self.sales_by_hotel_gamme_month.groupby(level=1).sum()
            gamme_totals = all_sales.sum(axis=0)

        total_ref = gamme_totals.sum()
        if total_ref == 0:
            total_ref = 1.0

        parts = (gamme_totals / total_ref).to_dict()

        # Filtrage des catégories
        if exclude_gammes:
            for g in exclude_gammes:
                parts[g] = 0.0
        if allowed_gammes:
            for g in list(parts.keys()):
                if g not in allowed_gammes:
                    parts[g] = 0.0

        # Renormalisation
        part_sum = sum(parts.values())
        if part_sum > 0:
            parts = {k: v / part_sum for k, v in parts.items()}

        # CA de référence annuel (basé sur données historiques)
        if hotel_name in self.sales_by_hotel_month.index:
            ref_annual = self.sales_by_hotel_month.loc[hotel_name].sum()
        else:
            ref_annual = self.sales_by_hotel_month.sum().sum() / max(len(self.sales_by_hotel_month), 1)

        # CA de base après m_lin et POI
        base_annual = ref_annual * mlin_scaler * poi_factor * extra_multiplier

        # Répartition mensuelle
        rows = []
        for mois in range(1, 13):
            month_factor = seasonality.get(mois, 1.0)
            ca_mois = base_annual / 12 * month_factor

            # Répartition par GAMME (pour info)
            ca_by_gamme = {g: ca_mois * p for g, p in parts.items() if p > 0}

            rows.append({
                "mois": mois,
                "ca_estime": round(ca_mois, 2),
                **{f"ca_{g}": round(v, 2) for g, v in ca_by_gamme.items()}
            })

        df = pd.DataFrame(rows)
        ca_annuel = df["ca_estime"].sum()

        summary = {
            "hotel_name": hotel_name,
            "m_lin": m_lin,
            "reference_m_lin": reference_m_lin,
            "mlin_scaler": round(mlin_scaler, 3),
            "poi_factor": round(poi_factor, 3),
            "ca_annuel_estime": round(ca_annuel, 2),
            "ca_mensuel_moyen": round(ca_annuel / 12, 2),
            "categories_utilisees": [g for g, p in parts.items() if p > 0],
            "parts_categories": {g: round(p, 3) for g, p in parts.items() if p > 0},
        }

        return df, summary


# =====================
# Fonction helper simple
# =====================

def simulate_corner(
    hotel_name: str,
    m_lin: float,
    allowed_gammes: Optional[List[str]] = None,
    exclude_gammes: Optional[List[str]] = None,
    **kwargs
) -> pd.DataFrame:
    """
    Version simple pour un appel rapide.
    Retourne directement le DataFrame mensuel.
    """
    sim = CornerSimulator()
    df, summary = sim.simulate(
        hotel_name=hotel_name,
        m_lin=m_lin,
        allowed_gammes=allowed_gammes,
        exclude_gammes=exclude_gammes,
        **kwargs
    )
    print("=== Résumé simulation ===")
    for k, v in summary.items():
        print(f"{k}: {v}")
    return df


if __name__ == "__main__":
    # Exemple d'utilisation
    print("=== Test du simulateur ===\n")

    # Exemple 1 : Ibis Budget Nice avec 4 mètres linéaires, sans alcool
    df1 = simulate_corner(
        hotel_name="Ibis budget Nice",
        m_lin=4.0,
        exclude_gammes=["ALCOOL"]
    )
    print("\nCA mensuel estimé (sans alcool):")
    print(df1[["mois", "ca_estime"]].to_string(index=False))
    print(f"CA annuel estimé: {df1['ca_estime'].sum():.2f} €\n")

    # Exemple 2 : Même hôtel avec plus de mètres et toutes catégories
    df2 = simulate_corner(
        hotel_name="Ibis budget Nice",
        m_lin=7.0
    )
    print("CA mensuel estimé (toutes catégories, 7m lin):")
    print(df2[["mois", "ca_estime"]].to_string(index=False))
