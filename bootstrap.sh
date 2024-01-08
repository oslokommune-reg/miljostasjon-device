#!/bin/bash

# Update and upgrade the system
sudo apt-get update
sudo apt-get upgrade -y

# Install Docker
curl -sSL https://get.docker.com | sh

# Add the default Pi user to the Docker group
sudo usermod -aG docker pi

# Install Python
sudo apt-get install -y python3 python3-pip

# Post-installation steps for Docker (optional, but recommended)
sudo systemctl enable docker
sudo systemctl start docker

# Verify Docker and Python installation
docker --version
python3 --version
pip3 --version

echo "Docker and Python have been successfully installed."


# Install docker compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

echo "Docker compose successfully installed."