# Foil Studio Classic packages

CI builds Windows x64 (`.exe`), separate macOS Intel x64 and Apple Silicon arm64
archives (`.zip` containing an unsigned `.app`), Ubuntu 22.04/24.04 amd64 (`.deb`)
and Ubuntu 22.04 ARMv7 (`.deb`). Names start with `FoilStudio-Classic-`. The internal
Python module and executable remain `bCNC` for compatibility.

Linux: `packaging/linux/build-deb.sh release 24.04` on the matching Ubuntu release.
ARMv7: `packaging/linux/build-armv7.sh` with Docker and ARM binfmt/QEMU support.
Windows: install dependencies with `pip install -c packaging/constraints.txt pyinstaller .`,
run `pyinstaller --noconfirm --clean packaging/windows/bcnc.spec`, then compile
`packaging/windows/bcnc.iss` with Inno Setup and `/DAppVersion=0.9.17`.
macOS uses the same PyInstaller spec on native Intel and Apple Silicon runners,
verifies the Mach-O architecture, and archives `Foil Studio.app` with `ditto`.

`.deb` files use system Python/Tk. Jammy and ARM use distro native scientific packages.
Other Python wheel dependencies use `constraints.txt`; the package contains dependency
inventories and license files. Windows signing is not configured yet.

See [release policy](../docs/development.md). CI builds are temporary Actions artifacts;
tag builds collect permanent versioned download assets in a draft GitHub Release.
On the `foilstudio` branch, push `foilstudio-v<setup.py version>` (or an `-rc.N`
suffix) to build and assemble all platforms.
