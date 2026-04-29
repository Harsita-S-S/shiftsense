// ================================================================
//  ShiftSense — Shared Client Config  (v5 — Hybrid Architecture)
//  Includes both /api/v1 (Node.js) and /api/v2 (FastAPI) endpoints.
//  Include this FIRST on every HTML page:
//    <script src="config.js"></script>
// ================================================================
(function () {
  const origin = window.location.origin;

  window.SS_CONFIG = {
    API: origin + '/api',          // v1 — Node.js (all existing endpoints)
    API_V2: origin + '/api/v2',    // v2 — FastAPI (analytics/ML endpoints)
    VERSION: '5.0',
    V2_AVAILABLE: null,
  };

  // Probe v2 availability on startup
  fetch(window.SS_CONFIG.API_V2 + '/health', { method: 'GET' })
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      window.SS_CONFIG.V2_AVAILABLE = !!(data && data.analytics);
      console.log('[ShiftSense] API v2 available:', window.SS_CONFIG.V2_AVAILABLE);
    })
    .catch(() => {
      window.SS_CONFIG.V2_AVAILABLE = false;
      console.warn('[ShiftSense] API v2 offline — using v1 fallback for analytics');
    });

  window.fetchV2 = async function (path, options = {}) {
    const token = localStorage.getItem('ss_token');
    const url = window.SS_CONFIG.API_V2 + path;
    const res = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token ? 'Bearer ' + token : '',
        ...(options.headers || {}),
      },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(err.error || 'v2 API error');
    }
    return res.json();
  };

  window.api = async function (path, options = {}) {
    const token = localStorage.getItem('ss_token');
    const url = window.SS_CONFIG.API + path;
    const res = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token ? 'Bearer ' + token : '',
        ...(options.headers || {}),
      },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(err.error || 'API error');
    }
    return res.json();
  };
})();
