from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

DECISION_RULES: Dict[str, Dict[str, str]] = {
    "day_ahead_d1_1700": {
        "name": "Day-Ahead (D-1 17:00 UTC)",
        "description": "Standard UK post-auction / final day-ahead nomination gate. For delivery date D, selects the latest forecast published on or before D-1 at 17:00:00 UTC.",
        "type": "day_ahead",
    },
    "day_ahead_d1_1200": {
        "name": "Day-Ahead Auction (D-1 12:00 UTC)",
        "description": "UK Day-Ahead power auction gate (EPEX SPOT / N2EX). Selects latest forecast published on or before D-1 at 12:00:00 UTC.",
        "type": "day_ahead",
    },
    "day_ahead_d1_2359": {
        "name": "Day-Ahead Midnight (D-1 23:59 UTC)",
        "description": "Pre-delivery day cutoff. Selects latest forecast published on or before D-1 at 23:59:59 UTC (prior to start of delivery day).",
        "type": "day_ahead",
    },
    "rolling_24h": {
        "name": "Rolling 24-Hour Ahead",
        "description": "Forecast must be published at least 24 hours prior to the target delivery interval start time (publishTime <= startTime - 24h).",
        "type": "rolling",
    },
    "latest_available": {
        "name": "Latest Available (Intraday Benchmark)",
        "description": "Intraday benchmark with look-ahead bias: selects the latest published forecast for the interval, even if published during or after delivery.",
        "type": "benchmark",
    },
}

def parse_iso(ts_str: str) -> datetime:
    """Parse ISO8601 timestamp string into timezone-aware UTC datetime."""
    s = ts_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def format_iso(dt: datetime) -> str:
    """Format datetime as UTC ISO8601 string ending with Z."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def get_cutoff_for_target(target_dt: datetime, rule: str) -> Optional[datetime]:
    """
    Compute the latest permissible publishTime for a target delivery interval under the given decision rule.
    Returns None if no cutoff is applied (e.g. latest_available benchmark).
    """
    if rule == "day_ahead_d1_1700":
        delivery_date = target_dt.date()
        d_minus_1 = delivery_date - timedelta(days=1)
        return datetime(d_minus_1.year, d_minus_1.month, d_minus_1.day, 17, 0, 0, tzinfo=timezone.utc)
    elif rule == "day_ahead_d1_1200":
        delivery_date = target_dt.date()
        d_minus_1 = delivery_date - timedelta(days=1)
        return datetime(d_minus_1.year, d_minus_1.month, d_minus_1.day, 12, 0, 0, tzinfo=timezone.utc)
    elif rule == "day_ahead_d1_2359":
        delivery_date = target_dt.date()
        d_minus_1 = delivery_date - timedelta(days=1)
        return datetime(d_minus_1.year, d_minus_1.month, d_minus_1.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    elif rule == "rolling_24h":
        return target_dt - timedelta(hours=24)
    elif rule == "latest_available":
        return None
    else:
        # Default fallback
        delivery_date = target_dt.date()
        d_minus_1 = delivery_date - timedelta(days=1)
        return datetime(d_minus_1.year, d_minus_1.month, d_minus_1.day, 17, 0, 0, tzinfo=timezone.utc)

def aggregate_actuals_hourly(
    actual_rows: List[Dict[str, Any]],
    start_filter: Optional[str] = None,
    end_filter: Optional[str] = None,
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """
    Aggregate half-hourly actuals (FUELHH) into 1-hour intervals.
    In GB power market, each hour comprises two 30-minute settlement periods (:00 and :30).
    Average MW is (G_00 + G_30) / 2.
    Returns:
    - dict of hour_iso -> {'generation': avg_mw, 'periods': [r1, r2], 'is_complete': bool}
    - list of partial/incomplete hour timestamps
    """
    hour_buckets: Dict[str, List[Dict[str, Any]]] = {}

    start_dt = parse_iso(start_filter) if start_filter else None
    end_dt = parse_iso(end_filter) if end_filter else None

    for r in actual_rows:
        try:
            ts_dt = parse_iso(r["startTime"])
            if start_dt and ts_dt < start_dt:
                continue
            if end_dt and ts_dt >= end_dt:
                continue

            hour_dt = datetime(ts_dt.year, ts_dt.month, ts_dt.day, ts_dt.hour, 0, 0, tzinfo=timezone.utc)
            hour_key = format_iso(hour_dt)
            hour_buckets.setdefault(hour_key, []).append(r)
        except (KeyError, ValueError):
            continue

    aggregated: Dict[str, Dict[str, Any]] = {}
    incomplete_hours: List[str] = []

    for hour_key, rows in sorted(hour_buckets.items()):
        # Deduplicate rows by startTime within hour if duplicates exist
        by_start = {}
        for row in rows:
            by_start[row["startTime"]] = row

        valid_rows = list(by_start.values())
        if len(valid_rows) == 2:
            avg_gen = sum(float(x["generation"]) for x in valid_rows) / 2.0
            aggregated[hour_key] = {
                "startTime": hour_key,
                "generation": round(avg_gen, 2),
                "halfHoursCount": 2,
                "settlementPeriods": [x.get("settlementPeriod") for x in valid_rows],
                "isComplete": True,
            }
        else:
            # Partial hour - record as incomplete so we never invent or misrepresent data
            incomplete_hours.append(hour_key)
            if len(valid_rows) > 0:
                avg_gen = sum(float(x["generation"]) for x in valid_rows) / len(valid_rows)
                aggregated[hour_key] = {
                    "startTime": hour_key,
                    "generation": round(avg_gen, 2),
                    "halfHoursCount": len(valid_rows),
                    "settlementPeriods": [x.get("settlementPeriod") for x in valid_rows],
                    "isComplete": False,
                }

    return aggregated, incomplete_hours

def match_forecast_to_actuals(
    actual_rows: List[Dict[str, Any]],
    forecast_rows: List[Dict[str, Any]],
    rule: str = "day_ahead_d1_1700",
    resolution: str = "hourly",
    start_filter: Optional[str] = None,
    end_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Match WINDFOR forecasts to FUELHH actuals without look-ahead bias according to the specified decision rule.

    Handles:
    - Multiple forecast publications for the same target interval
    - Decision gate cutoff enforcement
    - Tie-breaking duplicate forecast publications
    - Hourly aggregation (averaging two half-hours) or half-hourly resolution
    - Explicit tracking of unmatched and partial records
    """
    if rule not in DECISION_RULES:
        rule = "day_ahead_d1_1700"

    rule_info = DECISION_RULES[rule]

    start_dt = parse_iso(start_filter) if start_filter else None
    end_dt = parse_iso(end_filter) if end_filter else None

    # 1. Group forecasts by target startTime (normalized to ISO)
    # Target startTime in WINDFOR is the beginning of the 1-hour forecast interval
    forecasts_by_target: Dict[str, List[Dict[str, Any]]] = {}
    for f in forecast_rows:
        try:
            target_ts = format_iso(parse_iso(f["startTime"]))
            f_norm = {
                "targetStartTime": target_ts,
                "publishTime": format_iso(parse_iso(f["publishTime"])),
                "publishDateTime": parse_iso(f["publishTime"]),
                "generation": float(f["generation"]),
                "raw": f,
            }
            forecasts_by_target.setdefault(target_ts, []).append(f_norm)
        except (KeyError, ValueError, TypeError):
            continue

    # 2. Select forecast for each target hour according to decision rule
    selected_forecast_by_hour: Dict[str, Dict[str, Any]] = {}
    for target_ts, candidates in forecasts_by_target.items():
        target_dt = parse_iso(target_ts)
        cutoff_dt = get_cutoff_for_target(target_dt, rule)

        if cutoff_dt is not None:
            eligible = [c for c in candidates if c["publishDateTime"] <= cutoff_dt]
        else:
            eligible = candidates

        if eligible:
            # Pick latest publication before cutoff
            # For duplicates with identical publishDateTime, pick the last encountered
            best = max(eligible, key=lambda x: (x["publishDateTime"], id(x)))
            selected_forecast_by_hour[target_ts] = {
                "forecastMW": round(best["generation"], 2),
                "publishTime": best["publishTime"],
                "cutoffTime": format_iso(cutoff_dt) if cutoff_dt else None,
                "availableCandidatesCount": len(eligible),
                "totalPublicationsForTarget": len(candidates),
            }

    matched: List[Dict[str, Any]] = []
    unmatched_actuals: List[Dict[str, Any]] = []
    unmatched_forecasts: List[Dict[str, Any]] = []

    if resolution == "hourly":
        # Hourly actuals
        aggregated_act, incomplete_hours = aggregate_actuals_hourly(
            actual_rows, start_filter=start_filter, end_filter=end_filter
        )

        all_target_hours = sorted(set(aggregated_act.keys()) | set(selected_forecast_by_hour.keys()))
        if start_dt or end_dt:
            all_target_hours = [
                h for h in all_target_hours
                if (not start_dt or parse_iso(h) >= start_dt) and (not end_dt or parse_iso(h) < end_dt)
            ]

        for hour_ts in all_target_hours:
            act_info = aggregated_act.get(hour_ts)
            fc_info = selected_forecast_by_hour.get(hour_ts)

            if act_info is not None and fc_info is not None:
                act_val = act_info["generation"]
                fc_val = fc_info["forecastMW"]
                err = fc_val - act_val
                abs_err = abs(err)
                pct_err = (abs_err / act_val * 100.0) if act_val > 1e-6 else None

                matched.append({
                    "startTime": hour_ts,
                    "targetInterval": f"{hour_ts[:16]} UTC (1 hour)",
                    "actual": act_val,
                    "forecast": fc_val,
                    "error": round(err, 2),
                    "absoluteError": round(abs_err, 2),
                    "percentageError": round(pct_err, 2) if pct_err is not None else None,
                    "publishTime": fc_info["publishTime"],
                    "cutoffTime": fc_info["cutoffTime"],
                    "isCompleteActual": act_info.get("isComplete", True),
                })
            elif act_info is not None and fc_info is None:
                unmatched_actuals.append({
                    "startTime": hour_ts,
                    "actual": act_info["generation"],
                    "reason": f"No forecast published on or before decision cutoff ({rule_info['name']})",
                })
            elif act_info is None and fc_info is not None:
                unmatched_forecasts.append({
                    "startTime": hour_ts,
                    "forecast": fc_info["forecastMW"],
                    "publishTime": fc_info["publishTime"],
                    "reason": "No actual generation recorded for this interval",
                })

    else:
        # Half-hourly resolution
        # Match each settlement period directly with its hourly forecast
        act_by_ts: Dict[str, Dict[str, Any]] = {}
        for r in actual_rows:
            try:
                ts = format_iso(parse_iso(r["startTime"]))
                if start_dt and parse_iso(ts) < start_dt:
                    continue
                if end_dt and parse_iso(ts) >= end_dt:
                    continue
                act_by_ts[ts] = r
            except (KeyError, ValueError):
                continue

        for ts, act_row in sorted(act_by_ts.items()):
            ts_dt = parse_iso(ts)
            hour_dt = datetime(ts_dt.year, ts_dt.month, ts_dt.day, ts_dt.hour, 0, 0, tzinfo=timezone.utc)
            hour_ts = format_iso(hour_dt)

            fc_info = selected_forecast_by_hour.get(hour_ts)
            act_val = float(act_row["generation"])

            if fc_info is not None:
                fc_val = fc_info["forecastMW"]
                err = fc_val - act_val
                abs_err = abs(err)
                pct_err = (abs_err / act_val * 100.0) if act_val > 1e-6 else None

                matched.append({
                    "startTime": ts,
                    "targetInterval": f"{ts[:16]} UTC (SP {act_row.get('settlementPeriod', '?')})",
                    "actual": round(act_val, 2),
                    "forecast": fc_val,
                    "error": round(err, 2),
                    "absoluteError": round(abs_err, 2),
                    "percentageError": round(pct_err, 2) if pct_err is not None else None,
                    "publishTime": fc_info["publishTime"],
                    "cutoffTime": fc_info["cutoffTime"],
                    "settlementPeriod": act_row.get("settlementPeriod"),
                })
            else:
                unmatched_actuals.append({
                    "startTime": ts,
                    "actual": round(act_val, 2),
                    "reason": f"No forecast published on or before decision cutoff ({rule_info['name']})",
                })

    return {
        "rule": rule,
        "ruleInfo": rule_info,
        "resolution": resolution,
        "matched": matched,
        "unmatchedActuals": unmatched_actuals,
        "unmatchedForecasts": unmatched_forecasts,
    }
