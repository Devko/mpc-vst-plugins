---
title: Build a plugin
nav: Build
order: 20
summary: How to turn a sound engine or an app into a native MPC OS plugin with its own screen page, using this repo's tools.
---

An MPC OS plugin is a small Linux library (`.so`) for the device's ARM processor, plus a **skin**: a folder that describes the plugin's page on the MPC screen. This repo's tools build both from one small description file, and they test the result on your PC before it goes anywhere near a device.

## What you need
New to this? [Get set up](setup.html) walks through the tools below step by step.

- A checkout of [mpc-vst-plugins](https://github.com/sd88me/mpc-vst-plugins). A plugin lives in its own repo next to it, and points at it with the `MPC_VST` variable.
- Python 3 and Docker. The build runs the ARM compiler (`arm32v7/gcc:12`) under emulation, and the skin and preview tools run in containers.
- An engine to wrap: a synth or effect core in C or C++, or an engine from Schwung (it plugs in through an adapter).
- A device to try it on. Nothing here needs one until the very last step.

## 1. Pick your kind of plugin
- **A block-rendering engine** (a synth or effect core): the common case. You provide `mpc_engine()` and the tools do the rest.
- **An engine with extra glue** (network keys, dynamic lists): write a plugin-specific wrapper. Crate Digger is the example.
- **A MIDI generator** (sequencer, arpeggiator): MPC ignores a plugin's MIDI output, so it opens its own MIDI port.
- **An app** (network, files, helper programs): allowed. Keep the audio thread from ever waiting.

The [porting checklist](https://github.com/sd88me/mpc-vst-plugins/blob/main/docs/PORTING.md) covers each case in detail.

## 2. Describe the plugin
Put a `vst.json` next to the engine:

```
{
  "name": "My Synth", "vendor": "me", "uid": "MySy", "version": 1000,
  "so": "my_synth.so",
  "params": "params.json",
  "layout": "layout.conf",
  "build": {"root": "..", "sources": ["src/engine.c"], "cflags": ["-Isrc"], "libs": ["-lm"]}
}
```

`params.json` lists the parameters in the order MPC will number them. **The order is a promise**: saved projects store values by position, so once a plugin ships you only append. `uid` and `so` also never change between versions.

The engine's side of the contract is small: create, destroy, MIDI in, set and get a parameter by key, and render 128 stereo frames at 44.1 kHz. See `wrapper/engine.h`.

## 3. Build it
```
MPC_VST=/path/to/mpc-vst-plugins
"$MPC_VST/tools/build_port.sh" vst/vst.json
```

This generates the parameter table, the skin, the plugin-list entry and the ARM `.so`, all in `build/` next to `vst.json`. Without a `layout` it makes an automatic first page, which is a good starting point.

Two rules that save a crash: vendor any third-party engine source into your repo (do not fetch it at build time), and never hardcode `/sdcard/...` in the engine. Set `"defines": {"MODULE_SUBDIR": "\"engine\""}` and the plugin finds its own data folder next to the `.so`, wherever it was installed.

## 4. Design the page
The page is a description that MPC draws: knobs, faders, switches, buttons, option lists, pop-ups, live text and your own artwork. Edit it in the **Skin Studio**, a page editor in your browser (double-click `SkinStudio.command`, `SkinStudio.bat` or `SkinStudio.sh` in the repo), then preview every page as an image:

```
"$MPC_VST/tools/studio.py" preview "build/skin/<vendor> - VST - <Name>/Plugin Skins" -o page_%d.png
```

Live text can use two fonts, Titillium Web and Roboto. Anything else has to be baked into the artwork. The [Skin Studio guide](https://github.com/sd88me/mpc-vst-plugins/blob/main/docs/SKIN_STUDIO.md) has the details.

## 5. Test on your PC
```
"$MPC_VST/tools/test_port.sh" vst/vst.json
```

This builds the wrapper and your engine for your PC under a memory checker, and plays it: two instances, every parameter, options, notes into audio, and saving and restoring state. It must print `PASSED`.

## 6. Try it on a device
Only now does a device come in. Follow the [release workflow](workflow.html): measure CPU, install with the real installer, and test. The reference ports, Maze Voice, JV-880 and Crate Digger, are good to copy from.

## Where to read more
- [Porting checklist](https://github.com/sd88me/mpc-vst-plugins/blob/main/docs/PORTING.md)
- [What has been verified on real hardware](https://github.com/sd88me/mpc-vst-plugins/blob/main/docs/NOTES.md)
- [Skin Studio](https://github.com/sd88me/mpc-vst-plugins/blob/main/docs/SKIN_STUDIO.md)
- [CPU check](https://github.com/sd88me/mpc-vst-plugins/blob/main/docs/BENCH.md)
