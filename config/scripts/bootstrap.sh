#!/bin/bash

# Add startup.sh to boot
USER=$USER
SERVICE_NAME="miljostasjon-startup"
export SCRIPT_PATH="/home/${USER}/scripts/startup.sh"


# Make all scripts in ./scripts/ executable
chmod u+x /home/${USER}/scripts/*.sh

echo "Creating systemd service..."
cat <<EOF | sudo -E tee /etc/systemd/system/$SERVICE_NAME.service
[Unit]
Description=Startup procedure

[Service]
WorkingDirectory=/home/${USER}
ExecStart=$SCRIPT_PATH
StandardOutput=syslog
StandardError=syslog

[Install]
WantedBy=graphical.target
EOF


sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME.service
sudo systemctl start $SERVICE_NAME.service

# Add daily reboot to crontab
echo "Setting up daily reboot..."
(crontab -l 2>/dev/null; echo "0 2 * * * /sbin/shutdown -r now") | crontab -

# # Get Teamviewer ID from file
# source ./home/${USER}/teamviewer.env

# # # Auto-accept Teamviewer EULA
# sudo teamviewer daemon stop
# sudo bash -c 'echo "[int32] EulaAccepted = 1" >> /opt/teamviewer/config/global.conf'
# sudo bash -c 'echo "[int32] EulaAcceptedRevision = 6" >> /opt/teamviewer/config/global.conf'

# # Start TeamViewer daemon and service
# sudo teamviewer daemon start
# sudo teamviewer daemon enable

# # # Use teamviewer CLI to assign using assignment id
# # echo "Assignign device to Teamviewer"
# # sudo teamviewer assignment --id $TEAMVIEWER_ASSIGNMENT_ID

# # echo "Device addition complete!"

# # Final reboot
# # echo "Installation complete. Rebooting system..."
# # sudo reboot now