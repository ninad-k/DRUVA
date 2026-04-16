<#
.SYNOPSIS
    Build production Docker images for DHRUVA backend + frontend.
#>
[CmdletBinding()]
param([string]$Version = $env:DHRUVA_VERSION)
if (-not $Version) { $Version = "latest" }

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

Write-Host "==> Building dhruva/backend:$Version" -ForegroundColor Yellow
docker build -t "dhruva/backend:$Version"  -f backend/Dockerfile  backend

Write-Host "==> Building dhruva/frontend:$Version" -ForegroundColor Yellow
docker build -t "dhruva/frontend:$Version" -f frontend/Dockerfile frontend

Write-Host "==> Done" -ForegroundColor Green
docker images | Select-String "dhruva/(backend|frontend)"
