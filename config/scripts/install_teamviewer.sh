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

# Function to check TeamViewer connectivity
check_teamviewer_connection() {
    for i in {1..5}; do
        if sudo teamviewer info | grep -q "TeamViewer ID:"; then
            return 0
        fi
        echo "Attempt $i: Waiting for TeamViewer to connect..."
        sleep 10
    done
    return 1
}


# Update package lists and install TeamViewer if not installed
if ! is_teamviewer_installed; then
    echo "Installing TeamViewer..."

    # Install necessary dependencies
    sudo apt-get install -y libqt5gui5 qml-module-qtquick2 qml-module-qtquick-controls qml-module-qtquick-dialogs \
    qml-module-qtquick-privatewidgets qml-module-qtquick-window2 qml-module-qtquick-layouts \
    qml-module-qtquick2 libqt5qml5 libqt5quick5 libqt5webkit5 qml-module-qtwebkit \
    jq

    # Download TeamViewer DEB package
    echo "Performing wget for teamviewer host download..."
    sudo wget https://download.teamviewer.com/download/linux/teamviewer-host_armhf.deb

    # Install TeamViewer
    echo "Running dpkg on downloaded package..."
    sudo dpkg -i teamviewer-host_armhf.deb

    echo "Running sudo apt-get install -f -y"
    sudo apt-get install -f -y

    # Clean up downloaded package
    echo "Cleaning up installation package"
    rm teamviewer-host_armhf.deb

    echo "TeamViewer installation completed."

    # Get Teamviewer ID from file
    source /home/miljostasjon/teamviewer.env

    # Auto-accept Teamviewer EULA
    sudo teamviewer daemon stop
    sudo bash -c 'echo "[int32] EulaAccepted = 1" >> /opt/teamviewer/config/global.conf'
    sudo bash -c 'echo "[int32] EulaAcceptedRevision = 6" >> /opt/teamviewer/config/global.conf'

    # Start TeamViewer daemon and service
    sudo teamviewer daemon start
    sudo teamviewer daemon enable

    # Wait for TeamViewer to initialize (add delay)
    echo "Waiting for TeamViewer services to initialize..."
    sleep 60
    if check_teamviewer_connection; then
        echo "TeamViewer is connected. Proceeding with assignment..."
        # Use teamviewer CLI to assign using assignment id
        echo "Assigning device to TeamViewer"
        sudo teamviewer assignment --id $TEAMVIEWER_ASSIGNMENT_ID
        echo "Device addition complete!"
    else
        echo "ERROR: TeamViewer failed to establish connection after multiple attempts"
fi

else
    echo "Skipping installation. TeamViewer is already installed."
fi
