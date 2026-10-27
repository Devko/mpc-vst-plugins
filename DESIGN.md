# OpenMPC Plugin Manager G2: design

Status 2026-10-27. Evidence tags: **device** = seen on hardware (Live III, MPC 3.10.0.49, unless stated), **offline** = read
from source or images, **inference** = my reasoning, not checked. Facts about this repo's own code were read from
`src/manager.c` at `f01948b`; the manager was not run.

## 1. Goal and non-goals

Goal: browse, install, update and remove catalog plugins and addins from the MPC screen, on Gen2 first.
- **Right target, never silent.** Install only where MPC will give the plugin its skin, and say on screen when that is not possible.
- **Gen2 native.** aarch64 build, `/data/Settings`, `/nvme/Synths`, `pluginList-arm-64bit`, a restart that really restarts.
- **Safe.** A failed install leaves `MPC.settings` and the plugin folder as they were.
- **Coexists with poloq's manager** (own uid and id, own work folder), so both can be installed while this one matures.

Non-goals: no root route (that is the stick and the desktop app's job); no edits to `SynthContentLocations` (decided with
the user 2026-10-27: too much risk for a few edge cases); no takeover of MPC's screen.

## 2. What we start from

poloq's manager is one C file (`src/manager.c`, 1658 lines) that builds as a VST2 plugin through `mpc-vst-plugins`'
wrapper. It reads the device on open (`probe_device()`), fetches the catalog, queues installs, writes `apply.sh` and runs it
under `systemd-run` so stopping MPC does not kill it, then restarts MPC. Its test harness (`tests/run.sh`) builds the
file against fake devices (`tests/devices/*.sh`) in a `gcc:12` container.

### 2.1 Open work on poloq's repo (no reply from poloq for weeks) and what we do with it

| # | What | Disposition |
|---|---|---|
| PR #12 (ours) | Gen2: `/nvme`, `/data/Settings`, `pluginList-arm-64bit`, restart on aarch64, aarch64 build target | **Take as is** (5 files, +39/-16; includes `tests/devices/gen2.sh`). Branch `ref/pr12-gen2` |
| #9 | exFAT SD rejected; silent fall back to an unwritable internal path; state file in the wrong place | **Fix in section 5**: gate on writable + exec, not on filesystem name; report the reason; state file beside the settings |
| #10 | only the internal drive is offered | **Fix in section 5**: let the user pick among usable `SynthContentLocations` |
| #6 + PR #7 | catalog capped at 64 entries (`MAXPKG`); live catalog has 111+ | **Take the idea** (growable list, cached view). Author's licence unstated: re-implement or ask (see NOTICE.md) |
| #5 (and closed #4) | a plugin whose zip ships no `mpc-plugin.json` drops out of INSTALLED after an update | **Fix in section 6**: write the manifest from the catalog entry after a successful apply |
| PR #8 | reworked screen: category tabs, scrolling list, info overlay, search, thumbnails (+8658/-1045, 135 files) | **Later (M5)**. Read for ideas; ask FullPace before copying; credit as Padbangers |
| #3 | MPC OS 2.x support | **Out of scope for G2**. Plugins load on 2.x but skins do not draw (docs/OS2_SKINS.md in mpc-vst-plugins) |
| #13 (ours, 2026-10-27) | say on screen when the target is not a content location | **Implemented by design in section 5** |
| #11 (ours) | rebuild against the wrapper's Q-Link/automation fix | **Free**: we build against the current wrapper |

## 3. Gen2 facts the design relies on

- **Settings** at `/data/Settings/<profile>/MPC.settings`; Gen1 has `/media/az01-internal/Settings/...` (device, both).
- **Plugin list key** `pluginList-arm-64bit` on Gen2, `pluginList-arm` on Gen1 (device).
- **Storage on a Live III** (device): `/synths` (nvme0n1p1, exfat, **read-only**), `/nvme` (nvme0n1p2, exfat, **rw**, user drive),
  USB `/media/<label>` (vfat, **noexec** on the unit tested 2026-10-22). The only writable, exec-capable place is `/nvme/Synths`.
  Plugins loaded from there draw their skin once `/nvme/Synths` is a content location.
- **A fresh Gen2 may not list `/nvme/Synths`** (offline: stock data dump of 2026-10-09 lists `/synths/Synths`, `/synths/Expansions`,
  `/usr/share/Akai/Content/Synths` and two removable drives). On such a unit the writable drive is not a content location, so every install lands without a skin. Who added `/nvme/Synths` on the tested unit is unknown.
- **Skin rule** (device, MPC 3.10.0.49): the plugin loads from its `file=` path anywhere; its skin is found only through a listed
  `Synths` folder. A trailing `/` on the entry works, and MPC keeps it on save. Untested: a space in the path, a leaf not
  named `Synths`, a clean-quit rewrite of the file.
- **Restart**: `systemctl stop|start acvs` (or `inmusic-mpc` on Hakai firmware). On 3.10 the unit still runs from the
  3.9.1 rootfs with the 3.10 `MPC` bind-mounted over it (device); the restart is unchanged.
- **Root filesystem is dm-verity read-only on Gen2** (device): nothing outside `/data`, `/nvme`, `/media` can be written. This
  is why the addins folder stays `/data/mpc-addins`.
- **No filtering by filesystem type was found in MPC** (offline, strings only: no `noexec`, `/proc/mounts` or `exfat` strings in
  the four `MPC` binaries). `noexec` still blocks loading a `.so` (kernel behaviour).
- **exFAT has no symlinks or exec bits** (inference): `install.sh` restores exec bits and symlinks from a `MODES` file. A package
  with symlinks may fail on exFAT. Needs a device test before we promise exFAT for everything.

## 4. Review of Eurikon's installer

Read: README, DEVELOPER_FAQ, CHANGELOG, file list (`src/main.cpp`, `backend.cpp`, `sd_install.cpp`, `manager_update.cpp`,
`startup/hotplug.cpp`, `startup/bootstrap.sh`, `tools/deploy.cpp`). Source files not read line by line yet.

**What it is:** a standalone SDL2 application, not a plugin. It is launched from a USB stick or SD card (autorun on 3.9.1; a
"helper" imported into MPC Documents plus Shift+Menu on 3.10), stops MPC, takes the screen, and returns to MPC after five idle minutes.
Its own tests are on a Live II (Gen1) only; our Live III run of 2026-10-27 found 3.9.1 works and 3.10 does not open (docs/NOTES.md, mpc-vst-plugins).

| Idea | Verdict for G2 | Why |
|---|---|---|
| Runs outside MPC (own screen, own process) | **Not adopted** | Takes over the screen, auto-exits, restarts MPC on return (30 s+ on Gen1), and its launch routes are firmware-specific. A plugin stays in the user's project flow. |
| Writes installs through package scripts with `-y -n -t <target>` and `MPC_SETTINGS` set | **Same as poloq** | Both use the package's own `install.sh`. We keep that contract. |
| Requires a settings file, a writable+exec target **and a registered content location** before it lets you install | **Adopt** | It refuses where poloq falls back silently: exactly the skin problem of section 5. |
| `tools/deploy.cpp`: snapshot payload, registry and settings; verify; restore on failure | **Adopt the idea** | Its own FAQ says the default bundle lacks it and script failure can leave partial changes. We add a settings snapshot + restore around the apply. See 7. |
| `plugin-history.json` (schema 1: id, version, installed flag, timestamp), atomic save (temp, fsync, rename), refuses to overwrite invalid data | **Adopt** | History survives a plugin being removed or a zip losing its manifest (#5). Small and independent of the UI. |
| Per-source `local-plugins/` folder (install a zip you put on the drive) | **Adopt later (M4)** | Offline installs; checksum shown, not trusted. |
| Hotplug watcher for USB/SD | **Skip** | Needed for a launcher on removable media, not for a plugin in MPC. |
| Manager self-update from the screen | **Adopt later (M4)** | poloq's manager updates through the catalog like any plugin; keep that, check the hash. |
| 5 min idle exit, restart on crash | **Skip** | Plugin lifetime is MPC's. |
| Install target fixed to `/sdcard/Expansions` | **Not adopted** | Expansions is Akai's content tree; we use `Synths` folders (section 5). Our skin evidence is for `Synths`. |

## 5. Install-target policy (the core fix; closes #9, #10, #13)

Candidates are the **`SynthContentLocations` entries** read from `MPC.settings`, nothing else.
1. Normalise each entry: strip CR and trailing `/` (MPC accepts the slash, device).
2. A candidate is **usable** when it, or its parent if it does not exist yet, is on a mount that is `rw` and not `noexec` and has
   at least 64 MB free. **No filesystem-name whitelist** (poloq's `bad_fs()` accepts only ext3/ext4/f2fs/btrfs, which is why the
   Gen2 `/nvme` exFAT drive and #9's exFAT card are rejected). Keep the leaf rule (`.../Synths`) until the leaf test is done.
3. Show every candidate with its reason when unusable ("read-only", "noexec", "factory content", "under 64 MB").
4. **Pick**: internal storage first (`/nvme`, `/sdcard`, `/media/az01-internal`), then others; the user can change it from the
   screen (closes #10); an existing install of a plugin updates in place.
5. **No usable listed location: stop, do not fall back.** Show "Can't install: none of MPC's content locations is writable"
   with the list and reasons, and write the same to `device.txt`. (poloq falls back to its own folder, an installed plugin's
   folder, or a hard-coded default; none of those is checked against the list, and the note goes only to a log file.)
   An **Advanced** switch may allow an unlisted folder, with the standing banner "no skin until this folder is added to
   MPC's content locations".
6. The state file (`.pluginmgr-installed`) sits next to the settings profile, not under the target, so a read-only or
   removed target cannot break it.

## 6. Catalog and the installed list (closes #6, #5)

- Growable arrays; no `MAXPKG`. Cached filtered view rebuilt on refresh, tab or filter change.
- Choose the zip by device architecture from the catalog's `assets.aarch64` / `assets.armv7`; a Gen2-only plugin
  (`gen2_only`) is hidden or marked on Gen1; a plugin with no build for this device is greyed, never queued. Catalog contract: `mpc-vst-plugins` docs/CATALOG_SPEC.md.
- After a successful apply write `mpc-plugin.json` into the plugin folder from the catalog entry (installed version, catalog
  format), so a zip without one still shows as INSTALLED (#5; the version string must match a catalog release).
- Keep `plugin-history.json` as a second source for "was installed".

## 7. Apply and rollback

1. Queue on screen; **APPLY** asks, then writes `apply.sh` (poloq behaviour, kept).
2. `systemd-run` (or the cgroup-v2 fallback) detaches from MPC, stops MPC, **snapshots** `MPC.settings` and each touched plugin folder to a work folder on the same drive.
3. Runs each package's `install.sh -y -n -t <target>` or `uninstall.sh`, checks the exit status and that the plugin-list entry exists (`file=` and `uid`).
4. On any failure: restore the settings and the folders, mark the item failed with the log tail on screen, start MPC.
5. On success: refresh the manifest and history, start MPC.
The restart path must not be compiled out on aarch64 (poloq's `#ifdef __arm__` turned the apply into a dry run: PR #12 fixes it; keep a test that fails if the aarch64 build takes the dry-run branch).

## 8. Testing

Offline, in the existing harness plus new fake devices (each built from a real `MPC.settings` layout, CRLF included):

| Fake device | Case |
|---|---|
| `gen2` (from PR #12) | Live III 3.9.1: no `/sdcard`, `/data/Settings`, `/nvme` exFAT rw |
| `gen2-310` | `/nvme/Synths` **not** listed; listed read-only `/synths/Synths`; USB noexec. Expect "Can't install", no fallback |
| `gen2-nvme-listed` | `/nvme/Synths/` with a trailing slash, CRLF. Expect target `/nvme/Synths` |
| `exfat-sd` (#9) | exFAT card rw+exec listed; internal path unwritable. Expect the card |
| `two-targets` (#10) | two usable locations; pick changes the target |
| `catalog-111` (#6) | fixture with 120 entries; all shown |
| `no-manifest-zip` (#5) | zip without `mpc-plugin.json`; still INSTALLED after update |
| `apply-fails` | package script exits 1 mid-way; settings and folder restored |
| `aarch64-restart` | aarch64 build must call `systemctl`, not the dry run |

Real device, Live III on 3.9.1 and 3.10 (the unit is the user's live setup: ask before every restart, back up first):
adapt `docs/UPSTREAM_TESTING.md`, plus: unlisted target shows the banner; a listed one draws the skin; a failed install rolls back.

## 9. Plan

| Step | Content | Exit test |
|---|---|---|
| M0 | Baseline: run `tests/run.sh` on poloq's code as is | **done 2026-10-27 (offline): exit 0**, 4 fake devices + addin flow, host test under ASan; needs network, Docker `gcc:12` and the `mpc-vst-plugins` checkout next to this folder |
| M1 | Merge PR #12; rename (id, uid, work folder); build aarch64 | gen2 fake device passes; uid differs from poloq's `PlMg` |
| M2 | Section 5 target policy + fake devices | all section 8 rows for locations pass |
| M3 | Section 6 (catalog size, manifest) and section 7 (rollback) | `catalog-111`, `no-manifest-zip`, `apply-fails` pass |
| M4 | History file, local zips, self-update | offline pass |
| M5 | Screen rework (ask FullPace first) | device run |
| Device | Live III 3.9.1, then 3.10; Gen1 (Force) regression | table in docs/ with dates |

## 10. Open questions and risks

- **Does `systemd-run` detach work on Gen2 3.10?** poloq's code has an "untested" cgroup fallback; only Gen1 was run. Device test needed before M3 is called done.
- **Leaf name**: must the location end in `Synths`? Untested on a device.
- **How is the manager itself installed on Gen2 3.10?** There is no autorun route; use `mpc-vst-plugins`' desktop app or Eurikon's helper (does not open on 3.10 yet).
- **Licence of PR #7/#8 code**: ask before copying (NOTICE.md).
- **Name**: "MPC" is Akai's mark; the project already uses it descriptively. Keep "OpenMPC" wording off logos and the plugin's skin art.
- **exFAT and symlinks** (section 3): test a package that ships a symlink on `/nvme`.
- **Catalog id**: poloq's manager is catalog id `plugin-manager`; this one needs its own id and uid, and a catalog entry only after a device pass.
