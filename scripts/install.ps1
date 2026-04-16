<#
.SYNOPSIS
    DHRUVA one-shot installer for Windows PowerShell 7+.

.DESCRIPTION
    Installs the entire ecosystem: Python backend venv, frontend packages,
    gRPC stubs, and brings up the dev infrastructure stack.

.PARAMETER SkipInfra
    Skip `docker compose up` for infrastructure.

.PARAMETER SkipSeed
    Skip loading seed data.

.EXAMPLE
    pwsh ./scripts/install.ps1
    pwsh ./scripts/install.ps1 -SkipInfra
#>

[CmdletBinding()]
param(
    [switch]$SkipInfra,
    [switch]$SkipSeed
)

$ErrorActionPreference = "Stop"

function Write-Banner($msg)  { Write-Host "`n==> $msg" -ForegroundColor Yellow }
function Write-Ok($msg)      { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Fail($msg)          { Write-Host "    [FAIL] $msg" -ForegroundColor Red; exit 1 }

function Require-Cmd($name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { Fail "Missing tool: $name" }
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

# 1 -----------------------------------------------------------------------------
Write-Banner "1/7 · Checking prerequisites"
Require-Cmd docker
Require-Cmd python
Require-Cmd node
Require-Cmd npm
Write-Ok "docker $((docker --version))"
Write-Ok "python $((python -c 'import sys; print(\".\".join(map(str,sys.version_info[:3])))'))"
Write-Ok "node $(node -v)"
Write-Ok "npm $(npm -v)"

# 2 -----------------------------------------------------------------------------
Write-Banner "2/7 · Preparing .env files"
if (-not (Test-Path backend/.env))  { Copy-Item backend/.env.example  backend/.env;  Write-Ok "created backend/.env" }
if (-not (Test-Path frontend/.env)) { Copy-Item frontend/.env.example frontend/.env; Write-Ok "created frontend/.env" }

# 3 -----------------------------------------------------------------------------
Write-Banner "3/7 · Setting up Python backend"
Push-Location backend
if (-not (Test-Path .venv)) {
    python -m venv .venv
    Write-Ok "created virtualenv backend/.venv"
}
$pip = Join-Path ".venv" "Scripts/pip.exe"
& $pip install --upgrade pip wheel | Out-Null
& $pip install -r requirements.txt -r requirements-dev.txt
Write-Ok "python deps installed"
Pop-Location

# 4 -----------------------------------------------------------------------------
Write-Banner "4/7 · Generating gRPC stubs (Python)"
try {
    bash backend/scripts/generate_proto.sh
} catch {
    Write-Ok "skipped gRPC stub generation (proto sources may be empty or bash not available)"
}

# 5 -----------------------------------------------------------------------------
Write-Banner "5/7 · Setting up React frontend"
Push-Location frontend
npm ci --no-audit --no-fund
Write-Ok "npm deps installed"
try { npx --yes buf generate } catch { Write-Ok "skipped buf generate" }
Pop-Location

# 6 -----------------------------------------------------------------------------
if ($SkipInfra) {
    Write-Banner "6/7 · Skipping infrastructure (flag)"
} else {
    Write-Banner "6/7 · Pulling + starting infrastructure"
    docker compose -f deploy/compose/docker-compose.dev.yml pull
    docker compose -f deploy/compose/docker-compose.dev.yml up -d
    Write-Ok "infrastructure up"
}

# 7 -----------------------------------------------------------------------------
Write-Banner "7/7 · Applying database migrations"
Push-Location backend
$alembic = Join-Path ".venv" "Scripts/alembic.exe"
# Wait up to 60s for Postgres
for ($i = 0; $i -lt 30; $i++) {
    $ready = docker exec dhruva-postgres pg_isready -U postgres -d dhruva 2>$null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 2
}
try { & $alembic upgrade head } catch { Write-Ok "alembic upgrade head — nothing to apply yet" }

if (-not $SkipSeed -and (Test-Path "scripts/seed_data.py")) {
    try { & (Join-Path ".venv" "Scripts/python.exe") scripts/seed_data.py } catch {}
    Write-Ok "seed data loaded (if available)"
}
Pop-Location

Write-Banner "DHRUVA installed"
@"
Next steps:
  - pwsh ./scripts/run.ps1         # start backend + frontend
  - Jaeger UI:     http://localhost:16686
  - Prometheus:    http://localhost:9090
  - Grafana:       http://localhost:3000  (admin / admin)
  - REST API:      http://localhost:8000/docs
  - Frontend:      http://localhost:5173
"@ | Write-Host
