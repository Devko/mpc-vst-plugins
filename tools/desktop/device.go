package main

import (
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"golang.org/x/crypto/ssh"
)

// Config holds the few things that differ on a real device and in tests.
type Config struct {
	Port         string // ssh port, "22"
	User         string // "root"
	RemoteTmp    string // where packages are unpacked on the device, "/tmp"
	SynthsDir    string // "/sdcard/Synths"
	SettingsGlob string // where MPC.settings is
}

func defaultConfig() Config {
	return Config{Port: "22", User: "root", RemoteTmp: "/tmp", SynthsDir: "/sdcard/Synths", SettingsGlob: "/media/az01-internal/Settings/*/MPC.settings"}
}

type DeviceInfo struct {
	Host        string            `json:"host"`
	Arch        string            `json:"arch"`
	UID         string            `json:"uid"`
	Fingerprint string            `json:"fingerprint"`
	Synths      string            `json:"synths"`
	Settings    string            `json:"settings"`
	TmpFreeKB   int64             `json:"tmpFreeKB"`
	Tar         bool              `json:"tar"`
	Systemctl   bool              `json:"systemctl"`
	Installed   []string          `json:"installed"`
	Store       map[string]string `json:"store"` // plugin id -> version recorded by this app or mpc-store.sh
	Plugins     []DevPlugin       `json:"-"`
}

// DevPlugin is a plugin folder on the device (one with a plugin-meta.xml).
type DevPlugin struct {
	Folder string `json:"folder"`
	UID    string `json:"uid"`
	Name   string `json:"name"`
}

type Device struct {
	client *ssh.Client
	cfg    Config
	Info   DeviceInfo
}

var hostRe = regexp.MustCompile(`^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$`)

func validHost(h string) bool { return len(h) <= 253 && hostRe.MatchString(h) }

// authMethods: the password when one was given, then the user's default private keys that need no passphrase.
func authMethods(password string) []ssh.AuthMethod {
	var m []ssh.AuthMethod
	if password != "" {
		m = append(m, ssh.Password(password), ssh.KeyboardInteractive(func(_, _ string, qs []string, _ []bool) ([]string, error) {
			a := make([]string, len(qs))
			for i := range a {
				a[i] = password
			}
			return a, nil
		}))
	}
	if home, err := os.UserHomeDir(); err == nil {
		var signers []ssh.Signer
		for _, n := range []string{"id_ed25519", "id_ecdsa", "id_rsa"} {
			b, err := os.ReadFile(filepath.Join(home, ".ssh", n))
			if err != nil {
				continue
			}
			if s, err := ssh.ParsePrivateKey(b); err == nil {
				signers = append(signers, s)
			}
		}
		if len(signers) > 0 {
			m = append(m, ssh.PublicKeys(signers...))
		}
	}
	return m
}

// Dial connects and reads what the app needs to know about the device. The host key is not remembered between runs: the
// fingerprint is shown so it can be compared, and nothing about the device is written to disk.
func Dial(host, password string, cfg Config) (*Device, error) {
	if !validHost(host) {
		return nil, errors.New("use the address as numbers and dots (or a host name)")
	}
	auth := authMethods(password)
	if len(auth) == 0 {
		return nil, errors.New("enter the device's password (no SSH key was found on this computer)")
	}
	var fp string
	conf := &ssh.ClientConfig{
		User: cfg.User, Auth: auth, Timeout: 10 * time.Second,
		HostKeyCallback: func(_ string, _ net.Addr, key ssh.PublicKey) error { fp = ssh.FingerprintSHA256(key); return nil },
	}
	c, err := ssh.Dial("tcp", net.JoinHostPort(host, cfg.Port), conf)
	if err != nil {
		return nil, fmt.Errorf("cannot log in to %s: %w", host, err)
	}
	d := &Device{client: c, cfg: cfg}
	if err := d.readInfo(host, fp); err != nil {
		c.Close()
		return nil, err
	}
	return d, nil
}

func (d *Device) Close() {
	if d.client != nil {
		d.client.Close()
	}
}

type lineWriter struct {
	mu   *sync.Mutex
	buf  []byte
	emit func(string)
}

func (w *lineWriter) Write(p []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.buf = append(w.buf, p...)
	for {
		i := strings.IndexAny(string(w.buf), "\n\r")
		if i < 0 {
			break
		}
		if line := strings.TrimRight(string(w.buf[:i]), "\r"); line != "" && w.emit != nil {
			w.emit(line)
		}
		w.buf = w.buf[i+1:]
	}
	return len(p), nil
}

func (w *lineWriter) flush() {
	w.mu.Lock()
	defer w.mu.Unlock()
	if len(w.buf) > 0 && w.emit != nil {
		w.emit(strings.TrimRight(string(w.buf), "\r\n"))
	}
	w.buf = nil
}

// Run executes cmd on the device; stdout and stderr lines go to onLine. It returns the exit status.
func (d *Device) Run(cmd string, stdin io.Reader, onLine func(string)) (int, error) {
	s, err := d.client.NewSession()
	if err != nil {
		return -1, err
	}
	defer s.Close()
	var mu sync.Mutex
	lw := &lineWriter{mu: &mu, emit: onLine}
	s.Stdout, s.Stderr = lw, lw
	if stdin != nil {
		s.Stdin = stdin
	}
	err = s.Run(cmd)
	lw.flush()
	var ee *ssh.ExitError
	if errors.As(err, &ee) {
		return ee.ExitStatus(), nil
	}
	if err != nil {
		return -1, err
	}
	return 0, nil
}

func (d *Device) readInfo(host, fp string) error {
	script := fmt.Sprintf(`S=%s
echo "arch=$(uname -m)"; echo "uid=$(id -u)"; echo "synths=$S"
echo "settings=$(ls %s 2>/dev/null | head -n 1)"
echo "tmpfree=$(df -k %s 2>/dev/null | awk 'NR==2 {print $4}')"
command -v tar >/dev/null 2>&1 && echo tar=1
command -v systemctl >/dev/null 2>&1 && echo systemctl=1
ls -1 "$S" 2>/dev/null | grep ' - VST - ' | sed 's/^/installed=/'
[ -f "$S/.mpc-store" ] && sed 's/^/store=/' "$S/.mpc-store"
for d in "$S"/*/; do
  f="${d}plugin-meta.xml"; [ -f "$f" ] || continue
  u=$(sed -n 's/.* uid="\([^"]*\)".*/\1/p' "$f" | head -n 1); n=$(sed -n 's/.* name="\([^"]*\)".*/\1/p' "$f" | head -n 1)
  printf 'plug=%%s\t%%s\t%%s\n' "$(basename "$d")" "$u" "$n"
done
true`, shQuote(d.cfg.SynthsDir), d.cfg.SettingsGlob, shQuote(d.cfg.RemoteTmp))
	info := DeviceInfo{Host: host, Fingerprint: fp, Synths: d.cfg.SynthsDir, Installed: []string{}, Store: map[string]string{}}
	var lines []string
	var mu sync.Mutex
	code, err := d.Run(script, nil, func(l string) { mu.Lock(); lines = append(lines, l); mu.Unlock() })
	if err != nil || code != 0 {
		return fmt.Errorf("the device did not answer a basic command (%v, status %d)", err, code)
	}
	for _, l := range lines {
		k, v, ok := strings.Cut(l, "=")
		if !ok {
			continue
		}
		switch k {
		case "arch":
			info.Arch = v
		case "uid":
			info.UID = v
		case "settings":
			info.Settings = v
		case "tmpfree":
			info.TmpFreeKB, _ = strconv.ParseInt(strings.TrimSpace(v), 10, 64)
		case "tar":
			info.Tar = true
		case "systemctl":
			info.Systemctl = true
		case "installed":
			info.Installed = append(info.Installed, v)
		case "plug":
			if f := strings.Split(v, "\t"); len(f) >= 3 {
				info.Plugins = append(info.Plugins, DevPlugin{Folder: f[0], UID: f[1], Name: f[2]})
			}
		case "store":
			if f := strings.Split(v, "\t"); len(f) >= 2 && f[0] != "" {
				info.Store[f[0]] = f[1]
			}
		}
	}
	d.Info = info
	return nil
}

// problems lists why an install must not go ahead on this device (empty when it is fine).
func (i DeviceInfo) problems() []string {
	var p []string
	if i.UID != "0" {
		p = append(p, "you are not logged in as root")
	}
	if !strings.HasPrefix(i.Arch, "armv7") {
		p = append(p, "this is "+i.Arch+", not a 32-bit ARM MPC OS device")
	}
	if !i.Tar {
		p = append(p, "the device has no tar")
	}
	if !i.Systemctl {
		p = append(p, "the device has no systemctl (is this an MPC OS device?)")
	}
	if i.Settings == "" {
		p = append(p, "MPC.settings was not found")
	}
	return p
}

// shQuote wraps s in single quotes for a POSIX shell.
func shQuote(s string) string { return "'" + strings.ReplaceAll(s, "'", `'\''`) + "'" }
