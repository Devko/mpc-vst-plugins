package main

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/binary"
	"io"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"testing"

	"golang.org/x/crypto/ssh"
)

// fakeDevice is a tiny SSH server that runs every command with the local sh. Shim commands stand in for the device's
// uname, id, systemctl and pidof, and record what the app asked for, so the whole install path runs without hardware.
type fakeDevice struct {
	t      *testing.T
	addr   string
	dir    string // sandbox: tmp, Synths, settings and the shims live here
	shims  string
	logMu  sync.Mutex
	mpcLog string // systemctl calls, one per line
}

func newFakeDevice(t *testing.T) *fakeDevice {
	t.Helper()
	dir := t.TempDir()
	fd := &fakeDevice{t: t, dir: dir, shims: filepath.Join(dir, "shims"), mpcLog: filepath.Join(dir, "mpc.log")}
	os.MkdirAll(fd.shims, 0o755)
	os.MkdirAll(filepath.Join(dir, "tmp"), 0o755)
	os.MkdirAll(filepath.Join(dir, "Synths"), 0o755)
	os.MkdirAll(filepath.Join(dir, "Settings", "MPC"), 0o755)
	os.WriteFile(filepath.Join(dir, "Settings", "MPC", "MPC.settings"), []byte("<PROPERTIES/>"), 0o644)
	shim := func(name, body string) {
		os.WriteFile(filepath.Join(fd.shims, name), []byte("#!/bin/sh\n"+body+"\n"), 0o755)
	}
	shim("uname", "echo armv7l")
	shim("id", "echo 0")
	shim("pidof", "exit 1")
	shim("systemctl", `echo "$1 $2" >> `+fd.mpcLog)

	_, priv, _ := ed25519.GenerateKey(rand.Reader)
	signer, _ := ssh.NewSignerFromKey(priv)
	conf := &ssh.ServerConfig{PasswordCallback: func(c ssh.ConnMetadata, pw []byte) (*ssh.Permissions, error) {
		if string(pw) == "secret" {
			return nil, nil
		}
		return nil, io.ErrUnexpectedEOF
	}}
	conf.AddHostKey(signer)
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { ln.Close() })
	fd.addr = ln.Addr().String()
	go func() {
		for {
			c, err := ln.Accept()
			if err != nil {
				return
			}
			go fd.serve(c, conf)
		}
	}()
	return fd
}

func (fd *fakeDevice) cfg() Config {
	_, port, _ := net.SplitHostPort(fd.addr)
	return Config{Port: port, User: "root", RemoteTmp: filepath.Join(fd.dir, "tmp"), SynthsDir: filepath.Join(fd.dir, "Synths"),
		SettingsGlob: filepath.Join(fd.dir, "Settings", "*", "MPC.settings")}
}

func (fd *fakeDevice) calls() []string {
	b, _ := os.ReadFile(fd.mpcLog)
	var out []string
	for _, l := range strings.Split(string(b), "\n") {
		if l = strings.TrimSpace(l); l != "" {
			out = append(out, l) // "stop acvs", "start acvs"
		}
	}
	return out
}

func (fd *fakeDevice) serve(nc net.Conn, conf *ssh.ServerConfig) {
	_, chans, reqs, err := ssh.NewServerConn(nc, conf)
	if err != nil {
		return
	}
	go ssh.DiscardRequests(reqs)
	for nch := range chans {
		if nch.ChannelType() != "session" {
			nch.Reject(ssh.UnknownChannelType, "no")
			continue
		}
		ch, creqs, _ := nch.Accept()
		go func() {
			defer ch.Close()
			for r := range creqs {
				if r.Type != "exec" {
					r.Reply(false, nil)
					continue
				}
				n := binary.BigEndian.Uint32(r.Payload)
				cmd := string(r.Payload[4 : 4+n])
				r.Reply(true, nil)
				c := exec.Command("sh", "-c", cmd)
				c.Env = append(os.Environ(), "PATH="+fd.shims+":"+os.Getenv("PATH"))
				c.Stdin, c.Stdout, c.Stderr = ch, ch, ch.Stderr()
				code := 0
				if err := c.Run(); err != nil {
					if ee, ok := err.(*exec.ExitError); ok {
						code = ee.ExitCode()
					} else {
						code = 255
					}
				}
				ch.SendRequest("exit-status", false, ssh.Marshal(struct{ C uint32 }{uint32(code)}))
				return
			}
		}()
	}
}

func itoa(i int) string { return strconv.Itoa(i) }
