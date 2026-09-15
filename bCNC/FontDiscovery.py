"""Discover installed TrueType and OpenType fonts for the plotter editor."""

import glob
import os
import sys


def _font_files():
    roots = [
        os.path.expanduser("~/.fonts"),
        os.path.expanduser("~/.local/share/fonts"),
        "/usr/share/fonts",
        "/usr/local/share/fonts",
    ]
    if sys.platform == "darwin":
        roots.extend(["/Library/Fonts", os.path.expanduser("~/Library/Fonts")])
    elif os.name == "nt":
        roots.append(os.path.join(os.environ.get("WINDIR", "C:\\Windows"),
                                  "Fonts"))

    fonts = []
    for root in roots:
        for extension in ("*.ttf", "*.otf", "*.TTF", "*.OTF"):
            fonts.extend(glob.glob(os.path.join(root, "**", extension),
                                   recursive=True))
    return sorted(set(fonts), key=lambda path: os.path.basename(path).lower())
