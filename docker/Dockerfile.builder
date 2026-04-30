# OpenWrt firmware builder image
# Provides all build dependencies for compiling OpenWrt from source.
# Usage (called by scripts/build.sh — do not invoke directly):
#   docker build -f docker/Dockerfile.builder -t everywifi-builder .

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    ccache \
    cmake \
    curl \
    file \
    g++ \
    gawk \
    gettext \
    libncurses5-dev \
    libssl-dev \
    libelf-dev \
    make \
    perl \
    python3 \
    python3-distutils \
    rsync \
    subversion \
    unzip \
    wget \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root build user (OpenWrt must not be built as root)
RUN useradd -m -s /bin/bash builder
USER builder
WORKDIR /home/builder

# Clone OpenWrt source (pinned to a stable release tag)
ARG OPENWRT_TAG=v23.05.3
RUN git clone --depth 1 --branch ${OPENWRT_TAG} https://git.openwrt.org/openwrt/openwrt.git openwrt

WORKDIR /home/builder/openwrt

# Copy board config and feeds, then run the build
# BOARD and OUTPUT_DIR are injected at container run-time by scripts/build.sh
COPY --chown=builder:builder boards/ /home/builder/boards/
COPY --chown=builder:builder scripts/entrypoint-builder.sh /home/builder/entrypoint.sh

RUN chmod +x /home/builder/entrypoint.sh

ENTRYPOINT ["/home/builder/entrypoint.sh"]
