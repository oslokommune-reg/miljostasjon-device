#!/bin/bash
# ============================================================
# Miljostasjon startup script
# Runs at boot via systemd (miljostasjon-startup.service)
# ============================================================

# Run from the directory the script lives in (resolved to absolute path)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || { echo "ERROR: cannot cd into script dir"; exit 1; }
echo "Running from: $PWD"

# ------------------------------------------------------------
# TeamViewer daemon
# ------------------------------------------------------------
is_teamviewer_daemon_active() {
    systemctl is-active --quiet teamviewerd
}

if ! is_teamviewer_daemon_active; then
    echo "Starting TeamViewer daemon..."
    sudo teamviewer daemon enable
    sudo teamviewer daemon start
else
    echo "TeamViewer daemon already running."
fi

# Assign host to Teamviewer client using token
# ./scripts/enroll_teamviewer_host.sh

# ------------------------------------------------------------
# Load configuration (REPO_NAME, REPO_URL, ...)
# ------------------------------------------------------------
config_path="./scripts/config.sh"
fallback_config_path="./config.sh"

if [ -f "$config_path" ]; then
    # shellcheck disable=SC1090
    . "$config_path"
    echo "Loaded configuration from $config_path"
elif [ -f "$fallback_config_path" ]; then
    # shellcheck disable=SC1090
    . "$fallback_config_path"
    echo "Loaded configuration from $fallback_config_path"
else
    echo "ERROR: Configuration file not found in either path."
    exit 1
fi

# ------------------------------------------------------------
# Load env files (secrets)
# NOTE: env files live in the user's home directory, one level
# above this script (~/dev.env, ~/prod.env), not inside ~/scripts.
# ------------------------------------------------------------
set_env_variables() {
    local env_file=$1
    if [ -f "$env_file" ]; then
        echo "Setting environment variables from $env_file"
        set -a
        # shellcheck disable=SC1090
        source "$env_file"
        set +a
    else
        echo "WARNING: Environment file $env_file not found."
    fi
}

set_env_variables '../dev.env'
set_env_variables '../prod.env'

# Sanity check: warn loudly if the variables compose.yml needs are empty.
# Empty values cause silent failures like 'Invalid URL /power: No scheme supplied'.
if [ -z "${PROD_API_GATEWAY_MILJOSTASJON_URL:-}" ] || [ -z "${PROD_API_GATEWAY_MILJOSTASJON_KEY:-}" ]; then
    echo "WARNING: PROD_API_GATEWAY_MILJOSTASJON_URL or _KEY is empty. Check ../prod.env."
fi

# ------------------------------------------------------------
# Git: clone if missing, fetch, rebuild only on new commits
# ------------------------------------------------------------
BRANCH="${REPO_BRANCH:-main}"

# Clone if the repo doesn't exist yet
if [ ! -d "$REPO_NAME/.git" ]; then
    echo "Cloning $REPO_URL (branch $BRANCH)..."
    if ! git clone --branch "$BRANCH" "$REPO_URL" "$REPO_NAME"; then
        echo "ERROR: git clone failed; aborting startup."
        exit 1
    fi
fi

REPO_PATH="$(realpath "$REPO_NAME")"

# Whitelist the repo for ALL users (writes to /etc/gitconfig).
# Without this, 'git fetch' silently fails when systemd runs the script as
# root and the repo is owned by the regular user (or vice versa).
# Idempotent — git deduplicates entries on its own.
git config --system --add safe.directory "$REPO_PATH" 2>/dev/null || true

cd "$REPO_PATH" || { echo "ERROR: cannot cd into $REPO_PATH"; exit 1; }

echo "Currently at: $(git rev-parse --short HEAD) — $(git log -1 --format=%s)"

# General housekeeping (runs regardless of pull result)
sudo apt-get clean
sudo systemctl daemon-reload

# Fetch — intentionally NOT --quiet so failures appear in journalctl
if ! git fetch origin "$BRANCH"; then
    echo "WARNING: git fetch failed; running existing containers without update."
    sudo -E docker compose up -d --remove-orphans
    exit 0
fi

LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "Already up to date at $LOCAL; ensuring containers are running."
    sudo -E docker compose up -d --remove-orphans
else
    echo "New commits on origin/$BRANCH: $LOCAL -> $REMOTE"

    if ! git pull --ff-only origin "$BRANCH"; then
        echo "ERROR: git pull --ff-only failed (likely non-fast-forward). Manual fix needed."
        sudo -E docker compose up -d --remove-orphans
        exit 1
    fi

    echo "Now at: $(git rev-parse --short HEAD) — $(git log -1 --format=%s)"

    sudo -E docker compose down --remove-orphans || true
    sudo -E docker compose build --pull
    sudo -E docker compose up -d --force-recreate --remove-orphans
fi

# ------------------------------------------------------------
# Docker auto-cleanup (safe, cache-friendly)
# ------------------------------------------------------------
echo "Running docker cleanup..."

# Always: cheap cleanups
sudo docker image prune -f                                  # dangling images
sudo docker container prune -f --filter "until=720h"        # stopped >30d

DOCKER_DIR="${DOCKER_DIR:-/var/lib/docker}"
FREE_MB=$(df -Pm "$DOCKER_DIR" | awk 'NR==2{print $4}')
THRESHOLD_MB=3072                                           # 3 GB threshold

echo "Free space at $DOCKER_DIR: ${FREE_MB:-unknown}MB (threshold: ${THRESHOLD_MB}MB)"

if [ "${FREE_MB:-0}" -lt "$THRESHOLD_MB" ]; then
    echo "Low disk space — running aggressive prune (>30d only)."
    sudo docker image prune -a -f --filter "until=720h"
    sudo docker builder prune -f --filter "until=720h"
    sudo docker network prune -f
fi

if [ "$(date +%d)" = "01" ]; then
    echo "Monthly housekeeping prune."
    sudo docker image prune -a -f --filter "until=720h"
    sudo docker builder prune -f --filter "until=720h"
fi

echo "Startup complete."
