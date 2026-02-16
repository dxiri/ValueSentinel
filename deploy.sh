#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# ValueSentinel — Deployment Script (macOS / Linux)
# Usage:
#   ./deploy.sh              Deploy with Docker Compose (default)
#   ./deploy.sh --local      Deploy locally without Docker
#   ./deploy.sh --help       Show usage information
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colors ───────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERR]${NC}  $*"; }

# ── Parse arguments ──────────────────────────────────────────
MODE="docker"
SKIP_ENV=false

for arg in "$@"; do
    case "$arg" in
        --local)  MODE="local" ;;
        --docker) MODE="docker" ;;
        --skip-env) SKIP_ENV=true ;;
        --help|-h)
            echo "Usage: ./deploy.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --docker     Deploy with Docker Compose (default)"
            echo "  --local      Deploy locally with Python venv"
            echo "  --skip-env   Skip .env configuration prompt"
            echo "  --help, -h   Show this message"
            exit 0
            ;;
        *)
            error "Unknown option: $arg"
            echo "Run './deploy.sh --help' for usage."
            exit 1
            ;;
    esac
done

# ── Header ───────────────────────────────────────────────────
echo -e "${BOLD}"
echo "╔═══════════════════════════════════════════╗"
echo "║       ValueSentinel Deployment            ║"
echo "║       Mode: $(printf '%-30s' "$MODE")║"
echo "╚═══════════════════════════════════════════╝"
echo -e "${NC}"

# ── Helper: check a command exists ───────────────────────────
require() {
    if ! command -v "$1" &>/dev/null; then
        error "'$1' is not installed or not in PATH."
        if [[ -n "${2:-}" ]]; then
            echo "  Install: $2"
        fi
        exit 1
    fi
}

# ── Step 1: Prerequisites ───────────────────────────────────
info "Checking prerequisites..."

require git

if [[ "$MODE" == "docker" ]]; then
    require docker "https://docs.docker.com/get-docker/"
    # Check docker compose (v2 plugin or standalone)
    if docker compose version &>/dev/null; then
        COMPOSE="docker compose"
    elif command -v docker-compose &>/dev/null; then
        COMPOSE="docker-compose"
    else
        error "'docker compose' is not available."
        echo "  Install Docker Compose v2: https://docs.docker.com/compose/install/"
        exit 1
    fi
    success "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
    success "Compose $($COMPOSE version --short 2>/dev/null || $COMPOSE version | awk '{print $NF}')"
else
    require python3 "https://www.python.org/downloads/"
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    # Verify Python >= 3.10
    MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
    if [[ "$MAJOR" -lt 3 ]] || [[ "$MAJOR" -eq 3 && "$MINOR" -lt 10 ]]; then
        error "Python 3.10+ required (found $PYTHON_VERSION)"
        exit 1
    fi
    success "Python $PYTHON_VERSION"
fi

# ── Step 2: Environment file ────────────────────────────────
info "Checking environment configuration..."

if [[ ! -f .env ]]; then
    if [[ -f .env.example ]]; then
        cp .env.example .env
        warn ".env created from .env.example"
        if [[ "$SKIP_ENV" == false ]]; then
            echo ""
            echo -e "${YELLOW}  Please edit .env with your configuration before continuing.${NC}"
            echo "  At minimum, set your notification channel credentials."
            echo ""
            read -rp "  Press Enter to open .env in your default editor, or Ctrl+C to abort... "
            ${EDITOR:-${VISUAL:-nano}} .env
        fi
    else
        error ".env.example not found — is this the project root?"
        exit 1
    fi
else
    success ".env already exists"
fi

# ── Step 3: Create required directories ─────────────────────
mkdir -p logs data
success "Directories ready (logs/, data/)"

# ═════════════════════════════════════════════════════════════
# DOCKER DEPLOYMENT
# ═════════════════════════════════════════════════════════════
if [[ "$MODE" == "docker" ]]; then

    info "Building Docker images..."
    $COMPOSE build

    success "Images built"

    info "Starting services..."
    $COMPOSE up -d

    echo ""
    info "Waiting for services to be healthy..."
    sleep 5

    # Check container status
    RUNNING=$($COMPOSE ps --format '{{.Name}} {{.State}}' 2>/dev/null || $COMPOSE ps)
    echo "$RUNNING"
    echo ""

    # Quick health check
    if curl -s --max-time 10 http://localhost:8501 &>/dev/null; then
        success "Dashboard is reachable at http://localhost:8501"
    else
        warn "Dashboard not responding yet — it may still be starting up."
        echo "  Check logs with: $COMPOSE logs -f app"
    fi

    echo ""
    echo -e "${GREEN}${BOLD}Deployment complete!${NC}"
    echo ""
    echo "  Dashboard:  http://localhost:8501"
    echo "  Logs:       $COMPOSE logs -f"
    echo "  Stop:       $COMPOSE down"
    echo "  Restart:    $COMPOSE restart"
    echo ""

# ═════════════════════════════════════════════════════════════
# LOCAL DEPLOYMENT
# ═════════════════════════════════════════════════════════════
else

    # Virtual environment
    info "Setting up Python virtual environment..."
    if [[ ! -d .venv ]]; then
        python3 -m venv .venv
        success "Virtual environment created at .venv/"
    else
        success "Virtual environment already exists"
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    success "Activated .venv ($(python3 --version))"

    # Install dependencies
    info "Installing dependencies..."
    pip install --upgrade pip setuptools wheel -q
    pip install -e ".[dev]" -q
    success "Dependencies installed"

    # Check for PostgreSQL driver if DATABASE_URL points to postgres
    if grep -q "^DATABASE_URL=postgresql" .env 2>/dev/null; then
        info "PostgreSQL detected in DATABASE_URL — installing driver..."
        pip install -e ".[postgres]" -q
        success "psycopg2 installed"
    fi

    # Run migrations
    info "Running database migrations..."
    alembic upgrade head
    success "Database schema up to date"

    echo ""
    echo -e "${GREEN}${BOLD}Local setup complete!${NC}"
    echo ""
    echo "  Activate env:    source .venv/bin/activate"
    echo "  Start dashboard: streamlit run src/valuesentinel/dashboard/app.py"
    echo "  Start scheduler: python -m valuesentinel run"
    echo "  Run tests:       pytest"
    echo "  Add a ticker:    python -m valuesentinel add-ticker AAPL"
    echo ""

fi
