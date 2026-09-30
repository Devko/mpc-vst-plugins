# mpc-installer: install MPC OS plugins from your computer

A small local app for people who would rather not type SSH commands. It starts a web page **on your own computer**, opens it in your
browser, and from there you connect to your device, tick plugins from the catalog and/or drop release zips (including the ones you
built yourself, like Monomodule and Machinedrum), and press Install. It is one file (about 8 MB) with nothing to set up, for Windows,
macOS and Linux.

It uses the same release zips and the same `install.sh` as every other route (`docs/RELEASING.md`), so there is still one install
path. What it adds: a friendly page, one copy of each zip over SSH (as a tar stream, so executable bits and symlinks survive), and
one MPC stop and start around the whole batch when the installers allow it.

## What it does, in order

1. **Connect:** SSH as root with your password or a key in `~/.ssh` (no passphrase). It reads the device (32-bit ARM? `tar`?
   `systemctl`? where is `MPC.settings`?) and refuses one that is not an MPC OS device. The device's key fingerprint is shown; nothing
   about the device is saved.
2. **Choose:** the catalog's newest stable release of every downloadable plugin, plus any zips you drop in. A zip is checked before
   it is accepted (one folder, the manifest, no paths that leave it, links that stay inside, no more than 2 GB unpacked).
3. **Install:** catalog downloads are checked against the catalog's sha256 first (a mismatch installs nothing). Then, after you confirm
   (save your project: MPC restarts), it copies every package to a private folder in the device's `/tmp`, stops MPC once, runs each
   package's `install.sh -y -n`, starts MPC once and removes the copies. An installer that predates `-n` runs first with its own
   restart. MPC is started again even if something fails, and nothing after the failing plugin is installed.

What was installed is written to `<Synths>/.mpc-store` on the device, so `mpc-store.sh update` (the on-device script) knows about it.

## Safety

- The page is served on `127.0.0.1` only, behind a random token in the link the app prints. Every request must carry the token, the
  right `Host` and (for posts) the right `Origin`, and the page has a strict Content-Security-Policy, so other computers and other web
  pages cannot drive it.
- The password is used for that one connection and never written down. There is no telemetry.
- Only https downloads are accepted, and only what the catalog lists.

## Run it

Download the archive for your system from the releases, unpack it and start `mpc-installer` (double-click it, or run it in a
terminal). It prints a link and opens it in your browser. `--no-browser` only prints the link; `--port`, `--catalog` and `--version`
exist too.

The first run is unsigned, so the system warns you once:

- **Windows:** "Windows protected your PC": click *More info*, then *Run anyway*.
- **macOS:** it will not open on a double-click. Right-click the file, choose *Open*, then *Open* again (or run
  `xattr -d com.apple.quarantine mpc-installer` in a terminal).
- **Linux:** `chmod +x mpc-installer` if needed.

## Build and test

Go 1.26 or newer, one dependency (`golang.org/x/crypto`):

```
cd tools/desktop
go test -race ./...                       # includes a fake SSH device that runs the whole install in-process
CGO_ENABLED=0 go build -trimpath -ldflags="-s -w -X main.version=1.0.0" -o mpc-installer .
```

A browser test of the page against a stand-in device (sshd in a container) lives in `ui_test/`; see its header. The release workflow
is `.github/workflows/desktop.yml` (Actions, "Desktop installer", Run workflow: builds Windows, macOS and Linux binaries into a
draft release; install it, try it, then publish).
