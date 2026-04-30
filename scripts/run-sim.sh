#!/usr/bin/env bash
# run-sim.sh — Build (if needed) and run the docker-sim environment.
#
# Usage:
#   ./scripts/run-sim.sh [--rebuild]
#
# Options:
#   --rebuild   Force a fresh image build before running

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="everywifi-sim:latest"
REBUILD=false

for arg in "$@"; do
    case "${arg}" in
        --rebuild) REBUILD=true ;;
        *) echo "Unknown option: ${arg}"; exit 1 ;;
    esac
done

# Build image if it doesn't exist or --rebuild was requested
if [[ "${REBUILD}" == "true" ]] || ! docker image inspect "${IMAGE}" &>/dev/null; then
    echo "==> Building simulation image..."
    docker build \
        -f "${REPO_ROOT}/docker/Dockerfile.sim" \
        -t "${IMAGE}" \
        "${REPO_ROOT}"
fi

echo "==> Starting everywifi simulation (Ctrl+C to stop)..."
docker run --rm -it \
    --name everywifi-sim \
    --cap-add=NET_ADMIN \
    --cap-add=SYS_ADMIN \
    -p 5353:53/udp \
    -p 8080:80/tcp \
    "${IMAGE}"
