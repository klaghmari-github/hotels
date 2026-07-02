from flask import Blueprint, jsonify

from rod_ia.api.dependencies import AppContainer
from rod_ia.domain.services.sales_catalog_service import SalesCatalogService


def create_catalog_blueprint(container: AppContainer) -> Blueprint:
    blueprint = Blueprint("catalog", __name__)

    @blueprint.get("/api/sales-catalog")
    def sales_catalog():
        service = SalesCatalogService(container.settings.sales_csv_path)
        return jsonify(service.load_catalog())

    return blueprint