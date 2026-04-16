<#
.SYNOPSIS
    Stop DHRUVA backend + frontend processes. With -All, also stops infra.
#>
[CmdletBinding()]
param([switch]$All)

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

Get-Process | Where-Object { $_.Name -match "uvicorn|python" -and $_.CommandLine -match "app.main:app" } |
    ForEach-Object { try { Stop-Process -Id $_.Id -Force } catch {} }

Get-Process | Where-Object { $_.Name -match "node" -and $_.CommandLine -match "vite" } |
    ForEach-Object { try { Stop-Process -Id $_.Id -Force } catch {} }

Write-Host "Stopped backend + frontend processes" -ForegroundColor Green

if ($All) {
    docker compose -f deploy/compose/docker-compose.dev.yml down
    Write-Host "Infrastructure stopped" -ForegroundColor Green
}
