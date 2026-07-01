from pathlib import Path
import pandas as pd

class SalesMixExtractor:
    """Recalcule les métriques d'entrée ROD depuis les ventes pivots.

    Principe : exclure 2026 si souhaité, puis moyenner les ventes par mois,
    catégorie et gamme, sans tronquer l'historique au plus petit commun.
    """
    def __init__(self, sales_path: str | Path):
        self.sales_path = Path(sales_path)

    def load_sales(self) -> pd.DataFrame:
        if self.sales_path.suffix.lower() in ['.xlsx', '.xlsm']:
            return pd.read_excel(self.sales_path)
        return pd.read_csv(self.sales_path)

    def prepare(self, exclude_year: int | None = 2026) -> pd.DataFrame:
        df = self.load_sales().copy()
        date_col = 'DATETIME' if 'DATETIME' in df.columns else 'DATE'
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        df['year'] = df[date_col].dt.year
        df['month'] = df[date_col].dt.month
        if exclude_year:
            df = df[df['year'] < exclude_year]
        price_col = 'PRIX TTC' if 'PRIX TTC' in df.columns else 'PRIX_HT'
        qty_col = 'QUANTITE' if 'QUANTITE' in df.columns else 'QTE'
        df['montant'] = pd.to_numeric(df[price_col], errors='coerce').fillna(0) * pd.to_numeric(df[qty_col], errors='coerce').fillna(0)
        df['nbr_ventes'] = pd.to_numeric(df[qty_col], errors='coerce').fillna(0)
        return df

    def monthly_average_targets(self, exclude_year: int | None = 2026) -> pd.DataFrame:
        df = self.prepare(exclude_year=exclude_year)
        hotel_col = 'NOM BOUTIQUE' if 'NOM BOUTIQUE' in df.columns else 'HOTEL_NAME'
        keys = [hotel_col, 'month', 'TYPE', 'GAMME']
        annual_month = df.groupby(keys + ['year'], dropna=False)[['montant','nbr_ventes']].sum().reset_index()
        return annual_month.groupby(keys, dropna=False).agg(
            montant_moyen=('montant','mean'),
            nbr_ventes_moyen=('nbr_ventes','mean'),
            nb_years_used=('year','nunique'),
        ).reset_index()

    def mix_by_type_and_gamme(self, exclude_year: int | None = 2026) -> dict:
        avg = self.monthly_average_targets(exclude_year)
        total = avg['montant_moyen'].sum()
        if total == 0:
            return {}
        return {
            'by_type': (avg.groupby('TYPE')['montant_moyen'].sum() / total).to_dict(),
            'by_gamme': (avg.groupby('GAMME')['montant_moyen'].sum() / total).to_dict(),
        }
