from pathlib import Path
import json
from app.domain.services.sales_mix_extractor import SalesMixExtractor

sales_path = Path('app/data/raw/001.queryVentes.csv')
out_path = Path('app/data/reference/recomputed_sales_reference.json')
out_path.parent.mkdir(parents=True, exist_ok=True)

if not sales_path.exists():
    raise SystemExit('Déposer 001.queryVentes.csv dans app/data/raw avant exécution.')

extractor = SalesMixExtractor(sales_path)
ref = extractor.mix_by_type_and_gamme(exclude_year=2026)
ref['monthly_average_targets_note'] = 'Calculé en moyennant les mois disponibles par hôtel/mois/type/gamme, sans tronquer au plus petit historique.'
out_path.write_text(json.dumps(ref, ensure_ascii=False, indent=2), encoding='utf-8')
print('Wrote', out_path)
