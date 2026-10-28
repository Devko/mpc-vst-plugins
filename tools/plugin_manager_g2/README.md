# OpenMPC Plugin Manager G2

A plugin manager for Akai MPC / Force standalone devices that runs **inside MPC as a plugin** (native skin, Q-Links,
nothing takes over the screen) and is designed **Gen2-first** (MPC Live III and kin, aarch64, MPC OS 3.9.1 and 3.10),
while keeping Gen1 (armv7) working.

It starts as a fork of poloq's [mpc-vst-manager](https://github.com/poloq-instruments/mpc-vst-manager) (MIT, pinned at
`f01948b`, 1.2.0) and folds in the learnings of `sd88me/mpc-vst-plugins`, the open issues and PRs on poloq's repo, and a
review of Eurikon's [plugin-manager-usb-for-open-mpc](https://github.com/Eurikon/plugin-manager-usb-for-open-mpc) (MIT).

**Status: design only (2026-10-27).** Nothing here has run on a device yet; the code is poloq's, unmodified. Read
[DESIGN.md](DESIGN.md) first, then [NOTICE.md](NOTICE.md) for who wrote what and what still needs permission.

The upstream README and testing guide are kept as `docs/UPSTREAM_README.md` and `docs/UPSTREAM_TESTING.md`.
Licence: MIT (see `LICENSE`; poloq's notice is kept).
