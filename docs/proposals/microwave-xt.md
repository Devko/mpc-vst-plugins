# Proposal: a Microwave II/XT-style wavetable instrument for MPC (2026-09-30)

Status: proposal, nothing built yet. Author's inputs: the Microwave 2/XT *Controller Number Assignment* (OS 2.09)
and *System Exclusive Specification* (OS 2.16) documents, plus the projects listed under Sources.

## 1. Why the ROM emulators don't run, and what that changes

Xenia (Microwave II/XT) and Vavra (microQ) come from gearmulator. They run the original firmware on emulated chips:
a 68k-family microcontroller plus one DSP56300-family DSP for the XT (three with the voice expansion). gearmulator's
README says it supports **64-bit x86 and aarch64 only; 32-bit architectures are not supported**. The dsp56300 core has
JIT back ends for x64 and aarch64 only (`jitops_*_x64.cpp`, `jitops_*_aarch64.cpp`), so on a Gen1 MPC (RK3288,
32-bit armhf `MPC` binary, `docs/NOTES.md` "CPU layout") only the interpreter could run, and an interpreted
56300 at full speed is out of reach on a 1.8 GHz Cortex-A17. Surge XT has the same limit ("will not build on 32-bit
Raspberry Pi systems").

So there are two routes. They don't exclude each other:

| | Track A: native "XT-alike" engine (recommended) | Track B: run the real XT DSP program |
|---|---|---|
| What | New C engine that implements the XT's voice architecture and reads XT data (waves, tables, sound dumps) | Static recompile of the XT's DSP firmware (as Monomodule/Machinedrum do for their DSPs) plus a 68k host emulator |
| Accuracy | As close as calibration gets it (section 4) | Bit-exact if it runs |
| CPU | Fits, by design (section 5) | Unknown. Needs a spike: 56300 static recompile + 68k interpreter on armv7 |
| Distribution | Normal release, user supplies the data files (JV-880 precedent) | `build-yourself` (firmware-derived), like Monomodule |
| Gen2 note | Same | If a Gen2 MPC runs a 64-bit `MPC` (unverified: `tools/probe_device.sh`), gearmulator's aarch64 JIT becomes an option there |

The rest of this document is Track A. Track B stays a time-boxed spike (section 8), because if the existing
recompiler handles a 56300 program, the result would be exact.

## 2. The core idea: adopt the XT's own data model, don't design a "similar" synth

Everything that makes presets portable is already specified in the attached SysEx document. The engine uses it as
its native format:

- **The patch is the 256-byte SDATA block** (SysEx spec 3.1). The engine's state *is* that block. A `.syx` single
  dump (`F0 3E 0E dev 10 BB NN <256 bytes> xsum F7`) or an all-sounds dump (256 x 256 bytes, A001..B128) loads with
  no conversion. That is how "port the presets" gets to 100% at the data level: the only remaining error is in the DSP.
- **VST parameters = the non-reserved SDATA fields, in SDATA index order**, with the XT's raw ranges (0..127,
  enums, the -64..+63 offsets). The order is stable by construction (PORTING.md section 2: append only). Display strings
  follow the XT's own value texts (gearmulator's `parameterDescriptions_xt.json`, GPL-3.0, lists them all).
- **MIDI CCs follow the controller table** (CC 5 glide time, 14-21 envelopes, 24-31 LFOs, 33-48 osc/mix, 50-62
  filters/amp, 70-83 wave, 85-93 free env, 102-111 arp, 112-118 LFO extras). External controllers and MPC
  automation then behave like on the hardware.
- **SNDP parameter-change SysEx** (`F0 3E 0E dev 20 LL HH PP XX F7`, index = HH*128+PP) is accepted as well, so the
  plugin can be driven by existing XT editors if MPC ever forwards SysEx (untested).
- **Plugin state (chunk) = SDATA + a small header** (bank/program name, effect state). A "save .syx" action writes
  the current sound as a real single dump, so sounds move between the plugin, Xenia and real hardware.

Wave data follows the XT layout too: a wave is 128 signed 8-bit samples, stored as 64 (the second half is
`w[64+n] = -w[63-n]`); a wavetable is 64 slots referring to wave numbers; slots 61-63 are always triangle, square and
saw; empty slots are filled by the firmware with a "spectral interpolation" of their neighbours. gearmulator's
constants: 506 ROM waves, 250 RAM waves (1000-1249), 128 tables (96-127 user), tables 28-51 and 64-95 (0-based) are
algorithmic (computed, no control table).

### Errata to handle in the parser (the SysEx document contradicts itself)
- Osc semitone: SDATA says 52..76, the CC table says 56..76. Accept the full range, clamp to +-12.
- Wave start phase: "3-257 degree" in SDATA is a typo for 3..357.
- SDATA 188-191 are labelled "Modifier 3" again; they are Modifier 4.
- Mod destinations: range says 0..33, but the list has 36 entries (34 FM Amount, 35 F1 Extra). Use 0..35.
- Arp range: SDATA 1..10, CC 103 0..9 (CC value + 1).
- MULP: the ID table says 20h, the format says 21h. GLBR: 04h in the format, 14h in the ID list.
- Effect type: 0..35 on the XT, "subject to change", no list in the document. Take the list from the manual or the
  oracle (section 4).

## 3. Engine architecture (C, `wrapper/engine.h`, no JUCE)

```
 MIDI/CC/SysEx -> voice alloc (poly/mono, normal/dual/unison, glide, arp)
                     |
 control tick ------>+  (control rate to be measured; SDATA 54 "Time Quantization" hints at it)
   Filter env ADSR, Amp env ADSR, Wave env (8 stages, key-on/key-off loops),
   Free env (3 stages + release, bipolar), LFO1/2 (6 shapes, delay, sync, symmetry,
   humanize, phase), 4 modifiers (+ - * / xor or and S&H ramp switch abs min max lag
   ctlfilter diff) + modifier delay, 16-slot matrix (32 sources x 36 destinations)
                     |
 per voice, per sample at 40 kHz:
   Osc1/Osc2: wave position -> table slot -> mip level -> 8-bit wave read
              (sync, link, Osc1 FM, keytrack, pitchbend scale, 3 fixed tri/sqr/saw)
   Mixer: wave1, wave2, ring mod, noise, (external) -> "Clipping: saturate/overflow"
   Filter 1: 24LP 12LP 24BP 12BP 12HP sin-shaper>12LP 12LP>shaper dual-LP/BP FM-LP S&H-LP
   Filter 2: 6 dB LP/HP
   Amp: volume, velocity, keytrack, pan, pan keytrack
                     |
 mix -> effects (chorus + XT effect types) -> 40 kHz -> 44.1 kHz resampler -> int16 out
```

Design decisions:

- **Run the core at 40 kHz internally.** gearmulator's XT hardware class runs at 40 kHz (`wLib::Hardware(40000)`). Where
  the hardware aliases, it aliases at 40 kHz; running at the native rate keeps that character and lets the calibration
  compare against the oracle sample for sample. One polyphase 40 to 44.1 kHz resampler (160:147) on the summed stereo
  output costs almost nothing next to the voices.
- **No band-limited oscillator.** The DSP keeps each of a part's 64 waves as a mip pyramid in Y memory
  (128+64+32+...+1 = 256 words per wave, `xtWavePreview.cpp`) and reads from it. The XT's sound *is* stepped 8-bit
  waves with its own aliasing. Surge's windowed-sinc wavetable oscillator and FigBug's Wavetable would sound too clean
  and cost more. The "Aliasing" (off, 1-5), "Accuracy" and "Clipping" parameters are the knobs that choose how dirty.
- **Discrete wave stepping, no crossfade.** Movement comes from the 64 precomputed slots, not from morphing between
  them. That makes the oscillator cheap: a table lookup per sample.
- **Float for control, fixed-point where the hardware is.** The DSP56300 has 24-bit data and 56-bit accumulators. Where
  overflow/wrap is audible (mixer "overflow" mode, resonant filters), model it with integer or explicit wrap, not float
  saturation.
- **NEON across voices.** Process 4 voices per NEON lane group for the filters and mixer (Cortex-A17 has NEON/VFPv4).
- **One plugin instance = one XT part.** MPC tracks already provide multitimbrality, so Multi mode (MDATA/IDATA) is
  only parsed for importing sounds, not emulated.
- **Arp runs inside the instrument.** MPC ignores plugin MIDI out (NOTES.md), but the XT's arp only drives its own voices.

## 4. Getting it to sound as close as possible: the oracle rig

The accuracy work is measurement, not guessing. gearmulator's `xtLib` (GPL-3.0) runs fine on an x64 dev machine, so it
serves as a **firmware oracle**: an offline test tool that loads the user's own XT ROM or OS update, is driven by
SysEx and MIDI, and exposes the emulated DSP's memory and audio. It is a dev tool only. It never ships and never goes
to the device. (Someone else's Faust project proposes the same "firmware oracle" approach for the XT; see Sources.)

What the oracle gives us, in order of value:

1. **Exact wave data, including interpolated and algorithmic tables.** Select table N on part 0 (SNDP param 25), let
   the firmware build it, then read DSP Y memory at the wave area (`0x20000 + part*64*256`, 256 words per wave, per
   `xtWavePreview.cpp`). That gives all 64 slots *after* the firmware's spectral interpolation and for the
   algorithmic tables, plus the mip levels the DSP actually uses. We never have to reverse-engineer the interpolation.
   Confirm first that the firmware writes the table there on a table change. Output: one file per table, 64 x 256
   int8. Keep the WAVR/WCTR (sysex spec 2.31/2.41) dump of raw waves and control tables too, for user wavetables.
2. **The host-to-DSP control stream.** Log the HDI08 words the 68k sends the DSP while playing test patches. If per-voice
   pitch, wave position, cutoff coefficients and envelope levels travel that way (to be confirmed), the synth splits in
   two halves that can be matched separately: the control math (envelope curves, LFO shapes and rates, keytrack,
   cutoff to coefficient) against the logged stream, and the audio DSP against audio given the same stream.
3. **Filter responses through the external input.** The XT mixes an external input (SDATA 51, XT only). Feed sweeps,
   impulses and noise through each Filter 1 type at a grid of cutoff/resonance/keytrack values; fit our filters to the
   measured magnitude and phase responses and to the level-dependent (nonlinear) behaviour.
4. **Oscillator and mixer tests** with the filter open: every table at several pitches, sync, ring mod, FM, the
   aliasing/quantize/clipping settings.
5. **Preset-level regression.** Render every factory sound at several notes and velocities through both engines at
   40 kHz, and score each pair: multi-resolution STFT distance, RMS envelope contour error, pitch error. The scores
   run as a CI job and gate changes, so accuracy only goes up. Blind A/B listening for the sounds with the worst scores.

Order of work (bottom-up, so each layer is verified on a known input): waves, then oscillator pitch/phase/sync/FM,
then mixer and clipping, then filters, then envelopes and LFOs, then the matrix and modifiers, then effects.

## 5. CPU budget (to be confirmed with `tools/bench.sh` on a device)

A 128-frame block at 44.1 kHz is 2902 µs; PASS in BENCH.md is p99 <= 15%, about 435 µs. At 40 kHz a block is about
116 internal samples, so 10 voices (the XT's polyphony) is about 1160 voice-samples per block, about 375 ns or about 675
cycles each at 1.8 GHz. A table read, a mixer, a 2- or 4-pole filter and a 1-pole filter take on the order of 100 cycles,
and the modulation runs at control rate. 10 voices should PASS with room to spare. 30 voices (expanded XT) is a
likely WARN, so make polyphony a parameter. The first device bench happens as soon as one voice plays (Phase 1),
not at the end.

## 6. How the listed projects fit

| Project | Licence | Use |
|---|---|---|
| gearmulator (Xenia) | GPL-3.0 | The oracle (section 4). Reference for data layouts (`xtRomWaves`, `xtWavePreview`, `xtMidiTypes`, `xtState`) and value texts (`parameterDescriptions_xt.json`). Not runnable on 32-bit armhf. |
| Surge XT | GPL-3.0 | Not as a whole: no 32-bit ARM build. `sst-filters` is header-only GPL-3.0 (SSE intrinsics; on ARM via simde, which maps to NEON). Its LP/BP/HP and S&H filters are starting points before calibration. `sst-effects` for chorus/delay until the XT effects are modelled. |
| schwung-tablor | BSD-3-Clause | A Schwung module, so it builds for MPC today through `adapters/schwung` with no code change. Use it on day one to prove the build, skin, bench and install path, and borrow voice handling and file loading. Its DSP is FigBug-Wavetable-style, not XT, so it gets replaced. |
| FigBug Wavetable | BSD-3-Clause, needs JUCE | Not usable in the C wrapper. Useful for UI and modulation ideas only. |
| Waldorf legacy page | Waldorf's terms | Source of the manuals, OS updates and sound banks the user downloads. Could not be fetched from this environment, so its exact terms still need reading. |

## 7. Data, licensing and naming

- **Waldorf data never goes in the repo or the release zip**: no ROM waves, wavetables or factory banks. That includes
  the wave collections circulating online (archive.org, waveeditonline): their redistribution status is unclear.
- The plugin loads **user-supplied files at runtime**, like the JV-880 port loads user ROMs: (a) a wave/table file
  made by the extractor (the oracle tool from section 4, run by the user against their own OS update or ROM, or against
  their own hardware using WAVR/WCTR requests), and (b) `.syx` banks. File picking follows PORTING.md section 1
  (scan off the audio thread, sort, save by name). With no data present it still plays: built-in tri/square/saw and
  generated additive tables so it isn't silent.
- That keeps the plugin a normal published release (GPL-3.0 if any gearmulator or sst code is used), catalog-conformant,
  with `requires` naming the user files. The extractor may embed gearmulator; it is a desktop tool, not part of the
  plugin.
- Name: avoid Waldorf/Microwave trademarks in the product name. Describe compatibility plainly ("loads Microwave
  II/XT sound dumps").

## 8. Plan

| Phase | Deliverable | Gate |
|---|---|---|
| 0 | Oracle tool (x64, gearmulator `xtLib`), wave/table extractor, test-patch set; Tablor built through `adapters/schwung` and benched on a device | Extracted tables match Xenia's wave editor; pipeline proven on device |
| 1 | One voice: SDATA state, `.syx` loader, oscillators from extracted tables, mixer, amp env, 40 to 44.1 kHz resampler | Offline test (`tools/test_port.sh`), first device bench |
| 2 | Filter 1 (10 types) + Filter 2, filter env; external-input calibration | Filter response error within agreed tolerance |
| 3 | Wave env with loops, free env, LFOs, modifiers, 16-slot matrix, glide, allocation/unison, 10 voices | Preset regression scores on the factory banks |
| 4 | Parameters (SDATA order), CC map, skin pages (Osc, Wave, Mix, Filter, Env, LFO, Mod, FX, Arp) and Q-Link banks, preset browser, "save .syx" | Device test per PORTING.md section 4 |
| 5 | Effects (chorus + XT types), arp | Scores; bench PASS |
| 6 | Release: `release.py --repo --license`, `catalog_check.py --catalog`, `tested.json`, catalog entry | CLAUDE.md ground rules |

**Track B spike** (time-boxed, can run alongside Phase 0): (1) check whether the recompiler used for Monomodule and
Machinedrum targets the 56300 instruction set; (2) in the oracle, measure how much of the XT DSP's cycle budget
the firmware uses (the share of time in its idle loop); (3) estimate the 68k host cost under an interpreter on armv7.
Continue only if the numbers point at under 35% of one core (BENCH.md WARN). Otherwise Track A alone.

The port lives in its own repository (`PORTING.md`: "A port can live in its own repo"). This file moves there when it
starts.

## Open questions
- Control rate and envelope curve shapes (answered by oracle item 2).
- Whether every algorithmic table is static, or some depend on per-voice state (oracle item 1 shows it).
- The XT effect list and its parameters (manual + oracle).
- Whether MPC delivers SysEx and CCs to a VST2 instrument (device test, record in NOTES.md).
- Gen2 `MPC` binary word size (`tools/probe_device.sh`), which decides whether gearmulator itself is an option there.

## Sources
- gearmulator: <https://github.com/dsp56300/gearmulator> (README platform list; `source/waldi/xt/xtLib/xtRomWaves.cpp`,
  `xtWavePreview.cpp`, `xtMidiTypes.h`, `xtRomLoader.cpp`, `xtHardware.cpp`; `xtJucePlugin/weData.cpp`,
  `parameterDescriptions_xt.json`)
- dsp56300 emulator: <https://github.com/dsp56300/dsp56300> (JIT back ends in `source/dsp56kEmu/`)
- Surge XT: <https://github.com/surge-synthesizer/surge>; sst-filters: <https://github.com/surge-synthesizer/sst-filters>
- schwung-tablor: <https://github.com/athousanddetails/schwung-tablor>
- FigBug Wavetable: <https://github.com/FigBug/Wavetable>
- Faust "firmware oracle" plan for the MW II/XT: <https://github.com/curlcomplex/Faust-expr/issues/101>
- Not reachable from the research environment (to read by hand): <https://theusualsuspects.io/downloads/xenia>,
  <https://waldorfmusic.com/legacy-microwave-ii-xt-xtk-series/>
