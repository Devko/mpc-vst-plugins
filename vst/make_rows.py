#!/usr/bin/env python3
"""The plugin rows (DESIGN.md 6b): writes ROWS thin rows into layout.conf and their params into params.json, so a row is
described once here instead of copied by hand. Run it, then vst/shots.py (it adds each row's thumbnail buttons), then the build.
    python3 vst/make_rows.py
Everything between the first card list and the detail-view comment in layout.conf is replaced (the thumbnail lines come back
from shots.py); in params.json the card<N>_1 and r<N>_* params (not r<N>_shot) are replaced, at the place of the first one."""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = 5
TOP, PITCH, H = 210, 74, 70   # the list area is y 210..584; rows 74 apart, 70 tall
THUMB = (112, 56)             # keep in step with vst/shots.py and make_images.py (card_off.svg)


def layout_rows():
    out = []
    for r in range(1, ROWS + 1):
        t = TOP + PITCH * (r - 1)
        c = t + 35
        b = lambda cx, cy, key, img, w, h, when: out.append(   # noqa: E731
            'button cx=%d cy=%d label="" key=%s img=images/%s w=%d h=%d when=%s' % (cx, cy, key, img, w, h, when))
        k = "r%d_" % r
        out.append('list x=24 y=%d w=1232 h=%d cols=1 rows=1 th=%d gap=0 key=card%d img=images/card_off.svg img_on=images/card_on.svg '
                   'tx=136 ty=3 ttw=530 tth=34 tsize=28 tweight=bold tcolor=ececed when=%svis:on' % (t, H, H, r, k))
        # the thumbnails (shots.py adds them here), then the initials of a plugin without one and the corner text
        out.append('readout box=0 w=112 h=34 cx=90 cy=%d label="" key=%sinit tsize=32 tweight=bold tcolor=ececed talign=center tpad=0 when=%sshot:none' % (c - 2, k, k))
        out.append('readout box=0 w=40 h=14 cx=125 cy=%d label="" key=%skindtxt tsize=12 tcolor=c9ccd1 talign=right tpad=2' % (t + 55, k))
        out.append('readout box=0 w=530 h=22 cx=425 cy=%d label="" key=%smeta tsize=19 tweight=regular tcolor=b4b7bc talign=left tpad=0' % (t + 53, k))
        b(425, c - 2, k + "open", "card_hit.svg", 540, 60, k + "vis:on")
        # badges: the channel and CPU on the first line, the old-install and tested ones on the second
        b(736, t + 20, "noop", "badge_stable.svg", 72, 26, k + "chan:stable")
        b(732, t + 20, "noop", "badge_beta.svg", 64, 26, k + "chan:beta")
        b(836, t + 20, "noop", "badge_cpu.svg", 112, 26, k + "cpu:on")
        b(752, t + 50, "noop", "badge_old.svg", 104, 26, k + "old:on")
        b(912, t + 50, "noop", "badge_tested.svg", 200, 26, k + "tested:on")
        out.append('readout box=0 w=166 h=26 cx=924 cy=%d label="" key=%stested_txt tsize=21 tcolor=7fd6a8 talign=left tpad=0 when=%stested:on' % (t + 50, k, k))
        out.append('readout box=0 w=80 h=28 cx=945 cy=%d label="" key=%sver tsize=26 tcolor=ececed talign=left tpad=0' % (t + 20, k))
        out.append('readout box=0 w=64 h=20 cx=1012 cy=%d label="" key=%sfrom tsize=18 tcolor=f0b44a talign=left tpad=0' % (t + 22, k))
        for st, img in (("install", "btn_install"), ("update", "btn_update"), ("installed", "btn_installed"), ("q_install", "btn_q_install"),
                        ("q_update", "btn_q_update"), ("q_remove", "btn_q_remove"), ("disabled", "btn_disabled")):
            b(1129, c, k + "act", img + ".svg", 150, 44, "%sstate:%s" % (k, st))
        b(1094, c, k + "reinstall", "btn_reinstall.svg", 76, 44, k + "state:menu")
        b(1172, c, k + "remove", "btn_remove.svg", 76, 44, k + "state:menu")
        b(1236, c, k + "more", "more.svg", 44, 44, k + "inst:yes")
    return out


def main():
    lc = os.path.join(HERE, "layout.conf")
    lines = open(lc).read().split("\n")
    first = next(i for i, l in enumerate(lines) if re.match(r"list x=24 y=\d+ .*key=card1\b", l))
    last = max(i for i, l in enumerate(lines) if re.search(r"key=r\d_more\b", l))
    lines[first:last + 1] = layout_rows()
    open(lc, "w").write("\n".join(lines))

    pj = os.path.join(HERE, "params.json")
    p = json.load(open(pj))
    ps = p["params"]
    rowp = lambda x: re.match(r"(card\d_1|r\d_(?!shot$).*)$", x["key"])   # noqa: E731
    tmpl = [x for x in ps if re.match(r"(card1_1|r1_(?!shot$).*)$", x["key"])]
    at = next(i for i, x in enumerate(ps) if rowp(x))
    rest = [x for x in ps if not rowp(x)]
    new = []
    for r in range(1, ROWS + 1):
        for x in tmpl:
            y = json.loads(json.dumps(x))
            y["key"] = re.sub(r"^(card|r)1", lambda m: m.group(1) + str(r), y["key"])
            y["name"] = re.sub(r"\b1\b", str(r), y["name"])
            new.append(y)
    p["params"] = rest[:at] + new + rest[at:]
    open(pj, "w").write(json.dumps(p, indent=1) + "\n")
    print("%d rows: %d layout lines, %d params" % (ROWS, len(layout_rows()), len(new)))


if __name__ == "__main__":
    main()
