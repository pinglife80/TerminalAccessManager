#!/bin/bash
###############################################################################
# TerminalAccessManager - Unified Management Script
#
# A single, robust, idempotent script for full project lifecycle management.
#
# Usage: ./manage.sh [OPTIONS] <command> [ARGS]
#
# Options:
#   -y, --yes       Skip confirmation prompts (non-interactive mode)
#   -v, --verbose   Enable verbose/debug output
#   -h, --help      Show help message
#
# Lifecycle Commands:
#   deploy [--demo|--prod]     Full deployment with initialization wizard
#   start                      Start all services (idempotent)
#   stop                       Stop all services (idempotent)
#   restart [service]          Restart all or specific service
#   status                     Show service status and health
#   health                     Deep health check of all components
#   update                     Rebuild and restart (local code changes only)
#   upgrade [version]          Pull remote code and upgrade (with safety checks)
#
# Data Commands:
#   init                       Initialize database + admin user (idempotent)
#   migrate [revision]         Run database migrations (idempotent)
#   mock generate              Generate demo/mock data (idempotent)
#   mock clear                 Clear all mock data (keeps admin)
#   backup [file]              Backup database to SQL file
#   restore <file>             Restore database from SQL file
#
# Development Commands:
#   test                       Run backend test suite
#   shell [backend|db|redis]   Access service shell
#   logs [service] [-n N]      View logs (follow mode)
#   validate                   Run project validation checks
#
# Utility Commands:
#   config                     Show .env file configuration
#   config list                List all database system settings
#   config get <key>           Get a specific setting value
#   config set <key> <value>   Set a specific setting value
#   config branding [key] [v]  View or set branding configuration
#   config upload <purpose> <f> Upload branding resource (login_bg|favicon)
#   redis info                 Show Redis server info
#   redis keys [pattern]       List Redis keys (default pattern: *)
#   redis get <key>            Get a Redis key value
#   redis del <key>            Delete a Redis key
#   redis flush [db]           Flush Redis database (default: db 0)
#   scheduler status           Show scheduler task status and intervals
#   scheduler pause <task>     Pause a scheduler task
#   scheduler resume <task>    Resume a paused scheduler task
#   scheduler trigger <task>   Manually trigger a scheduler task
#   scheduler intervals        Show current scheduler intervals from config
#   ssl [--force]              Generate SSL certificates (idempotent)
#   clean                      Remove all containers, volumes, data
#   version                    Show version information
#   help                       Show this help message
###############################################################################

set -euo pipefail

###############################################################################
# Constants
###############################################################################
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly ENV_FILE="${SCRIPT_DIR}/.env"
readonly ENV_EXAMPLE="${SCRIPT_DIR}/.env.example"
readonly BACKUP_DIR="${SCRIPT_DIR}/backups"
readonly LOCK_FILE="/tmp/tam_manage.lock"
readonly STATE_DIR="${SCRIPT_DIR}/.manage"
readonly STATE_FILE="${STATE_DIR}/state.env"
readonly VERSION="2.0.0"

# Docker Compose project name (derived from directory name)
readonly COMPOSE_PROJECT_NAME="tam"

# Colors
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly MAGENTA='\033[0;35m'
readonly BOLD='\033[1m'
readonly DIM='\033[2m'
readonly NC='\033[0m'

###############################################################################
# Global Options
###############################################################################
YES_FLAG=false
VERBOSE_FLAG=false

###############################################################################
# Logging
###############################################################################
log_info()    { echo -e "${BLUE}[INFO]${NC}    $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}      $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}    $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC}   $*" >&2; }
log_verbose() { ${VERBOSE_FLAG} && echo -e "${DIM}[DEBUG]${NC}   $*" || true; }
log_step()    { echo -e "\n${CYAN}${BOLD}━━━ $* ━━━${NC}\n"; }
log_banner()  {
    echo -e "${CYAN}${BOLD}"
    echo "  ╔═══════════════════════════════════════════════════════╗"
    echo "  ║                                                       ║"
    echo "  ║          TerminalAccessManager v${VERSION}                ║"
    echo "  ║          Unified Management Script                    ║"
    echo "  ║                                                       ║"
    echo "  ╚═══════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

###############################################################################
# State Management (track deployment state for idempotency)
###############################################################################
save_state() {
    local key="$1"
    local value="$2"
    mkdir -p "${STATE_DIR}"
    if [ -f "${STATE_FILE}" ] && grep -q "^${key}=" "${STATE_FILE}" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${value}|" "${STATE_FILE}"
    else
        echo "${key}=${value}" >> "${STATE_FILE}"
    fi
}

get_state() {
    local key="$1"
    if [ -f "${STATE_FILE}" ]; then
        grep "^${key}=" "${STATE_FILE}" 2>/dev/null | cut -d'=' -f2- || echo ""
    else
        echo ""
    fi
}

is_deployed() {
    [ "$(get_state 'deployed')" = "true" ]
}

is_initialized() {
    [ "$(get_state 'db_initialized')" = "true" ]
}

###############################################################################
# Utility Functions
###############################################################################

# Check if a command exists
require_cmd() {
    if ! command -v "$1" &>/dev/null; then
        log_error "'$1' is required but not installed."
        case "$1" in
            docker) log_error "Install: https://docs.docker.com/get-docker/" ;;
            openssl) log_error "Install: apt-get install openssl / yum install openssl" ;;
            curl) log_error "Install: apt-get install curl / yum install curl" ;;
        esac
        exit 1
    fi
}

# Prompt for confirmation. Respects -y flag.
confirm() {
    local message="$1"
    local default="${2:-default_no}"

    if ${YES_FLAG}; then
        return 0
    fi

    local prompt
    if [ "$default" = "default_yes" ]; then
        prompt="[Y/n]"
    else
        prompt="[y/N]"
    fi

    echo -e "${YELLOW}${message}${NC} ${prompt}"
    read -rp "> " answer

    case "$answer" in
        [Yy]|[Yy][Ee][Ss]) return 0 ;;
        "") [ "$default" = "default_yes" ] && return 0 || return 1 ;;
        *) return 1 ;;
    esac
}

# Prompt for input with default value
prompt_input() {
    local message="$1"
    local default="${2:-}"
    local var_name="$3"

    if [ -n "$default" ]; then
        echo -e "${CYAN}${message}${NC} [${default}]"
    else
        echo -e "${CYAN}${message}${NC}"
    fi
    read -rp "> " input
    input="${input:-$default}"
    eval "${var_name}='${input}'"
}

# Prompt for password (hidden input)
prompt_password() {
    local message="$1"
    local var_name="$2"
    local required="${3:-true}"

    echo -e "${CYAN}${message}${NC}"
    read -rsp "> " input
    echo ""

    if ${required} && [ -z "$input" ]; then
        log_error "Password cannot be empty"
        exit 1
    fi
    eval "${var_name}='${input}'"
}

# Acquire lock to prevent concurrent execution
acquire_lock() {
    if [ -f "${LOCK_FILE}" ]; then
        local lock_pid
        lock_pid=$(cat "${LOCK_FILE}" 2>/dev/null || echo "")
        if [ -n "$lock_pid" ] && kill -0 "$lock_pid" 2>/dev/null; then
            log_error "Another manage.sh instance is running (PID: ${lock_pid})"
            log_error "If stale, remove lock: rm -f ${LOCK_FILE}"
            exit 1
        fi
        rm -f "${LOCK_FILE}"
    fi
    echo $$ > "${LOCK_FILE}"
}

release_lock() {
    rm -f "${LOCK_FILE}"
}

# Run docker compose with .env loaded
dc() {
    docker compose --env-file "${ENV_FILE}" -f "${SCRIPT_DIR}/docker-compose.yml" "$@"
}

# Ensure .env file exists (idempotent — never overwrites existing)
ensure_env() {
    if [ -f "${ENV_FILE}" ]; then
        log_verbose ".env file exists"
        return 0
    fi

    if [ -f "${ENV_EXAMPLE}" ]; then
        cp "${ENV_EXAMPLE}" "${ENV_FILE}"
        log_info "Created .env from .env.example"
    else
        log_error "No .env or .env.example found. Cannot continue."
        exit 1
    fi
}

# Check required environment variables for security
_INSECURE_VALUES=("password" "redis_password" "your-secret-key-change-in-production" "change-this-to-a-random-secret-key-in-production" "your-encryption-key-change-in-production" "change-this-to-a-unique-encryption-key")

_check_required_env() {
    local missing=()
    local insecure=()

    # Check required variables
    for var in DB_PASSWORD REDIS_PASSWORD SECRET_KEY; do
        local val
        val=$(get_env "${var}")
        if [ -z "$val" ]; then
            missing+=("${var}")
        elif echo "${_INSECURE_VALUES[@]}" | grep -qw "$val"; then
            insecure+=("${var}=${val}")
        fi
    done

    # Check ENCRYPTION_KEY (required for production, optional for dev)
    local enc_key
    enc_key=$(get_env "ENCRYPTION_KEY")
    local env_mode
    env_mode=$(get_env "ENVIRONMENT")
    if [ "${env_mode}" = "production" ]; then
        if [ -z "$enc_key" ]; then
            missing+=("ENCRYPTION_KEY")
        elif echo "${_INSECURE_VALUES[@]}" | grep -qw "$enc_key"; then
            insecure+=("ENCRYPTION_KEY=${enc_key}")
        fi
        # Check ENCRYPTION_KEY != SECRET_KEY
        local secret_val
        secret_val=$(get_env "SECRET_KEY")
        if [ -n "$enc_key" ] && [ "$enc_key" = "$secret_val" ]; then
            log_error "ENCRYPTION_KEY must be different from SECRET_KEY in production"
            insecure+=("ENCRYPTION_KEY=same_as_SECRET_KEY")
        fi
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        log_error "Required environment variables not set: ${missing[*]}"
        log_error "Run './manage.sh deploy' to configure, or edit .env manually"
        exit 1
    fi

    if [ ${#insecure[@]} -gt 0 ]; then
        log_warn "Insecure default values detected:"
        for item in "${insecure[@]}"; do
            log_warn "  - ${item}"
        done
        log_warn "These values are not safe for production. Run './manage.sh deploy --prod' to reconfigure."
        if [ "${env_mode}" = "production" ]; then
            log_error "Insecure defaults are not allowed in production mode. Aborting."
            exit 1
        fi
    fi
}

# Wait for a service to become healthy (with timeout)
wait_healthy() {
    local service="$1"
    local timeout="${2:-120}"
    local elapsed=0

    while [ $elapsed -lt $timeout ]; do
        local status
        status=$(dc ps "$service" --format json 2>/dev/null \
            | grep -o '"Health":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "")

        if [ "$status" = "healthy" ]; then
            log_verbose "$service is healthy"
            return 0
        fi

        # For services without healthcheck, "Up" is sufficient
        if [ -z "$status" ]; then
            if dc ps "$service" --format '{{.Status}}' 2>/dev/null | grep -q "Up"; then
                log_verbose "$service is running (no healthcheck defined)"
                return 0
            fi
        fi

        sleep 3
        elapsed=$((elapsed + 3))
    done

    log_warn "Service '$service' did not become healthy within ${timeout}s"
    return 1
}

# Check if any services are running
services_running() {
    dc ps --services --filter "status=running" 2>/dev/null | grep -q .
}

# Check if a specific service is running
service_running() {
    local service="$1"
    dc ps "$service" --format '{{.Status}}' 2>/dev/null | grep -q "Up"
}

# Require services to be running, exit with helpful message if not
require_services() {
    if ! services_running; then
        log_error "Services are not running."
        log_error "Start them first: ./manage.sh start"
        exit 1
    fi
}

# Get the value of an env variable from .env
get_env() {
    local key="$1"
    grep "^${key}=" "${ENV_FILE}" 2>/dev/null | cut -d'=' -f2- || echo ""
}

# Set an env variable in .env
set_env() {
    local key="$1"
    local value="$2"

    if grep -q "^${key}=" "${ENV_FILE}" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
    else
        echo "${key}=${value}" >> "${ENV_FILE}"
    fi
}

# Auto-backup before destructive operations
auto_backup() {
    local label="${1:-pre_op}"
    if ! services_running; then
        return 0
    fi
    mkdir -p "${BACKUP_DIR}"
    local backup_file="${BACKUP_DIR}/auto_${label}_$(date +%Y%m%d_%H%M%S).sql"
    if dc exec -T postgres pg_dump -U tam_admin tam_db > "$backup_file" 2>/dev/null; then
        log_verbose "Auto-backup saved: ${backup_file}"
    fi
}

# Start services in dependency order
start_services_ordered() {
    log_info "Starting infrastructure services..."
    dc up -d postgres redis
    wait_healthy postgres 120 || true
    wait_healthy redis 60 || true

    log_info "Starting application services..."
    dc up -d backend
    wait_healthy backend 60 || true

    log_info "Starting frontend and proxy..."
    dc up -d frontend nginx

    # Wait for frontend build to complete
    local fe_wait=0
    while [ $fe_wait -lt 120 ]; do
        if dc ps frontend --format '{{.Status}}' 2>/dev/null | grep -q "Exited"; then
            break
        fi
        sleep 3
        fe_wait=$((fe_wait + 3))
    done

    # Restart nginx to pick up frontend files
    dc restart nginx 2>/dev/null || true
    wait_healthy nginx 30 2>/dev/null || true
}

# Stop services in reverse dependency order
stop_services_ordered() {
    log_info "Stopping proxy and frontend..."
    dc stop nginx frontend 2>/dev/null || true

    log_info "Stopping application services..."
    dc stop backend 2>/dev/null || true

    log_info "Stopping infrastructure services..."
    dc stop redis postgres 2>/dev/null || true
}

###############################################################################
# Command: version
###############################################################################
cmd_version() {
    echo -e "${CYAN}${BOLD}TerminalAccessManager${NC}"
    echo ""
    echo -e "  ${BOLD}Version:${NC}     ${VERSION}"
    echo -e "  ${BOLD}Script:${NC}      ${SCRIPT_DIR}/manage.sh"
    echo -e "  ${BOLD}Docker:${NC}      $(docker --version 2>/dev/null || echo 'N/A')"
    echo -e "  ${BOLD}Compose:${NC}     $(docker compose version 2>/dev/null || echo 'N/A')"
    echo ""

    # Environment info
    if [ -f "${ENV_FILE}" ]; then
        echo -e "  ${BOLD}Env file:${NC}    ${GREEN}exists${NC}"
        local deploy_mode
        deploy_mode=$(get_state 'deploy_mode')
        if [ -n "$deploy_mode" ]; then
            echo -e "  ${BOLD}Deploy mode:${NC} ${deploy_mode}"
        fi
    else
        echo -e "  ${BOLD}Env file:${NC}    ${YELLOW}not found${NC}"
    fi

    # Service status
    if services_running 2>/dev/null; then
        echo -e "  ${BOLD}Status:${NC}      ${GREEN}Running${NC}"
        # Show running services count
        local running_count
        running_count=$(dc ps --services --filter "status=running" 2>/dev/null | wc -l)
        echo -e "  ${BOLD}Services:${NC}    ${running_count} running"
    else
        echo -e "  ${BOLD}Status:${NC}      ${DIM}Stopped${NC}"
    fi

    # Database status
    if is_initialized; then
        echo -e "  ${BOLD}Database:${NC}    ${GREEN}initialized${NC}"
    else
        echo -e "  ${BOLD}Database:${NC}    ${DIM}not initialized${NC}"
    fi
}

###############################################################################
# Command: deploy — Full deployment with initialization wizard
###############################################################################
cmd_deploy() {
    local mode=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --demo)  mode="demo"  ;;
            --prod)  mode="prod"  ;;
            *)       log_error "Unknown option: $1"; cmd_help; exit 1 ;;
        esac
        shift
    done

    log_banner

    # ─── Step 1: Choose deployment mode ──────────────────────────────────
    if [ -z "$mode" ]; then
        echo -e "${BOLD}Select deployment mode:${NC}"
        echo ""
        echo -e "  ${GREEN}1) Demo${NC}        - Quick start with auto-config and sample data"
        echo -e "                  Best for: evaluation, testing, development"
        echo ""
        echo -e "  ${YELLOW}2) Production${NC}  - Manual configuration, production-ready"
        echo -e "                  Best for: live deployment, real traffic"
        echo ""
        read -rp "Choose [1/2]: " choice
        case "$choice" in
            1) mode="demo"  ;;
            2) mode="prod"  ;;
            *) log_error "Invalid selection"; exit 1 ;;
        esac
    fi

    save_state 'deploy_mode' "$mode"
    log_step "Deploying TerminalAccessManager (${mode} mode)"

    # ─── Step 2: Prerequisites check ─────────────────────────────────────
    log_step "Step 1/6: Checking Prerequisites"
    require_cmd docker
    require_cmd openssl

    if ! docker compose version &>/dev/null; then
        log_error "Docker Compose v2 is required"
        log_error "Install: https://docs.docker.com/compose/install/"
        exit 1
    fi

    if ! docker info &>/dev/null; then
        log_error "Docker daemon is not running"
        log_error "Start it: sudo systemctl start docker"
        exit 1
    fi

    # Disk space check
    local free_gb
    free_gb=$(df -BG "${SCRIPT_DIR}" | tail -1 | awk '{print $4}' | sed 's/G//')
    if [ "${free_gb:-0}" -lt 3 ]; then
        log_error "Insufficient disk space: ${free_gb}GB (minimum: 3GB, recommended: 5GB+)"
        exit 1
    fi
    log_success "Disk space: ${free_gb}GB available"

    # Port availability check
    for port in 8080 8443; do
        if ss -tlnp 2>/dev/null | grep -q ":${port} " || \
           netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
            log_warn "Port ${port} is already in use (may cause conflicts)"
        fi
    done

    log_success "Prerequisites OK"

    # ─── Step 3: SSL Certificates ────────────────────────────────────────
    log_step "Step 2/6: SSL Certificates"
    cmd_ssl

    # ─── Step 4: Environment Configuration ───────────────────────────────
    log_step "Step 3/6: Environment Configuration"

    if [ "$mode" = "demo" ]; then
        _configure_demo_env
    else
        _configure_production_wizard
    fi

    # ─── Step 5: Build & Start ───────────────────────────────────────────
    log_step "Step 4/6: Building and Starting Services"

    log_info "Pulling base images..."
    dc pull 2>/dev/null || true

    log_info "Building application images..."
    dc up -d --build

    log_success "Images built"

    # ─── Step 6: Wait for services ───────────────────────────────────────
    log_step "Step 5/6: Waiting for Services"

    log_info "Waiting for PostgreSQL..."
    if wait_healthy postgres 120; then
        log_success "PostgreSQL is ready"
    else
        log_error "PostgreSQL failed to start. Check logs: ./manage.sh logs postgres"
        exit 1
    fi

    log_info "Waiting for Redis..."
    if wait_healthy redis 60; then
        log_success "Redis is ready"
    else
        log_error "Redis failed to start. Check logs: ./manage.sh logs redis"
        exit 1
    fi

    log_info "Waiting for Backend..."
    if wait_healthy backend 90; then
        log_success "Backend is ready"
    else
        log_error "Backend failed to start. Check logs: ./manage.sh logs backend"
        exit 1
    fi

    log_info "Waiting for Frontend build..."
    local fe_wait=0
    while [ $fe_wait -lt 180 ]; do
        if dc ps frontend --format '{{.Status}}' 2>/dev/null | grep -q "Exited"; then
            break
        fi
        sleep 3
        fe_wait=$((fe_wait + 3))
    done

    if [ $fe_wait -ge 180 ]; then
        log_warn "Frontend build is taking longer than expected"
    fi

    # Restart nginx to pick up frontend files
    dc restart nginx 2>/dev/null || true
    wait_healthy nginx 30 2>/dev/null || true
    log_success "All services ready"

    # ─── Step 7: Initialize Database ─────────────────────────────────────
    log_step "Step 6/6: Initializing Database"

    if is_initialized; then
        log_info "Database already initialized (skipping)"
    else
        if dc exec -T backend python cli.py setup 2>&1; then
            save_state 'db_initialized' 'true'
            log_success "Database initialized"
        else
            log_warn "Database init had warnings (may already be initialized)"
            save_state 'db_initialized' 'true'
        fi
    fi

    # ─── Demo Data ───────────────────────────────────────────────────────
    if [ "$mode" = "demo" ]; then
        log_step "Generating Demo Data"
        dc exec -T backend python cli.py mock generate
        log_success "Demo data generated"
    fi

    # ─── Save deployment state ───────────────────────────────────────────
    save_state 'deployed' 'true'
    save_state 'deploy_time' "$(date -Iseconds)"

    # ─── Verify ──────────────────────────────────────────────────────────
    log_step "Verifying Deployment"
    dc ps
    echo ""

    local http_ok=false
    if curl -sk -o /dev/null -w "%{http_code}" https://localhost:8443/ 2>/dev/null | grep -q "200"; then
        log_success "HTTPS: https://localhost:8443 (200 OK)"
        http_ok=true
    elif curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ 2>/dev/null | grep -q "200\|301"; then
        log_success "HTTP:  http://localhost:8080 (200 OK)"
        http_ok=true
    fi

    if [ "$http_ok" = false ]; then
        log_warn "Web interface not yet accessible (may need a moment)"
        log_info "Check status: ./manage.sh status"
    fi

    # ─── Summary ─────────────────────────────────────────────────────────
    echo ""
    echo -e "${GREEN}${BOLD}╔═══════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║            Deployment Complete!                        ║${NC}"
    echo -e "${GREEN}${BOLD}╚═══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${CYAN}HTTPS:${NC}  https://localhost:8443"
    echo -e "  ${CYAN}HTTP:${NC}   http://localhost:8080 (redirects to HTTPS)"
    echo ""

    if [ "$mode" = "demo" ]; then
        echo -e "  ${CYAN}Login:${NC}   admin / Admin123"
        echo ""
        echo -e "  ${YELLOW}This is a DEMO environment with sample data${NC}"
        echo -e "  ${YELLOW}NOT suitable for production use${NC}"
    else
        echo -e "  ${CYAN}Login:${NC}   admin / [password you set]"
        echo ""
        echo -e "  ${YELLOW}Change the default password after first login${NC}"
    fi

    echo ""
    echo -e "  ${DIM}Next steps:${NC}"
    echo -e "  ${DIM}  ./manage.sh status     # Check service health${NC}"
    echo -e "  ${DIM}  ./manage.sh logs       # View application logs${NC}"
    echo -e "  ${DIM}  ./manage.sh health     # Deep health check${NC}"
    echo -e "  ${DIM}  ./manage.sh help       # See all commands${NC}"
    echo ""
}

_configure_demo_env() {
    # Demo: always regenerate .env for consistency
    rm -f "${ENV_FILE}"
    cp "${ENV_EXAMPLE}" "${ENV_FILE}"

    local db_pass redis_pass secret enc_key
    db_pass="demo_db_pass_$(openssl rand -hex 4)"
    redis_pass="demo_redis_$(openssl rand -hex 4)"
    secret="$(openssl rand -hex 32)"
    enc_key="$(openssl rand -hex 32)"

    set_env "DB_PASSWORD" "${db_pass}"
    set_env "REDIS_PASSWORD" "${redis_pass}"
    set_env "SECRET_KEY" "${secret}"
    set_env "ENCRYPTION_KEY" "${enc_key}"

    # Clear optional integrations
    set_env "SANGFOR_BASE_URL" ""
    set_env "SANGFOR_USERNAME" ""
    set_env "SANGFOR_PASSWORD" ""
    set_env "SWITCH_HOST" ""
    set_env "SWITCH_USERNAME" ""
    set_env "SWITCH_PASSWORD" ""

    log_success "Demo environment configured (auto-generated passwords)"
}

_configure_production_wizard() {
    echo -e "${BOLD}${MAGENTA}Production Configuration Wizard${NC}"
    echo -e "${DIM}This wizard will guide you through the production setup.${NC}"
    echo ""

    # ─── Existing config check ───────────────────────────────────────────
    if [ -f "${ENV_FILE}" ]; then
        log_info "Existing .env configuration found"
        if ! ${YES_FLAG}; then
            echo ""
            echo -e "  ${CYAN}1)${NC} Keep existing configuration"
            echo -e "  ${CYAN}2)${NC} Reconfigure from scratch"
            echo -e "  ${CYAN}3)${NC} Review and edit existing values"
            echo ""
            read -rp "Choose [1/2/3]: " env_choice
            case "${env_choice:-1}" in
                1)
                    log_info "Using existing .env configuration"
                    return 0
                    ;;
                2)
                    rm -f "${ENV_FILE}"
                    cp "${ENV_EXAMPLE}" "${ENV_FILE}"
                    ;;
                3)
                    _edit_existing_env
                    return 0
                    ;;
                *)
                    log_info "Using existing .env configuration"
                    return 0
                    ;;
            esac
        else
            log_info "Using existing .env (-y flag set)"
            return 0
        fi
    else
        cp "${ENV_EXAMPLE}" "${ENV_FILE}"
    fi

    # ─── Database Configuration ──────────────────────────────────────────
    echo ""
    echo -e "${BOLD}── Database Configuration ──${NC}"
    echo -e "${DIM}PostgreSQL connection settings${NC}"
    echo ""

    local db_pass
    prompt_password "Set database password (min 8 characters recommended):" db_pass
    if [ ${#db_pass} -lt 8 ]; then
        log_warn "Password is short — consider using a stronger one"
    fi
    set_env "DB_PASSWORD" "${db_pass}"

    # ─── Redis Configuration ─────────────────────────────────────────────
    echo ""
    echo -e "${BOLD}── Redis Configuration ──${NC}"
    echo -e "${DIM}Redis cache connection settings${NC}"
    echo ""

    local redis_pass
    prompt_password "Set Redis password:" redis_pass
    set_env "REDIS_PASSWORD" "${redis_pass}"

    # ─── Security Configuration ──────────────────────────────────────────
    echo ""
    echo -e "${BOLD}── Security Configuration ──${NC}"
    echo ""

    local secret
    secret="$(openssl rand -hex 32)"
    set_env "SECRET_KEY" "${secret}"
    log_info "JWT secret key auto-generated"

    # ─── Encryption Key ────────────────────────────────────────────────────
    local enc_key
    enc_key="$(openssl rand -hex 32)"
    set_env "ENCRYPTION_KEY" "${enc_key}"
    log_info "Encryption key auto-generated (separate from JWT secret)"

    # ─── Optional Integrations ───────────────────────────────────────────
    echo ""
    echo -e "${BOLD}── Optional Integrations ──${NC}"
    echo -e "${DIM}Configure external integrations (can be set later via ./manage.sh config)${NC}"
    echo ""

    # Sangfor API
    if confirm "Configure Sangfor API integration?" "default_no"; then
        local s_url s_user s_pass
        prompt_input "Sangfor API URL (e.g. https://api.sangfor.com/v1):" "" s_url
        prompt_input "Sangfor username:" "" s_user
        prompt_password "Sangfor password:" s_pass "false"
        set_env "SANGFOR_BASE_URL" "${s_url}"
        set_env "SANGFOR_USERNAME" "${s_user}"
        set_env "SANGFOR_PASSWORD" "${s_pass}"
        log_success "Sangfor API configured"
    else
        set_env "SANGFOR_BASE_URL" ""
        set_env "SANGFOR_USERNAME" ""
        set_env "SANGFOR_PASSWORD" ""
    fi

    # Network Switch
    if confirm "Configure network switch integration?" "default_no"; then
        local sw_host sw_user sw_pass
        prompt_input "Switch IP address:" "" sw_host
        prompt_input "Switch username:" "" sw_user
        prompt_password "Switch password:" sw_pass "false"
        set_env "SWITCH_HOST" "${sw_host}"
        set_env "SWITCH_USERNAME" "${sw_user}"
        set_env "SWITCH_PASSWORD" "${sw_pass}"
        log_success "Network switch configured"
    else
        set_env "SWITCH_HOST" ""
        set_env "SWITCH_USERNAME" ""
        set_env "SWITCH_PASSWORD" ""
    fi

    # ─── Summary ─────────────────────────────────────────────────────────
    echo ""
    echo -e "${BOLD}── Configuration Summary ──${NC}"
    echo -e "  Database password:  ${GREEN}set${NC}"
    echo -e "  Redis password:     ${GREEN}set${NC}"
    echo -e "  JWT secret:         ${GREEN}auto-generated${NC}"
    echo -e "  Encryption key:     ${GREEN}auto-generated${NC}"
    echo -e "  Sangfor API:        $(if [ -n "$(get_env SANGFOR_BASE_URL)" ]; then echo "${GREEN}configured${NC}"; else echo "${DIM}skipped${NC}"; fi)"
    echo -e "  Network switch:     $(if [ -n "$(get_env SWITCH_HOST)" ]; then echo "${GREEN}configured${NC}"; else echo "${DIM}skipped${NC}"; fi)"
    echo ""

    log_success "Production environment configured"
}

_edit_existing_env() {
    echo ""
    echo -e "${BOLD}Current configuration:${NC}"
    echo ""

    local keys=("DB_PASSWORD" "REDIS_PASSWORD" "SECRET_KEY" "ENCRYPTION_KEY" "SANGFOR_BASE_URL" "SWITCH_HOST")
    local labels=("Database password" "Redis password" "JWT Secret Key" "Encryption Key" "Sangfor API URL" "Switch Host")

    for i in "${!keys[@]}"; do
        local val
        val=$(get_env "${keys[$i]}")
        if [ "${keys[$i]}" = "DB_PASSWORD" ] || [ "${keys[$i]}" = "REDIS_PASSWORD" ] || [ "${keys[$i]}" = "SECRET_KEY" ] || [ "${keys[$i]}" = "ENCRYPTION_KEY" ]; then
            echo -e "  ${labels[$i]}: ${DIM}(set)${NC}"
        else
            echo -e "  ${labels[$i]}: ${val:-${DIM}(empty)${NC}}"
        fi
    done

    echo ""
    echo -e "Enter key name to update, or press Enter to finish:"
    while true; do
        read -rp "> " key_to_edit
        [ -z "$key_to_edit" ] && break

        if ! grep -q "^${key_to_edit}=" "${ENV_FILE}" 2>/dev/null; then
            log_warn "Key '${key_to_edit}' not found in .env"
            continue
        fi

        if [[ "$key_to_edit" == *"PASSWORD"* ]] || [[ "$key_to_edit" == *"SECRET"* ]]; then
            prompt_password "New value for ${key_to_edit}:" new_val "false"
        else
            prompt_input "New value for ${key_to_edit}:" "$(get_env "$key_to_edit")" new_val
        fi
        set_env "$key_to_edit" "$new_val"
        log_success "Updated ${key_to_edit}"
    done

    log_success "Configuration updated"
}

###############################################################################
# Command: start
###############################################################################
cmd_start() {
    ensure_env
    _check_required_env
    log_step "Starting Services"

    if services_running; then
        log_info "Services already running"
        dc ps
        return 0
    fi

    start_services_ordered
    log_success "Services started"
    dc ps
}

###############################################################################
# Command: stop
###############################################################################
cmd_stop() {
    log_step "Stopping Services"

    if ! services_running; then
        log_info "Services already stopped"
        return 0
    fi

    stop_services_ordered
    dc down
    log_success "Services stopped"
}

###############################################################################
# Command: restart
###############################################################################
cmd_restart() {
    local service="${1:-}"
    ensure_env

    if [ -n "$service" ]; then
        log_step "Restarting ${service}"
        dc restart "$service"
        wait_healthy "$service" 60 || true
    else
        log_step "Restarting All Services"
        stop_services_ordered
        start_services_ordered
    fi

    log_success "Restarted"
}

###############################################################################
# Command: status
###############################################################################
cmd_status() {
    log_step "Service Status"
    echo ""

    if ! services_running; then
        log_warn "No services running"
        echo ""
        echo -e "  Start with: ${CYAN}./manage.sh start${NC}"
        echo -e "  Deploy new: ${CYAN}./manage.sh deploy${NC}"
        return 0
    fi

    dc ps
    echo ""

    # Service health summary
    local services=("postgres" "redis" "backend" "nginx")
    local service_names=("PostgreSQL" "Redis" "Backend API" "Nginx Proxy")

    echo -e "${BOLD}Service Health:${NC}"
    for i in "${!services[@]}"; do
        local svc="${services[$i]}"
        local name="${service_names[$i]}"

        if ! service_running "$svc"; then
            echo -e "  ${RED}●${NC} ${name}: ${RED}stopped${NC}"
            continue
        fi

        local health
        health=$(dc ps "$svc" --format json 2>/dev/null \
            | grep -o '"Health":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "")

        case "$health" in
            healthy)
                echo -e "  ${GREEN}●${NC} ${name}: ${GREEN}healthy${NC}"
                ;;
            unhealthy)
                echo -e "  ${RED}●${NC} ${name}: ${RED}unhealthy${NC}"
                ;;
            *)
                echo -e "  ${GREEN}●${NC} ${name}: ${GREEN}running${NC}"
                ;;
        esac
    done

    # Web access
    echo ""
    echo -e "${BOLD}Web Access:${NC}"
    if curl -sk -o /dev/null -w "%{http_code}" https://localhost:8443/ 2>/dev/null | grep -q "200"; then
        echo -e "  ${GREEN}●${NC} https://localhost:8443 (200 OK)"
    elif curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ 2>/dev/null | grep -q "200"; then
        echo -e "  ${GREEN}●${NC} http://localhost:8080 (200 OK)"
    else
        echo -e "  ${YELLOW}●${NC} Web UI not accessible"
    fi

    # Deployment info
    local deploy_mode
    deploy_mode=$(get_state 'deploy_mode')
    if [ -n "$deploy_mode" ]; then
        echo ""
        echo -e "${BOLD}Deployment:${NC}"
        echo -e "  Mode: ${deploy_mode}"
        local deploy_time
        deploy_time=$(get_state 'deploy_time')
        [ -n "$deploy_time" ] && echo -e "  Time: ${deploy_time}"
    fi

    echo ""
}

###############################################################################
# Command: health — Deep health check
###############################################################################
cmd_health() {
    log_step "Deep Health Check"
    local issues=0

    # 1. Docker daemon
    echo -e "${BOLD}1. Docker Daemon${NC}"
    if docker info &>/dev/null; then
        log_success "Docker daemon is running"
    else
        log_error "Docker daemon is not running"
        issues=$((issues + 1))
    fi

    # 2. Service containers
    echo ""
    echo -e "${BOLD}2. Service Containers${NC}"
    if ! services_running; then
        log_error "No services running"
        issues=$((issues + 1))
        echo ""
        echo -e "  ${DIM}Start with: ./manage.sh start${NC}"
        return $issues
    fi

    for svc in postgres redis backend frontend nginx; do
        if service_running "$svc"; then
            local health
            health=$(dc ps "$svc" --format json 2>/dev/null \
                | grep -o '"Health":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "")

            if [ "$health" = "healthy" ]; then
                log_success "${svc}: healthy"
            elif [ "$health" = "unhealthy" ]; then
                log_error "${svc}: unhealthy"
                issues=$((issues + 1))
            else
                log_success "${svc}: running"
            fi
        elif [ "$svc" = "frontend" ]; then
            # Frontend is a build-only container (restart: "no") — exited(0) is normal
            local exit_code
            exit_code=$(dc ps -a "$svc" --format json 2>/dev/null \
                | grep -o '"ExitCode":[0-9]*' | head -1 | cut -d: -f2 || echo "")
            if [ "$exit_code" = "0" ]; then
                log_success "${svc}: build complete (exited)"
            else
                log_error "${svc}: build failed (exit code: ${exit_code:-unknown})"
                issues=$((issues + 1))
            fi
        else
            log_error "${svc}: not running"
            issues=$((issues + 1))
        fi
    done

    # 3. Database connectivity
    echo ""
    echo -e "${BOLD}3. Database Connectivity${NC}"
    if dc exec -T postgres pg_isready -U tam_admin -d tam_db &>/dev/null; then
        log_success "PostgreSQL accepting connections"
    else
        log_error "PostgreSQL not accepting connections"
        issues=$((issues + 1))
    fi

    # 4. Redis connectivity
    echo ""
    echo -e "${BOLD}4. Redis Connectivity${NC}"
    local redis_pass
    redis_pass=$(get_env "REDIS_PASSWORD")
    if dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli ping 2>/dev/null | grep -q "PONG"; then
        log_success "Redis responding to ping"
    else
        log_error "Redis not responding"
        issues=$((issues + 1))
    fi

    # 5. Backend API
    echo ""
    echo -e "${BOLD}5. Backend API${NC}"
    if dc exec -T backend python -c "from app.core.database import engine; import asyncio; asyncio.run(engine.dispose()); print('OK')" &>/dev/null; then
        log_success "Backend can connect to database"
    else
        log_warn "Backend database connection check failed (may be transient)"
    fi

    # 6. Web UI
    echo ""
    echo -e "${BOLD}6. Web UI${NC}"
    local http_code
    http_code=$(curl -sk -o /dev/null -w "%{http_code}" https://localhost:8443/ 2>/dev/null || echo "000")
    if [ "$http_code" = "200" ]; then
        log_success "HTTPS accessible (200 OK)"
    elif [ "$http_code" = "000" ]; then
        log_error "HTTPS not reachable (connection refused)"
        issues=$((issues + 1))
    else
        log_warn "HTTPS returned status ${http_code}"
    fi

    # 7. SSL Certificate
    echo ""
    echo -e "${BOLD}7. SSL Certificate${NC}"
    if [ -f "${SCRIPT_DIR}/nginx/certs/cert.pem" ]; then
        if openssl x509 -checkend 2592000 -noout -in "${SCRIPT_DIR}/nginx/certs/cert.pem" &>/dev/null; then
            local expiry
            expiry=$(openssl x509 -enddate -noout -in "${SCRIPT_DIR}/nginx/certs/cert.pem" | cut -d= -f2)
            log_success "SSL certificate valid (expires: ${expiry})"
        else
            log_warn "SSL certificate expires soon or is expired"
            log_info "Regenerate: ./manage.sh ssl --force"
        fi
    else
        log_error "SSL certificate not found"
        issues=$((issues + 1))
    fi

    # 8. Disk space
    echo ""
    echo -e "${BOLD}8. Disk Space${NC}"
    local free_gb
    free_gb=$(df -BG "${SCRIPT_DIR}" | tail -1 | awk '{print $4}' | sed 's/G//')
    if [ "${free_gb:-0}" -lt 2 ]; then
        log_error "Low disk space: ${free_gb}GB"
        issues=$((issues + 1))
    elif [ "${free_gb:-0}" -lt 5 ]; then
        log_warn "Disk space: ${free_gb}GB (recommended: 5GB+)"
    else
        log_success "Disk space: ${free_gb}GB available"
    fi

    # Docker disk usage
    local docker_usage
    docker_usage=$(docker system df --format '{{.Size}}' 2>/dev/null | head -1 || echo "unknown")
    log_info "Docker disk usage: ${docker_usage}"

    # Summary
    echo ""
    echo -e "${BOLD}━━━ Health Check Summary ━━━${NC}"
    if [ "$issues" -eq 0 ]; then
        echo -e "  ${GREEN}${BOLD}All checks passed${NC} - system is healthy"
    else
        echo -e "  ${RED}${BOLD}${issues} issue(s) found${NC} - review above for details"
    fi
    echo ""

    return $issues
}

###############################################################################
# Command: logs
###############################################################################
cmd_logs() {
    local service=""
    local tail_n="100"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -n)
                tail_n="${2:-100}"
                shift 2
                ;;
            *)
                service="$1"
                shift
                ;;
        esac
    done

    if [ -n "$service" ]; then
        dc logs -f --tail "$tail_n" "$service"
    else
        dc logs -f --tail "$tail_n"
    fi
}

###############################################################################
# Command: logs-cleanup
###############################################################################
cmd_logs_cleanup() {
    log_step "Cleaning up Docker logs"
    local dry_run=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run) dry_run=true; shift ;;
            *) shift ;;
        esac
    done

    local total_size=0
    for svc in postgres redis backend frontend nginx; do
        local container
        container=$(dc ps -q "$svc" 2>/dev/null)
        if [[ -n "$container" ]]; then
            local log_path
            log_path=$(docker inspect --format='{{.LogPath}}' "$container" 2>/dev/null)
            if [[ -n "$log_path" && -f "$log_path" ]]; then
                local size
                size=$(stat -c%s "$log_path" 2>/dev/null || echo 0)
                total_size=$((total_size + size))
                local size_mb
                size_mb=$(echo "scale=2; $size / 1048576" | bc 2>/dev/null || echo "0")
                echo "  $svc: ${size_mb}MB"
            fi
        fi
    done

    local total_mb
    total_mb=$(echo "scale=2; $total_size / 1048576" | bc 2>/dev/null || echo "0")
    echo "  Total: ${total_mb}MB"

    if $dry_run; then
        echo "[DRY RUN] No logs were truncated"
        return 0
    fi

    echo ""
    echo "Truncating Docker container logs..."
    for svc in postgres redis backend frontend nginx; do
        local container
        container=$(dc ps -q "$svc" 2>/dev/null)
        if [[ -n "$container" ]]; then
            local log_path
            log_path=$(docker inspect --format='{{.LogPath}}' "$container" 2>/dev/null)
            if [[ -n "$log_path" && -f "$log_path" ]]; then
                truncate -s 0 "$log_path" 2>/dev/null && echo "  $svc: truncated" || echo "  $svc: failed (need root)"
            fi
        fi
    done
    log_ok "Docker logs cleaned up"
}

###############################################################################
# Command: logs-archive
###############################################################################
cmd_logs_archive() {
    ensure_env
    log_step "Archiving application logs"

    local BACKUP_DIR="${SCRIPT_DIR}/backups"
    mkdir -p "${BACKUP_DIR}"
    local TIMESTAMP
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    local ARCHIVE_DIR="${BACKUP_DIR}/logs_${TIMESTAMP}"
    mkdir -p "${ARCHIVE_DIR}"

    # Archive Docker logs for each service
    for svc in postgres redis backend frontend nginx; do
        local container
        container=$(dc ps -q "$svc" 2>/dev/null)
        if [[ -n "$container" ]]; then
            docker logs "$container" > "${ARCHIVE_DIR}/${svc}.log" 2>&1
            echo "  Archived ${svc} logs"
        fi
    done

    # Archive application log file if available
    if dc exec backend test -f /var/log/tam/app.log 2>/dev/null; then
        docker cp tam_backend:/var/log/tam/app.log "${ARCHIVE_DIR}/app.log" 2>/dev/null
        echo "  Archived app.log"
    fi

    # Compress archive
    tar -czf "${ARCHIVE_DIR}.tar.gz" -C "${BACKUP_DIR}" "logs_${TIMESTAMP}" 2>/dev/null
    rm -rf "${ARCHIVE_DIR}"

    log_ok "Logs archived to ${ARCHIVE_DIR}.tar.gz"
}

###############################################################################
# Command: audit-cleanup
###############################################################################
cmd_audit_cleanup() {
    ensure_env
    log_step "Cleaning up expired audit logs"

    local DAYS=180
    local ARCHIVE=false
    local FORCE=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --days)   DAYS="${2:-180}"; shift 2 ;;
            --archive) ARCHIVE=true; shift ;;
            --force)  FORCE=true; shift ;;
            *) shift ;;
        esac
    done

    # Count records to be cleaned
    local count
    count=$(docker exec tam_db psql -U "${DB_USER:-tam_admin}" -d tam_db -t -c \
        "SELECT COUNT(*) FROM audit_logs WHERE timestamp < NOW() - INTERVAL '${DAYS} days';" 2>/dev/null | tr -d ' ')

    if [[ -z "$count" || "$count" == "0" ]]; then
        echo "No audit logs older than ${DAYS} days found"
        return 0
    fi

    echo "Found ${count} audit log(s) older than ${DAYS} days"

    # Archive if requested
    if $ARCHIVE; then
        local BACKUP_DIR="${SCRIPT_DIR}/backups"
        mkdir -p "${BACKUP_DIR}"
        local TIMESTAMP
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        local CSV_FILE="${BACKUP_DIR}/audit_logs_${TIMESTAMP}.csv"

        echo "Exporting to ${CSV_FILE}..."
        docker exec tam_db psql -U "${DB_USER:-tam_admin}" -d tam_db -c \
            "COPY (SELECT * FROM audit_logs WHERE timestamp < NOW() - INTERVAL '${DAYS} days' ORDER BY timestamp) TO STDOUT WITH CSV HEADER" \
            > "$CSV_FILE" 2>/dev/null
        echo "  Exported ${count} record(s)"
    fi

    # Confirm deletion
    if ! $FORCE; then
        echo ""
        echo "This will permanently delete ${count} audit log(s) older than ${DAYS} days."
        read -rp "Continue? [y/N] " confirm
        [[ "$confirm" != "y" && "$confirm" != "Y" ]] && { echo "Aborted"; return 1; }
    fi

    # Delete records
    docker exec tam_db psql -U "${DB_USER:-tam_admin}" -d tam_db -c \
        "DELETE FROM audit_logs WHERE timestamp < NOW() - INTERVAL '${DAYS} days';" 2>/dev/null

    # Vacuum to reclaim space
    docker exec tam_db psql -U "${DB_USER:-tam_admin}" -d tam_db -c "VACUUM audit_logs;" 2>/dev/null

    log_ok "Cleaned up ${count} audit log(s) older than ${DAYS} days"
}

###############################################################################
# Command: update
###############################################################################
cmd_update() {
    ensure_env
    log_step "Rebuilding Application (local code only)"

    # Auto-backup before update
    auto_backup "pre_update"

    # Rebuild and restart
    log_info "Rebuilding services..."
    dc up -d --build

    # Wait for backend
    wait_healthy backend 60 || true

    log_success "Update complete (local code rebuilt)"
    log_info "Check logs: ./manage.sh logs"
    log_info "Run health: ./manage.sh health"
}

###############################################################################
# Command: upgrade — Pull remote code and upgrade with safety checks
###############################################################################
cmd_upgrade() {
    local target_version=""
    local skip_migrate=false
    local check_only=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --skip-migrate) skip_migrate=true ;;
            --check)        check_only=true ;;
            --latest)       target_version="" ;;
            *)
                if [ -z "$target_version" ]; then
                    target_version="$1"
                else
                    log_error "Unknown option: $1"
                    echo "Usage: ./manage.sh upgrade [version] [--skip-migrate] [--check]"
                    exit 1
                fi
                ;;
        esac
        shift
    done

    ensure_env

    # ─── Pre-flight checks ────────────────────────────────────────────────
    log_step "Upgrade Pre-flight Checks"

    # 1. Check git repo
    if [ ! -d "${SCRIPT_DIR}/.git" ]; then
        log_error "Not a git repository. Cannot pull remote code."
        log_error "Use './manage.sh update' to rebuild with local code."
        exit 1
    fi

    # 2. Check current service health
    if services_running; then
        local unhealthy=0
        for svc in postgres redis backend; do
            if ! service_running "$svc"; then
                log_warn "Service '$svc' is not running"
                unhealthy=$((unhealthy + 1))
            fi
        done
        if [ $unhealthy -gt 0 ]; then
            log_warn "Some services are not running — upgrade may fail"
            if ! confirm "Continue with unhealthy services?"; then
                log_info "Cancelled"
                return 0
            fi
        else
            log_success "All critical services are running"
        fi
    else
        log_warn "Services are not running — will start after upgrade"
    fi

    # 3. Check disk space
    local free_gb
    free_gb=$(df -BG "${SCRIPT_DIR}" | tail -1 | awk '{print $4}' | sed 's/G//')
    if [ "${free_gb:-0}" -lt 2 ]; then
        log_error "Insufficient disk space: ${free_gb}GB (minimum: 2GB for upgrade)"
        exit 1
    fi
    log_success "Disk space: ${free_gb}GB available"

    # 4. Show current version
    local current_branch current_commit
    current_branch=$(git -C "${SCRIPT_DIR}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    current_commit=$(git -C "${SCRIPT_DIR}" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    echo ""
    echo -e "  ${BOLD}Current version:${NC}  branch=${current_branch}  commit=${current_commit}"

    # 5. Fetch remote and check for updates
    log_info "Fetching remote updates..."
    git -C "${SCRIPT_DIR}" fetch --all 2>/dev/null || true

    local target_ref
    if [ -n "$target_version" ]; then
        target_ref="$target_version"
    else
        target_ref="origin/${current_branch}"
    fi

    # Check if target ref exists
    if ! git -C "${SCRIPT_DIR}" rev-parse --verify "$target_ref" &>/dev/null; then
        log_error "Target version '${target_version}' not found in repository"
        log_info "Available tags:"
        git -C "${SCRIPT_DIR}" tag -l 2>/dev/null | tail -10 || echo "  (none)"
        exit 1
    fi

    local target_commit
    target_commit=$(git -C "${SCRIPT_DIR}" rev-parse --short "$target_ref" 2>/dev/null || echo "unknown")

    # Check if there are changes
    local local_commit
    local_commit=$(git -C "${SCRIPT_DIR}" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    if [ "$local_commit" = "$target_commit" ] && [ -z "$target_version" ]; then
        log_info "Already up to date (commit ${local_commit})"
        if ! ${check_only}; then
            if ! confirm "No remote changes found. Force rebuild anyway?"; then
                log_info "Cancelled"
                return 0
            fi
        else
            return 0
        fi
    fi

    # Count commits ahead/behind
    local ahead behind
    ahead=$(git -C "${SCRIPT_DIR}" rev-list --count HEAD.."${target_ref}" 2>/dev/null || echo "0")
    behind=$(git -C "${SCRIPT_DIR}" rev-list --count "${target_ref}"..HEAD 2>/dev/null || echo "0")

    echo -e "  ${BOLD}Target version:${NC}   ${target_ref} (commit ${target_commit})"
    echo -e "  ${BOLD}Commits behind:${NC}   ${ahead}"
    echo -e "  ${BOLD}Commits ahead:${NC}    ${behind}"
    echo ""

    # --check mode: only show available updates
    if ${check_only}; then
        log_info "Check mode — no changes made"
        if [ "$ahead" -gt 0 ]; then
            echo ""
            echo -e "  ${GREEN}Updates available:${NC} ${ahead} commit(s) behind remote"
            echo -e "  Run: ./manage.sh upgrade${target_version:+ $target_version}"
        else
            echo -e "  Already up to date"
        fi
        return 0
    fi

    # ─── Safety warning ───────────────────────────────────────────────────
    echo -e "${RED}${BOLD}╔═══════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}${BOLD}║              UPGRADE WARNING                         ║${NC}"
    echo -e "${RED}${BOLD}╚═══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}This operation will:${NC}"
    echo -e "    1. Pull remote code from '${target_ref}'"
    echo -e "    2. Rebuild and restart all Docker services"
    if ! ${skip_migrate}; then
        echo -e "    3. Run database migrations (may be ${RED}irreversible${NC})"
    fi
    echo ""
    echo -e "  ${BOLD}Potential impact:${NC}"
    echo -e "    • Services will be ${RED}unavailable${NC} during rebuild"
    echo -e "    • Database schema changes may be ${RED}irreversible${NC}"
    echo -e "    • Downgrade may not be possible after migration"
    echo -e "    • Custom .env changes are preserved, but code-level"
    echo -e "      config changes may override defaults"
    echo ""
    echo -e "  ${BOLD}Recommended before upgrade:${NC}"
    echo -e "    ${GREEN}✓${NC} Backup database:    ./manage.sh backup"
    echo -e "    ${GREEN}✓${NC} Backup .env file:   cp .env .env.backup"
    echo -e "    ${GREEN}✓${NC} Check health:       ./manage.sh health"
    echo -e "    ${DIM}○ Notify users of planned downtime${NC}"
    echo -e "    ${DIM}○ Test in staging environment first${NC}"
    echo ""

    if ! confirm "Proceed with upgrade?"; then
        log_info "Upgrade cancelled"
        return 0
    fi

    # ─── Execute upgrade ──────────────────────────────────────────────────
    log_step "Upgrading Application"

    # Auto-backup (mandatory)
    auto_backup "pre_upgrade"
    log_success "Auto-backup completed"

    # Pull code
    log_info "Pulling code from ${target_ref}..."
    if [ -n "$target_version" ]; then
        git -C "${SCRIPT_DIR}" checkout "$target_version" 2>&1 || {
            log_error "Failed to checkout ${target_version}"
            log_info "Rollback: git checkout ${current_branch}"
            exit 1
        }
    else
        git -C "${SCRIPT_DIR}" pull 2>&1 || {
            log_error "Failed to pull code"
            log_info "Check network or resolve conflicts manually"
            exit 1
        }
    fi
    log_success "Code updated"

    # Rebuild and restart
    log_info "Rebuilding services..."
    dc up -d --build

    # Wait for backend
    wait_healthy backend 90 || true

    # Run migrations (unless skipped)
    if ! ${skip_migrate}; then
        log_info "Running database migrations..."
        if dc exec -T backend python -m alembic upgrade head 2>&1; then
            log_success "Database migrations completed"
        else
            log_error "Database migration FAILED!"
            echo ""
            echo -e "  ${RED}${BOLD}CRITICAL: Migration failed!${NC}"
            echo -e "  The application may not function correctly."
            echo -e "  ${BOLD}Recovery options:${NC}"
            echo -e "    1. Check migration error: ./manage.sh logs backend"
            echo -e "    2. Restore database:      ./manage.sh restore <backup>"
            echo -e "    3. Rollback code:         git checkout ${current_branch}"
            echo ""
            exit 1
        fi
    else
        log_warn "Database migration SKIPPED (--skip-migrate)"
        log_warn "Application may not function if schema changes are required"
    fi

    # Verify
    log_step "Verifying Upgrade"
    local new_commit
    new_commit=$(git -C "${SCRIPT_DIR}" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    echo -e "  ${BOLD}Previous commit:${NC}  ${local_commit}"
    echo -e "  ${BOLD}Current commit:${NC}   ${new_commit}"
    echo ""

    if services_running; then
        local http_ok=false
        if curl -sk -o /dev/null -w "%{http_code}" https://localhost:8443/ 2>/dev/null | grep -q "200"; then
            http_ok=true
        fi
        if ${http_ok}; then
            log_success "Web interface accessible"
        else
            log_warn "Web interface not yet accessible (may need a moment)"
        fi
    fi

    log_success "Upgrade complete"
    log_info "Check health: ./manage.sh health"
    log_info "Check logs:   ./manage.sh logs"
}

###############################################################################
# Command: init
###############################################################################
cmd_init() {
    ensure_env
    log_step "Initializing Database"

    require_services

    if is_initialized; then
        log_info "Database already initialized (idempotent skip)"
        log_info "To reinitialize, run: ./manage.sh clean && ./manage.sh deploy"
        return 0
    fi

    wait_healthy backend 60 || true
    dc exec -T backend python cli.py setup
    save_state 'db_initialized' 'true'
    log_success "Database initialized"
}

###############################################################################
# Command: migrate — Run database migrations
###############################################################################
cmd_migrate() {
    local revision="${1:-head}"

    ensure_env
    log_step "Running Database Migrations (target: ${revision})"

    require_services
    wait_healthy backend 60 || true

    # Warning for non-idempotent migrations
    if [ "$revision" = "head" ]; then
        echo -e "${YELLOW}${BOLD}⚠ Database Migration Notice:${NC}"
        echo -e "  • Schema changes may be ${RED}irreversible${NC} (no automatic downgrade)"
        echo -e "  • Recommended: run './manage.sh backup' before migration"
        echo -e "  • To check current state: './manage.sh shell db'"
        echo ""
        if ! confirm "Run database migration to '${revision}'?"; then
            log_info "Cancelled"
            return 0
        fi
    fi

    # Check current migration state
    log_info "Current migration state:"
    dc exec -T backend python -m alembic current 2>&1 || true
    echo ""

    # Run migration
    log_info "Running alembic upgrade ${revision}..."
    if dc exec -T backend python -m alembic upgrade "$revision" 2>&1; then
        log_success "Migration completed"
    else
        log_error "Migration failed. Check error above."
        log_info "To inspect: ./manage.sh shell db"
        exit 1
    fi

    # Show new state
    echo ""
    log_info "New migration state:"
    dc exec -T backend python -m alembic current 2>&1 || true
}

###############################################################################
# Command: test
###############################################################################
cmd_test() {
    ensure_env
    log_step "Running Backend Tests"

    if ! services_running; then
        log_info "Starting services for testing..."
        dc up -d
        wait_healthy postgres 120 || true
        wait_healthy redis 60 || true
        wait_healthy backend 60 || true
    fi

    log_info "Running pytest..."
    if dc exec -T backend python -m pytest tests/ -v --tb=short 2>&1; then
        log_success "All tests passed"
    else
        log_error "Tests failed"
        exit 1
    fi
}

###############################################################################
# Command: mock
###############################################################################
cmd_mock() {
    local subcmd="${1:-}"

    case "$subcmd" in
        generate)
            ensure_env
            log_step "Generating Demo Data"
            require_services
            wait_healthy backend 60 || true
            dc exec -T backend python cli.py mock generate
            log_success "Demo data generated"
            ;;
        clear)
            ensure_env
            log_step "Clearing Demo Data"
            require_services

            echo -e "${RED}${BOLD}╔═══════════════════════════════════════════════════════╗${NC}"
            echo -e "${RED}${BOLD}║              MOCK DATA CLEAR WARNING                 ║${NC}"
            echo -e "${RED}${BOLD}╚═══════════════════════════════════════════════════════╝${NC}"
            echo ""
            echo -e "  ${BOLD}Impact:${NC}"
            echo -e "    • ${RED}ALL data${NC} will be deleted except the admin user"
            echo -e "    • Terminals, whitelist, blacklist, audit logs will be cleared"
            echo -e "    • Data sources and compliance baselines will be removed"
            echo -e "    • This action is ${RED}irreversible${NC}"
            echo ""

            if ! confirm "This will delete ALL data except the admin user. Continue?"; then
                log_info "Cancelled"
                return 0
            fi

            auto_backup "pre_mock_clear"
            echo "DELETE" | dc exec -T backend python cli.py mock clear
            log_success "Demo data cleared"
            ;;
        *)
            log_error "Usage: ./manage.sh mock [generate|clear]"
            ;;
    esac
}

###############################################################################
# Command: backup
###############################################################################
cmd_backup() {
    local backup_file="${1:-}"

    ensure_env
    require_services

    mkdir -p "${BACKUP_DIR}"

    # Generate filename if not provided
    if [ -z "$backup_file" ]; then
        backup_file="${BACKUP_DIR}/backup_$(date +%Y%m%d_%H%M%S).sql"
    fi

    # Idempotent: if file already exists, append timestamp suffix
    if [ -f "$backup_file" ]; then
        local suffix
        suffix="_$(date +%H%M%S)"
        backup_file="${backup_file%.sql}${suffix}.sql"
        log_warn "Backup file exists, using: ${backup_file}"
    fi

    log_step "Backing Up Database"
    dc exec -T postgres pg_dump -U tam_admin tam_db > "$backup_file"

    if [ -f "$backup_file" ] && [ -s "$backup_file" ]; then
        local size
        size=$(du -h "$backup_file" | cut -f1)
        log_success "Backup saved: ${backup_file} (${size})"
    else
        log_error "Backup failed (empty or missing file)"
        rm -f "$backup_file"
        exit 1
    fi

    # Backup Redis
    local TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    echo "  Backing up Redis..."
    docker exec tam_redis env REDISCLI_AUTH="${REDIS_PASSWORD}" redis-cli BGSAVE
    sleep 2
    docker cp tam_redis:/data/dump.rdb "${BACKUP_DIR}/redis_${TIMESTAMP}.rdb" 2>/dev/null || echo "  [WARN] Redis backup failed (data may be empty)"

    # Clean old backups (keep last 10)
    local count
    count=$(find "${BACKUP_DIR}" -name "backup_*.sql" | wc -l)
    if [ "$count" -gt 10 ]; then
        find "${BACKUP_DIR}" -name "backup_*.sql" -printf '%T+ %p\n' \
            | sort | head -n -$((count - 10)) | awk '{print $2}' | xargs rm -f
        log_info "Cleaned old backups (kept last 10)"
    fi
}

###############################################################################
# Command: restore
###############################################################################
cmd_restore() {
    local backup_file="${1:-}"

    if [ -z "$backup_file" ]; then
        log_error "Usage: ./manage.sh restore <backup_file.sql>"
        echo ""
        echo "Available backups:"
        if ls "${BACKUP_DIR}"/backup_*.sql &>/dev/null; then
            ls -lht "${BACKUP_DIR}"/backup_*.sql
        else
            echo "  (none)"
        fi
        exit 1
    fi

    if [ ! -f "$backup_file" ]; then
        log_error "File not found: ${backup_file}"
        exit 1
    fi

    ensure_env
    require_services

    echo -e "${RED}${BOLD}╔═══════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}${BOLD}║              DATABASE RESTORE WARNING                 ║${NC}"
    echo -e "${RED}${BOLD}╚═══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Impact:${NC}"
    echo -e "    • ${RED}ALL current data will be replaced${NC} with backup data"
    echo -e "    • Active user sessions will be terminated"
    echo -e "    • Redis data (token blacklist, login locks, captcha) will be restored from backup"
    echo -e "    • Data created after the backup will be ${RED}permanently lost${NC}"
    echo -e "    • Services will restart during restore"
    echo ""
    echo -e "  ${BOLD}Recovery:${NC} Auto-backup will be created before restore"
    echo ""

    if ! confirm "This will OVERWRITE the current database! Continue?"; then
        log_info "Cancelled"
        return 0
    fi

    # Auto-backup before restore
    auto_backup "pre_restore"

    log_step "Restoring Database"

    # Drop and recreate the database to ensure clean restore
    log_info "Recreating database for clean restore..."
    # Terminate all connections to the target database first
    dc exec -T postgres psql -U tam_admin -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'tam_db' AND pid <> pg_backend_pid();" 2>/dev/null || true
    dc exec -T postgres psql -U tam_admin -d postgres -c "DROP DATABASE IF EXISTS tam_db;" 2>/dev/null || true
    dc exec -T postgres psql -U tam_admin -d postgres -c "CREATE DATABASE tam_db;" 2>/dev/null || true

    cat "$backup_file" | dc exec -T postgres psql -U tam_admin -d tam_db
    dc restart backend
    # Restore Redis data
    local BACKUP_DIR_PATH
    BACKUP_DIR_PATH=$(dirname "$backup_file")
    local REDIS_RDB
    REDIS_RDB=$(ls -t "${BACKUP_DIR_PATH}"/redis_*.rdb 2>/dev/null | head -1)
    if [[ -n "${REDIS_RDB}" ]]; then
        log_info "Restoring Redis data from: ${REDIS_RDB}"
        dc stop redis 2>/dev/null || true
        sleep 1
        docker cp "${REDIS_RDB}" tam_redis:/data/dump.rdb 2>/dev/null || {
            log_warn "Failed to copy Redis RDB file, skipping Redis restore"
            dc start redis 2>/dev/null || true
        }
        dc start redis 2>/dev/null || true
        wait_healthy redis 30 || true
        log_info "Redis data restored"
    else
        log_info "No Redis backup found, skipping Redis restore"
    fi
    log_success "Database restored from: ${backup_file}"
}

###############################################################################
# Command: backup-schedule - Configure automatic backup schedule
# =============================================================================
cmd_backup_schedule() {
    local action="${1:-}"
    local schedule="${2:-daily}"

    local cron_marker="# TAM_AUTO_BACKUP"
    local script_path="$(cd "$(dirname "$0")" && pwd)/manage.sh"

    case "$action" in
        enable)
            local cron_expr=""
            case "$schedule" in
                hourly)  cron_expr="0 * * * *" ;;
                daily)   cron_expr="0 2 * * *" ;;
                weekly)  cron_expr="0 2 * * 0" ;;
                *)       echo "Invalid schedule: $schedule (use: hourly/daily/weekly)"; exit 1 ;;
            esac

            # Remove existing TAM backup cron
            (crontab -l 2>/dev/null | grep -v "$cron_marker" || true) | { cat; echo "$cron_expr $script_path backup $cron_marker"; } | crontab -
            echo "✓ Auto backup enabled: $schedule ($cron_expr)"
            echo "  Command: $script_path backup"
            crontab -l | grep "$cron_marker" || true
            ;;
        disable)
            crontab -l 2>/dev/null | grep -v "$cron_marker" || true | crontab -
            echo "✓ Auto backup disabled"
            ;;
        status)
            local existing=$(crontab -l 2>/dev/null | grep "$cron_marker" || true)
            if [ -n "$existing" ]; then
                echo "Auto backup: ENABLED"
                echo "  $existing"
            else
                echo "Auto backup: DISABLED"
            fi
            ;;
        *)
            echo "Usage: $0 backup-schedule <enable|disable|status> [hourly|daily|weekly]"
            echo ""
            echo "Examples:"
            echo "  $0 backup-schedule enable daily    # Daily at 2:00 AM"
            echo "  $0 backup-schedule enable hourly   # Every hour"
            echo "  $0 backup-schedule enable weekly   # Every Sunday at 2:00 AM"
            echo "  $0 backup-schedule disable         # Disable auto backup"
            echo "  $0 backup-schedule status          # Check current schedule"
            ;;
    esac
}

###############################################################################
# Command: shell
###############################################################################
cmd_shell() {
    local target="${1:-backend}"

    ensure_env
    require_services

    case "$target" in
        backend|b)
            log_info "Opening backend shell..."
            dc exec backend sh
            ;;
        db|database|postgres|p)
            log_info "Opening database shell..."
            dc exec postgres psql -U tam_admin -d tam_db
            ;;
        redis|r)
            log_info "Opening Redis CLI..."
            local redis_pass
            redis_pass=$(get_env "REDIS_PASSWORD")
            dc exec redis env REDISCLI_AUTH="${redis_pass}" redis-cli
            ;;
        *)
            log_error "Unknown shell target: $target"
            echo "Options: backend (b), db (p), redis (r)"
            ;;
    esac
}

###############################################################################
# Command: ssl
###############################################################################
cmd_ssl() {
    local force=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force) force=true ;;
        esac
        shift
    done

    local cert_dir="${SCRIPT_DIR}/nginx/certs"

    # Idempotent: skip if valid certificates already exist (unless --force)
    if ! ${force} && [ -f "${cert_dir}/cert.pem" ] && [ -f "${cert_dir}/key.pem" ]; then
        if openssl x509 -checkend 86400 -noout -in "${cert_dir}/cert.pem" &>/dev/null; then
            log_verbose "SSL certificates exist and are valid"
            return 0
        else
            log_warn "SSL certificate is expired or about to expire, regenerating..."
        fi
    fi

    log_step "Generating Self-Signed SSL Certificates"
    mkdir -p "${cert_dir}"

    # Remove old certificates if --force
    if ${force}; then
        rm -f "${cert_dir}/cert.pem" "${cert_dir}/key.pem"
    fi

    openssl req -x509 -nodes -days 3650 \
        -newkey rsa:2048 \
        -keyout "${cert_dir}/key.pem" \
        -out "${cert_dir}/cert.pem" \
        -subj "/C=CN/ST=Beijing/L=Beijing/O=TerminalAccessManager/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
        2>/dev/null

    chmod 644 "${cert_dir}/cert.pem"
    chmod 600 "${cert_dir}/key.pem"

    log_success "SSL certificates generated (valid for 10 years)"
    log_info "  Cert: ${cert_dir}/cert.pem"
    log_info "  Key:  ${cert_dir}/key.pem"

    # If nginx is running, reload to pick up new certs
    if service_running nginx; then
        log_info "Reloading nginx to apply new certificates..."
        dc exec nginx nginx -s reload 2>/dev/null || true
    fi
}

###############################################################################
# Command: config
###############################################################################

# API base URL (use internal network when inside container context)
_API_BASE_URL="https://localhost:8443/api/v1"

# Get admin token by logging in
_config_get_admin_token() {
    local admin_password
    admin_password=$(get_env "ADMIN_PASSWORD")
    if [ -z "$admin_password" ]; then
        admin_password="Admin123"
    fi

    local response
    response=$(curl -sk -X POST "${_API_BASE_URL}/auth/login" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=admin&password=${admin_password}" 2>/dev/null)

    if [ -z "$response" ]; then
        log_error "Failed to connect to backend API"
        log_error "Make sure services are running: ./manage.sh start"
        return 1
    fi

    local token
    token=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")

    if [ -z "$token" ]; then
        log_error "Failed to obtain admin token (check ADMIN_PASSWORD in .env)"
        return 1
    fi

    echo "$token"
}

# Prompt user to restart services after config change
_config_prompt_restart() {
    echo ""
    if confirm "Configuration updated. Restart services to apply changes?" "default_yes"; then
        cmd_restart
    else
        log_info "Restart manually: ./manage.sh restart"
    fi
}

# Subcommand: config list — List all database system settings (grouped by category)
_config_list() {
    log_step "Database System Configuration"

    local token
    token=$(_config_get_admin_token) || return 1

    local response
    response=$(curl -sk -X GET "${_API_BASE_URL}/settings/" \
        -H "Authorization: Bearer ${token}" 2>/dev/null)

    if [ -z "$response" ]; then
        log_error "Failed to fetch settings from API"
        return 1
    fi

    # Parse and display settings grouped by category
    echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    # API returns {category: {key: value, ...}, ...}
    if isinstance(data, dict):
        # Check if it's grouped by category (values are dicts)
        first_val = next(iter(data.values()), None)
        if isinstance(first_val, dict):
            # Grouped format: {category: {key: value}}
            for cat, items in sorted(data.items()):
                print()
                cat_title = cat.replace('_', ' ').title()
                print(f'\033[1m{cat_title}:\033[0m')
                for key, value in sorted(items.items()):
                    if any(s in key.upper() for s in ['PASSWORD', 'SECRET', 'TOKEN', 'KEY']):
                        display_val = '********' if value else '(not set)'
                    else:
                        display_val = str(value) if value else '(not set)'
                    print(f'  {key:35s} = {display_val}')
        elif isinstance(data, list):
            # List format: [{key, value, category}, ...]
            categories = {}
            for item in data:
                cat = item.get('category', 'General') or 'General'
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(item)
            for cat, items in sorted(categories.items()):
                print()
                cat_title = cat.replace('_', ' ').title()
                print(f'\033[1m{cat_title}:\033[0m')
                for item in items:
                    key = item.get('key', 'N/A')
                    value = item.get('value', '')
                    desc = item.get('description', '')
                    if any(s in key.upper() for s in ['PASSWORD', 'SECRET', 'TOKEN', 'KEY']):
                        display_val = '********' if value else '(not set)'
                    else:
                        display_val = value if value else '(not set)'
                    line = f'  {key:35s} = {display_val}'
                    if desc:
                        line += f'  \033[2m({desc})\033[0m'
                    print(line)
        else:
            print('  (no settings found)')
    else:
        print('  (no settings found)')
except json.JSONDecodeError:
    print('  (failed to parse API response)')
except Exception as e:
    print(f'  (error: {e})')
" 2>/dev/null

    if [ $? -ne 0 ]; then
        log_error "Failed to parse settings response"
        return 1
    fi

    echo ""
}

# Subcommand: config get <key> — Get a specific setting value
_config_get() {
    local key="${1:-}"

    if [ -z "$key" ]; then
        log_error "Usage: ./manage.sh config get <key>"
        return 1
    fi

    local token
    token=$(_config_get_admin_token) || return 1

    local response
    response=$(curl -sk -X GET "${_API_BASE_URL}/settings/" \
        -H "Authorization: Bearer ${token}" 2>/dev/null)

    if [ -z "$response" ]; then
        log_error "Failed to fetch settings from API"
        return 1
    fi

    local result
    result=$(echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    # API returns {category: {key: value, ...}, ...}
    if isinstance(data, dict):
        found = False
        for cat, items in data.items():
            if isinstance(items, dict) and '${key}' in items:
                value = items['${key}']
                if any(s in '${key}'.upper() for s in ['PASSWORD', 'SECRET', 'TOKEN', 'KEY']):
                    display_val = '********' if value else '(not set)'
                else:
                    display_val = str(value) if value else '(not set)'
                print(f'${key} = {display_val}')
                print(f'\033[2m  Category: {cat.replace(\"_\", \" \").title()}\033[0m')
                found = True
                break
        if not found:
            print('${key} = (not found)')
    else:
        print('${key} = (not found)')
except Exception:
    print('${key} = (error fetching value)')
" 2>/dev/null)

    echo -e "$result"
}

# Subcommand: config set <key> <value> — Set a specific setting value
# Security-sensitive config keys that require extra confirmation
_SECURITY_CONFIG_KEYS="lockout_threshold lockout_duration captcha_required max_login_attempts rate_limit"

_config_set() {
    local key="${1:-}"
    local value="${2:-}"

    if [ -z "$key" ]; then
        log_error "Usage: ./manage.sh config set <key> <value>"
        return 1
    fi

    if [ -z "$value" ]; then
        log_error "Usage: ./manage.sh config set <key> <value>"
        log_error "Value cannot be empty"
        return 1
    fi

    # Get current value for comparison
    local current_val
    current_val=$(_config_get "$key" 2>/dev/null | grep -oP '(?<= = ).*' || echo "(not set)")

    # Show change preview
    echo -e "  ${BOLD}Configuration Change:${NC}"
    echo -e "    Key:     ${CYAN}${key}${NC}"
    echo -e "    Current: ${DIM}${current_val}${NC}"
    echo -e "    New:     ${GREEN}${value}${NC}"
    echo ""

    # Extra warning for security-sensitive keys
    local is_security=false
    for sec_key in $_SECURITY_CONFIG_KEYS; do
        if [[ "$key" == *"$sec_key"* ]]; then
            is_security=true
            break
        fi
    done

    if ${is_security}; then
        echo -e "${YELLOW}${BOLD}⚠ Security Configuration Change:${NC}"
        echo -e "  • This affects system security policies"
        echo -e "  • Incorrect values may ${RED}lock out users${NC} or ${RED}weaken security${NC}"
        echo -e "  • Changes take effect immediately after restart"
        echo ""
        if ! confirm "Apply this security configuration change?"; then
            log_info "Cancelled"
            return 0
        fi
    fi

    local token
    token=$(_config_get_admin_token) || return 1

    local response
    response=$(curl -sk -X PUT "${_API_BASE_URL}/settings/update" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "[{\"key\":\"${key}\",\"value\":\"${value}\"}]" 2>/dev/null)

    if [ -z "$response" ]; then
        log_error "Failed to update setting via API"
        return 1
    fi

    # Check for success
    local success
    success=$(echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    # Check for error indicators
    if isinstance(data, dict):
        if data.get('detail') or data.get('error'):
            print('false')
        else:
            print('true')
    else:
        print('true')
except:
    print('true')
" 2>/dev/null)

    if [ "$success" = "false" ]; then
        local detail
        detail=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('detail',d.get('error','Unknown error')))" 2>/dev/null || echo "Unknown error")
        log_error "Failed to update setting: ${detail}"
        return 1
    fi

    # Mask sensitive values in output
    if [[ "$key" == *"PASSWORD"* ]] || [[ "$key" == *"SECRET"* ]] || [[ "$key" == *"TOKEN"* ]] || [[ "$key" == *"KEY"* ]]; then
        log_success "Set ${key} = ********"
    else
        log_success "Set ${key} = ${value}"
    fi

    _config_prompt_restart
}

# Subcommand: config branding — View/set branding configuration
_config_branding() {
    local key="${1:-}"
    local value="${2:-}"

    # Fetch current branding (public endpoint, no auth needed)
    local branding_response
    branding_response=$(curl -sk -X GET "${_API_BASE_URL}/settings/branding" 2>/dev/null)

    if [ -z "$branding_response" ]; then
        log_error "Failed to fetch branding configuration"
        log_error "Make sure services are running: ./manage.sh start"
        return 1
    fi

    if [ -z "$key" ]; then
        # Display all branding settings
        log_step "Branding Configuration"

        echo "$branding_response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if isinstance(data, dict) and 'data' in data:
        data = data['data']

    branding_keys = ['app_name', 'app_short_name', 'app_subtitle', 'login_heading',
                     'login_subheading', 'login_footer_text', 'login_bg_url', 'favicon_url',
                     'footer_copyright', 'footer_icp_number', 'footer_icp_url']
    labels = {
        'app_name': 'Application Name',
        'app_short_name': 'Application Short Name',
        'app_subtitle': 'Application Subtitle',
        'login_heading': 'Login Heading',
        'login_subheading': 'Login Subheading',
        'login_footer_text': 'Login Footer Text',
        'login_bg_url': 'Login Background URL',
        'favicon_url': 'Favicon URL',
        'footer_copyright': 'Footer Copyright',
        'footer_icp_number': 'ICP Number',
        'footer_icp_url': 'ICP URL',
    }

    for k in branding_keys:
        v = data.get(k, '(not set)') or '(not set)'
        label = labels.get(k, k)
        print(f'  {label:22s} = {v}')

    # Show any extra keys
    for k, v in data.items():
        if k not in branding_keys:
            print(f'  {k:22s} = {v or \"(not set)\"}')
except json.JSONDecodeError:
    print('  (failed to parse branding response)')
except Exception as e:
    print(f'  (error: {e})')
" 2>/dev/null

        echo ""
        log_info "Update branding: ./manage.sh config branding <key> <value>"
        log_info "Upload assets:   ./manage.sh config upload <purpose> <file>"
        echo ""
        return 0
    fi

    # Set a branding value
    if [ -z "$value" ]; then
        # Show specific branding key
        local current_val
        current_val=$(echo "$branding_response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if isinstance(data, dict) and 'data' in data:
        data = data['data']
    print(data.get('${key}', '(not found)') or '(not set)')
except:
    print('(error)')
" 2>/dev/null)
        echo "${key} = ${current_val}"
        return 0
    fi

    # Update branding via settings/update API
    local token
    token=$(_config_get_admin_token) || return 1

    local response
    response=$(curl -sk -X PUT "${_API_BASE_URL}/settings/update" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "[{\"key\":\"${key}\",\"value\":\"${value}\"}]" 2>/dev/null)

    if [ -z "$response" ]; then
        log_error "Failed to update branding via API"
        return 1
    fi

    log_success "Branding updated: ${key} = ${value}"
    _config_prompt_restart
}

# Subcommand: config upload <purpose> <file> — Upload branding resource
_config_upload() {
    local purpose="${1:-}"
    local file="${2:-}"

    if [ -z "$purpose" ] || [ -z "$file" ]; then
        log_error "Usage: ./manage.sh config upload <purpose> <file>"
        echo ""
        echo -e "  ${BOLD}Purpose options:${NC}"
        echo -e "    login_bg   - Login page background image"
        echo -e "    favicon    - Browser favicon"
        return 1
    fi

    # Validate purpose
    case "$purpose" in
        login_bg|favicon) ;;
        *)
            log_error "Invalid purpose: ${purpose}"
            log_error "Valid options: login_bg, favicon"
            return 1
            ;;
    esac

    # Validate file exists
    if [ ! -f "$file" ]; then
        log_error "File not found: ${file}"
        return 1
    fi

    local token
    token=$(_config_get_admin_token) || return 1

    log_info "Uploading ${purpose}: ${file}..."

    local response
    response=$(curl -sk -X POST "${_API_BASE_URL}/settings/upload?purpose=${purpose}" \
        -H "Authorization: Bearer ${token}" \
        -F "file=@${file}" 2>/dev/null)

    if [ -z "$response" ]; then
        log_error "Failed to upload file via API"
        return 1
    fi

    # Check for error
    local has_error
    has_error=$(echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if isinstance(data, dict) and (data.get('detail') or data.get('error')):
        print('true')
    else:
        print('false')
except:
    print('false')
" 2>/dev/null)

    if [ "$has_error" = "true" ]; then
        local detail
        detail=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('detail',d.get('error','Unknown error')))" 2>/dev/null || echo "Unknown error")
        log_error "Upload failed: ${detail}"
        return 1
    fi

    log_success "Uploaded ${purpose}: ${file}"
    _config_prompt_restart
}

cmd_config() {
    local subcmd="${1:-}"
    shift 2>/dev/null || true

    ensure_env

    case "$subcmd" in
        list)
            # List all database system settings
            _config_list
            ;;
        get)
            # Get a specific setting value
            _config_get "$@"
            ;;
        set)
            # Set a specific setting value
            _config_set "$@"
            ;;
        branding)
            # View/set branding configuration
            _config_branding "$@"
            ;;
        upload)
            # Upload branding resource
            _config_upload "$@"
            ;;
        "")
            # No subcommand: show .env configuration (original behavior)
            log_step "Current Configuration (.env)"
            echo ""

            # Group and display config
            echo -e "${BOLD}Database:${NC}"
            echo -e "  DB_USER       = $(get_env DB_USER)"
            echo -e "  DB_PASSWORD   = $(if [ -n "$(get_env DB_PASSWORD)" ]; then echo '********'; else echo '(not set)'; fi)"
            echo ""

            echo -e "${BOLD}Redis:${NC}"
            echo -e "  REDIS_PASSWORD = $(if [ -n "$(get_env REDIS_PASSWORD)" ]; then echo '********'; else echo '(not set)'; fi)"
            echo ""

            echo -e "${BOLD}Security:${NC}"
            echo -e "  SECRET_KEY     = $(if [ -n "$(get_env SECRET_KEY)" ]; then echo '********'; else echo '(not set)'; fi)"
            echo ""

            echo -e "${BOLD}Integrations:${NC}"
            echo -e "  SANGFOR_BASE_URL  = $(get_env SANGFOR_BASE_URL || echo '(not set)')"
            echo -e "  SANGFOR_USERNAME  = $(get_env SANGFOR_USERNAME || echo '(not set)')"
            echo -e "  SWITCH_HOST       = $(get_env SWITCH_HOST || echo '(not set)')"
            echo -e "  SWITCH_USERNAME   = $(get_env SWITCH_USERNAME || echo '(not set)')"
            echo ""

            echo -e "${BOLD}Deployment State:${NC}"
            echo -e "  Deployed      = $(get_state 'deployed' || echo 'false')"
            echo -e "  Mode          = $(get_state 'deploy_mode' || echo 'N/A')"
            echo -e "  DB Initialized = $(get_state 'db_initialized' || echo 'false')"
            echo -e "  Deploy Time   = $(get_state 'deploy_time' || echo 'N/A')"
            echo ""

            echo -e "${DIM}Tip: Use 'config list' to view database system settings${NC}"
            echo -e "${DIM}     Use 'config branding' to view branding settings${NC}"
            echo ""
            ;;
        --help|-h)
            # Show config help
            echo -e "${BOLD}Usage:${NC} ./manage.sh config [subcommand] [args]"
            echo ""
            echo -e "${BOLD}Subcommands:${NC}"
            echo -e "  ${CYAN}(none)${NC}                Show .env file configuration"
            echo -e "  ${CYAN}list${NC}                  List all database system settings"
            echo -e "  ${CYAN}get${NC} <key>             Get a specific setting value"
            echo -e "  ${CYAN}set${NC} <key> <value>      Set a specific setting value"
            echo -e "  ${CYAN}branding${NC} [key] [val]  View or set branding configuration"
            echo -e "  ${CYAN}upload${NC} <purpose> <file> Upload branding resource"
            echo ""
            echo -e "${BOLD}Legacy (no subcommand):${NC}"
            echo -e "  ./manage.sh config              Show .env configuration"
            echo -e "  ./manage.sh config <key>        Show .env value for key"
            echo -e "  ./manage.sh config <key> <val>  Set .env value for key"
            echo ""
            echo -e "${BOLD}Upload purposes:${NC}"
            echo -e "  login_bg    Login page background image"
            echo -e "  favicon     Browser favicon"
            echo ""
            echo -e "${BOLD}Branding keys:${NC}"
            echo -e "  app_name, login_heading, login_subheading, footer_copyright"
            echo ""
            ;;
        *)
            # Legacy behavior: treat as .env key[=value]
            local key="$subcmd"
            local value="${1:-}"

            if [ -z "$value" ]; then
                # Show specific .env key
                local current
                current=$(get_env "$key")
                if [ -n "$current" ]; then
                    if [[ "$key" == *"PASSWORD"* ]] || [[ "$key" == *"SECRET"* ]]; then
                        echo "${key} = ********"
                    else
                        echo "${key} = ${current}"
                    fi
                else
                    echo "${key} = (not set)"
                fi
            else
                # Set .env key=value
                set_env "$key" "$value"
                log_success "Set ${key} = $(if [[ "$key" == *"PASSWORD"* ]] || [[ "$key" == *"SECRET"* ]]; then echo '********'; else echo "$value"; fi)"

                # If services are running and this is a runtime config, suggest restart
                if [[ "$key" == *"PASSWORD"* ]] || [[ "$key" == *"SECRET"* ]]; then
                    log_info "Restart services to apply: ./manage.sh restart"
                fi
            fi
            ;;
    esac
}

###############################################################################
# Command: redis — Redis management
###############################################################################
cmd_redis() {
    local subcmd="${1:-info}"
    shift 2>/dev/null || true

    ensure_env
    require_services

    local redis_pass
    redis_pass=$(get_env "REDIS_PASSWORD")

    case "$subcmd" in
        info)
            log_step "Redis Server Info"
            dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli INFO server 2>/dev/null \
                | grep -E "^(redis_version|redis_mode|os|tcp_port|uptime_in_days|connected_clients|used_memory_human|maxmemory_human|keyspace_hits|keyspace_misses)" || true
            echo ""
            echo -e "${BOLD}Memory:${NC}"
            dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli INFO memory 2>/dev/null \
                | grep -E "^(used_memory_human|used_memory_peak_human|maxmemory_human|mem_fragmentation_ratio)" || true
            echo ""
            echo -e "${BOLD}Keyspace:${NC}"
            dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli INFO keyspace 2>/dev/null || true
            ;;
        keys)
            local pattern="${1:-*}"
            log_step "Redis Keys (pattern: ${pattern})"
            local keys
            keys=$(dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli KEYS "$pattern" 2>/dev/null)
            if [ -z "$keys" ]; then
                log_info "No keys matching pattern: ${pattern}"
            else
                local count
                count=$(echo "$keys" | wc -l)
                log_info "Found ${count} key(s):"
                echo "$keys" | while read -r key; do
                    local ttl
                    ttl=$(dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli TTL "$key" 2>/dev/null || echo "?")
                    local type
                    type=$(dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli TYPE "$key" 2>/dev/null || echo "?")
                    if [ "$ttl" = "-1" ]; then
                        ttl_str="no TTL"
                    elif [ "$ttl" = "-2" ]; then
                        ttl_str="expired"
                    else
                        ttl_str="TTL ${ttl}s"
                    fi
                    echo -e "  ${CYAN}${key}${NC}  ${DIM}[${type}] [${ttl_str}]${NC}"
                done
            fi
            ;;
        get)
            local key="${1:-}"
            if [ -z "$key" ]; then
                log_error "Usage: ./manage.sh redis get <key>"
                return 1
            fi
            local type
            type=$(dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli TYPE "$key" 2>/dev/null || echo "none")
            case "$type" in
                string)
                    dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli GET "$key" 2>/dev/null
                    ;;
                hash)
                    dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli HGETALL "$key" 2>/dev/null
                    ;;
                list)
                    local len
                    len=$(dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli LLEN "$key" 2>/dev/null || echo "0")
                    log_info "List length: ${len}"
                    dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli LRANGE "$key" 0 19 2>/dev/null
                    ;;
                set)
                    dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli SMEMBERS "$key" 2>/dev/null
                    ;;
                zset)
                    dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli ZRANGE "$key" 0 -1 WITHSCORES 2>/dev/null
                    ;;
                none)
                    log_warn "Key '${key}' does not exist"
                    ;;
                *)
                    log_warn "Unsupported type: ${type}"
                    dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli DUMP "$key" 2>/dev/null | head -c 200
                    ;;
            esac
            ;;
        del)
            local key="${1:-}"
            if [ -z "$key" ]; then
                log_error "Usage: ./manage.sh redis del <key>"
                return 1
            fi
            echo -e "${YELLOW}${BOLD}⚠ Redis Key Deletion:${NC}"
            echo -e "  • Deleting '${key}' may affect running services"
            echo -e "  • Scheduler control keys (scheduler:ctrl:*) affect task scheduling"
            echo -e "  • Cache keys will be rebuilt automatically"
            echo ""
            if ! confirm "Delete Redis key '${key}'?"; then
                log_info "Cancelled"
                return 0
            fi
            dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli DEL "$key" 2>/dev/null
            log_success "Deleted key: ${key}"
            ;;
        flush)
            local db_num="${1:-0}"
            echo -e "${RED}${BOLD}╔═══════════════════════════════════════════════════════╗${NC}"
            echo -e "${RED}${BOLD}║              REDIS FLUSH WARNING                     ║${NC}"
            echo -e "${RED}${BOLD}╚═══════════════════════════════════════════════════════╝${NC}"
            echo ""
            echo -e "  ${BOLD}Impact:${NC}"
            echo -e "    • ${RED}ALL keys${NC} in Redis database ${db_num} will be deleted"
            echo -e "    • Active user sessions will be terminated (re-login required)"
            echo -e "    • Login rate limit counters will be reset"
            echo -e "    • Scheduler pause states will be cleared (all tasks resume)"
            echo -e "    • Compliance/whitelist caches will be rebuilt on next access"
            echo ""
            if ! confirm "Flush Redis database ${db_num}? This deletes ALL keys!"; then
                log_info "Cancelled"
                return 0
            fi
            dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli -n "$db_num" FLUSHDB 2>/dev/null
            log_success "Flushed Redis database ${db_num}"
            ;;
        *)
            log_error "Unknown redis subcommand: ${subcmd}"
            echo ""
            echo -e "  ${BOLD}Usage:${NC} ./manage.sh redis <subcommand> [args]"
            echo ""
            echo -e "  ${CYAN}info${NC}              Show Redis server info"
            echo -e "  ${CYAN}keys${NC} [pattern]    List keys (default: *)"
            echo -e "  ${CYAN}get${NC} <key>        Get key value"
            echo -e "  ${CYAN}del${NC} <key>        Delete a key"
            echo -e "  ${CYAN}flush${NC} [db]       Flush a Redis database (default: 0)"
            ;;
    esac
}

###############################################################################
# Command: scheduler — Scheduler task management
###############################################################################

# Scheduler task name mapping
_SCHEDULER_TASKS="arp_collection,ipguard_sync,firewall_query,compliance_check,auto_unblock"

# Get scheduler control key for a task
_sched_ctrl_key() {
    local task="$1"
    echo "scheduler:ctrl:${task}"
}

# Get task display name
_sched_display_name() {
    local task="$1"
    case "$task" in
        arp_collection)    echo "ARP Data Collection" ;;
        ipguard_sync)      echo "Compliance Baseline Sync" ;;
        firewall_query)    echo "Firewall Blacklist Query" ;;
        compliance_check)  echo "Compliance Check" ;;
        auto_unblock)      echo "Auto Unblock" ;;
        *)                 echo "$task" ;;
    esac
}

cmd_scheduler() {
    local subcmd="${1:-status}"
    shift 2>/dev/null || true

    ensure_env
    require_services

    local redis_pass
    redis_pass=$(get_env "REDIS_PASSWORD")

    case "$subcmd" in
        status)
            log_step "Scheduler Task Status"
            echo ""

            # Get intervals from config API
            local token
            token=$(_config_get_admin_token) 2>/dev/null || true

            local intervals_response
            intervals_response=$(curl -sk -X GET "${_API_BASE_URL}/settings/" \
                -H "Authorization: Bearer ${token}" 2>/dev/null)

            # Display each task
            echo -e "${BOLD}Task                          Interval    Status${NC}"
            echo -e "${DIM}─────────────────────────────────────────────────${NC}"

            for task in $(echo "$_SCHEDULER_TASKS" | tr ',' ' '); do
                local display_name
                display_name=$(_sched_display_name "$task")

                # Get interval from config
                local config_key="scheduler_${task}_interval"
                local interval_val
                interval_val=$(echo "$intervals_response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if isinstance(data, dict):
        for cat, items in data.items():
            if isinstance(items, dict) and '${config_key}' in items:
                print(items['${config_key}'])
                break
        else:
            print('?')
    else:
        print('?')
except:
    print('?')
" 2>/dev/null || echo "?")

                # Format interval
                local interval_display
                if [ "$interval_val" != "?" ] && [ "$interval_val" -eq "$interval_val" ] 2>/dev/null; then
                    if [ "$interval_val" -ge 3600 ]; then
                        interval_display="$((interval_val / 3600))h"
                    elif [ "$interval_val" -ge 60 ]; then
                        interval_display="$((interval_val / 60))m"
                    else
                        interval_display="${interval_val}s"
                    fi
                else
                    interval_display="${interval_val}"
                fi

                # Check pause state from Redis
                local ctrl_key
                ctrl_key=$(_sched_ctrl_key "$task")
                local is_paused
                is_paused=$(dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli GET "$ctrl_key" 2>/dev/null || echo "")

                local status_display
                if [ "$is_paused" = "paused" ]; then
                    status_display="${YELLOW}PAUSED${NC}"
                else
                    status_display="${GREEN}RUNNING${NC}"
                fi

                printf "  %-28s %-11s " "$display_name" "$interval_display"
                echo -e "$status_display"
            done

            echo ""
            echo -e "${DIM}Pause:   ./manage.sh scheduler pause <task>${NC}"
            echo -e "${DIM}Resume:  ./manage.sh scheduler resume <task>${NC}"
            echo -e "${DIM}Trigger: ./manage.sh scheduler trigger <task>${NC}"
            echo ""
            echo -e "${DIM}Task names: arp_collection, ipguard_sync, firewall_query, compliance_check, auto_unblock${NC}"
            echo ""
            ;;
        pause)
            local task="${1:-}"
            if [ -z "$task" ]; then
                log_error "Usage: ./manage.sh scheduler pause <task>"
                echo -e "  Tasks: arp_collection, ipguard_sync, firewall_query, compliance_check, auto_unblock"
                return 1
            fi
            local ctrl_key
            ctrl_key=$(_sched_ctrl_key "$task")
            dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli SET "$ctrl_key" "paused" 2>/dev/null >/dev/null
            log_success "Paused: $(_sched_display_name "$task")"
            log_info "Resume with: ./manage.sh scheduler resume ${task}"
            ;;
        resume)
            local task="${1:-}"
            if [ -z "$task" ]; then
                log_error "Usage: ./manage.sh scheduler resume <task>"
                echo -e "  Tasks: arp_collection, ipguard_sync, firewall_query, compliance_check, auto_unblock"
                return 1
            fi
            local ctrl_key
            ctrl_key=$(_sched_ctrl_key "$task")
            dc exec -T redis env REDISCLI_AUTH="${redis_pass}" redis-cli DEL "$ctrl_key" 2>/dev/null >/dev/null
            log_success "Resumed: $(_sched_display_name "$task")"
            ;;
        trigger)
            local task="${1:-}"
            if [ -z "$task" ]; then
                log_error "Usage: ./manage.sh scheduler trigger <task>"
                echo -e "  Tasks: arp_collection, ipguard_sync, firewall_query, compliance_check, auto_unblock"
                return 1
            fi
            local display_name
            display_name=$(_sched_display_name "$task")
            log_info "Triggering: ${display_name}..."

            # Trigger via backend CLI
            local trigger_result
            trigger_result=$(dc exec -T backend python cli.py scheduler trigger "$task" 2>&1) || true

            if echo "$trigger_result" | grep -qi "error\|fail\|not found"; then
                log_error "Trigger failed for ${display_name}"
                echo "$trigger_result"
            else
                log_success "Triggered: ${display_name}"
                if [ -n "$trigger_result" ]; then
                    echo "$trigger_result"
                fi
            fi
            ;;
        intervals)
            log_step "Scheduler Intervals (from config)"
            echo ""

            local token
            token=$(_config_get_admin_token) 2>/dev/null || true

            local response
            response=$(curl -sk -X GET "${_API_BASE_URL}/settings/" \
                -H "Authorization: Bearer ${token}" 2>/dev/null)

            echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if isinstance(data, dict) and 'scheduler' in data:
        sched = data['scheduler']
        task_names = {
            'scheduler_arp_collection_interval': 'ARP Data Collection',
            'scheduler_ipguard_sync_interval': 'Compliance Baseline Sync',
            'scheduler_firewall_query_interval': 'Firewall Blacklist Query',
            'scheduler_compliance_check_interval': 'Compliance Check',
            'scheduler_auto_unblock_interval': 'Auto Unblock',
        }
        for key, label in sorted(task_names.items()):
            val = sched.get(key, '?')
            if isinstance(val, int):
                if val >= 3600:
                    display = f'{val}s ({val // 3600}h)'
                elif val >= 60:
                    display = f'{val}s ({val // 60}m)'
                else:
                    display = f'{val}s'
            else:
                display = str(val)
            print(f'  {label:28s} {display}')
        print()
        print('  Modify: ./manage.sh config set <key> <seconds>')
        print('  Range:  30 - 86400 (30s - 1 day)')
    else:
        print('  (scheduler config not found)')
except Exception as e:
    print(f'  (error: {e})')
" 2>/dev/null
            echo ""
            ;;
        *)
            log_error "Unknown scheduler subcommand: ${subcmd}"
            echo ""
            echo -e "  ${BOLD}Usage:${NC} ./manage.sh scheduler <subcommand> [args]"
            echo ""
            echo -e "  ${CYAN}status${NC}              Show task status and intervals"
            echo -e "  ${CYAN}pause${NC} <task>        Pause a scheduler task"
            echo -e "  ${CYAN}resume${NC} <task>       Resume a paused task"
            echo -e "  ${CYAN}trigger${NC} <task>      Manually trigger a task"
            echo -e "  ${CYAN}intervals${NC}           Show configured intervals"
            echo ""
            echo -e "  ${BOLD}Tasks:${NC} arp_collection, ipguard_sync, firewall_query, compliance_check, auto_unblock"
            ;;
    esac
}

###############################################################################
# Command: validate
###############################################################################
cmd_validate() {
    log_step "Running Validation"

    if services_running; then
        dc exec -T backend python cli.py validate
    else
        log_warn "Services not running, running local validation only"
        local errors=0

        # Check required files
        for f in docker-compose.yml .env.example backend/Dockerfile frontend/Dockerfile; do
            if [ -f "${SCRIPT_DIR}/$f" ]; then
                log_success "Found: $f"
            else
                log_error "Missing: $f"
                errors=$((errors + 1))
            fi
        done

        # Check .env
        if [ -f "${ENV_FILE}" ]; then
            log_success ".env file exists"

            # Validate required env vars
            for var in DB_PASSWORD REDIS_PASSWORD SECRET_KEY; do
                if [ -n "$(get_env "$var")" ]; then
                    log_success "${var} is set"
                else
                    log_error "${var} is not set"
                    errors=$((errors + 1))
                fi
            done
        else
            log_warn ".env file not found (run: ./manage.sh deploy)"
        fi

        # Check SSL
        if [ -f "${SCRIPT_DIR}/nginx/certs/cert.pem" ]; then
            log_success "SSL certificate exists"
        else
            log_warn "SSL certificate not found (run: ./manage.sh ssl)"
        fi

        # Check docker-compose.yml syntax
        if docker compose -f "${SCRIPT_DIR}/docker-compose.yml" config --quiet 2>/dev/null; then
            log_success "docker-compose.yml syntax valid"
        else
            log_error "docker-compose.yml has syntax errors"
            errors=$((errors + 1))
        fi

        if [ "$errors" -gt 0 ]; then
            log_error "Validation failed with ${errors} error(s)"
            exit 1
        fi

        log_success "Local validation passed"
    fi
}

###############################################################################
# Command: clean
###############################################################################
cmd_clean() {
    echo -e "${RED}${BOLD}╔═══════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}${BOLD}║              WARNING: DESTRUCTIVE ACTION              ║${NC}"
    echo -e "${RED}${BOLD}╚═══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "  This will:"
    echo "    - Stop all containers"
    echo "    - Remove all containers and images"
    echo "    - Remove all volumes (DELETE ALL DATA)"
    echo "    - Remove all networks"
    echo "    - Reset deployment state"
    echo ""
    echo -e "  ${RED}This action CANNOT be undone!${NC}"
    echo ""

    if ! confirm "Type 'yes' to confirm destructive cleanup"; then
        log_info "Cancelled"
        return 0
    fi

    log_step "Cleaning Up"

    # Check if there's anything to clean
    if ! services_running && ! dc ps -a --format '{{.Names}}' 2>/dev/null | grep -q .; then
        log_info "Nothing to clean (no containers found)"
        # Still reset state
        rm -rf "${STATE_DIR}"
        log_success "State reset"
        return 0
    fi

    dc down -v --remove-orphans --rmi local 2>/dev/null || dc down -v --remove-orphans

    # Reset deployment state
    rm -rf "${STATE_DIR}"

    log_success "Cleanup complete"
    log_info "To redeploy: ./manage.sh deploy"
}

###############################################################################
# Command: help
###############################################################################
cmd_help() {
    log_banner

    echo -e "${BOLD}Usage:${NC} ./manage.sh [OPTIONS] <command> [ARGS]"
    echo ""
    echo -e "${BOLD}Options:${NC}"
    echo -e "  -y, --yes       Skip confirmation prompts (non-interactive)"
    echo -e "  -v, --verbose   Enable verbose/debug output"
    echo -e "  -h, --help      Show this help message"
    echo ""
    echo -e "${BOLD}Lifecycle:${NC}"
    echo ""
    echo -e "  ${GREEN}deploy${NC} [--demo|--prod]   Full deployment with init wizard"
    echo -e "  ${GREEN}start${NC}                    Start all services (idempotent)"
    echo -e "  ${GREEN}stop${NC}                     Stop all services (idempotent)"
    echo -e "  ${GREEN}restart${NC} [service]        Restart all or specific service"
    echo -e "  ${GREEN}status${NC}                    Show service status and health"
    echo -e "  ${GREEN}health${NC}                    Deep health check of all components"
    echo -e "  ${GREEN}update${NC}                    Rebuild and restart (local code only)"
    echo -e "  ${GREEN}upgrade${NC} [version]         Pull remote code and upgrade (with safety checks)"
    echo ""
    echo -e "${BOLD}Data Management:${NC}"
    echo ""
    echo -e "  ${YELLOW}init${NC}                      Initialize database + admin user"
    echo -e "  ${YELLOW}migrate${NC} [revision]        Run database migrations (idempotent)"
    echo -e "  ${YELLOW}mock generate${NC}            Generate demo/mock data"
    echo -e "  ${YELLOW}mock clear${NC}               Clear all mock data (keeps admin)"
    echo -e "  ${YELLOW}backup${NC} [file]             Backup database to SQL file"
    echo -e "  ${YELLOW}backup-schedule${NC}           Configure automatic backup schedule (enable/disable/status)"
    echo -e "  ${YELLOW}restore${NC} <file>            Restore database from SQL file"
    echo ""
    echo -e "${BOLD}Development:${NC}"
    echo ""
    echo -e "  ${BLUE}test${NC}                      Run backend test suite"
    echo -e "  ${BLUE}shell${NC} [backend|db|redis]   Access service shell"
    echo -e "  ${BLUE}logs${NC} [service] [-n N]      View logs (follow mode)"
    echo -e "  ${BLUE}validate${NC}                  Run project validation checks"
    echo ""
    echo -e "${BOLD}Utilities:${NC}"
    echo ""
    echo -e "  ${CYAN}config${NC}                     Show .env file configuration"
    echo -e "  ${CYAN}config list${NC}               List all database system settings"
    echo -e "  ${CYAN}config get${NC} <key>          Get a specific setting value"
    echo -e "  ${CYAN}config set${NC} <key> <value>   Set a specific setting value"
    echo -e "  ${CYAN}config branding${NC} [key] [val] View/set branding configuration"
    echo -e "  ${CYAN}config upload${NC} <purpose> <file> Upload branding resource"
    echo -e "  ${CYAN}redis info${NC}               Show Redis server info"
    echo -e "  ${CYAN}redis keys${NC} [pattern]     List Redis keys"
    echo -e "  ${CYAN}redis get${NC} <key>         Get Redis key value"
    echo -e "  ${CYAN}redis del${NC} <key>         Delete a Redis key"
    echo -e "  ${CYAN}redis flush${NC} [db]        Flush Redis database"
    echo -e "  ${CYAN}scheduler status${NC}         Show scheduler task status"
    echo -e "  ${CYAN}scheduler pause${NC} <task>   Pause a scheduler task"
    echo -e "  ${CYAN}scheduler resume${NC} <task>  Resume a paused task"
    echo -e "  ${CYAN}scheduler trigger${NC} <task> Manually trigger a task"
    echo -e "  ${CYAN}scheduler intervals${NC}      Show configured intervals"
    echo -e "  ${CYAN}ssl${NC} [--force]              Generate SSL certificates (idempotent)"
    echo -e "  ${CYAN}clean${NC}                     Remove ALL containers, volumes, data"
    echo -e "  ${CYAN}version${NC}                   Show version information"
    echo ""
    echo -e "${BOLD}Quick Start:${NC}"
    echo ""
    echo -e "  ${DIM}# Demo deployment (one command)${NC}"
    echo -e "  ${DIM}./manage.sh deploy --demo${NC}"
    echo ""
    echo -e "  ${DIM}# Production deployment (guided wizard)${NC}"
    echo -e "  ${DIM}./manage.sh deploy --prod${NC}"
    echo ""
    echo -e "  ${DIM}# Non-interactive production (use existing .env)${NC}"
    echo -e "  ${DIM}./manage.sh -y deploy --prod${NC}"
    echo ""
    echo -e "${BOLD}Examples:${NC}"
    echo ""
    echo -e "  ${DIM}./manage.sh status               # Check service status${NC}"
    echo -e "  ${DIM}./manage.sh health               # Deep health check${NC}"
    echo -e "  ${DIM}./manage.sh update               # Rebuild with local code${NC}"
    echo -e "  ${DIM}./manage.sh upgrade              # Pull remote code and upgrade${NC}"
    echo -e "  ${DIM}./manage.sh upgrade --check      # Check for available updates${NC}"
    echo -e "  ${DIM}./manage.sh upgrade v2.1.0       # Upgrade to specific version${NC}"
    echo -e "  ${DIM}./manage.sh logs backend -n 50   # Last 50 lines of backend logs${NC}"
    echo -e "  ${DIM}./manage.sh shell db             # Open database shell${NC}"
    echo -e "  ${DIM}./manage.sh backup               # Backup database${NC}"
    echo -e "  ${DIM}./manage.sh config               # View .env configuration${NC}"
    echo -e "  ${DIM}./manage.sh config list           # List database settings${NC}"
    echo -e "  ${DIM}./manage.sh config get app_name   # Get a setting value${NC}"
    echo -e "  ${DIM}./manage.sh config set app_name MyApp  # Set a setting${NC}"
    echo -e "  ${DIM}./manage.sh config branding       # View branding config${NC}"
    echo -e "  ${DIM}./manage.sh config upload login_bg bg.png  # Upload asset${NC}"
    echo -e "  ${DIM}./manage.sh migrate               # Run database migrations${NC}"
    echo -e "  ${DIM}./manage.sh redis info             # Show Redis info${NC}"
    echo -e "  ${DIM}./manage.sh redis keys 'ipguard:*' # List IPGuard cache keys${NC}"
    echo -e "  ${DIM}./manage.sh scheduler status        # Show scheduler status${NC}"
    echo -e "  ${DIM}./manage.sh scheduler pause arp_collection  # Pause task${NC}"
    echo -e "  ${DIM}./manage.sh scheduler trigger compliance_check  # Trigger task${NC}"
    echo -e "  ${DIM}./manage.sh ssl --force          # Force regenerate SSL certs${NC}"
    echo -e "  ${DIM}./manage.sh -y clean             # Clean without confirmation${NC}"
    echo ""
}

###############################################################################
# Main Entry Point
###############################################################################
main() {
    # Parse global options
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -y|--yes)
                YES_FLAG=true
                shift
                ;;
            -v|--verbose)
                VERBOSE_FLAG=true
                shift
                ;;
            -h|--help)
                cmd_help
                exit 0
                ;;
            *)
                break
                ;;
        esac
    done

    local command="${1:-help}"
    shift 2>/dev/null || true

    # Always cd to script directory
    cd "${SCRIPT_DIR}"

    case "$command" in
        deploy)       cmd_deploy "$@" ;;
        start)        cmd_start ;;
        stop)         cmd_stop ;;
        restart)      cmd_restart "$@" ;;
        status)       cmd_status ;;
        health)       cmd_health ;;
        logs)         cmd_logs "$@" ;;
        logs-cleanup) cmd_logs_cleanup "$@" ;;
        logs-archive) cmd_logs_archive "$@" ;;
        audit-cleanup) cmd_audit_cleanup "$@" ;;
        update)       cmd_update "$@" ;;
        upgrade)      cmd_upgrade "$@" ;;
        init)         cmd_init ;;
        migrate)      cmd_migrate "$@" ;;
        test)         cmd_test ;;
        mock)         cmd_mock "$@" ;;
        backup)       cmd_backup "$@" ;;
        backup-schedule) cmd_backup_schedule "$@" ;;
        restore)      cmd_restore "$@" ;;
        shell)        cmd_shell "$@" ;;
        ssl)          cmd_ssl "$@" ;;
        config)       cmd_config "$@" ;;
        redis)        cmd_redis "$@" ;;
        scheduler)    cmd_scheduler "$@" ;;
        validate)     cmd_validate ;;
        clean)        cmd_clean ;;
        version)      cmd_version ;;
        help|--help|-h) cmd_help ;;
        *)
            log_error "Unknown command: ${command}"
            echo ""
            cmd_help
            exit 1
            ;;
    esac
}

# Error handler
trap 'log_error "Command failed at line ${LINENO}. Check the error above."; release_lock; exit 1' ERR

# Ensure lock is released on exit
trap release_lock EXIT

main "$@"
