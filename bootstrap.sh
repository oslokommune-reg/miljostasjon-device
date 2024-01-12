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
chmod u+x scripts/*.sh

# Enforce keyboard layout
sudo ./scripts/change_keyboard_layout.sh

# Install teamviewer
sudo ./scripts/install_teamviewer.sh

# Auto register into teamviewer account
# ./scripts/configure_teamviewer.sh

# Add startup.sh to boot
USER=$(logname)
SERVICE_NAME="startup"
export SCRIPT_PATH="/home/${USER}/scripts/startup.sh"
cat <<EOF | sudo -E tee /etc/systemd/system/$SERVICE_NAME.service
[Unit]
Description=Startup procedure

[Service]
WorkingDirectory=/home/miljostasjon/scripts
ExecStart=$SCRIPT_PATH
StandardOutput=syslog
StandardError=syslog

[Install]
WantedBy=graphical.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME.service
sudo systemctl start $SERVICE_NAME.service

# (crontab -l 2>/dev/null; echo "@reboot /home/scripts/startup.sh") | crontab -

# Add daily reboot
(crontab -l 2>/dev/null; echo "0 2 * * * /sbin/shutdown -r now") | crontab -

# Install latest version of Docker if not already installed
if ! command -v docker &> /dev/null
then
    curl -sSL https://get.docker.com | sh
fi

# Install Docker Compose
sudo apt-get install docker-compose-plugin -y

# Reboot
sudo reboot now
