import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from fastapi import HTTPException
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["targetPeriod"] == "January 2026"

def test_decision_rules_endpoint():
    res = client.get("/api/decision-rules")
    assert res.status_code == 200
    data = res.json()
    assert "day_ahead_d1_1700" in data["rules"]
    assert "day_ahead_d1_1200" in data["rules"]
    assert "latest_available" in data["rules"]
    assert data["default"] == "day_ahead_d1_1700"

@patch("app.main.get_actual_generation", new_callable=AsyncMock)
def test_actual_endpoint(mock_get_actual):
    mock_get_actual.return_value = [
        {"dataset": "FUELHH", "startTime": "2026-01-01T00:00:00Z", "publishTime": "2026-01-01T00:30:00Z", "settlementDate": "2026-01-01", "settlementPeriod": 1, "fuelType": "WIND", "generation": 12000.0}
    ]
    res = client.get("/api/actual?from_date=2026-01-01&to_date=2026-01-01")
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "Elexon BMRS FUELHH stream"
    assert data["count"] == 1
    assert data["data"][0]["generation"] == 12000.0

@patch("app.main.get_forecast_generation", new_callable=AsyncMock)
def test_forecast_endpoint(mock_get_forecast):
    mock_get_forecast.return_value = [
        {"dataset": "WINDFOR", "startTime": "2026-01-01T00:00:00Z", "publishTime": "2025-12-31T15:30:00Z", "generation": 12500.0}
    ]
    res = client.get("/api/forecast")
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "Elexon BMRS WINDFOR stream"
    assert data["count"] == 1
    assert data["data"][0]["generation"] == 12500.0

@patch("app.main.get_forecast_generation", new_callable=AsyncMock)
@patch("app.main.get_actual_generation", new_callable=AsyncMock)
def test_analysis_endpoint_success(mock_get_actual, mock_get_forecast):
    mock_get_actual.return_value = [
        {"dataset": "FUELHH", "startTime": "2026-01-01T00:00:00Z", "publishTime": "2026-01-01T00:30:00Z", "settlementDate": "2026-01-01", "settlementPeriod": 1, "fuelType": "WIND", "generation": 10000.0},
        {"dataset": "FUELHH", "startTime": "2026-01-01T00:30:00Z", "publishTime": "2026-01-01T01:00:00Z", "settlementDate": "2026-01-01", "settlementPeriod": 2, "fuelType": "WIND", "generation": 10000.0},
    ]
    mock_get_forecast.return_value = [
        {"dataset": "WINDFOR", "startTime": "2026-01-01T00:00:00Z", "publishTime": "2025-12-31T15:30:00Z", "generation": 10800.0}
    ]
    res = client.get("/api/analysis?decision_rule=day_ahead_d1_1700&resolution=hourly")
    assert res.status_code == 200
    data = res.json()
    assert data["counts"]["matchedIntervals"] == 1
    assert data["metrics"]["maeMW"] == 800.0
    assert data["metrics"]["biasMW"] == 800.0
    assert len(data["dailyProfile"]) == 1
    assert len(data["data"]) == 1

def test_analysis_invalid_rule():
    res = client.get("/api/analysis?decision_rule=unknown_rule")
    assert res.status_code == 400
    assert "Invalid decision_rule" in res.json()["detail"]

def test_analysis_invalid_resolution():
    res = client.get("/api/analysis?resolution=secondly")
    assert res.status_code == 400
    assert "Invalid resolution" in res.json()["detail"]

@patch("app.main.get_actual_generation", new_callable=AsyncMock)
def test_analysis_upstream_error_handling(mock_get_actual):
    mock_get_actual.side_effect = HTTPException(status_code=502, detail="Elexon returned HTTP 502")
    res = client.get("/api/analysis")
    assert res.status_code == 502
    assert "Elexon returned HTTP 502" in res.json()["detail"]
