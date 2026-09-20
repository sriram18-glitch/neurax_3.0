# NeuraX — one-command demo startup (PowerShell)
#
# Starts the real FastAPI backend and serves the built frontend.
# No internet required at run time; no external services.
#
#   .\start_demo.ps1            # backend + built frontend (recommended for judging)
#   .\start_demo.ps1 -Dev       # backend + vite dev server (for development)
#   .\start_demo.ps1 -SkipBuild # reuse the existing dist/ build
#
# Press Ctrl+C in either window to stop.

param(
    [switch]$Dev,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

function Wait-ForBackend {
    param([int]$Attempts = 60)
    for ($i = 0; $i -lt $Attempts; $i++) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -eq 200) { return $true }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    return $false
}

Write-Host "=== NeuraX demo startup ===" -ForegroundColor Cyan

# 1) Backend ------------------------------------------------------------------
Write-Host "[1/3] Starting backend on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "8000" `
    -WorkingDirectory $backend -WindowStyle Minimized

if (-not (Wait-ForBackend)) {
    Write-Host "Backend did not become healthy. Check the backend window for errors." -ForegroundColor Red
    exit 1
}
Write-Host "      Backend healthy." -ForegroundColor Green

# 2) Frontend build -----------------------------------------------------------
if ($Dev) {
    Write-Host "[2/3] Starting vite dev server on http://localhost:5173 ..." -ForegroundColor Cyan
    Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev" -WorkingDirectory $frontend
    Write-Host "      Dev server starting." -ForegroundColor Green
} else {
    if (-not $SkipBuild -or -not (Test-Path (Join-Path $frontend "dist\index.html"))) {
        Write-Host "[2/3] Building frontend ..." -ForegroundColor Cyan
        Push-Location $frontend
        try {
            npm run build | Out-Host
        } finally {
            Pop-Location
        }
    } else {
        Write-Host "[2/3] Reusing existing frontend build." -ForegroundColor Cyan
    }
    Write-Host "[3/3] Serving frontend on http://localhost:4173 ..." -ForegroundColor Cyan
    Start-Process -FilePath "npm.cmd" -ArgumentList "run", "preview" -WorkingDirectory $frontend
}

Write-Host ""
Write-Host "WORKSTATION:   http://localhost:4173" -ForegroundColor Green
Write-Host "API:           http://127.0.0.1:8000/api/health" -ForegroundColor Green
Write-Host ""
Write-Host "Demo dataset:  Manufacturing Data Shared Facility - Discrete-Event Simulation\Model 1\Model_1.csv"
Write-Host "Demo script:   DEMO_SCRIPT.md"
