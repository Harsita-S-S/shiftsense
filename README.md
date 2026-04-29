# ShiftSense v5 — Production-Grade Predictive Analytics

> Gig-economy earnings intelligence platform, refactored to a **hybrid Node.js + FastAPI architecture** with a full 20XD43-compliant analytical engine. Zero hardcoded constants. Zero breakage of existing functionality.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Browser / Mobile App                        │
│           (Dashboard, Shifts, Zones, Analytics, Predict)        │
└───────────────────────┬─────────────────────────────────────────┘
                        │  HTTP
          ┌─────────────▼──────────────┐
          │    Node.js (Port 3000)     │
          │    Express + SQLite3       │
          │                            │
          │  /api/v1/*  → handled here │
          │  /api/v2/*  → proxied ─────┼──► FastAPI (Port 3001)
          │  /static    → HTML/CSS/JS  │     Python analytics engine
          └────────────────────────────┘
                        │
                        ▼
              ┌──────────────────┐
              │   shiftsense.db  │  ← Shared SQLite database
              │   (SQLite3)      │    read by BOTH servers
              └──────────────────┘
```

### Why Hybrid?
- **Zero breakage**: Node.js continues serving ALL existing v1 endpoints unchanged
- **Safe migration**: FastAPI adds capabilities without touching existing code
- **Graceful fallback**: If FastAPI is offline, the UI falls back to safe defaults (no crash)
- **Same DB**: Both servers read the same `shiftsense.db` file

---

## Project Structure

```
shiftsense_v5/
│
├── start.sh                   # Linux/Mac startup (both servers)
├── start.bat                  # Windows startup
├── requirements.txt           # Python deps (FastAPI, uvicorn)
│
├── backend/                   # FastAPI Analytics Engine (NEW)
│   └── app/
│       ├── main.py            # FastAPI app + all /api/v2 routes
│       └── stats/
│           ├── regression.py  # OLS: β0, β1, R², prediction intervals
│           ├── forecasting.py # Exponential Smoothing + Seasonal Index
│           ├── wrangling.py   # IQR outlier removal, normalization, CSV parsing
│           └── zone_tree.py   # CART Decision Tree for zone ranking
│
└── frontend/                  # Node.js + Static HTML (PRESERVED)
    ├── server.js              # Express backend (v1 API, unchanged + v2 proxy)
    ├── config.js              # Updated: adds fetchV2() helper + v2 probe
    ├── predict.html           # Updated: live OLS, forecast, z-score, CART
    ├── dashboard.html         # UNCHANGED ✓
    ├── shifts.html            # UNCHANGED ✓
    ├── zones.html             # UNCHANGED ✓
    ├── analytics.html         # UNCHANGED ✓
    ├── history.html           # UNCHANGED ✓
    ├── index.html             # UNCHANGED ✓
    ├── shared.css             # UNCHANGED ✓
    └── seed_data.js           # UNCHANGED ✓
```

---

## Quick Start

### Option 1: Automatic (recommended)
```bash
# Linux / Mac
bash start.sh

# Windows
start.bat
```

### Option 2: Manual

**Terminal 1 — FastAPI analytics engine:**
```bash
pip install -r requirements.txt
uvicorn backend.app.main:app --port 3001 --reload
```

**Terminal 2 — Node.js backend + frontend:**
```bash
cd frontend
npm install
node server.js
# or: npm start
```

Open http://localhost:3000

---

## API Reference

### v1 Endpoints (Node.js — UNCHANGED)
All existing endpoints work exactly as before:

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Register new user |
| POST | `/api/auth/login` | Login |
| GET | `/api/auth/me` | Get profile |
| PUT | `/api/auth/profile` | Update profile |
| GET | `/api/shifts` | List shifts |
| POST | `/api/shifts` | Add shift |
| PUT | `/api/shifts/:id` | Update shift |
| DELETE | `/api/shifts/:id` | Delete shift |
| POST | `/api/shifts/bulk` | Bulk import (JSON) |
| GET | `/api/shifts/stats` | Earnings summary |
| GET | `/api/zones` | Zone list |
| GET | `/api/platforms` | Platform list |
| GET | `/api/analytics/weekly` | Weekly breakdown |
| GET | `/api/analytics/by-platform` | Per-platform stats |
| GET | `/api/analytics/by-zone` | Per-zone stats |

### v2 Endpoints (FastAPI — NEW)
All new endpoints follow the SAME auth pattern as v1:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v2/analytics/regression` | OLS: β0, β1, R² from user data |
| GET | `/api/v2/analytics/predict?hours=5` | Predict earnings for N hours |
| GET | `/api/v2/analytics/forecast` | 7-day exponential smoothing forecast |
| GET | `/api/v2/analytics/today` | Today's predicted earnings |
| GET | `/api/v2/analytics/performance` | Z-score vs historical rates |
| GET | `/api/v2/analytics/platforms` | MLR platform ranking |
| GET | `/api/v2/analytics/zones?hour_of_day=12` | CART zone ranking |
| GET | `/api/v2/analytics/dashboard` | All analytics in one call |
| POST | `/api/v2/shifts/bulk` | Bulk CSV import with wrangling |
| POST | `/api/v2/shifts/bulk-json` | Bulk JSON import |
| GET | `/api/v2/health` | Health check |

---

## Analytical Models (20XD43 Compliance)

### 1. Earnings Estimator — OLS Regression
```
ŷ = β₀ + β₁ × hours
```
- β₀ (intercept) and β₁ (slope) computed from user's actual shifts
- R² score, standard error, 95% confidence intervals
- Falls back to `β₀=42, β₁=138` only if < 3 shifts exist
- File: `backend/app/stats/regression.py` → `ols_regression()`

### 2. Forecast System — Exponential Smoothing
```
Sₜ = α·yₜ + (1-α)·Sₜ₋₁
```
- α = 0.3 (configurable via `?alpha=0.3`)
- Day-of-week seasonal index: each day's ratio to overall average
- File: `backend/app/stats/forecasting.py` → `forecast_demand()`

### 3. Platform Ranking — MLR Proxy
- Features: rate/hour (60%), avg earning (30%), consistency (10%)
- Composite score ranks platforms dynamically
- File: `backend/app/stats/regression.py` → `platform_regression()`

### 4. Performance Signal — Z-Score
```
Z = (current_rate - mean_rate) / std_dev
```
- Signals: excellent (Z>1.5), good (Z>0.5), neutral, below_average, poor
- Percentile mapping for UX display
- File: `backend/app/stats/regression.py` → `z_score_performance()`

### 5. Zone Intelligence — CART Decision Tree
Decision nodes (depth 4):
1. Historical rate available? → use it (weighted by confidence)
2. Apply demand multiplier: high=1.3×, medium=1.0×, low=0.75×
3. Peak-time bonus: evening surge (+0.25), lunch (+0.2)
4. Cluster adjustment: cluster 1=1.1×, cluster 2=1.0×, cluster 3=0.85×

- File: `backend/app/stats/zone_tree.py` → `zone_decision_tree()`

---

## Data Wrangling Pipeline

`POST /api/v2/shifts/bulk` accepts raw CSV:

```csv
zone,platform,hours,earn,shift_date
Koramangala,Swiggy,4.5,680,2024-01-15
Indiranagar,Zomato,6,920,2024-01-16
```

Pipeline steps:
1. **Column normalization** — aliases: `earnings→earn`, `hrs→hours`, `date→shift_date`
2. **Required field validation** — zone, platform, hours, earn
3. **Type casting** — hours (float), earn (int)
4. **Date normalization** — supports DD-MM-YYYY, YYYY-MM-DD, etc.
5. **IQR outlier removal** — earnings and hours outside Q1–1.5×IQR / Q3+1.5×IQR
6. **Response format**: `{ accepted: N, rejected: M, errors: [...], outliers_removed: K }`

---

## No Hardcoded Constants

| Old (Hardcoded) | New (Dynamic) |
|----------------|---------------|
| `B0 = 42` | Computed via OLS from user's shifts |
| `B1 = 138` | Computed via OLS from user's shifts |
| `Rate = 180` | Pulled from zones DB or computed from history |
| Fixed 7-day forecast | Exponential smoothing on actual weekly data |
| Static platform colors | Fetched from platforms table |

Safe defaults are used ONLY when insufficient data exists (< 3 shifts), and the UI explicitly marks them as estimates.

---

## Environment Variables

```bash
# Node.js server
PORT=3000               # Default: 3000
JWT_SECRET=your-secret  # REQUIRED in production
DB_PATH=./shiftsense.db # Default: ./shiftsense.db
FASTAPI_URL=http://localhost:3001  # FastAPI URL for proxy

# FastAPI server (reads same env vars)
JWT_SECRET=your-secret  # Must match Node.js
DB_PATH=./shiftsense.db # Must point to same DB
```

---

## Changelog: v4 → v5

### Added
- ✅ FastAPI backend (`backend/`) with full analytics engine
- ✅ `/api/v2` proxy in Node.js server (graceful fallback if offline)
- ✅ OLS regression engine (pure Python, no sklearn required)
- ✅ Exponential smoothing forecaster with seasonal index
- ✅ CART-style zone decision tree
- ✅ Z-score performance signal
- ✅ MLR platform ranking
- ✅ Full CSV wrangling pipeline (IQR outlier removal)
- ✅ `POST /api/v2/shifts/bulk` — CSV import with wrangling
- ✅ `config.js` updated: `fetchV2()` helper + v2 availability probe
- ✅ `predict.html` updated: all analytics pulled live from v2 API

### Preserved (Unchanged)
- ✅ All v1 Node.js endpoints — same request/response format
- ✅ `dashboard.html`, `shifts.html`, `zones.html`, `analytics.html`, `history.html`
- ✅ `index.html` (login/register page)
- ✅ `shared.css` — layout, colors, components identical
- ✅ SQLite schema — same tables, same columns
- ✅ JWT auth flow — same tokens, same middleware

---

## Production Deployment Notes

1. Set `JWT_SECRET` as environment variable (never use default in production)
2. Both servers must use the same `DB_PATH` and `JWT_SECRET`
3. Use a process manager (PM2 / systemd) to keep both servers running
4. Consider nginx to proxy both servers behind a single domain
5. For high traffic: migrate SQLite → PostgreSQL (both FastAPI and Node.js support it)
