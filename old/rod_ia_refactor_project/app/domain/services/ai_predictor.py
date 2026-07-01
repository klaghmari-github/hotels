from pathlib import Path
import json
import re
import joblib
import pandas as pd
from app.domain.models.simulation import RodSimulationRequest, SimulationResult, MonthlyProjection

class AIRodRevenuePredictor:
    """Prédicteur IA.

    Si aucun modèle n'est disponible, retourne un résultat vide avec warning.
    """
    def __init__(self, artifacts_dir: str | Path):
        self.artifacts_dir = Path(artifacts_dir)
        self.model = None
        self.feature_cols = []
        self.target_cols = []
        self.load_warnings=[]
        self._load()

    def _load(self):
        model_path = self.artifacts_dir / 'model.joblib'
        if model_path.exists():
            self.model = joblib.load(model_path)
        else:
            self.load_warnings.append('model.joblib absent: prédiction IA désactivée.')
        f = self.artifacts_dir / 'feature_cols.json'
        if f.exists():
            self.feature_cols = json.loads(f.read_text(encoding='utf-8'))
        t = self.artifacts_dir / 'target_cols.json'
        if t.exists():
            self.target_cols = json.loads(t.read_text(encoding='utf-8'))

    def request_to_features(self, req: RodSimulationRequest) -> pd.DataFrame:
        data = {
            'nb_chambres': req.operating.nb_chambres,
            'taux_occupation': req.operating.taux_occupation,
            'guests_per_chambre': req.operating.guests_per_chambre,
            'm_lin': req.store.m_lin,
            'fb_share': req.store.mix.fb_share,
            'non_fb_share': req.store.mix.non_fb_share,
        }
        for k,v in req.enriched.poi.items():
            data[f'poi_{k}'] = v
        for k,v in req.enriched.weather_monthly.items():
            data[f'weather_{k}'] = v
        for k,v in req.enriched.nearest.items():
            data[f'nearest_{k}'] = v
        df = pd.DataFrame([data])
        if self.feature_cols:
            for col in self.feature_cols:
                if col not in df.columns:
                    df[col] = 0
            df = df[self.feature_cols]
        return df

    def predict(self, req: RodSimulationRequest) -> SimulationResult:
        warnings=list(self.load_warnings)
        if self.model is None:
            monthly=[MonthlyProjection(month=i, ca=0.0, nbr_ventes=0.0) for i in range(1,13)]
            return SimulationResult('AI_MODEL', req.store.concept, req.store.m_lin, 0, 0, 0, 0, None, monthly, warnings=warnings)
        X = self.request_to_features(req)
        pred = self.model.predict(X)
        values = pred[0] if hasattr(pred, '__len__') else [float(pred)]
        monthly = {i: {'ca': 0.0, 'nbr_ventes': 0.0} for i in range(1,13)}
        for col, val in zip(self.target_cols, values):
            m = re.search(r'm(\d\d)', col)
            if not m:
                continue
            month=int(m.group(1))
            if 'montant' in col or 'ca' in col.lower():
                monthly[month]['ca'] += max(float(val), 0.0)
            if 'nbr_ventes' in col or 'ventes' in col.lower():
                monthly[month]['nbr_ventes'] += max(float(val), 0.0)
        rows=[MonthlyProjection(month=i, ca=monthly[i]['ca'], nbr_ventes=monthly[i]['nbr_ventes']) for i in range(1,13)]
        ca=sum(r.ca for r in rows)
        sales=sum(r.nbr_ventes for r in rows)
        return SimulationResult('AI_MODEL', req.store.concept, req.store.m_lin, ca, sales, ca, 0, None, rows, warnings=warnings)
