# ShiftSense v4 — Setup Guide

## Quick Start

```bash
npm install
node seed_data.js     # seeds DB with demo user + 14 days of shifts
node server.js        # starts server on http://localhost:3000
```

Then open **http://localhost:3000** in your browser.

## Demo Login
- **Phone:** 9999999999  
- **Password:** demo1234

## Environment Variables

All configuration is driven by environment variables — no hardcoded values:

| Variable | Default | Description |
|---|---|---|
| `PORT` | `3000` | HTTP server port |
| `JWT_SECRET` | *(insecure dev default)* | **Set this in production!** |
| `DB_PATH` | `./shiftsense.db` | SQLite database file path |
| `SEED_PHONE` | `9999999999` | Demo user phone |
| `SEED_PASSWORD` | `demo1234` | Demo user password |
| `SEED_NAME` | `Aarav Kumar` | Demo user name |
| `SEED_CITY` | `Coimbatore` | Demo user city |
| `SEED_PLATFORM` | `Swiggy` | Demo user primary platform |
| `SEED_TARGET` | `5000` | Demo user weekly earnings target ₹ |

Example production start:
```bash
PORT=8080 JWT_SECRET=my-super-secret-key node server.js
```

## Supported Cities & Zones

Zones are stored in the database and loaded dynamically. Supported cities out of the box:
- Bengaluru, Coimbatore, Chennai, Hyderabad, Mumbai, Delhi, Pune, Kolkata

**Adding a new city:** Insert rows into the `zones` table:
```sql
INSERT INTO zones (city, name, lat, lng, demand, rate, peak_hours, cluster)
VALUES ('Mysuru', 'Vijayanagar', 12.3051, 76.6551, 'medium', 130, '7-9 PM', 1);
```

The app will automatically show the new city in the registration dropdown and zone heatmap.

## CSV Bulk Import

Go to **Shifts** page → **📥 Import CSV**

Required columns: `zone, platform, hours, earn`  
Optional columns: `orders, predicted, shift_date` (YYYY-MM-DD), `date_label`

Maximum 1,000 shifts per import.

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/register` | — | Create account |
| `POST` | `/api/auth/login` | — | Login |
| `GET` | `/api/auth/me` | ✓ | Get current user |
| `PUT` | `/api/auth/profile` | ✓ | Update profile |
| `PUT` | `/api/auth/password` | ✓ | Change password |
| `GET` | `/api/shifts` | ✓ | Get shifts (filterable) |
| `POST` | `/api/shifts` | ✓ | Log a shift |
| `PUT` | `/api/shifts/:id` | ✓ | Edit a shift |
| `DELETE` | `/api/shifts/:id` | ✓ | Delete a shift |
| `POST` | `/api/shifts/bulk` | ✓ | Bulk import shifts |
| `GET` | `/api/shifts/stats` | ✓ | Summary statistics |
| `GET` | `/api/zones?city=X` | ✓ | Get zones for a city |
| `GET` | `/api/zones/cities` | — | List all cities |
| `GET` | `/api/platforms` | — | List all platforms |
| `GET` | `/api/analytics/weekly` | ✓ | Weekly earnings by day |
| `GET` | `/api/analytics/by-platform` | ✓ | Earnings breakdown by platform |
| `GET` | `/api/analytics/by-zone` | ✓ | Rate per hour by zone |
| `GET` | `/api/health` | — | Health check |

## What Changed in v4

### Hardcoded Values Removed
- **API URL** — all pages now use `window.location.origin + '/api'` (works on any host/port)
- **Default city** — was hardcoded `'Bengaluru'` everywhere; now uses first city from DB
- **Default platform** — was hardcoded `'Swiggy'`; now uses user's registered platform
- **Default target** — was `₹5000` hardcoded in client; now always read from user profile
- **Demo credentials** — configurable via environment variables
- **Day-average fallbacks** — were `[620,680,710,740,920,1080,780]`; now computed from actual user data
- **Seasonal index** — now computed from real shifts, not static guesses
- **Logit model** — coefficients are now window-level variables, ready for per-user calibration

### New API Routes
- `PUT /api/shifts/:id` — edit existing shifts
- `GET /api/shifts/stats` — aggregate statistics
- `GET /api/zones` + `GET /api/zones/cities` — zones served from DB, not hardcoded JS
- `GET /api/platforms` — platforms served from DB
- `GET /api/analytics/weekly|by-platform|by-zone` — server-side aggregation
- `GET /api/health` — health check for monitoring

### New Database Tables
- `zones` — city/zone data with lat/lng, demand, rate, peak hours
- `platforms` — platform list with colors/icons

### Bug Fixes
- Phone numbers normalized to digits on registration and login (prevents duplicate account issues with formatting differences)
- `currentPw` verification added to password change endpoint
- Shift edit (`PUT /api/shifts/:id`) now fully implemented
- `config.js` shared across all pages — no more per-file URL duplication
- Default platform in shift creation now falls back to user's first registered platform (not hardcoded 'Swiggy')
- History and analytics tables no longer show 'Swiggy' for shifts with missing platform

### Architecture
```
User action → HTML page JS
  → config.js (dynamic API URL)
  → apiFetch() + Bearer token
  → Express route (JWT auth middleware)
  → SQLite via dbRun/dbGet/dbAll
  → JSON response → UI render
```

No direct DB access from UI. No localStorage as data store. No hardcoded cities, platforms, or targets.
