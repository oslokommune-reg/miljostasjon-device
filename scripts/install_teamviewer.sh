# Installer TeamViewer
echo "Installerer TeamViewer..."
sudo apt-get install libminizip1
wget https://download.teamviewer.com/download/linux/teamviewer_armhf.deb
sudo dpkg -i teamviewer_armhf.deb
sudo apt-get install -fy
rm teamviewer_armhf.deb