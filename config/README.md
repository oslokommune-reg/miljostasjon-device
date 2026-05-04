# Miljostasjon image builder

## Usage

Documentation for the sdm package is found here:
https://github.com/gitbls/sdm/blob/master/Docs/Plugins.md#copyfile


Firstly, install SDM so that you can build the image(s):
```
curl -L https://raw.githubusercontent.com/gitbls/sdm/master/EZsdmInstaller | bash
```

Ensure there is an image present in the directory. The script is configured to run for the image `2024-10-22-raspios-bookworm-arm64.img`, this can be changed in the `build_sdm.sh` file.

Now run the below command to customize the image
```
./build_sdm.sh
```

Once that has succeed, burn the image to your SD card (change the path as needed):
```
./format_and_burn_sdcard.sh --path mmcblk0 --hostname miljostasjon-3

```

## Building from Windows (via WSL)

If you are on Windows, run the build through WSL. The wrapper script `build_image.sh` handles the WSL-specific quirks (mirroring the project to WSL's native filesystem for performance and loop-device support) and adds a timestamp to the resulting image.

**One-time setup:**

1. Install WSL2 and Ubuntu (PowerShell as admin):
   ```
   wsl --install
   ```
   Restart if prompted. Verify with `wsl -l -v` that VERSION is 2.

2. In the Ubuntu/WSL terminal, install dependencies:
   ```
   sudo apt update
   sudo apt install -y rsync curl dos2unix
   curl -L https://raw.githubusercontent.com/gitbls/sdm/master/EZsdmInstaller | bash
   ```

3. From the project directory in WSL, fix line endings (since files come from Windows) and make the wrapper executable:
   ```
   find . -type f \( -name "*.sh" -o -name "*.env" \) -exec dos2unix {} +
   chmod +x build_image.sh
   ```

**Build:**
```
./build_image.sh
```

When done, you'll find `miljostasjon-pi-YYYYMMDD-HHMMSS.img` in the project directory, ready to burn to an SD card.

Note: the `apt upgrade` step inside the build typically takes 15–40 minutes on WSL due to ARM emulation. This is normal.


## Enabling easy access in Teamviewer
The device should auto assign itself using the hostname into the Teamviewer account using the TEAMVIEWER_ASSIGNMENT_ID located in the teamviewer.env directory.

Once this is done, user should find the assigned device (hostname) in the Teamviewer console. Select `Manage Device Attributes`, navigate to `Managers` menu using the sidebar. Select `Dataplattform`, and check the `Easy Access` box.