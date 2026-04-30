#!/usr/bin/env bash
# build.sh — Board-selection build entry point
#
# Usage:
#   ./scripts/build.sh <board>
#
# Supported boards:
#   mt7621               — OpenWrt firmware for MediaTek MT7621 routers
#   xiaomi-mi-router-4a  — OpenWrt firmware for Xiaomi Mi Router 4A Gigabit
#   docker-sim           — Docker simulation image for local testing
#
# The build runs entirely inside a Docker container; Docker is the only
# host dependency.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOARD="${1:-}"

usage() {
    echo "Usage: $0 <board>"
    echo ""
    echo "Supported boards:"
    echo "  mt7621               OpenWrt firmware for MT7621 routers"
    echo "  xiaomi-mi-router-4a  OpenWrt firmware for Xiaomi Mi Router 4A Gigabit"
    echo "  docker-sim           Docker simulation image for local testing"
    exit 1
}

[[ -z "${BOARD}" ]] && { echo "ERROR: No board specified."; usage; }

BOARD_DIR="${REPO_ROOT}/boards/${BOARD}"
if [[ ! -d "${BOARD_DIR}" ]]; then
    echo "ERROR: Unknown board '${BOARD}'. Available boards:"
    ls "${REPO_ROOT}/boards/"
    exit 1
fi

OUTPUT_DIR="${REPO_ROOT}/output/${BOARD}"
mkdir -p "${OUTPUT_DIR}"

echo "==> Board     : ${BOARD}"
echo "==> Output    : ${OUTPUT_DIR}"
echo ""

case "${BOARD}" in
    docker-sim)
        echo "==> Building docker-sim image..."
        docker build \
            -f "${REPO_ROOT}/docker/Dockerfile.sim" \
            -t everywifi-sim:latest \
            "${REPO_ROOT}"
        echo "==> docker-sim image built: everywifi-sim:latest"
        echo "    Run with: ./scripts/run-sim.sh"
        ;;

    mt7621|xiaomi-mi-router-4a)
        echo "==> Building OpenWrt firmware for ${BOARD}..."
        docker build \
            -f "${REPO_ROOT}/docker/Dockerfile.builder" \
            -t everywifi-builder:latest \
            "${REPO_ROOT}"

        docker run --rm \
            -e BOARD="${BOARD}" \
            -v "${OUTPUT_DIR}:/output/${BOARD}" \
            everywifi-builder:latest

        echo "==> Firmware artifacts saved to: ${OUTPUT_DIR}"
        ;;

    *)
        echo "ERROR: Board '${BOARD}' is recognized but has no build rule." >&2
        echo "       Add a case block in scripts/build.sh." >&2
        exit 1
        ;;
esac

echo "==> Done."
