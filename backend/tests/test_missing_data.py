import pytest
from app.matching import match_forecast_to_actuals
from app.metrics import calculate_metrics

def test_missing_forecast_not_treated_as_zero():
    # Actuals exist for 00:00 and 01:00, but forecast ONLY exists for 00:00
    actual_rows = [
        {"startTime": "2026-01-01T00:00:00Z", "generation": 10000.0, "settlementPeriod": 1},
        {"startTime": "2026-01-01T00:30:00Z", "generation": 10000.0, "settlementPeriod": 2},
        {"startTime": "2026-01-01T01:00:00Z", "generation": 8000.0, "settlementPeriod": 3},
        {"startTime": "2026-01-01T01:30:00Z", "generation": 8000.0, "settlementPeriod": 4},
    ]
    forecast_rows = [
        {"startTime": "2026-01-01T00:00:00Z", "publishTime": "2025-12-31T15:30:00Z", "generation": 10500.0},
        # No forecast for 01:00
    ]

    res = match_forecast_to_actuals(actual_rows, forecast_rows, rule="day_ahead_d1_1700")

    # Only 1 interval should be matched
    assert len(res["matched"]) == 1
    assert res["matched"][0]["startTime"] == "2026-01-01T00:00:00Z"
    assert res["matched"][0]["actual"] == 10000.0
    assert res["matched"][0]["forecast"] == 10500.0

    # The missing forecast interval must be tracked in unmatchedActuals
    assert len(res["unmatchedActuals"]) == 1
    assert res["unmatchedActuals"][0]["startTime"] == "2026-01-01T01:00:00Z"
    assert res["unmatchedActuals"][0]["actual"] == 8000.0

    # Metrics MUST be calculated only on matched intervals (N=1), NOT treating 01:00 forecast as 0
    metrics = calculate_metrics(res["matched"], expected_intervals=2)
    assert metrics["count"] == 1
    assert metrics["expectedCount"] == 2
    assert metrics["coveragePercent"] == 50.0
    assert metrics["maeMW"] == 500.0  # If it were treated as zero, MAE would be (500 + 8000)/2 = 4250!
    assert metrics["rmseMW"] == 500.0

def test_missing_actual_not_treated_as_zero():
    # Forecast exists for 00:00 and 01:00, but actuals ONLY exist for 00:00
    actual_rows = [
        {"startTime": "2026-01-01T00:00:00Z", "generation": 5000.0, "settlementPeriod": 1},
        {"startTime": "2026-01-01T00:30:00Z", "generation": 5000.0, "settlementPeriod": 2},
    ]
    forecast_rows = [
        {"startTime": "2026-01-01T00:00:00Z", "publishTime": "2025-12-31T15:30:00Z", "generation": 5200.0},
        {"startTime": "2026-01-01T01:00:00Z", "publishTime": "2025-12-31T15:30:00Z", "generation": 6000.0},
    ]

    res = match_forecast_to_actuals(actual_rows, forecast_rows, rule="day_ahead_d1_1700")

    assert len(res["matched"]) == 1
    assert len(res["unmatchedForecasts"]) == 1
    assert res["unmatchedForecasts"][0]["startTime"] == "2026-01-01T01:00:00Z"
    assert res["unmatchedForecasts"][0]["forecast"] == 6000.0

    metrics = calculate_metrics(res["matched"], expected_intervals=2)
    assert metrics["count"] == 1
    assert metrics["maeMW"] == 200.0
