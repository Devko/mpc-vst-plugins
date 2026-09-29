#!/usr/bin/env python3
"""Offline test of the release manifest and validator: builds a fake package with tools/release.py and checks that
tools/catalog_check.py accepts it and rejects tampered copies. No device, no toolchain: python3 tools/test_catalog.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import catalog_check  # noqa: E402

ENTRY = ('<PLUGIN name="Test Synth" format="VST" category="Synth" manufacturer="Acme" version="1.0" '
         'file="/sdcard/vst/test_synth.so" uid="1a2b3c4d" isInstrument="1" fileTime="0" infoUpdateTime="0" '
         'numInputs="0" numOutputs="2" isShell="0" hasARAExtension="0" uniqueId="0"/>')


def fake_so(path, machine=40, glibc=b"GLIBC_2.30"):
    hdr = bytearray(b"\x7fELF" + bytes(16))
    hdr[18:20] = machine.to_bytes(2, "little")
    open(path, "wb").write(bytes(hdr) + b"\0" + glibc + b"\0")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def build(self, version="1.2.0", machine=40, glibc=b"GLIBC_2.30", extra=()):
        t = self.tmp
        fake_so(os.path.join(t, "test_synth.so"), machine, glibc)
        skin = os.path.join(t, "Acme - VST - Test Synth")
        os.makedirs(os.path.join(skin, "Plugin Skins"), exist_ok=True)
        open(os.path.join(skin, "version.xml"), "w").write("<v/>")
        open(os.path.join(skin, "Plugin Skins", "TUI.json"), "w").write("{}")
        open(os.path.join(t, "entry.xml"), "w").write(ENTRY)
        out = os.path.join(t, "dist")
        subprocess.check_call([sys.executable, os.path.join(HERE, "release.py"), "--so", os.path.join(t, "test_synth.so"),
                               "--skin", skin, "--entry", os.path.join(t, "entry.xml"), "--version", version,
                               "--repo", "acme/test-synth", "--license", "MIT", "-o", out, *extra],
                              stdout=subprocess.DEVNULL)
        return os.path.join(out, "Test-Synth-%s-mpc-armv7.zip" % version)

    def tamper(self, zpath, member_suffix, fn):
        out = zpath + ".t.zip"
        with zipfile.ZipFile(zpath) as zin, zipfile.ZipFile(out, "w") as zout:
            for i in zin.infolist():
                data = zin.read(i.filename)
                if i.filename.endswith(member_suffix):
                    data = fn(data)
                zout.writestr(i, data)
        return out


class CatalogTest(Base):
    def test_good_package(self):
        z = self.build()
        errors, warnings, rec = catalog_check.check(z, catalog=True, expect_id="test-synth", expect_repo="acme/test-synth")
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        m = rec["manifest"]
        self.assertEqual((m["id"], m["arch"], m["max_glibc"], m["param_compat"]), ("test-synth", "armv7", "2.30", 1))
        self.assertEqual(len(rec["sha256"]), 64)

    def test_wrong_arch_and_glibc(self):
        e, _, _ = catalog_check.check(self.build(machine=62))
        self.assertTrue(any("armv7" in x for x in e))
        e, _, _ = catalog_check.check(self.build(glibc=b"GLIBC_2.38"))
        self.assertTrue(any("GLIBC" in x for x in e))

    def test_tampered_file_fails_checksum(self):
        z = self.tamper(self.build(), "payload/vst/test_synth.so", lambda d: d + b"x")
        e, _, _ = catalog_check.check(z)
        self.assertTrue(any("checksum mismatch" in x for x in e))

    def test_modified_installer_warns(self):
        z = self.build()
        # rebuild SHA256SUMS consistently so only the installer-template check can object
        import hashlib
        def mod(d): return d + b"\n# evil\n"
        z = self.tamper(z, "/install.sh", mod)
        z = self.tamper(z, "/SHA256SUMS", lambda d: "\n".join(
            l if "install.sh" not in l or "uninstall" in l else
            "%s  install.sh" % hashlib.sha256(self._install(zipfile.ZipFile(z))).hexdigest()
            for l in d.decode().splitlines()).encode() + b"\n")
        e, w, _ = catalog_check.check(z)
        self.assertEqual(e, [])
        self.assertTrue(any("install.sh differs" in x for x in w))

    @staticmethod
    def _install(zf):
        return [zf.read(n) for n in zf.namelist() if n.endswith("/install.sh")][0]

    def test_catalog_needs_repo_and_license(self):
        t = self.tmp
        z = self.build()
        z2 = self.tamper(z, "mpc-plugin.json", lambda d: json.dumps({**json.loads(d), "license": None}).encode())
        e, _, _ = catalog_check.check(z2, catalog=True)
        self.assertTrue(any("license" in x for x in e))

    def test_symlinks_inside_package_ok_outside_rejected(self):
        z = self.build()
        def add(target):
            out = z + "." + str(abs(hash(target))) + ".zip"
            with zipfile.ZipFile(z) as zin, zipfile.ZipFile(out, "w") as zout:
                for i in zin.infolist():
                    zout.writestr(i, zin.read(i.filename))
                top = zin.namelist()[0].split("/")[0]
                i = zipfile.ZipInfo(top + "/payload/vst/d1/l"); i.external_attr = 0o120777 << 16
                zout.writestr(i, target)
            return out
        e, _, _ = catalog_check.check(add("../d2/x"), catalog=True)
        self.assertFalse(any("symlink" in x for x in e))
        e, _, _ = catalog_check.check(add("../../../../etc/passwd"), catalog=True)
        self.assertTrue(any("symlink" in x for x in e))

    def test_id_mismatch_with_registry(self):
        e, _, _ = catalog_check.check(self.build(), expect_id="other")
        self.assertTrue(any("registry id" in x for x in e))



import catalog_build  # noqa: E402


class FakeGitHub:
    def __init__(self, releases, zips):
        self.releases, self.zips = releases, zips

    def list_releases(self, repo):
        if repo not in self.releases:
            raise RuntimeError("404")
        return self.releases[repo]

    def download(self, asset, dest):
        shutil.copy(self.zips[asset["id"]], dest)


class BuildTest(Base):
    ENTRY = {"id": "test-synth", "name": "Test Synth", "author": "A", "repo": "acme/test-synth", "kind": "instrument",
             "license": "MIT", "summary": "s"}

    def rel(self, tag, aid, pre=False, name="x-mpc-armv7.zip"):
        return {"tag_name": tag, "prerelease": pre, "draft": False, "published_at": "2026-09-29T00:00:00Z", "body": "notes",
                "assets": [{"id": aid, "name": name, "browser_download_url": "https://x/" + name, "download_count": 3}]}

    def test_build_keeps_good_versions_and_reports_bad(self):
        good, newer = self.build("1.0.0"), self.build("1.1.0")
        bad = self.tamper(self.build("1.2.0"), "payload/vst/test_synth.so", lambda d: d + b"x")
        gh = FakeGitHub({"acme/test-synth": [self.rel("v1.2.0", 3), self.rel("v1.1.0", 2), self.rel("v1.0.0", 1),
                                              self.rel("v1.3.0-b", 4, pre=True, name="nope.txt")]},
                        {1: good, 2: newer, 3: bad})
        cat, problems = catalog_build.build([self.ENTRY], gh, os.path.join(self.tmp, "cache"), {"test-synth@1.0.0"})
        p = cat["plugins"][0]
        self.assertEqual([v["version"] for v in p["versions"]], ["1.1.0", "1.0.0"])
        self.assertEqual(p["latest"], "1.1.0")
        self.assertTrue(p["versions"][1]["yanked"])
        self.assertEqual(p["downloads"], 6)
        self.assertEqual(sorted((x["tag"] for x in problems)), ["v1.2.0", "v1.3.0-b"])

    def test_tested_json_attaches_to_matching_version(self):
        gh = FakeGitHub({"acme/test-synth": [self.rel("v1.0.0", 1)]}, {1: self.build("1.0.0")})
        gh.tested = lambda repo: [{"version": "v1.0.0", "device": "MPC Live II", "firmware": "3.6", "date": "2026-09-01"},
                                  {"version": "9.9.9", "device": "Force"}]
        cat, _ = catalog_build.build([self.ENTRY], gh, os.path.join(self.tmp, "c"), set())
        self.assertEqual(cat["plugins"][0]["versions"][0]["tested"],
                         [{"device": "MPC Live II", "firmware": "3.6", "date": "2026-09-01"}])

    def test_unreadable_repo_is_reported_not_fatal(self):
        cat, problems = catalog_build.build([self.ENTRY], FakeGitHub({}, {}), os.path.join(self.tmp, "c"), set())
        self.assertEqual(cat["plugins"][0]["versions"], [])
        self.assertIsNone(cat["plugins"][0]["latest"])
        self.assertIn("cannot list", problems[0]["error"])

    def test_registry_rules(self):
        self.assertEqual(catalog_build.check_entry(self.ENTRY, "x/test-synth.json"), [])
        self.assertTrue(catalog_build.check_entry({**self.ENTRY, "license": "Proprietary"}))
        self.assertTrue(catalog_build.check_entry(self.ENTRY, "x/other.json"))
        self.assertTrue(catalog_build.check_entry({**self.ENTRY, "repo": "nope"}))


import catalog_issues  # noqa: E402


class IssuesTest(unittest.TestCase):
    def test_plan_dedupes_and_skips_open(self):
        pr = [{"id": "a", "tag": "v1", "error": "x"}, {"id": "a", "tag": "v1", "error": "y"},
              {"id": "a", "tag": "v2", "error": "z"}, {"id": "b", "tag": None, "error": "404"}]
        got = catalog_issues.plan(pr, {"Catalog: a v2 failed validation"})
        self.assertEqual([t for t, _ in got], ["Catalog: a v1 failed validation", "Catalog: b cannot be read"])
        self.assertIn("- x", got[0][1]); self.assertIn("- y", got[0][1])


import catalog_site  # noqa: E402


class SiteTest(unittest.TestCase):
    def test_render_embeds_catalog_safely(self):
        cat = {"schema": 1, "generated": "x", "plugins": [{"id": "a", "name": "A </script><b>", "versions": []}]}
        html = catalog_site.render(cat)
        self.assertNotIn("/*CATALOG_JSON*/", html)
        data = html.split('<script id="data" type="application/json">')[1].split("</script>")[0]
        self.assertEqual(json.loads(data), cat)   # round-trips, and the embedded "</script>" can't end the block

    def test_atom_feed_skips_yanked_and_escapes(self):
        v = lambda ver, y: {"version": ver, "date": "2026-09-2%s" % ver[0], "url": "https://x/a?b=1&c=2", "yanked": y, "channel": "stable"}
        cat = {"schema": 1, "generated": "g", "plugins": [{"id": "a", "name": "A <&>", "author": "Z", "summary": "s",
                                                         "versions": [v("2.0", False), v("1.0", True)]}]}
        import xml.dom.minidom
        doc = xml.dom.minidom.parseString(catalog_site.atom(cat, "https://e.io/x/"))
        self.assertEqual(len(doc.getElementsByTagName("entry")), 1)
        self.assertIn("A <&>", doc.getElementsByTagName("title")[1].firstChild.data)

    def test_registry_style_and_source_available(self):
        e = dict(BuildTest.ENTRY, license="MAME license")
        self.assertTrue(catalog_build.check_entry(e))
        self.assertEqual(catalog_build.check_entry(dict(e, source_available=True, style="rompler", tags=["jv-880"])), [])
        self.assertTrue(catalog_build.check_entry(dict(BuildTest.ENTRY, style="Bad Style")))


import catalog_md  # noqa: E402


class PagesTest(unittest.TestCase):
    def test_markdown_subset_and_escaping(self):
        html = catalog_md.render("# T <b>\n\ntext with `a<b` and **bold** [x](https://e.io/a?b=1&c=2) [bad](javascript:alert(1))\n\n"
                                 "- one\n  wrapped\n- two\n\n1. a\n2. b\n\n```\n<x> & y\n```\n\n> note\n\n| h1 | h2 |\n|---|---|\n| a | b |\n")
        self.assertIn('<h1 id="t">T &lt;b&gt;</h1>', html)
        self.assertIn("<code>a&lt;b</code>", html)
        self.assertIn("<strong>bold</strong>", html)
        self.assertIn('<a href="https://e.io/a?b=1&amp;c=2">x</a>', html)
        self.assertNotIn('href="javascript', html)
        self.assertIn("<li>one wrapped</li>", html)
        self.assertIn("<ol><li>a</li><li>b</li></ol>", html)
        self.assertIn("<pre><code>&lt;x&gt; &amp; y</code></pre>", html)
        self.assertIn("<blockquote>", html)
        self.assertIn("<th>h1</th>", html)
        self.assertNotIn("<b>", html)

    def test_install_page_explains_where_to_build(self):
        pages = catalog_site.load_pages(os.path.join(HERE, "..", "catalog", "pages"))
        html = catalog_site.render_page([p for p in pages if p["slug"] == "install"][0], pages)
        self.assertIn('id="plugins-you-build-yourself"', html)   # the card links here
        self.assertIn("on <strong>your computer</strong>", html)
        idx = catalog_site.render({"schema": 1, "generated": "x", "plugins": []}, pages)
        self.assertIn("Run this on your computer (needs Docker), not on the device.", idx)
        self.assertIn('install.html#plugins-you-build-yourself', idx)

    def test_repo_pages_render_with_nav(self):
        pages = catalog_site.load_pages(os.path.join(HERE, "..", "catalog", "pages"))
        self.assertGreaterEqual(len(pages), 5)
        self.assertEqual([p["slug"] for p in pages], ["setup", "install", "build", "workflow", "add"])
        for p in pages:
            html = catalog_site.render_page(p, pages)
            self.assertIn('aria-current="page"', html)
            for marker in ("/*NAV*/", "/*TITLE*/", "/*DESC*/", "/*BODY*/", "/*SITE_CSS*/"):
                self.assertNotIn(marker, html)
        idx = catalog_site.render({"schema": 1, "generated": "x", "plugins": []}, pages)
        for p in pages:
            self.assertIn('href="%s.html"' % p["slug"], idx)
        self.assertNotIn("/*NAV*/", idx)

class FakeTags:
    """GitHub stand-in for build-yourself entries: tags, files per tag, releases, dates."""
    def __init__(self, tags=None, files=(), releases=None, tested=None):
        self.tags, self.files, self.releases, self._tested = tags or {}, set(files), releases or {}, tested or {}

    def list_tags(self, repo):
        if repo not in self.tags:
            raise RuntimeError("404 Not Found")
        return [{"name": n, "sha": "sha-" + n} for n in self.tags[repo]]

    def list_releases(self, repo):
        return self.releases.get(repo, [])

    def file_exists(self, repo, path, ref):
        return (repo, ref, path) in self.files

    def tag_date(self, repo, sha):
        return "2026-09-2" + str(len(sha) % 10)

    def tested(self, repo):
        return self._tested.get(repo, [])


BY_ENTRY = {
    "id": "fw-synth", "name": "Firmware Synth", "author": "A", "repo": "acme/fw-synth", "kind": "instrument", "license": "AGPL-3.0-only",
    "summary": "s", "distribution": "build-yourself",
    "requires_user_files": [{"name": "OS.syx", "description": "Your own OS file."}],
    "build": {"command": "release/build.sh <OS.syx> [-d <ip>]", "script": "release/build.sh", "docs_url": "https://github.com/acme/fw-synth/blob/{tag}/README.md", "needs": ["Docker"]},
    "components": [{"id": "fw-one", "name": "FW One", "kind": "instrument", "uid": "FwOn"}, {"id": "fw-fx", "name": "FW FX", "kind": "effect", "uid": "FwFx"}],
}


class BuildYourselfTest(Base):
    def entry(self, **kw):
        e = json.loads(json.dumps(BY_ENTRY))
        e.update(kw)
        return e

    def test_registry_accepts_a_valid_entry(self):
        self.assertEqual(catalog_build.check_entry(self.entry(), "x/fw-synth.json"), [])

    def test_registry_guardrails(self):
        bad = {
            "no user files": self.entry(requires_user_files=[]),
            "user file without description": self.entry(requires_user_files=[{"name": "x"}]),
            "no build": {k: v for k, v in self.entry().items() if k != "build"},
            "script outside the repo": self.entry(build=dict(BY_ENTRY["build"], script="../x.sh", command="../x.sh")),
            "absolute script": self.entry(build=dict(BY_ENTRY["build"], script="/x.sh", command="/x.sh")),
            "command does not run the script": self.entry(build=dict(BY_ENTRY["build"], command="make")),
            "http docs url": self.entry(build=dict(BY_ENTRY["build"], docs_url="http://x.io")),
            "not an open license": self.entry(license="MAME license"),
            "source_available is not enough": self.entry(license="MAME license", source_available=True),
            "asset_pattern makes no sense": self.entry(asset_pattern="*.zip"),
            "bad component": self.entry(components=[{"id": "Bad Id", "name": "x", "kind": "instrument"}]),
            "bad component uid": self.entry(components=[{"id": "a", "name": "x", "kind": "instrument", "uid": "toolong"}]),
            "duplicate component": self.entry(components=[{"id": "a", "name": "x", "kind": "instrument"}, {"id": "a", "name": "y", "kind": "effect"}]),
            "unknown distribution": self.entry(distribution="download"),
        }
        for why, e in bad.items():
            self.assertTrue(catalog_build.check_entry(e, "x/fw-synth.json"), why)

    def test_release_entries_cannot_carry_build_fields(self):
        e = dict(BuildTest.ENTRY, requires_user_files=BY_ENTRY["requires_user_files"])
        self.assertTrue(catalog_build.check_entry(e, "x/test-synth.json"))
        self.assertEqual(catalog_build.check_entry(dict(BuildTest.ENTRY, distribution="release"), "x/test-synth.json"), [])
        self.assertEqual(catalog_build.check_entry(BuildTest.ENTRY, "x/test-synth.json"), [])   # default distribution

    def test_component_ids_are_unique_across_the_registry(self):
        d = os.path.join(self.tmp, "reg")
        os.makedirs(d)
        a, b = self.entry(), self.entry(id="other", repo="acme/other")
        for e in (a, b):
            json.dump(e, open(os.path.join(d, e["id"] + ".json"), "w"))
        entries, problems = catalog_build.load_registry(d)
        self.assertEqual([e["id"] for e in entries], ["fw-synth"])
        self.assertTrue(any("component id" in m for _, m in problems))

    def test_versions_come_from_tags_and_need_the_script(self):
        e = self.entry()
        before = json.dumps(e, sort_keys=True)
        gh = FakeTags(tags={"acme/fw-synth": ["v0.9.0", "v0.9.1", "v1.0.0-rc1", "nightly"]},
                      files={("acme/fw-synth", "v0.9.1", "release/build.sh"), ("acme/fw-synth", "v0.9.1", "LICENSE"),
                             ("acme/fw-synth", "v0.9.0", "LICENSE")},
                      tested={"acme/fw-synth": [{"version": "0.9.1", "device": "Akai Force", "firmware": "3.9.1", "date": "2026-09-29"}]})
        cat, problems = catalog_build.build([e], gh, os.path.join(self.tmp, "c"), set())
        p = cat["plugins"][0]
        self.assertEqual([v["version"] for v in p["versions"]], ["0.9.1"])   # v0.9.0 has no script; rc and nightly are ignored
        self.assertEqual(p["latest"], "0.9.1")
        self.assertEqual(p["distribution"], "build-yourself")
        v = p["versions"][0]
        self.assertEqual((v["tag"], v["source_url"], v["tested"]), ("v0.9.1", "https://github.com/acme/fw-synth/tree/v0.9.1", [{"device": "Akai Force", "firmware": "3.9.1", "date": "2026-09-29"}]))
        for k in ("url", "sha256", "size", "param_compat", "manifest"):
            self.assertNotIn(k, v)   # nothing is published: no download, checksum or zip manifest
        self.assertEqual(v["warnings"], [])   # this tag has a LICENSE file
        self.assertEqual([c["id"] for c in p["components"]], ["fw-one", "fw-fx"])
        self.assertEqual(problems, [])   # the old tag v0.9.0 without the script is skipped quietly, not reported
        self.assertEqual(json.dumps(e, sort_keys=True), before)   # the registry entry is not mutated

    def test_only_the_newest_tag_missing_the_script_is_reported(self):
        files = {("acme/fw-synth", "v0.9.0", "release/build.sh"), ("acme/fw-synth", "v0.9.0", "LICENSE")}
        gh = FakeTags(tags={"acme/fw-synth": ["v0.9.0", "v0.9.1"]}, files=files)   # the newest tag lacks the script
        cat, problems = catalog_build.build([self.entry()], gh, os.path.join(self.tmp, "c"), set())
        self.assertEqual([v["version"] for v in cat["plugins"][0]["versions"]], ["0.9.0"])
        self.assertEqual([(x["tag"], "does not exist at this tag" in x["error"]) for x in problems], [("v0.9.1", True)])

    def test_license_file_missing_is_a_warning_on_the_version(self):
        gh = FakeTags(tags={"acme/fw-synth": ["v0.1.0"]}, files={("acme/fw-synth", "v0.1.0", "release/build.sh")})
        cat, problems = catalog_build.build([self.entry()], gh, os.path.join(self.tmp, "c"), set())
        self.assertEqual(cat["plugins"][0]["versions"][0]["warnings"], ["no LICENSE file at the root of this tag"])
        self.assertEqual(problems, [])

    def test_published_zip_is_reported_loudly_but_entry_stays(self):
        rel = {"tag_name": "v0.1.0", "draft": False, "assets": [{"id": 1, "name": "FW-0.1.0-mpc-armv7.zip", "browser_download_url": "https://x/z"}]}
        gh = FakeTags(tags={"acme/fw-synth": ["v0.1.0"]}, files={("acme/fw-synth", "v0.1.0", "release/build.sh")}, releases={"acme/fw-synth": [rel]})
        cat, problems = catalog_build.build([self.entry()], gh, os.path.join(self.tmp, "c"), set())
        self.assertEqual(cat["plugins"][0]["latest"], "0.1.0")
        self.assertEqual(len(problems), 1)
        self.assertIn("LICENCE RISK", problems[0]["error"])
        self.assertEqual(problems[0]["tag"], "v0.1.0")
        gh.releases["acme/fw-synth"][0]["draft"] = True   # a draft is not public
        self.assertEqual(catalog_build.build([self.entry()], gh, os.path.join(self.tmp, "c"), set())[1], [])

    def test_missing_repo_and_no_tags_are_reported(self):
        cat, problems = catalog_build.build([self.entry()], FakeTags(), os.path.join(self.tmp, "c"), set())
        self.assertEqual(cat["plugins"][0]["versions"], [])
        self.assertIsNone(cat["plugins"][0]["latest"])
        self.assertIn("cannot read the repo", problems[0]["error"])
        cat, problems = catalog_build.build([self.entry()], FakeTags(tags={"acme/fw-synth": ["nightly"]}), os.path.join(self.tmp, "c"), set())
        self.assertIn("no vX.Y.Z tag", problems[0]["error"])

    def test_yanked_tag_is_never_latest(self):
        gh = FakeTags(tags={"acme/fw-synth": ["v0.2.0", "v0.1.0"]},
                      files={("acme/fw-synth", t, "release/build.sh") for t in ("v0.2.0", "v0.1.0")} | {("acme/fw-synth", t, "LICENSE") for t in ("v0.2.0", "v0.1.0")})
        cat, _ = catalog_build.build([self.entry()], gh, os.path.join(self.tmp, "c"), {"fw-synth@0.2.0"})
        self.assertEqual(cat["plugins"][0]["latest"], "0.1.0")

    def test_release_entries_are_untouched_in_a_mixed_catalog(self):
        class Mixed(FakeTags):
            def download(self, asset, dest):
                shutil.copy(good, dest)
        good = self.build("1.0.0")
        rel = {"tag_name": "v1.0.0", "prerelease": False, "draft": False, "published_at": "2026-09-29T00:00:00Z", "body": "",
               "assets": [{"id": 1, "name": "x-mpc-armv7.zip", "browser_download_url": "https://x/x", "download_count": 3}]}
        gh = Mixed(tags={"acme/fw-synth": ["v0.1.0"]}, files={("acme/fw-synth", "v0.1.0", "release/build.sh")}, releases={"acme/test-synth": [rel]})
        cat, problems = catalog_build.build([BuildTest.ENTRY, self.entry()], gh, os.path.join(self.tmp, "c"), set())
        r = [p for p in cat["plugins"] if p["id"] == "test-synth"][0]
        self.assertEqual((r["distribution"], r["latest"], r["downloads"]), ("release", "1.0.0", 3))
        self.assertIn("sha256", r["versions"][0])
        self.assertIn("url", r["versions"][0])
        self.assertFalse([x for x in problems if x["id"] == "test-synth"])

    def test_site_shows_build_instructions_not_downloads(self):
        html = catalog_site.render({"schema": 1, "generated": "x", "plugins": []})
        self.assertIn("The result contains firmware-derived data: build it yourself, install it on your own devices only, never share it.", html)
        self.assertIn("How to build", html)
        cat = {"schema": 1, "generated": "x", "plugins": [{"id": "fw-synth", "name": "FW", "author": "A", "summary": "s", "versions": [
            {"version": "0.1.0", "tag": "v0.1.0", "date": "2026-09-29", "channel": "stable", "yanked": False, "source_url": "https://github.com/a/b/tree/v0.1.0"}]}]}
        self.assertIn("<link href=\"https://github.com/a/b/tree/v0.1.0\"/>", catalog_site.atom(cat))


if __name__ == "__main__":
    unittest.main()
