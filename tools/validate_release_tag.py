"""Reject wrong branch-family/version tags before release assembly."""
import os
from pathlib import Path
import re
import sys
family = sys.argv[1]
if family not in ("classic", "foilstudio"):
    raise SystemExit(f"Unsupported release family: {family}")
tag = os.environ["GITHUB_REF_NAME"]
version = re.search(r'version="([^"\n]+)"', Path("setup.py").read_text())[1]
pattern = re.escape(family + "-v" + version) + r"(?:-rc\.[1-9][0-9]*)?"
if not re.fullmatch(pattern, tag):
    raise SystemExit(f"Tag {tag!r} does not match {family} version {version}")
