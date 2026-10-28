package main

// The "easy" USB stick: instead of building a stick from the user's own firmware (stick.go), download the
// community plugin manager's prebuilt universal stick (Eurikon/plugin-manager-usb-for-open-mpc, MIT) and unpack it
// onto the chosen drive. One bundle carries the MPC OS 3.9.1 autorun route and the OS 3.10 controller helper, and
// picks the Gen1 or Gen2 runtime by `uname -m` on the device, so the installer needs to know neither the OS version
// nor the generation. No firmware is read here.
//
// The stick runs as root on the device, so the release is pinned by SHA-256 and never "latest". To move to a new
// release, bump the three constants below after reading its changelog and testing it on a device.

import (
	"archive/zip"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path"
	"path/filepath"
	"strings"
	"time"
)

const (
	easyStickVersion = "v1.2.1" // stable; 1.2.1 fixes Gen2 installs when the SSD has no Synths folder (follows MPC's Content Download Drive); beta.2 device-tested on a Live III, v1.2.1 retest pending (2026-10-28)
	easyStickMaxSize = 16 << 20        // the zip is ~1.8 MB; refuse anything wildly larger
)

// easyStickSHA256 is a var, like the URL, so tests can pin a fixture instead.
var easyStickSHA256 = "c05199ae06111d4377f2e0e2c8fe3a127a10f8fe4f34cb9e2d5ae75f4a282b9f"

// easyStickURL is a var so tests can point it at a local server.
var easyStickURL = "https://github.com/Eurikon/plugin-manager-usb-for-open-mpc/releases/download/" +
	easyStickVersion + "/plugin-manager-usb-" + easyStickVersion + ".zip"

// fetchEasyStick downloads the pinned zip and checks its hash before returning it.
func fetchEasyStick() ([]byte, error) {
	c := &http.Client{Timeout: 2 * time.Minute}
	resp, err := c.Get(easyStickURL)
	if err != nil {
		return nil, fmt.Errorf("couldn't download the plugin manager stick: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("couldn't download the plugin manager stick: HTTP %d", resp.StatusCode)
	}
	data, err := io.ReadAll(io.LimitReader(resp.Body, easyStickMaxSize+1))
	if err != nil {
		return nil, err
	}
	if len(data) > easyStickMaxSize {
		return nil, errors.New("the plugin manager download is larger than expected; refusing it")
	}
	if sum := sha256.Sum256(data); hex.EncodeToString(sum[:]) != easyStickSHA256 {
		return nil, errors.New("the plugin manager download doesn't match the checksum this installer expects; refusing it")
	}
	return data, nil
}

// WriteEasyStick unpacks the zip onto out, which must be missing or empty (a drive's own housekeeping aside), the
// same rule as BuildStick. Entries that would land outside out are refused.
func WriteEasyStick(out string, data []byte) error {
	if st, err := os.Stat(out); err == nil {
		if !st.IsDir() {
			return fmt.Errorf("%s already exists and is not a folder", out)
		}
		des, err := os.ReadDir(out)
		if err != nil {
			return err
		}
		for _, d := range des {
			if !isHousekeeping(d.Name()) {
				return fmt.Errorf("%s is not empty; pick an empty folder (or an empty, freshly formatted USB stick)", out)
			}
		}
	}
	zr, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return err
	}
	// Validate every name before writing anything, so a bad zip leaves the drive untouched.
	for _, f := range zr.File {
		name := path.Clean(f.Name)
		if name == "." || strings.HasPrefix(name, "/") || name == ".." || strings.HasPrefix(name, "../") ||
			strings.Contains(name, `\`) || strings.Contains(name, ":") {
			return fmt.Errorf("unsafe path in the plugin manager zip: %q", f.Name)
		}
	}
	if err := os.MkdirAll(out, 0755); err != nil {
		return err
	}
	for _, f := range zr.File {
		dst := filepath.Join(out, filepath.FromSlash(path.Clean(f.Name)))
		if f.FileInfo().IsDir() {
			if err := os.MkdirAll(dst, 0755); err != nil {
				return err
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(dst), 0755); err != nil {
			return err
		}
		rc, err := f.Open()
		if err != nil {
			return err
		}
		w, err := os.Create(dst)
		if err == nil {
			_, err = io.Copy(w, rc)
			if cerr := w.Close(); err == nil {
				err = cerr
			}
		}
		rc.Close()
		if err != nil {
			return err
		}
	}
	for _, need := range []string{"autorun/autorun.json", "autorun/autorun.check", "autorun/open.sh", ".mpc-manager-id"} {
		if _, err := os.Stat(filepath.Join(out, filepath.FromSlash(need))); err != nil {
			return fmt.Errorf("the plugin manager zip is missing %s", need)
		}
	}
	return nil
}
