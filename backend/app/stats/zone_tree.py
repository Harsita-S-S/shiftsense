"""
ShiftSense — Zone Intelligence Engine (20XD43 Compliant)
Decision Tree (CART-inspired) to rank zones by expected earnings.
Pure Python implementation — no sklearn dependency required.
"""
from typing import List, Dict, Optional


DEMAND_WEIGHTS = {"high": 1.3, "medium": 1.0, "low": 0.75}


def zone_decision_tree(
    zone_history: List[dict],
    zone_master: List[dict],
    vehicle: str = "bike",
    hour_of_day: int = 12,
) -> List[dict]:
    """
    CART-style zone ranking using:
    - Historical rate_per_hour (from user's shifts)
    - Zone demand_level from master table
    - Time-of-day match with peak_hours
    - Cluster assignment

    Returns zones sorted by expected_earnings_score DESC.
    """
    # Build history lookup: zone_name → stats
    hist_lookup: Dict[str, dict] = {}
    for h in zone_history:
        z = h.get("zone", "")
        hist_lookup[z] = {
            "rate_per_hour": float(h.get("rate_per_hour", 0) or 0),
            "shift_count": int(h.get("shift_count", 0) or 0),
            "total_earn": float(h.get("total_earn", 0) or 0),
        }

    # Time-of-day bucket
    if 6 <= hour_of_day < 12:
        time_bucket = "morning"
    elif 12 <= hour_of_day < 15:
        time_bucket = "lunch"
    elif 15 <= hour_of_day < 19:
        time_bucket = "afternoon"
    else:
        time_bucket = "evening"

    results = []
    for zone in zone_master:
        name = zone.get("name", "")
        demand = zone.get("demand", "medium").lower()
        master_rate = float(zone.get("rate", 120) or 120)
        peak_hours = str(zone.get("peak_hours", ""))
        cluster = int(zone.get("cluster", 2) or 2)

        # Decision tree node 1: use historical rate if available (depth 1)
        hist = hist_lookup.get(name)
        if hist and hist["shift_count"] >= 3:
            base_rate = hist["rate_per_hour"]
            data_confidence = min(1.0, hist["shift_count"] / 10.0)
        else:
            base_rate = master_rate
            data_confidence = 0.3

        # Decision tree node 2: apply demand multiplier (depth 2)
        # Look up weight using the canonical key BEFORE normalising for the frontend
        demand_mult = DEMAND_WEIGHTS.get(demand, 1.0)
        demand_display = "med" if demand == "medium" else demand  # normalise for frontend
        rate_after_demand = base_rate * demand_mult

        # Decision tree node 3: peak time bonus (depth 3)
        peak_bonus = _peak_bonus(peak_hours, time_bucket)

        # Decision tree node 4: cluster penalty/bonus (depth 4)
        cluster_mult = {1: 1.1, 2: 1.0, 3: 0.85}.get(cluster, 1.0)

        # Composite expected earnings score (per hour)
        expected_rate = rate_after_demand * (1 + peak_bonus) * cluster_mult

        # Blend historical data with master data based on confidence
        if hist and hist["shift_count"] >= 3:
            final_rate = data_confidence * expected_rate + (1 - data_confidence) * master_rate
        else:
            final_rate = expected_rate

        results.append({
            "zone": name,
            "city": zone.get("city", ""),
            "expected_rate": round(final_rate, 1),
            "demand": demand_display,
            "master_rate": master_rate,
            "historical_rate": hist["rate_per_hour"] if hist else None,
            "shift_count": hist["shift_count"] if hist else 0,
            "peak_hours": peak_hours,
            "cluster": cluster,
            "peak_bonus": round(peak_bonus, 2),
            "recommendation_score": round(final_rate, 1),
            "data_source": "historical" if (hist and hist["shift_count"] >= 3) else "master",
        })

    # Sort by recommendation_score DESC
    results.sort(key=lambda x: x["recommendation_score"], reverse=True)

    # Rank them
    for i, r in enumerate(results):
        r["rank"] = i + 1

    return results


def _peak_bonus(peak_hours_str: str, time_bucket: str) -> float:
    """
    Peak-hours matching: rewards zones whose peak aligns with the current
    time bucket and penalises zones that clearly peak at a different time.
    This ensures the ranked list reorders meaningfully across filters.

    Returns a multiplier addend in the range [-0.20, +0.30].
    """
    ph = peak_hours_str.lower()

    # Detect which slot(s) this zone peaks in
    has_am      = "am" in ph
    has_pm      = "pm" in ph
    is_morning   = has_am and not has_pm  # e.g. "8–10 AM"
    is_lunch     = "12" in ph or "lunch" in ph or "1 pm" in ph or "2 pm" in ph or "1\u20132" in ph or "12\u20132" in ph
    is_afternoon = "3 pm" in ph or "4 pm" in ph or "5 pm" in ph or "3\u20135" in ph or "afternoon" in ph
    is_evening   = has_pm and any(t in ph for t in ["6 pm", "7 pm", "8 pm", "9 pm", "10 pm",
                                                     "6\u20139", "7\u201310", "7\u20139", "8\u201310",
                                                     "evening", "night"])

    MATCH    =  0.30   # zone peaks right now
    ADJACENT =  0.05   # zone has no strong peak signal or is adjacent
    MISMATCH = -0.20   # zone clearly peaks at a different time

    if time_bucket == "morning":
        if is_morning:                              return MATCH
        if is_evening or is_lunch:                  return MISMATCH
        return ADJACENT

    if time_bucket == "lunch":
        if is_lunch:                                return MATCH
        if is_evening or is_morning:                return MISMATCH
        return ADJACENT

    if time_bucket == "afternoon":
        if is_afternoon:                            return MATCH
        if is_lunch:                                return ADJACENT
        if is_evening or is_morning:                return MISMATCH
        return ADJACENT

    if time_bucket == "evening":
        if is_evening:                              return MATCH
        if is_afternoon:                            return ADJACENT
        if is_morning or is_lunch:                  return MISMATCH
        return ADJACENT

    return 0.0
