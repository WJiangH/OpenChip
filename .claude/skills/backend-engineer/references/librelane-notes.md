# LibreLane / signoff notes (P0, LibreLane 3.0.5)

- Exit 0 ≠ clean: the flow exits 0 with real violations logged as warnings.
  Read final/metrics.json (`design__*_violation__count`) and per-corner
  checks.rpt; quote them in SIGNOFF.md.
- Config keys drift across 3.x (FP_CORE_MARGIN removed, FP_PDN_*→PDN_*).
  Self-serve the live schema inside the image:
  `python3 -c "from librelane.flows import Flow; print(Flow.factory.get('Classic').config_vars)"`
- Always mount the PDK cache `~/.ciel` (make gds does); first fetch ~2.1 GB.
- Pin images by digest — ghcr tags are mutable and there is no `latest`.
- Docker registry ops hang forever when ~/.docker/config.json has
  `credsStore: desktop` and the keychain is unreachable:
  `DOCKER_CONFIG=<dir containing '{}' config.json> docker ...`
- Long unbuffered nets on sparse dies → max-slew violations. Fix by
  TIGHTENING repair knobs (DESIGN_REPAIR_MAX_WIRE_LENGTH, slew margin),
  never by loosening the limit; record rejected approaches in SIGNOFF.md.
- Yosys mapped-netlist `check` needs `read_liberty -lib` first or every cell
  output reads undriven; `splitnets -ports` harms scalar ports.
