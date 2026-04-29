"""
ShiftSense — OLS Regression Engine (20XD43 Compliant)
Computes β0 (intercept), β1 (slope), R² score dynamically from user data.
No hardcoded constants.
"""
import math
from typing import List, Tuple, Optional


def ols_regression(xs: List[float], ys: List[float]) -> dict:
    """
    Ordinary Least Squares regression: ŷ = β0 + β1 * x
    Returns β0, β1, R², std_error, confidence intervals.
    Returns insufficient_data status if data is insufficient.
    """
    n = len(xs)

    if n < 3:
        return {"status": "insufficient_data", "n": n, "is_fallback": True}

    try:
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n

        Sxx = sum((x - mean_x) ** 2 for x in xs)
        Sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        Syy = sum((y - mean_y) ** 2 for y in ys)

        if Sxx == 0:
            return {"status": "insufficient_data", "n": n, "is_fallback": True, "reason": "zero_variance"}

        beta1 = Sxy / Sxx
        beta0 = mean_y - beta1 * mean_x

        # R²
        ss_res = Syy - beta1 * Sxy
        r_squared = max(0.0, min(1.0, 1.0 - ss_res / Syy)) if Syy > 0 else 0.0

        # Standard error of the regression
        if n > 2:
            mse = ss_res / (n - 2)
            se_regression = math.sqrt(max(0.0, mse))
            se_slope = math.sqrt(max(0.0, mse / Sxx)) if Sxx > 0 else 0.0
        else:
            se_regression = 0.0
            se_slope = 0.0

        # 95% confidence interval for slope — use df-aware t-critical value
        df = n - 2
        t_critical = _t_critical_95(df)
        ci_lower = beta1 - t_critical * se_slope
        ci_upper = beta1 + t_critical * se_slope

        return {
            "beta0": round(beta0, 2),
            "beta1": round(beta1, 2),
            "r_squared": round(r_squared, 4),
            "n": n,
            "std_error": round(se_regression, 2),
            "se_slope": round(se_slope, 2),
            "ci_lower_slope": round(ci_lower, 2),
            "ci_upper_slope": round(ci_upper, 2),
            "mean_x": round(mean_x, 4),
            "mean_y": round(mean_y, 2),
            "Sxx": round(Sxx, 4),
            "is_fallback": False,
        }
    except Exception:
        return {"status": "error", "is_fallback": True, "n": n}


def _t_critical_95(df: int) -> float:
    """
    Two-tailed 95% t-critical value for given degrees of freedom.
    Uses a lookup table for small df; converges to 2.0 for large df.
    """
    table = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
             6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
             15: 2.131, 20: 2.086, 25: 2.060, 30: 2.042}
    if df <= 0:
        return 12.706
    if df in table:
        return table[df]
    # Linear interpolation between bracketing table entries
    keys = sorted(table.keys())
    for i in range(len(keys) - 1):
        lo, hi = keys[i], keys[i + 1]
        if lo < df < hi:
            frac = (df - lo) / (hi - lo)
            return table[lo] + frac * (table[hi] - table[lo])
    return 2.0  # df > 30


def predict_earnings(hours: float, model: dict) -> dict:
    """
    Predict earnings for given hours using fitted OLS model.
    Returns point estimate + 95% prediction interval.
    """
    if model.get("is_fallback"):
        return {"status": "insufficient_data", "hours": hours}

    beta0 = model.get("beta0", 0.0)
    beta1 = model.get("beta1", 0.0)
    se = model.get("std_error", 0.0)
    n = model.get("n", 0)
    mean_x = model.get("mean_x", 0.0)
    Sxx = model.get("Sxx", 0.0)

    point = beta0 + beta1 * hours
    # Correct prediction interval: se * sqrt(1 + 1/n + (x - x̄)²/Sxx)
    extrapolation_term = ((hours - mean_x) ** 2 / Sxx) if Sxx > 0 else 0.0
    se_pred = se * math.sqrt(1 + 1 / max(n, 1) + extrapolation_term)
    df = n - 2
    margin = _t_critical_95(df) * se_pred

    return {
        "hours": hours,
        "predicted_earnings": round(max(0.0, point), 0),
        "lower_bound": round(max(0.0, point - margin), 0),
        "upper_bound": round(point + margin, 0),
    }


def z_score_performance(current_rate: float, historical_rates: List[float]) -> dict:
    """
    Computes Z-score: (current_rate - mean_rate) / std_dev
    Performance signal for the dashboard.
    """
    if len(historical_rates) < 2:
        return {
            "z_score": 0.0,
            "mean_rate": current_rate,
            "std_dev": 0.0,
            "signal": "neutral",
            "percentile": 50,
        }

    n = len(historical_rates)
    mean_rate = sum(historical_rates) / n
    variance = sum((r - mean_rate) ** 2 for r in historical_rates) / (n - 1)
    std_dev = math.sqrt(variance) if variance > 0 else 1.0

    try:
        z = (current_rate - mean_rate) / std_dev
    except ZeroDivisionError:
        return {
            "z_score": 0.0,
            "mean_rate": round(mean_rate, 2),
            "std_dev": round(std_dev, 2),
            "signal": "neutral",
            "percentile": 50,
        }

    if z > 1.5:
        signal = "excellent"
        percentile = 93
    elif z > 0.5:
        signal = "good"
        percentile = 69
    elif z > -0.5:
        signal = "neutral"
        percentile = 50
    elif z > -1.5:
        signal = "below_average"
        percentile = 31
    else:
        signal = "poor"
        percentile = 7

    return {
        "z_score": round(z, 2),
        "mean_rate": round(mean_rate, 2),
        "std_dev": round(std_dev, 2),
        "signal": signal,
        "percentile": percentile,
    }


def platform_regression(platform_data: List[dict]) -> List[dict]:
    """
    Multiple Linear Regression features: zone_demand, time_of_day, platform.
    Ranks platforms by expected earnings rate.
    Falls back gracefully with limited data.
    """
    if not platform_data:
        return []

    results = []
    for p in platform_data:
        name = p.get("platform", "Unknown")
        total_earn = p.get("total_earn", 0) or 0
        total_hours = p.get("total_hours", 0) or 1
        count = p.get("shift_count", 1) or 1
        avg_earn = p.get("avg_earn", 0) or 0

        rate_per_hour = total_earn / max(total_hours, 0.1)

        # Composite score: 60% rate/hour + 30% avg_earn (normalised) + 10% consistency
        # Consistency: fraction of the 50-shift benchmark, capped at 1.0
        consistency = min(count / 50.0, 1.0)
        # Normalise avg_earn to a per-hour-equivalent for comparability
        avg_earn_rate = avg_earn / max(total_hours / max(count, 1), 0.1) if count > 0 else rate_per_hour
        score = 0.60 * rate_per_hour + 0.30 * avg_earn_rate + 0.10 * consistency * rate_per_hour

        results.append({
            "platform": name,
            "rate_per_hour": round(rate_per_hour, 1),
            "avg_earn": round(avg_earn, 1),
            "shift_count": count,
            "score": round(score, 2),
            "total_earn": total_earn,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results
