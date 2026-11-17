import math


class _Handler:
    def __init__(self, *args, **kwargs):
        pass


CommandEventHandler = InputChangedEventHandler = ValidateInputsEventHandler = _Handler
CommandCreatedEventHandler = _Handler


class DialogResults:
    DialogOK = 0
    DialogCancel = 1


class DropDownStyles:
    TextListDropDownStyle = 0


class Point3D:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    @staticmethod
    def create(x=0.0, y=0.0, z=0.0):
        return Point3D(x, y, z)


class Vector3D(Point3D):
    @staticmethod
    def create(x=0.0, y=0.0, z=0.0):
        return Vector3D(x, y, z)


class Matrix3D:
    def __init__(self):
        self.translation = Vector3D()

    @staticmethod
    def create():
        return Matrix3D()


class ObjectCollection(list):
    @staticmethod
    def create():
        return ObjectCollection()

    def add(self, item):
        self.append(item)
        return True

    @property
    def count(self):
        return len(self)

    def item(self, i):
        return self[i]


class ValueInput:
    def __init__(self, real=None, text=None):
        self.realValue, self.stringValue = real, text

    @staticmethod
    def createByReal(v):
        return ValueInput(real=float(v))

    @staticmethod
    def createByString(s):
        return ValueInput(text=s)


# ---------------------------------------------------------------- user interface

class FakeUI:
    def __init__(self):
        self.messages = []
        self.next_files = []
        self.commandDefinitions = FakeCommandDefinitions()

    def messageBox(self, text, title='', *rest):
        self.messages.append((title, text))

    def createProgressDialog(self):
        return FakeProgress()

    def createFileDialog(self):
        return FakeFileDialog(self)


class FakeProgress:
    def __init__(self):
        self.isCancelButtonShown = True
        self.progressValue, self.message, self.visible = 0, '', False

    def show(self, title, message, lo, hi):
        self.visible = True

    def hide(self):
        self.visible = False


class FakeFileDialog:
    def __init__(self, ui):
        self.ui = ui
        self.filename = ''
        self.initialDirectory = ''

    def showOpen(self):
        if not self.ui.next_files:
            return DialogResults.DialogCancel
        self.filename = self.ui.next_files.pop(0)
        return DialogResults.DialogOK


class FakeEvent(list):
    def add(self, handler):
        self.append(handler)
        return True


class FakeCommandDefinition:
    def __init__(self, defs, cid):
        self.defs, self.id = defs, cid
        self.commandCreated = FakeEvent()
        self.deleted = False

    def deleteMe(self):
        self.deleted = True
        self.defs.items.pop(self.id, None)

    def execute(self, *args):
        self.defs.executed.append(self.id)


class FakeCommandDefinitions:
    def __init__(self):
        self.items, self.executed = {}, []

    def itemById(self, cid):
        return self.items.get(cid)

    def addButtonDefinition(self, cid, name, tooltip, resources):
        assert cid not in self.items, 'command id already exists'
        self.items[cid] = FakeCommandDefinition(self, cid)
        return self.items[cid]


class Application:
    _app = None

    def __init__(self):
        self.userInterface = FakeUI()
        self.activeProduct = None

    @staticmethod
    def get():
        if Application._app is None:
            Application._app = Application()
        return Application._app
