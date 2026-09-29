---
title: Install a plugin
nav: Install
order: 10
summary: How to put a plugin from the catalog on your MPC or Force, check it, update it and remove it.
---

Every plugin in the catalog is one zip file with an installer inside. You need a computer on the same network as the device and a few minutes.

> Installing plugins this way is unofficial. It edits MPC's settings file, so it needs **root (SSH) access**, which stock MPC OS does not offer. These releases are for modded units. Back up your projects first and use it at your own risk.

## What you need
- A first-generation MPC OS standalone device with a 32-bit ARM processor: Force, MPC Live and Live II, One, X and Key 61. The installer refuses anything else. Newer models are untested.
- Root SSH access to the device, and its IP address. The address is assigned by your router, so look it up on the device or in your router each time.
- The plugin's release zip from the catalog. Each plugin's page lists any extra files it needs (for example, a sound engine that needs ROM files you supply yourself).

## 1. Download and check the zip
Download the zip from the plugin's card on the catalog. Every version lists a checksum (SHA-256). Compare it with your download:

```
shasum -a 256 Name-1.2.0-mpc-armv7.zip      # macOS and Linux
certutil -hashfile Name-1.2.0-mpc-armv7.zip SHA256    # Windows
```

If the first characters do not match the catalog, download it again. Also open the plugin's source link and read what you are about to run as root: the installer is a plain shell script.

## 2. Copy it to the device
Unzip it, then copy the whole folder over:

```
unzip Name-1.2.0-mpc-armv7.zip
scp -r Name-1.2.0 root@<device-ip>:/tmp/
```

## 3. Run the installer
Save your project on the device first. The installer **stops MPC and starts it again**.

```
ssh root@<device-ip> sh /tmp/Name-1.2.0/install.sh
```

It checks the device, copies the plugin and its skin, backs up `MPC.settings` next to the original, adds the plugin to MPC's plugin list and restarts MPC. Add `-y` to skip the confirmation question. If anything fails, MPC is restarted and your settings are left unchanged.

## 4. Use it
On the device, add the plugin to a track from the plugin browser: instruments under Instrument plugins, effects under Insert effects. Its screen appears in the plugin view, and the Q-Links follow the page. Save and reload a project once to make sure it comes back.

## Plugins you build yourself
A plugin with the **Build it yourself** badge has no download: its build embeds your own firmware, so nobody can publish the result. You build it once, on **your computer**, then install it on your device. The device itself does not build anything.

1. **Get your own files.** The plugin's card lists them under "You need" (for example an Elektron OS `.syx` file). Keep them somewhere you can find.
2. **Set up your computer.** Install [Docker](https://www.docker.com/) and git. The build scripts are shell scripts, so use macOS or Linux (on Windows, WSL should work; the plugin's README says what it was tested on).
3. **Get the plugin's source on your computer.** This is the `git clone` step in the plugin's README: run `git clone --recursive https://github.com/<owner>/<plugin-repo>.git`, then `cd <plugin-repo>`. The card's Source link shows the repo.
4. **Run the build command** from the plugin's card, with the path to your own file. It builds inside Docker and takes a few minutes; the first run also downloads what it needs. It stops with an error if its self-check fails rather than giving you a build that is not verified.
5. **Install it.** If the command has a `-d <device-ip>` option, adding it copies the result to your device over SSH and runs the installer, which **stops and restarts MPC** (save your project first). Without it, the build leaves a zip in the plugin's `dist/` folder; install that as described in "Install a plugin" above, from step 2.
6. **Keep the result to yourself.** It contains data derived from your firmware. Install it on your own devices only and never share or upload it.

The exact command, and any extra tools it needs, are on the plugin's card and in its README.

## Update to a new version
Run the new version's `install.sh` the same way. It replaces the old files in place and keeps the same plugin entry, so your projects still find the plugin.

The catalog shows a **Compat** number for each version. If it goes up, the parameters changed, and projects saved with an older version will sound different. Read the release notes before updating a plugin you use in finished songs.

If MPC still runs the old version afterwards, remove every copy of the plugin from your project and insert it again.

## Remove a plugin
```
ssh root@<device-ip> sh /tmp/Name-1.2.0/uninstall.sh
```

This removes the files and the plugin-list entry (after a backup) and restarts MPC. Projects that used the plugin still open, without it.

## Install by hand
Each zip's `INSTALL.md` lists the manual steps: copy the files, stop MPC (`systemctl stop acvs`), back up `MPC.settings`, add the line from `plugin.xml` to the plugin list, and start MPC (`systemctl start acvs`).

## If something goes wrong
- **MPC shows default settings after the restart.** The edited settings file was not accepted. Restore the backup the installer made, named `MPC.settings.bak-<plugin>-<date>`, next to `MPC.settings`.
- **The plugin is not in the list.** MPC reads its plugin list at startup. Restart MPC and check that the installer finished with "Done".
- **The plugin loads but has no screen.** The skin goes in a `/sdcard/Synths` folder, and MPC must have that folder in its content locations. The installer warns if it does not.
- **A message about ARM or `armv7`.** Your device is not a supported model.
- **Silence, or default sounds.** Some plugins need files you provide, such as ROMs or banks. Check the plugin's own page.

Ask in the community with the plugin's name, version, your device model and the installer's output.
