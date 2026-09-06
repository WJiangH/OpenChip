# cpu_bridge — spec findings (rtl-engineer, SIM-L1 1.0-rc3)

Filed by the RTL author against `docs/spec/llm-soc-v1/` at 1.0-rc3. None of these
were resolved in RTL: each entry records the most conservative reading that was
implemented meanwhile, marked in the source with `// ISSUE-cpu_bridge-NN: provisional`.

---

## ISSUE-cpu_bridge-01 — native handshake semantics are not specified anywhere

- **spec_ref**: `contract.json` `protocols.native` — the whole definition is
  `{"signals": {"mem_valid":1, "mem_instr":1, "mem_ready":1, "mem_addr":32,
  "mem_wdata":32, "mem_wstrb":4, "mem_rdata":32}}`. `system.md` SYS-02: "Selected core
  is PicoRV32 native interface, with project-owned error-aware native→AXI adapter".
  `axi.md` AXI-02: "The native CPU already aligns addresses, replicates subword store
  data and supplies mapped WSTRB."
- **observation**: The contract lists native *signals* and their widths, but no
  handshake rule: it does not state that `mem_wstrb != 0` selects a write and
  `mem_wstrb == 0` a read, that `mem_ready` is a one-cycle completion pulse sampled
  with `mem_rdata` in the same cycle, whether the initiator may hold `mem_valid`
  asserted across two back-to-back requests, or whether `mem_ready` may depend
  combinationally on `mem_valid`. The only place these rules exist is the pinned
  upstream PicoRV32 implementation, which the spec forbids the DV side from reading
  and which the architect states was not read either (dependencies.md preamble).
- **why_it_blocks**: The bridge is the target of this interface, and an independently
  written testbench must drive it. Any mismatch (for example a stimulus that keeps
  `mem_valid` high across two requests, or one that expects `mem_ready` combinationally
  in the request cycle) shows up as a bridge bug with no spec text to arbitrate it.
- **options**:
  1. Add a native-protocol paragraph to `system.md` §1 (normative handshake rules) and
     to `contract.json` `protocols.native.semantics`. Cost: one spec edit; makes the
     interface independently testable.
  2. Normatively reference upstream PicoRV32 `README`/`picorv32.v` memory-interface
     section as the definition of the native protocol. Cost: makes an external
     document part of the contract; DV must be allowed to read it.
  3. Leave silent. Cost: bridge/DV disagreement is decided by whoever runs first.
- **your_recommendation**: option 1 (contract-local semantics string, plus a
  one-paragraph SYS-02 addendum), because the fabric-facing side of the same
  transaction is already fully specified and this is the only unspecified interface
  the CPU partition owns.
- **what_you_implemented_meanwhile**: upstream PicoRV32 native semantics, the most
  conservative variant — request captured only in the idle state on
  `mem_valid & ~stop`; `mem_wstrb != 0` = write, `== 0` = read; `mem_ready` a
  registered single-cycle pulse with `mem_rdata` valid in that cycle; no requirement
  that `mem_valid` drop between requests (a back-to-back request is accepted the
  cycle after the pulse); no combinational path from `mem_valid` to `mem_ready`.

---

## ISSUE-cpu_bridge-02 — AXI-07 lists `cpu_bridge` as an owner module, SYS-12 gives the timer to the fabric

- **spec_ref**: `contract.json` `requirements` AXI-07: `"owner_modules": ["fabric",
  "cpu_bridge", "lite_bridge", "extmem"]`, same list as AXI-01..AXI-10.
  `system.md` SYS-12: "CPU bridge reports read/write response errors 1/2 with aligned
  issued address, fabric reports progress 3 or protocol 6 …".
  `axi.md` AXI-07: "A progress monitor shall track each source/channel and each live
  transaction obligation independently."
- **observation**: The machine contract's `owner_modules` field is identical for every
  AXI requirement, including AXI-10 (external memory model) which the bridge plainly
  does not implement, so it reads as a participation list rather than an implementation
  assignment. SYS-12 assigns reasons 3 and 6 exclusively to the fabric, which leaves
  the bridge with reasons 1 and 2 only and no timeout obligation.
- **why_it_blocks**: It does not block — but "owner_modules" is the machine-readable
  field an integrator would use to check that every requirement has an implementer,
  and it currently over-assigns.
- **options**:
  1. Split `owner_modules` into implementing vs. participating modules per requirement.
  2. Add `"implemented_by"` to AXI-07 naming `fabric` only, leaving `owner_modules` as
     the verification-scope list.
  3. Leave as is and rely on SYS-12 prose (prose wins for semantics).
- **your_recommendation**: option 2 — it is additive, does not touch requirement IDs,
  and makes the timeout owner machine-checkable.
- **what_you_implemented_meanwhile**: no timeout counter in `cpu_bridge`. The bridge
  emits reason 1 and 2 only. If an offered VALID or an accepted transaction never
  completes, the bridge waits forever and the fabric monitor produces reason 3.

---

## ISSUE-cpu_bridge-03 — one-cycle window where the bridge may still accept a native request after a *foreign* fatal event

- **spec_ref**: `system.md` SYS-12: "Producers stop offering new transactions on their
  own fatal detection edge; sys drives sticky `stop_new_transactions` to CPU
  bridge, NPU controller, NPU DMA, fabric at the fatal capture edge." … "Fabric
  drains/routs retained work but accepts no newly offered transaction after the stop
  boundary". SYS-07: "assert local CPU reset before any further native request is
  accepted".
- **observation**: For a fault the bridge detects itself (reason 1/2) the bridge stops
  on its own edge, so SYS-07 holds exactly. For a fault raised by another producer
  (trap 4, watchdog 5, progress 3, protocol 6) the sequence is: producer registers
  `fault_valid` at edge N, sys captures FATAL and asserts `stop_new_transactions` at
  edge N+1, the bridge observes it in cycle N+1. In cycle N the bridge can still accept
  a native request and offer AR/AW/W in cycle N+1 — i.e. at or after the fabric's stop
  boundary. The fabric is then required not to accept it, while AXI-03/SYS-12 forbid
  the bridge from retracting VALID, so that AR/AW stays asserted until coordinated
  reset. The spec appears to intend this (AXI-07: "live AXI state is retained until
  coordinated reset"), but never says so for a *newly offered* post-stop transaction,
  and it is indistinguishable at the fabric port from an initiator that ignored stop.
- **why_it_blocks**: It does not block the bridge, but sys, fabric and the DV
  stop/drain checks must agree on whether a VALID first offered after the stop boundary
  is legal-and-retained or a protocol violation (reason 6). Two blocks implementing
  opposite readings deadlock or fabricate a fatal.
- **options**:
  1. State in SYS-12 that a transaction accepted by a producer at or before the fatal
     capture edge may be offered afterwards and joins the retained set; the fabric
     never treats a post-stop offer as reason 6.
  2. Require `stop_new_transactions` to be combinational from `fault_valid` inside sys
     so the bridge sees it in the same cycle as the fault edge. Removes the window but
     puts a combinational path across four blocks.
  3. Require producers to also gate on their own observation of any peer fault. Not
     possible: the bridge has no visibility of peer fault events in `contract.json`.
- **your_recommendation**: option 1 — it matches the retained-drain philosophy already
  written for offered AW/W and needs no new wires.
- **what_you_implemented_meanwhile**: the bridge samples `i_stop_new_transactions` at
  the same edge at which it would capture a native request and refuses the request if
  stop is high at that edge; anything captured before that edge is offered and then
  held per AXI-03 until READY or coordinated reset.
