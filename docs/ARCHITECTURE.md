# Platform Architecture

OpenChip is two things: a **flow** (spec → GDSII, all open source) and an **agent
organization** that operates the flow ([AGENTS.md](AGENTS.md)). This document covers the flow.

## Design decisions and rationale

### HDL: SystemVerilog, Yosys-safe synthesizable subset

| Considered | Verdict |
|---|---|
| **SystemVerilog (subset)** | ✅ Chosen. Largest LLM training corpus by far → agents write it best; native input to Verilator, Yosys, LibreLane; what industry DV expects. |
| Chisel / SpinalHDL | Great for humans, thin LLM corpus, adds a Scala generation step between agents and tool diagnostics. Revisit for generators later. |
| Amaranth (Python) | Attractive (agents write Python well) but small corpus and community. Candidate for peripheral generators in v2. |

The subset is what Yosys reads natively (see CLAUDE.md conventions). If we later
need full SV (interfaces, unpacked structs), the escape hatch is the
`yosys-slang` frontend or `sv2v` — an ADR must be written before adopting either.

### Simulation: Verilator primary, Icarus secondary

Verilator compiles RTL to C++ — fast enough for full-SoC firmware boots and
CoreMark in CI. Icarus stays available for the rare event-driven/4-state corner
Verilator can't model. Testbenches are **cocotb** so they are simulator-portable
and agents write them in Python.

### Formal: SymbiYosys

BMC + k-induction over SMT solvers. Used for: Wishbone protocol compliance
(bus never hangs, one-hot grants, handshake liveness), FIFO invariants,
CSR write/read-back correctness, and core lock-step properties where feasible.

### Golden models: Spike + Python

- **Spike** (`riscv-isa-sim`) is the ISA golden model. The core is proven by
  riscv-arch-test/RISCOF signature comparison, and optionally per-instruction
  co-simulation (commit-log diff) for debug.
- Peripheral golden models are plain Python in `verif/common/models/`,
  written from the spec by DV agents (never from the RTL).

### Physical design: LibreLane on OpenROAD

LibreLane (the 2026 continuation of OpenLane 2, first release 3.0.0) drives
Yosys → OpenROAD → Magic/KLayout/Netgen. Python-configurable, Dockerized,
reproducible. PDK: **sky130A** primary (largest community knowledge base,
active Tiny Tapeout shuttles), **IHP SG13G2** as the second target to keep the
flow honest about portability.

### Proof-of-life ladder (no physical hardware)

Confidence is built in rungs, each machine-checked:

1. Lint clean (Verilator + Verible)
2. Unit sim green + coverage ≥ gate (cocotb/Verilator)
3. Formal proofs pass (SymbiYosys)
4. ISA compliance: riscv-arch-test 100%, signatures == Spike
5. Full-SoC sim: boots ROM firmware, UART "hello", CoreMark checksum correct
6. Post-synth: Yosys netlist equivalence smoke + OpenSTA timing met
7. Post-layout: DRC clean, LVS clean
8. **Gate-level sim with SDF timing re-runs rung 5 firmware** — the strongest
   pure-simulation claim that the manufactured chip will work
9. (Optional, real world) Tiny Tapeout shuttle → physical bring-up report

## Environment & reproducibility

Everything runs from pinned versions — "works on my machine" is banned:

| Component | Distribution | Pin |
|---|---|---|
| Yosys, Verilator, Icarus, SymbiYosys, GTKWave, Verible | [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build) nightly tarball | date-pinned in `flow/versions.mk` |
| LibreLane + OpenROAD + signoff | Docker image (or Nix) | tag-pinned in `flow/versions.mk` |
| RISC-V GCC | xPack `riscv-none-elf-gcc` | version-pinned |
| Spike, RISCOF | built from source / pip | commit/version-pinned |
| cocotb | pip, `requirements.txt` | version-pinned |

CI (GitHub Actions) installs the same pins, so an agent's local green == CI green.

## Directory contract

```
docs/spec/          One .md per architectural unit: ISA subset, memory map,
                    each peripheral's registers & behavior. Numbered sections
                    so RTL/DV/formal can cite "spec §3.2".
rtl/<mod>/          <mod>.sv (+ submodule files). No testbench code.
verif/<mod>/        cocotb suite + Makefile; BUGS.md for open bug reports.
verif/common/       shared drivers/monitors/scoreboards + golden models.
formal/<mod>/       <mod>.sby + properties file (bind-able SVA).
sw/                 crt0.S, link.ld, libc-lite, apps/ (hello, coremark).
syn/                per-module yosys scripts + STA constraints (.sdc).
pd/<top>/           LibreLane config.yaml, pin order, floorplan notes; runs/
                    output is gitignored, signoff summaries are committed.
flow/               sim.mk, formal.mk, synth.mk, gates.mk (thresholds),
                    versions.mk (tool pins).
```

## Architecture Decision Records

Any change to: HDL subset, bus protocol, reset scheme, tool choice, PDK,
coverage/timing gates → requires an ADR in `docs/adr/NNNN-title.md`
(context, decision, consequences) merged via reviewed PR.
