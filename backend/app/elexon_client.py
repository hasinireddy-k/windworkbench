import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
import httpx
from fastapi import HTTPException

from .config import BASE_URL, CACHE_DIR, CACHE_ENABLED

logger = logging.getLogger("wind_forecast_workbench.elexon")

# Ensure cache dir exists
if CACHE_ENABLED and not os.path.exists(CACHE_DIR):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
    except Exception as e:
        logger.warning(f"Failed to create cache directory {CACHE_DIR}: {e}")

_memory_cache: Dict[str, Any] = {}

def get_cache_path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")

def load_cache(key: str) -> Optional[List[Dict[str, Any]]]:
    if not CACHE_ENABLED:
        return None
    if key in _memory_cache:
        return _memory_cache[key]
    cache_file = get_cache_path(key)
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                _memory_cache[key] = data
                return data
        except Exception as e:
            logger.warning(f"Error reading cache file {cache_file}: {e}")
    return None

def save_cache(key: str, data: List[Dict[str, Any]]) -> None:
    if not CACHE_ENABLED:
        return
    _memory_cache[key] = data
    cache_file = get_cache_path(key)
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"Error writing cache file {cache_file}: {e}")

def extract_rows(payload: Any) -> List[Dict[str, Any]]:
    """Extract list of dict rows from varied Elexon response shapes."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for k in ("data", "results", "items", "result"):
            val = payload.get(k)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]
    return []

async def fetch_stream_with_retry(
    endpoint: str,
    params: Dict[str, Any],
    max_retries: int = 2,
    timeout: float = 35.0,
) -> List[Dict[str, Any]]:
    """
    Fetch stream dataset from Elexon BMRS API with timeout and retries.
    """
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    headers = {"Accept": "application/json"}

    last_error: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    try:
                        return extract_rows(resp.json())
                    except ValueError as e:
                        raise HTTPException(
                            status_code=502,
                            detail=f"Elexon returned invalid JSON from {endpoint}: {e}",
                        ) from e
                elif resp.status_code in (404, 400):
                    raise HTTPException(
                        status_code=resp.status_code,
                        detail=f"Elexon API client error ({resp.status_code}) for {endpoint}. Check query parameters.",
                    )
                else:
                    # 5xx or rate limit: retry if attempts remain
                    resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            last_error = e
            if attempt == max_retries:
                raise HTTPException(
                    status_code=502,
                    detail=f"Elexon returned HTTP {e.response.status_code} for {endpoint}.",
                ) from e
        except (httpx.TimeoutException, httpx.RequestError) as e:
            last_error = e
            if attempt == max_retries:
                raise HTTPException(
                    status_code=504 if isinstance(e, httpx.TimeoutException) else 502,
                    detail=f"Failed to communicate with Elexon BMRS API ({type(e).__name__}): {e}",
                ) from e
        # Sleep briefly before retry
        time.sleep(0.5)

    raise HTTPException(status_code=502, detail=f"Elexon request failed: {last_error}")

def normalize_fuelhh(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize FUELHH actual wind generation records."""
    out = []
    for r in rows:
        ts = next((r.get(k) for k in ("startTime", "start_time", "settlementDateTime") if r.get(k)), None)
        gen = next((r.get(k) for k in ("generation", "quantity", "value", "power") if r.get(k) is not None), None)
        pub = next((r.get(k) for k in ("publishTime", "publishDateTime") if r.get(k)), None)
        fuel = r.get("fuelType", "WIND")

        if ts is not None and gen is not None:
            try:
                out.append({
                    "dataset": "FUELHH",
                    "startTime": str(ts),
                    "publishTime": str(pub) if pub else str(ts),
                    "settlementDate": str(r.get("settlementDate") or str(ts)[:10]),
                    "settlementPeriod": int(r.get("settlementPeriod") or 0),
                    "fuelType": str(fuel),
                    "generation": float(gen),
                })
            except (ValueError, TypeError):
                continue
    return out

def normalize_windfor(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize WINDFOR forecast wind generation records."""
    out = []
    for r in rows:
        ts = next((r.get(k) for k in ("startTime", "start_time", "settlementDateTime") if r.get(k)), None)
        gen = next((r.get(k) for k in ("generation", "quantity", "value", "power") if r.get(k) is not None), None)
        pub = next((r.get(k) for k in ("publishTime", "publishDateTime") if r.get(k)), None)

        if ts is not None and gen is not None:
            try:
                out.append({
                    "dataset": "WINDFOR",
                    "startTime": str(ts),
                    "publishTime": str(pub) if pub else "",
                    "generation": float(gen),
                })
            except (ValueError, TypeError):
                continue
    return out

async def get_actual_generation(
    from_date: str = "2026-01-01",
    to_date: str = "2026-01-31",
    refresh: bool = False,
) -> List[Dict[str, Any]]:
    """
    Retrieve actual wind generation from FUELHH dataset for January 2026.
    Uses settlementDate filtering: settlementDateFrom=from_date, settlementDateTo=to_date, fuelType=WIND.
    """
    cache_key = f"fuelhh_{from_date}_{to_date}"
    if not refresh:
        cached = load_cache(cache_key)
        if cached is not None:
            return cached

    # Query Elexon FUELHH stream
    params = {
        "settlementDateFrom": from_date,
        "settlementDateTo": to_date,
        "fuelType": "WIND",
    }
    raw = await fetch_stream_with_retry("datasets/FUELHH/stream", params)
    normalized = normalize_fuelhh(raw)
    save_cache(cache_key, normalized)
    return normalized

async def get_forecast_generation(
    publish_from: str = "2025-12-30T00:00:00Z",
    publish_to: str = "2026-02-01T23:59:59Z",
    refresh: bool = False,
) -> List[Dict[str, Any]]:
    """
    Retrieve WINDFOR forecast stream data covering January 2026 delivery targets.
    Fetches publications starting Dec 30 2025 so Day-Ahead forecasts for Jan 1 2026 are included.
    """
    cache_key = f"windfor_{publish_from[:10]}_{publish_to[:10]}"
    if not refresh:
        cached = load_cache(cache_key)
        if cached is not None:
            return cached

    params = {
        "publishDateTimeFrom": publish_from,
        "publishDateTimeTo": publish_to,
    }
    raw = await fetch_stream_with_retry("datasets/WINDFOR/stream", params)
    normalized = normalize_windfor(raw)
    save_cache(cache_key, normalized)
    return normalized
