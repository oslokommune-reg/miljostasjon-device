# Set keyboard layout to Norwegian
sudo sed -i '/^XKBLAYOUT=/s/".*"/"no"/' /etc/default/keyboard

# Reconfigure keyboard-configuration
sudo dpkg-reconfigure -f noninteractive keyboard-configuration