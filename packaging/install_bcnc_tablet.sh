#!/usr/bin/env bash
set -euo pipefail

# Install latest ARMv7 bCNC release on a remote tablet over SSH and fix launcher/icon.
#
# Usage:
#   ./packaging/install_bcnc_tablet.sh --host plotter.local
#
# Options:
#   --host HOST            Remote host (required)
#   --ssh-user USER        SSH user on remote host (default: root)
#   --tablet-user USER     Desktop user that owns launcher (default: tablet)
#   --repo OWNER/REPO      GitHub repo for releases (default: pratanczuk/bCNC)
#   --tag TAG              Release tag to install (default: latest)
#   --ssh-port PORT        SSH port (default: 22)

HOST=""
SSH_USER="root"
TABLET_USER="tablet"
REPO="pratanczuk/bCNC"
TAG="latest"
SSH_PORT="22"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --ssh-user)
      SSH_USER="${2:-}"
      shift 2
      ;;
    --tablet-user)
      TABLET_USER="${2:-}"
      shift 2
      ;;
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    --tag)
      TAG="${2:-}"
      shift 2
      ;;
    --ssh-port)
      SSH_PORT="${2:-}"
      shift 2
      ;;
    -h|--help)
      sed -n '1,40p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$HOST" ]]; then
  echo "Missing required --host argument" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

if ! command -v ssh >/dev/null 2>&1 || ! command -v scp >/dev/null 2>&1; then
  echo "ssh and scp are required" >&2
  exit 1
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

release_api="https://api.github.com/repos/${REPO}/releases"
if [[ "$TAG" == "latest" ]]; then
  release_api+="/latest"
else
  release_api+="/tags/${TAG}"
fi

release_json="$workdir/release.json"
curl -fsSL "$release_api" -o "$release_json"

readarray -t parsed < <(python3 - "$release_json" <<'PY'
import json
import re
import sys

path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

tag = data.get('tag_name', '')
assets = data.get('assets', [])

# Prefer explicit armv7 .deb naming, then any armhf/armv7 .deb fallback.
preferred = None
fallback = None
for asset in assets:
    name = asset.get('name', '')
    url = asset.get('browser_download_url', '')
    if not name.endswith('.deb') or not url:
      continue
    lname = name.lower()
    if 'armv7' in lname:
      preferred = (name, url)
      break
    if ('armhf' in lname or 'arm' in lname) and fallback is None:
      fallback = (name, url)

chosen = preferred or fallback
if not chosen:
    print('ERROR')
    sys.exit(2)

print(tag)
print(chosen[0])
print(chosen[1])
PY
)

if [[ "${parsed[0]:-}" == "ERROR" || ${#parsed[@]} -lt 3 ]]; then
  echo "Could not find an ARM .deb asset in release metadata for ${REPO} (${TAG})." >&2
  exit 2
fi

resolved_tag="${parsed[0]}"
asset_name="${parsed[1]}"
asset_url="${parsed[2]}"
local_deb="$workdir/$asset_name"
remote_deb="/tmp/$asset_name"

echo "Release: $resolved_tag"
echo "Asset:   $asset_name"
echo "Repo:    $REPO"
echo "Host:    ${SSH_USER}@${HOST}:${SSH_PORT}"

curl -fL "$asset_url" -o "$local_deb"

scp -P "$SSH_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$local_deb" "${SSH_USER}@${HOST}:${remote_deb}"

ssh -p "$SSH_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${SSH_USER}@${HOST}" \
  TABLET_USER="$TABLET_USER" REMOTE_DEB="$remote_deb" bash -s <<'REMOTE'
set -euo pipefail

if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y >/dev/null || true
  apt-get install -y "$REMOTE_DEB"
else
  dpkg -i "$REMOTE_DEB"
fi

# Ensure the default launcher always uses package-provided /usr/bin/bCNC.
if [[ -e /usr/local/bin/bCNC ]]; then
  cp -f /usr/local/bin/bCNC /usr/local/bin/bCNC.backup-pre-package || true
fi
cat >/usr/local/bin/bCNC <<'EOF'
#!/bin/sh
exec /usr/bin/bCNC "$@"
EOF
chmod 755 /usr/local/bin/bCNC

# Install icon fallback in common desktop location.
if [[ -f /opt/bcnc/lib/bCNC/bCNC.png ]]; then
  install -Dm644 /opt/bcnc/lib/bCNC/bCNC.png /usr/share/pixmaps/bcnc.png
  install -Dm644 /opt/bcnc/lib/bCNC/bCNC.png /usr/share/pixmaps/bCNC.png
fi

# System desktop entry should not depend on theme-only lookup.
if [[ -f /usr/share/applications/bCNC.desktop ]]; then
  sed -i 's|^Exec=.*$|Exec=bCNC|' /usr/share/applications/bCNC.desktop || true
  sed -i 's|^Icon=.*$|Icon=/usr/share/pixmaps/bcnc.png|' /usr/share/applications/bCNC.desktop || true
fi

# User desktop shortcut fix.
user_desktop="/home/${TABLET_USER}/Desktop/bCNC.desktop"
if [[ -d "/home/${TABLET_USER}/Desktop" ]]; then
  if [[ ! -f "$user_desktop" ]]; then
    cat >"$user_desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=bCNC
Comment=bCNC Controller
Exec=bCNC
Icon=/usr/share/pixmaps/bcnc.png
Keywords=CNC;PCB;
Path=
Terminal=true
StartupNotify=false
EOF
  else
    sed -i 's|^Exec=.*$|Exec=bCNC|' "$user_desktop" || true
    sed -i 's|^Icon=.*$|Icon=/usr/share/pixmaps/bcnc.png|' "$user_desktop" || true
  fi
  chown "${TABLET_USER}:${TABLET_USER}" "$user_desktop" || true
  chmod 644 "$user_desktop" || true
fi

update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null 2>&1 || true

echo "Installed package:"
dpkg -s bcnc | egrep '^(Package|Version|Architecture|Status)'
echo "Desktop icon path:"
if [[ -f "$user_desktop" ]]; then
  grep '^Icon=' "$user_desktop" || true
fi
REMOTE

echo "Done. Installed ${asset_name} (${resolved_tag}) on ${SSH_USER}@${HOST}."
