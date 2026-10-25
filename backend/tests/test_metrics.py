import pytest
import math
from app.metrics import calculate_metrics

def test_empty_records():
    res = calculate_metrics([], expected_intervals=744)
    assert res["count"] == 0
    assert res["expectedCount"] == 744
    assert res["coveragePercent"] == 0.0
    assert res["maeMW"] is None
    assert res["rmseMW"] is None
    assert res["biasMW"] is None
    assert res["wapePercent"] is None
    assert res["smapePercent"] is None
    assert res["nmaePercent"] is None
    assert res["filteredMape"]["includedCount"] == 0

def test_perfect_accuracy():
    records = [
        {"actual": 5000.0, "forecast": 5000.0},
        {"actual": 8000.0, "forecast": 8000.0},
        {"actual": 12000.0, "forecast": 12000.0},
    ]
    res = calculate_metrics(records, expected_intervals=3)
    assert res["count"] == 3
    assert res["coveragePercent"] == 100.0
    assert res["maeMW"] == 0.0
    assert res["rmseMW"] == 0.0
    assert res["biasMW"] == 0.0
    assert res["wapePercent"] == 0.0
    assert res["smapePercent"] == 0.0
    assert res["nmaePercent"] == 0.0
    assert res["filteredMape"]["mapePercent"] == 0.0

def test_constant_over_forecast():
    # Constant 500 MW over-forecast
    records = [
        {"actual": 1000.0, "forecast": 1500.0},
        {"actual": 2000.0, "forecast": 2500.0},
        {"actual": 3000.0, "forecast": 3500.0},
        {"actual": 4000.0, "forecast": 4500.0},
    ]
    res = calculate_metrics(records, expected_intervals=4)
    assert res["maeMW"] == 500.0
    assert res["rmseMW"] == 500.0
    assert res["biasMW"] == 500.0  # Positive bias = over-forecast
    # Total actual = 10000, Total abs error = 2000 -> WAPE = 20.0%
    assert res["wapePercent"] == 20.0

def test_constant_under_forecast():
    # Constant 300 MW under-forecast
    records = [
        {"actual": 1500.0, "forecast": 1200.0},
        {"actual": 2500.0, "forecast": 2200.0},
    ]
    res = calculate_metrics(records)
    assert res["maeMW"] == 300.0
    assert res["rmseMW"] == 300.0
    assert res["biasMW"] == -300.0  # Negative bias = under-forecast

def test_cancelling_errors_bias_vs_mae():
    # Error +1000 and -1000: Bias should be 0, but MAE should be 1000, RMSE 1000
    records = [
        {"actual": 5000.0, "forecast": 6000.0},  # +1000
        {"actual": 5000.0, "forecast": 4000.0},  # -1000
    ]
    res = calculate_metrics(records)
    assert res["biasMW"] == 0.0
    assert res["maeMW"] == 1000.0
    assert res["rmseMW"] == 1000.0

def test_rmse_penalizes_large_miss():
    # Scenario A: two misses of 500 MW -> MAE = 500, RMSE = 500
    res_a = calculate_metrics([
        {"actual": 2000.0, "forecast": 2500.0},
        {"actual": 2000.0, "forecast": 2500.0},
    ])
    # Scenario B: one miss of 0 MW and one miss of 1000 MW -> MAE = 500, RMSE = 707.11
    res_b = calculate_metrics([
        {"actual": 2000.0, "forecast": 2000.0},
        {"actual": 2000.0, "forecast": 3000.0},
    ])
    assert res_a["maeMW"] == res_b["maeMW"] == 500.0
    assert res_b["rmseMW"] > res_a["rmseMW"]
    assert pytest.approx(res_b["rmseMW"], 0.01) == 707.11

def test_near_zero_handling_and_filtered_mape():
    # Calm days with generation near zero: raw division explodes
    records = [
        {"actual": 10.0, "forecast": 50.0},     # Below 100 MW threshold
        {"actual": 500.0, "forecast": 600.0},   # Above 100 MW (err 100 / 500 = 20%)
        {"actual": 1000.0, "forecast": 1100.0}, # Above 100 MW (err 100 / 1000 = 10%)
    ]
    res = calculate_metrics(records, near_zero_threshold_mw=100.0)
    # Filtered MAPE must exclude the 10 MW point
    fm = res["filteredMape"]
    assert fm["includedCount"] == 2
    assert fm["excludedCount"] == 1
    # Average of 20% and 10% = 15.0%
    assert fm["mapePercent"] == 15.0
    # WAPE is stable across all records: total error = 40 + 100 + 100 = 240; total actual = 1510
    assert pytest.approx(res["wapePercent"], 0.01) == round(240 / 1510 * 100.0, 2)
