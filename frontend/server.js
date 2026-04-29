// ================================================================
//  ShiftSense — Express + SQLite3 Backend  (v4 — Fully Dynamic)
//  Run:  node server.js
//  API base: http://localhost:PORT/api
//
//  Environment variables:
//    PORT       — default 3000
//    JWT_SECRET — MUST be set in production
// ================================================================

const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const bcrypt  = require('bcryptjs');
const jwt     = require('jsonwebtoken');
const cors    = require('cors');
const path    = require('path');

const app = express();

// ── Config from environment (never hardcode secrets) ───────────
const JWT_SECRET = process.env.JWT_SECRET || 'shiftsense-dev-secret-change-in-prod';
const PORT       = parseInt(process.env.PORT, 10) || 3000;
const DB_PATH    = process.env.DB_PATH || './shiftsense.db';

if (!process.env.JWT_SECRET) {
  console.warn('[WARN] JWT_SECRET not set in environment — using insecure default. Set it in production!');
}

// ── Database Setup ──────────────────────────────────────────────
const db = new sqlite3.Database(DB_PATH, (err) => {
  if (err) { console.error('Cannot open database:', err.message); process.exit(1); }
  console.log(`Connected to ${DB_PATH}`);
});

const dbRun = (sql, params = []) => new Promise((resolve, reject) => {
  db.run(sql, params, function(err) { err ? reject(err) : resolve(this); });
});
const dbGet = (sql, params = []) => new Promise((resolve, reject) => {
  db.get(sql, params, (err, row) => { err ? reject(err) : resolve(row); });
});
const dbAll = (sql, params = []) => new Promise((resolve, reject) => {
  db.all(sql, params, (err, rows) => { err ? reject(err) : resolve(rows); });
});

// ── Initialize Tables ───────────────────────────────────────────
db.serialize(() => {
  db.run(`CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    phone       TEXT    NOT NULL UNIQUE,
    email       TEXT,
    pw_hash     TEXT    NOT NULL,
    city        TEXT    NOT NULL,
    vehicle     TEXT    NOT NULL,
    platforms   TEXT    NOT NULL DEFAULT '[]',
    target      INTEGER NOT NULL DEFAULT 3000,
    max_hours   INTEGER NOT NULL DEFAULT 40,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
  )`);

  db.run(`CREATE TABLE IF NOT EXISTS shifts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    zone        TEXT    NOT NULL,
    platform    TEXT    NOT NULL DEFAULT 'Other',
    hours       REAL    NOT NULL,
    earn        INTEGER NOT NULL,
    orders      INTEGER NOT NULL DEFAULT 0,
    predicted   INTEGER NOT NULL DEFAULT 0,
    date_label  TEXT    NOT NULL DEFAULT 'Mon',
    shift_date  DATE    NOT NULL DEFAULT (date('now')),
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
  )`);

  // Zone metadata table — allows admins/users to extend zones without code changes
  db.run(`CREATE TABLE IF NOT EXISTS zones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    city        TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    lat         REAL,
    lng         REAL,
    demand      TEXT    DEFAULT 'medium',
    rate        INTEGER DEFAULT 120,
    peak_hours  TEXT    DEFAULT '6–9 PM',
    cluster     INTEGER DEFAULT 1,
    UNIQUE(city, name)
  )`);

  // Platforms master table — fully dynamic list
  db.run(`CREATE TABLE IF NOT EXISTS platforms (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#6366F1',
    icon  TEXT DEFAULT 'bike'
  )`);

  // Seed default platforms if empty
  db.get('SELECT COUNT(*) as n FROM platforms', (err, row) => {
    if (!err && row && row.n === 0) {
      const plats = [
        ['Swiggy',   '#FC8019', 'bike'],
        ['Zomato',   '#E23744', 'bike'],
        ['Ola',      '#25D366', 'car'],
        ['Uber',     '#000000', 'car'],
        ['Blinkit',  '#F4D03F', 'bike'],
        ['Porter',   '#0070E0', 'truck'],
        ['Rapido',   '#FFD700', 'bike'],
        ['Dunzo',    '#00C48C', 'bike'],
        ['Other',    '#6B7280', 'bike'],
      ];
      plats.forEach(([name, color, icon]) => {
        db.run('INSERT OR IGNORE INTO platforms (name, color, icon) VALUES (?,?,?)', [name, color, icon]);
      });
    }
  });

  // Seed default zones if empty
  db.get('SELECT COUNT(*) as n FROM zones', (err, row) => {
    if (!err && row && row.n === 0) {
      const zoneData = [
        // Bengaluru
        ['Bengaluru','Koramangala',12.9352,77.6245,'high',168,'7–10 PM',1],
        ['Bengaluru','Indiranagar',12.9784,77.6408,'high',162,'7–10 PM',1],
        ['Bengaluru','HSR Layout',12.9116,77.6389,'medium',145,'12–2 PM',2],
        ['Bengaluru','Whitefield',12.9698,77.7499,'medium',138,'12–2 PM',2],
        ['Bengaluru','Marathahalli',12.9591,77.6974,'medium',140,'6–9 PM',2],
        ['Bengaluru','MG Road',12.9756,77.6097,'high',155,'7–10 PM',1],
        ['Bengaluru','JP Nagar',12.9102,77.5830,'medium',135,'6–9 PM',2],
        ['Bengaluru','Electronic City',12.8452,77.6601,'low',118,'5–8 PM',3],
        ['Bengaluru','Jayanagar',12.9299,77.5827,'medium',140,'12–2 PM',2],
        ['Bengaluru','Bellandur',12.9261,77.6770,'medium',138,'7–9 PM',2],
        ['Bengaluru','BTM Layout',12.9166,77.6101,'medium',142,'12–2 PM',2],
        // Coimbatore
        ['Coimbatore','RS Puram',11.0050,76.9598,'high',155,'12–2 PM',1],
        ['Coimbatore','Gandhipuram',11.0168,76.9558,'high',148,'12–2 PM & 7–9 PM',1],
        ['Coimbatore','Peelamedu',11.0262,77.0046,'high',142,'7–9 PM',1],
        ['Coimbatore','Saibaba Colony',11.0131,76.9489,'medium',130,'6–9 PM',2],
        ['Coimbatore','Singanallur',11.0030,77.0234,'medium',125,'5–8 PM',2],
        ['Coimbatore','Ganapathy',11.0456,76.9701,'medium',128,'12–2 PM',2],
        ['Coimbatore','Hopes College',11.0300,76.9350,'low',115,'7–9 PM',3],
        ['Coimbatore','Race Course',11.0072,76.9678,'high',158,'12–2 PM',1],
        // Chennai
        ['Chennai','T. Nagar',13.0418,80.2341,'high',165,'7–10 PM',1],
        ['Chennai','Anna Nagar',13.0850,80.2101,'high',158,'7–10 PM',1],
        ['Chennai','Adyar',13.0067,80.2567,'medium',145,'6–9 PM',2],
        ['Chennai','Velachery',12.9815,80.2180,'medium',140,'5–8 PM',2],
        ['Chennai','Mylapore',13.0368,80.2676,'high',160,'12–2 PM',1],
        ['Chennai','Nungambakkam',13.0569,80.2425,'medium',150,'7–10 PM',2],
        // Hyderabad
        ['Hyderabad','Banjara Hills',17.4125,78.4485,'high',170,'7–10 PM',1],
        ['Hyderabad','Jubilee Hills',17.4252,78.4099,'high',165,'7–10 PM',1],
        ['Hyderabad','Hitech City',17.4474,78.3762,'medium',148,'12–2 PM',2],
        ['Hyderabad','Gachibowli',17.4400,78.3489,'medium',145,'6–9 PM',2],
        ['Hyderabad','Madhapur',17.4474,78.3856,'medium',150,'7–10 PM',2],
        ['Hyderabad','Secunderabad',17.4399,78.4983,'medium',138,'12–2 PM',2],
        // Mumbai
        ['Mumbai','Bandra',19.0596,72.8295,'high',175,'7–10 PM',1],
        ['Mumbai','Andheri',19.1136,72.8697,'high',168,'7–10 PM',1],
        ['Mumbai','Lower Parel',18.9950,72.8218,'high',172,'12–2 PM',1],
        ['Mumbai','Powai',19.1176,72.9060,'medium',148,'6–9 PM',2],
        ['Mumbai','Navi Mumbai',19.0330,73.0297,'low',105,'5–7 PM',3],
        ['Mumbai','Mulund',19.1727,72.9575,'medium',132,'12–2 PM',2],
        // Delhi
        ['Delhi','Connaught Place',28.6315,77.2167,'high',178,'7–10 PM',1],
        ['Delhi','Hauz Khas',28.5494,77.2001,'high',170,'7–10 PM',1],
        ['Delhi','Saket',28.5245,77.2066,'medium',152,'6–9 PM',2],
        ['Delhi','Dwarka',28.5921,77.0460,'medium',138,'5–8 PM',2],
        ['Delhi','Rohini',28.7041,77.1025,'medium',135,'12–2 PM',2],
        ['Delhi','Lajpat Nagar',28.5672,77.2434,'medium',148,'12–2 PM',2],
        // Pune
        ['Pune','Koregaon Park',18.5362,73.8928,'high',162,'7–10 PM',1],
        ['Pune','Kothrud',18.5074,73.8077,'high',155,'7–10 PM',1],
        ['Pune','Viman Nagar',18.5679,73.9143,'medium',148,'6–9 PM',2],
        ['Pune','Baner',18.5590,73.7868,'medium',145,'12–2 PM',2],
        ['Pune','Hinjewadi',18.5912,73.7389,'medium',140,'5–8 PM',2],
        ['Pune','FC Road',18.5241,73.8479,'high',165,'12–2 PM',1],
        // Kolkata
        ['Kolkata','Park Street',22.5519,88.3520,'high',158,'7–10 PM',1],
        ['Kolkata','New Town',22.5958,88.4799,'medium',142,'6–9 PM',2],
        ['Kolkata','Salt Lake',22.5697,88.4183,'medium',140,'5–8 PM',2],
        ['Kolkata','Ballygunge',22.5260,88.3638,'high',155,'7–10 PM',1],
        ['Kolkata','Gariahat',22.5202,88.3672,'medium',148,'12–2 PM',2],
        ['Kolkata','Howrah',22.5958,88.2636,'low',115,'5–8 PM',3],
      ];
      zoneData.forEach(z => {
        db.run(
          'INSERT OR IGNORE INTO zones (city, name, lat, lng, demand, rate, peak_hours, cluster) VALUES (?,?,?,?,?,?,?,?)',
          z
        );
      });
    }
  });
});

// ── Middleware ───────────────────────────────────────────────────
app.use(cors());
app.use(express.json({ limit: '5mb' }));
app.use(express.static(path.join(__dirname)));

// ── /api/v2 → Proxy to FastAPI Analytics Backend ─────────────────
// All /api/v2/* requests are forwarded to FastAPI on port 3001.
// FastAPI reads the same SQLite DB as Node.js (shared database).
const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:3001';
const http_module = require('http');
const https_module = require('https');

app.use('/api/v2', (req, res) => {
  const lib = FASTAPI_URL.startsWith('https') ? https_module : http_module;
  const targetPath = '/api/v2' + req.url;
  const parsedUrl = new URL(FASTAPI_URL);
  
  // Re-serialize the body (Express already parsed it), so we must
  // recalculate content-length to avoid FastAPI receiving a mismatch
  // that causes a plain-text "Internal Server Error" (non-JSON) response.
  const bodyData = (req.method !== 'GET' && req.method !== 'HEAD' && req.body && Object.keys(req.body).length > 0)
    ? JSON.stringify(req.body)
    : null;

  const proxyHeaders = {
    ...req.headers,
    host: parsedUrl.hostname,
    'content-type': 'application/json',
  };

  if (bodyData) {
    proxyHeaders['content-length'] = Buffer.byteLength(bodyData);
  } else {
    delete proxyHeaders['content-length'];
  }

  const options = {
    hostname: parsedUrl.hostname,
    port: parsedUrl.port || (FASTAPI_URL.startsWith('https') ? 443 : 80),
    path: targetPath,
    method: req.method,
    headers: proxyHeaders,
  };

  const proxyReq = lib.request(options, (proxyRes) => {
    res.status(proxyRes.statusCode);
    Object.entries(proxyRes.headers || {}).forEach(([k, v]) => {
      if (k !== 'transfer-encoding') res.setHeader(k, v);
    });
    proxyRes.pipe(res);
  });

  proxyReq.on('error', () => {
    res.status(503).json({
      error: 'Analytics service unavailable. Start FastAPI first.',
      fallback: true,
      start_command: 'uvicorn backend.app.main:app --port 3001 --reload',
    });
  });

  if (bodyData) {
    proxyReq.write(bodyData);
  }
  proxyReq.end();
});



// ── Auth Middleware ──────────────────────────────────────────────
function auth(req, res, next) {
  const header = req.headers.authorization || '';
  const token  = header.startsWith('Bearer ') ? header.slice(7) : null;
  if (!token) return res.status(401).json({ error: 'No token provided' });
  try {
    req.user = jwt.verify(token, JWT_SECRET);
    next();
  } catch {
    res.status(401).json({ error: 'Invalid or expired token' });
  }
}

function safeUser(u) {
  return {
    id: u.id, name: u.name, phone: u.phone, email: u.email || null,
    city: u.city, vehicle: u.vehicle,
    platforms: JSON.parse(u.platforms || '[]'),
    target: u.target, maxHours: u.max_hours
  };
}

// ================================================================
//  AUTH ROUTES
// ================================================================

app.post('/api/auth/register', async (req, res) => {
  try {
    const { name, phone, email, pw, city, vehicle, platforms, target, maxHours } = req.body;

    // Validation
    if (!name || !name.trim())         return res.status(400).json({ error: 'Name is required' });
    if (!phone || !phone.trim())       return res.status(400).json({ error: 'Phone is required' });
    if (!pw)                           return res.status(400).json({ error: 'Password is required' });
    if (pw.length < 6)                 return res.status(400).json({ error: 'Password must be at least 6 characters' });
    if (!city || !city.trim())         return res.status(400).json({ error: 'City is required' });
    if (!vehicle || !vehicle.trim())   return res.status(400).json({ error: 'Vehicle type is required' });
    if (!platforms || !platforms.length) return res.status(400).json({ error: 'Select at least one platform' });

    const parsedTarget   = parseInt(target, 10);
    const parsedMaxHours = parseInt(maxHours, 10);
    if (isNaN(parsedTarget) || parsedTarget <= 0)     return res.status(400).json({ error: 'Target earnings must be a positive number' });
    if (isNaN(parsedMaxHours) || parsedMaxHours <= 0) return res.status(400).json({ error: 'Max hours must be a positive number' });
    if (parsedMaxHours > 168)                         return res.status(400).json({ error: 'Max hours cannot exceed 168 per week' });

    const phoneNorm = phone.trim().replace(/\D/g, ''); // normalize to digits only
    const existing  = await dbGet('SELECT id FROM users WHERE phone = ?', [phoneNorm]);
    if (existing) return res.status(409).json({ error: 'Phone number already registered' });

    const pw_hash = bcrypt.hashSync(pw, 10);
    const result  = await dbRun(
      `INSERT INTO users (name, phone, email, pw_hash, city, vehicle, platforms, target, max_hours)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [name.trim(), phoneNorm, email ? email.trim() : null, pw_hash,
       city.trim(), vehicle.trim(), JSON.stringify(platforms),
       parsedTarget, parsedMaxHours]
    );

    const user  = await dbGet('SELECT * FROM users WHERE id = ?', [result.lastID]);
    const token = jwt.sign({ id: user.id, name: user.name }, JWT_SECRET, { expiresIn: '30d' });
    res.json({ token, user: safeUser(user) });
  } catch (err) {
    console.error('Register error:', err.message);
    res.status(500).json({ error: 'Registration failed. Please try again.' });
  }
});

app.post('/api/auth/login', async (req, res) => {
  try {
    const { phone, pw } = req.body;
    if (!phone || !pw) return res.status(400).json({ error: 'Phone and password required' });

    const phoneNorm = phone.trim().replace(/\D/g, '');
    const user = await dbGet('SELECT * FROM users WHERE phone = ?', [phoneNorm]);
    if (!user || !bcrypt.compareSync(pw, user.pw_hash))
      return res.status(401).json({ error: 'Invalid phone or password' });

    const token = jwt.sign({ id: user.id, name: user.name }, JWT_SECRET, { expiresIn: '30d' });
    res.json({ token, user: safeUser(user) });
  } catch (err) {
    console.error('Login error:', err.message);
    res.status(500).json({ error: 'Login failed. Please try again.' });
  }
});

app.get('/api/auth/me', auth, async (req, res) => {
  try {
    const user = await dbGet('SELECT * FROM users WHERE id = ?', [req.user.id]);
    if (!user) return res.status(404).json({ error: 'User not found' });
    res.json(safeUser(user));
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put('/api/auth/profile', auth, async (req, res) => {
  try {
    const { name, email, city, vehicle, platforms, target, maxHours } = req.body;

    // Only validate fields that are being updated
    if (target !== undefined) {
      const t = parseInt(target, 10);
      if (isNaN(t) || t <= 0) return res.status(400).json({ error: 'Target must be a positive number' });
    }
    if (maxHours !== undefined) {
      const mh = parseInt(maxHours, 10);
      if (isNaN(mh) || mh <= 0 || mh > 168) return res.status(400).json({ error: 'Max hours must be 1–168' });
    }

    await dbRun(
      `UPDATE users SET
         name      = COALESCE(?, name),
         email     = COALESCE(?, email),
         city      = COALESCE(?, city),
         vehicle   = COALESCE(?, vehicle),
         platforms = COALESCE(?, platforms),
         target    = COALESCE(?, target),
         max_hours = COALESCE(?, max_hours)
       WHERE id = ?`,
      [name    || null,
       email   || null,
       city    || null,
       vehicle || null,
       platforms ? JSON.stringify(platforms) : null,
       target    ? parseInt(target, 10)    : null,
       maxHours  ? parseInt(maxHours, 10)  : null,
       req.user.id]
    );
    const user = await dbGet('SELECT * FROM users WHERE id = ?', [req.user.id]);
    res.json(safeUser(user));
  } catch (err) {
    console.error('Profile update error:', err.message);
    res.status(500).json({ error: err.message });
  }
});

app.put('/api/auth/password', auth, async (req, res) => {
  try {
    const { pw, currentPw } = req.body;
    if (!pw || pw.length < 6) return res.status(400).json({ error: 'New password must be at least 6 characters' });

    // Optionally verify current password if provided
    if (currentPw) {
      const user = await dbGet('SELECT pw_hash FROM users WHERE id = ?', [req.user.id]);
      if (!bcrypt.compareSync(currentPw, user.pw_hash))
        return res.status(401).json({ error: 'Current password is incorrect' });
    }

    const pw_hash = bcrypt.hashSync(pw, 10);
    await dbRun('UPDATE users SET pw_hash = ? WHERE id = ?', [pw_hash, req.user.id]);
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ================================================================
//  SHIFTS ROUTES
// ================================================================

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function validateShift(data) {
  const { zone, platform, hours, earn } = data;
  if (!zone || !zone.trim())              return 'Zone is required';
  if (!hours || isNaN(parseFloat(hours))) return 'Valid hours are required';
  const h = parseFloat(hours);
  if (h <= 0 || h > 24)                  return 'Hours must be between 0 and 24';
  if (earn === undefined || earn === null || isNaN(parseInt(earn, 10))) return 'Valid earnings are required';
  if (parseInt(earn, 10) < 0)            return 'Earnings cannot be negative';
  return null;
}

app.get('/api/shifts', auth, async (req, res) => {
  try {
    const { from, to, platform, zone, limit } = req.query;
    let sql    = 'SELECT * FROM shifts WHERE user_id = ?';
    const params = [req.user.id];

    if (from)     { sql += ' AND shift_date >= ?'; params.push(from); }
    if (to)       { sql += ' AND shift_date <= ?'; params.push(to); }
    if (platform) { sql += ' AND platform = ?';   params.push(platform); }
    if (zone)     { sql += ' AND zone = ?';       params.push(zone); }

    sql += ' ORDER BY shift_date DESC, created_at DESC';
    if (limit && !isNaN(parseInt(limit, 10))) {
      sql += ' LIMIT ?'; params.push(parseInt(limit, 10));
    }

    const shifts = await dbAll(sql, params);
    res.json(shifts);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/shifts', auth, async (req, res) => {
  try {
    const { zone, platform, hours, earn, orders, predicted, date_label, shift_date } = req.body;

    const validErr = validateShift(req.body);
    if (validErr) return res.status(400).json({ error: validErr });

    const parsedHours = parseFloat(hours);
    const parsedEarn  = parseInt(earn, 10);
    const finalDate   = shift_date || new Date().toISOString().slice(0, 10);
    const finalLabel  = date_label || DAYS[new Date(finalDate + 'T00:00:00').getDay()] || 'Mon';

    // Use first user platform as default if platform not specified
    let finalPlatform = platform && platform.trim() ? platform.trim() : null;
    if (!finalPlatform) {
      const user = await dbGet('SELECT platforms FROM users WHERE id = ?', [req.user.id]);
      const userPlatforms = JSON.parse(user.platforms || '[]');
      finalPlatform = userPlatforms[0] || 'Other';
    }

    const result = await dbRun(
      `INSERT INTO shifts (user_id, zone, platform, hours, earn, orders, predicted, date_label, shift_date)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [req.user.id, zone.trim(), finalPlatform, parsedHours, parsedEarn,
       parseInt(orders, 10) || 0, parseInt(predicted, 10) || 0, finalLabel, finalDate]
    );

    const shift = await dbGet('SELECT * FROM shifts WHERE id = ?', [result.lastID]);
    res.json(shift);
  } catch (err) {
    console.error('Create shift error:', err.message);
    res.status(500).json({ error: err.message });
  }
});

app.put('/api/shifts/:id', auth, async (req, res) => {
  try {
    const shift = await dbGet(
      'SELECT * FROM shifts WHERE id = ? AND user_id = ?',
      [req.params.id, req.user.id]
    );
    if (!shift) return res.status(404).json({ error: 'Shift not found or not yours' });

    const { zone, platform, hours, earn, orders, predicted, date_label, shift_date } = req.body;

    if (hours !== undefined) {
      const h = parseFloat(hours);
      if (isNaN(h) || h <= 0 || h > 24) return res.status(400).json({ error: 'Hours must be 0–24' });
    }
    if (earn !== undefined) {
      const e = parseInt(earn, 10);
      if (isNaN(e) || e < 0) return res.status(400).json({ error: 'Earnings cannot be negative' });
    }

    await dbRun(
      `UPDATE shifts SET
         zone       = COALESCE(?, zone),
         platform   = COALESCE(?, platform),
         hours      = COALESCE(?, hours),
         earn       = COALESCE(?, earn),
         orders     = COALESCE(?, orders),
         predicted  = COALESCE(?, predicted),
         date_label = COALESCE(?, date_label),
         shift_date = COALESCE(?, shift_date)
       WHERE id = ?`,
      [zone      || null,
       platform  || null,
       hours     != null ? parseFloat(hours)     : null,
       earn      != null ? parseInt(earn, 10)    : null,
       orders    != null ? parseInt(orders, 10)  : null,
       predicted != null ? parseInt(predicted, 10) : null,
       date_label || null,
       shift_date || null,
       req.params.id]
    );
    const updated = await dbGet('SELECT * FROM shifts WHERE id = ?', [req.params.id]);
    res.json(updated);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.delete('/api/shifts/:id', auth, async (req, res) => {
  try {
    const shift = await dbGet(
      'SELECT id FROM shifts WHERE id = ? AND user_id = ?',
      [req.params.id, req.user.id]
    );
    if (!shift) return res.status(404).json({ error: 'Shift not found or not yours' });
    await dbRun('DELETE FROM shifts WHERE id = ?', [req.params.id]);
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── Bulk CSV Import ──────────────────────────────────────────────
app.post('/api/shifts/bulk', auth, async (req, res) => {
  try {
    const { shifts } = req.body;
    if (!Array.isArray(shifts) || !shifts.length)
      return res.status(400).json({ error: 'No shifts provided' });
    if (shifts.length > 1000)
      return res.status(400).json({ error: 'Maximum 1000 shifts per import' });

    // Get user's default platform
    const user = await dbGet('SELECT platforms FROM users WHERE id = ?', [req.user.id]);
    const userPlatforms = JSON.parse(user.platforms || '[]');
    const defaultPlatform = userPlatforms[0] || 'Other';

    let inserted = 0;
    const errors = [];

    for (let i = 0; i < shifts.length; i++) {
      const s   = shifts[i];
      const row = i + 2;

      if (!s.zone || !s.platform || !s.hours || s.earn == null) {
        errors.push(`Row ${row}: missing required field(s): zone, platform, hours, earn`);
        continue;
      }

      const hours = parseFloat(s.hours);
      const earn  = parseInt(s.earn, 10);
      if (isNaN(hours) || hours <= 0 || hours > 24) {
        errors.push(`Row ${row}: invalid hours value "${s.hours}" (must be 0–24)`);
        continue;
      }
      if (isNaN(earn) || earn < 0) {
        errors.push(`Row ${row}: invalid earn value "${s.earn}" (must be non-negative)`);
        continue;
      }

      const finalDate  = s.shift_date || new Date().toISOString().slice(0, 10);
      const d          = new Date(finalDate + 'T00:00:00');
      const finalLabel = s.date_label || (isNaN(d.getTime()) ? 'Mon' : DAYS[d.getDay()]);
      const platform   = (s.platform && s.platform.trim()) ? s.platform.trim() : defaultPlatform;

      try {
        await dbRun(
          `INSERT INTO shifts (user_id, zone, platform, hours, earn, orders, predicted, date_label, shift_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
          [req.user.id, s.zone.trim(), platform, hours, earn,
           parseInt(s.orders, 10) || 0, parseInt(s.predicted, 10) || 0, finalLabel, finalDate]
        );
        inserted++;
      } catch (e) {
        errors.push(`Row ${row}: ${e.message}`);
      }
    }

    res.json({ inserted, errors: errors.slice(0, 20), total: shifts.length });
  } catch (err) {
    console.error('Bulk import error:', err.message);
    res.status(500).json({ error: err.message });
  }
});

// ── Shift Statistics (summary for a user) ───────────────────────
app.get('/api/shifts/stats', auth, async (req, res) => {
  try {
    const stats = await dbGet(
      `SELECT
         COUNT(*)           AS total_shifts,
         SUM(earn)          AS total_earn,
         SUM(hours)         AS total_hours,
         AVG(earn)          AS avg_earn,
         AVG(hours)         AS avg_hours,
         MAX(earn)          AS best_earn,
         MIN(shift_date)    AS first_shift,
         MAX(shift_date)    AS last_shift
       FROM shifts WHERE user_id = ?`,
      [req.user.id]
    );
    res.json(stats);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ================================================================
//  ZONES & PLATFORMS ROUTES (Dynamic Data)
// ================================================================

// Get zones for a specific city (or all cities)
app.get('/api/zones', auth, async (req, res) => {
  try {
    const { city } = req.query;
    let rows;
    if (city) {
      rows = await dbAll('SELECT * FROM zones WHERE city = ? ORDER BY demand DESC, rate DESC', [city]);
      // If no zones found for city, fall back to first available city
      if (!rows.length) {
        rows = await dbAll('SELECT * FROM zones WHERE city = (SELECT city FROM zones LIMIT 1) ORDER BY demand DESC, rate DESC');
      }
    } else {
      rows = await dbAll('SELECT * FROM zones ORDER BY city, demand DESC, rate DESC');
    }
    res.json(rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Get list of available cities
app.get('/api/zones/cities', async (req, res) => {
  try {
    const rows = await dbAll('SELECT DISTINCT city FROM zones ORDER BY city');
    res.json(rows.map(r => r.city));
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Get all platforms
app.get('/api/platforms', async (req, res) => {
  try {
    const rows = await dbAll('SELECT * FROM platforms ORDER BY name');
    res.json(rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ================================================================
//  ANALYTICS ROUTE (pre-computed summaries)
// ================================================================

app.get('/api/analytics/weekly', auth, async (req, res) => {
  try {
    const rows = await dbAll(
      `SELECT
         date_label,
         strftime('%w', shift_date) AS dow,
         SUM(earn)  AS total_earn,
         SUM(hours) AS total_hours,
         COUNT(*)   AS shift_count
       FROM shifts WHERE user_id = ?
       GROUP BY date_label, dow
       ORDER BY CAST(dow AS INTEGER)`,
      [req.user.id]
    );
    res.json(rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/analytics/by-platform', auth, async (req, res) => {
  try {
    const rows = await dbAll(
      `SELECT
         platform,
         COUNT(*)   AS shift_count,
         SUM(earn)  AS total_earn,
         SUM(hours) AS total_hours,
         AVG(earn)  AS avg_earn
       FROM shifts WHERE user_id = ?
       GROUP BY platform
       ORDER BY total_earn DESC`,
      [req.user.id]
    );
    res.json(rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/analytics/by-zone', auth, async (req, res) => {
  try {
    const rows = await dbAll(
      `SELECT
         zone,
         COUNT(*)                    AS shift_count,
         SUM(earn)                   AS total_earn,
         SUM(hours)                  AS total_hours,
         ROUND(SUM(earn)*1.0/SUM(hours), 1) AS rate_per_hour
       FROM shifts WHERE user_id = ? AND hours > 0
       GROUP BY zone
       ORDER BY rate_per_hour DESC`,
      [req.user.id]
    );
    res.json(rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── Health Check ─────────────────────────────────────────────────
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', version: '5.0', node_api: 'v1', analytics_api: 'v2', timestamp: new Date().toISOString() });
});

// ── Start Server ─────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n═══════════════════════════════════════`);
  console.log(`  ShiftSense v5 — Hybrid Architecture`);
  console.log(`  Node.js (v1): http://localhost:${PORT}`);
  console.log(`  FastAPI (v2): ${FASTAPI_URL}`);
  console.log(`  http://localhost:${PORT}`);
  console.log(`  DB: ${DB_PATH}`);
  console.log(`═══════════════════════════════════════\n`);
});
