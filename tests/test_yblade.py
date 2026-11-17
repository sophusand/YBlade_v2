"""
Tests for YBlade v3 that run without Fusion 360:

    python3 -m unittest discover -s tests -v

The Fusion API is replaced by tests/fake_adsk, which records what would be
built and refuses what Fusion refuses (zero-length lines, repeated spline
points, open outlines). The geometry is checked against the v2 placement of
the sections and against the example QBlade files.
"""
import json
import math
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, 'fake_adsk'))
sys.path.insert(0, ROOT)

import adsk  # noqa: E402  (the fake one)
import adsk.core  # noqa: E402
import adsk.fusion  # noqa: E402
import YBlade as yb  # noqa: E402

EXAMPLES = os.path.join(ROOT, 'bladeExample', 'Fysik Klubben test blades')
BLD_4812 = os.path.join(EXAMPLES, '4812_TSR5', '4812_TSR5_-_3.bld')
AFL_4812 = os.path.join(EXAMPLES, '4812_TSR5', 'NACA 4812.afl')
AFL_4812_LR = os.path.join(EXAMPLES, '4812_TSR5', 'NACA 4812 LR.afl')
BLD_0012 = os.path.join(EXAMPLES, '0012', '0012_TSR5_-_3.bld')
AFL_0012 = os.path.join(EXAMPLES, '0012', 'NACA 0012.afl')
JSON_EXAMPLE = os.path.join(ROOT, 'bladeExample', 'Combined json', 'NACA4812_TSR5.json')


def naca4(m, p, t, n=40):
    """Selig-ordered NACA 4-digit section with a sharp trailing edge."""
    xs = [0.5 * (1 - math.cos(math.pi * i / (n - 1))) for i in range(n)]
    up, lo = [], []
    for x in xs:
        yt = 5 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x ** 2 + 0.2843 * x ** 3 - 0.1036 * x ** 4)
        if p and x < p:
            yc, dy = m / p ** 2 * (2 * p * x - x * x), 2 * m / p ** 2 * (p - x)
        elif p:
            yc, dy = m / (1 - p) ** 2 * ((1 - 2 * p) + 2 * p * x - x * x), 2 * m / (1 - p) ** 2 * (p - x)
        else:
            yc, dy = 0.0, 0.0
        th = math.atan(dy)
        up.append((x - yt * math.sin(th), yc + yt * math.cos(th)))
        lo.append((x + yt * math.sin(th), yc - yt * math.cos(th)))
    return list(reversed(up)) + lo[1:]


def v2_outline(profile, chord, twist, p_axis, first_p_axis):
    """How YBlade v2 placed one section (deduceOffset + profilePoints)."""
    pos = [(x, y) for x, y in profile if y > 0]
    neg = [(x, y) for x, y in profile if y < 0]
    yp = min(pos, key=lambda q: abs(q[0] - first_p_axis))[1]
    yn = min(neg, key=lambda q: abs(q[0] - first_p_axis))[1]
    off = -(yp + yn) / 2 * chord
    t = math.radians(twist)
    out = []
    for x, y in profile:
        px, py = x * chord - chord * p_axis, y * chord + off
        out.append((px * math.cos(t) - py * math.sin(t), px * math.sin(t) + py * math.cos(t)))
    return out


class ReadingFiles(unittest.TestCase):
    def test_qblade_example_skips_circular_root(self):
        stations, notes = yb.read_bld(BLD_4812)
        self.assertEqual(len(stations), 18)                 # 20 rows, 2 circular
        self.assertAlmostEqual(stations[0].pos, 9.158)      # cm
        self.assertAlmostEqual(stations[0].chord, 7.330)
        self.assertAlmostEqual(stations[0].p_axis, 0.296)
        self.assertTrue(any('circular' in n for n in notes))

    def test_units_override(self):
        stations, _ = yb.read_bld(BLD_4812, 'millimeter')
        self.assertAlmostEqual(stations[0].pos, 0.09158 * 0.1)

    def test_afl_selig(self):
        pts = yb.read_afl(AFL_4812_LR)
        self.assertEqual(pts[0], (1.0, 0.0))
        self.assertEqual(pts[-1], (1.0, 0.0))

    def test_afl_lednicer_matches_selig(self):
        selig = naca4(0.04, 0.4, 0.12)
        n = (len(selig) + 1) // 2
        upper = list(reversed(selig[:n]))
        lower = selig[n - 1:]
        text = ['NACA 4412 (Lednicer)', f'{len(upper)}. {len(lower)}.', '']
        text += [f'{x} {y}' for x, y in upper] + [''] + [f'{x} {y}' for x, y in lower]
        self.assertEqual(yb.parse_afl_lines(text), selig)

    def test_json_with_own_outlines_and_units(self):
        rows = []
        for i, t in enumerate((0.18, 0.15, 0.12, 0.10)):
            rows.append({'pos': 50 + 100 * i, 'chord': 80 - 10 * i, 'twist': 30 - 8 * i,
                         'p_axis': 0.25, 'points': naca4(0.04, 0.4, t)})
        blade = yb.parse_json({'meta': {'units': 'Millimeter', 'name': 'test'}, 'blade': rows})
        self.assertIsNone(blade.outline)
        self.assertAlmostEqual(blade.stations[1].pos, 15.0)
        self.assertAlmostEqual(blade.stations[1].chord, 7.0)
        self.assertTrue(any('own section outline' in n for n in blade.notes))

    def test_json_station_without_any_outline_is_refused(self):
        with self.assertRaises(ValueError):
            yb.parse_json({'blade': [{'pos': 0.1, 'chord': 0.05, 'twist': 0},
                                     {'pos': 0.2, 'chord': 0.04, 'twist': 0}]})

    def test_example_json_reads(self):
        blade = yb.load_blade(JSON_EXAMPLE)
        self.assertEqual(len(blade.stations), 18)
        self.assertEqual(blade.name, 'NACA 4812 TSR5')


class SectionGeometry(unittest.TestCase):
    def test_doubled_points_removed_and_orientation_fixed(self):
        sel = naca4(0.04, 0.4, 0.12)
        doubled = sel[:20] + [sel[19]] + sel[20:]
        self.assertEqual(yb.clean_outline(doubled), sel)
        self.assertEqual(yb.clean_outline(list(reversed(sel))), sel)

    def test_trailing_edge_opened_to_request(self):
        st = yb.Station(10.0, 5.0, 12.0, 0.3)
        pts, opened = yb.station_outline(st, naca4(0.04, 0.4, 0.12), 0.08)   # 0.8 mm
        self.assertTrue(opened)
        self.assertAlmostEqual(math.dist(pts[0], pts[-1]), 0.08, places=6)

    def test_thick_trailing_edge_left_alone(self):
        blunt = [(x, y + (0.01 if i < 40 else -0.01) * x) for i, (x, y) in enumerate(naca4(0.04, 0.4, 0.12))]
        st = yb.Station(10.0, 5.0, 0.0, 0.25)
        pts, opened = yb.station_outline(st, blunt, 0.05)
        self.assertFalse(opened)

    def test_nose_untouched_by_trailing_edge(self):
        sel = naca4(0.04, 0.4, 0.12)
        thick = yb.thicken_trailing_edge(sel, 0.02)
        i = yb._nose(sel)
        for a, b in zip(sel[i - 5:i + 6], thick[i - 5:i + 6]):
            self.assertLess(abs(a[1] - b[1]), 1e-5)      # 0.001 % of the chord

    def test_same_placement_as_v2(self):
        """Away from the trailing edge, v3 puts every point where v2 did, up to
        one common shift from centring on interpolated rather than nearest
        points."""
        profile = yb.read_afl(AFL_4812)
        stations, _ = yb.read_bld(BLD_4812)
        for st in stations[::5]:
            new, _ = yb.station_outline(st, profile, 0.0)
            old = v2_outline(yb.clean_outline(profile), st.chord, st.twist, st.p_axis, stations[0].p_axis)
            self.assertEqual(len(new), len(old))
            shifts = [(a[0] - b[0], a[1] - b[1]) for a, b, (x, _y) in
                      zip(new, old, yb.clean_outline(profile)) if x < 0.9]
            sx = sum(s[0] for s in shifts) / len(shifts)
            sy = sum(s[1] for s in shifts) / len(shifts)
            self.assertLess(math.hypot(sx, sy), 0.02)           # < 0.2 mm
            # the 0.02 mm minimum trailing-edge opening moves the aft points a little
            for dx, dy in shifts:
                self.assertLess(math.hypot(dx - sx, dy - sy), 0.003)   # cm

    def test_thinning_drops_stations_a_straight_blend_reproduces(self):
        prof = naca4(0.04, 0.4, 0.12)
        sts = [yb.Station(5.0 + i, 8.0 - 0.2 * i, 10.0, 0.25) for i in range(21)]  # linear taper
        outs = [yb.station_outline(s, prof, 0.05)[0] for s in sts]
        zs = [s.pos for s in sts]
        self.assertEqual(yb.thin_stations(zs, outs, 0.005), [0, 20])

    def test_thinning_keeps_a_kink(self):
        prof = naca4(0.04, 0.4, 0.12)
        sts = [yb.Station(5.0 + i, 8.0 - (0.2 * i if i <= 10 else 2.0 + 0.05 * (i - 10)), 10.0, 0.25)
               for i in range(21)]
        outs = [yb.station_outline(s, prof, 0.05)[0] for s in sts]
        self.assertEqual(yb.thin_stations([s.pos for s in sts], outs, 0.005), [0, 10, 20])

    def test_thinning_error_is_bounded(self):
        """Every left-out station lies within the tolerance of the straight
        blend of the kept stations around it."""
        blade = yb.load_blade(BLD_4812, AFL_4812)
        tol = 0.005
        full = yb.plan_blade(blade, 0.05, 0.0, True)
        thin = yb.plan_blade(blade, 0.05, tol, True)
        self.assertLess(thin.used, full.used)
        for z, out in zip(full.zs, full.outlines):
            k = max(i for i, zz in enumerate(thin.zs) if zz <= z + 1e-12)
            if k == len(thin.zs) - 1:
                continue
            t = (z - thin.zs[k]) / (thin.zs[k + 1] - thin.zs[k])
            for a, b, p in zip(thin.outlines[k], thin.outlines[k + 1], out):
                ex = p[0] - (a[0] + t * (b[0] - a[0]))
                ey = p[1] - (a[1] + t * (b[1] - a[1]))
                self.assertLessEqual(math.hypot(ex, ey), tol + 1e-9)

    def test_start_at_zero(self):
        blade = yb.load_blade(BLD_4812, AFL_4812_LR)
        self.assertAlmostEqual(yb.plan_blade(blade, 0.05, 0.005, True).zs[0], 0.0)
        self.assertAlmostEqual(yb.plan_blade(blade, 0.05, 0.005, False).zs[0], 9.158)


class FakeInput:
    def __init__(self, iid, name='', value=None, items=None):
        self.id, self.name, self.value = iid, name, value
        self.isEnabled, self.isVisible, self.isFullWidth = True, True, False
        self.tooltip = self.tooltipDescription = ''
        self.formattedText = ''
        self.listItems = items

    @property
    def selectedItem(self):
        return next(i for i in self.listItems if i.isSelected)


class FakeList(list):
    def add(self, name, selected):
        item = type('Item', (), {})()
        item.name, item.isSelected = name, selected
        self.append(item)
        return item


class FakeInputs:
    def __init__(self, registry=None):
        self.items = {} if registry is None else registry

    def _add(self, iid, name='', value=None, items=None):
        assert iid not in self.items, f'duplicate input id {iid}'
        self.items[iid] = FakeInput(iid, name, value, items)
        return self.items[iid]

    def itemById(self, iid):
        return self.items.get(iid)

    def addGroupCommandInput(self, iid, name):
        group = self._add(iid, name)
        group.children = FakeInputs(self.items)     # ids are unique across the dialog
        group.isExpanded = False
        return group

    def addBoolValueInput(self, iid, name, is_check, res, value):
        return self._add(iid, name, value)

    def addDropDownCommandInput(self, iid, name, style):
        return self._add(iid, name, None, FakeList())

    def addValueInput(self, iid, name, unit, vi):
        number, u = vi.stringValue.split()
        return self._add(iid, name, float(number) * {'mm': 0.1, 'cm': 1.0}[u])

    def addTextBoxCommandInput(self, iid, name, text, rows, read_only):
        item = self._add(iid, name)
        item.formattedText, item.numRows = text, rows
        return item


class FakeCommand:
    def __init__(self):
        self.commandInputs = FakeInputs()
        self.execute, self.inputChanged = adsk.core.FakeEvent(), adsk.core.FakeEvent()
        self.validateInputs, self.destroy = adsk.core.FakeEvent(), adsk.core.FakeEvent()
        self.okButtonText = 'OK'
        self.size = self.min_size = None

    def setDialogInitialSize(self, w, h):
        self.size = (w, h)

    def setDialogMinimumSize(self, w, h):
        self.min_size = (w, h)


def args(**kw):
    a = type('Args', (), {})()
    for k, v in kw.items():
        setattr(a, k, v)
    return a


class FusionBuild(unittest.TestCase):
    def setUp(self):
        adsk.core.Application._app = None
        adsk.terminated = False
        self.app = adsk.core.Application.get()
        self.design = adsk.fusion.Design()
        self.app.activeProduct = self.design

    def build(self, blade, te=0.05, tol=0.005, **kw):
        plan = yb.plan_blade(blade, te, tol, True)
        body, summary = yb.build_blade(self.design, self.design.rootComponent, plan, blade.name, **kw)
        return plan, body, summary

    def test_qblade_example_builds(self):
        blade = yb.load_blade(BLD_4812, AFL_4812)
        plan, body, _ = self.build(blade)
        comp = self.design.rootComponent
        self.assertEqual(len(comp.sketches), plan.used)
        self.assertEqual(len(comp.constructionPlanes), plan.used - 1)    # station 1 on the XY plane
        loft = comp.features.loftFeatures.made[0]
        self.assertEqual(len(loft.input.loftSections), plan.used)
        self.assertTrue(loft.input.isSolid)
        self.assertEqual(body.name, '4812_TSR5_-_3')
        self.assertTrue(all(not s.isLightBulbOn for s in comp.sketches))
        self.assertTrue(all(not p.isLightBulbOn for p in comp.constructionPlanes))
        self.assertEqual(len(self.design.timeline.timelineGroups), 1)
        # sections are where the plan says, and the blade is as long as the file says
        zs = [sec[0][2] for sec in body.sections]
        self.assertAlmostEqual(zs[0], 0.0)
        self.assertAlmostEqual(zs[-1], 36.0 - 9.158)

    def test_sharp_trailing_edge_closes(self):
        # the LR file has a perfectly sharp trailing edge; v2 closed it with a zero-length line
        blade = yb.load_blade(BLD_4812, AFL_4812_LR)
        self.build(blade, te=0.0)
        for s in self.design.rootComponent.sketches:
            self.assertEqual(s.profiles.count, 1)

    def test_other_sketches_stay_visible(self):
        mine = self.design.rootComponent.sketches.add(self.design.rootComponent.xYConstructionPlane)
        self.build(yb.load_blade(BLD_0012, AFL_0012))
        self.assertTrue(mine.isLightBulbOn)

    def test_guide_rails_and_centre_of_mass(self):
        plan, body, summary = self.build(yb.load_blade(BLD_4812, AFL_4812_LR),
                                         guide_rails=True, center_mass=True)
        comp = self.design.rootComponent
        guide = comp.sketches[-1]
        self.assertEqual(len(guide.splines), 2)
        self.assertTrue(guide.splines[1].isConstruction)
        self.assertEqual(len(comp.features.moveFeatures.made), 1)
        self.assertTrue(summary)

    def test_direct_design_has_no_timeline_group(self):
        self.design = adsk.fusion.Design(adsk.fusion.DesignTypes.DirectDesignType)
        self.app.activeProduct = self.design
        self.build(yb.load_blade(BLD_4812, AFL_4812_LR))
        self.assertEqual(len(self.design.timeline.timelineGroups), 0)

    def test_json_with_own_outlines_builds(self):
        rows = [{'pos': 0.05 + 0.4 * i / 24, 'chord': 0.09 - 0.045 * i / 24, 'twist': 38 - 35 * i / 24,
                 'p_axis': 0.25, 'points': naca4(0.04, 0.4, 0.18 - 0.08 * min(i / 17, 1))}
                for i in range(25)]
        blade = yb.parse_json({'meta': {'name': 'tapered'}, 'blade': rows})
        plan, body, _ = self.build(blade)
        self.assertGreater(plan.used, 2)
        # thickness really changes along the blade: root section thicker than tip section
        def thickness(sec):
            ys = [math.hypot(p[0], p[1]) for p in sec]
            return max(ys)
        root = body.sections[0]
        tip = body.sections[-1]
        t_root = max(p[1] for p in yb.clean_outline(rows[0]['points'])) - min(p[1] for p in yb.clean_outline(rows[0]['points']))
        t_tip = max(p[1] for p in yb.clean_outline(rows[-1]['points'])) - min(p[1] for p in yb.clean_outline(rows[-1]['points']))
        self.assertGreater(t_root, t_tip + 0.07)
        self.assertEqual(len(root), len(tip))


class CommandFlow(unittest.TestCase):
    """The dialog, end to end: run, choose files, Import, close."""

    def setUp(self):
        adsk.core.Application._app = None
        adsk.terminated = False
        self.app = adsk.core.Application.get()
        self.ui = self.app.userInterface
        self.design = adsk.fusion.Design()
        self.app.activeProduct = self.design

    def open_dialog(self):
        yb.run(None)
        cmd_def = self.ui.commandDefinitions.itemById(yb.CMD_ID)
        self.assertEqual(self.ui.commandDefinitions.executed, [yb.CMD_ID])
        cmd = FakeCommand()
        for h in cmd_def.commandCreated:
            h.notify(args(command=cmd))
        self.assertEqual(self.ui.messages, [])
        return cmd

    def click(self, cmd, iid):
        inp = cmd.commandInputs.itemById(iid)
        inp.value = True
        for h in cmd.inputChanged:
            # Fusion hands over the collection the input sits in -- a group's children
            h.notify(args(input=inp, inputs=FakeInputs()))
        self.assertFalse(inp.value)

    def valid(self, cmd):
        a = args(inputs=cmd.commandInputs, areInputsValid=None)
        for h in cmd.validateInputs:
            h.notify(a)
        return a.areInputsValid

    def text(self, cmd, iid):
        return cmd.commandInputs.itemById(iid).formattedText

    def test_layout(self):
        cmd = self.open_dialog()
        self.assertEqual(cmd.okButtonText, 'Import')
        self.assertEqual(cmd.size, yb.DIALOG_SIZE)
        items = cmd.commandInputs.items
        for iid in ('files', 'settings', 'preview'):
            self.assertTrue(items[iid].isExpanded)
        # labels short enough for Fusion's label column; the rest is in tooltips
        for item in items.values():
            if item.name and not item.isFullWidth and item.id not in ('files', 'settings', 'preview'):
                self.assertLessEqual(len(item.name), 18, item.name)
                self.assertTrue(item.tooltip, item.id)
        for iid in ('bladeFile', 'airfoilFile', 'status', 'bladeBrowse', 'airfoilBrowse'):
            self.assertTrue(items[iid].isFullWidth, iid)
        self.assertIn('Choose a blade file', self.text(cmd, 'status'))

    def test_qblade_pair(self):
        cmd = self.open_dialog()
        self.assertFalse(self.valid(cmd))
        self.ui.next_files = [BLD_4812, AFL_4812]
        self.click(cmd, 'bladeBrowse')
        self.assertIn('<b>4812_TSR5_-_3.bld</b>', self.text(cmd, 'bladeFile'))
        self.assertIn('in folder 4812_TSR5', self.text(cmd, 'bladeFile'))
        self.assertIn('airfoil', self.text(cmd, 'status'))
        self.assertFalse(self.valid(cmd))
        self.click(cmd, 'airfoilBrowse')
        self.assertIn('NACA 4812.afl', self.text(cmd, 'airfoilFile'))
        status = self.text(cmd, 'status')
        self.assertTrue(status.startswith('<b>Ready to import'), status)
        self.assertIn('&bull;', status)
        self.assertTrue(self.valid(cmd))

        for h in cmd.execute:
            h.notify(args(command=cmd))
        title, text = self.ui.messages[-1]
        self.assertIn('created', text, text)
        self.assertEqual(len(self.design.rootComponent.bodies), 1)

        for h in cmd.destroy:
            h.notify(args(command=cmd))
        self.assertTrue(adsk.terminated)
        yb.stop(None)
        self.assertIsNone(self.ui.commandDefinitions.itemById(yb.CMD_ID))

    def test_json_needs_no_airfoil(self):
        cmd = self.open_dialog()
        self.ui.next_files = [JSON_EXAMPLE]
        self.click(cmd, 'bladeBrowse')
        self.assertFalse(cmd.commandInputs.itemById('airfoilBrowse').isVisible)
        self.assertFalse(cmd.commandInputs.itemById('airfoilFile').isVisible)
        self.assertTrue(self.valid(cmd))
        for h in cmd.execute:
            h.notify(args(command=cmd))
        self.assertIn('created', self.ui.messages[-1][1])

    def test_file_names_are_escaped(self):
        self.assertNotIn('<script>', yb._file_html('/tmp/<script>.json', ''))

    def test_bad_file_reports_instead_of_crashing(self):
        cmd = self.open_dialog()
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            f.write('{"blade": []}')
        try:
            self.ui.next_files = [f.name]
            self.click(cmd, 'bladeBrowse')
            self.assertIn('Problem', self.text(cmd, 'status'))
            for h in cmd.execute:
                h.notify(args(command=cmd))
            self.assertIn('Import failed', self.ui.messages[-1][1])
        finally:
            os.remove(f.name)

    def test_changing_a_setting_updates_the_preview(self):
        cmd = self.open_dialog()
        self.ui.next_files = [JSON_EXAMPLE]
        self.click(cmd, 'bladeBrowse')
        before = self.text(cmd, 'status')
        tol = cmd.commandInputs.itemById('tolerance')
        tol.value = 0.0
        for h in cmd.inputChanged:
            h.notify(args(input=tol, inputs=FakeInputs()))
        self.assertNotEqual(before, self.text(cmd, 'status'))
        self.assertIn('18 of 18 stations', self.text(cmd, 'status'))

    def test_cancelled_file_dialog_keeps_the_old_file(self):
        cmd = self.open_dialog()
        self.ui.next_files = [JSON_EXAMPLE]
        self.click(cmd, 'bladeBrowse')
        self.ui.next_files = []          # the user presses Cancel
        self.click(cmd, 'bladeBrowse')
        self.assertIn('NACA4812_TSR5.json', self.text(cmd, 'bladeFile'))

    def test_no_design_open(self):
        cmd = self.open_dialog()
        self.app.activeProduct = object()
        self.ui.next_files = [JSON_EXAMPLE]
        self.click(cmd, 'bladeBrowse')
        for h in cmd.execute:
            h.notify(args(command=cmd))
        self.assertIn('Open a design', self.ui.messages[-1][1])

    def test_running_twice_does_not_duplicate_the_command(self):
        yb.run(None)
        yb.run(None)          # a previous run that never ended
        self.assertEqual(len(self.ui.commandDefinitions.items), 1)


if __name__ == '__main__':
    unittest.main()
