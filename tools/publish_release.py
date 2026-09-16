"""Assemble drafts idempotently without replacing existing release assets."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
family, directory = sys.argv[1:]
tag = os.environ["GITHUB_REF_NAME"]
assets = sorted(p for p in Path(directory).iterdir() if p.is_file())
if not assets or not (Path(directory) / "SHA256SUMS").exists():
    raise SystemExit("Release assets/checksums missing")
def gh(*args):
    return subprocess.check_output(["gh", *args], text=True)
view = subprocess.run(["gh", "release", "view", tag, "--json", "isDraft,assets"], text=True, capture_output=True)
if view.returncode:
    notes = ("Foil Studio Classic candidate. Binary distribution license review and physical cutting validation remain outstanding. "
             "Unsigned Windows installer. See docs/development.md in the source archive." if family == "classic" else
             "Flutter/Rust project preview only. No machine connection, cutting or project saving yet. Unsigned desktop previews.")
    gh("release", "create", tag, "--verify-tag", "--draft", "--prerelease", "--latest=false", "--title", tag, "--notes", notes)
    existing = set()
else:
    data = json.loads(view.stdout)
    if not data["isDraft"]:
        raise SystemExit("Refusing to modify a published release; create a new version")
    existing = {a["name"] for a in data["assets"]}
for asset in assets:
    if asset.name in existing:
        with tempfile.TemporaryDirectory() as folder:
            gh("release", "download", tag, "--pattern", asset.name, "--dir", folder)
            if hashlib.sha256(asset.read_bytes()).digest() != hashlib.sha256((Path(folder)/asset.name).read_bytes()).digest():
                raise SystemExit(f"Existing asset differs: {asset.name}; use a new version")
    else:
        gh("release", "upload", tag, str(asset))
print(f"Draft {tag}: all assets uploaded without overwriting")
