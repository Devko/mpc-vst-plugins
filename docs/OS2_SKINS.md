# MPC OS 2.x skins: findings, open questions and the experiment plan

Written 2026-10-04 so the work can be picked up later. The verified facts, with dates, are in [NOTES.md](NOTES.md) (section
"2026-10-03: MPC OS 2.15.1"); this file is the plan and the state of play. Stock Akai skin files are analysed offline
only and are never committed (see `CLAUDE.md`).

## Where we are

- Plugins **load** on MPC OS 2.15.1 (an MPC Live, first generation) when built for glibc 2.32 or less, and their Q-Links work.
- Our generated skins **did not draw** there: MPC's frame, an empty body, nothing in the log. Other 2.x users report the same.
- 2.x does read a skin from a plugin folder (a stock skin copied into the plugin's folder showed up), so the problem was
  inside our `TUI.json`.
- Every JSON object in a skin has a `version`. The stock skins on 2.15.1 use versions 1 to 3; ours wrote 3, 4 and 5.
- **Confirmed 2026-10-03:** Dexed's skin rewritten in the 2.15.1 shape draws on the 2.15.1 MPC Live, and the same file draws on a
  Force (3.x) and looks the same on both. Touch behaviour on 2.x was still being checked.

The 2.x shape (what `to_mpc2x` in `tools/shadow_skin.py` writes, PR #139, opt-in via `SHADOW_SKIN_MPC_OS=2`, not merged):

| Part of `TUI.json` | MPC OS 3.x shape (ours today) | MPC OS 2.15.1 shape |
|---|---|---|
| Tab | `version 3`, page named by `componentName`, plus `initialSize`, `scale` | `version 1`, page inline as `componentDefinition` |
| Page / widget definition | `version 4`, with `repeats` and `hideQLinkBounds` | `version 2`, without them |
| `Knob` data | `version 5`, with `invert`, `dragOrientation` | `version 1` (`knobType`, `filmStrip`, `numFrames`, `handleName`) |
| `Button` data | `version 2`, with `gestureBehaviour` | `version 1` |
| Same on both | `Image`, `Label`, `Focus` data; child `version 2`; `bounds` versions 1 and 2; `Q-Links.json` version 4 | |

What the Force's own stock skins (111 of them, read 2026-10-04) tell us: each component type has one data version per firmware
generation (Knob 5, Slider 4, Meter 3, Button 2); the fields we drop only ever hold one value (`gestureBehaviour` `Instant`,
`dragOrientation` `Vertical`, `invert` `False`, `repeats` 1, `hideQLinkBounds` `False`, tab `initialSize` `0 0 1280 628`,
`scale` 1.0), so dropping them most likely falls back to those defaults. The Force reads the older shapes too, so
**existing 3.x skins keep working on 3.x unchanged**; only 2.x users need the older shape.

## Decision still open (do not change the generator default yet)

The concern: changing the default shape could affect skins the community already built, and nobody should have to re-release.
Options, to be chosen after the experiment:

1. Keep the default; the 2.x ("compatible") shape stays opt-in.
2. **Install-time conversion:** the installer app reads the device's MPC OS version and rewrites a skin when installing to a
   2.x device, so existing releases work on 2.x with no re-release (a Go port of `to_mpc2x`, with the same tests).
3. Only authors who want 2.x support re-release.

Leaning towards 2, pending the experiment. A Discord post asking the community for input was drafted on 2026-10-04.

## Known gaps

- `to_mpc2x` only handles `Knob` (5 to 1) and `Button` (2 to 1). The Force has `Slider` (data 4) and `Meter` (data 3) as well.
  None of the six released skins (Dexed, JV-880, Acid, Maze Voice, Crate Digger, Monomodule) use them, but other authors' skins might.
  What 2.x does with a `Slider` is unknown. 2.15.1's 45 uses of version 3 may be `Meter`.
- What the dropped fields do on 3.x is inferred from Akai's skins only using one value each. Not tested by changing them.
- One 2.x unit (an MPC Live on 2.15.1). Other 2.x versions and models are untested.
- Only Dexed has been seen on a 2.x screen. The other skins convert cleanly on paper (nothing above version 2 remains).

## The experiment

**A. Compare the two firmware generations (reading only).** Ask a 2.x user for a tar of the stock skins and build the same
per-type version table the Force corpus gave:
```
cd /usr/share/Akai/Content/Synths
tar czf /tmp/stock_skins_2x.tgz */'Plugin Skins'/TUI.json */'Plugin Skins'/Q-Links.json
```
Compare per component type (Knob, Button, Slider, Meter, Image, Label, Focus, Decorator, Indicator and the data fields of each).
Then extend `to_mpc2x` for any type that differs (Slider first).

**B. Bisect what 2.x rejects.** Start from the compat skin that works and add back one 3.x element per variant (everything
else identical):

| Variant | Content |
|---|---|
| V0 | the normal 3.x skin (control) |
| V1 | the compat skin (known good on both) |
| V2 | V1 plus `Button` data version 2 with `gestureBehaviour` |
| V3 | V1 plus `Knob` data version 5 |
| V4 | V1 plus definition version 4 (`repeats`, `hideQLinkBounds`) |
| V5 | V1 plus tab version 3 (`componentName`, `initialSize`, `scale`) |
| V6 | V1 plus an unknown extra field on a version 2 object (does 2.x ignore unknown fields?) |

Ship them in one zip as `TUI.V0.json` to `TUI.V6.json` and have the 2.x tester swap one file at a time (`cp`), then add the plugin
to a new track and report drawn or blank. First find out whether re-adding the plugin picks up a changed `TUI.json` without an
MPC restart (try V0 against V1). Each variant is a normal release-style zip if dropped into the installer app (update
`SHA256SUMS`; `python3 tools/catalog_check.py <zip>` must say OK).

**C. Behaviour on the Force.** Install each variant and test buttons (do they respond and toggle as before), knob drags, Q-Links
and every tab. Do not put values Akai's skins never use into a skin on a live device.

How to rebuild a test zip from a release zip: read `Plugin Skins/TUI.json` from it, call `shadow_skin.to_mpc2x(obj)`, write
it back with the same file list and an updated `SHA256SUMS` line (the permission bits in the zip must be preserved).

## State of things (2026-10-04)

- PR #138 (docs: skin-format findings) is merged. PR #139 (`to_mpc2x`, opt-in) is open and must not be merged until a 2.x unit has
  confirmed touch behaviour; its unit tests (12 in `tools/test_shadow_skin.py`) pass offline.
- The main README and the nine plugin READMEs still say "Requires MPC OS 3.x; 2.x needs further development". Change them
  when a release carries a 2.x-capable skin, not before.
- The test Force has Dexed's converted `TUI.json` installed; the original is at `/sdcard/os2test-backup/TUI.json.os3` on that
  device (copy it back over `Plugin Skins/TUI.json` to restore). MPC restarted on its own within seconds of that file swap;
  the cause is unknown (no crash lines in the log), so do not swap skin files on a live unit without telling the owner.
- Awaiting: the 2.x user's stock-skin tar (A), and their touch, tab and preset checks of the converted Dexed skin.
- A social post asking for 2.x model and OS reports was published; a Discord post with the options above was drafted.

## Do not

- Change the generator's default shape or ask authors to re-release before the experiment says it is safe.
- Commit any stock Akai skin file (analysis copies live in a scratch folder and are deleted afterwards).
- Restart MPC on someone's device without asking first.
