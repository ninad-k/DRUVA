<#
.SYNOPSIS
    Start DHRUVA backend (uvicorn) + frontend (vite) in parallel, plus dev infra.

.DESCRIPTION
    - Ensures dev infra containers are running (postgres, redis, jaeger, envoy, prometheus, grafana).
    - Launches backend and frontend as PowerShell jobs and tails their output.
    - Ctrl+C cleanly stops both. Infra is left running; use stop.ps1 -All to tear down.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

Write-Host "`n==> Ensuring dev infrastructure is up" -ForegroundColor Yellow
docker compose -f deploy/compose/docker-compose.dev.yml up -d

Write-Host "`n==> Starting backend (:8000) and frontend (:5173)" -ForegroundColor Yellow

$backendJob = Start-Job -Name dhruva-backend -ScriptBlock {
    param($Root)
    Set-Location (Join-Path $Root "backend")
    & (Join-Path ".venv" "Scripts/activate.ps1")
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
} -ArgumentList $RepoRoot

$frontendJob = Start-Job -Name dhruva-frontend -ScriptBlock {
    param($Root)
    Set-Location (Join-Path $Root "frontend")
    npm run dev
} -ArgumentList $RepoRoot

try {
    while ($backendJob.State -eq "Running" -or $frontendJob.State -eq "Running") {
        Receive-Job -Job $backendJob  | ForEach-Object { Write-Host "[backend]  $_" }
        Receive-Job -Job $frontendJob | ForEach-Object { Write-Host "[frontend] $_" }
        Start-Sleep -Milliseconds 400
    }
} finally {
    Write-Host "`n==> Shutting down" -ForegroundColor Yellow
    Stop-Job -Job $backendJob, $frontendJob -ErrorAction SilentlyContinue | Out-Null
    Remove-Job -Job $backendJob, $frontendJob -ErrorAction SilentlyContinue | Out-Null
}
