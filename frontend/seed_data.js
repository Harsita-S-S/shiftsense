// ================================================================
//  ShiftSense — Seed Data Script  (v4)
//  Run ONCE:  node seed_data.js
//
//  Env overrides (all optional):
//    SEED_PHONE     — demo user phone  (default: 9999999999)
//    SEED_PASSWORD  — demo password    (default: demo1234)
//    SEED_NAME      — demo user name   (default: Aarav Kumar)
//    SEED_CITY      — demo user city   (default: Coimbatore)
//    SEED_PLATFORM  — default platform (default: Swiggy)
//    SEED_TARGET    — weekly target ₹  (default: 5000)
//    DB_PATH        — SQLite file path (default: ./shiftsense.db)
// ================================================================

const sqlite3 = require('sqlite3').verbose();
const bcrypt  = require('bcryptjs');

const DB_PATH = process.env.DB_PATH || './shiftsense.db';

const SEED_PHONE    = process.env.SEED_PHONE    || '9999999999';
const SEED_PASSWORD = process.env.SEED_PASSWORD || 'demo1234';
const SEED_NAME     = process.env.SEED_NAME     || 'Aarav Kumar';
const SEED_CITY     = process.env.SEED_CITY     || 'Coimbatore';
const SEED_PLATFORM = process.env.SEED_PLATFORM || 'Swiggy';
const SEED_TARGET   = parseInt(process.env.SEED_TARGET, 10) || 5000;

const db = new sqlite3.Database(DB_PATH, (err) => {
  if (err) { console.error('Cannot open DB:', err.message); process.exit(1); }
  console.log(`Connected to ${DB_PATH}`);
});

const run = (sql, params = []) => new Promise((res, rej) =>
  db.run(sql, params, function(err) { err ? rej(err) : res(this); })
);
const get = (sql, params = []) => new Promise((res, rej) =>
  db.get(sql, params, (err, row) => { err ? rej(err) : res(row); })
);
const all = (sql, params = []) => new Promise((res, rej) =>
  db.all(sql, params, (err, rows) => { err ? rej(err) : res(rows); })
);

// ── Zone pools by city (matches server.js) ───────────────────────
const ZONES_BY_CITY = {
  'Bengaluru':   ['Koramangala','Indiranagar','HSR Layout','Whitefield','Marathahalli','MG Road','JP Nagar','Electronic City','Jayanagar','Bellandur','BTM Layout'],
  'Coimbatore':  ['RS Puram','Gandhipuram','Peelamedu','Saibaba Colony','Singanallur','Ganapathy','Race Course'],
  'Chennai':     ['T. Nagar','Anna Nagar','Adyar','Velachery','Mylapore','Nungambakkam'],
  'Hyderabad':   ['Banjara Hills','Jubilee Hills','Hitech City','Gachibowli','Madhapur','Secunderabad'],
  'Mumbai':      ['Bandra','Andheri','Lower Parel','Powai','Navi Mumbai','Mulund'],
  'Delhi':       ['Connaught Place','Hauz Khas','Saket','Dwarka','Rohini','Lajpat Nagar'],
  'Pune':        ['Koregaon Park','Kothrud','Viman Nagar','Baner','Hinjewadi','FC Road'],
  'Kolkata':     ['Park Street','New Town','Salt Lake','Ballygunge','Gariahat','Howrah'],
};

const DAYS       = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const PLATFORMS  = [SEED_PLATFORM, 'Zomato'];

function rand(min, max) { return Math.random() * (max - min) + min; }
function pick(arr)       { return arr[Math.floor(Math.random() * arr.length)]; }

// ── Main ──────────────────────────────────────────────────────────
(async () => {
  // 1. Create tables (mirrors server.js schema)
  await run(`CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL UNIQUE,
    email TEXT,
    pw_hash TEXT NOT NULL,
    city TEXT NOT NULL,
    vehicle TEXT NOT NULL,
    platforms TEXT NOT NULL,
    target INTEGER NOT NULL DEFAULT 3000,
    max_hours INTEGER NOT NULL DEFAULT 40,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )`);

  await run(`CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    zone TEXT NOT NULL,
    platform TEXT NOT NULL,
    hours REAL NOT NULL,
    earn INTEGER NOT NULL,
    orders INTEGER NOT NULL DEFAULT 0,
    predicted INTEGER NOT NULL DEFAULT 0,
    date_label TEXT NOT NULL,
    shift_date DATE NOT NULL DEFAULT (date('now')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )`);

  console.log('Tables ready.');

  // 2. Insert demo user (skip if already exists)
  const phoneNorm = SEED_PHONE.replace(/\D/g, '');
  const existing  = await get('SELECT id FROM users WHERE phone = ?', [phoneNorm]);

  if (existing) {
    console.log(`Demo user already exists (id: ${existing.id}). Skipping user insert.`);
    console.log(`To reset: DELETE FROM users WHERE phone='${phoneNorm}'; in SQLite\n`);
    await seedShifts(existing.id, SEED_CITY, true);
    return;
  }

  const pw_hash = bcrypt.hashSync(SEED_PASSWORD, 10);
  const result  = await run(
    `INSERT INTO users (name, phone, email, pw_hash, city, vehicle, platforms, target, max_hours)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [SEED_NAME, phoneNorm, `${SEED_NAME.toLowerCase().replace(' ', '.')}@example.com`,
     pw_hash, SEED_CITY, 'Bike', JSON.stringify(PLATFORMS), SEED_TARGET, 40]
  );

  console.log(`✓ Created demo user  id: ${result.lastID}  city: ${SEED_CITY}`);
  await seedShifts(result.lastID, SEED_CITY, false);
})().catch(e => { console.error(e); process.exit(1); });


async function seedShifts(userId, city, skipIfExists) {
  const count = await get('SELECT COUNT(*) as n FROM shifts WHERE user_id = ?', [userId]);
  if (count.n > 0 && skipIfExists) {
    console.log(`Shifts already exist (${count.n} rows) — skipping.`);
    printCredentials();
    db.close();
    return;
  }

  // Use city-specific zones; fall back to Bengaluru if unknown city
  const ZONES = ZONES_BY_CITY[city] || ZONES_BY_CITY['Bengaluru'];

  // Build 14 days of realistic shifts
  const shifts = [];
  const today  = new Date();

  for (let i = 13; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const dateStr   = d.toISOString().slice(0, 10);
    const dayLabel  = DAYS[d.getDay()];
    const isWeekend = d.getDay() === 0 || d.getDay() === 6;

    // ~85% work day probability; weekends slightly higher
    if (Math.random() > (isWeekend ? 0.9 : 0.85)) continue;

    // Primary shift
    const zone      = pick(ZONES);
    const platform  = pick(PLATFORMS);
    const hours     = Math.round(rand(3, 7) * 10) / 10;
    const predicted = Math.round(150 * hours);
    const earn      = Math.round(predicted * rand(0.80, 1.30));
    const orders    = Math.round(hours * rand(2, 4));
    shifts.push([userId, zone, platform, hours, earn, orders, predicted, dayLabel, dateStr]);

    // ~40% chance of a second shorter shift
    if (Math.random() < 0.4) {
      const z2 = pick(ZONES);
      const h2 = Math.round(rand(1.5, 3.5) * 10) / 10;
      const p2 = Math.round(150 * h2);
      const e2 = Math.round(p2 * rand(0.85, 1.25));
      const o2 = Math.round(h2 * rand(1.5, 3.5));
      shifts.push([userId, z2, pick(PLATFORMS), h2, e2, o2, p2, dayLabel, dateStr]);
    }
  }

  const stmt = db.prepare(
    `INSERT INTO shifts (user_id, zone, platform, hours, earn, orders, predicted, date_label, shift_date)
     VALUES (?,?,?,?,?,?,?,?,?)`
  );
  shifts.forEach(s => stmt.run(s));
  stmt.finalize(() => {
    const total = shifts.reduce((s, r) => s + r[4], 0);
    console.log(`✓ Seeded ${shifts.length} shifts for ${city}  (total: ₹${total.toLocaleString('en-IN')})`);
    printCredentials();
    db.close();
  });
}

function printCredentials() {
  console.log('\n════════════════════════════════════');
  console.log('  Demo login credentials');
  console.log(`  Phone:    ${SEED_PHONE}`);
  console.log(`  Password: ${SEED_PASSWORD}`);
  console.log(`  City:     ${SEED_CITY}`);
  console.log('════════════════════════════════════');
  console.log('\nNow run:  node server.js');
  console.log(`Open:     http://localhost:${process.env.PORT || 3000}\n`);
}
