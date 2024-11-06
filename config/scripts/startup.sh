#!/bin/bash

# Set dir to local dir
SCRIPT_DIR=$(dirname "$0")
echo "$PWD"

# Function to check if TeamViewer daemon is active
is_teamviewer_daemon_active() {
    if systemctl is-active --quiet teamviewerd; then
        echo "TeamViewer daemon is already active."
        return 0
    else
        echo "TeamViewer daemon is not active."
        return 1
    fi
}

# Start TeamViewer daemon if not active
if ! is_teamviewer_daemon_active; then
    echo "Starting TeamViewer daemon..."
    sudo teamviewer daemon enable
    sudo teamviewer daemon start
    echo "TeamViewer daemon started."
else
    echo "No need to start TeamViewer daemon. It's already running."
fi

# Assign host to Teamviewer client using token
# ./scripts/enroll_teamviewer_host.sh

config_path="./scripts/config.sh"
fallback_config_path="./config.sh"

if [ -f "$config_path" ]; then
    # If the config file exists in the scripts directory, use it
    . "$config_path"
    echo "Loaded configuration from $config_path"
elif [ -f "$fallback_config_path" ]; then
    # If the config file exists in the current directory, use it
    . "$fallback_config_path"
    echo "Loaded configuration from $fallback_config_path"
else
    # If neither file exists, print an error message
    echo "Error: Configuration file not found in either path."
    exit 1
fi

# Load secrets for each environment
set_env_variables() {
    local env_file=$1

    if [ -f "$env_file" ]; then
        echo "Setting environment variables from $env_file"
        set -a # Automatically export all variables
        source "$env_file"
        set +a
    else
        echo "Environment file $env_file not found."
    fi
}

# Set environment variable for dev and prod
set_env_variables 'dev.env'
set_env_variables 'prod.env' 

# Function to clone or pull a repository
function clone_or_pull() {
    local repo_name=$1
    local repo_url=$2

    if [ -d "$repo_name" ]; then
        echo "Repository exists. Updating..."
        cd "$repo_name" && git pull
        cd ..
    else
        echo "Cloning repository..."
        git clone "$repo_url" "$repo_name"
    fi
}

# Perform Git operations
clone_or_pull $REPO_NAME $REPO_URL
cd $REPO_NAME 

# Clean cache
sudo apt-get clean

# Remove all unused docker images
sudo docker image prune -a -f

# Update all systemctl daemon in case any changes have been made (testing)
sudo systemctl daemon-reload

sudo -E docker compose up --build --remove-orphans --force-recreate
