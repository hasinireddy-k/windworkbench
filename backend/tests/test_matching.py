import pytest
from app.matching import match_forecast_to_actuals, aggregate_actuals_hourly, get_cutoff_for_target, parse_iso

def test_aggregate_actuals_hourly():
    # Two half-hour settlement periods in 2026-01-01 00:00 hour
    actual_rows = [
        {"startTime": "2026-01-01T00:00:00Z", "generation": 10000.0, "settlementPeriod": 1},
        {"startTime": "2026-01-01T00:30:00Z", "generation": 12000.0, "settlementPeriod": 2},
        {"startTime": "2026-01-01T01:00:00Z", "generation": 14000.0, "settlementPeriod": 3},
        {"startTime": "2026-01-01T01:30:00Z", "generation": 16000.0, "settlementPeriod": 4},
    ]
    agg, incomplete = aggregate_actuals_hourly(actual_rows)
    assert len(incomplete) == 0
    assert "2026-01-01T00:00:00Z" in agg
    assert "2026-01-01T01:00:00Z" in agg
    assert agg["2026-01-01T00:00:00Z"]["generation"] == 11000.0
    assert agg["2026-01-01T01:00:00Z"]["generation"] == 15000.0

def test_incomplete_hour_actuals_flagged():
    # Only one half-hour present for 02:00
    actual_rows = [
        {"startTime": "2026-01-01T02:00:00Z", "generation": 9000.0, "settlementPeriod": 5},
    ]
    agg, incomplete = aggregate_actuals_hourly(actual_rows)
    assert "2026-01-01T02:00:00Z" in incomplete
    assert agg["2026-01-01T02:00:00Z"]["isComplete"] is False

def test_look_ahead_bias_decision_gates():
    # Target delivery interval: 2026-01-02T10:00:00Z
    # Multiple publications are released over time:
    forecast_rows = [
        {"startTime": "2026-01-02T10:00:00Z", "publishTime": "2026-01-01T09:30:00Z", "generation": 1000.0}, # Before 12:00 D-1
        {"startTime": "2026-01-02T10:00:00Z", "publishTime": "2026-01-01T15:30:00Z", "generation": 2000.0}, # Between 12:00 and 17:00 D-1
        {"startTime": "2026-01-02T10:00:00Z", "publishTime": "2026-01-01T18:30:00Z", "generation": 3000.0}, # After 17:00 D-1, before midnight
        {"startTime": "2026-01-02T10:00:00Z", "publishTime": "2026-01-02T07:30:00Z", "generation": 4000.0}, # Intraday (look-ahead)
    ]
    actual_rows = [
        {"startTime": "2026-01-02T10:00:00Z", "generation": 2500.0, "settlementPeriod": 21},
        {"startTime": "2026-01-02T10:30:00Z", "generation": 2500.0, "settlementPeriod": 22},
    ]

    # 1. Day-Ahead Auction Gate (D-1 12:00 UTC) -> must select 1000.0 (pub 09:30)
    res_12 = match_forecast_to_actuals(actual_rows, forecast_rows, rule="day_ahead_d1_1200", resolution="hourly")
    assert len(res_12["matched"]) == 1
    assert res_12["matched"][0]["forecast"] == 1000.0
    assert res_12["matched"][0]["publishTime"] == "2026-01-01T09:30:00Z"

    # 2. Standard Day-Ahead Gate (D-1 17:00 UTC) -> must select 2000.0 (pub 15:30)
    res_17 = match_forecast_to_actuals(actual_rows, forecast_rows, rule="day_ahead_d1_1700", resolution="hourly")
    assert len(res_17["matched"]) == 1
    assert res_17["matched"][0]["forecast"] == 2000.0
    assert res_17["matched"][0]["publishTime"] == "2026-01-01T15:30:00Z"

    # 3. Midnight Gate (D-1 23:59 UTC) -> must select 3000.0 (pub 18:30)
    res_23 = match_forecast_to_actuals(actual_rows, forecast_rows, rule="day_ahead_d1_2359", resolution="hourly")
    assert len(res_23["matched"]) == 1
    assert res_23["matched"][0]["forecast"] == 3000.0
    assert res_23["matched"][0]["publishTime"] == "2026-01-01T18:30:00Z"

    # 4. Latest Available Benchmark (Allows look-ahead) -> selects 4000.0 (pub 07:30 intraday)
    res_latest = match_forecast_to_actuals(actual_rows, forecast_rows, rule="latest_available", resolution="hourly")
    assert len(res_latest["matched"]) == 1
    assert res_latest["matched"][0]["forecast"] == 4000.0
    assert res_latest["matched"][0]["publishTime"] == "2026-01-02T07:30:00Z"

def test_duplicate_publications_tie_breaking():
    # Two identical records with identical publishTime and target startTime
    forecast_rows = [
        {"startTime": "2026-01-01T00:00:00Z", "publishTime": "2025-12-31T15:30:00Z", "generation": 8000.0},
        {"startTime": "2026-01-01T00:00:00Z", "publishTime": "2025-12-31T15:30:00Z", "generation": 8000.0},
    ]
    actual_rows = [
        {"startTime": "2026-01-01T00:00:00Z", "generation": 7500.0, "settlementPeriod": 1},
        {"startTime": "2026-01-01T00:30:00Z", "generation": 7500.0, "settlementPeriod": 2},
    ]
    res = match_forecast_to_actuals(actual_rows, forecast_rows, rule="day_ahead_d1_1700")
    # Must produce exactly 1 matched interval without duplicating
    assert len(res["matched"]) == 1
    assert res["matched"][0]["forecast"] == 8000.0
    assert res["matched"][0]["actual"] == 7500.0
    assert res["matched"][0]["error"] == 500.0

def test_rolling_24h_rule():
    # Target delivery: 2026-01-05T14:00:00Z
    # Cutoff is 24h prior: 2026-01-04T14:00:00Z
    forecast_rows = [
        {"startTime": "2026-01-05T14:00:00Z", "publishTime": "2026-01-04T12:00:00Z", "generation": 5000.0}, # Eligible (26h ahead)
        {"startTime": "2026-01-05T14:00:00Z", "publishTime": "2026-01-04T15:00:00Z", "generation": 6000.0}, # Ineligible (23h ahead)
    ]
    actual_rows = [
        {"startTime": "2026-01-05T14:00:00Z", "generation": 4800.0, "settlementPeriod": 29},
        {"startTime": "2026-01-05T14:30:00Z", "generation": 5000.0, "settlementPeriod": 30},
    ]
    res = match_forecast_to_actuals(actual_rows, forecast_rows, rule="rolling_24h")
    assert len(res["matched"]) == 1
    assert res["matched"][0]["forecast"] == 5000.0
    assert res["matched"][0]["publishTime"] == "2026-01-04T12:00:00Z"
