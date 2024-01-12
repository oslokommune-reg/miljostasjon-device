#!/bin/bash

# Update and upgrade the system
sudo apt-get update
sudo apt-get upgrade -y

# Install Git
sudo apt-get install git -y

# Check version
echo python3 --version

# Install pip
sudo apt install python3-pip -y

# Path to the config file
CONFIG_FILE="config.sh"

# Load config file variables
echo "Loading configuration variables"
chmod u+x ./config.sh
. ./config.sh

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
set_env_variables "dev.env"
set_env_variables "prod.env" 

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

# Remove all unused docker images
docker image prune -a -f

docker compose up --build --remove-orphans --force-recreate