# UK Wind Forecast Workbench (January 2026)

A production-grade full-stack forecasting intelligence application built for UK energy utility trading and risk management desks. The system quantitatively evaluates the accuracy of National Energy System Operator (NESO) wind generation forecasts against outturn actual generation across the entire month of **January 2026**, strictly eliminating look-ahead bias to reflect actionable day-ahead market purchasing decisions.

---

## 1. Domain Context & Decision Rules

In Great Britain's electricity market (governed by the Balancing and Settlement Code / Elexon), day-ahead physical and financial commitments occur before gate closure and auction deadlines on day $D-1$:
- **EPEX SPOT / Nord Pool UK Day-Ahead Auction**: Closes at **12:00 UTC** (11:00 auction gate).
- **Post-Auction Scheduling & Final Day-Ahead Nomination Gate**: Finalized by **17:00 UTC** on day $D-1$.
- **Day-Ahead Midnight Boundary**: Pre-delivery day cutoff at **23:59 UTC** on day $D-1$.

### Look-Ahead Bias Prevention
Evaluating forecast accuracy by naively taking the "latest published forecast" introduces severe **look-ahead bias** because it incorporates intraday weather forecasts released hours or minutes before delivery. 

This workbench enforces strict decision-gate filtering:
$$\text{For delivery on Date } D \text{ at hour } T, \quad \text{Eligible Forecasts} = \{ f \in \text{WINDFOR} : \text{publishTime} \le \text{GateCutoff}(D) \}$$
The system selects the latest forecast available to the trader **on or before the chosen market gate cutoff**:
1. **`day_ahead_d1_1700` (Default)**: Post-auction day-ahead nomination gate ($D-1$ at 17:00:00 UTC).
2. **`day_ahead_d1_1200`**: Day-ahead power auction gate ($D-1$ at 12:00:00 UTC).
3. **`day_ahead_d1_2359`**: Pre-delivery day midnight gate ($D-1$ at 23:59:59 UTC).
4. **`rolling_24h`**: Fixed horizon gate ($\text{publishTime} \le T - 24\text{ hours}$).
5. **`latest_available` (Benchmark)**: Latest published forecast regardless of publication time, explicitly provided to demonstrate the look-ahead distortion penalty.

### Interval Alignment (Hourly vs Half-Hourly)
- **Forecast Stream (`WINDFOR`)**: Published at hourly target intervals ($H:00:00\text{Z}$) in average MW.
- **Actual Generation (`FUELHH`)**: Published at half-hourly settlement periods ($H:00:00\text{Z}$ and $H:30:00\text{Z}$) in average MW.
- **Hourly Alignment Rule**: To prevent data distortion or dropping half the dataset, the hourly actual generation is calculated as the exact arithmetic average of the two 30-minute settlement periods:
  $$\text{Actual}_{\text{hourly}}(H) = \frac{\text{FUELHH}(H:00) + \text{FUELHH}(H:30)}{2}$$
- **Data Integrity**: Missing data is **never treated as zero**. Unmatched intervals are transparently tracked and surfaced in the audit interface.

---

## 2. Accuracy Metrics

| Metric | Formula | Definition & Energy Market Rationale |
| :--- | :--- | :--- |
| **MAE** | $\frac{1}{N} \sum \|F_i - A_i\|$ | Mean Absolute Error (MW). Quantifies average unbalance volume. |
| **RMSE** | $\sqrt{\frac{1}{N} \sum (F_i - A_i)^2}$ | Root Mean Squared Error (MW). Penalizes extreme volumetric forecasting blunders. |
| **Bias** | $\frac{1}{N} \sum (F_i - A_i)$ | Mean Forecast Bias (MW). Positive indicates systemic over-forecasting; negative indicates systemic under-forecasting. |
| **WAPE** | $\frac{\sum \|F_i - A_i\|}{\sum A_i} \times 100\%$ | Weighted Absolute Percentage Error (%). Energy trading industry standard; immune to near-zero actual generation divisions. |
| **sMAPE** | $\frac{100\%}{N} \sum \frac{2\|F_i - A_i\|}{\|F_i\| + \|A_i\|}$ | Symmetric Mean Absolute Percentage Error (%). Bounded between 0% and 200%. |
| **nMAE** | $\frac{\text{MAE}}{\bar{A}} \times 100\%$ | Normalized MAE relative to mean outturn generation. |
| **Filtered MAPE** | $\frac{100\%}{\|K\|} \sum_{i \in K} \frac{\|F_i - A_i\|}{A_i}$ | Traditional MAPE evaluated exclusively for intervals where $A_i \ge 100\text{ MW}$. Excluded calm intervals are explicitly reported. |
| **Coverage** | $\frac{N_{\text{matched}}}{N_{\text{expected}}} \times 100\%$ | Ratio of successfully matched intervals against the 744 target hours of January 2026. |

---

## 3. Verified January 2026 Results (Live Elexon Data)

Evaluated across all **744 hours (1,488 half-hourly settlement periods)** of January 2026:

| Decision Gate | Matched Hours | Coverage | MAE (MW) | RMSE (MW) | Bias (MW) | WAPE (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Day-Ahead (D-1 17:00 UTC)** | **744 / 744** | **100.0%** | **1,980.9 MW** | **2,443.2 MW** | **+1,816.9 MW** | **17.10%** |
| **Day-Ahead (D-1 12:00 UTC)** | 744 / 744 | 100.0% | 2,058.4 MW | 2,529.7 MW | +1,878.2 MW | 17.77% |
| **Day-Ahead (D-1 23:59 UTC)** | 744 / 744 | 100.0% | 1,936.5 MW | 2,398.6 MW | +1,780.4 MW | 16.72% |
| **Latest Available (Look-Ahead Benchmark)** | 744 / 744 | 100.0% | 1,766.9 MW | 2,217.4 MW | +1,634.5 MW | 15.26% |

> **Key Trading Takeaway**: Incorporating intraday updates (look-ahead benchmark) artificially flatters MAE by **~214 MW** and WAPE by **~1.84%**. Day-ahead procurement models must use the **D-1 17:00** or **D-1 12:00** metrics to avoid under-hedging imbalance risk.

---

## 4. Architecture & File Structure

```
wind-forecast-workbench/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py           # Environment variables & CORS settings
│   │   ├── elexon_client.py    # Elexon BMRS API client with retries & caching
│   │   ├── matching.py         # Look-ahead bias prevention & interval alignment
│   │   ├── metrics.py          # MAE, RMSE, Bias, WAPE, sMAPE, nMAE, Filtered MAPE
│   │   └── main.py             # FastAPI REST endpoints
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_api.py         # Endpoint & error-handling integration tests
│   │   ├── test_matching.py    # Look-ahead gate & deduplication unit tests
│   │   ├── test_metrics.py     # Quantitative metric calculation unit tests
│   │   └── test_missing_data.py# Missing data & audit verification unit tests
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── main.jsx            # React dashboard (KPIs, Recharts, filterable audit)
│   │   └── style.css           # Energy intelligence dark-theme styling
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── Dockerfile
├── docker-compose.yml
├── .gitignore
└── README.md
```

---

## 5. Quickstart & Local Setup

### Prerequisites
- Node.js 18+ (Node 22 LTS recommended)
- Python 3.11+
- (Optional) Docker Desktop

### Option A: Run with Docker Compose (Recommended)
```bash
docker compose up --build
```
- **Frontend Dashboard**: [http://localhost:5173](http://localhost:5173)
- **Backend API & Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/api/health](http://localhost:8000/api/health)

### Option B: Run Locally (VS Code / CLI)

**1. Backend Setup:**
```bash
cd backend
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
# source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**2. Frontend Setup:**
```bash
cd frontend
npm install
npm run dev
```

---

## 6. Automated Backend Tests

The automated test suite runs offline with mocked API responses (satisfying challenge constraint #7) covering metrics calculation, look-ahead bias rejection, duplicate publication handling, missing data handling, and upstream 502/504 errors.

Run the test suite:
```bash
cd backend
python -m pytest tests/ -v
```

Expected output:
```
tests/test_api.py::test_health_endpoint PASSED
tests/test_api.py::test_decision_rules_endpoint PASSED
tests/test_api.py::test_actual_endpoint PASSED
tests/test_api.py::test_forecast_endpoint PASSED
tests/test_api.py::test_analysis_endpoint_success PASSED
tests/test_api.py::test_analysis_invalid_rule PASSED
tests/test_api.py::test_analysis_invalid_resolution PASSED
tests/test_api.py::test_analysis_upstream_error_handling PASSED
tests/test_matching.py::test_aggregate_actuals_hourly PASSED
tests/test_matching.py::test_incomplete_hour_actuals_flagged PASSED
tests/test_matching.py::test_look_ahead_bias_decision_gates PASSED
tests/test_matching.py::test_duplicate_publications_tie_breaking PASSED
tests/test_matching.py::test_rolling_24h_rule PASSED
tests/test_metrics.py::test_empty_records PASSED
tests/test_metrics.py::test_perfect_accuracy PASSED
tests/test_metrics.py::test_constant_over_forecast PASSED
tests/test_metrics.py::test_constant_under_forecast PASSED
tests/test_metrics.py::test_cancelling_errors_bias_vs_mae PASSED
tests/test_metrics.py::test_rmse_penalizes_large_miss PASSED
tests/test_metrics.py::test_near_zero_handling_and_filtered_mape PASSED
tests/test_missing_data.py::test_missing_forecast_not_treated_as_zero PASSED
tests/test_missing_data.py::test_missing_actual_not_treated_as_zero PASSED
======================== 22 passed in 2.14s ========================
```

---

## 7. Deployment Instructions

### Backend (Render / Railway / Fly.io / AWS)
1. Deploy `backend` as a Docker web service using the included `Dockerfile`.
2. Configure environment variables:
   - `ALLOWED_ORIGINS`: Comma-separated list of allowed frontend domains (e.g. `https://wind-forecast-workbench.vercel.app`).
   - `ELEXON_API_BASE`: `https://data.elexon.co.uk/bmrs/api/v1`
   - `CACHE_ENABLED`: `true`
3. Health check path: `/api/health`.

### Frontend (Vercel / Netlify / Cloudflare Pages)
1. Set the root directory to `frontend`.
2. Build command: `npm run build`.
3. Output directory: `dist`.
4. Environment variable:
   - `VITE_API_BASE`: Set to the deployed backend URL (e.g., `https://your-backend.onrender.com`).

---

## 8. Known Limitations & Operating Notes

1. **Transmission vs Embedded Wind**:
   - Elexon BMRS `FUELHH` and `WINDFOR` capture transmission-system-metered generation (Power Park Modules visible to NESO). Embedded distributed wind connected to distribution networks is not fully captured in FUELHH transmission metering.
2. **Fixed Historical Window**:
   - This application is configured specifically for January 2026. The backend client caches January 2026 immutable results for sub-10ms response times, while providing a `Live Refresh` bypass parameter to query Elexon live on demand.

---

## 9. AI Assistance Disclosure

In accordance with REint challenge rules, AI assistance was utilized during development:
- Google Antigravity (Advanced Agentic Coding) assisted in querying Elexon OpenAPI documentation, auditing timestamp semantics between FUELHH and WINDFOR, structuring automated pytest test cases, and implementing the frontend diurnal and error distribution visualizations.
- All code, decision gates, mathematical formulas, and live Elexon data integrations have been strictly audited and tested by the engineer.
