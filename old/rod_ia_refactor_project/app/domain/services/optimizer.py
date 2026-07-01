from copy import deepcopy
from itertools import product
from app.domain.models.simulation import RodSimulationRequest

class RodOptimizer:
    """Optimiseur sous contraintes utilisateur.

    Il teste plusieurs configurations et garde celle qui maximise la marge annuelle.
    Les champs présents dans locked_fields ne sont pas modifiés.
    """
    def __init__(self, simulator):
        self.simulator = simulator

    def optimize(self, req: RodSimulationRequest, concepts=('SIMPLY','LIBERTY','CONNECTED'), m_lins=(1,2,3,4,5,6), fb_shares=(0.5,0.6,0.7,0.8,0.9)):
        locked = set(req.store.locked_fields)
        best = None
        best_req = None
        for concept, m_lin, fb in product(concepts, m_lins, fb_shares):
            candidate = deepcopy(req)
            if 'concept' not in locked:
                candidate.store.concept = concept
            if 'm_lin' not in locked:
                candidate.store.m_lin = float(m_lin)
            if 'fb_share' not in locked:
                candidate.store.mix.fb_share = float(fb)
                candidate.store.mix.non_fb_share = float(1 - fb)
            result = self.simulator.simulate(candidate)
            score = result.marge_annuelle
            if best is None or score > best.marge_annuelle:
                best = result
                best_req = candidate
        return {'request': best_req.store.to_dict() if best_req else None, 'result': best.to_dict() if best else None}
