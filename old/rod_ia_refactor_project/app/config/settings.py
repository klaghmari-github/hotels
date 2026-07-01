from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = APP_DIR.parent
DATA_DIR = APP_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
REFERENCE_DIR = DATA_DIR / "reference"
FEATURE_STORE_DIR = APP_DIR / "feature_store" / "hotels"
ARTIFACTS_DIR = APP_DIR / "artifacts"
WEB_DIR = APP_DIR / "web"

DEFAULT_POI_RADII_KM = [0.1, 0.2, 0.3, 0.4, 0.5]
DEFAULT_COUNTRY = "France"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "accor-rod-ia/0.1"
