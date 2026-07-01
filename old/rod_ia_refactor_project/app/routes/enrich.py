from flask import Blueprint, request, jsonify
from app.config.settings import FEATURE_STORE_DIR
from app.domain.services.enrich_hotel import EnrichHotelService

enrich_bp = Blueprint('enrich', __name__)
service = EnrichHotelService(FEATURE_STORE_DIR)

@enrich_bp.post('/api/enrich')
def enrich():
    payload = request.get_json(force=True) or {}
    identity = payload.get('identity', payload)
    hotel_id, features = service.enrich(
        hotel_name=identity.get('hotel_name',''),
        address=identity.get('address',''),
        city=identity.get('city',''),
        force_refresh=bool(payload.get('force_refresh', False)),
    )
    return jsonify({'hotel_id': hotel_id, 'features': features.to_dict()})
