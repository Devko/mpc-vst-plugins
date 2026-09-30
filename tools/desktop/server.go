package main

import (
	"crypto/subtle"
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

//go:embed web/index.html
var indexHTML []byte

// App is the local web server. It listens on 127.0.0.1 only and every request must carry the random token the app printed, so
// nothing else on the network, and no web page open in the browser, can drive it. Nothing about the device is written to disk.
type App struct {
	cfg        Config
	token      string
	hosts      map[string]bool // accepted Host headers
	catalogURL string
	work       string

	mu      sync.Mutex
	dev     *Device
	uploads map[string]*Package
	cat     []CatPlugin
	catAt   time.Time
	job     *Job
}

func NewApp(cfg Config, token, hostport, catalogURL, work string) *App {
	port := hostport[strings.LastIndex(hostport, ":")+1:]
	return &App{cfg: cfg, token: token, catalogURL: catalogURL, work: work, uploads: map[string]*Package{},
		hosts: map[string]bool{"127.0.0.1:" + port: true, "localhost:" + port: true}}
}

func (a *App) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/", a.index)
	mux.HandleFunc("/api/state", a.state)
	mux.HandleFunc("/api/connect", a.connect)
	mux.HandleFunc("/api/disconnect", a.disconnect)
	mux.HandleFunc("/api/catalog", a.catalog)
	mux.HandleFunc("/api/upload", a.upload)
	mux.HandleFunc("/api/discard", a.discard)
	mux.HandleFunc("/api/plan", a.plan)
	mux.HandleFunc("/api/install", a.install)
	mux.HandleFunc("/api/job", a.jobStatus)
	return a.guard(mux)
}

func (a *App) guard(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h := w.Header()
		h.Set("Cache-Control", "no-store")
		h.Set("X-Content-Type-Options", "nosniff")
		h.Set("Referrer-Policy", "no-referrer")
		h.Set("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'")
		if !a.hosts[r.Host] { // a page reaching us through a rebound DNS name has another Host
			http.Error(w, "unexpected host", http.StatusForbidden)
			return
		}
		if o := r.Header.Get("Origin"); o != "" && !a.hosts[strings.TrimPrefix(o, "http://")] {
			http.Error(w, "unexpected origin", http.StatusForbidden)
			return
		}
		got := r.Header.Get("X-MPC-Token")
		if r.URL.Path == "/" {
			got = r.URL.Query().Get("t")
		}
		if subtle.ConstantTimeCompare([]byte(got), []byte(a.token)) != 1 {
			http.Error(w, "open the link the app printed (it contains the access token)", http.StatusForbidden)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(v)
}

func fail(w http.ResponseWriter, code int, msg string) {
	writeJSON(w, code, map[string]string{"error": msg})
}

func postOnly(w http.ResponseWriter, r *http.Request) bool {
	if r.Method != http.MethodPost {
		fail(w, http.StatusMethodNotAllowed, "POST only")
		return false
	}
	return true
}

func (a *App) index(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Write(indexHTML)
}

func (a *App) state(w http.ResponseWriter, r *http.Request) {
	a.mu.Lock()
	defer a.mu.Unlock()
	up := []*Package{}
	for _, p := range a.uploads {
		up = append(up, p)
	}
	out := map[string]any{"connected": a.dev != nil, "uploads": up}
	if a.dev != nil {
		out["device"] = a.dev.Info
		out["problems"] = a.dev.Info.problems()
	}
	if a.job != nil {
		out["job"] = a.job.ID
	}
	writeJSON(w, 200, out)
}

func (a *App) connect(w http.ResponseWriter, r *http.Request) {
	if !postOnly(w, r) {
		return
	}
	var in struct{ Host, Password string }
	if err := json.NewDecoder(io.LimitReader(r.Body, 1<<16)).Decode(&in); err != nil {
		fail(w, 400, "bad request")
		return
	}
	dev, err := Dial(strings.TrimSpace(in.Host), in.Password, a.cfg)
	if err != nil {
		fail(w, 400, err.Error())
		return
	}
	a.mu.Lock()
	if a.dev != nil {
		a.dev.Close()
	}
	a.dev = dev
	a.mu.Unlock()
	writeJSON(w, 200, map[string]any{"device": dev.Info, "problems": dev.Info.problems()})
}

func (a *App) disconnect(w http.ResponseWriter, r *http.Request) {
	if !postOnly(w, r) {
		return
	}
	a.mu.Lock()
	if a.dev != nil {
		a.dev.Close()
		a.dev = nil
	}
	a.mu.Unlock()
	writeJSON(w, 200, map[string]bool{"ok": true})
}

func (a *App) catalog(w http.ResponseWriter, r *http.Request) {
	a.mu.Lock()
	if a.cat == nil || time.Since(a.catAt) > 10*time.Minute {
		a.mu.Unlock()
		cat, err := FetchCatalog(a.catalogURL)
		if err != nil {
			fail(w, 502, "cannot read the catalog: "+err.Error()+" (you can still install zips you have already downloaded)")
			return
		}
		a.mu.Lock()
		a.cat, a.catAt = cat, time.Now()
	}
	defer a.mu.Unlock()
	installed := map[string]bool{}
	if a.dev != nil {
		for _, s := range a.dev.Info.Installed {
			installed[s] = true
		}
	}
	type row struct {
		CatPlugin
		Installed bool `json:"installed"`
	}
	rows := []row{}
	for _, c := range a.cat {
		rows = append(rows, row{c, installed[c.Skin]})
	}
	writeJSON(w, 200, map[string]any{"plugins": rows})
}

func (a *App) upload(w http.ResponseWriter, r *http.Request) {
	if !postOnly(w, r) {
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, 2*maxUncompressed)
	mr, err := r.MultipartReader()
	if err != nil {
		fail(w, 400, "expected a file upload")
		return
	}
	type res struct {
		Name    string   `json:"name"`
		Package *Package `json:"package,omitempty"`
		Error   string   `json:"error,omitempty"`
	}
	var out []res
	for {
		part, err := mr.NextPart()
		if err == io.EOF {
			break
		}
		if err != nil {
			fail(w, 400, err.Error())
			return
		}
		name := filepath.Base(part.FileName())
		if part.FileName() == "" {
			continue
		}
		handle := randHex(6)
		dest := filepath.Join(a.work, handle+".zip")
		f, err := os.Create(dest)
		if err != nil {
			fail(w, 500, err.Error())
			return
		}
		_, cerr := io.Copy(f, part)
		f.Close()
		if cerr != nil {
			os.Remove(dest)
			fail(w, 400, "upload failed: "+cerr.Error())
			return
		}
		p, perr := OpenPackage(dest, "upload")
		if perr != nil {
			os.Remove(dest)
			out = append(out, res{Name: name, Error: perr.Error()})
			continue
		}
		p.Handle = handle
		a.mu.Lock()
		a.uploads[handle] = p
		a.mu.Unlock()
		out = append(out, res{Name: name, Package: p})
	}
	writeJSON(w, 200, map[string]any{"results": out})
}

func (a *App) discard(w http.ResponseWriter, r *http.Request) {
	if !postOnly(w, r) {
		return
	}
	var in struct{ Handle string }
	if err := json.NewDecoder(io.LimitReader(r.Body, 1<<12)).Decode(&in); err != nil {
		fail(w, 400, "bad request")
		return
	}
	a.mu.Lock()
	if p, ok := a.uploads[in.Handle]; ok {
		os.Remove(p.Path)
		delete(a.uploads, in.Handle)
	}
	a.mu.Unlock()
	writeJSON(w, 200, map[string]bool{"ok": true})
}

type selection struct {
	Catalog []string `json:"catalog"`
	Uploads []string `json:"uploads"`
	Confirm bool     `json:"confirm"`
}

// resolve turns a selection into install items. Caller holds a.mu.
func (a *App) resolve(s selection) ([]Item, error) {
	var items []Item
	seen := map[string]bool{}
	for _, id := range s.Catalog {
		if seen["c"+id] {
			continue
		}
		seen["c"+id] = true
		var found *CatPlugin
		for i := range a.cat {
			if a.cat[i].ID == id {
				c := a.cat[i]
				found = &c
			}
		}
		if found == nil {
			return nil, fmt.Errorf("%q is not in the catalog", id)
		}
		items = append(items, Item{Catalog: found})
	}
	for _, h := range s.Uploads {
		if seen["u"+h] {
			continue
		}
		seen["u"+h] = true
		p, ok := a.uploads[h]
		if !ok {
			return nil, errors.New("a zip you added is no longer there: add it again")
		}
		items = append(items, Item{Pkg: p})
	}
	if len(items) == 0 {
		return nil, errors.New("nothing selected")
	}
	return items, nil
}

func (a *App) plan(w http.ResponseWriter, r *http.Request) {
	if !postOnly(w, r) {
		return
	}
	var s selection
	if err := json.NewDecoder(io.LimitReader(r.Body, 1<<16)).Decode(&s); err != nil {
		fail(w, 400, "bad request")
		return
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	items, err := a.resolve(s)
	if err != nil {
		fail(w, 400, err.Error())
		return
	}
	type line struct {
		Title   string `json:"title"`
		Version string `json:"version"`
		Source  string `json:"source"`
		MB      int64  `json:"mb"`
	}
	var lines []line
	restarts := 0
	anyDefer, fromCatalog := false, false
	for _, it := range items {
		if it.Catalog != nil {
			lines = append(lines, line{it.Catalog.Name, it.Catalog.Version, "catalog", it.Catalog.Size >> 20})
			anyDefer, fromCatalog = true, true // a catalog zip's installer is only known once it is downloaded
		} else {
			lines = append(lines, line{it.Pkg.Title, it.Pkg.Version, "your zip", it.Pkg.Size >> 20})
			if it.Pkg.Defer {
				anyDefer = true
			} else {
				restarts++
			}
		}
	}
	if anyDefer {
		restarts++
	}
	writeJSON(w, 200, map[string]any{"items": lines, "restarts": restarts, "maybeMore": fromCatalog})
}

func (a *App) install(w http.ResponseWriter, r *http.Request) {
	if !postOnly(w, r) {
		return
	}
	var s selection
	if err := json.NewDecoder(io.LimitReader(r.Body, 1<<16)).Decode(&s); err != nil {
		fail(w, 400, "bad request")
		return
	}
	if !s.Confirm {
		fail(w, 400, "the install must be confirmed")
		return
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.dev == nil {
		fail(w, 400, "connect to the device first")
		return
	}
	if a.job != nil {
		if st, _, _, _ := a.job.snapshot(0); st == "running" {
			fail(w, 409, "an install is already running")
			return
		}
	}
	items, err := a.resolve(s)
	if err != nil {
		fail(w, 400, err.Error())
		return
	}
	j := &Job{ID: randHex(4), State: "running"}
	a.job = j
	dev := a.dev
	go RunInstall(dev, items, a.work, j, func() {
		a.mu.Lock()
		defer a.mu.Unlock()
		if a.dev == dev {
			dev.readInfo(dev.Info.Host, dev.Info.Fingerprint)
		}
	})
	writeJSON(w, 200, map[string]string{"job": j.ID})
}

func (a *App) jobStatus(w http.ResponseWriter, r *http.Request) {
	a.mu.Lock()
	j := a.job
	a.mu.Unlock()
	if j == nil {
		fail(w, 404, "no install has been started")
		return
	}
	since := 0
	fmt.Sscanf(r.URL.Query().Get("since"), "%d", &since)
	st, lines, next, result := j.snapshot(since)
	writeJSON(w, 200, map[string]any{"id": j.ID, "state": st, "lines": lines, "next": next, "result": result})
}
