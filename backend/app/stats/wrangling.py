"""
ShiftSense — Data Wrangling Pipeline (20XD43 Compliant)
IQR-based outlier removal, missing value handling, time normalization.
"""
import re
from typing import List, Tuple, Optional
from datetime import datetime, date


# ── CSV Column Mapping ───────────────────────────────────────────
REQUIRED_COLS = {"zone", "platform", "hours", "earn"}
OPTIONAL_COLS = {"shift_date", "orders", "date_label"}
ALL_COLS = REQUIRED_COLS | OPTIONAL_COLS

COL_ALIASES = {
    "earnings": "earn",
    "earning": "earn",
    "amt": "earn",
    "amount": "earn",
    "hrs": "hours",
    "hour": "hours",
    "duration": "hours",
    "date": "shift_date",
    "shift date": "shift_date",
    "day": "date_label",
}

DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def normalize_column_names(headers: List[str]) -> List[str]:
    """Normalize CSV headers to canonical field names."""
    normalized = []
    for h in headers:
        h_clean = h.strip().lower().replace("-", "_").replace(" ", "_")
        normalized.append(COL_ALIASES.get(h_clean, h_clean))
    return normalized


def parse_date(value: str) -> Optional[str]:
    """Parse various date formats to ISO YYYY-MM-DD."""
    if not value or not str(value).strip():
        return None
    v = str(value).strip()

    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def remove_outliers_iqr(values: List[float], multiplier: float = 1.5) -> Tuple[float, float]:
    """
    IQR-based outlier bounds: [Q1 - 1.5*IQR, Q3 + 1.5*IQR]
    Uses linear interpolation for accurate quartile computation.
    Returns (lower_bound, upper_bound).
    """
    if len(values) < 4:
        return (float("-inf"), float("inf"))

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def percentile(p: float) -> float:
        """Linear interpolation percentile (matches numpy's default)."""
        idx = p * (n - 1)
        lo_i = int(idx)
        hi_i = min(lo_i + 1, n - 1)
        frac = idx - lo_i
        return sorted_vals[lo_i] + frac * (sorted_vals[hi_i] - sorted_vals[lo_i])

    q1 = percentile(0.25)
    q3 = percentile(0.75)
    iqr = q3 - q1

    return (q1 - multiplier * iqr, q3 + multiplier * iqr)


def preprocess(rows: List[dict]) -> Tuple[List[dict], List[dict]]:
    """
    Main wrangling pipeline:
    1. Normalize field names
    2. Validate required fields
    3. Type-cast numeric fields
    4. Handle missing optional fields
    5. Normalize date formats
    6. Remove outliers (IQR on earnings)
    7. Return (clean_rows, error_rows)
    """
    clean = []
    errors = []

    if not rows:
        return clean, errors

    # Collect earnings for outlier detection
    all_earns = []
    parsed_rows = []

    for i, row in enumerate(rows):
        row_num = i + 2  # 1-indexed, accounting for header row
        errs = []

        # Normalize keys
        norm = {COL_ALIASES.get(k.strip().lower(), k.strip().lower()): v for k, v in row.items()}

        # Validate required fields
        zone = str(norm.get("zone", "")).strip()
        if not zone:
            errs.append(f"Row {row_num}: missing zone")

        platform = str(norm.get("platform", "")).strip()
        if not platform:
            errs.append(f"Row {row_num}: missing platform")

        # Validate hours
        try:
            hours = float(str(norm.get("hours", "")).strip())
            if hours <= 0 or hours > 24:
                errs.append(f"Row {row_num}: hours must be 0–24, got {hours}")
                hours = None
        except (ValueError, TypeError):
            errs.append(f"Row {row_num}: invalid hours '{norm.get('hours')}'")
            hours = None

        # Validate earn
        try:
            earn = int(float(str(norm.get("earn", "")).strip()))
            if earn < 0:
                errs.append(f"Row {row_num}: earnings cannot be negative")
                earn = None
        except (ValueError, TypeError):
            errs.append(f"Row {row_num}: invalid earn '{norm.get('earn')}'")
            earn = None

        if errs:
            errors.append({"row": row_num, "errors": errs, "data": row})
            continue

        # Optional fields
        shift_date = parse_date(str(norm.get("shift_date", "")))
        if not shift_date:
            shift_date = datetime.now().strftime("%Y-%m-%d")

        try:
            d = datetime.strptime(shift_date, "%Y-%m-%d")
            # Correct mapping: Mon=1 in Python weekday → Mon in DAYS[1]
            day_map = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
            date_label = day_map.get(d.weekday(), "Mon")
        except Exception:
            date_label = "Mon"

        if norm.get("date_label"):
            dl = str(norm["date_label"]).strip()[:3].capitalize()
            if dl in DAYS:
                date_label = dl

        try:
            orders = int(float(str(norm.get("orders", "0")).strip()))
        except (ValueError, TypeError):
            orders = 0

        clean_row = {
            "zone": zone,
            "platform": platform,
            "hours": hours,
            "earn": earn,
            "orders": max(0, orders),
            "shift_date": shift_date,
            "date_label": date_label,
        }
        parsed_rows.append((row_num, clean_row))
        all_earns.append(earn)

    # Outlier detection — only apply sigma clipping when dataset is large enough
    # For small datasets (< 20 rows), accept all rows that passed validation
    if len(parsed_rows) >= 20:
        all_hours = [r["hours"] for _, r in parsed_rows]
        lower_e, upper_e = remove_outliers_iqr(all_earns)
        lower_h, upper_h = remove_outliers_iqr(all_hours)

        for row_num, row in parsed_rows:
            outlier_reasons = []
            if not (lower_e <= row["earn"] <= upper_e):
                outlier_reasons.append(f"earnings ₹{row['earn']} is a statistical outlier")
            if not (lower_h <= row["hours"] <= upper_h):
                outlier_reasons.append(f"hours {row['hours']} is a statistical outlier")

            if outlier_reasons:
                errors.append({
                    "row": row_num,
                    "errors": [f"Outlier detected: {', '.join(outlier_reasons)}"],
                    "data": row,
                    "is_outlier": True,
                })
            else:
                clean.append(row)
    else:
        # Small dataset: accept all rows that passed validation (0 <= hours <= 24, earn >= 0)
        for row_num, row in parsed_rows:
            if 0 <= row["hours"] <= 24 and row["earn"] >= 0:
                clean.append(row)
            else:
                errors.append({
                    "row": row_num,
                    "errors": [f"Row {row_num}: values out of valid range"],
                    "data": row,
                })

    return clean, errors


def parse_csv_text(csv_text: str) -> Tuple[List[dict], str]:
    """
    Parse raw CSV text into list of dicts.
    Returns (rows, error_message or "").
    """
    lines = [l.strip() for l in csv_text.strip().splitlines() if l.strip()]
    if not lines:
        return [], "CSV is empty"

    # Parse headers
    headers = [h.strip().strip('"') for h in lines[0].split(",")]
    headers = normalize_column_names(headers)

    # Check required columns
    missing = REQUIRED_COLS - set(headers)
    if missing:
        return [], f"Missing required columns: {', '.join(missing)}"

    rows = []
    for line in lines[1:]:
        if not line:
            continue
        # Handle quoted fields
        vals = _parse_csv_line(line)
        if len(vals) < len(headers):
            vals.extend([""] * (len(headers) - len(vals)))
        row = {headers[i]: vals[i].strip().strip('"') for i in range(len(headers))}
        rows.append(row)

    return rows, ""


def _parse_csv_line(line: str) -> List[str]:
    """Parse a single CSV line, respecting quoted fields."""
    result = []
    current = ""
    in_quotes = False
    for ch in line:
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == "," and not in_quotes:
            result.append(current)
            current = ""
        else:
            current += ch
    result.append(current)
    return result
