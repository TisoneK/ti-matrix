#!/bin/sh
# Build the sidecar bundle the desktop app ships: PyInstaller one-dir -> app/release/sidecar/.
# Runs on CI's three OSes and locally, from server/:  sh scripts/build-sidecar.sh
set -e
cd "$(dirname "$0")/.."

python -m PyInstaller ti-matrix-server.spec --noconfirm --distpath build
# electron-builder's extraResources reads this directory (app/electron-builder.yml)
rm -rf ../app/release/sidecar
mkdir -p ../app/release
cp -R build/ti-matrix-server ../app/release/sidecar
echo "sidecar bundle ready at app/release/sidecar"
