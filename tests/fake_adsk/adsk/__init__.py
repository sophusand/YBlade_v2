"""A stand-in for the part of the Fusion 360 API that YBlade uses, so the script
can be run outside Fusion. It records what would be built and checks the same
things Fusion would refuse (zero-length lines, open outlines)."""
from . import core, fusion  # noqa: F401

terminated = False
auto_terminate = True


def doEvents():
    pass


def terminate():
    global terminated
    terminated = True


def autoTerminate(value):
    global auto_terminate
    auto_terminate = value
