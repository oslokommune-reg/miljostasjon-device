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


## Enabling easy access in Teamviewer
The device should auto assign itself using the hostname into the Teamviewer account using the TEAMVIEWER_ASSIGNMENT_ID located in the teamviewer.env directory.

Once this is done, user should find the assigned device (hostname) in the Teamviewer console. Select `Manage Device Attributes`, navigate to `Managers` menu using the sidebar. Select `Dataplattform`, and check the `Easy Access` box. 

