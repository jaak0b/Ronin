"""Export the pocket-side view of V2 Backplate 6.11 for render_drawing.py.

Runs inside Fusion with the design open. Easiest route: ask Claude to run this file
through the autodesk-fusion MCP server's script tool (it is read-only). It also runs
from Utilities > Scripts and Add-Ins.

Writes backplate_geom.json next to this file. When Fusion runs it from a string (the
MCP script tool, where __file__ is undefined) it writes to DEFAULT_OUT instead.
Nothing in the design is changed.

Exported, in mm, for the FRONT view (X right, Z up, looking at the -Y pocket side):
  edges   every edge of the planar faces facing -Y; on this 2.5D part those are
          exactly the visible edges of the view
  cyl     every cylindrical face: diameter, centre, Y range, full circle or arc
  pairs   facing wall pairs GAPS apart (Maxwell slots, rib gaps), open space between
  params, threads, bbox, and the source document name/version
"""
import json
import math
import os
import traceback

import adsk.core
import adsk.fusion

DEFAULT_OUT = r'E:\Development\CxChanger\Drawing\backplate_geom.json'
OUT = (os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backplate_geom.json')
       if '__file__' in globals() else DEFAULT_OUT)
DOC_PREFIX = 'V2 Backplate 6.11'
GAPS = (10.833, 3.25)       # wall spacings the drawing dimensions: Maxwell slot width, rib gap
MM = 10.0                   # Fusion API lengths are cm
TAU = 2 * math.pi
CT = adsk.core.Curve3DTypes
ST = adsk.core.SurfaceTypes


def P2(pt):
    return [round(pt.x * MM, 4), round(pt.z * MM, 4)]


def arc2d(edge):
    g = edge.geometry
    c = g.center
    ok, t0, t1 = edge.evaluator.getParameterExtents()
    ok, pts = edge.evaluator.getPointsAtParameters([t0, (t0 + t1) / 2.0, t1])
    ang = lambda P: math.atan2(P.z - c.z, P.x - c.x)
    a1, am, a2 = ang(pts[0]), ang(pts[1]), ang(pts[2])
    ccw = (a2 - a1) % TAU
    sw = ccw if ((am - a1) % TAU) <= ccw + 1e-9 else -((a1 - a2) % TAU)
    return {'t': 'A', 'c': P2(c), 'r': round(g.radius * MM, 4), 'a1': round(math.degrees(a1), 4),
            'sw': round(math.degrees(sw), 4)}


def edge2d(e):
    g = e.geometry
    if g.curveType == CT.Line3DCurveType:
        a, b = e.startVertex.geometry, e.endVertex.geometry
        if abs(a.x - b.x) < 1e-7 and abs(a.z - b.z) < 1e-7:
            return None             # parallel to the view direction
        return {'t': 'L', 'p': [P2(a), P2(b)]}
    if g.curveType == CT.Circle3DCurveType:
        return {'t': 'C', 'c': P2(g.center), 'r': round(g.radius * MM, 4)}
    if g.curveType == CT.Arc3DCurveType:
        return arc2d(e)
    ok, t0, t1 = e.evaluator.getParameterExtents()
    ok, pts = e.evaluator.getPointsAtParameters([t0 + (t1 - t0) * i / 40 for i in range(41)])
    return {'t': 'P', 'p': [P2(q) for q in pts]}


def export():
    app = adsk.core.Application.get()
    doc = app.activeDocument
    if not doc.name.startswith(DOC_PREFIX):
        for i in range(app.documents.count):
            d = app.documents.item(i)
            if d.name.startswith(DOC_PREFIX):
                d.activate()
                doc = d
                break
        else:
            raise RuntimeError('open "%s" in Fusion first' % DOC_PREFIX)
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    body = root.bRepBodies.item(0)
    bb = body.boundingBox
    data = {'source': {'name': doc.name, 'version': doc.dataFile.versionNumber},
            'bbox': {'min': [round(bb.minPoint.x * MM, 4), round(bb.minPoint.y * MM, 4), round(bb.minPoint.z * MM, 4)],
                     'max': [round(bb.maxPoint.x * MM, 4), round(bb.maxPoint.y * MM, 4), round(bb.maxPoint.z * MM, 4)]},
            'params': {}, 'edges': [], 'cyl': [], 'pairs': [], 'threads': []}
    for i in range(design.userParameters.count):
        u = design.userParameters.item(i)
        data['params'][u.name] = {'expr': u.expression, 'unit': u.unit, 'value': u.value}

    seen, walls, nfront = set(), [], 0
    for f in body.faces:
        g = f.geometry
        if g.surfaceType == ST.PlaneSurfaceType:
            ok, n = f.evaluator.getNormalAtPoint(f.pointOnFace)
            if n.y < -0.999999:                     # faces the viewer: all its edges are visible
                nfront += 1
                fy = round(f.pointOnFace.y * MM, 4)
                for e in f.edges:
                    if e.tempId in seen:
                        continue
                    seen.add(e.tempId)
                    d2 = edge2d(e)
                    if d2:
                        d2['y'] = fy
                        data['edges'].append(d2)
            elif abs(n.y) < 1e-6:                   # side wall
                seg = None
                for e in f.edges:
                    if e.geometry.curveType == CT.Line3DCurveType:
                        a, b = e.startVertex.geometry, e.endVertex.geometry
                        if abs(a.y - b.y) < 1e-7:
                            seg = [P2(a), P2(b)]
                            break
                pt = f.pointOnFace
                walls.append({'n': [n.x, n.z], 'off': (n.x * pt.x + n.z * pt.z) * MM, 'seg': seg,
                              'y': [f.boundingBox.minPoint.y * MM, f.boundingBox.maxPoint.y * MM]})
        elif g.surfaceType == ST.CylinderSurfaceType:
            cyl = adsk.core.Cylinder.cast(g)
            pt = f.pointOnFace
            ok, n = f.evaluator.getNormalAtPoint(pt)
            ax = cyl.axis.copy()
            ax.normalize()
            v = cyl.origin.vectorTo(pt)
            al = v.dotProduct(ax)
            rad = adsk.core.Vector3D.create(v.x - ax.x * al, v.y - ax.y * al, v.z - ax.z * al)
            arcs = [arc2d(e) for e in f.edges if e.geometry.curveType == CT.Arc3DCurveType]
            data['cyl'].append({'d': round(2 * cyl.radius * MM, 4), 'c': P2(cyl.origin),
                                'concave': rad.dotProduct(n) < 0,
                                'full': any(e.geometry.curveType == CT.Circle3DCurveType for e in f.edges),
                                'y': [round(f.boundingBox.minPoint.y * MM, 4), round(f.boundingBox.maxPoint.y * MM, 4)],
                                'arc': arcs[0] if arcs else None})

    for i, A in enumerate(walls):
        for B in walls[i + 1:]:
            if abs(A['n'][0] + B['n'][0]) > 1e-6 or abs(A['n'][1] + B['n'][1]) > 1e-6:
                continue
            gap = -(A['off'] + B['off'])            # > 0: open space between the two walls
            if not any(abs(gap - gp) < 0.01 for gp in GAPS):
                continue
            if min(A['y'][1], B['y'][1]) - max(A['y'][0], B['y'][0]) <= 1e-4 or not A['seg'] or not B['seg']:
                continue
            tx, tz = -A['n'][1], A['n'][0]
            sa = sorted(q[0] * tx + q[1] * tz for q in A['seg'])
            sb = sorted(q[0] * tx + q[1] * tz for q in B['seg'])
            if min(sa[1], sb[1]) - max(sa[0], sb[0]) <= 1e-4:
                continue
            data['pairs'].append({'gap': round(gap, 4), 'A': A['seg'], 'B': B['seg'],
                                  'nA': [round(A['n'][0], 6), round(A['n'][1], 6)]})

    tfs = root.features.threadFeatures
    for i in range(tfs.count):
        t = tfs.item(i)
        data['threads'].append({'name': t.name, 'designation': t.threadInfo.threadDesignation,
                                'class': t.threadInfo.threadClass, 'internal': t.threadInfo.isInternal,
                                'fullLength': t.isFullLength, 'suppressed': t.isSuppressed})

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as fh:
        json.dump(data, fh)
    return ('%s | %d front faces, %d edges, %d cylinders, pairs %s | wrote %s'
            % (doc.name, nfront, len(data['edges']), len(data['cyl']),
               sorted(q['gap'] for q in data['pairs']), OUT))


def run(context):
    try:
        print(export())
    except Exception:
        print(traceback.format_exc())
