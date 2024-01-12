#!/bin/bash

# Function to check if TeamViewer is installed
is_teamviewer_installed() {
    if command -v teamviewer >/dev/null 2>&1; then
        echo "TeamViewer is already installed."
        return 0
    else
        echo "TeamViewer is not installed."
        return 1
    fi
}

# Update package lists and install TeamViewer if not installed
if ! is_teamviewer_installed; then
    echo "Installing TeamViewer..."

    # Update package lists
    sudo apt-get update

    # Install necessary dependencies
    sudo apt-get install -y libqt5gui5 qml-module-qtquick2 qml-module-qtquick-controls qml-module-qtquick-dialogs \
    qml-module-qtquick-privatewidgets qml-module-qtquick-window2 qml-module-qtquick-layouts \
    qml-module-qtquick2 libqt5qml5 libqt5quick5 libqt5webkit5 qml-module-qtwebkit

    # Download TeamViewer DEB package
    wget https://download.teamviewer.com/download/linux/teamviewer-host_armhf.deb

    # Install TeamViewer
    sudo dpkg -i teamviewer-host_armhf.deb
    sudo apt-get install -f -y

    # Clean up downloaded package
    rm teamviewer-host_armhf.deb

    # Start TeamViewer service
    sudo teamviewer daemon enable
    sudo teamviewer daemon start

    echo "TeamViewer installation completed."
else
    echo "Skipping installation. TeamViewer is already installed."
fi
