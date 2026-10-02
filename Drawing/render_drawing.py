#!/usr/bin/env python3
"""JLC CNC drawing for V2 Backplate 6.11 (A3 landscape, ISO), written straight to PDF.

Reads backplate_geom.json (written inside Fusion by export_geometry.py) and writes a
one-page vector PDF using only the standard library.
After model changes: rerun export_geometry.py in Fusion, then this script.

Usage: py -3 render_drawing.py [out.pdf] [--preview]

Without out.pdf it writes "V2 Backplate 6.11 - JLC drawing.pdf" next to this script.
--preview also writes preview.svg (the same sheet, viewable in a browser).

View: the pocket side (-Y), X to the right, Z up, same as Fusion's FRONT view.
"""
import json
import math
import os
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
GEOM = os.path.join(HERE, 'backplate_geom.json')
ARGS = [a for a in sys.argv[1:] if not a.startswith('--')]
OUT_PDF = ARGS[0] if ARGS else os.path.join(HERE, 'V2 Backplate 6.11 - JLC drawing.pdf')
G = json.load(open(GEOM, encoding='utf-8'))

SW, SH = 420.0, 297.0
CAP = 0.718                      # Helvetica cap height as a fraction of the em
W_VIS, W_THIN, W_FRAME = 0.35, 0.18, 0.5
AR_L, AR_W = 2.5, 0.85
PM, DIA, TIMES, DEG = '±', 'Ø', '×', '°'
TOL = PM + '0.05'
THREAD_R = 1.5                   # M3 major radius, for the ISO thread symbol

# Helvetica advance widths (1/1000 em), ASCII 32..126, then the extra WinAnsi glyphs used here
_HW = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
       556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
       1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
       667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
       333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
       556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
_HW_EXTRA = {PM: 584, TIMES: 584, DIA: 778, DEG: 400}

ops = []                          # PDF content stream pieces (bytes)
TEXT_BOXES = []                   # corner lists of every text drawn, so centre lines can leave gaps


# ---------------------------------------------------------------- primitives
def _f(v):
    s = '%.3f' % v
    s = s.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def _pts(*vals):
    return ' '.join(_f(v) for v in vals)


def em_width(s, bold=False):
    w = 0
    for ch in s:
        o = ord(ch)
        w += _HW[o - 32] if 32 <= o <= 126 else _HW_EXTRA.get(ch, 556)
    return w / 1000.0 * (1.06 if bold else 1.0)


def text_w(s, h, bold=False):
    return em_width(s, bold) * h / CAP


def _stroke(path, w, dash=None):
    ops.append(('%s w %s %s S' % (_f(w), '[%s] 0 d' % dash if dash else '[] 0 d', path)).encode('latin-1'))


def line(p, q, w=W_THIN, dash=None):
    _stroke('%s m %s l' % (_pts(*p), _pts(*q)), w, dash)


def polyline(pts, w=W_VIS, closed=False):
    path = '%s m ' % _pts(*pts[0]) + ' '.join('%s l' % _pts(*p) for p in pts[1:])
    _stroke(path + (' h' if closed else ''), w)


def circle_path(c, r):
    k = 0.5522847498 * r
    x, y = c
    return ('%s m %s c %s c %s c %s c h'
            % (_pts(x + r, y),
               _pts(x + r, y + k, x + k, y + r, x, y + r),
               _pts(x - k, y + r, x - r, y + k, x - r, y),
               _pts(x - r, y - k, x - k, y - r, x, y - r),
               _pts(x + k, y - r, x + r, y - k, x + r, y)))


def circle(c, r, w=W_VIS):
    _stroke(circle_path(c, r), w)


def arc(c, r, a1, sw, w=W_VIS):
    """Arc from angle a1 sweeping sw degrees (counter-clockwise positive)."""
    if abs(sw) >= 359.99:
        return circle(c, r, w)
    n = max(1, int(math.ceil(abs(sw) / 90.0)))
    d = math.radians(sw) / n
    t = math.radians(a1)
    k = 4.0 / 3.0 * math.tan(d / 4.0) * r
    parts = ['%s m' % _pts(c[0] + r * math.cos(t), c[1] + r * math.sin(t))]
    for i in range(n):
        t1, t2 = t + i * d, t + (i + 1) * d
        p0 = (c[0] + r * math.cos(t1), c[1] + r * math.sin(t1))
        p3 = (c[0] + r * math.cos(t2), c[1] + r * math.sin(t2))
        parts.append('%s c' % _pts(p0[0] - k * math.sin(t1), p0[1] + k * math.cos(t1),
                                   p3[0] + k * math.sin(t2), p3[1] - k * math.cos(t2), p3[0], p3[1]))
    _stroke(' '.join(parts), w)


def arrow(tip, ang):
    a = math.radians(ang)
    ux, uy = math.cos(a), math.sin(a)
    bx, by = tip[0] - ux * AR_L, tip[1] - uy * AR_L
    nx, ny = -uy * AR_W / 2, ux * AR_W / 2
    ops.append(('%s m %s l %s l h f' % (_pts(*tip), _pts(bx + nx, by + ny), _pts(bx - nx, by - ny))).encode('latin-1'))


def text(p, s, h=2.5, ang=0.0, anchor='middle', bold=False):
    size = h / CAP
    w = em_width(s, bold) * size
    dx = {'middle': -w / 2, 'start': 0.0, 'end': -w}[anchor]
    a = math.radians(ang)
    ca, sa = math.cos(a), math.sin(a)
    x, y = p[0] + dx * ca, p[1] + dx * sa
    TEXT_BOXES.append([(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in ((0, 0), (w, 0), (w, h), (0, h))])
    raw = s.encode('cp1252').replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)')
    ops.append(('BT /%s %s Tf %s Tm (' % ('F2' if bold else 'F1', _f(size), _pts(ca, sa, -sa, ca, x, y))).encode('latin-1')
               + raw + b') Tj ET')


def readable(a):
    """Text angle readable from the bottom or the right of the sheet."""
    a = (a + 180.0) % 360.0 - 180.0
    if a > 90.0:
        a -= 180.0
    elif a <= -90.0:
        a += 180.0
    return a


def text_box(p, s, h, ang, anchor='middle'):
    """Corner points of a text's cap-height box."""
    w = text_w(s, h)
    x0 = {'middle': -w / 2, 'start': 0.0, 'end': -w}[anchor]
    a = math.radians(ang)
    ca, sa = math.cos(a), math.sin(a)
    return [(p[0] + x * ca - y * sa, p[1] + x * sa + y * ca) for x, y in ((x0, 0), (x0 + w, 0), (x0 + w, h), (x0, h))]


# ---------------------------------------------------------------- dimensions
def dim_between(p1, p2, label, h=2.5):
    """Dimension line p1->p2, arrows pointing out to p1 and p2, text above the line."""
    ang = math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))
    line(p1, p2)
    arrow(p1, ang + 180)
    arrow(p2, ang)
    ta = readable(ang)
    up = (-math.sin(math.radians(ta)), math.cos(math.radians(ta)))
    mid = ((p1[0] + p2[0]) / 2 + up[0] * 0.8, (p1[1] + p2[1]) / 2 + up[1] * 0.8)
    text(mid, label, h, ta)
    return text_box(mid, label, h, ta)


def dim_h(p1, p2, yd, label, h=2.5):
    s = -1 if yd < min(p1[1], p2[1]) else 1
    for p in (p1, p2):
        line((p[0], p[1] + s * 0.8), (p[0], yd + s * 2.0))
    return dim_between((p1[0], yd), (p2[0], yd), label, h)


def dim_v(p1, p2, xd, label, h=2.5):
    s = 1 if xd > max(p1[0], p2[0]) else -1
    for p in (p1, p2):
        line((p[0] + s * 0.8, p[1]), (xd + s * 2.0, p[1]))
    return dim_between((xd, p1[1]), (xd, p2[1]), label, h)


def leader(tip, knee, label, h=2.5, side=None):
    """Leader: arrow at tip, straight line to knee, horizontal shoulder carrying the text."""
    ang = math.degrees(math.atan2(tip[1] - knee[1], tip[0] - knee[0]))
    line(knee, tip)
    arrow(tip, ang)
    if side is None:
        side = -1 if knee[0] < tip[0] else 1
    line(knee, (knee[0] + side * (text_w(label, h) + 2.0), knee[1]))
    text((knee[0] + side * 1.0, knee[1] + 0.8), label, h, 0, 'start' if side > 0 else 'end')


def inside_box(pt, box, pad):
    """Point inside a text box (corners counter-clockwise) grown by pad."""
    for i in range(4):
        a, b = box[i], box[(i + 1) % 4]
        L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
        if ((pt[0] - a[0]) * (b[1] - a[1]) - (pt[1] - a[1]) * (b[0] - a[0])) / L > pad:
            return False
    return True


def center_line(p, q, dash='6 1 1 1', pad=0.8):
    """Thin chain line p->q, left out wherever it would cross text."""
    n = max(2, int(math.dist(p, q) / 0.2))
    run = []
    for i in range(n + 1):
        pt = (p[0] + (q[0] - p[0]) * i / n, p[1] + (q[1] - p[1]) * i / n)
        if any(inside_box(pt, b, pad) for b in TEXT_BOXES):
            if len(run) > 1:
                line(run[0], run[-1], W_THIN, dash)
            run = []
        else:
            run.append(pt)
    if len(run) > 1:
        line(run[0], run[-1], W_THIN, dash)


def angle_dim(V, vertex, a1, a2, R, label, h=2.5):
    """Angular dimension: arc of radius R (model) about vertex from a1 to a2 (deg, counter-clockwise)."""
    c, r = V.P(vertex), R * V.s
    arc(c, r, a1, a2 - a1, W_THIN)
    for a, at_end in ((a1, False), (a2, True)):
        t = math.radians(a)
        tangent = math.degrees(math.atan2(math.cos(t), -math.sin(t)))      # counter-clockwise direction
        arrow((c[0] + r * math.cos(t), c[1] + r * math.sin(t)), tangent if at_end else tangent + 180)
    am = math.radians((a1 + a2) / 2)
    out = (math.cos(am), math.sin(am))
    ta = readable(math.degrees(am) + 90)
    up = (-math.sin(math.radians(ta)), math.cos(math.radians(ta)))
    rb = r + 0.8 if up[0] * out[0] + up[1] * out[1] > 0 else r + 0.8 + h   # keep the glyphs outside the arc
    text((c[0] + out[0] * rb, c[1] + out[1] * rb), label, h, ta)
    return TEXT_BOXES[-1]


# ---------------------------------------------------------------- model data
def near(a, b, tol=0.01):
    return abs(a - b) < tol


class View:
    def __init__(self, s, mc, sc):
        self.s, self.mc, self.sc = s, mc, sc

    def P(self, u, v=None):
        if v is None:
            u, v = u
        return (self.sc[0] + self.s * (u - self.mc[0]), self.sc[1] + self.s * (v - self.mc[1]))

    def M(self, x, y):
        return (self.mc[0] + (x - self.sc[0]) / self.s, self.mc[1] + (y - self.sc[1]) / self.s)


def extend_seg(seg):
    """Grow a wall segment to the full run of collinear visible edges it belongs to.

    The export keeps one boundary edge per wall; a wall that meets two floor levels
    has its boundary split, so that edge can be a short piece of the wall."""
    (x1, y1), (x2, y2) = seg
    L = math.hypot(x2 - x1, y2 - y1)
    tx, ty = (x2 - x1) / L, (y2 - y1) / L
    nx, ny = -ty, tx
    off = nx * x1 + ny * y1
    lo, hi = sorted((tx * x1 + ty * y1, tx * x2 + ty * y2))
    runs = []
    for e in G['edges']:
        if e['t'] != 'L':
            continue
        (a1, b1), (a2, b2) = e['p']
        if abs(nx * a1 + ny * b1 - off) < 1e-3 and abs(nx * a2 + ny * b2 - off) < 1e-3:
            runs.append(tuple(sorted((tx * a1 + ty * b1, tx * a2 + ty * b2))))
    grown = True
    while grown:
        grown = False
        for a, b in runs:
            if a <= hi + 1e-3 and b >= lo - 1e-3 and (a < lo - 1e-9 or b > hi + 1e-9):
                lo, hi, grown = min(lo, a), max(hi, b), True
    return [(nx * off + tx * lo, ny * off + ty * lo), (nx * off + tx * hi, ny * off + ty * hi)]


cyl = G['cyl']
d_mag = G['params']['magnet_hole_diameter']['value'] * 10.0
tapped = sorted({(round(c['c'][0], 4), round(c['c'][1], 4)) for c in cyl
                 if c['concave'] and c['full'] and near(c['d'], 2.529, 0.005)})
clover = sorted([c for c in cyl if c['concave'] and not c['full'] and near(c['d'], d_mag) and near(c['y'][0], 1.0)],
                key=lambda c: (-c['c'][1], c['c'][0]))
magnet_tl = [c for c in cyl if c['concave'] and c['full'] and near(c['d'], d_mag) and c['y'][0] > 4.9]
# the through bore; a second, hidden Ø16.2 cut sits 0.5 mm higher on the top side only
bore = next(c for c in cyl if c['concave'] and near(c['d'], 16.2) and c['y'][0] < 1.0)
assert len(tapped) == 10 and len(clover) == 4 and len(magnet_tl) == 1, (len(tapped), len(clover), len(magnet_tl))
magnet_tl = magnet_tl[0]
holes_full = [(c['c'], c['d'] / 2.0) for c in cyl if c['concave'] and c['full']]

for q in G['pairs']:
    q['A'], q['B'] = extend_seg(q['A']), extend_seg(q['B'])
slots = [q for q in G['pairs'] if near(q['gap'], 10.833)]
ribgaps = [q for q in G['pairs'] if near(q['gap'], 3.25)]
channel = next(q for q in slots if near(abs(q['nA'][0]), 1.0, 1e-4))
angled = [q for q in slots if q is not channel]
assert len(slots) == 3 and len(ribgaps) == 2


def pair_frame(q):
    n = q['nA']
    t = (-n[1], n[0])
    oA = n[0] * q['A'][0][0] + n[1] * q['A'][0][1]
    sA = sorted(t[0] * p[0] + t[1] * p[1] for p in q['A'])
    sB = sorted(t[0] * p[0] + t[1] * p[1] for p in q['B'])
    return n, t, oA, (max(sA[0], sB[0]), min(sA[1], sB[1]))


def pair_points(q, s):
    n, t, oA, _ = pair_frame(q)
    pa = (n[0] * oA + t[0] * s, n[1] * oA + t[1] * s)
    return pa, (pa[0] + n[0] * q['gap'], pa[1] + n[1] * q['gap'])


def free_interval(q, extra=(), limits=None, margin=1.0):
    """Largest stretch along the walls that no hole (or extra interval) blocks."""
    n, t, oA, (s0, s1) = pair_frame(q)
    lo, hi = s0 + margin, s1 - margin
    if limits:
        lo, hi = max(lo, limits[0]), min(hi, limits[1])
    ivs = list(extra)
    for cc, r in holes_full:
        on = n[0] * cc[0] + n[1] * cc[1]
        if oA - r < on < oA + q['gap'] + r:
            st = t[0] * cc[0] + t[1] * cc[1]
            rr = THREAD_R if near(2 * r, 2.529, 0.01) else r
            ivs.append((st - rr, st + rr))
    best, cur = None, lo
    for a, b in sorted(ivs):
        a, b = a - 0.2, b + 0.2
        if a > cur and min(a, hi) - cur > (best[1] - best[0] if best else 0):
            best = (cur, min(a, hi))
        cur = max(cur, b)
    if hi - cur > (best[1] - best[0] if best else 0):
        best = (cur, hi)
    assert best, ('no free stretch in slot', q['gap'])
    return best


def slot_dim(V, q, h, extra=(), limits=None):
    n, t, _, _ = pair_frame(q)
    a, b = free_interval(q, extra, limits)
    ta = readable(math.degrees(math.atan2(n[1], n[0])))
    up = (-math.sin(math.radians(ta)), math.cos(math.radians(ta)))
    band, pad = (0.8 + h) / V.s, 0.3
    assert b - a >= band + pad, ('no room for slot text', q['gap'], a, b)
    s = a + pad if up[0] * t[0] + up[1] * t[1] > 0 else b - pad
    pa, pb = pair_points(q, s)
    return dim_between(V.P(pa), V.P(pb), '%s %s' % (('%.3f' % q['gap']).rstrip('0').rstrip('.'), TOL), h)


def edge_samples(step=0.25):
    pts = []
    for e in G['edges']:
        if e['t'] == 'L':
            (x1, y1), (x2, y2) = e['p']
            n = max(2, int(math.hypot(x2 - x1, y2 - y1) / step))
            pts += [(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n) for i in range(n + 1)]
        elif e['t'] in ('C', 'A'):
            a1, sw = (0.0, 360.0) if e['t'] == 'C' else (e['a1'], e['sw'])
            n = max(4, int(abs(math.radians(sw)) * e['r'] / step))
            pts += [(e['c'][0] + e['r'] * math.cos(math.radians(a1 + sw * i / n)),
                     e['c'][1] + e['r'] * math.sin(math.radians(a1 + sw * i / n))) for i in range(n + 1)]
        else:
            pts += [tuple(p) for p in e['p']]
    for c in tapped:
        pts += [(c[0] + THREAD_R * math.cos(math.radians(a)), c[1] + THREAD_R * math.sin(math.radians(a)))
                for a in range(90, 361, 10)]
    return pts


def draw_geometry(V):
    for e in G['edges']:
        if e['t'] == 'L':
            line(V.P(e['p'][0]), V.P(e['p'][1]), W_VIS)
        elif e['t'] == 'C':
            circle(V.P(e['c']), e['r'] * V.s)
        elif e['t'] == 'A':
            arc(V.P(e['c']), e['r'] * V.s, e['a1'], e['sw'])
        else:
            polyline([V.P(p) for p in e['p']])
    for c in tapped:   # ISO 6410 internal thread, end view: thin 3/4 circle at the major diameter
        arc(V.P(c), THREAD_R * V.s, 90.0, 270.0, W_THIN)


def point_on_circle(c, r, ang):
    return (c[0] + r * math.cos(math.radians(ang)), c[1] + r * math.sin(math.radians(ang)))


def on_arc(e, ang):
    a = (ang - e['a1']) % 360.0 if e['sw'] > 0 else (e['a1'] - ang) % 360.0
    return a <= abs(e['sw'])


# ---------------------------------------------------------------- layout
bb0, bb1 = G['bbox']['min'], G['bbox']['max']
MAIN = View(2.0, ((bb0[0] + bb1[0]) / 2, (bb0[2] + bb1[2]) / 2), (125.0, 152.0))
samples = edge_samples()
xs = [p[0] for p in samples]
ys = [p[1] for p in samples]
pL, pR = samples[xs.index(min(xs))], samples[xs.index(max(xs))]
pB, pT = samples[ys.index(min(ys))], samples[ys.index(max(ys))]
# sampling can miss an arc's apex by a few microns; the bounding box is exact
pL, pR = (bb0[0], pL[1]), (bb1[0], pR[1])
pB, pT = (pB[0], bb0[2]), (pT[0], bb1[2])

n_ch, t_ch, o_ch, _ = pair_frame(channel)
ch_mid_u = n_ch[0] * (o_ch + channel['gap'] / 2)
rib_walls = [min((q['A'], q['B']), key=lambda sg: math.dist(sg[0], sg[1])) for q in ribgaps]
rib_v = (min(min(p[1] for p in sg) for sg in rib_walls), max(max(p[1] for p in sg) for sg in rib_walls))
DET_R = 10.0
DET = View(5.0, (ch_mid_u, (rib_v[0] + rib_v[1]) / 2 - 1.8), (318.0, 162.0))

ops.append(b'1 J 1 j 0 G 0 g')

# frame
polyline([(20, 10), (410, 10), (410, 287), (20, 287)], W_FRAME, closed=True)

# --- main view
draw_geometry(MAIN)
taken = []   # model-space boxes the M3 tags must avoid


def take(corners):
    m = [MAIN.M(x, y) for x, y in corners]
    taken.append((min(p[0] for p in m), min(p[1] for p in m), max(p[0] for p in m), max(p[1] for p in m)))


for q in angled:
    take(slot_dim(MAIN, q, 2.5))

# overall size (general tolerance)
take(dim_h(MAIN.P(pL), MAIN.P(pR), MAIN.P(pB)[1] - 10.0, '%.2f' % (pR[0] - pL[0])))
take(dim_v(MAIN.P(pB), MAIN.P(pT), MAIN.P(pR)[0] + 11.0, '%.2f' % (pT[1] - pB[1])))

# magnet pockets and bore
cl = clover[0]                                   # upper-left lobe
tip = point_on_circle(cl['c'], cl['d'] / 2, 150)
leader(MAIN.P(tip), MAIN.P(pL[0] - 2.5, tip[1] + (tip[0] - pL[0] + 2.5) * math.tan(math.radians(30))),
       '4%s %s%.2f %s' % (TIMES, DIA, cl['d'], TOL))
tip = point_on_circle(magnet_tl['c'], magnet_tl['d'] / 2, 120)
knee_v = pT[1] - 2.0
leader(MAIN.P(tip), MAIN.P(tip[0] - (knee_v - tip[1]) / math.tan(math.radians(60)), knee_v),
       '%s%.2f %s' % (DIA, magnet_tl['d'], TOL))
bore_arcs = [e for e in G['edges'] if e['t'] == 'A' and near(e['r'], bore['d'] / 2) and near(e['c'][0], bore['c'][0])
             and near(e['c'][1], bore['c'][1])]
bore_ang = next(a for a in (190, 200, 340, 350, 180, 0, 210, 330) if any(on_arc(e, a) for e in bore_arcs))
tip = point_on_circle(bore['c'], bore['d'] / 2, bore_ang)
side = -1 if math.cos(math.radians(bore_ang)) < 0 else 1
knee_u = pL[0] - 2.5 if side < 0 else pR[0] + 2.5
leader(MAIN.P(tip), MAIN.P(knee_u, tip[1] + (knee_u - tip[0]) * math.tan(math.radians(bore_ang))),
       '%s%.2f %s' % (DIA, bore['d'], TOL))

# threads: callout on the hole nearest the top right, tag on every tapped hole
th = max(tapped, key=lambda c: c[0] + c[1])
tip = point_on_circle(th, THREAD_R, 100)
knee_v = pT[1] + 4.5
leader(MAIN.P(tip), MAIN.P(tip[0] + (knee_v - tip[1]) / math.tan(math.radians(100)), knee_v),
       '10%s M3%s0.5-6H THRU' % (TIMES, TIMES), side=1)

# Ø5 holes of the three Maxwell slots: H1/H2 at the bottom (left, right), H3 at the top, tagged
# P1-P3 on the sheet. Their positions go in a table: a dimension line from H3 would run through the
# two M3 holes beside it.
holes5 = sorted((tuple(c['c']) for c in cyl if c['concave'] and c['full'] and near(c['d'], 5.0)),
                key=lambda p: (p[1], p[0]))
assert len(holes5) == 3, holes5
H1, H2 = sorted(holes5[:2])
H3 = holes5[2]
ex = ((H2[0] - H1[0]) / math.dist(H1, H2), (H2[1] - H1[1]) / math.dist(H1, H2))   # table X: H1 -> H2
ey = (-ex[1], ex[0])
base = math.degrees(math.atan2(ex[1], ex[0]))


def pair_mid(q):
    pts = q['A'] + q['B']
    return (sum(p[0] for p in pts) / 4, sum(p[1] for p in pts) / 4)


def slot_axis_deg(q):
    n = q['nA']
    return math.degrees(math.atan2(n[0], -n[1])) % 180.0      # wall direction (-n_y, n_x)


# slot angles, measured outside the part between the H1-H2 line and each slot's centre line
ANG_R = 8.5
slot_L, slot_R = sorted(angled, key=lambda q: pair_mid(q)[0])
ang_L = (slot_axis_deg(slot_L) - base) % 180.0
ang_R = (180.0 - (slot_axis_deg(slot_R) - base)) % 180.0
axis_L, axis_R = 180.0 + base + ang_L, 360.0 + base - ang_R     # slot centre lines, pointing outwards
for hole, a1, a2, ang in ((H1, 180.0 + base, axis_L, ang_L), (H2, axis_R, 360.0 + base, ang_R)):
    take(angle_dim(MAIN, hole, a1, a2, ANG_R, '%s%s %s0.2%s' % (('%.1f' % ang).rstrip('0').rstrip('.'), DEG, PM, DEG)))

REACH5 = ANG_R + 2.5
cl5 = [((H1[0] - ex[0] * REACH5, H1[1] - ex[1] * REACH5), (H2[0] + ex[0] * REACH5, H2[1] + ex[1] * REACH5)),
       (H1, point_on_circle(H1, REACH5, axis_L)), (H2, point_on_circle(H2, REACH5, axis_R))]
for p_, q_ in cl5:                       # keep tags off these centre lines
    n_ = int(math.dist(p_, q_) / 0.25)
    samples += [(p_[0] + (q_[0] - p_[0]) * i / n_, p_[1] + (q_[1] - p_[1]) * i / n_) for i in range(n_ + 1)]


def place_tag(c, r_clear, label, h, bold=False):
    """Put a short label beside a hole where it crosses the fewest edges and no earlier text."""
    w, ht = text_w(label, h, bold) / MAIN.s, h / MAIN.s
    best = None
    for a in (45, 135, -45, -135, 0, 180, 90, -90):
        ar = math.radians(a)
        d = r_clear + 0.3 + w / 2 * abs(math.cos(ar)) + ht / 2 * abs(math.sin(ar))
        cx, cy = c[0] + math.cos(ar) * d, c[1] + math.sin(ar) * d
        box = (cx - w / 2 - 0.15, cy - ht / 2 - 0.15, cx + w / 2 + 0.15, cy + ht / 2 + 0.15)
        score = sum(1 for x, y in samples if box[0] <= x <= box[2] and box[1] <= y <= box[3])
        score += 1000 * sum(1 for b in taken if not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]))
        if best is None or score < best[0]:
            best = (score, (cx, cy), box)
    taken.append(best[2])
    text(MAIN.P(best[1][0], best[1][1] - ht / 2), label, h, bold=bold)


TAG_H = 2.2
for c in tapped:
    place_tag(c, THREAD_R, 'M3', TAG_H)
for c, lab in ((H1, 'P1'), (H2, 'P2'), (H3, 'P3')):   # P, not H: "H3" next to an "M3" mark reads alike
    place_tag(c, 2.5, lab, 2.5, bold=True)

# centre lines last, so they can leave gaps around every text drawn so far
for p_, q_ in cl5:
    center_line(MAIN.P(p_), MAIN.P(q_))
for hole in (H1, H2, H3):
    for d_ in (ey, ex) if hole is H3 else (ey,):
        center_line(MAIN.P(hole[0] - d_[0] * 4.0, hole[1] - d_[1] * 4.0),
                    MAIN.P(hole[0] + d_[0] * 4.0, hole[1] + d_[1] * 4.0), dash='3 0.8 0.8 0.8')

# detail A marker on the main view; the letter sits in the empty bore just above the circle
circle(MAIN.P(DET.mc), DET_R * MAIN.s, W_THIN)
text(MAIN.P(point_on_circle(DET.mc, DET_R + 1.2, 70)), 'A', 5.0, 0, 'start', bold=True)

# --- detail A (5:1)
ops.append(('q %s W n' % circle_path(DET.sc, DET_R * DET.s)).encode('latin-1'))
draw_geometry(DET)
ops.append(b'Q')
circle(DET.sc, DET_R * DET.s, W_THIN)
text((DET.sc[0], DET.sc[1] - DET_R * DET.s - 9.0), 'A (5 : 1)', 5.0, 0, 'middle', bold=True)

# central slot width: below the rib, inside the circle
rib_s = sorted(t_ch[1] * v for v in rib_v)
reach = math.sqrt(DET_R ** 2 - (channel['gap'] / 2) ** 2) - 0.6
lim = sorted(t_ch[1] * (DET.mc[1] + k * reach) for k in (-1, 1))
slot_dim(DET, channel, 3.0, extra=[tuple(rib_s)], limits=lim)

# gaps either side of the rib: extension lines up into the bore, text above
v_dim = rib_v[1] + 3.0
for q in ribgaps:
    walls = sorted([(sg[0][0], max(sg[0][1], sg[1][1])) for sg in (q['A'], q['B'])])
    (x1, t1), (x2, t2) = walls
    dim_h(DET.P(x1, t1), DET.P(x2, t2), DET.P(0, v_dim)[1], '%.2f %s' % (q['gap'], TOL), 2.5)

# --- notes
NX, NY = 238.0, 280.0
text((NX, NY), 'NOTES', 3.5, 0, 'start', bold=True)
# only what the JLC order form and the STEP can't carry
notes = [
    ['All geometry per the 3D model (STEP). Untoleranced dimensions: ISO 2768-mK.'],
    ['Only the 10 holes marked "M3" are threaded (M3%s0.5-6H, through).' % TIMES,
     'All other holes are plain, not threaded.'],
]
row = 0
for num, lines in enumerate(notes, 1):
    text((NX, NY - 6.5 - row * 4.6), '%d.' % num, 2.5, 0, 'start')
    for s in lines:
        text((NX + 5.5, NY - 6.5 - row * 4.6), s, 2.5, 0, 'start')
        row += 1

# --- Ø5 hole positions (they set the Maxwell coupling geometry, so ±0.05)
HX, HY = 238.0, 254.0
text((HX, HY), '%s5 HOLE POSITIONS  %s0.05 FROM P1' % (DIA, PM), 2.5, 0, 'start', bold=True)
text((HX, HY - 3.6), 'X along P1-P2, Y towards P3', 1.8, 0, 'start')
cols = (HX, HX + 14.0, HX + 33.0, HX + 52.0)
grid = [HY - 6.0 - i * 5.0 for i in range(5)]
for yy in grid:
    line((cols[0], yy), (cols[-1], yy), W_THIN)
for xx in cols:
    line((xx, grid[0]), (xx, grid[-1]), W_THIN)
rows = [('HOLE', 'X', 'Y')]
for lab, p in (('P1', H1), ('P2', H2), ('P3', H3)):
    d = (p[0] - H1[0], p[1] - H1[1])
    rows.append((lab, '%.2f' % (round(d[0] * ex[0] + d[1] * ex[1], 2) + 0.0),
                 '%.2f' % (round(d[0] * ey[0] + d[1] * ey[1], 2) + 0.0)))
for r, cells in enumerate(rows):
    for ci, s in enumerate(cells):
        text(((cols[ci] + cols[ci + 1]) / 2, grid[r] - 3.6), s, 2.5, 0, 'middle', bold=(r == 0))

# --- title block: material and finish live in the JLC order form, so only name, units, scale, date
TX0, TX1, TY0, TY1 = 290.0, 410.0, 10.0, 32.0
polyline([(TX0, TY0), (TX1, TY0), (TX1, TY1), (TX0, TY1)], W_FRAME, closed=True)
line((TX0, 21.0), (TX1, 21.0), W_THIN)
for xx in (320.0, 360.0):
    line((xx, TY0), (xx, 21.0), W_THIN)


def cell(x, y_top, label, value, vh=2.5):
    text((x + 1.5, y_top - 3.0), label, 1.8, 0, 'start')
    text((x + 1.5, y_top - 7.2), value, vh, 0, 'start')


text((TX0 + 2.0, 24.5), 'V2 BACKPLATE', 5.0, 0, 'start', bold=True)
cell(TX0, 21.0, 'UNITS', 'mm')
cell(320.0, 21.0, 'SCALE', '2:1  (A 5:1)')
cell(360.0, 21.0, 'DATE', '2026-09-30')


# ---------------------------------------------------------------- PDF file
def write_pdf(path):
    mm = 72.0 / 25.4
    content = zlib.compress(('%s 0 0 %s 0 0 cm\n' % (_f(mm), _f(mm))).encode('latin-1') + b'\n'.join(ops))
    objs = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        ('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %s %s] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> '
         '/Contents 6 0 R >>' % (_f(SW * mm), _f(SH * mm))).encode('latin-1'),
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>',
        b'<< /Length %d /Filter /FlateDecode >>\nstream\n' % len(content) + content + b'\nendstream',
        b'<< /Title (V2 Backplate 6.11 - JLC CNC drawing) /Producer (render_drawing.py) >>',
    ]
    out = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b'%d 0 obj\n' % i + body + b'\nendobj\n'
    xref = len(out)
    out += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objs) + 1)
    out += b''.join(b'%010d 00000 n \n' % o for o in offsets)
    out += b'trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objs) + 1, len(objs), xref)
    with open(path, 'wb') as fh:
        fh.write(out)


def write_svg(out_path):
    """Same content stream drawn as SVG, for checking the layout in a browser."""
    import html
    import re
    tok = re.compile(rb'\((?:\\.|[^\\)])*\)|\[[^\]]*\]|/[A-Za-z0-9-]+|[-+]?(?:\d+\.?\d*|\.\d+)|[A-Za-z*]+')
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="100%%" height="100%%" viewBox="0 0 %s %s">' % (_f(SW), _f(SH)),
           '<rect width="%s" height="%s" fill="#fff"/>' % (_f(SW), _f(SH))]
    path, w, dash, font, size, tm, groups, clip, nclip = [], W_THIN, '', 'F1', 3.0, None, [], False, 0
    for chunk in ops:
        args = []
        for t in tok.findall(chunk):
            if t[:1] in (b'(', b'[', b'/'):
                args.append(t)
                continue
            try:
                args.append(float(t))
                continue
            except ValueError:
                pass
            op = t.decode()
            if op == 'm':
                path.append('M%s %s' % (_f(args[0]), _f(SH - args[1])))
            elif op == 'l':
                path.append('L%s %s' % (_f(args[0]), _f(SH - args[1])))
            elif op == 'c':
                path.append('C' + ' '.join('%s %s' % (_f(args[i]), _f(SH - args[i + 1])) for i in (0, 2, 4)))
            elif op == 'h':
                path.append('Z')
            elif op == 'w':
                w = args[0]
            elif op == 'd':
                arr = args[0].decode().strip('[]').split()
                dash = ' stroke-dasharray="%s"' % ' '.join(arr) if arr else ''
            elif op == 'S':
                out.append('<path d="%s" fill="none" stroke="#000" stroke-width="%s" stroke-linecap="round" '
                           'stroke-linejoin="round"%s/>' % (' '.join(path), _f(w), dash))
                path = []
            elif op == 'f':
                out.append('<path d="%s" fill="#000"/>' % ' '.join(path))
                path = []
            elif op == 'W':
                clip = True
            elif op == 'n':
                if clip:
                    nclip += 1
                    out.append('<clipPath id="c%d"><path d="%s"/></clipPath><g clip-path="url(#c%d)">'
                               % (nclip, ' '.join(path), nclip))
                    if groups:
                        groups[-1] = True
                    clip = False
                path = []
            elif op == 'q':
                groups.append(False)
            elif op == 'Q':
                if groups and groups.pop():
                    out.append('</g>')
            elif op == 'Tf':
                font, size = args[0].decode()[1:], args[1]
            elif op == 'Tm':
                tm = args[:6]
            elif op == 'Tj':
                s = re.sub(rb'\\(.)', rb'\1', args[0][1:-1]).decode('cp1252')
                a, b, c, d, e, f = tm
                out.append('<text transform="matrix(%s %s %s %s %s %s)" font-family="Helvetica, Arial, sans-serif" '
                           'font-size="%s"%s>%s</text>' % (_f(a), _f(-b), _f(-c), _f(d), _f(e), _f(SH - f), _f(size),
                                                          ' font-weight="bold"' if font == 'F2' else '', html.escape(s)))
            args = []
    out.append('</svg>')
    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(out))


write_pdf(OUT_PDF)
if '--preview' in sys.argv:
    write_svg(os.path.join(os.path.dirname(os.path.abspath(OUT_PDF)), 'preview.svg'))
print('wrote', OUT_PDF, '| tapped', len(tapped), '| bore tip angle', bore_ang, '| rib v', rib_v)
