#!/usr/bin/env python3
"""Offline unit tests for shadow_skin geometry/invariants that don't need the art toolchain or a device:
seg_rects honouring sw=, the two filmstrip frame-count conventions, and html_art's inlined SVGs keeping their ids
and classes apart. No device: python3 tools/test_shadow_skin.py"""
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shadow_skin  # noqa: E402
import html_art  # noqa: E402


class SegRects(unittest.TestCase):
    def widths(self, w):
        return {r[2] for r in shadow_skin.seg_rects(w)}

    def test_enum_v_defaults_to_135(self):
        w = {"kind": "enum_v", "options": ["A", "B", "C"], "cx": 100, "cy": 100}
        self.assertEqual(self.widths(w), {135})

    def test_enum_v_honours_sw(self):
        w = {"kind": "enum_v", "options": ["A", "B", "C"], "cx": 100, "cy": 100, "sw": 56}
        self.assertEqual(self.widths(w), {56})

    def test_enum_h_defaults_to_117(self):
        w = {"kind": "enum_h", "options": ["A", "B"], "cx": 100, "cy": 100}
        self.assertEqual(self.widths(w), {117})

    def test_enum_h_honours_sw(self):
        w = {"kind": "enum_h", "options": ["A", "B"], "cx": 100, "cy": 100, "sw": 68}
        self.assertEqual(self.widths(w), {68})


class FilmStripFrames(unittest.TestCase):
    def test_rotary_knob_is_one_fewer_than_strip(self):
        self.assertEqual(shadow_skin.ROT_FRAMES, shadow_skin.FRAMES - 1)

    def test_slider_and_meter_equal_strip_length(self):
        # the (l)sstrip generator emits exactly FRAMES frames for sliders and meters, so their FilmStrip
        # numFrames must match it; FRAMES-1 here is the second-thumb bug.
        self.assertEqual(shadow_skin.STRIP_FRAMES, shadow_skin.FRAMES)


class InlinedSvgs(unittest.TestCase):
    SVG = ('<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           'id="root" width="10" height="10" viewBox="0 0 10 10"><style>.cls-1{fill:url(#g)}</style>'
           '<defs><linearGradient id="g"><stop offset="0" stop-color="%s"/></linearGradient></defs>'
           '<rect class="cls-1" width="10" height="10"/><circle id="c" r="2" fill="url(\'#g\')"/>'
           '<use xlink:href="#c"/><use href="#c"/></svg>')

    def test_two_svgs_sharing_ids_and_classes_stay_apart(self):
        with tempfile.TemporaryDirectory() as d:
            art = html_art.Art()
            for i, colour in enumerate(("red", "blue")):
                path = os.path.join(d, "%d.svg" % i)
                open(path, "w").write(self.SVG % colour)
                art.images[path] = "img%d" % i
            defs = art.image_defs()
        ids = re.findall(r'\sid="([^"]+)"', defs)
        self.assertEqual(len(ids), len(set(ids)), ids)
        for iid, colour in (("img0", "red"), ("img1", "blue")):
            part = defs[defs.index('id="%s"' % iid):]
            part = part[:part.index("</svg>")]
            self.assertIn('id="%s-g"><stop offset="0" stop-color="%s"' % (iid, colour), part)
            self.assertIn(".%s-cls-1{fill:url(#%s-g)}" % (iid, iid), part)
            self.assertIn('class="%s-cls-1"' % iid, part)
            self.assertIn("url('#%s-g')" % iid, part)
            self.assertEqual(part.count('href="#%s-c"' % iid), 2)
            self.assertNotRegex(part, r'(url\(\s*[\'"]?#|href="#)(g|c)\b')


if __name__ == "__main__":
    unittest.main()
