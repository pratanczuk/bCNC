#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
host_uid=$(id -u)
host_gid=$(id -g)

docker run --rm \
    --platform linux/arm/v7 \
    --volume "$repo_dir:/workspace" \
    --workdir /workspace \
    --env "HOST_UID=$host_uid" \
    --env "HOST_GID=$host_gid" \
    arm32v7/ubuntu:22.04 \
    bash -euc '
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        apt-get install --yes --no-install-recommends \
            ca-certificates \
            libgl1 \
            libglib2.0-0 \
            python3-fonttools \
            python3-numpy \
            python3-pil \
            python3-pip \
            python3-serial \
            python3-shapely \
            python3-tk
        BCNC_ARTIFACT_ARCH=armv7 \
        BCNC_SYSTEM_NATIVE_DEPS=1 \
            packaging/linux/build-deb.sh release 22.04
        package=$(find /workspace/release -maxdepth 1 -name "*-ubuntu-22.04-armv7.deb" -print -quit)
        package_root=$(mktemp -d)
        dpkg-deb --info "$package"
        dpkg-deb --extract "$package" "$package_root"
        cd /tmp
        PYTHONPATH="$package_root/opt/bcnc/lib" /usr/bin/python3 -c \
            "import bCNC, numpy, serial, shapely, shxparser, svgelements, tkinter_gl"
        chown "$HOST_UID:$HOST_GID" "$package"
    '
