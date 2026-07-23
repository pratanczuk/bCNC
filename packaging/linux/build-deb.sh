#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
release_dir=${1:-"$repo_dir/release"}
ubuntu_version=${2:-unknown}
version=${BCNC_VERSION:-$(sed -n 's/^[[:space:]]*version="\([^"]*\)".*/\1/p' "$repo_dir/setup.py" | head -n 1)}
architecture=$(dpkg --print-architecture)
artifact_architecture=${BCNC_ARTIFACT_ARCH:-$architecture}
python_bin=${PYTHON_BIN:-/usr/bin/python3}
runtime_dependencies="python3 (>= 3.8), python3-tk, libgl1, libglib2.0-0"

if [[ ! $version =~ ^[0-9]+([.][0-9]+)*([+~-][0-9A-Za-z.+~-]+)?$ ]]; then
    echo "Invalid Debian package version: $version" >&2
    exit 1
fi

staging_dir=$(mktemp -d)
trap 'rm -rf -- "$staging_dir"' EXIT
package_root="$staging_dir/bcnc"

mkdir -p \
    "$package_root/DEBIAN" \
    "$package_root/opt/bcnc/lib" \
    "$package_root/usr/bin" \
    "$package_root/usr/share/applications" \
    "$package_root/usr/share/icons/hicolor/204x204/apps" \
    "$package_root/usr/share/doc/bcnc" \
    "$release_dir"

if [[ ${BCNC_SYSTEM_NATIVE_DEPS:-0} == 1 ]]; then
    "$python_bin" -m pip install \
        --disable-pip-version-check \
        --no-compile \
        --no-deps \
        --target "$package_root/opt/bcnc/lib" \
        "$repo_dir" \
        "svgelements>=1,<2" \
        "shxparser>=0.0.2" \
        "tkinter-gl>=1.0"
    runtime_dependencies+=", python3-numpy, python3-scipy, python3-serial, python3-pil, python3-fonttools, python3-shapely"
else
    "$python_bin" -m pip install \
        --disable-pip-version-check \
        --no-compile \
        --target "$package_root/opt/bcnc/lib" \
        "$repo_dir"
fi

rm -rf -- "$package_root/opt/bcnc/lib/bin"
install -m 0755 "$repo_dir/packaging/linux/bcnc" "$package_root/usr/bin/bCNC"
install -m 0644 "$repo_dir/bCNC/bCNC.desktop" "$package_root/usr/share/applications/bCNC.desktop"
install -m 0644 "$repo_dir/bCNC/bCNC.png" "$package_root/usr/share/icons/hicolor/204x204/apps/bCNC.png"
install -m 0644 "$repo_dir/LICENSE.md" "$package_root/usr/share/doc/bcnc/copyright"

installed_size=$(du -sk "$package_root" | cut -f1)
cat >"$package_root/DEBIAN/control" <<EOF
Package: bcnc
Version: $version
Section: electronics
Priority: optional
Architecture: $architecture
Installed-Size: $installed_size
Maintainer: bCNC contributors
Depends: $runtime_dependencies
Description: GRBL CNC command sender and G-code editor
 bCNC is a graphical CNC command sender, autoleveler, and G-code editor.
 This build bundles its Python dependencies for Ubuntu $ubuntu_version.
EOF

artifact="$release_dir/bCNC-${version}-ubuntu-${ubuntu_version}-${artifact_architecture}.deb"
dpkg-deb --root-owner-group --build "$package_root" "$artifact"
echo "$artifact"
