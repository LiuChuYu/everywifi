# everywifi
開發公用wifi熱點+lora iot網路

---

## Build System

The build system runs entirely inside Docker — **Docker is the only host dependency**.

### Supported boards

| Board | Description |
|---|---|
| `mt7621` | OpenWrt firmware for MediaTek MT7621 routers |
| `xiaomi-mi-router-4a` | OpenWrt firmware for Xiaomi Mi Router 4A Gigabit |
| `docker-sim` | Docker simulation image for local development/testing |

### Quick start

```bash
# Build firmware for MT7621
make build BOARD=mt7621

# Build firmware for Xiaomi Mi Router 4A Gigabit
make build BOARD=xiaomi-mi-router-4a

# Build the simulation image
make build BOARD=docker-sim

# Run the simulation environment (builds image if needed)
make sim

# Force-rebuild the simulation image, then run it
make sim-rebuild

# Clean all build output
make clean

# Clean output for a specific board only
make clean BOARD=mt7621
```

You can also call the scripts directly:

```bash
./scripts/build.sh mt7621
./scripts/build.sh xiaomi-mi-router-4a
./scripts/build.sh docker-sim
./scripts/run-sim.sh
./scripts/run-sim.sh --rebuild
```

### Directory structure

```
everywifi/
├── boards/
│   ├── mt7621/config               # OpenWrt .config for MT7621 (ramips/mt7621)
│   ├── xiaomi-mi-router-4a/config  # OpenWrt .config for Xiaomi Mi Router 4A Gigabit
│   └── docker-sim/config           # Simulation environment settings
├── docker/
│   ├── Dockerfile.builder  # Ubuntu-based OpenWrt build container
│   └── Dockerfile.sim      # Alpine-based simulation runtime
├── scripts/
│   ├── build.sh            # Board-selection build entry point
│   ├── run-sim.sh          # Launch simulation environment
│   ├── entrypoint-builder.sh  # Builder container entry point
│   └── entrypoint-sim.sh   # Simulation container entry point
├── output/                 # Build artifacts (git-ignored)
│   └── <board>/
└── Makefile
```

### Adding a new board

1. Create `boards/<board-name>/config` with target-specific settings.
2. Add a `case` block in `scripts/build.sh` with the board's build steps.
3. Run `make build BOARD=<board-name>`.
