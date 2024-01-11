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
chmod u+x ./config.sh
. ./config.sh

# Function to clone or pull a repository
clone_or_pull() {
    if [ -d "$2" ]; then
        # Directory exists, so pull
        cd "$2"
        git pull origin "$1"
        cd ..
    else
        # Directory does not exist, so clone
        git clone -b "$1" "$REPO_URL" "$2"
    fi
}

# Perform Git operations
clone_or_pull $MAIN_BRANCH $MAIN_DIR
clone_or_pull $DEV_BRANCH $DEV_DIR

cd $REPO_NAME 
docker compose up --build --remove-orphans --force-recreate

# Remove all unused docker images
docker image prune -a