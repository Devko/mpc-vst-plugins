---
title: Get set up
nav: Setup
order: 5
summary: What you need on your computer before you install or build MPC OS plugins, in plain steps, with a check after each one.
---

You do not need to be a programmer. This page gets a computer ready for the other guides. The commands are examples: for anything you install, the linked official pages have the current steps.

## What you need
**To install a downloaded plugin** you only need:
- A computer on the same network as your device, with a terminal that has `ssh` and `scp`. macOS and Linux have them; Windows 10 and 11 have them in PowerShell.
- **Root SSH access** to your MPC or Force, and its IP address. Stock MPC OS does not offer this; you need a modded unit.

**To build a plugin yourself** (a "Build it yourself" plugin, or your own port) you also need:
- **A Linux-style shell:** Terminal on macOS, Ubuntu on Linux, or Ubuntu inside WSL on Windows.
- **Git** and **Python 3.**
- **Docker.** The builds run inside it, so nothing else has to be installed by hand.
- Several GB of free disk space (Docker downloads build images the first time) and a few minutes.

Building never happens on the device. The device only receives the finished plugin.

## 1. Open a terminal
- **macOS:** open the Terminal app.
- **Ubuntu or other Linux:** press Ctrl+Alt+T, or open "Terminal".
- **Windows:** the build scripts are shell scripts, so use Ubuntu inside WSL 2. In PowerShell (as administrator) run `wsl --install`, restart, then open "Ubuntu" from the Start menu and finish its first-run setup. See Microsoft's [WSL install guide](https://learn.microsoft.com/windows/wsl/install). From here on, run every command in the Ubuntu window.

## 2. Install git and Python 3
- **Ubuntu and WSL:** `sudo apt update && sudo apt install git python3`
- **macOS:** run `xcode-select --install` once; it installs git and Python 3.

Check: `git --version` and `python3 --version` each print a version number.

## 3. Install Docker
- **macOS and Windows:** install [Docker Desktop](https://docs.docker.com/desktop/) and start it. On Windows, open its settings and turn on WSL integration for Ubuntu.
- **Ubuntu:** follow Docker's [Ubuntu install guide](https://docs.docker.com/engine/install/ubuntu/). Then let your user run Docker without `sudo`: `sudo usermod -aG docker $USER`, and log out and back in.

Check: `docker run --rm hello-world` prints a short welcome message. If it does, Docker works.

## 4. Find your device and test SSH
Find the IP address in the device's network settings, or in your router's list of connected devices. It can change, so check it each time. Then, from the terminal:

```
ssh root@<device-ip>
```

Answer `yes` to the fingerprint question. You should get a shell prompt on the device; type `exit` to leave. If this does not work, fix it first, because every install uses it.

## 5. Keep your files in the right place
On Windows with WSL, work inside your Ubuntu home folder (`cd ~`), not under `/mnt/c/`. Builds are much faster there and file permissions behave.

## When something fails
| You see | Usually means |
|---|---|
| `docker: permission denied` | Your user is not in the `docker` group yet. Run the `usermod` command above, then log out and back in. |
| `Cannot connect to the Docker daemon` | Docker is not running. Start Docker Desktop, or on Linux `sudo systemctl start docker`. |
| `ssh: connect to host ... timed out` | Wrong IP, the device is asleep, or it is on a different network. |
| `Permission denied` from `ssh` | Root SSH is not enabled on this unit. |
| A build stops with an error about its self-check | Your OS file or your tools differ from what the plugin was built against, and the build refuses to make an unverified plugin. Check the file name and version on the plugin's card. |

## Next
- **Install a downloaded plugin:** [Install](install.html).
- **Build one that has no download:** [Plugins you build yourself](install.html#plugins-you-build-yourself).
- **Build your own plugin from an engine:** [Build](build.html).
