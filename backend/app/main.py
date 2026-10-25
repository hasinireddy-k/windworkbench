from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import ALLOWED_ORIGINS, CACHE_ENABLED, DEFAULT_END, DEFAULT_START
from .elexon_client import get_actual_generation, get_forecast_generation
from .matching import DECISION_RULES, match_forecast_to_actuals, parse_iso
from .metrics import calculate_metrics

app = FastAPI(
    title="Wind Forecast Workbench API",
    description="Quantitative accuracy evaluation for UK January 2026 wind forecasts vs actual generation.",
    version="2.0.0",
)

# CORS configuration
if "*" in ALLOWED_ORIGINS:
    allow_origins = ["*"]
else:
    allow_origins = ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "Wind Forecast Workbench API",
        "version": "2.0.0",
        "targetPeriod": "January 2026",
        "cacheEnabled": CACHE_ENABLED,
    }

@app.get("/api/decision-rules")
async def decision_rules():
    return {
        "rules": DECISION_RULES,
        "default": "day_ahead_d1_1700",
    }

@app.get("/api/actual")
async def actual(
    from_date: Annotated[str, Query(description="Settlement date from (YYYY-MM-DD)")] = "2026-01-01",
    to_date: Annotated[str, Query(description="Settlement date to (YYYY-MM-DD)")] = "2026-01-31",
    refresh: Annotated[bool, Query(description="Bypass cache and fetch live from Elexon")] = False,
):
    try:
        data = await get_actual_generation(from_date=from_date, to_date=to_date, refresh=refresh)
        return {
            "source": "Elexon BMRS FUELHH stream",
            "period": {"from": from_date, "to": to_date},
            "fuelType": "WIND",
            "count": len(data),
            "data": data,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error processing actuals: {e}")

@app.get("/api/forecast")
async def forecast(
    publish_from: Annotated[str, Query(description="Publication timestamp from (ISO8601)")] = "2025-12-30T00:00:00Z",
    publish_to: Annotated[str, Query(description="Publication timestamp to (ISO8601)")] = "2026-02-01T23:59:59Z",
    refresh: Annotated[bool, Query(description="Bypass cache and fetch live from Elexon")] = False,
):
    try:
        data = await get_forecast_generation(publish_from=publish_from, publish_to=publish_to, refresh=refresh)
        return {
            "source": "Elexon BMRS WINDFOR stream",
            "publishPeriod": {"from": publish_from, "to": publish_to},
            "count": len(data),
            "data": data,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error processing forecasts: {e}")

@app.get("/api/analysis")
async def analysis(
    decision_rule: Annotated[str, Query(description="Decision gate rule key")] = "day_ahead_d1_1700",
    resolution: Annotated[str, Query(description="'hourly' (aggregated) or 'half_hourly'")] = "hourly",
    from_time: Annotated[str, Query(alias="from", description="Target start UTC ISO")] = DEFAULT_START,
    to_time: Annotated[str, Query(alias="to", description="Target end UTC ISO")] = DEFAULT_END,
    refresh: Annotated[bool, Query(description="Bypass cache and fetch live from Elexon")] = False,
):
    if decision_rule not in DECISION_RULES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid decision_rule '{decision_rule}'. Supported rules: {list(DECISION_RULES.keys())}",
        )

    if resolution not in ("hourly", "half_hourly"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid resolution '{resolution}'. Must be 'hourly' or 'half_hourly'.",
        )

    # 1. Fetch data from Elexon
    from_date = from_time[:10]
    to_date = to_time[:10]
    # For Jan 2026, to_date in FUELHH settlement date query is inclusive
    if to_time.endswith("T00:00:00Z") and to_date > from_date:
        # e.g. 2026-02-01T00:00:00Z means settlement dates through 2026-01-31
        dt_end = parse_iso(to_time)
        from datetime import timedelta
        prev_date = (dt_end - timedelta(days=1)).strftime("%Y-%m-%d")
        actual_to_date = prev_date
    else:
        actual_to_date = to_date

    actual_rows = await get_actual_generation(from_date=from_date, to_date=actual_to_date, refresh=refresh)

    # For forecasts, ensure we include D-1 publications for the first delivery day
    # So if from_time is 2026-01-01, publish_from should be 2025-12-30
    fc_publish_from = "2025-12-30T00:00:00Z"
    fc_publish_to = "2026-02-01T23:59:59Z"
    forecast_rows = await get_forecast_generation(publish_from=fc_publish_from, publish_to=fc_publish_to, refresh=refresh)

    # 2. Match forecasts to actuals using specified decision gate and resolution
    match_result = match_forecast_to_actuals(
        actual_rows=actual_rows,
        forecast_rows=forecast_rows,
        rule=decision_rule,
        resolution=resolution,
        start_filter=from_time,
        end_filter=to_time,
    )

    matched = match_result["matched"]
    expected_intervals = 744 if resolution == "hourly" else 1488

    # 3. Calculate quantitative accuracy metrics
    metrics = calculate_metrics(matched, expected_intervals=expected_intervals, near_zero_threshold_mw=100.0)

    # 4. Compute daily error profiles
    daily_buckets: Dict[str, List[Dict[str, Any]]] = {}
    for r in matched:
        day_key = r["startTime"][:10]
        daily_buckets.setdefault(day_key, []).append(r)

    daily_profile = []
    for day_key in sorted(daily_buckets.keys()):
        rows = daily_buckets[day_key]
        m = calculate_metrics(rows)
        daily_profile.append({
            "day": day_key,
            "count": len(rows),
            "mae": m["maeMW"],
            "rmse": m["rmseMW"],
            "bias": m["biasMW"],
            "wape": m["wapePercent"],
            "meanActual": m["meanActualMW"],
            "meanForecast": m["meanForecastMW"],
        })

    # 5. Compute diurnal (hour of day 00 to 23) error profiles
    diurnal_buckets: Dict[int, List[Dict[str, Any]]] = {h: [] for h in range(24)}
    for r in matched:
        try:
            hour_of_day = int(r["startTime"][11:13])
            diurnal_buckets[hour_of_day].append(r)
        except (ValueError, IndexError):
            pass

    diurnal_profile = []
    for h in range(24):
        rows = diurnal_buckets[h]
        if rows:
            m = calculate_metrics(rows)
            diurnal_profile.append({
                "hour": f"{h:02d}:00",
                "count": len(rows),
                "mae": m["maeMW"],
                "bias": m["biasMW"],
                "actualAvg": m["meanActualMW"],
                "forecastAvg": m["meanForecastMW"],
            })

    # 6. Top deviations
    largest_errors = sorted(matched, key=lambda x: x["absoluteError"], reverse=True)[:15]

    return {
        "period": {"from": from_time, "to": to_time},
        "decisionRule": match_result["ruleInfo"],
        "resolution": resolution,
        "counts": {
            "actualRowsRaw": len(actual_rows),
            "forecastRowsRaw": len(forecast_rows),
            "expectedIntervals": expected_intervals,
            "matchedIntervals": len(matched),
            "unmatchedActuals": len(match_result["unmatchedActuals"]),
            "unmatchedForecasts": len(match_result["unmatchedForecasts"]),
        },
        "metrics": metrics,
        "dailyProfile": daily_profile,
        "diurnalProfile": diurnal_profile,
        "largestErrors": largest_errors,
        "unmatchedActuals": match_result["unmatchedActuals"],
        "unmatchedForecasts": match_result["unmatchedForecasts"],
        "data": matched,
        "notes": [
            f"Rule '{decision_rule}': {match_result['ruleInfo']['description']}",
            "Hourly resolution aggregates two 30-minute settlement periods (FUELHH) into average MW over the forecast hour.",
            "WAPE (Weighted Absolute Percentage Error) is the energy industry standard percentage metric for intermittent renewables, avoiding division-by-zero on calm days.",
            "Filtered MAPE excludes actuals < 100 MW where percentage error diverges unstably; excluded count is reported explicitly.",
            "No missing data is treated as zero or silently omitted.",
        ],
    }
