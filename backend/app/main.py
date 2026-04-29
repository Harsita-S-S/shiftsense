"""
ShiftSense — FastAPI Analytics Backend (v2)
/api/v2 endpoints — runs PARALLEL to existing Node.js /api/v1 backend.
Provides ML/stats endpoints without breaking existing functionality.

Run with:  uvicorn backend.app.main:app --port 3001 --reload
"""
from __future__ import annotations
import json
import sqlite3
import os
from datetime import datetime
from typing import List, Optional, Any
from contextlib import asynccontextmanager

try:
    from fastapi import FastAPI, Header, HTTPException, Depends, Body, Query
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

from .stats.regression import ols_regression, predict_earnings, z_score_performance, platform_regression
from .stats.forecasting import forecast_demand, predict_today, seasonal_index
from .stats.wrangling import preprocess, parse_csv_text
from .stats.zone_tree import zone_decision_tree


# ── Database helpers ──────────────────────────────────────────────
DB_PATH = os.environ.get("DB_PATH", "./shiftsense.db")


def get_db():
    """Get raw SQLite connection (shares DB with Node.js backend)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def db_all(sql: str, params: tuple = ()) -> List[dict]:
    conn = get_db()
    try:
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def db_get(sql: str, params: tuple = ()) -> Optional[dict]:
    conn = get_db()
    try:
        cursor = conn.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def db_run(sql: str, params: tuple = ()):
    conn = get_db()
    try:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


# ── JWT verification (mirrors Node.js logic) ──────────────────────
import jwt as pyjwt

JWT_SECRET = os.environ.get("JWT_SECRET", "")
_JWT_FALLBACK = "shiftsense-dev-secret-change-in-prod"

if not JWT_SECRET:
    JWT_SECRET = _JWT_FALLBACK
    print(
        "\n[SECURITY WARNING] JWT_SECRET environment variable is NOT set.\n"
        "  Using insecure default secret — safe for local dev only.\n"
        "  Set JWT_SECRET before any public or production deployment.\n"
        "  Example:  set JWT_SECRET=your-strong-random-secret-here\n"
    )


def get_user_id(authorization: str = Header(default="")) -> int:
    """Extract user ID from Authorization header using PyJWT."""
    if not authorization.startswith("Bearer "):
        raise ValueError("No token")
    token = authorization[7:]
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        raise ValueError("Invalid token")
    uid = payload.get("id")
    if uid is None:
        raise ValueError("Invalid token payload")
    return uid


# ── FastAPI App ───────────────────────────────────────────────────
if FASTAPI_AVAILABLE:
    app = FastAPI(
        title="ShiftSense Analytics API v2",
        description="20XD43-compliant predictive analytics for gig workers",
        version="2.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Pydantic Models ──────────────────────────────────────────
    class BulkShiftCSV(BaseModel):
        csv_text: str = Field(..., description="Raw CSV content as string")

    class BulkShiftJSON(BaseModel):
        shifts: List[dict]

    # ── Helper: get auth user ────────────────────────────────────
    def auth_user(request_auth: str) -> int:
        try:
            return get_user_id(request_auth)
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or missing token")


    # ════════════════════════════════════════════════════════════
    # ANALYTICS ROUTES  /api/v2/analytics/*
    # ════════════════════════════════════════════════════════════

    @app.get("/api/v2/analytics/regression")
    def get_regression(authorization: str = Header(default="")):
        """
        OLS Regression: hours → earnings
        Returns β0, β1, R², prediction interval.
        """
        uid = auth_user(authorization)
        shifts = db_all(
            "SELECT hours, earn FROM shifts WHERE user_id = ? AND hours > 0",
            (uid,)
        )
        xs = [float(s["hours"]) for s in shifts]
        ys = [float(s["earn"]) for s in shifts]
        model = ols_regression(xs, ys)
        if model.get("status") == "insufficient_data":
            return {"status": "insufficient_data", "total_shifts": len(xs)}
        return {"model": model, "formula": f"Ŷ = ₹{model['beta0']} + ₹{model['beta1']} × Hours"}

    @app.get("/api/v2/analytics/predict")
    def get_prediction(hours: float = 5.0, authorization: str = Header(default="")):
        """Predict earnings for given hours using OLS model."""
        uid = auth_user(authorization)
        shifts = db_all(
            "SELECT hours, earn FROM shifts WHERE user_id = ? AND hours > 0",
            (uid,)
        )
        xs = [float(s["hours"]) for s in shifts]
        ys = [float(s["earn"]) for s in shifts]
        model = ols_regression(xs, ys)
        return predict_earnings(hours, model)

    @app.get("/api/v2/analytics/forecast")
    def get_forecast(alpha: float = 0.3, authorization: str = Header(default="")):
        """
        Exponential Smoothing + Day-of-Week Seasonal Index forecast.
        Returns predicted earnings per day for next 7 days.
        """
        uid = auth_user(authorization)
        rows = db_all(
            """SELECT strftime('%w', shift_date) AS dow,
                      SUM(earn)  AS total_earn,
                      SUM(hours) AS total_hours,
                      COUNT(*)   AS shift_count
               FROM shifts WHERE user_id = ?
               GROUP BY dow
               ORDER BY CAST(dow AS INTEGER)""",
            (uid,)
        )
        s_idx = seasonal_index(rows)
        forecasts = forecast_demand(rows, alpha=alpha)
        return {"forecasts": forecasts, "seasonal_index": s_idx, "alpha": alpha}

    @app.get("/api/v2/analytics/today")
    def get_today_forecast(authorization: str = Header(default="")):
        """Predict today's earnings."""
        uid = auth_user(authorization)
        # IMPORTANT: Python's weekday() returns Mon=0..Sun=6
        # SQLite strftime('%w') returns Sun=0..Sat=6
        # We convert Python → SQLite convention: (weekday + 1) % 7
        today_dow = datetime.now().weekday()  # Mon=0, Tue=1, ..., Sun=6
        sun_based = (today_dow + 1) % 7       # Sun=0, Mon=1, ..., Sat=6  ← matches SQLite
        rows = db_all(
            """SELECT strftime('%w', shift_date) AS dow,
                      SUM(earn) AS total_earn, SUM(hours) AS total_hours,
                      COUNT(*) AS shift_count
               FROM shifts WHERE user_id = ?
               GROUP BY dow
               ORDER BY CAST(dow AS INTEGER)""",
            (uid,)
        )
        return predict_today(rows, sun_based)

    @app.get("/api/v2/analytics/performance")
    def get_performance(authorization: str = Header(default="")):
        """
        Z-score performance signal: (current_rate - mean) / std_dev.
        Compares last shift rate to historical average.
        """
        uid = auth_user(authorization)
        shifts = db_all(
            """SELECT earn, hours FROM shifts
               WHERE user_id = ? AND hours > 0
               ORDER BY shift_date DESC, created_at DESC""",
            (uid,)
        )
        if not shifts:
            return {"z_score": 0.0, "signal": "neutral", "percentile": 50, "message": "No data yet"}

        rates = [float(s["earn"]) / max(float(s["hours"]), 0.1) for s in shifts]
        current_rate = rates[0]
        historical = rates[1:] if len(rates) > 1 else rates

        result = z_score_performance(current_rate, historical)
        result["current_rate"] = round(current_rate, 1)
        result["last_shift_earn"] = shifts[0]["earn"]
        result["last_shift_hours"] = shifts[0]["hours"]
        return result

    @app.get("/api/v2/analytics/platforms")
    def get_platform_ranking(authorization: str = Header(default="")):
        """
        Platform ranking using Multiple Linear Regression proxy.
        Ranks platforms by expected earnings rate.
        """
        uid = auth_user(authorization)
        rows = db_all(
            """SELECT platform, COUNT(*) AS shift_count,
                      SUM(earn) AS total_earn, SUM(hours) AS total_hours,
                      AVG(earn) AS avg_earn
               FROM shifts WHERE user_id = ?
               GROUP BY platform ORDER BY total_earn DESC""",
            (uid,)
        )
        return {"rankings": platform_regression(rows)}

    @app.get("/api/v2/analytics/zones")
    def get_zone_ranking(hour_of_day: int = 12, authorization: str = Header(default="")):
        """
        Zone Intelligence: CART-style decision tree ranking zones
        by expected earnings based on history + demand + time.
        """
        uid = auth_user(authorization)
        user = db_get("SELECT city, vehicle FROM users WHERE id = ?", (uid,))
        city = user["city"] if user else None

        zone_history = db_all(
            """SELECT zone,
                      COUNT(*) AS shift_count,
                      SUM(earn) AS total_earn,
                      SUM(hours) AS total_hours,
                      ROUND(SUM(earn)*1.0/SUM(hours), 1) AS rate_per_hour
               FROM shifts WHERE user_id = ? AND hours > 0
               GROUP BY zone ORDER BY rate_per_hour DESC""",
            (uid,)
        )

        if city:
            zone_master = db_all(
                "SELECT * FROM zones WHERE city = ? ORDER BY demand DESC, rate DESC",
                (city,)
            )
        else:
            zone_master = db_all("SELECT * FROM zones ORDER BY city, demand DESC, rate DESC")

        vehicle = user["vehicle"] if user else "bike"
        rankings = zone_decision_tree(zone_history, zone_master, vehicle, hour_of_day)
        return {"rankings": rankings, "city": city, "hour_of_day": hour_of_day}

    @app.get("/api/v2/analytics/dashboard")
    def get_dashboard_analytics(authorization: str = Header(default="")):
        """
        Consolidated dashboard analytics payload.
        Single request to power the entire dashboard efficiently.
        """
        uid = auth_user(authorization)
        # IMPORTANT: Python weekday() is Mon=0; SQLite strftime('%w') is Sun=0
        # Convert: (weekday + 1) % 7  →  Sun=0..Sat=6 to match DB values
        today_dow = (datetime.now().weekday() + 1) % 7  # Sun=0, Mon=1, ..., Sat=6

        shifts = db_all(
            "SELECT hours, earn FROM shifts WHERE user_id = ? AND hours > 0",
            (uid,)
        )
        xs = [float(s["hours"]) for s in shifts]
        ys = [float(s["earn"]) for s in shifts]
        model = ols_regression(xs, ys)

        weekly = db_all(
            """SELECT strftime('%w', shift_date) AS dow,
                      SUM(earn) AS total_earn, SUM(hours) AS total_hours,
                      COUNT(*) AS shift_count
               FROM shifts WHERE user_id = ?
               GROUP BY dow
               ORDER BY CAST(dow AS INTEGER)""",
            (uid,)
        )

        today_pred = predict_today(weekly, today_dow)

        rates = [ys[i] / max(xs[i], 0.1) for i in range(len(xs))] if xs else []
        perf = z_score_performance(rates[0] if rates else 0, rates[1:] if len(rates) > 1 else rates)

        platform_data = db_all(
            """SELECT platform, COUNT(*) AS shift_count,
                      SUM(earn) AS total_earn, SUM(hours) AS total_hours,
                      AVG(earn) AS avg_earn
               FROM shifts WHERE user_id = ?
               GROUP BY platform ORDER BY total_earn DESC""",
            (uid,)
        )

        # ── peak_hour: day with highest forecast from weekly data ──
        forecasts = forecast_demand(weekly)
        peak_hour = None
        if forecasts:
            peak = max(forecasts, key=lambda f: f.get("forecast", 0))
            peak_hour = {
                "day": peak.get("day"),
                "forecast": round(peak.get("forecast", 0), 1),
                "seasonal_index": round(peak.get("seasonal_index", 1.0), 3),
            }

        # ── best_windows: top 3 zone rankings (current hour) ──────
        current_hour = datetime.now().hour
        user = db_get("SELECT city, vehicle FROM users WHERE id = ?", (uid,))
        city = user["city"] if user else None
        vehicle = user["vehicle"] if user else "bike"

        zone_history = db_all(
            """SELECT zone,
                      COUNT(*) AS shift_count,
                      SUM(earn) AS total_earn,
                      SUM(hours) AS total_hours,
                      ROUND(SUM(earn)*1.0/SUM(hours), 1) AS rate_per_hour
               FROM shifts WHERE user_id = ? AND hours > 0
               GROUP BY zone ORDER BY rate_per_hour DESC""",
            (uid,)
        )
        if city:
            zone_master = db_all(
                "SELECT * FROM zones WHERE city = ? ORDER BY demand DESC, rate DESC",
                (city,)
            )
        else:
            zone_master = db_all("SELECT * FROM zones ORDER BY city, demand DESC, rate DESC")

        all_zone_rankings = zone_decision_tree(zone_history, zone_master, vehicle, current_hour)
        best_windows = all_zone_rankings[:3] if all_zone_rankings else []

        base_response = {
            "regression": model,
            "today_forecast": today_pred,
            "performance": perf,
            "platform_rankings": platform_regression(platform_data),
            "peak_hour": peak_hour,
            "best_windows": best_windows,
        }
        if model.get("status") == "insufficient_data":
            base_response["model_status"] = "insufficient_data"
        else:
            base_response["formula"] = f"Ŷ = ₹{model['beta0']} + ₹{model['beta1']} × Hours | R² = {model['r_squared']}"
        return base_response


    # ════════════════════════════════════════════════════════════
    # BULK IMPORT  /api/v2/shifts/bulk
    # Maintains SAME response format as Node.js /api/shifts/bulk
    # ════════════════════════════════════════════════════════════

    @app.post("/api/v2/shifts/bulk")
    async def bulk_import_csv(
        payload: BulkShiftCSV,
        authorization: str = Header(default=""),
    ):
        """
        Accept CSV text, wrangle with pandas-style pipeline,
        validate, and insert. Returns {accepted, rejected, errors}.
        """
        uid = auth_user(authorization)

        user = db_get("SELECT platforms FROM users WHERE id = ?", (uid,))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        try:
            user_platforms = json.loads(user.get("platforms", "[]") or "[]")
        except Exception:
            user_platforms = []
        default_platform = user_platforms[0] if user_platforms else "Other"

        rows, parse_err = parse_csv_text(payload.csv_text)
        if parse_err:
            return JSONResponse(
                status_code=400,
                content={"error": parse_err, "accepted": 0, "rejected": 0, "errors": [parse_err]}
            )

        if not rows:
            return {"accepted": 0, "rejected": 0, "errors": ["No valid rows found in CSV"]}

        if len(rows) > 1000:
            return JSONResponse(
                status_code=400,
                content={"error": "Maximum 1000 rows per import", "accepted": 0, "rejected": len(rows), "errors": []}
            )

        clean_rows, error_rows = preprocess(rows)

        inserted = 0
        insert_errors = []

        conn = get_db()
        try:
            for row in clean_rows:
                platform = row.get("platform") or default_platform
                conn.execute(
                    """INSERT INTO shifts
                       (user_id, zone, platform, hours, earn, orders, predicted, date_label, shift_date)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (uid, row["zone"], platform, row["hours"], row["earn"],
                     row.get("orders", 0), 0, row.get("date_label", "Mon"),
                     row.get("shift_date", datetime.now().strftime("%Y-%m-%d")))
                )
                inserted += 1
            conn.commit()
        except Exception as e:
            insert_errors.append(f"Database error: {str(e)}")
        finally:
            conn.close()

        # Format errors for response (max 20)
        formatted_errors = []
        for e in error_rows[:20]:
            if isinstance(e.get("errors"), list):
                formatted_errors.extend(e["errors"])
            else:
                formatted_errors.append(str(e))

        return {
            "accepted": inserted,
            "rejected": len(error_rows),
            "errors": (formatted_errors + insert_errors)[:20],
            "total": len(rows) + len(error_rows),
            "outliers_removed": sum(1 for e in error_rows if e.get("is_outlier")),
        }

    @app.post("/api/v2/shifts/bulk-json")
    async def bulk_import_json(payload: BulkShiftJSON, authorization: str = Header(default="")):
        """JSON version of bulk import (same as Node.js /api/shifts/bulk format)."""
        uid = auth_user(authorization)
        user = db_get("SELECT platforms FROM users WHERE id = ?", (uid,))
        default_platform = "Other"
        if user:
            try:
                ps = json.loads(user.get("platforms", "[]") or "[]")
                default_platform = ps[0] if ps else "Other"
            except Exception:
                pass

        if not payload.shifts:
            raise HTTPException(status_code=400, detail="No shifts provided")
        if len(payload.shifts) > 1000:
            raise HTTPException(status_code=400, detail="Maximum 1000 shifts per import")

        clean_rows, error_rows = preprocess(payload.shifts)
        inserted = 0
        conn = get_db()
        try:
            for row in clean_rows:
                conn.execute(
                    """INSERT INTO shifts
                       (user_id, zone, platform, hours, earn, orders, predicted, date_label, shift_date)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (uid, row["zone"], row.get("platform") or default_platform,
                     row["hours"], row["earn"], row.get("orders", 0), 0,
                     row.get("date_label", "Mon"),
                     row.get("shift_date", datetime.now().strftime("%Y-%m-%d")))
                )
                inserted += 1
            conn.commit()
        finally:
            conn.close()

        return {
            "inserted": inserted,
            "accepted": inserted,
            "rejected": len(error_rows),
            "errors": [str(e.get("errors", "")) for e in error_rows[:20]],
            "total": len(payload.shifts),
        }


    # ── Health Check ─────────────────────────────────────────────
    @app.get("/api/v2/health")
    def health():
        return {
            "status": "ok",
            "version": "2.0.0",
            "analytics": True,
            "timestamp": datetime.now().isoformat(),
        }

else:
    # Fallback if FastAPI not installed — print instructions
    print("FastAPI not available. Install with: pip install fastapi uvicorn")
