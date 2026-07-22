# Installer builds

The automated workflow builds these self-contained release artifacts:

- `bCNC-<version>-windows-x64-setup.exe` for Windows 11 x64
- `bCNC-<version>-ubuntu-22.04-amd64.deb` for Ubuntu 22.04
- `bCNC-<version>-ubuntu-24.04-amd64.deb` for Ubuntu 24.04
- `bCNC-<version>-ubuntu-22.04-armv7.deb` for Ubuntu 22.04 ARMv7
  32-bit (`armhf`)

Every push to `master`, pull request, or manual workflow run stores the installers
as workflow artifacts. Pushing a tag such as `v0.9.16` also creates or updates the
matching GitHub Release and attaches all installers.

## Local Ubuntu build

Install Python 3, pip, and Debian packaging tools, then run:

```sh
packaging/linux/build-deb.sh release 24.04
```

The output goes to `release/`. The `.deb` bundles Python packages under
`/opt/bcnc` and uses the system Python and Tk libraries. Build each Ubuntu package
on the matching Ubuntu release because bundled native extensions are not expected
to be portable between distributions.

The ARMv7 build runs an `arm32v7/ubuntu:22.04` container through QEMU and uses
Ubuntu's native ARM packages for NumPy, Pillow, FontTools, and Shapely. OpenCV is
not included on ARM, matching the platform rule in `setup.py`. To build it locally,
install Docker with ARM `binfmt_misc` emulation enabled and run:

```sh
packaging/linux/build-armv7.sh
```

Install or upgrade it with:

```sh
sudo apt install ./release/bCNC-0.9.16-ubuntu-24.04-amd64.deb
```

## Local Windows build

On 64-bit Windows with Python 3.12 and Inno Setup 6 installed:

```powershell
py -m pip install --upgrade pip pyinstaller .
pyinstaller --noconfirm --clean packaging/windows/bcnc.spec
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" `
  "/DAppVersion=0.9.16" "packaging\windows\bcnc.iss"
```

The installer is written to `release/`. It installs per-user, so administrator
rights are not required. Code signing is deliberately not configured: add a
certificate-backed signing step before public distribution if avoiding Windows
SmartScreen warnings is important.
