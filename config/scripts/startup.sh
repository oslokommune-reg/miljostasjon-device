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
# Docker self-repair
# A power cut can leave Docker's network database with two "docker0"
# bridges; dockerd then refuses to start ("networks have same bridge name")
# and nothing runs until someone fixes it by hand. The database is
# recreated automatically, so removing it is safe.
# ------------------------------------------------------------
ensure_docker() {
    systemctl is-active --quiet docker && return 0
    sudo systemctl start docker && sleep 3
    systemctl is-active --quiet docker && return 0

    if sudo journalctl -u docker -b --no-pager | grep -q "networks have same bridge name"; then
        echo "Docker network state is corrupt; resetting it."
        sudo systemctl stop docker.socket docker.service
        sudo rm -f /var/lib/docker/network/files/local-kv.db
        sudo systemctl reset-failed docker
        sudo systemctl start docker
    fi
    systemctl is-active --quiet docker || echo "ERROR: Docker is not running."
}

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

# Older images cloned the repo into ~/<repo> instead of ~/scripts/<repo>.
# Reuse that clone if present, so those stations are not re-cloned.
if [ ! -d "$REPO_NAME/.git" ] && [ -d "../$REPO_NAME/.git" ]; then
    REPO_NAME="../$REPO_NAME"
fi

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

# Remove stale lock files left by a git process killed mid-operation
# (power loss, reboot). Nothing else runs git at boot, and a leftover
# lock makes every later fetch/pull fail, so the station stops updating.
find .git -maxdepth 4 -name '*.lock' -mmin +5 -print -delete 2>/dev/null || true

# Follow the checked-out branch (like older startup.sh versions did), so a
# test station can track e.g. test-pi. New clones are on main. REPO_BRANCH
# overrides; a detached HEAD falls back to main.
if [ -z "${REPO_BRANCH:-}" ]; then
    CURRENT_BRANCH="$(git symbolic-ref --short -q HEAD || true)"
    BRANCH="${CURRENT_BRANCH:-main}"
fi
echo "Tracking branch: $BRANCH"

# Fetch — intentionally NOT --quiet so failures appear in journalctl
UPDATED=0
if ! git fetch origin "$BRANCH"; then
    echo "WARNING: git fetch failed; running existing version without update."
elif [ "$(git rev-parse HEAD)" = "$(git rev-parse "origin/$BRANCH")" ]; then
    echo "Already up to date at $(git rev-parse --short HEAD)."
else
    echo "New commits on origin/$BRANCH: $(git rev-parse --short HEAD) -> $(git rev-parse --short "origin/$BRANCH")"
    if git pull --ff-only origin "$BRANCH"; then
        UPDATED=1
        echo "Now at: $(git rev-parse --short HEAD) — $(git log -1 --format=%s)"
    else
        echo "ERROR: git pull --ff-only failed (likely non-fast-forward). Manual fix needed."
    fi
fi

# ------------------------------------------------------------
# Power-safety host config (data dir, controlled shutdown, fewer SD
# writes). Idempotent; only present on branches that have it.
# ------------------------------------------------------------
if [ -f config/host/apply_host_config.sh ]; then
    sudo bash config/host/apply_host_config.sh || echo "WARNING: host config failed."
fi

ensure_docker

if [ "$UPDATED" = 1 ]; then
    sudo -E docker compose down --remove-orphans || true
    sudo -E docker compose build --pull
fi
sudo -E docker compose up -d --remove-orphans

# ------------------------------------------------------------
# Remove the old daily-reboot cron job. Older images added
# "0 2 * * * /sbin/shutdown -r now" to the user's crontab; it never worked
# (non-root), and stations are now power-cycled via a Shelly relay instead.
# ------------------------------------------------------------
CRON_USER="$(stat -c %U "$SCRIPT_DIR")"
for u in "$CRON_USER" root; do
    if crontab -u "$u" -l 2>/dev/null | grep -q '/sbin/shutdown -r now'; then
        crontab -u "$u" -l 2>/dev/null | grep -v '/sbin/shutdown -r now' | crontab -u "$u" -
        echo "Removed daily-reboot cron job for $u."
    fi
done

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
