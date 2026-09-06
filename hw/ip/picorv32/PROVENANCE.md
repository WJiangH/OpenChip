# picorv32 — imported IP provenance

- Upstream: https://github.com/YosysHQ/picorv32
- Commit: a473fc8fca393771d83b0ffcf0b14db3393339d8
- License: ISC (COPYING, sha256 041ebc727233e5bf096dd41260cbb81014d3d29ca007a15f3b1807d4e9ff288e)
- picorv32.v sha256: 0836050971b3c6cdd28ac3b1e5719a67fb645161912bef1e472e63995ceb0622 (94657 bytes), byte-identical to upstream; never edited here.
- Selected configuration and integration limits: docs/spec/llm-soc-v1/dependencies.md
  (native `picorv32` module only; the upstream `picorv32_axi` wrapper is rejected
  because it has no RRESP/BRESP inputs — see intake/ip-RECOMMENDATION.md).
- Intake evidence (strict lint exit 1 / 46 warnings, Yosys check 0 problems, 0 latch
  cells) is recorded in docs/spec/llm-soc-v1/intake/; it is not an acceptance gate.
