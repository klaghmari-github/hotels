"""Catalogue TYPE / GAMME depuis le CSV ventes."""

from rod_ia.config.settings import get_settings
from rod_ia.domain.services.sales_catalog_service import SalesCatalogService


def test_sales_catalog_from_csv():
    settings = get_settings()
    catalog = SalesCatalogService(settings.sales_csv_path).load_catalog()
    assert "F&B" in catalog["types"]
    assert "NON-F&B" in catalog["types"]
    assert "ALCOOL" in catalog["gammes"]
    assert "ALCOOL" in catalog["by_type"]["F&B"]
    assert "#REF!" not in catalog["gammes"]
    assert len(catalog["gammes"]) >= 10