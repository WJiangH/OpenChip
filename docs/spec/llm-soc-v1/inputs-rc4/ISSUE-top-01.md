# llm_soc_top — integration findings

Filed by the rtl-engineer role that wired `hw/rtl/llm_soc_top/llm_soc_top.sv`
against `docs/spec/llm-soc-v1/` @ 1.0-rc3. Nothing here was "fixed" in the top:
the top contains no logic, only instances, wires and renames.

## Audit method (what "no mismatch" means below)

Every port of the fourteen instantiated modules was extracted from its
declaration and mechanically compared, per `contract.json` connection, against
the port it is joined to: direction (producer output vs consumer input), bit
width, and presence of every field named in the corresponding
`protocols.<name>.signals` entry. Result: **0 width mismatches, 0 direction
mismatches, 0 missing or extra protocol fields, 0 undriven module inputs,
0 module outputs unconnected other than the three recorded in CONNECTIONS.md §4.**
The only findings are ISSUE-top-01 below (documentation-level, wired anyway) and
the flow defect at the end (not an RTL defect).

Port-name spelling differs between authors — `npu_ctl.o_dma_dispatch_x_base` vs
`npu_dma.i_dispatch_x_base`, `cpu_bridge.axi_awvalid` vs `fabric.s0_axi_awvalid`,
`npu_dma.o_dma_terminal_done` vs `npu_ctl.i_dma_done`. Those are pure renames
and are resolved by the top's port map; they are not defects and are not listed
as issues. `hw/rtl/npu_dma/ISSUES.md` ISSUE-npu_dma-01 already asks the architect
to fix port spelling in the ICD; this integration confirms that request is worth
doing (the renames are the only thing this top had to invent).

---

## ISSUE-top-01 — `dma_terminal` (C23): producer implements sticky levels, consumer documents one-cycle pulses

- **spec_ref**: `contract.json` `protocols.dma_terminal` =
  `{"signals": {"done": 1, "error": 1, "error_code": 3}}` — no `valid`/`ready`,
  unlike `protocols.terminal`, and no statement of pulse-vs-level.
  `npu.md` §4: "DMA emits done only after output B responses; error feeds
  controller as code5/6." `connections[C23]` names only the protocol.
- **observation**: the two authors documented opposite conventions on the same
  three wires.

  Producer, `hw/rtl/npu_dma/npu_dma.sv`:

  ```systemverilog
      // C23 dma_terminal {done, error, error_code} — producer, no handshake.
      output logic       o_dma_terminal_done,
      output logic       o_dma_terminal_error,
      output logic [2:0] o_dma_terminal_error_code,
  ```

  with `hw/rtl/npu_dma/ISSUES.md` ISSUE-npu_dma-02 stating what was built:
  "sticky levels. `done`/`error`/`error_code` assert on the terminal edge and
  hold until the next accepted dispatch (C13 handshake) or reset."

  Consumer, `hw/rtl/npu_ctl/npu_ctl.sv`:

  ```systemverilog
      // C23: npu_dma -> npu_ctl, protocol dma_terminal (npu_ctl is consumer).
      // No valid/ready in this protocol (contract.json protocols.dma_terminal):
      // done/error are one-cycle, mutually-exclusive pulses; error_code is only
      // meaningful in the same cycle error is asserted (values 5 read, 6 write;
      // NPU-06 "if read and write error coincide, code5 wins" is resolved by
      // npu_dma before it asserts this pulse).
      input wire        i_dma_done,
      input wire        i_dma_error,
      input wire [ 2:0] i_dma_error_code,
  ```

- **which module I believe is wrong against `contract.json`**: neither. The
  contract does not state the rule, so both readings are legal and the defect is
  in the spec (`protocols.dma_terminal` must say "level, held until the next
  accepted dispatch" or "single-cycle pulse"). ISSUE-npu_dma-02 already asks for
  exactly that and recommends the level reading; `npu_ctl`'s comment records the
  narrower assumption but its RTL does not depend on it.
- **why it is still wired, with no glue and no safe-value tie**: a level is a
  strict superset of a pulse *for this consumer*. `npu_ctl` samples
  `i_dma_done`/`i_dma_error` only in state `ST_WAIT_DONE` and leaves that state
  on the first assertion it sees; it re-enters `ST_WAIT_DONE` only after its own
  C13 dispatch handshake, which is the same edge on which `npu_dma` clears
  `done_q`/`error_q`/`ecode_q`. So a stale level from the previous command can
  never be resampled, and a level satisfies a pulse-expecting sampler. Tying
  these three wires to a documented safe value would instead make every NPU
  command hang until the NPU-07 watchdog fires, i.e. it would destroy the
  functionality the contract requires, so it is the wrong response to a
  documentation-level divergence.
- **residual risk / what only simulation can settle**: the argument above is a
  static reading of both state machines. A system test that issues back-to-back
  commands (terminal, CLEAR, SUBMIT again) with zero idle cycles between the
  terminal record and the next SUBMIT is the check that would falsify it; that
  is a DV obligation, not something this top can decide. If it ever fires it
  shows up as a spurious terminal on the *second* command with the first
  command's `error_code`.
- **status**: wired, no glue logic, no waiver. Escalated to the chief architect
  as a spec-text defect.

---

## Not an RTL issue: flow-level defect in the lint recipe (reported, not fixed)

`make lint MOD=<mod>` runs

```
verilator --lint-only -Wall --timing --timescale 1ns/1ps \
  -Ihw/rtl -Ihw/rtl/$(MOD) $(IP_INCS) $(IP_WAIVERS) hw/rtl/$(MOD)/*.sv
```

The tool resolves a missing module `x` as `<incdir>/x.sv`, but every delivered
module lives at `hw/rtl/<x>/<x>.sv`, so `-Ihw/rtl` resolves none of them. For a
leaf module this never mattered (`-Ihw/rtl/$(MOD)` covers it); for an
integration top it makes the gate impossible to run: bare
`hw/rtl/llm_soc_top/llm_soc_top.sv` fails with

```
%Error-MODMISSING: hw/rtl/llm_soc_top/llm_soc_top.sv:...: Cannot find file containing module: 'cpu'
```

The tool also does not search the including file's own directory for
`` `include ``, so `hw/rtl/rom/rom.sv`'s `` `include "rom_data.svh" `` is
unresolvable without `-Ihw/rtl/rom`.

`flow/` and the `Makefile` are owned by the orchestrator (AGENTS.md: "Flow-level
defects you discover ... are reported, not fixed: work around inside your own
directories and flag it"). The in-directory workaround is two shim files,
`hw/rtl/llm_soc_top/llm_soc_top_deps.sv` (includes the fourteen module sources)
and `hw/rtl/llm_soc_top/rom_data.svh` (forwards to `rom/rom_data.svh`). Both
carry a header saying what they are; CONNECTIONS.md §5 tells every other flow to
exclude them. The proper fix is one of:

1. add `$(addprefix -y ,$(wildcard hw/rtl/*/))` (plus `-Ihw/rtl/rom`, or `-y`
   semantics for includes) to the lint recipe, or
2. give each module directory an `.f` filelist that the recipe consumes,

after which both shims should be deleted.
