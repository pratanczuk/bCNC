# Foil Studio Classic packages

CI builds Windows x64 (`.exe`), Ubuntu 22.04/24.04 amd64 (`.deb`) and Ubuntu 22.04
ARMv7 (`.deb`). Names start with `FoilStudio-Classic-`. The internal Python module
and Windows executable remain `bCNC` for compatibility.

Linux: `packaging/linux/build-deb.sh release 24.04` on the matching Ubuntu release.
ARMv7: `packaging/linux/build-armv7.sh` with Docker and ARM binfmt/QEMU support.
Windows: install dependencies with `pip install -c packaging/constraints.txt pyinstaller .`,
run `pyinstaller --noconfirm --clean packaging/windows/bcnc.spec`, then compile
`packaging/windows/bcnc.iss` with Inno Setup and `/DAppVersion=0.9.17`.

`.deb` files use system Python/Tk. Jammy and ARM use distro native scientific packages.
Other Python wheel dependencies use `constraints.txt`; the package contains dependency
inventories and license files. Windows signing is not configured yet.

See [release policy](../docs/development.md). CI builds are temporary Actions artifacts;
tag builds collect permanent versioned download assets in a draft GitHub Release.
