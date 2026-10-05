#!/bin/sh
set -eu
# Removes the patch: stops the timer, takes the executable mount off (a normal umount, never forced or lazy), deletes the files this
# patch installed. Plugins, skins, MPC.settings and fstab are not touched. Original: timomacquis, 0.1.3 (adapted: the drive and folder
# come from the config; FVE_PREFIX, tests only, redirects the paths).
P=${FVE_PREFIX:-}
if [ -z "$P" ]; then PATH=/usr/sbin:/usr/bin:/sbin:/bin; export PATH; fi   # fixed PATH on the device; tests (FVE_PREFIX) bring their own shims
[ "$(id -u)" = 0 ] || { echo 'Root required'; exit 1; }
[ -f "$P/etc/force-vst-exec/VERSION" ] || { echo 'Patch not installed'; exit 0; }
[ "$(cat "$P/etc/force-vst-exec/VERSION")" = 0.2.0 ] || { echo 'Different version: use its matching uninstaller'; exit 1; }
FORCEHD_ROOT=; EXEC_DIR=
. "$P/etc/force-vst-exec/config"
mpc_service() {
 if systemctl cat acvs >/dev/null 2>&1; then echo acvs
 elif systemctl cat inmusic-mpc >/dev/null 2>&1; then echo inmusic-mpc
 else echo acvs; fi
}
for pid in $(pidof MPC || true); do
 if grep -qF "$FORCEHD_ROOT/$EXEC_DIR/" "/proc/$pid/maps"; then
  echo "MPC is using a plugin from $FORCEHD_ROOT/$EXEC_DIR. Save the project, stop MPC, then retry the removal."
  echo "Command after saving: systemctl stop $(mpc_service)"
  exit 1
 fi
done
# Retain the existing enabled state if revert fails.
ENABLED=0
systemctl is-enabled --quiet force-vst-exec.timer && ENABLED=1 || true
systemctl disable --now force-vst-exec.timer
systemctl stop force-vst-exec.service
if ! /bin/sh "$P/etc/force-vst-exec/force-vst-exec.sh" revert; then
 [ "$ENABLED" = 0 ] || systemctl enable --now force-vst-exec.timer
 echo 'Uninstallation cancelled: mount busy or unmanaged'
 exit 1
fi
/bin/sh "$P/etc/force-vst-exec/root-bootstrap.sh" remove
systemctl stop force-vst-exec-bootstrap.service 2>/dev/null || true
rm -f "$P/etc/systemd/system/force-vst-exec.service" "$P/etc/systemd/system/force-vst-exec.timer"
rm -f "$P/etc/force-vst-exec/force-vst-exec.sh" "$P/etc/force-vst-exec/config" "$P/etc/force-vst-exec/VERSION" "$P/etc/force-vst-exec/uninstall.sh" "$P/etc/force-vst-exec/bootstrap.sh" "$P/etc/force-vst-exec/root-bootstrap.sh"
rmdir "$P/etc/force-vst-exec" 2>/dev/null || true
systemctl daemon-reload
rm -f "${FORCE_VST_EXEC_STATE:-$P/run/force-vst-exec}/lock" "${FORCE_VST_EXEC_STATE:-$P/run/force-vst-exec}/last-status"
rmdir "${FORCE_VST_EXEC_STATE:-$P/run/force-vst-exec}" 2>/dev/null || true
sync
echo 'Patch removed. The drive itself stays mounted as it was.'
echo 'Backups remain in /data/mpc-vst-plugins/backups.'
echo "If MPC was stopped manually, restart it: systemctl start $(mpc_service)"
echo 'Plugins on the drive stay where they are, but they will not load again until the patch is back (the drive is noexec).'
