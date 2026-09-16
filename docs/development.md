# Development and releases

## Branch policy

`main` maintains Classic; `next` develops Flutter/Rust. Target feature PRs at the
appropriate branch. No routine cross-branch merges: deliberately port fixes and sync
`contracts/` and `fixtures/`. Both branches are designed to require the `CI gate` check.
GitHub rejected branch protection on 2026-09-16: this private repository needs GitHub
Pro. Until the account plan changes, PR-only branch updates cannot be enforced;
release jobs still depend on the gate. Enable strict required status `CI gate`,
PRs (zero extra reviewers for solo work), conversation resolution, no force pushes
and no branch deletion on both branches once available. Preserve
attribution and history. Generated audit images, logs, videos and installers belong in
Actions artifacts, not Git. Selected product documentation screenshots remain tracked.

## CI and storage

PRs and branch pushes run tests and package smoke checks. Artifacts expire after 14 days;
coverage evidence after 14 days. Tagged builds assemble GitHub Release assets with
SHA-256 checksums, source, dependency inventories and notices. Native distro dependencies
are version-inventoried, not claimed to be reproducible from rolling APT repositories.
Git stores source and small compatibility fixtures. No gateway container exists yet;
GHCR will be added when it does.

## Classic release

Create `classic-v<setup.py version>` or `classic-v<version>-rc.<N>` from `main`.
The workflow checks ancestry and version, runs regression tests and all package builds,
then creates a **draft** release and attaches all assets. It never overwrites an asset.
Complete the license review, review artifact inventories, install/upgrade/rollback smoke
tests, and physical pen/knife validation before publishing the draft. Repository release
immutability must be enabled so published assets and tags cannot be replaced.
The first migration build is `classic-v0.9.17-rc.1`, not a new claim of stable readiness.

Windows builds are unsigned until a signing certificate is configured. They retain the
existing installer AppId and internal path for upgrade compatibility. Linux package name
is `foil-studio-classic` and replaces/conflicts with `bcnc`; backup user configuration before
upgrading. No machine is automatically deployed to by CI.

## Next release

Next starts as a project-preview vertical slice, not an operational cutter. Tag
`next-v<pubspec version without +build>` from `next`. CI packages desktop previews. Android and iOS receive UI compile checks only;
these do not imply a working native mobile engine or installable signed IPA delivery.
Apple signing/notarization, Windows signing and store accounts remain external setup.
Mark Next releases as prereleases and never Latest while Classic is production.

## Migration record

Imported history through `8626953`, plus reviewed working-tree Pillow/Tk compatibility
fixes. The old bCNC checkout is untouched. Legacy local branches and tags are not pushed.
Historical audit output remains in Git history; no history rewriting was performed.

## Manual workflow discovery

`next.yml` is also present on default branch `main` so GitHub can expose its manual
Run workflow control. Select branch `next` for Next builds. The workflow guards
against running Next jobs on `main`. Keep that discovery copy synchronized when
changing Next workflows; product code remains isolated by branch.
