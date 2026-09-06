# llm_soc_top — integration findings

Filed by the rtl-engineer role that wired `hw/rtl/llm_soc_top/llm_soc_top.sv`.
Re-audited against `docs/spec/llm-soc-v1/` @ 1.0-rc4 (commit `bd3b438d`,
CHANGE_ORDER_rc4.md) and the rc4-updated module sources. Nothing here was
"fixed" in the top: the top contains no logic, only instances, wires and renames.

**Open issues: none.** ISSUE-top-01 is closed by rc4 (ruling below). The rc4
re-audit found no new mismatch: the only port-level change across the seven
`rtl/*` branches is the C34 pair `npu_ctl.o_dot_lifecycle_flush` ->
`npu_dot.i_dot_lifecycle_flush`, which this top now wires as `dotlife_flush`.
Checked, not assumed: the port list (direction, width, name, order) of each of
the fourteen modules at this commit was diffed against the same file at `b9b9896`
(the rc3 top delivery). Twelve are identical, including all of the rc4-changed
sys / uart / fabric / npu_csr — their rc4 work is behavioural. The only two
deltas are `+output o_dot_lifecycle_flush` on npu_ctl and
`+input i_dot_lifecycle_flush` on npu_dot.

## Audit method (what "no mismatch" means below)

Every port of the fourteen instantiated modules was extracted from its
declaration and mechanically compared, per `contract.json` connection, against
the port it is joined to: direction (producer output vs consumer input), bit
width, and presence of every field named in the corresponding
`protocols.<name>.signals` entry. Re-run in full on the rc4 sources (778 instance
pins over fourteen modules). Result: **0 width mismatches, 0 direction
mismatches, 0 missing or extra protocol fields, 0 undriven module inputs,
0 multiply-driven nets, 0 module outputs unconnected other than the three
recorded in CONNECTIONS.md §4.** No open finding remains.

Port-name spelling differs between authors — `npu_ctl.o_dma_dispatch_x_base` vs
`npu_dma.i_dispatch_x_base`, `cpu_bridge.axi_awvalid` vs `fabric.s0_axi_awvalid`,
`npu_dma.o_dma_terminal_done` vs `npu_ctl.i_dma_done`. Those are pure renames
and are resolved by the top's port map; they are not defects and are not listed
as issues. `hw/rtl/npu_dma/ISSUES.md` ISSUE-npu_dma-01 already asks the architect
to fix port spelling in the ICD; this integration confirms that request is worth
doing (the renames are the only thing this top had to invent).

---

## ISSUE-top-01 — CLOSED by rc4 — `dma_terminal` (C23): producer implements sticky levels, consumer documents one-cycle pulses

- **status**: **closed, ruled**. CHANGE_ORDER_rc4.md row "ISSUE-npu_dma-02 +
  ISSUE-top-01 (F-04)", disposition *spec-gap*: "`dma_terminal` is **level**,
  not pulse: registered, set on the npu_dma terminal edge, held until the
  npu_dma C13 handshake edge or reset; npu_ctl samples only from the cycle after
  its own C13 handshake and takes the first sampled assertion as T." The text is
  now normative in `npu.md` NPU-09(c) and `contract.json`
  `protocols.dma_terminal.semantics`. The ruling confirms npu_dma's
  implementation and orders npu_ctl's pulse *documentation* (not its logic) to
  change; both modules were updated on their own branches, and the C23 wiring in
  this top is unchanged — the escalation cost this top no glue and no tie.
  The residual risk recorded below (back-to-back terminal -> CLEAR -> SUBMIT with
  zero idle cycles) is now an explicit rc4 DV obligation, not a top-level
  assumption. Kept below for the record; nothing here is actionable any more.

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
- **status (as filed)**: wired, no glue logic, no waiver. Escalated to the chief
  architect as a spec-text defect. Ruled in rc4, see the closure note above.

---

## Not an RTL issue: flow-level defect in the lint recipe — RESOLVED

The rc3 delivery of this top reported that `make lint MOD=<mod>` could not
resolve `hw/rtl/<x>/<x>.sv` for an integration top (it passed only `-Ihw/rtl`,
which resolves `hw/rtl/x.sv`), and worked around it with two shim files inside
this directory, `llm_soc_top_deps.sv` and `rom_data.svh`.

The flow owner fixed the recipe (commit `6a85971`: the lint rule now adds `-y`
library directories and per-module include dirs for every `hw/rtl/<m>/`), and
the two shims were deleted in commit `c14fdf8`. `make lint MOD=llm_soc_top` now
elaborates the real fourteen module sources with no file in this directory other
than `llm_soc_top.sv`. Nothing is outstanding; CONNECTIONS.md no longer carries
the "do not read these two files" section that the workaround required.
