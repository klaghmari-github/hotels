import pandas as pd

from rod_ia.domain.services.sales_percentage_service import SalesPercentageService


def test_monthly_percentages_sum_to_one():
    monthly_avg = pd.DataFrame(
        [
            {"hotel_id": "h1", "month": 1, "TYPE": "F&B", "GAMME": "ALCOOL", "avg_montant": 100},
            {"hotel_id": "h1", "month": 2, "TYPE": "F&B", "GAMME": "ALCOOL", "avg_montant": 100},
        ]
    )
    service = SalesPercentageService(monthly_avg)
    _, long_pct = service.compute_all()
    level1 = long_pct[long_pct["level"] == 1]
    assert abs(level1["pct"].sum() - 1.0) < 1e-6