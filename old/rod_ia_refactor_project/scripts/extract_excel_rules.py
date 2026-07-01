from pathlib import Path
import csv
from app.domain.repositories.excel_repository import ExcelRuleRepository

RAW = Path('app/data/raw')
OUT = Path('docs/audit')
OUT.mkdir(parents=True, exist_ok=True)

for path in RAW.glob('*.xls*'):
    repo = ExcelRuleRepository(path)
    formulas = repo.extract_formulas()
    with (OUT / f'{path.stem}_formulas.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['workbook','sheet','cell','formula','value','comment'])
        writer.writeheader()
        for x in formulas:
            writer.writerow(x.__dict__)
    comments = repo.extract_comments()
    with (OUT / f'{path.stem}_comments.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['workbook','sheet','cell','comment','value'])
        writer.writeheader()
        writer.writerows(comments)
    print(path.name, 'formulas', len(formulas), 'comments', len(comments))
