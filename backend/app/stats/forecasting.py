"""
ShiftSense — Forecasting Engine (20XD43 Compliant)
Exponential Smoothing + Day-of-Week Seasonal Index
"""
import math
from typing import List, Optional, Dict


def exponential_smoothing(values: List[float], alpha: float = 0.3) -> List[float]:
    """
    Single Exponential Smoothing: Sₜ = α·yₜ + (1-α)·Sₜ₋₁
    alpha: smoothing factor [0..1]. Higher = more weight on recent obs.
    """
    if not values:
        return []
    smoothed = [values[0]]
    for v in values[1:]:
        smoothed.append(alpha * v + (1 - alpha) * smoothed[-1])
    return smoothed


def seasonal_index(shifts: List[dict]) -> Dict[str, float]:
    """
    Day-of-week seasonal index: ratio of day's avg earnings to overall avg.
    Days: 0=Sun, 1=Mon, ..., 6=Sat
    """
    days = {i: [] for i in range(7)}
    for s in shifts:
        dow = s.get("dow")
        earn = s.get("total_earn", 0)
        if dow is not None and earn is not None:
            try:
                days[int(dow)].append(float(earn))
            except (ValueError, TypeError):
                pass

    day_avgs = {}
    all_vals = []
    for d, vals in days.items():
        if vals:
            avg = sum(vals) / len(vals)
            day_avgs[d] = avg
            all_vals.extend(vals)

    if not all_vals:
        # Return neutral index (1.0 for all days)
        labels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        return {labels[i]: 1.0 for i in range(7)}

    overall_avg = sum(all_vals) / len(all_vals)
    labels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    index = {}
    for i in range(7):
        if i in day_avgs and overall_avg > 0:
            index[labels[i]] = round(day_avgs[i] / overall_avg, 3)
        else:
            index[labels[i]] = 1.0

    return index


def forecast_demand(weekly_data: List[dict], alpha: float = 0.3, periods: int = 7) -> List[dict]:
    """
    Forecast next N periods using exponential smoothing + seasonal adjustment.
    weekly_data: list of {dow, total_earn, total_hours, shift_count}
    """
    if not weekly_data:
        # No data yet — return zero forecast clearly marked as estimate
        labels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        return [{"day": labels[i % 7], "forecast": 0.0, "seasonal_index": 1.0, "is_estimate": True} for i in range(periods)]

    # Sort by dow
    by_dow = {}
    for row in weekly_data:
        dow = row.get("dow")
        earn = row.get("total_earn", 0)
        try:
            dow = int(dow)
            by_dow.setdefault(dow, []).append(float(earn) if earn else 0.0)
        except (TypeError, ValueError):
            pass

    # Build time series (avg per day)
    labels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    dow_avgs = {}
    all_earns = []
    for d in range(7):
        vals = by_dow.get(d, [])
        if vals:
            avg = sum(vals) / len(vals)
            dow_avgs[d] = avg
            all_earns.extend(vals)

    overall = sum(all_earns) / len(all_earns) if all_earns else 0.0

    # Seasonal indices
    s_idx = {}
    for d in range(7):
        if d in dow_avgs and overall > 0:
            s_idx[d] = dow_avgs[d] / overall
        else:
            s_idx[d] = 1.0

    # Smooth the available time series
    ts = [dow_avgs.get(d, overall) for d in range(7)]
    smoothed = exponential_smoothing(ts, alpha)
    base_forecast = smoothed[-1] if smoothed else overall

    forecasts = []
    for i in range(periods):
        dow = i % 7
        adj = base_forecast * s_idx.get(dow, 1.0)
        forecasts.append({
            "day": labels[dow],
            "forecast": round(max(0.0, adj), 0),
            "seasonal_index": round(s_idx.get(dow, 1.0), 3),
        })

    return forecasts


def predict_today(weekly_data: List[dict], today_dow: int = 0) -> dict:
    """
    Predict today's earnings using smoothed forecast + seasonal index.
    """
    forecasts = forecast_demand(weekly_data)
    labels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    today_label = labels[today_dow % 7]

    for f in forecasts:
        if f["day"] == today_label:
            # Compare to yesterday
            yesterday_dow = (today_dow - 1) % 7
            yesterday_label = labels[yesterday_dow]
            yesterday_earn = next((f2["forecast"] for f2 in forecasts if f2["day"] == yesterday_label), f["forecast"])
            pct_change = ((f["forecast"] - yesterday_earn) / max(yesterday_earn, 1)) * 100

            return {
                "day": today_label,
                "predicted": f["forecast"],
                "seasonal_index": f["seasonal_index"],
                "vs_yesterday_pct": round(pct_change, 1),
                "trend": "up" if pct_change > 0 else "down" if pct_change < 0 else "flat",
            }

    return {"day": today_label, "predicted": 0.0, "seasonal_index": 1.0, "vs_yesterday_pct": 0.0, "trend": "flat", "is_estimate": True}
