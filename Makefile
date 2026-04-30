# everywifi — top-level build targets
#
# Usage:
#   make build BOARD=mt7621       # Build OpenWrt firmware for MT7621
#   make build BOARD=docker-sim   # Build Docker simulation image
#   make sim                      # Run the simulation environment
#   make sim-rebuild              # Rebuild and run the simulation
#   make clean                    # Remove build output
#   make clean BOARD=mt7621       # Remove output for a specific board

SHELL := /bin/bash
.DEFAULT_GOAL := help

REPO_ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
BOARD ?=
OUTPUT_DIR := $(REPO_ROOT)output

.PHONY: help build sim sim-rebuild clean

help:
	@echo "everywifi build system"
	@echo ""
	@echo "Targets:"
	@echo "  make build BOARD=<board>   Build firmware/image for the given board"
	@echo "  make sim                   Run the docker-sim environment"
	@echo "  make sim-rebuild           Rebuild the sim image then run it"
	@echo "  make clean [BOARD=<board>] Remove build output"
	@echo ""
	@echo "Supported boards:"
	@for d in boards/*/; do echo "  $${d#boards/}" | tr -d '/'; done

build:
ifndef BOARD
	$(error BOARD is not set. Usage: make build BOARD=<board>)
endif
	@bash scripts/build.sh "$(BOARD)"

sim:
	@bash scripts/run-sim.sh

sim-rebuild:
	@bash scripts/run-sim.sh --rebuild

clean:
ifdef BOARD
	rm -rf "$(OUTPUT_DIR)/$(BOARD)"
	@echo "Removed output for board: $(BOARD)"
else
	rm -rf "$(OUTPUT_DIR)"
	@echo "Removed all build output"
endif
