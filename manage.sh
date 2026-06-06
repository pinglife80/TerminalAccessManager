#!/bin/bash
###############################################################################
# MAC Security Platform - Unified Management Script
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
#   update [--no-git]          Rebuild and restart (after code changes)
#
# Data Commands:
#   init                       Initialize database + admin user (idempotent)
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
#   config [key] [value]       View or set configuration
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
readonly LOCK_FILE="/tmp/mac_security_manage.lock"
readonly STATE_DIR="${SCRIPT_DIR}/.manage"
readonly STATE_FILE="${STATE_DIR}/state.env"
readonly VERSION="2.0.0"

# Docker Compose project name (derived from directory name)
readonly COMPOSE_PROJECT_NAME="mac_security"

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
    echo "  ║          MAC Security Platform v${VERSION}                ║"
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
    if dc exec -T postgres pg_dump -U mac_admin mac_security > "$backup_file" 2>/dev/null; then
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
    echo -e "${CYAN}${BOLD}MAC Security Platform${NC}"
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
    log_step "Deploying MAC Security Platform (${mode} mode)"

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
        echo -e "  ${CYAN}Login:${NC}   admin / admin123"
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

    local db_pass redis_pass secret
    db_pass="demo_db_pass_$(openssl rand -hex 4)"
    redis_pass="demo_redis_$(openssl rand -hex 4)"
    secret="$(openssl rand -hex 32)"

    set_env "DB_PASSWORD" "${db_pass}"
    set_env "REDIS_PASSWORD" "${redis_pass}"
    set_env "SECRET_KEY" "${secret}"

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
    echo -e "  Sangfor API:        $(if [ -n "$(get_env SANGFOR_BASE_URL)" ]; then echo "${GREEN}configured${NC}"; else echo "${DIM}skipped${NC}"; fi)"
    echo -e "  Network switch:     $(if [ -n "$(get_env SWITCH_HOST)" ]; then echo "${GREEN}configured${NC}"; else echo "${DIM}skipped${NC}"; fi)"
    echo ""

    log_success "Production environment configured"
}

_edit_existing_env() {
    echo ""
    echo -e "${BOLD}Current configuration:${NC}"
    echo ""

    local keys=("DB_PASSWORD" "REDIS_PASSWORD" "SECRET_KEY" "SANGFOR_BASE_URL" "SWITCH_HOST")
    local labels=("Database password" "Redis password" "JWT Secret Key" "Sangfor API URL" "Switch Host")

    for i in "${!keys[@]}"; do
        local val
        val=$(get_env "${keys[$i]}")
        if [ "${keys[$i]}" = "DB_PASSWORD" ] || [ "${keys[$i]}" = "REDIS_PASSWORD" ] || [ "${keys[$i]}" = "SECRET_KEY" ]; then
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
        else
            log_error "${svc}: not running"
            issues=$((issues + 1))
        fi
    done

    # 3. Database connectivity
    echo ""
    echo -e "${BOLD}3. Database Connectivity${NC}"
    if dc exec -T postgres pg_isready -U mac_admin -d mac_security &>/dev/null; then
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
    if dc exec -T redis redis-cli -a "${redis_pass}" ping 2>/dev/null | grep -q "PONG"; then
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
# Command: update
###############################################################################
cmd_update() {
    local no_git=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --no-git) no_git=true ;;
            *)        log_error "Unknown option: $1"; exit 1 ;;
        esac
        shift
    done

    ensure_env
    log_step "Updating Application"

    # Auto-backup before update
    auto_backup "pre_update"

    # Pull latest code if git repo
    if [ -d "${SCRIPT_DIR}/.git" ] && ! ${no_git}; then
        log_info "Pulling latest code..."
        if git -C "${SCRIPT_DIR}" pull; then
            log_success "Code updated"
        else
            log_warn "Git pull failed (continuing with local code)"
        fi
    fi

    # Rebuild and restart
    log_info "Rebuilding services..."
    dc up -d --build

    # Wait for backend
    wait_healthy backend 60 || true

    log_success "Update complete"
    log_info "Check logs: ./manage.sh logs"
    log_info "Run health: ./manage.sh health"
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
    dc exec -T postgres pg_dump -U mac_admin mac_security > "$backup_file"

    if [ -f "$backup_file" ] && [ -s "$backup_file" ]; then
        local size
        size=$(du -h "$backup_file" | cut -f1)
        log_success "Backup saved: ${backup_file} (${size})"
    else
        log_error "Backup failed (empty or missing file)"
        rm -f "$backup_file"
        exit 1
    fi

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
    dc exec -T postgres psql -U mac_admin -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'mac_security' AND pid <> pg_backend_pid();" 2>/dev/null || true
    dc exec -T postgres psql -U mac_admin -d postgres -c "DROP DATABASE IF EXISTS mac_security;" 2>/dev/null || true
    dc exec -T postgres psql -U mac_admin -d postgres -c "CREATE DATABASE mac_security;" 2>/dev/null || true

    cat "$backup_file" | dc exec -T postgres psql -U mac_admin -d mac_security
    dc restart backend
    log_success "Database restored from: ${backup_file}"
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
            dc exec postgres psql -U mac_admin -d mac_security
            ;;
        redis|r)
            log_info "Opening Redis CLI..."
            local redis_pass
            redis_pass=$(get_env "REDIS_PASSWORD")
            dc exec redis redis-cli -a "${redis_pass}"
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
        -subj "/C=CN/ST=Beijing/L=Beijing/O=MAC Security/CN=localhost" \
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
cmd_config() {
    local key="${1:-}"
    local value="${2:-}"

    ensure_env

    if [ -z "$key" ]; then
        # Show all configuration
        log_step "Current Configuration"
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
        return 0
    fi

    if [ -z "$value" ]; then
        # Show specific key
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
        # Set key=value
        set_env "$key" "$value"
        log_success "Set ${key} = $(if [[ "$key" == *"PASSWORD"* ]] || [[ "$key" == *"SECRET"* ]]; then echo '********'; else echo "$value"; fi)"

        # If services are running and this is a runtime config, suggest restart
        if [[ "$key" == *"PASSWORD"* ]] || [[ "$key" == *"SECRET"* ]]; then
            log_info "Restart services to apply: ./manage.sh restart"
        fi
    fi
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
    echo -e "  ${GREEN}update${NC} [--no-git]         Rebuild and restart (after code changes)"
    echo ""
    echo -e "${BOLD}Data Management:${NC}"
    echo ""
    echo -e "  ${YELLOW}init${NC}                      Initialize database + admin user"
    echo -e "  ${YELLOW}mock generate${NC}            Generate demo/mock data"
    echo -e "  ${YELLOW}mock clear${NC}               Clear all mock data (keeps admin)"
    echo -e "  ${YELLOW}backup${NC} [file]             Backup database to SQL file"
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
    echo -e "  ${CYAN}config${NC} [key] [value]       View or set configuration"
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
    echo -e "  ${DIM}./manage.sh logs backend -n 50   # Last 50 lines of backend logs${NC}"
    echo -e "  ${DIM}./manage.sh shell db             # Open database shell${NC}"
    echo -e "  ${DIM}./manage.sh backup               # Backup database${NC}"
    echo -e "  ${DIM}./manage.sh config               # View all configuration${NC}"
    echo -e "  ${DIM}./manage.sh config DB_PASSWORD x # Set a config value${NC}"
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
        update)       cmd_update "$@" ;;
        init)         cmd_init ;;
        test)         cmd_test ;;
        mock)         cmd_mock "$@" ;;
        backup)       cmd_backup "$@" ;;
        restore)      cmd_restore "$@" ;;
        shell)        cmd_shell "$@" ;;
        ssl)          cmd_ssl "$@" ;;
        config)       cmd_config "$@" ;;
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
