<#
.SYNOPSIS
    Run DHRUVA backend (pytest) and frontend (vitest) test suites.
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

Write-Host "==> Backend tests" -ForegroundColor Yellow
Push-Location backend
& (Join-Path ".venv" "Scripts/activate.ps1")
ruff check .
try { mypy app/core app/brokers } catch {}
pytest
Pop-Location

Write-Host "==> Frontend tests" -ForegroundColor Yellow
Push-Location frontend
npm run lint
npm run typecheck
npm run test
Pop-Location
