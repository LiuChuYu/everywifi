#!/usr/bin/env bash
# entrypoint-builder.sh — runs inside the Dockerfile.builder container
# Called automatically by scripts/build.sh; do not invoke directly.
set -euo pipefail

BOARD="${BOARD:?'BOARD env var is required (e.g. mt7621)'}"
OUTPUT_DIR="/output/${BOARD}"

OPENWRT_DIR="/home/builder/openwrt"
BOARD_CONFIG="/home/builder/boards/${BOARD}/config"

echo "==> Building for board: ${BOARD}"

if [[ ! -f "${BOARD_CONFIG}" ]]; then
    echo "ERROR: Board config not found: ${BOARD_CONFIG}" >&2
    exit 1
fi

cd "${OPENWRT_DIR}"

# Install feeds
./scripts/feeds update -a
./scripts/feeds install -a

# Apply board config
cp "${BOARD_CONFIG}" .config
make defconfig

# Build
make -j"$(nproc)" V=s

# Collect artifacts
mkdir -p "${OUTPUT_DIR}"
find bin/targets -type f \( -name "*.bin" -o -name "*.img" -o -name "*.itb" \) \
    -exec cp {} "${OUTPUT_DIR}/" \;

echo "==> Build complete. Artifacts in ${OUTPUT_DIR}"
