#Author-Jan Mrázek, updated by sophusand / Fysik Klubben
#Description-Import a wind turbine blade (QBlade .bld + .afl, or one combined .json) into Fusion 360 as a single solid body.

"""
YBlade v3 -- import a wind turbine blade into Fusion 360 as one solid body.

Input is either
  * a QBlade blade file (.bld, QBlade CE 2.x or v0.963) plus the airfoil it
    uses (.afl), or
  * one combined .json file that holds the stations and the section outline,
    optionally a different outline per station (see README.md).

Every station becomes its own sketch on its own construction plane, and the
blade is one loft through all of them. The file-reading and geometry code
above the "Fusion" line does not touch the Fusion API, so it can be tested
outside Fusion (see tests/).
"""

import html
import json
import math
import os
import traceback

import adsk.core
import adsk.fusion

VERSION = '3.0.0'
CMD_ID = 'YBladeV3Import'
CMD_NAME = 'YBlade v3: import blade'

# Fusion works in centimetres internally.
UNIT_TO_CM = {'meter': 100.0, 'decimeter': 10.0, 'centimeter': 1.0, 'millimeter': 0.1}
UNIT_ALIASES = {'m': 'meter', 'meters': 'meter', 'metre': 'meter', 'dm': 'decimeter',
                'cm': 'centimeter', 'mm': 'millimeter', 'millimeters': 'millimeter'}

# A closing line shorter than this between the two trailing-edge ends cannot
# form a closed sketch profile, whatever the user asks for.
MIN_TE_GAP_CM = 0.002

handlers = []
_last_folder = ''


class Station:
    """One blade section. Lengths in cm, angles in degrees."""

    def __init__(self, pos, chord, twist, p_axis=0.25, offset_x=0.0, offset_y=0.0,
                 points=None, foil=''):
        self.pos = pos
        self.chord = chord
        self.twist = twist
        self.p_axis = p_axis
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.points = points        # own outline (unit chord), or None for the shared one
        self.foil = foil


class BladeData:
    """Everything read from the input files, plus notes worth showing the user."""

    def __init__(self, stations, outline, name, notes):
        self.stations = stations
        self.outline = outline      # shared outline (unit chord); None if every station has its own
        self.name = name
        self.notes = notes


# ===================================================================== reading files

def _unit_factor(unit, default='meter'):
    key = (unit or default).strip().lower()
    key = UNIT_ALIASES.get(key, key)
    if key not in UNIT_TO_CM:
        raise ValueError(f'Unknown unit "{unit}". Use meter, decimeter, centimeter or millimeter.')
    return UNIT_TO_CM[key]


def parse_afl_lines(lines):
    """Airfoil coordinates from an .afl/.dat file: Selig format (one loop from
    the trailing edge over the top to the nose and back along the bottom) or
    Lednicer format (top and bottom as two runs from the nose, after a line
    with the point counts)."""
    rows = []
    for line in lines:
        tokens = line.replace(',', ' ').split()
        if len(tokens) < 2:
            continue
        try:
            rows.append((float(tokens[0]), float(tokens[1])))
        except ValueError:
            continue                # the name line, or a comment
    if not rows:
        raise ValueError('The airfoil file contains no coordinates.')

    if rows[0][0] > 1.5 and rows[0][1] > 1.5:
        # Lednicer: "n_upper n_lower", then the upper and the lower surface,
        # both running from the leading edge to the trailing edge.
        n_up, n_lo = int(round(rows[0][0])), int(round(rows[0][1]))
        upper, lower = rows[1:1 + n_up], rows[1 + n_up:1 + n_up + n_lo]
        if len(upper) != n_up or len(lower) != n_lo:
            raise ValueError('The airfoil file looks like Lednicer format, but the point '
                             'counts in its header do not match the data.')
        rows = list(reversed(upper)) + lower[1:]
    return rows


def read_afl(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return parse_afl_lines(f.readlines())
    except OSError as err:
        raise ValueError(f'Could not read the airfoil file: {err}')


def parse_bld_lines(lines, unit='meter'):
    """Stations from a QBlade blade file, and notes about what was left out.

    QBlade CE 2.x: POS CHORD TWIST OFFSET_X OFFSET_Y P_AXIS POLAR_FILE
    QBlade v0.963: POS CHORD TWIST OFFSET P_AXIS (data from line 4)
    """
    k = _unit_factor(unit)
    new_format, start = False, 3
    for i, line in enumerate(lines):
        if 'Blade Data' in line:
            new_format = True
            for j in range(i + 1, len(lines)):
                if 'POS_[m]' in lines[j]:
                    start = j + 1
                    break
            break

    stations, circular, foil_count = [], 0, {}
    any_offset = False
    for line in lines[start:]:
        tokens = line.split()
        if len(tokens) < 5 or line.strip().startswith('-'):
            continue
        try:
            pos, chord, twist = float(tokens[0]) * k, float(tokens[1]) * k, float(tokens[2])
            if new_format:
                if len(tokens) < 6:
                    continue
                ox, oy, p_axis = float(tokens[3]) * k, float(tokens[4]) * k, float(tokens[5])
                foil = ' '.join(tokens[6:])
            else:
                ox, oy, p_axis = float(tokens[3]) * k, 0.0, float(tokens[4])
                foil = ''
        except ValueError:
            continue
        if 'circular' in foil.lower():
            circular += 1           # a cylinder root section, not an airfoil
            continue
        if foil:
            foil_count[foil] = foil_count.get(foil, 0) + 1
        any_offset = any_offset or abs(ox) > 1e-9 or abs(oy) > 1e-9
        stations.append(Station(pos, chord, twist, p_axis, ox, oy, None, foil))

    notes = []
    if circular:
        notes.append(f'Skipped {circular} circular root section(s). The blade starts at the first '
                     f'airfoil section; model the root fitting yourself.')
    if len(foil_count) > 1:
        main = max(foil_count, key=foil_count.get)
        notes.append(f'The blade uses {len(foil_count)} different airfoil polars. Every section gets '
                     f'the shape from the airfoil file you chose (most sections use '
                     f'{os.path.basename(main)}).')
    if any_offset:
        notes.append('The blade file has offsets (sweep or prebend). They are ignored: every '
                     'section is stacked on its pitch axis.')
    return stations, notes


def read_bld(path, unit='meter'):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return parse_bld_lines(f.readlines(), unit)
    except OSError as err:
        raise ValueError(f'Could not read the blade file: {err}')


def parse_json(data, unit=None):
    """Stations and outline(s) from the combined format (see README.md)."""
    meta = data.get('meta') or {}
    k = _unit_factor(unit or meta.get('units'), 'meter')

    shared = None
    airfoil = data.get('airfoil') or {}
    if airfoil.get('coordinates'):
        shared = parse_afl_lines(f'{x} {y}' for x, y in airfoil['coordinates'])

    rows = data.get('blade') or []
    if len(rows) < 2:
        raise ValueError('The file needs at least two stations under "blade".')

    stations, notes, own = [], [], 0
    any_offset = False
    for n, row in enumerate(rows, start=1):
        try:
            points = None
            if row.get('points'):
                points = parse_afl_lines(f'{x} {y}' for x, y in row['points'])
                own += 1
            elif shared is None:
                raise ValueError('it has no "points" and the file has no shared "airfoil"')
            ox = float(row.get('offset_x', 0.0)) * k
            oy = float(row.get('offset_y', 0.0)) * k
            any_offset = any_offset or abs(ox) > 1e-9 or abs(oy) > 1e-9
            stations.append(Station(float(row['pos']) * k, float(row['chord']) * k,
                                    float(row['twist']), float(row.get('p_axis', 0.25)),
                                    ox, oy, points))
        except (KeyError, TypeError, ValueError) as err:
            raise ValueError(f'Station {n} in the file is not valid: {err}')

    if own:
        notes.append(f'{own} of {len(stations)} stations have their own section outline.')
    if any_offset:
        notes.append('The file has offsets (sweep or prebend). They are ignored: every section '
                     'is stacked on its pitch axis.')
    return BladeData(stations, shared, meta.get('name') or '', notes)


def read_json(path, unit=None):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except OSError as err:
        raise ValueError(f'Could not read the file: {err}')
    except ValueError as err:
        raise ValueError(f'The file is not valid JSON: {err}')
    blade = parse_json(data, unit)
    if not blade.name:
        blade.name = os.path.splitext(os.path.basename(path))[0]
    return blade


def load_blade(blade_path, airfoil_path=None, unit=None):
    """Read the input files into a BladeData. `unit` None means: from the file
    (.json meta.units, else metres; QBlade files are always in metres)."""
    if blade_path.lower().endswith('.json'):
        return read_json(blade_path, unit)
    if not airfoil_path:
        raise ValueError('A QBlade blade file needs an airfoil file (.afl) as well.')
    outline = read_afl(airfoil_path)
    stations, notes = read_bld(blade_path, unit or 'meter')
    if len(stations) < 2:
        raise ValueError('Found fewer than two airfoil sections in the blade file.')
    name = os.path.splitext(os.path.basename(blade_path))[0]
    return BladeData(stations, outline, name, notes)


# ================================================================= section geometry

def clean_outline(points):
    """Drop repeated points (a doubled nose point makes the sketch spline fail)
    and turn the loop so it runs trailing edge -> top -> nose -> bottom."""
    pts = [points[0]]
    for p in points[1:]:
        if abs(p[0] - pts[-1][0]) > 1e-9 or abs(p[1] - pts[-1][1]) > 1e-9:
            pts.append(p)
    if len(pts) < 5:
        raise ValueError('The section outline has fewer than five distinct points.')
    area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))
    if area < 0:
        pts.reverse()               # bottom surface first -> flip to top first
    return pts


def _nose(pts):
    return min(range(len(pts)), key=lambda i: (pts[i][0], abs(pts[i][1])))


def thicken_trailing_edge(pts, gap):
    """Open the trailing edge to at least `gap` (fraction of chord).

    The extra thickness is added to the aft part of the section only (it grows
    with x**3 from the nose), so the nose and the front of the section keep
    their shape. A real gap is also what lets the trailing edge close with a
    proper line, and what a 3D printer can actually make.
    """
    now = pts[0][1] - pts[-1][1]
    if now >= gap:
        return list(pts)
    add = (gap - now) / 2.0
    i_nose = _nose(pts)
    x0 = pts[i_nose][0]
    span = max(max(p[0] for p in pts) - x0, 1e-9)
    out = []
    for i, (x, y) in enumerate(pts):
        w = max(0.0, (x - x0) / span) ** 3
        if i < i_nose:
            out.append((x, y + add * w))
        elif i > i_nose:
            out.append((x, y - add * w))
        else:
            out.append((x, y))
    return out


def _surface_y(run, x):
    """y on one surface at x. `run` goes from the nose to the trailing edge."""
    for (x0, y0), (x1, y1) in zip(run, run[1:]):
        if min(x0, x1) <= x <= max(x0, x1) and abs(x1 - x0) > 1e-12:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return min(run, key=lambda p: abs(p[0] - x))[1]


def mid_thickness(pts, x):
    """Middle between the top and the bottom surface at chord position x."""
    i = _nose(pts)
    top = list(reversed(pts[:i + 1]))
    bottom = pts[i:]
    return 0.5 * (_surface_y(top, x) + _surface_y(bottom, x))


def station_outline(station, shared, te_gap_cm):
    """The station's outline in its sketch plane, in cm: pitch axis at the
    origin, the section centred on its own thickness there, turned by the
    twist. Returns (points, whether the trailing edge had to be opened)."""
    pts = clean_outline(station.points or shared)
    gap = max(te_gap_cm, MIN_TE_GAP_CM) / station.chord
    opened = pts[0][1] - pts[-1][1] < gap - 1e-12
    pts = thicken_trailing_edge(pts, gap)
    c, p = station.chord, station.p_axis
    dy = -mid_thickness(pts, p) * c
    t = math.radians(station.twist)
    ct, st = math.cos(t), math.sin(t)
    out = []
    for x, y in pts:
        px, py = x * c - p * c, y * c + dy
        out.append((px * ct - py * st, px * st + py * ct))
    return out, opened


def thin_stations(zs, outlines, tolerance_cm):
    """Indices of the stations worth keeping.

    A station is left out when blending its two neighbours puts every point of
    its outline within `tolerance_cm` of where it should be -- the loft between
    the remaining stations then passes it anyway. Stations where the shape
    bends are kept. (Douglas-Peucker on whole outlines.)
    """
    n = len(zs)
    if n <= 2 or tolerance_cm <= 0:
        return list(range(n))
    if len({len(o) for o in outlines}) != 1:
        return list(range(n))      # outlines do not correspond point by point

    def worst(a, b):
        best, where = -1.0, None
        za, zb = zs[a], zs[b]
        for k in range(a + 1, b):
            t = (zs[k] - za) / (zb - za)
            dev = 0.0
            for (xa, ya), (xb, yb), (xk, yk) in zip(outlines[a], outlines[b], outlines[k]):
                ex = xk - (xa + t * (xb - xa))
                ey = yk - (ya + t * (yb - ya))
                dev = max(dev, ex * ex + ey * ey)
            if dev > best:
                best, where = dev, k
        return math.sqrt(best), where

    keep = {0, n - 1}
    todo = [(0, n - 1)]
    while todo:
        a, b = todo.pop()
        if b - a < 2:
            continue
        dev, k = worst(a, b)
        if dev > tolerance_cm:
            keep.add(k)
            todo += [(a, k), (k, b)]
    return sorted(keep)


class Plan:
    """What will be built: the kept stations, their outlines, and notes."""

    def __init__(self, zs, outlines, total, opened, notes):
        self.zs = zs
        self.outlines = outlines
        self.used = len(zs)
        self.total = total
        self.opened = opened        # stations whose trailing edge had to be opened
        self.notes = notes


def plan_blade(blade, te_gap_cm, tolerance_cm, start_at_zero):
    st = sorted(blade.stations, key=lambda s: s.pos)
    for a, b in zip(st, st[1:]):
        if b.pos - a.pos < 1e-6:
            raise ValueError(f'Two stations sit at the same radius ({a.pos * 10:.2f} mm).')
    for s in st:
        if s.chord <= 0:
            raise ValueError(f'The station at {s.pos * 10:.1f} mm has no chord.')
    shift = st[0].pos if start_at_zero else 0.0
    zs, outlines, opened = [], [], 0
    for s in st:
        pts, was_opened = station_outline(s, blade.outline, te_gap_cm)
        zs.append(s.pos - shift)
        outlines.append(pts)
        opened += was_opened
    keep = thin_stations(zs, outlines, tolerance_cm)
    notes = list(blade.notes)
    if len({len(o) for o in outlines}) != 1:
        notes.append('The section outlines have different point counts, so no stations were '
                     'left out. The loft may twist between them.')
    return Plan([zs[i] for i in keep], [outlines[i] for i in keep], len(st), opened, notes)


def edge_points(outline):
    """(leading edge, middle of the trailing edge) of one placed outline. The
    leading edge is the point farthest from the trailing edge."""
    te = ((outline[0][0] + outline[-1][0]) / 2.0, (outline[0][1] + outline[-1][1]) / 2.0)
    le = max(outline, key=lambda p: (p[0] - te[0]) ** 2 + (p[1] - te[1]) ** 2)
    return le, te


def describe(plan, te_gap_cm):
    lines = [f'{plan.used} of {plan.total} stations used (the rest lie within the tolerance).',
             f'Blade length {(plan.zs[-1] - plan.zs[0]) * 10:.1f} mm.']
    if plan.opened:
        lines.append(f'Trailing edge opened to {max(te_gap_cm, MIN_TE_GAP_CM) * 10:.2f} mm '
                     f'on {plan.opened} of {plan.total} stations.')
    return lines + plan.notes


# ============================================================================ Fusion

def _name(entity, name):
    """Naming is cosmetic; never let it stop an import."""
    try:
        entity.name = name
    except Exception:
        pass


def _progress(dialog, value, message):
    if dialog:
        dialog.progressValue = value
        dialog.message = message
        adsk.doEvents()


def build_blade(design, comp, plan, name, guide_rails=False, center_mass=False, dialog=None):
    """Sketches, construction planes and the loft. Returns (body, summary lines)."""
    timeline = None
    if design.designType == adsk.fusion.DesignTypes.ParametricDesignType:
        timeline = design.timeline
        start = timeline.markerPosition

    planes, sketches = comp.constructionPlanes, comp.sketches
    xy = comp.xYConstructionPlane
    made_planes, made_sketches, profiles = [], [], []
    n = len(plan.zs)

    for i, (z, outline) in enumerate(zip(plan.zs, plan.outlines)):
        _progress(dialog, 1 + int(7 * i / n), f'Station {i + 1} of {n}...')
        if abs(z) < 1e-9:
            plane = xy
        else:
            pin = planes.createInput()
            pin.setByOffset(xy, adsk.core.ValueInput.createByReal(z))
            plane = planes.add(pin)
            _name(plane, f'{name} station {i + 1}')
            made_planes.append(plane)
        sketch = sketches.add(plane)
        _name(sketch, f'{name} station {i + 1}')
        made_sketches.append(sketch)

        sketch.isComputeDeferred = True
        pts = adsk.core.ObjectCollection.create()
        for x, y in outline:
            pts.add(adsk.core.Point3D.create(x, y, 0))
        spline = sketch.sketchCurves.sketchFittedSplines.add(pts)
        sketch.sketchCurves.sketchLines.addByTwoPoints(spline.startSketchPoint, spline.endSketchPoint)
        sketch.isComputeDeferred = False
        if sketch.profiles.count != 1:
            raise RuntimeError(f'Station {i + 1} (z = {z * 10:.1f} mm) gave {sketch.profiles.count} '
                               f'closed regions instead of one. Check the airfoil file.')
        profiles.append(sketch.profiles.item(0))

    _progress(dialog, 8, 'Lofting the blade...')
    lofts = comp.features.loftFeatures
    loft_in = lofts.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    for profile in profiles:
        loft_in.loftSections.add(profile)
    loft_in.isSolid = True
    try:
        loft = lofts.add(loft_in)
    except RuntimeError as err:
        raise RuntimeError(f'Fusion could not loft through the {n} stations:\n{err}\n\n'
                           f'Try a larger "Trailing edge" or a larger "Tolerance" setting.')
    body = loft.bodies.item(0)
    _name(body, name)

    if guide_rails:
        guide = sketches.add(xy)
        _name(guide, f'{name} leading and trailing edge')
        le_pts, te_pts = adsk.core.ObjectCollection.create(), adsk.core.ObjectCollection.create()
        for z, outline in zip(plan.zs, plan.outlines):
            le, te = edge_points(outline)
            le_pts.add(adsk.core.Point3D.create(le[0], le[1], z))
            te_pts.add(adsk.core.Point3D.create(te[0], te[1], z))
        guide.sketchCurves.sketchFittedSplines.add(le_pts)
        guide.sketchCurves.sketchFittedSplines.add(te_pts).isConstruction = True

    summary = []
    if center_mass:
        _progress(dialog, 9, 'Moving the blade...')
        com = body.physicalProperties.centerOfMass
        lowest = body.boundingBox.minPoint.z
        move = adsk.core.Matrix3D.create()
        move.translation = adsk.core.Vector3D.create(-com.x, -com.y, -lowest)
        bodies = adsk.core.ObjectCollection.create()
        bodies.add(body)
        moves = comp.features.moveFeatures
        if hasattr(moves, 'createInput2'):
            move_in = moves.createInput2(bodies)
            move_in.defineAsFreeMove(move)
        else:
            move_in = moves.createInput(bodies, move)
        moves.add(move_in)
        summary.append('Moved so the centre of mass is on the Z axis and the root at Z = 0.')

    for s in made_sketches:
        s.isLightBulbOn = False
    for p in made_planes:
        p.isLightBulbOn = False

    if timeline is not None and timeline.markerPosition - 1 > start:
        group = timeline.timelineGroups.add(start, timeline.markerPosition - 1)
        _name(group, f'YBlade: {name}')
    return body, summary


# ---------------------------------------------------------------------- command UI
#
# Fusion gives the labels about a third of the dialog's width and cuts off
# anything longer, so the labels are short and the explanations sit in the
# tooltips. File names are shown in text boxes across the full width instead of
# whole paths in narrow fields.

DIALOG_SIZE = (480, 640)
DIALOG_MIN_SIZE = (420, 520)

_files = {'blade': '', 'airfoil': ''}
_ui = {}                # the dialog's inputs by id, kept so nothing has to be looked up


def _esc(text):
    return html.escape(str(text), quote=False)


def _file_html(path, empty):
    if not path:
        return f'<i>{_esc(empty)}</i>'
    folder = os.path.basename(os.path.dirname(path)) or os.path.dirname(path)
    return f'<b>{_esc(os.path.basename(path))}</b><br>in folder {_esc(folder)}'


def _set_status(title, lines=()):
    body = ''.join(f'<br>&bull; {_esc(line)}' for line in lines)
    _ui['status'].formattedText = f'<b>{_esc(title)}</b>{body}'


def _options():
    unit = _ui['unit'].selectedItem.name
    return {
        'blade': _files['blade'],
        'airfoil': _files['airfoil'],
        'unit': None if unit == 'Auto' else unit,
        'te_gap': _ui['teGap'].value,          # cm
        'tolerance': _ui['tolerance'].value,   # cm
        'start_at_zero': _ui['startAtZero'].value,
        'center_mass': _ui['centerMass'].value,
        'guide_rails': _ui['guideRails'].value,
    }


def _refresh():
    """Show the chosen files and what will be built, before Import is pressed."""
    o = _options()
    is_json = o['blade'].lower().endswith('.json')
    _ui['bladeFile'].formattedText = _file_html(o['blade'], 'No blade file chosen yet.')
    _ui['airfoilFile'].formattedText = _file_html(o['airfoil'], 'No airfoil file chosen yet.')
    for iid in ('airfoilBrowse', 'airfoilFile'):
        _ui[iid].isVisible = not is_json        # a .json carries its own airfoil
    if not o['blade']:
        _set_status('Choose a blade file.',
                    ['QBlade: the blade (.bld), then its airfoil (.afl).',
                     'QBlade esay / Vindmølle Designer: the .json export alone.'])
        return
    if not is_json and not o['airfoil']:
        _set_status('Now choose the airfoil file (.afl) the blade uses.')
        return
    try:
        blade = load_blade(o['blade'], o['airfoil'], o['unit'])
        plan = plan_blade(blade, o['te_gap'], o['tolerance'], o['start_at_zero'])
        _set_status(f'Ready to import "{blade.name}"', describe(plan, o['te_gap']))
    except Exception as err:
        _set_status('Problem with the file:', [str(err)])


def _browse(ui, title, file_filter):
    global _last_folder
    dlg = ui.createFileDialog()
    dlg.isMultiSelectEnabled = False
    dlg.title = title
    dlg.filter = file_filter
    if _last_folder:
        dlg.initialDirectory = _last_folder
    if dlg.showOpen() != adsk.core.DialogResults.DialogOK:
        return None
    _last_folder = os.path.dirname(dlg.filename)
    return dlg.filename


class ExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        app = adsk.core.Application.get()
        ui = app.userInterface
        dialog = None
        try:
            # Fetched here, not when the script started: the user may have
            # switched documents in between.
            design = adsk.fusion.Design.cast(app.activeProduct)
            if not design:
                raise RuntimeError('Open a design (the Design workspace) first.')
            o = _options()
            dialog = ui.createProgressDialog()
            dialog.isCancelButtonShown = False
            dialog.show('YBlade', 'Reading the files...', 0, 10)
            blade = load_blade(o['blade'], o['airfoil'], o['unit'])
            plan = plan_blade(blade, o['te_gap'], o['tolerance'], o['start_at_zero'])
            body, extra = build_blade(design, design.activeComponent, plan, blade.name,
                                      o['guide_rails'], o['center_mass'], dialog)
            dialog.hide()
            dialog = None
            ui.messageBox('\n'.join([f'Blade "{body.name}" created.', '']
                                    + ['- ' + line for line in describe(plan, o['te_gap']) + extra]),
                          'YBlade v' + VERSION)
        except Exception as err:
            if dialog:
                dialog.hide()
            ui.messageBox(f'Import failed:\n\n{err}', 'YBlade v' + VERSION)


class InputChangedHandler(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        ui = adsk.core.Application.get().userInterface
        try:
            changed = args.input
            if changed.id in ('status', 'bladeFile', 'airfoilFile'):
                return
            if changed.id == 'bladeBrowse':
                changed.value = False   # a button: reset it, whatever Fusion set it to
                path = _browse(ui, 'Blade file (.bld or .json)',
                               'Blade files (*.bld *.json);;All files (*.*)')
                if path:
                    _files['blade'] = path
            elif changed.id == 'airfoilBrowse':
                changed.value = False
                path = _browse(ui, 'Airfoil file (.afl)',
                               'Airfoil files (*.afl *.dat *.txt);;All files (*.*)')
                if path:
                    _files['airfoil'] = path
            _refresh()
        except Exception:
            ui.messageBox(traceback.format_exc(), 'YBlade v' + VERSION)


class ValidateHandler(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        blade = _files['blade']
        args.areInputsValid = bool(blade) and (blade.lower().endswith('.json') or bool(_files['airfoil']))


class DestroyHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        adsk.terminate()            # the script set autoTerminate(False), so it ends itself here


def _tip(item, short, long=''):
    item.tooltip = short
    if long:
        item.tooltipDescription = long
    return item


class CreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        ui = adsk.core.Application.get().userInterface
        try:
            cmd = args.command
            for event, handler in ((cmd.execute, ExecuteHandler()),
                                   (cmd.inputChanged, InputChangedHandler()),
                                   (cmd.validateInputs, ValidateHandler()),
                                   (cmd.destroy, DestroyHandler())):
                event.add(handler)
                handlers.append(handler)

            cmd.okButtonText = 'Import'
            try:
                cmd.setDialogInitialSize(*DIALOG_SIZE)
                cmd.setDialogMinimumSize(*DIALOG_MIN_SIZE)
            except Exception:
                pass                # older Fusion: default size

            _files.update(blade='', airfoil='')
            _ui.clear()
            inputs = cmd.commandInputs

            def keep(item):
                _ui[item.id] = item
                return item

            def text_box(parent, iid, rows):
                box = keep(parent.addTextBoxCommandInput(iid, '', '', rows, True))
                box.isFullWidth = True
                return box

            def button(parent, iid, label, tip, long):
                btn = keep(parent.addBoolValueInput(iid, label, False, '', False))
                btn.isFullWidth = True
                return _tip(btn, tip, long)

            files = inputs.addGroupCommandInput('files', 'Files')
            files.isExpanded = True
            f = files.children
            button(f, 'bladeBrowse', 'Choose blade file...', 'Blade file',
                   'A QBlade blade file (.bld), or a .json exported by QBlade esay / '
                   'Vindmølle Designer (which also holds the airfoil).')
            text_box(f, 'bladeFile', 2)
            button(f, 'airfoilBrowse', 'Choose airfoil file...', 'Airfoil file',
                   'The airfoil (.afl) the QBlade blade uses. QBlade: Airfoil Design, '
                   'select the airfoil, Export. Not needed for a .json file.')
            text_box(f, 'airfoilFile', 2)

            settings = inputs.addGroupCommandInput('settings', 'Settings')
            settings.isExpanded = True
            s = settings.children
            _tip(keep(s.addValueInput('teGap', 'Trailing edge', 'mm',
                                      adsk.core.ValueInput.createByString('0.5 mm'))),
                 'Minimum trailing edge thickness',
                 'The trailing edge is opened to at least this thickness. A sharp edge '
                 'cannot be lofted or printed; 0.5 mm suits a 0.4 mm nozzle.')
            _tip(keep(s.addValueInput('tolerance', 'Tolerance', 'mm',
                                      adsk.core.ValueInput.createByString('0.05 mm'))),
                 'Station tolerance',
                 'A station is left out when the blade would move less than this without it. '
                 '0 keeps every station.')
            unit = keep(s.addDropDownCommandInput('unit', 'Units',
                                                  adsk.core.DropDownStyles.TextListDropDownStyle))
            for label in ('Auto', 'Meter', 'Decimeter', 'Centimeter', 'Millimeter'):
                unit.listItems.add(label, label == 'Auto')
            _tip(unit, 'Units in the file',
                 'Auto: metres for QBlade files, the "units" field for .json files. '
                 'Choose a unit only if your file uses something else.')
            _tip(keep(s.addBoolValueInput('startAtZero', 'Root at Z = 0', True, '', True)),
                 'Start the blade at Z = 0',
                 'Untick to keep the blade at its real distance from the rotor centre, '
                 'e.g. to pattern three blades around the Y axis.')
            _tip(keep(s.addBoolValueInput('centerMass', 'Centre mass on Z', True, '', False)),
                 'Centre of mass on the Z axis',
                 'Moves the finished blade so its centre of mass is on the Z axis and the root at Z = 0.')
            _tip(keep(s.addBoolValueInput('guideRails', 'Edge sketches', True, '', False)),
                 'Sketch the leading and trailing edge',
                 'Draws the leading edge (solid) and the trailing edge (dashed) as splines, '
                 'handy for modelling a tip or a root fitting.')

            preview = inputs.addGroupCommandInput('preview', 'What will be built')
            preview.isExpanded = True
            text_box(preview.children, 'status', 8)
            _refresh()
        except Exception:
            ui.messageBox(traceback.format_exc(), 'YBlade v' + VERSION)


def run(context):
    ui = None
    try:
        ui = adsk.core.Application.get().userInterface
        old = ui.commandDefinitions.itemById(CMD_ID)
        if old:
            old.deleteMe()          # left over from a run that did not end cleanly
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, 'Import a wind turbine blade as one solid body.', './resources')
        on_created = CreatedHandler()
        cmd_def.commandCreated.add(on_created)
        handlers.append(on_created)
        cmd_def.execute()
        adsk.autoTerminate(False)   # keep the script alive until the dialog closes
    except Exception:
        if ui:
            ui.messageBox(traceback.format_exc(), 'YBlade v' + VERSION)


def stop(context):
    try:
        ui = adsk.core.Application.get().userInterface
        cmd_def = ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()
    except Exception:
        pass
