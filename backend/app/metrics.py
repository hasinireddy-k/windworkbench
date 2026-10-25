import math
from typing import Any, Dict, List, Optional

def calculate_metrics(
    matched_records: List[Dict[str, Any]],
    expected_intervals: Optional[int] = None,
    near_zero_threshold_mw: float = 100.0,
) -> Dict[str, Any]:
    """
    Calculate quantitative forecast accuracy metrics over matched target intervals.
    Never invents data or treats missing intervals as zero.

    Metrics:
    - MAE: Mean Absolute Error (MW)
    - RMSE: Root Mean Squared Error (MW)
    - Bias: Mean forecast error (Forecast - Actual, in MW). Positive = over-forecast.
    - WAPE: Weighted Absolute Percentage Error (sum(|error|) / sum(actual) * 100).
      Standard in energy trading; robust against near-zero division.
    - sMAPE: Symmetric Mean Absolute Percentage Error (%).
    - nMAE: Normalized MAE by mean actual generation (MAE / mean(actual) * 100).
    - Filtered MAPE: Traditional MAPE evaluated only for intervals where actual >= near_zero_threshold_mw.
      Explicitly reports the number of included and excluded intervals.
    - Coverage: Matched intervals / expected intervals (%).
    """
    n = len(matched_records)
    if n == 0:
        return {
            "count": 0,
            "expectedCount": expected_intervals,
            "coveragePercent": 0.0 if expected_intervals and expected_intervals > 0 else None,
            "maeMW": None,
            "rmseMW": None,
            "biasMW": None,
            "wapePercent": None,
            "smapePercent": None,
            "nmaePercent": None,
            "filteredMape": {
                "mapePercent": None,
                "thresholdMW": near_zero_threshold_mw,
                "includedCount": 0,
                "excludedCount": 0,
            },
            "meanActualMW": None,
            "meanForecastMW": None,
            "maxErrorMW": None,
            "minErrorMW": None,
        }

    sum_abs_err = 0.0
    sum_sq_err = 0.0
    sum_err = 0.0
    sum_actual = 0.0
    sum_forecast = 0.0
    sum_smape = 0.0
    smape_count = 0

    filtered_mape_sum = 0.0
    filtered_included = 0
    filtered_excluded = 0

    errors = []

    for r in matched_records:
        actual = float(r["actual"])
        forecast = float(r["forecast"])
        err = forecast - actual
        abs_err = abs(err)

        errors.append(err)
        sum_err += err
        sum_abs_err += abs_err
        sum_sq_err += err * err
        sum_actual += actual
        sum_forecast += forecast

        # sMAPE: 200 * |F - A| / (|F| + |A|)
        denom_smape = abs(forecast) + abs(actual)
        if denom_smape > 1e-6:
            sum_smape += (2.0 * abs_err / denom_smape)
            smape_count += 1

        # Filtered MAPE
        if actual >= near_zero_threshold_mw:
            filtered_mape_sum += (abs_err / actual)
            filtered_included += 1
        else:
            filtered_excluded += 1

    mae = sum_abs_err / n
    rmse = math.sqrt(sum_sq_err / n)
    bias = sum_err / n
    mean_actual = sum_actual / n
    mean_forecast = sum_forecast / n

    # WAPE
    wape = (sum_abs_err / sum_actual * 100.0) if sum_actual > 1e-6 else None

    # sMAPE
    smape = (sum_smape / smape_count * 100.0) if smape_count > 0 else None

    # nMAE
    nmae = (mae / mean_actual * 100.0) if mean_actual > 1e-6 else None

    # Filtered MAPE
    filtered_mape_val = (
        (filtered_mape_sum / filtered_included * 100.0)
        if filtered_included > 0
        else None
    )

    coverage_pct = (
        (n / expected_intervals * 100.0)
        if expected_intervals and expected_intervals > 0
        else None
    )

    return {
        "count": n,
        "expectedCount": expected_intervals,
        "coveragePercent": round(coverage_pct, 2) if coverage_pct is not None else None,
        "maeMW": round(mae, 2),
        "rmseMW": round(rmse, 2),
        "biasMW": round(bias, 2),
        "wapePercent": round(wape, 2) if wape is not None else None,
        "smapePercent": round(smape, 2) if smape is not None else None,
        "nmaePercent": round(nmae, 2) if nmae is not None else None,
        "filteredMape": {
            "mapePercent": round(filtered_mape_val, 2) if filtered_mape_val is not None else None,
            "thresholdMW": near_zero_threshold_mw,
            "includedCount": filtered_included,
            "excludedCount": filtered_excluded,
        },
        "meanActualMW": round(mean_actual, 2),
        "meanForecastMW": round(mean_forecast, 2),
        "maxErrorMW": round(max(errors), 2) if errors else None,
        "minErrorMW": round(min(errors), 2) if errors else None,
    }
