#!/bin/bash
# Build Archivist.app and a drag-to-Applications disk image (.dev/dist/Archivist-Setup.dmg).
# Usage: .dev/build-macos.sh [version]      Optional: CODESIGN_IDENTITY="Developer ID Application: ..."
set -euo pipefail

VERSION="${1:-1.0.0}"
if ! [[ "$VERSION" =~ ^[0-9]+(\.[0-9]+){1,3}$ ]]; then
    echo "Version must be numeric, for example 1.0.0." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_ROOT="$SCRIPT_DIR/build"
DIST_ROOT="$SCRIPT_DIR/dist"
VENV="$BUILD_ROOT/venv-macos"
PYTHON="$VENV/bin/python"
APP="$DIST_ROOT/Archivist.app"
DMG="$DIST_ROOT/Archivist-Setup.dmg"
ICONSET="$BUILD_ROOT/archivist.iconset"
ICNS="$BUILD_ROOT/archivist.icns"
STAGING="$BUILD_ROOT/dmg-staging"
IDENTITY="${CODESIGN_IDENTITY:--}"

mkdir -p "$BUILD_ROOT" "$DIST_ROOT"

BASE_PYTHON="$(command -v python3.11 || true)"
if [[ -z "$BASE_PYTHON" ]]; then
    echo "Python 3.11 was not found. Run 'brew install python@3.11' and run this script again." >&2
    exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
    "$BASE_PYTHON" -m venv "$VENV"
fi
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -r "$REPO_ROOT/requirements.txt" "pyinstaller==6.14.2"

rm -rf "$ICONSET" "$ICNS"
mkdir -p "$ICONSET"
"$PYTHON" - "$REPO_ROOT/images/archivist.png" "$ICONSET" <<'PY'
import sys
from PIL import Image

with Image.open(sys.argv[1]) as logo:
    logo = logo.convert("RGB")
    side = round(logo.height * 0.9)
    left = round(logo.width * 0.02)
    top = (logo.height - side) // 2
    mark = logo.crop((left, top, left + side, top + side))
    for size in (16, 32, 128, 256, 512):
        mark.resize((size, size), Image.Resampling.LANCZOS).save(f"{sys.argv[2]}/icon_{size}x{size}.png")
        mark.resize((size * 2, size * 2), Image.Resampling.LANCZOS).save(f"{sys.argv[2]}/icon_{size}x{size}@2x.png")
PY
iconutil -c icns "$ICONSET" -o "$ICNS"

rm -rf "$APP" "$DIST_ROOT/Archivist"
"$PYTHON" -m PyInstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name Archivist \
    --icon "$ICNS" \
    --osx-bundle-identifier "com.archivist.app" \
    --distpath "$DIST_ROOT" \
    --workpath "$BUILD_ROOT/pyinstaller" \
    --specpath "$BUILD_ROOT" \
    --paths "$REPO_ROOT" \
    --add-data "$REPO_ROOT/run/web/static:run/web/static" \
    --add-data "$REPO_ROOT/fonts:fonts" \
    --collect-all webview \
    --collect-all pyexiv2 \
    --collect-all PIL \
    --collect-submodules run \
    "$SCRIPT_DIR/desktop_launcher.py"

[[ -d "$APP" ]] || { echo "PyInstaller did not create $APP." >&2; exit 1; }

PLIST="$APP/Contents/Info.plist"
for key in CFBundleShortVersionString CFBundleVersion; do
    /usr/libexec/PlistBuddy -c "Set :$key $VERSION" "$PLIST" 2>/dev/null \
        || /usr/libexec/PlistBuddy -c "Add :$key string $VERSION" "$PLIST"
done

# Re-sign after the plist edit; ad-hoc by default, which is enough to run locally.
SIGN_ARGS=(--force --deep --sign "$IDENTITY")
[[ "$IDENTITY" != "-" ]] && SIGN_ARGS+=(--options runtime --timestamp)
codesign "${SIGN_ARGS[@]}" "$APP"
codesign --verify --deep --strict "$APP"

rm -rf "$STAGING" "$DMG"
mkdir -p "$STAGING"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"
hdiutil create -volname "Archivist" -srcfolder "$STAGING" -ov -format UDZO "$DMG"
rm -rf "$STAGING"

[[ -f "$DMG" ]] || { echo "The installer was not created at $DMG." >&2; exit 1; }
echo "Installer created: $DMG"
