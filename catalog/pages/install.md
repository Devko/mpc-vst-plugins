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

## Fast option: one command for several plugins
On the [catalog](index.html), tick **Add to install list** on each plugin you want, open the bar that appears at the bottom, type your device's IP address and copy the command. Paste it into a terminal (Terminal on a Mac, PowerShell on Windows 10 or later) and press Enter. The command logs in to your device, downloads a small script (`mpc-store.sh`) from this site and runs it. The script:

- downloads every zip you picked and checks it against the checksum in the catalog, before it changes anything on the device;
- asks you to confirm, then stops MPC **once**, runs each plugin's own installer, and starts MPC again **once**;
- remembers what it installed, so `update` later installs newer versions (and holds back a change that would alter saved projects unless you add `--major`).

Prefer to read the script before running it? The bar has a "Read the script first" section with the steps and the hash the script should have. The same command with `list`, `update`, `remove <id>` or `sync` at the end shows what is available, updates what you installed, removes a plugin (your own files in its folder are kept), or registers plugin folders you copied into `Synths` by hand. It needs the same root SSH access as the manual steps below, and plugins you build yourself are not included: they have their own steps.

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

It checks the device, stops MPC, copies the plugin folder (the plugin, its skin and its data) into `/sdcard/Synths`, backs up `MPC.settings` next to the original, adds the plugin to MPC's plugin list and starts MPC again. Add `-y` to skip the confirmation question. If anything fails, MPC is restarted and your settings are left unchanged.

## Easy option: use Termius instead of typing commands
If you would rather click than type, use an SSH app with a file browser. [Termius](https://termius.com/) is one (macOS, Windows, Linux, iPhone, iPad and Android); other SFTP and SSH apps work the same way. You do the same two things as steps 2 and 3, with the mouse:

1. **Add your device as a host.** In Termius, add a new host with the device's IP address and the username `root`, using the same login you would use with `ssh`. Connect once to check it works.
2. **Copy the folder over.** Unzip the plugin's zip on your computer first. Open the host's file browser (SFTP), go to `/tmp` on the device, and drag the unzipped plugin folder into it.
3. **Run the installer.** Open a terminal on the same host and type `sh /tmp/<the-folder-name>/install.sh` (Tab completes the folder name). Save your project first: it stops and restarts MPC. Answer `y` when it asks, or add `-y` to skip the question.

The app's buttons and plans change over time, so check Termius's own help if a screen looks different. It is only a nicer way to do steps 2 and 3: the plugin, the checksum check and the installer are the same.

## 4. Use it
On the device, add the plugin to a track from the plugin browser: instruments under Instrument plugins, effects under Insert effects. Its screen appears in the plugin view, and the Q-Links follow the page. Save and reload a project once to make sure it comes back.

## Plugins you build yourself
A plugin with the **Build it yourself** badge has no download: its build embeds your own firmware, so nobody can publish the result. You build it once, on **your computer**, then install it on your device. The device itself does not build anything.

1. **Get your own files.** The plugin's card lists them under "You need" (for example an Elektron OS `.syx` file). Keep them somewhere you can find.
2. **Set up your computer.** You need Docker, git and Python 3, and a Linux-style shell: macOS, Ubuntu, or Ubuntu in WSL on Windows. The [Get set up](setup.html) page walks through it, with a check after each step.
3. **Get the plugin's source on your computer.** This is the `git clone` step in the plugin's README: run `git clone --recursive https://github.com/<owner>/<plugin-repo>.git`, then `cd <plugin-repo>`. The card's Source link shows the repo.
4. **Run the build command** from the plugin's card, with the path to your own file. It builds inside Docker and takes a few minutes; the first run also downloads what it needs. It stops with an error if its self-check fails rather than giving you a build that is not verified.
5. **Install it.** If the command has a `-d <device-ip>` option, adding it copies the result to your device over SSH and runs the installer, which **stops and restarts MPC** (save your project first). Without it, the build leaves a zip in the plugin's `dist/` folder; install that as described in "Install a plugin" above, from step 2.
6. **Keep the result to yourself.** It contains data derived from your firmware. Install it on your own devices only and never share or upload it.

The exact command, and any extra tools it needs, are on the plugin's card and in its README.

## Update to a new version
Run the new version's `install.sh` the same way. It replaces the old files in place and keeps the same plugin entry, so your projects still find the plugin. Files you added yourself (ROMs, kits, banks) are kept. If you installed the plugin with an older release (the `.so` in `/sdcard/vst`), the installer replaces that install and moves your files into the plugin's new folder in `/sdcard/Synths`.

The catalog shows a **Compat** number for each version. If it goes up, the parameters changed, and projects saved with an older version will sound different. Read the release notes before updating a plugin you use in finished songs.

If MPC still runs the old version afterwards, remove every copy of the plugin from your project and insert it again.

## Remove a plugin
```
ssh root@<device-ip> sh /tmp/Name-1.2.0/uninstall.sh
```

This removes the files and the plugin-list entry (after a backup) and restarts MPC. Projects that used the plugin still open, without it.

## Install by hand
Each zip's `INSTALL.md` lists the manual steps: copy the plugin folder (`portable/<Vendor> - VST - <Name>/` in the zip) to `/sdcard/Synths/`, stop MPC (`systemctl stop acvs`), back up `MPC.settings`, add the line from that folder's `plugin-meta.xml` to the plugin list with `%payload-path%` replaced by `/sdcard/Synths`, and start MPC (`systemctl start acvs`). Edit the settings file only while MPC is stopped (see below).

## If a plugin disappears after a restart
MPC keeps its whole plugin list in one place: the `pluginList-arm` list in its settings file, `MPC.settings`. Every way of installing plugins edits that same list, so one method can undo another. The plugin's files usually are still on the card; only its line in the list is gone. The usual causes:

- **The settings file was edited while MPC was running.** MPC holds its settings in memory while it runs and saves them itself, so a change made underneath it can be overwritten. Stop MPC first (`systemctl stop acvs`), edit, then start it (`systemctl start acvs`). The installer does this for you.
- **Another tool rebuilt the whole list.** Some community installers and scan scripts do not add one line: they write a new list from the plugin folders they find in the `Synths` folders (each folder with a `plugin-meta.xml` inside). A plugin that is not such a folder, for example one added by hand or installed by an older release with its `.so` in `/sdcard/vst`, drops off the list at the next scan. A release is such a folder if its zip has a `portable/` folder inside, and a scan keeps it. Reinstall anything older with a release that has one.
- **The settings file became invalid.** After a broken edit MPC resets `MPC.settings` to its defaults, which empties the plugin list along with your other preferences. Restore a backup (below).
- **The line points to a file that is not there**: a plugin folder was moved or renamed, or the card it is on is not inserted.

Check what MPC has registered, and whether each file exists (on the device, over SSH):

```
grep -o 'file="[^"]*"' /media/az01-internal/Settings/*/MPC.settings | cut -d'"' -f2 |
    while read -r f; do [ -f "$f" ] && echo "ok       $f" || echo "MISSING  $f"; done
```

To get plugins back:
- **Run each plugin's `install.sh` again** (the current release). It adds its own line back and leaves every other plugin's line alone. This is the safest fix.
- **Or restore a backup of the settings file.** The installer and uninstaller leave one next to the original each time they run, named `MPC.settings.bak-<plugin>-<date>`. List them newest first with `ls -t /media/az01-internal/Settings/*/MPC.settings.bak-*`, then stop MPC, copy the one you want over `MPC.settings`, and start MPC. A backup also brings back the preferences you had at that time.

Before you paste a command you found online into the device's shell, copy the settings file to your computer: `scp "root@<device-ip>:/media/az01-internal/Settings/*/MPC.settings" .` Any command that rebuilds, restores or resets that file replaces your whole plugin list.

## If something goes wrong
- **MPC shows default settings after the restart.** The edited settings file was not accepted. Restore the backup the installer made, named `MPC.settings.bak-<plugin>-<date>`, next to `MPC.settings`.
- **The plugin is not in the list.** MPC reads its plugin list at startup. Check that the installer finished with "Done", then see "If a plugin disappears after a restart" above.
- **The plugin loads but has no screen.** The skin goes in a `/sdcard/Synths` folder, and MPC must have that folder in its content locations. The installer warns if it does not.
- **A message about ARM or `armv7`.** Your device is not a supported model.
- **Silence, or default sounds.** Some plugins need files you provide, such as ROMs or banks. Check the plugin's own page.

Ask in the community with the plugin's name, version, your device model and the installer's output.
