# CLAUDE.md — Rules for all agents working in this repo

OpenChip is an end-to-end open-source silicon platform built by collaborating AI agents.
Read this file fully before touching anything. These rules are non-negotiable.

## The Iron Rules

1. **The spec is the single source of truth.** Everything derives from `docs/spec/`.
   If the spec is ambiguous or wrong, STOP and escalate to the architect role /
   the human maintainer — never silently "fix" behavior in RTL or testbench.

2. **Design/DV independence.** The agent (or session) that writes a module's RTL
   must never write or modify that module's testbench, and vice versa.
   - RTL work writes only under `rtl/` (+ its formal constraints under `formal/` are OK).
   - DV work writes only under `verif/` and derives expected values from
     `docs/spec/` and golden models — **never** from reading the RTL implementation.
   - If a test fails, the DV agent files a bug report (GitHub issue or
     `verif/<mod>/BUGS.md`); it does not patch the RTL. The RTL agent fixes it.

3. **Tools are the arbiter.** Work is done only when the machine says so:
   lint clean → sim green → coverage met → formal proven → timing met → DRC/LVS clean.
   Never claim success without pasting the actual tool output summary.

4. **One module per branch.** Branch names: `rtl/<mod>`, `dv/<mod>`, `formal/<mod>`,
   `pd/<top>`, `sw/<feature>`. Agents work in separate git worktrees and merge via PR.

5. **Never weaken a gate to make it pass.** Do not lower coverage thresholds, waive
   lint rules, loosen timing constraints, or delete failing tests without an
   explicit human-approved note in the PR description.

## Commands

```bash
make lint                # Verilator --lint-only + Verible over all rtl/
make sim MOD=<mod>       # cocotb suite for one module (omit MOD for all)
make formal MOD=<mod>    # SymbiYosys proof for one module
make synth MOD=<mod>     # Yosys synth + OpenSTA report
make gds  MOD=<top>      # LibreLane RTL→GDSII (Docker)
make sw                  # build RISC-V firmware (requires riscv-none-elf-gcc)
make clean
```

## RTL conventions (Yosys-safe SystemVerilog subset)

- One module per file; filename == module name; lowercase `snake_case` everywhere.
- `` `default_nettype none `` at top of every file, `` `default_nettype wire `` at bottom.
- Synchronous, active-low reset named `rst_n`; every flop resets. Clock named `clk`.
- `always_ff` / `always_comb` only — no plain `always`, no latches, no `initial`
  (except in testbench/formal code), no delays, no tri-state on internal logic.
- Stay inside the Yosys-supported SV subset: no classes, no interfaces in
  synthesizable code, no unpacked-struct ports across the synthesis boundary.
- Wishbone B4 pipelined is the on-chip bus. Signal prefix `wb_`.
- Module I/O: `i_` inputs, `o_` outputs (bus ports keep the `wb_` prefix convention).

## Verification conventions

- cocotb testbenches in `verif/<mod>/`, one `Makefile` including `flow/sim.mk`.
- Golden/reference models live in `verif/common/models/` as plain Python;
  they must cite the spec section they implement in a docstring.
- Every test suite ends by writing coverage; the gate is ≥ 90% line + toggle
  (thresholds live in `flow/gates.mk` — never edit them to pass, see Iron Rule 5).
- The RISC-V core is additionally verified by riscv-arch-test/RISCOF against
  Spike — architectural compliance is not negotiable.

## Commit signature convention

Every agent commits its own deliverables with its role signature as the git
author, format `<role>-agent-<Model><Version>-<effort>`:

```
git commit --author="dv-agent-Sonnet5-high <dv-engineer@agents.openchip>" ...
```

The model/effort in the signature is what the session actually ran on — no
honorary upgrades. One role's deliverables per commit; don't mix roles.

## When you finish a task

1. Run the relevant `make` gates locally and include the summary lines in your report.
2. Open a PR; CI re-runs the gates. The reviewer role checks spec conformance.
3. Report honestly: failing gates, skipped checks, and open questions go in the
   PR description — surfacing a failure is rewarded, hiding one is a protocol breach.
