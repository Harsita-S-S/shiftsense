@echo off
REM ================================================================
REM  ShiftSense v5 — Windows Startup Script
REM  Run: start.bat
REM ================================================================

echo.
echo ═══════════════════════════════════════════════════════
echo   ShiftSense v5 — Hybrid Architecture Startup
echo ═══════════════════════════════════════════════════════
echo.

cd /d "%~dp0"

REM ── Install Node dependencies if needed ────────────────────────
if not exist "frontend\node_modules" (
  echo Installing Node.js dependencies...
  cd frontend && npm install && cd ..
)

REM ── Start FastAPI (if Python available) ────────────────────────
python --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  python -c "import fastapi" >nul 2>&1
  if %ERRORLEVEL% EQU 0 (
    echo Starting FastAPI analytics on port 3001...
    start "ShiftSense FastAPI" cmd /c "python -m uvicorn backend.app.main:app --port 3001"
    timeout /t 2 /nobreak >nul
  ) else (
    echo [WARN] FastAPI not installed. Run: pip install -r requirements.txt
  )
) else (
  echo [WARN] Python not found. Analytics v2 API unavailable.
)

REM ── Start Node.js ───────────────────────────────────────────────
echo.
echo Starting Node.js backend on port 3000...
echo Open: http://localhost:3000
echo.

cd frontend && node server.js
