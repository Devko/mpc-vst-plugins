# Design: an "Advanced" patches tab in the installer app (proposal, nothing built yet)

Status 2026-10-03: proposal. Verified facts go in `NOTES.md`; this file says what we would build and what is still unknown.

## Why
Some community work is not a plugin: it changes the device itself. Today that is `tools/mpc_patch` (16-pad drum layout, patches Akai's
`/usr/bin/MPC`, checked on MPC OS 3.9.1.2) and, if the author shares it, issue #150's "ForceHD exec" patch (makes one folder on the Force
SSD executable so plugins can load from it; the SSD is `noexec`, NOTES 2026-10-03). People run these by hand over SSH. The installer app
already has the SSH session, the backups and the "stop MPC once" logic, so it can run them with the safety rails the scripts already have.

## What it must not become
A plugin install is additive (files plus one settings entry). A patch rewrites Akai's program or the mounts and survives reboots. So:
- its own tab, collapsed behind a warning, off the plugin list and out of the batch install; nothing runs at connect time except `status`;
- never applied by default, never as part of an update, never without the user's click and a typed confirmation;
- one patch at a time, with what it changes, what it backs up and how to undo it shown first.

## Shape
1. **Manifest** `catalog/patches.json` (checked by a script like `catalog_check.py`; nothing hand-edited on the site). Per patch: `id`, `title`,
   `summary`, `author`, `license`, `script` (URL in this repo or the author's, pinned to a commit), `sha256`, `supports` (exact firmware
   checksum or version list), `modifies` (`/usr/bin/MPC`, `fstab`, ...), `reversible`, `restarts_mpc`, `docs`.
2. **The script stays the unit.** The app downloads it, checks the sha256, copies it to the device's `/tmp` and runs `status`, `install`,
   `uninstall`. The patch logic is not reimplemented in Go, so the manual route and the app route stay the same code.
3. **Contract each script must meet** (a `patch_check.py` would test it):
   - `status` changes nothing and prints `key=value` lines (`state=stock|patched|old-patch|unsupported`, `checksum=`, `backup=`) next to the human text;
   - `install --yes-i-understand` (name open) skips the typed prompt, because the app shows the same warning and takes the typed word itself;
     today `mpc-drum-pad-patch.sh` reads the word from `/dev/tty` and falls back to stdin, so piping `PATCH` would already work, but an explicit flag is clearer;
   - exact-match gate on the firmware (checksum), refusal otherwise, full backup before the first write, checked result, automatic restore on failure;
   - `uninstall` that works even if the app is gone;
   - exit status 0 only when the device ended in the state asked for.
4. **App flow:** Advanced tab, warning, list from the manifest with the device's `status` per patch (supported / applied / unsupported firmware),
   a detail view (what it does, what it changes, backup location), Apply and Undo behind a typed confirmation, the script's output streamed like an install.
   MPC is stopped and started by the script or by the app, never twice.
5. **Staged rollout:** (a) docs only: the tab lists patches with copy-paste commands, no Run; (b) read-only `status` per patch; (c) Apply and Undo.
   Stop at (b) until a patch has been applied from the app on a real device.

## Open questions
- **The ForceHD patch is unreviewed.** We have the issue text only: it reportedly makes `/media/ForceHD/vst` executable and leaves the rest of the
  SSD `noexec`, persistently, on a Force Gen1, MPC OS 3.9.1. Before it is listed: the script, its licence, what it edits (fstab, a bind mount, a service),
  how it survives a firmware update, and how to undo it. Note our layout puts the `.so` inside a `Synths` folder (skin and plugin together), so a patch that
  only frees one `vst` folder also needs the installer to know about that path; it is a different layout from today's.
- **Firmware drift:** every MPC OS update breaks a binary patch. The manifest's `supports` list is what makes the app refuse instead of guess.
- **Support load:** "my Force will not start" lands on us. The backup and `uninstall` path must be tested on a device before stage (c), and the README must say how to restore by hand.
- **Rules for authors:** nothing of Akai's in a script (only changed bytes and checksums, as in `tools/mpc_patch`); a licence; a `status` and an `uninstall`.
- **Device facts to check:** whether the app can run an interactive script over a plain `exec` session (no tty) on a Force; whether two patches can touch the same file.
