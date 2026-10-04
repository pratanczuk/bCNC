# Development and releases

## Branch policy

This repository maintains Foil Studio, the Python/Tk application derived from
bCNC. Target feature PRs at `foilstudio`. Release jobs require the `CI gate` check.
Preserve attribution and history. Generated audit images, logs, videos and
installers belong in Actions artifacts, not Git. Selected product documentation
screenshots remain tracked. Use required checks and PR protection where supported
by the repository's GitHub plan; do not force-push release history.

## CI and storage

PRs and branch pushes run tests and package smoke checks. Artifacts expire after 14 days;
coverage evidence after 14 days. Tagged builds assemble GitHub Release assets with
SHA-256 checksums, source, dependency inventories and notices. Native distro dependencies
are version-inventoried, not claimed to be reproducible from rolling APT repositories.
Git stores source and small compatibility fixtures. No gateway container exists yet;
GHCR will be added when it does.

## Foil Studio release

Create `foilstudio-v<setup.py version>` or `foilstudio-v<version>-rc.<N>` from
`foilstudio`. The tag must be an ancestor of that branch.
The workflow checks ancestry and version, runs regression tests and all package builds,
then creates a **draft** release and attaches all assets. It never overwrites an asset.
Complete the license review, review artifact inventories, install/upgrade/rollback smoke
tests, and physical pen/knife validation before publishing the draft. Repository release
immutability must be enabled so published assets and tags cannot be replaced.
Release candidates are not a claim of stable readiness. Legacy `classic-v*` tags
from `main` remain supported for compatibility with earlier release tooling.

Windows and macOS builds are unsigned until signing credentials are configured. They retain the
existing installer AppId and internal path for upgrade compatibility. Linux package name
is `foil-studio-classic` and replaces/conflicts with `bcnc`; backup user configuration before
upgrading. No machine is automatically deployed to by CI.

## Migration record

Imported history through `8626953`, plus reviewed working-tree Pillow/Tk compatibility
fixes. The old bCNC checkout is untouched. Legacy local branches and tags are not pushed.
Historical audit output remains in Git history; no history rewriting was performed.

The public product name is Foil Studio. Historical package and tag identifiers
remain only for upgrade compatibility; they do not identify a separate product.
