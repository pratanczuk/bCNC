""" This file is a collection of simple helper functions. It was necessary to
remove them from other files, since there were circular imports.
XXX: This file might be removed, once the circular imports are cleared.
"""

import os
import gettext
import sys

gettext.install(True, localedir=None)

__all__ = (
    "to_zip",
)

__prg__ = "bCNC"
prgpath = os.path.abspath(os.path.dirname(__file__))
if getattr(sys, "frozen", False):
    # When being bundled by pyinstaller, paths are different
    print("Running as pyinstaller bundle!", sys.argv[0])
    bundle_root = getattr(
        sys, "_MEIPASS", os.path.abspath(os.path.dirname(sys.executable))
    )
    package_root = os.path.join(bundle_root, __prg__)
    prgpath = package_root if os.path.isdir(package_root) else bundle_root


def to_zip(*args, **kwargs):
    return list(zip(*args, **kwargs))


def N_(message):
    return message
