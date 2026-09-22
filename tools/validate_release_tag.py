"""Reject wrong branch-family/version tags before release assembly."""
import os
from pathlib import Path
import re
import sys
family = sys.argv[1]
tag = os.environ["GITHUB_REF_NAME"]
if family in ("classic", "foilstudio"):
    version = re.search(r'version="([^"\n]+)"', Path("setup.py").read_text())[1]
    pattern = re.escape(family + "-v" + version) + r"(?:-rc\.[1-9][0-9]*)?"
else:
    version = re.search(r"^version: ([^+\n]+)", Path("apps/foil_studio/pubspec.yaml").read_text(), re.M)[1]
    pattern = re.escape("next-v" + version)
if not re.fullmatch(pattern, tag):
    raise SystemExit(f"Tag {tag!r} does not match {family} version {version}")
