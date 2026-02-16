# ─────────────────────────────────────────────────────────────
# ValueSentinel — Deployment Script (Windows PowerShell)
# Usage:
#   .\deploy.ps1              Deploy with Docker Compose (default)
#   .\deploy.ps1 -Mode local  Deploy locally without Docker
#   .\deploy.ps1 -Help        Show usage information
# ─────────────────────────────────────────────────────────────
[CmdletBinding()]
param(
    [ValidateSet("docker", "local")]
    [string]$Mode = "docker",

    [switch]$SkipEnv,

    [switch]$Help
)

$ErrorActionPreference = "Stop"

# ── Colors / Output helpers ──────────────────────────────────
function Write-Info    { param([string]$Msg) Write-Host "[INFO] $Msg" -ForegroundColor Cyan }
function Write-Ok      { param([string]$Msg) Write-Host "[OK]   $Msg" -ForegroundColor Green }
function Write-Warn    { param([string]$Msg) Write-Host "[WARN] $Msg" -ForegroundColor Yellow }
function Write-Err     { param([string]$Msg) Write-Host "[ERR]  $Msg" -ForegroundColor Red }

# ── Help ─────────────────────────────────────────────────────
if ($Help) {
    Write-Host @"
Usage: .\deploy.ps1 [OPTIONS]

Options:
  -Mode docker   Deploy with Docker Compose (default)
  -Mode local    Deploy locally with Python venv
  -SkipEnv       Skip .env configuration prompt
  -Help          Show this message
"@
    exit 0
}

# ── Header ───────────────────────────────────────────────────
Write-Host ""
Write-Host "+=============================================+" -ForegroundColor White
Write-Host "|       ValueSentinel Deployment              |" -ForegroundColor White
Write-Host "|       Mode: $($Mode.PadRight(32))|" -ForegroundColor White
Write-Host "+=============================================+" -ForegroundColor White
Write-Host ""

# ── Helper: check a command exists ───────────────────────────
function Require-Command {
    param(
        [string]$Name,
        [string]$InstallUrl = ""
    )
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Err "'$Name' is not installed or not in PATH."
        if ($InstallUrl) {
            Write-Host "  Install: $InstallUrl"
        }
        exit 1
    }
}

# ── Step 1: Prerequisites ───────────────────────────────────
Write-Info "Checking prerequisites..."

Require-Command "git"

if ($Mode -eq "docker") {
    Require-Command "docker" "https://docs.docker.com/get-docker/"

    # Check docker compose
    $composeAvailable = $false
    try {
        docker compose version 2>$null | Out-Null
        $composeAvailable = $true
    } catch {}

    if (-not $composeAvailable) {
        try {
            docker-compose version 2>$null | Out-Null
            $composeAvailable = $true
            $script:UseOldCompose = $true
        } catch {}
    }

    if (-not $composeAvailable) {
        Write-Err "'docker compose' is not available."
        Write-Host "  Install Docker Desktop: https://docs.docker.com/desktop/install/windows-install/"
        exit 1
    }

    $dockerVersion = (docker --version) -replace 'Docker version ', '' -replace ',.*', ''
    Write-Ok "Docker $dockerVersion"
    Write-Ok "Docker Compose available"
}
else {
    # Check Python
    $pythonCmd = $null
    foreach ($cmd in @("python", "python3", "py")) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) {
            $pythonCmd = $cmd
            break
        }
    }

    if (-not $pythonCmd) {
        Write-Err "Python is not installed or not in PATH."
        Write-Host "  Install: https://www.python.org/downloads/"
        exit 1
    }

    $pyVersion = & $pythonCmd --version 2>&1 | ForEach-Object { $_ -replace 'Python ', '' }
    $pyParts = $pyVersion -split '\.'
    $pyMajor = [int]$pyParts[0]
    $pyMinor = [int]$pyParts[1]

    if ($pyMajor -lt 3 -or ($pyMajor -eq 3 -and $pyMinor -lt 10)) {
        Write-Err "Python 3.10+ required (found $pyVersion)"
        exit 1
    }

    Write-Ok "Python $pyVersion ($pythonCmd)"
}

# ── Step 2: Environment file ────────────────────────────────
Write-Info "Checking environment configuration..."

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Warn ".env created from .env.example"

        if (-not $SkipEnv) {
            Write-Host ""
            Write-Host "  Please edit .env with your configuration before continuing." -ForegroundColor Yellow
            Write-Host "  At minimum, set your notification channel credentials."
            Write-Host ""
            $response = Read-Host "  Press Enter to open .env in Notepad, or type 'skip' to continue"
            if ($response -ne "skip") {
                if (Get-Command "code" -ErrorAction SilentlyContinue) {
                    & code .env
                    Write-Host "  Opened .env in VS Code. Save and close when done."
                    Read-Host "  Press Enter to continue"
                }
                else {
                    Start-Process notepad.exe -ArgumentList ".env" -Wait
                }
            }
        }
    }
    else {
        Write-Err ".env.example not found - is this the project root?"
        exit 1
    }
}
else {
    Write-Ok ".env already exists"
}

# ── Step 3: Create required directories ─────────────────────
if (-not (Test-Path "logs")) { New-Item -ItemType Directory -Path "logs" | Out-Null }
if (-not (Test-Path "data")) { New-Item -ItemType Directory -Path "data" | Out-Null }
Write-Ok "Directories ready (logs/, data/)"

# ═════════════════════════════════════════════════════════════
# DOCKER DEPLOYMENT
# ═════════════════════════════════════════════════════════════
if ($Mode -eq "docker") {

    function Invoke-Compose {
        param([Parameter(ValueFromRemainingArguments)]$Args)
        if ($script:UseOldCompose) {
            & docker-compose @Args
        } else {
            & docker compose @Args
        }
    }

    Write-Info "Building Docker images..."
    Invoke-Compose build
    if ($LASTEXITCODE -ne 0) { Write-Err "Docker build failed."; exit 1 }
    Write-Ok "Images built"

    Write-Info "Starting services..."
    Invoke-Compose up -d
    if ($LASTEXITCODE -ne 0) { Write-Err "Docker start failed."; exit 1 }

    Write-Host ""
    Write-Info "Waiting for services to be healthy..."
    Start-Sleep -Seconds 5

    Invoke-Compose ps

    Write-Host ""

    # Quick health check
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8501" -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
        Write-Ok "Dashboard is reachable at http://localhost:8501"
    }
    catch {
        Write-Warn "Dashboard not responding yet - it may still be starting up."
        Write-Host "  Check logs with: docker compose logs -f app"
    }

    Write-Host ""
    Write-Host "Deployment complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Dashboard:  http://localhost:8501"
    Write-Host "  Logs:       docker compose logs -f"
    Write-Host "  Stop:       docker compose down"
    Write-Host "  Restart:    docker compose restart"
    Write-Host ""
}

# ═════════════════════════════════════════════════════════════
# LOCAL DEPLOYMENT
# ═════════════════════════════════════════════════════════════
else {

    # Virtual environment
    Write-Info "Setting up Python virtual environment..."

    if (-not (Test-Path ".venv")) {
        & $pythonCmd -m venv .venv
        Write-Ok "Virtual environment created at .venv/"
    }
    else {
        Write-Ok "Virtual environment already exists"
    }

    # Activate
    $activateScript = Join-Path ".venv" "Scripts" "Activate.ps1"
    if (-not (Test-Path $activateScript)) {
        # Linux-style venv on WSL
        $activateScript = Join-Path ".venv" "bin" "Activate.ps1"
    }

    if (Test-Path $activateScript) {
        & $activateScript
        Write-Ok "Activated .venv"
    }
    else {
        Write-Warn "Could not find activation script - continuing with venv Python directly"
    }

    # Use the venv Python
    $venvPython = Join-Path ".venv" "Scripts" "python.exe"
    if (-not (Test-Path $venvPython)) {
        $venvPython = Join-Path ".venv" "bin" "python"
    }

    # Install dependencies
    Write-Info "Installing dependencies..."
    & $venvPython -m pip install --upgrade pip setuptools wheel -q
    & $venvPython -m pip install -e ".[dev]" -q
    Write-Ok "Dependencies installed"

    # Check for PostgreSQL driver
    $envContent = Get-Content ".env" -ErrorAction SilentlyContinue
    if ($envContent -match "^DATABASE_URL=postgresql") {
        Write-Info "PostgreSQL detected in DATABASE_URL - installing driver..."
        & $venvPython -m pip install -e ".[postgres]" -q
        Write-Ok "psycopg2 installed"
    }

    # Run migrations
    Write-Info "Running database migrations..."
    $venvAlembic = Join-Path ".venv" "Scripts" "alembic.exe"
    if (-not (Test-Path $venvAlembic)) {
        $venvAlembic = Join-Path ".venv" "bin" "alembic"
    }

    if (Test-Path $venvAlembic) {
        & $venvAlembic upgrade head
    }
    else {
        & $venvPython -m alembic upgrade head
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Err "Migration failed. Check DATABASE_URL in .env"
        exit 1
    }
    Write-Ok "Database schema up to date"

    Write-Host ""
    Write-Host "Local setup complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Activate env:    .\.venv\Scripts\Activate.ps1"
    Write-Host "  Start dashboard: streamlit run src\valuesentinel\dashboard\app.py"
    Write-Host "  Start scheduler: python -m valuesentinel run"
    Write-Host "  Run tests:       pytest"
    Write-Host "  Add a ticker:    python -m valuesentinel add-ticker AAPL"
    Write-Host ""
}
