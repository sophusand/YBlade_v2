import math

from . import core


class FeatureOperations:
    NewBodyFeatureOperation = 'new body'


class DesignTypes:
    ParametricDesignType = 'parametric'
    DirectDesignType = 'direct'


class Design:
    def __init__(self, design_type=DesignTypes.ParametricDesignType):
        self.designType = design_type
        self.timeline = Timeline()
        self.rootComponent = Component(self)
        self.activeComponent = self.rootComponent

    @staticmethod
    def cast(obj):
        return obj if isinstance(obj, Design) else None


class Timeline:
    def __init__(self):
        self.markerPosition = 0
        self.timelineGroups = TimelineGroups()

    def step(self):
        self.markerPosition += 1


class TimelineGroups(list):
    def add(self, start, end):
        assert end > start
        g = type('Group', (), {})()
        g.start, g.end, g.name = start, end, ''
        self.append(g)
        return g


class Plane:
    def __init__(self, z):
        self.z = z
        self.name = ''
        self.isLightBulbOn = True


class PlaneInput:
    def setByOffset(self, base, value):
        self.z = base.z + value.realValue


class ConstructionPlanes(list):
    def __init__(self, comp):
        super().__init__()
        self.comp = comp

    def createInput(self):
        return PlaneInput()

    def add(self, pin):
        assert abs(pin.z) > 1e-12, 'zero offset plane'
        p = Plane(pin.z)
        self.append(p)
        self.comp.design.timeline.step()
        return p


class SketchPoint:
    def __init__(self, p):
        self.geometry = p


class Spline:
    def __init__(self, pts):
        assert len(pts) >= 3
        for a, b in zip(pts, pts[1:]):
            assert math.dist((a.x, a.y, a.z), (b.x, b.y, b.z)) > 1e-9, 'coincident fit points'
        self.points = list(pts)
        self.startSketchPoint, self.endSketchPoint = SketchPoint(pts[0]), SketchPoint(pts[-1])
        self.isConstruction = False


class Line:
    def __init__(self, a, b):
        pa, pb = a.geometry, b.geometry
        assert math.dist((pa.x, pa.y, pa.z), (pb.x, pb.y, pb.z)) > 1e-7, 'zero-length line'
        self.start, self.end = a, b


class SketchCurves:
    def __init__(self, sketch):
        self.sketch = sketch
        self.sketchFittedSplines = _Adder(sketch.splines, Spline)
        self.sketchLines = _LineAdder(sketch.lines)


class _Adder:
    def __init__(self, store, kind):
        self.store, self.kind = store, kind

    def add(self, pts):
        item = self.kind(pts)
        self.store.append(item)
        return item


class _LineAdder:
    def __init__(self, store):
        self.store = store

    def addByTwoPoints(self, a, b):
        line = Line(a, b)
        self.store.append(line)
        return line


class Profile:
    def __init__(self, sketch):
        self.sketch = sketch


class Sketch:
    def __init__(self, comp, plane):
        self.comp, self.plane = comp, plane
        self.name = ''
        self.isLightBulbOn = True
        self.isComputeDeferred = False
        self.splines, self.lines = [], []
        self.sketchCurves = SketchCurves(self)

    @property
    def profiles(self):
        """One closed region when a spline is closed by a line between its own
        end points -- the only thing the script draws."""
        closed = [s for s in self.splines
                  if any(l.start is s.startSketchPoint and l.end is s.endSketchPoint for l in self.lines)]
        return core.ObjectCollection([Profile(self) for _ in closed])

    def outline_3d(self):
        """The drawn outline in model space."""
        s = self.splines[0]
        return [(p.x, p.y, p.z + self.plane.z) for p in s.points]


class Sketches(list):
    def __init__(self, comp):
        super().__init__()
        self.comp = comp

    def add(self, plane):
        s = Sketch(self.comp, plane)
        self.append(s)
        self.comp.design.timeline.step()
        return s


class Body:
    def __init__(self, sections):
        self.name = ''
        self.sections = sections
        pts = [p for sec in sections for p in sec]
        n = len(pts)
        self.physicalProperties = type('P', (), {})()
        self.physicalProperties.centerOfMass = core.Point3D(sum(p[0] for p in pts) / n,
                                                            sum(p[1] for p in pts) / n,
                                                            sum(p[2] for p in pts) / n)
        self.boundingBox = type('B', (), {})()
        self.boundingBox.minPoint = core.Point3D(min(p[0] for p in pts), min(p[1] for p in pts),
                                                 min(p[2] for p in pts))


class LoftInput:
    def __init__(self, op):
        self.operation = op
        self.loftSections = core.ObjectCollection()
        self.isSolid = False


class LoftFeatures:
    def __init__(self, comp):
        self.comp = comp
        self.made = []

    def createInput(self, op):
        return LoftInput(op)

    def add(self, li):
        if len(li.loftSections) < 2:
            raise RuntimeError('loft needs two sections')
        feature = type('Loft', (), {})()
        feature.input = li
        feature.bodies = core.ObjectCollection([Body([p.sketch.outline_3d() for p in li.loftSections])])
        self.comp.bodies.append(feature.bodies[0])
        self.made.append(feature)
        self.comp.design.timeline.step()
        return feature


class MoveInput:
    def __init__(self, bodies):
        self.bodies, self.transform = bodies, None

    def defineAsFreeMove(self, transform):
        self.transform = transform
        return True


class MoveFeatures:
    def __init__(self, comp):
        self.comp = comp
        self.made = []

    def createInput2(self, bodies):
        return MoveInput(bodies)

    def add(self, mi):
        assert mi.transform is not None
        self.made.append(mi)
        self.comp.design.timeline.step()
        return mi


class Features:
    def __init__(self, comp):
        self.loftFeatures = LoftFeatures(comp)
        self.moveFeatures = MoveFeatures(comp)


class Component:
    def __init__(self, design):
        self.design = design
        self.xYConstructionPlane = Plane(0.0)
        self.constructionPlanes = ConstructionPlanes(self)
        self.sketches = Sketches(self)
        self.features = Features(self)
        self.bodies = []
