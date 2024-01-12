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
sudo ./scripts/configure_teamviewer.sh

# Add startup.sh to desktop entry 
# Allows run on boot in dedicated terminal window
USERNAME=$(logname)
echo "[Desktop Entry]" > /home/$USERNAME/StartupScript.desktop
echo "Type=Application" >> /home/$USERNAME/StartupScript.desktop
echo "Name=StartupScript" >> /home/$USERNAME/StartupScript.desktop
echo "Exec=lxterminal -e '/home/$USERNAME/scripts/startup.sh'" >> /home/$USERNAME/StartupScript.desktop

# Ensure the Autostart Directory Exists
mkdir -p /home/$USERNAME/.config/autostart/

# Move the Desktop Entry to the Autostart Directory
mv /home/$USERNAME/StartupScript.desktop /home/$USERNAME/.config/autostart/

# Add daily reboot
(crontab -l 2>/dev/null; echo "0 2 * * * /sbin/shutdown -r now") | crontab -

# Install latest version of Docker if not already installed
if ! command -v docker &> /dev/null
then
    curl -sSL https://get.docker.com | sh
fi

# Install Docker Compose
sudo apt-get install docker-compose-plugin -y

# Run startup script
gnome-terminal -- bash -c "sudo ./scripts/startup.sh; exec bash"
