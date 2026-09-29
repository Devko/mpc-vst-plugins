# Catalog specification (schema 1)

Three formats: the **release manifest** inside every zip (written by `tools/release.py`), the **registry entry**
(written once by a plugin's author), and the generated **catalog.json**. Design and roadmap: `docs/CATALOG.md`.
Validate a zip with `tools/catalog_check.py <zip> [--catalog]`; the offline test is `python3 tools/test_catalog.py`.

## Release zip
`<Name>-<X.Y.Z>-mpc-armv7.zip`, one top folder `<Name>-<X.Y.Z>/` (layout in `docs/RELEASING.md`), containing
`mpc-plugin.json`, `plugin.xml`, `install.sh`, `uninstall.sh`, `plugin_list.awk`, `INSTALL.md`, `SHA256SUMS` and
`payload/` and, unless built with `--no-portable`, `portable/<skin>/` (below). Every file except `SHA256SUMS` is listed
there. No absolute or `..` paths, no symlinks leaving the package.

### Portable layout (`portable/<skin>/`)
The same plugin as **one self-contained folder** for installers that copy a folder into the device's `Synths` content
folder and register it from a file inside it (received from Locrian's builds, 2026-09-29, not yet run on a device):
```
<Vendor> - VST - <Name>/
  version.xml          identical to our skin's version.xml (<plugincontent>, identifier <vendor>.vst.<name>, version 1.0.0.0)
  plugin-meta.xml      the plugin-list <PLUGIN .../> element, with file="%payload-path%/<Vendor> - VST - <Name>/<so>"
  <name>.so            the plugin, inside the skin folder
  Plugin Skins/        the skin
  <extras>             any engine data, next to the .so (relative paths like `engine/` for MODULE_SUBDIR)
```
The zip also carries `install-portable.sh` / `uninstall-portable.sh` (preview; `sh install-portable.sh [-y] [-t <synths-dir>]`,
default target `/sdcard/Synths`). The installer copies the folder in, registers it with `%payload-path%` replaced by the
Synths folder, replaces an older entry of the same `uid` (so an old `/sdcard/vst/...` install is not duplicated), removes the
old `.so`, and keeps the paths in the manifest's `user_data` (folders where the user puts ROMs or kits, given to `release.py`
with `--user-data`) across upgrades and uninstalls. It is tested against a copy of `MPC.settings` (`python3 tools/test_catalog.py`),
not yet on a device (`docs/PORTABLE_TEST.md`).

`plugin-meta.xml` is exactly our `plugin.xml` except `file=`: `%payload-path%` is a placeholder the installer replaces with
the directory it copied the folder into (for example `/media/<card>/Synths`). The folder name in `file=` must equal the
folder's own name. Because the `.so` can end up anywhere, engines must find their data next to it
(`wrapper/plugin_dir.h`, `MODULE_SUBDIR`), never at a fixed `/sdcard/...` path.

## `mpc-plugin.json`
| field | meaning |
|---|---|
| `schema` | `1` |
| `id` | catalog id, `[a-z0-9]+(-[a-z0-9]+)*`; never changes |
| `name`, `manufacturer` | as in the plugin list entry |
| `version` | `X.Y.Z`; X bumps when parameter indices change |
| `param_compat` | equals X: a bump means saved projects change |
| `kind` | `instrument` or `effect` |
| `uid` | VST uid (hex), same as `plugin.xml`; never changes |
| `so`, `so_dir` | library file name and the directory in the plugin-list entry |
| `skin`, `extras` | skin folder name; extra payload paths under `vst/` |
| `portable` | `portable/<skin>` when the zip has the portable layout, else null |
| `user_data` | list of folders inside the plugin folder that hold the user's own files; the portable installer keeps them |
| `arch` | ELF machine of the `.so`; the catalog accepts `armv7` only |
| `max_glibc` | highest `GLIBC_x.y` symbol version needed; the catalog limit is 2.36 |
| `about`, `requires` | one-line description; extra requirements |
| `source_repo`, `license` | `owner/name` on GitHub; SPDX id. **Required for the catalog** |
| `cpu` | `{p99_pct, max_pct, verdict}` from `tools/bench.sh -j`, or null |

## Validator rules (`catalog_check.py`)
Errors (exit 1): unsafe paths; missing required file; manifest missing a field or wrong schema; bad id/version;
`param_compat` != major; arch not armv7; GLIBC above 2.36; `plugin.xml` `file=`/`uid`/`name` disagree with the
manifest; `.so` not ELF; skin missing `version.xml` or `Plugin Skins/TUI.json`; a file missing from or wrong in
`SHA256SUMS`; a `portable` folder that is missing `version.xml`, `Plugin Skins/TUI.json`, `plugin-meta.xml`, the `.so` or an
extra, whose `.so` differs from `payload/vst/`, or whose `plugin-meta.xml` differs from `plugin.xml` in anything but
`file=%payload-path%/<skin>/<so>`; with `--catalog`, no `source_repo` or `license`; with `--expect-id/--expect-repo`, a registry mismatch.
Warnings (need a human look): `install.sh`/`uninstall.sh`/`plugin_list.awk` differ from the repo's current template
(regenerated from the manifest and compared), `max_glibc` not recorded.

## Registry entry: `plugins/<id>.json` (catalog repo)
```json
{ "id": "my-synth", "name": "My Synth", "author": "Someone", "repo": "someone/my-synth-vst",
  "kind": "instrument", "license": "MIT", "summary": "One line.",
  "style": "synth", "tags": ["poly"], "source_available": false,
  "screenshot": "optional URL or path", "asset_pattern": "*-mpc-armv7.zip" }
```
`style` (one slug) and `tags` (slugs) are optional and drive the site filters. `source_available: true` is required
when `license` is not on the open-source list; the site shows a "Restricted use" badge.
No version fields: they are read from the releases (or, for `build-yourself`, the git tags). `id` must equal the manifest `id`, `repo` the manifest
`source_repo`. Stable releases are GitHub releases that are not prereleases; prereleases form the beta channel.

### Build-yourself entries
For a plugin that cannot publish a zip because the build embeds the user's own firmware. Schema 1 is unchanged: the
fields below are additive and `distribution` defaults to `"release"`, so existing entries and readers are unaffected.
```json
{ "id": "monomodule", "name": "Monomodule One + FX", "author": "sd88me", "repo": "sd88me/mpc-vst-monomodule",
  "kind": "instrument", "license": "AGPL-3.0-only", "summary": "...",
  "distribution": "build-yourself",
  "requires_user_files": [ { "name": "Monomachine OS 1.32B .syx", "description": "Your own copy of the OS file." } ],
  "build": { "command": "release/release.sh <Monomachine OS 1.32B .syx> [-d <device-ip>]", "script": "release/release.sh",
             "docs_url": "https://github.com/sd88me/mpc-vst-monomodule/blob/{tag}/README.md#install", "needs": ["Docker"] },
  "components": [ { "id": "monomodule-one", "name": "Monomodule One", "kind": "instrument", "uid": "MnmO" },
                  { "id": "monomodule-fx", "name": "Monomodule FX", "kind": "effect", "uid": "MnmF" } ] }
```
| field | rules |
|---|---|
| `distribution` | `release` (default) or `build-yourself` |
| `license` | an open SPDX id from the list in `tools/catalog_build.py`; `source_available` is rejected |
| `requires_user_files` | required, non-empty: `{name, description}` each |
| `build.command` | required; shown verbatim and must contain `build.script` |
| `build.script` | required; a path inside the repo (no leading `/`, no `..`); a tag without it is not listed |
| `build.docs_url` | required, `https://`; `{tag}` is replaced by the shown version's tag (`HEAD` if none) |
| `build.needs` | optional list of strings (tools the build needs) |
| `components` | optional non-empty list of `{id, name, kind, uid?}`; ids are unique across the whole registry; `uid` is the four characters from `vst.json` |
| `asset_pattern` | not allowed |

`requires_user_files`, `build` and `components` are rejected on a `release` entry.

Versions are the repo's `vX.Y.Z` git tags (a leading `v` is optional; other tags are ignored). A tag is listed only if
`build.script` exists at it. An older tag without the script is skipped quietly (tags are never moved, so it could not
be fixed); only the newest tag missing it is reported. Builder checks and reports in `problems.json`: repo unreadable,
no valid tag, script missing at the newest tag, and (loudly, `LICENCE RISK`) a GitHub release with a `*-mpc-armv7.zip` asset. A tag without a root
`LICENSE`/`COPYING` file gets a version warning. There is no zip, so no `catalog_check.py`, sha256 or size.

## `catalog.json` (generated)
`{"schema": 1, "generated": <ISO time>, "plugins": [ <registry fields> + "versions": [ <record>, ... ], "latest",
"latest_beta", "downloads", "updated" ]}`, versions
newest first. A record is what `catalog_check.py --json` prints (`version`, `size`, `sha256` of the zip,
`param_compat`, `max_glibc`, `cpu`, `manifest`) plus `url`, `date`, `channel` (`stable`|`beta`), `notes`, `yanked`
and `tested` (`[{device, firmware, date}]`), added by the builder.

Every plugin also has `distribution`. For `build-yourself` plugins the record carries the entry's `requires_user_files`,
`build` and `components`, and each version is `{version, tag, date, channel: "stable", source_url, yanked, downloads: 0,
warnings, tested, notes: ""}`: no `url`, `size`, `sha256`, `param_compat` or `manifest`. Readers must treat those
keys as absent for such entries (an installer must skip them: there is nothing to download).

## Portable paths (for engines)
Engines locate their data next to the `.so` (`wrapper/plugin_dir.h`, `MODULE_SUBDIR`), never at a fixed `/sdcard`.
The installers currently still install to the directory in the entry's `file=` and skins to `/sdcard/Synths`.
