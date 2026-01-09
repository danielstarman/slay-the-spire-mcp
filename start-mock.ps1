# start-mock.ps1
# One-button startup for MCP server in mock mode
# Usage: .\start-mock.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== Slay the Spire MCP - Mock Mode Startup ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check if Docker is running
Write-Host "[1/4] Checking Docker status..." -ForegroundColor Yellow

$dockerRunning = $false
try {
    $null = docker ps 2>&1
    if ($LASTEXITCODE -eq 0) {
        $dockerRunning = $true
        Write-Host "      Docker is already running." -ForegroundColor Green
    }
} catch {
    # Docker not running
}

# Step 2: Start Docker Desktop if needed
if (-not $dockerRunning) {
    Write-Host "[2/4] Starting Docker Desktop..." -ForegroundColor Yellow

    $dockerPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path $dockerPath)) {
        Write-Host "ERROR: Docker Desktop not found at $dockerPath" -ForegroundColor Red
        Write-Host "Please install Docker Desktop or update the path in this script." -ForegroundColor Red
        exit 1
    }

    Start-Process $dockerPath
    Write-Host "      Docker Desktop launched. Waiting for daemon..." -ForegroundColor Yellow

    # Wait for Docker to be ready (max 60 seconds)
    $maxWait = 60
    $waited = 0
    $ready = $false

    while ($waited -lt $maxWait) {
        Start-Sleep -Seconds 2
        $waited += 2

        try {
            $null = docker ps 2>&1
            if ($LASTEXITCODE -eq 0) {
                $ready = $true
                break
            }
        } catch {
            # Still waiting
        }

        Write-Host "      Waiting... ($waited/$maxWait seconds)" -ForegroundColor Gray
    }

    if (-not $ready) {
        Write-Host "ERROR: Docker failed to start within $maxWait seconds." -ForegroundColor Red
        Write-Host "Please start Docker Desktop manually and try again." -ForegroundColor Red
        exit 1
    }

    Write-Host "      Docker is ready!" -ForegroundColor Green
} else {
    Write-Host "[2/4] Skipped (Docker already running)" -ForegroundColor Gray
}

# Step 3: Start the mock server
Write-Host "[3/4] Starting mock server container..." -ForegroundColor Yellow

# Change to project directory (where docker-compose.yml is)
Push-Location $PSScriptRoot

try {
    # Build and start in detached mode
    docker-compose --profile mock up server-mock --build -d

    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to start container." -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}

Write-Host "      Container started." -ForegroundColor Green

# Step 4: Wait for container to be healthy
Write-Host "[4/4] Waiting for server to be healthy..." -ForegroundColor Yellow

$maxHealthWait = 30
$healthWaited = 0
$healthy = $false

while ($healthWaited -lt $maxHealthWait) {
    Start-Sleep -Seconds 2
    $healthWaited += 2

    $health = docker inspect --format='{{.State.Health.Status}}' slay-the-spire-mcp-mock 2>&1

    if ($health -eq "healthy") {
        $healthy = $true
        break
    }

    Write-Host "      Health status: $health ($healthWaited/$maxHealthWait seconds)" -ForegroundColor Gray
}

if (-not $healthy) {
    Write-Host "WARNING: Container may not be fully healthy yet, but continuing..." -ForegroundColor Yellow
} else {
    Write-Host "      Server is healthy!" -ForegroundColor Green
}

# Success message
Write-Host ""
Write-Host "=== SUCCESS ===" -ForegroundColor Green
Write-Host ""
Write-Host "Mock server is running at: http://localhost:8000" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Restart Claude Code to pick up the MCP server"
Write-Host "  2. Try: 'get the game state' or 'show my deck'"
Write-Host ""
Write-Host "To stop: .\stop-mock.ps1" -ForegroundColor Gray
Write-Host ""
