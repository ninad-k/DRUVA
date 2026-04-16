<#
.SYNOPSIS
    Apply Alembic migrations, or create a new one with -Create.

.EXAMPLE
    pwsh ./scripts/migrate.ps1
    pwsh ./scripts/migrate.ps1 -Create "add users table"
#>
[CmdletBinding()]
param(
    [string]$Create
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location (Join-Path $RepoRoot "backend")
& (Join-Path ".venv" "Scripts/activate.ps1")

if ($Create) {
    alembic revision --autogenerate -m $Create
} else {
    alembic upgrade head
}
