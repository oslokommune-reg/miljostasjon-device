#!/bin/bash

# Update and upgrade the system
sudo apt-get update
sudo apt-get upgrade -y

# Install Git
sudo apt-get install git -y

# Check Python version
echo "Python version:"
python3 --version

# Install pip
sudo apt install python3-pip -y

# Make scripts runnable
chmod u+x ./startup.sh
chmod u+x ./install_teamviewer.sh

# Install teamviewer
sudo ./install_teamviewer.sh

# Add startup script to run on boot
# Assuming 'startup.sh' should be run at boot, add it to crontab
(crontab -l 2>/dev/null; echo "@reboot $(pwd)/startup.sh") | crontab -

# Install latest version of Docker if not already installed
if ! command -v docker &> /dev/null
then
    curl -sSL https://get.docker.com | sh
fi

# Install Docker Compose
sudo apt-get install docker-compose-plugin -y

# Run startup script
sudo ./startup.sh