# stop-mock.ps1
# Stop the MCP mock server
# Usage: .\stop-mock.ps1 [-StopDocker]

param(
    [switch]$StopDocker = $false
)

$ErrorActionPreference = "Stop"

Write-Host "=== Slay the Spire MCP - Stopping Mock Mode ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Stop the container
Write-Host "[1/2] Stopping mock server container..." -ForegroundColor Yellow

Push-Location $PSScriptRoot

try {
    docker-compose --profile mock down

    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARNING: docker-compose down returned non-zero exit code." -ForegroundColor Yellow
    } else {
        Write-Host "      Container stopped." -ForegroundColor Green
    }
} catch {
    Write-Host "WARNING: Could not stop container (may not be running)." -ForegroundColor Yellow
} finally {
    Pop-Location
}

# Step 2: Optionally stop Docker Desktop
if ($StopDocker) {
    Write-Host "[2/2] Stopping Docker Desktop..." -ForegroundColor Yellow

    try {
        # Graceful shutdown via taskkill
        Stop-Process -Name "Docker Desktop" -Force -ErrorAction SilentlyContinue
        Write-Host "      Docker Desktop stopped." -ForegroundColor Green
    } catch {
        Write-Host "      Could not stop Docker Desktop (may not be running)." -ForegroundColor Gray
    }
} else {
    Write-Host "[2/2] Skipped (use -StopDocker to also stop Docker Desktop)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Green
Write-Host ""
