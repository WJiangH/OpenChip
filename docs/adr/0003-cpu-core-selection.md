# ADR 0003 — CPU core selection: PicoRV32 for the SoC control core

**Status: proposed — AWAITING HUMAN APPROVAL. This ADR is not accepted and no spec, RTL,
DV, model or PD work may derive from it until a human maintainer changes this line.**

Date: 2026-07-27 · Author role: chief-architect · Supersedes: nothing · Depends on: ADR 0001, ADR 0002

Evidence base: desk research against each project's own upstream repository and
documentation (no local runnable script — this ADR does not introduce a `cost_model.py`
because no dimension here needed simulation; every number is a citation, not a derivation).
All sources are linked inline and collected in "Sources" at the end.

---

## Context

Per ADR 0002 (proposed), the NPU is a 1×8 weight-streaming GEMV unit and the CPU's job
is orchestration only: kernel dispatch, DMA descriptor setup, UART, and (per issue #1)
**performance is explicitly not a selection criterion**. What is a criterion, per CLAUDE.md
and the issue: license compatibility, verification maturity, sky130 area, toolchain fit
with the Yosys-native SV subset fixed by ADR 0001, integration effort onto Wishbone B4,
and a path to the M2 gate — riscv-arch-test via RISCOF against Spike, which CLAUDE.md
states is "not negotiable."

Two candidates named in the issue: **ibex** (lowRISC) and **PicoRV32** (Clifford Wolf /
YosysHQ).

---

## Decision

### D1 — Selected core: PicoRV32

Recommended configuration: RV32IMC (M for address/pointer arithmetic in firmware, C to
shrink the firmware image; both optional and can be dropped if area gets tight), using
the upstream `picorv32_wb` variant.

### D2 — Criterion-by-criterion comparison

**License.**
Both are permissively licensed. Ibex is Apache-2.0
([lowRISC/ibex](https://github.com/lowRISC/ibex)). PicoRV32 is ISC
([YosysHQ/picorv32](https://github.com/YosysHQ/picorv32)) — functionally a BSD-2-Clause/MIT
equivalent, but ISC is not one of the three licenses CLAUDE.md names explicitly
(Apache-2.0/BSD/MIT). Flagged as **Q1** below rather than silently treated as equivalent.
**Wash, pending Q1.**

**Toolchain fit — Yosys-native SV subset (ADR 0001).**
PicoRV32 is a single-file, Verilog-2001-style synthesizable core written by Yosys's own
author; it is Yosys-native by construction and has no dependency on SystemVerilog
interfaces, classes, or packages. Ibex is written in more structured SystemVerilog, and
CHIPS Alliance / Antmicro's own writeup of getting ibex through an open-source synthesis
flow is titled "Enabling Open Source Ibex Synthesis... via UHDM/Surelog"
([antmicro.com/blog/2020/12](https://antmicro.com/blog/2020/12/ibex-support-in-verilator-yosys-via-uhdm-surelog),
[chipsalliance.org](https://www.chipsalliance.org/news/ibex-synthesis-and-simulation/)) —
i.e. the community's own path to synthesizing ibex through Yosys runs via an added
UHDM/Surelog (or, today, yosys-slang) frontend, not vanilla Yosys. ADR 0001 already
names that frontend as an explicit escape hatch that **"requires a new ADR"** if ever
needed. Selecting ibex would very likely trigger that clause immediately, before a single
line of the CPU spec is written. **PicoRV32 wins decisively.**

**Integration effort — Wishbone B4.**
PicoRV32 ships an **official, first-party** Wishbone B4 master wrapper in the upstream
repo (`picorv32_wb.v`, with its own `testbench_wb.v`), alongside the native and AXI4-Lite
variants (verified directly from the repo listing,
[github.com/YosysHQ/picorv32](https://github.com/YosysHQ/picorv32)). Ibex's native bus is
OBI ([OBI v1.0 spec via openhwgroup](https://github.com/lowRISC/ibex/issues/758)); its
only first-party wrapper is OpenTitan's TileLink-UL adapter
([opentitan.org/book/hw/ip/rv_core_ibex](https://opentitan.org/book/hw/ip/rv_core_ibex/)),
neither of which is Wishbone. Wishbone wrappers for ibex exist only as small third-party
forks with no visible relationship to lowRISC and no evident active maintenance
([pbing/ibex_wb](https://github.com/pbing/ibex_wb),
[batuhanates/ibex_wb](https://github.com/batuhanates/ibex_wb)). **PicoRV32 wins:** zero
new RTL needed for the bus adapter versus either writing one from scratch or taking on an
unmaintained third-party dependency.

**Verification maturity (upstream DV environment, silicon track record).**
Ibex has a real UVM/SV testbench (`dv/uvm/core_ibex`) driven by Google's `riscv-dv`
random instruction generator, cosimulated instruction-by-instruction against a
lowRISC-forked Spike, reaching what lowRISC calls "V2S" maturity (>90% code + functional
coverage) for the OpenTitan configuration
([ibex verification docs](https://github.com/lowRISC/ibex/blob/master/doc/03_reference/verification.rst)).
This is a genuinely strong environment — but Iron Rule 2 in this repo means OpenChip's DV
role writes its own independent cocotb testbench from the spec regardless of what either
upstream ships; ibex's UVM bench is not something this project inherits or runs. Its
practical value to us is indirect (confidence that the *design* has been heavily exercised
upstream), not direct (we don't reuse the bench). PicoRV32's own repo verification is
lighter — directed tests from `riscv-tests` plus `testbench.v`/`testbench_wb.v`
([repo listing](https://github.com/YosysHQ/picorv32)) — but it has RVFI bindings in the
`riscv-formal` framework (`cores/picorv32/`), giving it exhaustive bounded formal proof of
ISA compliance on top of directed simulation
([SymbioticEDA/riscv-formal](https://github.com/SymbioticEDA/riscv-formal)), which fits
this project's existing SymbiYosys-based formal flow (ADR 0001) directly.
Silicon track record tips further toward PicoRV32 for *this* project specifically:
PicoRV32 is the management-core CPU of Efabless Caravel, the harness used across dozens of
real SkyWater **sky130** MPW/chipIgnite shuttles, clocked at ~50 MHz
([efabless/caravel](https://github.com/efabless/caravel)) — the same PDK and almost
exactly the same clock target this project already committed to
(`flow/gates.mk` `CLOCK_PERIOD_NS = 20`). Ibex's silicon record (OpenTitan Earl Grey and
academic tapeouts) is real and arguably broader in absolute terms, but none of it is on
sky130. **Net: roughly even on rigor, PicoRV32 ahead on relevance** — proven on our exact
PDK and clock target, plus a formal-proof path that plugs into tooling we already run.

**Area on sky130.**
Neither core has an officially published *standalone-core* sky130 area number; this is
flagged as **Q3**, not guessed. Available anchors, all noted with their caveats:
- PicoRV32: FPGA utilization only in the official README (761 Slice LUTs / 442 registers,
  small variant; 917/583 regular; 2019/1085 large —
  [github.com/YosysHQ/picorv32](https://github.com/YosysHQ/picorv32)), plus one
  community-reported ASIC figure of **5,437 gate-equivalents** at 250 nm (Design Compiler,
  LEDA library) that the reporter themself flagged as uncertain
  ([issue #119](https://github.com/cliffordwolf/picorv32/issues/119)) — a single
  third-party data point, not a benchmark.
- Ibex: 57 kGE for the "RV32EMCB" *embedded* baseline configuration (with M and B
  extensions enabled, which this project doesn't need) on **FreePDK45**, not sky130, from
  a commercial synthesis tool
  ([lowrisc.org/news/memory-safety-features...](https://lowrisc.org/news/memory-safety-features-impact-on-ibex-based-processor-area/)).
  FreePDK45 vs sky130 (130 nm) standard-cell density differs enough that this number
  cannot be rescaled with any confidence.
Even granting generous error bars on both, PicoRV32 is almost certainly the smaller core
by a wide margin — consistent with its design goal (`picorv32` literally means
"size-optimized") versus ibex's broader feature/verification surface. Against ADR 0002's
free-form 2×2 mm die budget (3.24 mm² core, 14% already spoken for by the NPU), neither
core is an existential area risk, so this criterion is directional, not decisive — but it
adds one more small point in PicoRV32's favor for a control-only, performance-agnostic
core exactly matching the issue's framing.

**riscv-arch-test / RISCOF path (M2 gate).**
This is ibex's strongest showing: the upstream repo directly vendors
`riscv-arch-tests`, `riscv-isa-sim` (Spike), and `google_riscv-dv` under `vendor/`
([lowRISC/ibex vendor tree](https://github.com/lowRISC/ibex/tree/master/vendor)) — i.e.
the exact RISCOF-against-Spike shape CLAUDE.md mandates is already wired up upstream.
PicoRV32 has **no** vendored `riscv-arch-test`, RISCOF plugin, or Spike integration in its
own repo; only ad hoc `riscv-tests` ([repo listing](https://github.com/YosysHQ/picorv32)).
This is real, honest cost: OpenChip will have to build its own RISCOF DUT plugin
(signature dump + linker script glue) for PicoRV32 from scratch. It is not, however, a
novel problem — RISCOF's DUT interface is signature-file-based and core-agnostic by
design, and PicoRV32's simplicity (no privileged-mode complexity beyond machine mode, no
PMP, no vectors) makes it one of the easier cores to wire up this way. Weighed against the
Yosys-subset and Wishbone-integration costs ibex would introduce immediately, this is the
better trade: a bounded, one-time DV-role task versus an immediate ADR-0001 escape-hatch
trigger. **Ibex wins the criterion in isolation; PicoRV32 wins the trade.**

### D3 — Net call

Weighting the criteria this project's own constraints weight hardest — staying inside the
Yosys-native SV subset ADR 0001 already committed to, minimizing new unmaintained
dependencies, and reusing this project's existing SymbiYosys formal flow — PicoRV32 is the
better fit despite ibex's stronger out-of-the-box RISCOF/Spike story. The RISCOF gap is
real and is carried forward as an explicit integration-spec obligation (Q2), not
hand-waved.

---

## Rejected alternative

**ibex (lowRISC).** Rejected, not because it is a weaker core — its verification pedigree
and silicon track record are both genuinely stronger in absolute terms — but because two
of its properties directly collide with decisions this project already made:
1. Its practical open-source synthesis path needs a UHDM/Surelog- or slang-based frontend
   rather than vanilla Yosys, which per ADR 0001 requires opening a new ADR before this
   project could even lint it, let alone synthesize it.
2. It has no first-party Wishbone B4 wrapper, only unofficial, apparently-unmaintained
   forks, versus PicoRV32's upstream `picorv32_wb.v`.
Both are process/dependency costs, not capability gaps, but they are costs this project
does not need to pay: nothing about the CPU's job (orchestration, not performance) needs
ibex's larger feature set (PMP, bitmanip, ECC caches, cheriot variants) to begin with.

---

## Consequences

- (+) Zero new RTL needed for the bus adapter (`picorv32_wb` is upstream and
  first-party); the integration spec can go straight to CSR/descriptor design instead of
  bus-wrapper design.
- (+) Stays inside the Yosys-native SV subset ADR 0001 already committed the project to;
  no new escape-hatch ADR forced by the CPU choice.
- (+) Real sky130 silicon precedent at ~50 MHz via Efabless Caravel, the closest thing to
  an existing "proof this runs on our exact PDK and clock" available for either candidate.
- (+) `riscv-formal` RVFI bindings already exist for PicoRV32 and plug into the
  SymbiYosys flow this project already runs (ADR 0001) — a bounded formal ISA-compliance
  proof is available cheaply, independent of the RISCOF simulation gate.
- (−) **No existing RISCOF/Spike integration.** Building the DUT plugin (signature dump +
  Spike reference run) for the M2 gate is new work with no upstream template to start
  from, unlike ibex. This is the single biggest cost this decision accepts; it must be
  scoped explicitly in the integration spec, not discovered at M2.
- (−) PicoRV32's interrupt mechanism is a small custom scheme, not a standard RISC-V
  CLINT/PLIC. Kernel-dispatch and DMA-completion signaling will need a small
  project-owned interrupt/CSR block regardless of which core was chosen (ibex doesn't
  ship a PLIC either — OpenTitan supplies its own), so this is core-agnostic work, not an
  ibex-avoided cost, but it must be scoped in the integration spec.
- (−) PicoRV32's own repo verification (directed `riscv-tests` + a Verilog testbench) is
  materially lighter than ibex's UVM/riscv-dv environment. This project's own DV role
  writes independent tests regardless (Iron Rule 2), which caps how much this really costs
  us, but it means less upstream bug-finding to lean on going in.
- (−) ISC license is functionally permissive but not literally on CLAUDE.md's named list
  (Apache-2.0/BSD/MIT); needs an explicit one-line human sign-off rather than being
  silently treated as equivalent (Q1).

---

## Open questions the integration spec MUST settle

**Q1 — ISC license sign-off.** Confirm ISC is acceptable under the project's IP policy
(it is textually near-identical to BSD-2-Clause/MIT, but CLAUDE.md names three specific
licenses and ISC isn't one of them). Low risk, but a human call, not an agent one.

**Q2 — RISCOF/Spike DUT plugin for PicoRV32.** No upstream template exists. The
integration spec must define: how the DUT emits a RISCOF-compatible signature dump from
cocotb/Verilator, which Spike build/config serves as reference, and which subset of
riscv-arch-test applies given the chosen extension set (Q4). This is the load-bearing
open question of this ADR — everything else here is a smaller cost than this one.

**Q3 — Real sky130 area number.** No official standalone-core sky130 synthesis exists for
either candidate. A trial Yosys synthesis of `picorv32_wb` against
`sky130_fd_sc_hd` (mirroring the blink signoff flow, ADR 0002 §"Area anchors") should run
before spec freeze, both to pin the real number and to confirm PicoRV32 lints/synthesizes
cleanly end-to-end in this project's actual flow rather than resting on the README's FPGA
figures.

**Q4 — Extension set.** RV32IMC is recommended above (M for firmware address math, C for
code size) but neither is forced by anything architectural here since performance is not
a criterion; RV32I-only is a legitimate smaller-and-simpler fallback if Q3's area number or
Q2's RISCOF scoping favor shrinking the ISA surface. The integration spec must pick one.

**Q5 — Interrupt/CSR architecture.** Per the Consequences section: PicoRV32's native IRQ
scheme vs. a small project-owned CLINT-like block. This gates the DMA-completion and
UART-interrupt story and should be settled alongside the Wishbone descriptor model (ADR
0002 Q4, which is the NPU-side half of the same bus programming model).

---

## Sources

- [lowRISC/ibex](https://github.com/lowRISC/ibex) — overview, license, RTL
- [Ibex verification docs](https://github.com/lowRISC/ibex/blob/master/doc/03_reference/verification.rst) — UVM/riscv-dv/Spike cosim methodology, V2S coverage claim
- [Ibex compliance docs](https://ibex-core.readthedocs.io/en/latest/01_overview/compliance.html) — ISA/privileged-spec versions
- [Ibex vendor tree](https://github.com/lowRISC/ibex/tree/master/vendor) — vendored riscv-arch-tests, riscv-isa-sim, google_riscv-dv
- [Ibex issue #758](https://github.com/lowRISC/ibex/issues/758) — OBI bus alignment
- [OpenTitan rv_core_ibex docs](https://opentitan.org/book/hw/ip/rv_core_ibex/) — TileLink-UL wrapper
- [pbing/ibex_wb](https://github.com/pbing/ibex_wb), [batuhanates/ibex_wb](https://github.com/batuhanates/ibex_wb) — unofficial Wishbone forks
- [lowRISC: memory-safety features impact on Ibex area](https://lowrisc.org/news/memory-safety-features-impact-on-ibex-based-processor-area/) — 57 kGE FreePDK45 baseline
- [Antmicro: Ibex synthesis via UHDM/Surelog](https://antmicro.com/blog/2020/12/ibex-support-in-verilator-yosys-via-uhdm-surelog), [CHIPS Alliance mirror](https://www.chipsalliance.org/news/ibex-synthesis-and-simulation/) — open-source Yosys-adjacent synthesis path
- [YosysHQ/picorv32](https://github.com/YosysHQ/picorv32) — overview, license, configs, `picorv32_wb.v`, FPGA utilization figures
- [picorv32 issue #119](https://github.com/cliffordwolf/picorv32/issues/119) — community-reported 5,437 GE @ 250 nm
- [SymbioticEDA/riscv-formal](https://github.com/SymbioticEDA/riscv-formal) — PicoRV32 RVFI bindings
- [efabless/caravel](https://github.com/efabless/caravel) — PicoRV32-based management SoC, sky130, ~50 MHz, real MPW/chipIgnite silicon
- [efabless/raven-picorv32](https://github.com/efabless/raven-picorv32) — first silicon-validated PicoRV32 SoC
