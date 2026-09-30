#!/bin/sh
# Browser test of the installer page against a stand-in Force (sshd plus shims for uname/systemctl/pidof) inside the html_art image:
# a full install of the catalog's Acid (real download, old installer) and a package with the current installer, then checks.
#   cd tools/desktop
#   docker run --rm -v "$PWD":/src -v /tmp/o:/out -w /src golang:1.26 sh -c 'CGO_ENABLED=0 go build -o /out/mpc-installer .'
#   cp ui_test/ui_test.py ui_test/run_ui.sh /tmp/o/ ; cp <a release zip built with the current release.py> /tmp/o/fake-1.4.0.zip
#   cp <Acid-x.y.z-mpc-armv7.zip> /tmp/o/acid/   (or edit ui_test.py)   ; docker build -q -t mpc-vst-html-art ../html_art
#   docker run --rm -v /tmp/o:/out -w /out mpc-vst-html-art sh /out/run_ui.sh
# a stand-in Force inside the test container: sshd + shims for the few device-only commands
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null && apt-get install -y -qq openssh-server >/dev/null
mkdir -p /run/sshd /media/az01-internal/Settings/MPC /sdcard/Synths
echo '<?xml version="1.0" encoding="UTF-8"?>
<PROPERTIES>
  <VALUE name="SynthContentLocations" val="/sdcard/Synths"/>
</PROPERTIES>' > /media/az01-internal/Settings/MPC/MPC.settings
mkdir -p "/sdcard/Synths/other - VST - Existing"
cat > /usr/local/bin/uname <<'X'
#!/bin/sh
[ "$1" = "-m" ] && { echo armv7l; exit 0; }
exec /usr/bin/uname "$@"
X
printf '#!/bin/sh\necho "$1 $2" >> /tmp/systemctl.log\n' > /usr/local/bin/systemctl
printf '#!/bin/sh\nexit 1\n' > /usr/local/bin/pidof
chmod +x /usr/local/bin/uname /usr/local/bin/systemctl /usr/local/bin/pidof
echo 'root:secret' | chpasswd
printf 'PermitRootLogin yes\nPasswordAuthentication yes\nUsePAM no\n' >> /etc/ssh/sshd_config
/usr/sbin/sshd
sleep 1
python3 /out/ui_test.py
