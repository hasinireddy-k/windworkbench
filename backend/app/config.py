import os
from typing import List

ELEXON_API_BASE: str = os.getenv("ELEXON_API_BASE", "https://data.elexon.co.uk/bmrs/api/v1").rstrip("/")
BASE_URL: str = ELEXON_API_BASE
ALLOWED_ORIGINS_RAW: str = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS: List[str] = [o.strip() for o in ALLOWED_ORIGINS_RAW.split(",") if o.strip()]

CACHE_ENABLED: bool = os.getenv("CACHE_ENABLED", "true").lower() in ("true", "1", "yes")
CACHE_DIR: str = os.getenv("CACHE_DIR", os.path.join(os.path.dirname(__file__), "..", ".cache"))

DEFAULT_START: str = "2026-01-01T00:00:00Z"
DEFAULT_END: str = "2026-02-01T00:00:00Z"
