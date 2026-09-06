# fabric — spec issues raised during RTL implementation

Spec baseline: `docs/spec/llm-soc-v1/` 1.0-rc3 (system.md, axi.md, contract.json).
Each entry states what was implemented meanwhile; every provisional decision is
marked in `fabric.sv` with a `// ISSUE-fabric-NN: provisional` comment.

---

## ISSUE-fabric-01 — precedence between DECERR (mapping/permission) and SLVERR (unsupported attribute)

- **spec_ref**
  - `system.md` §2 SYS-04: "Unmapped or unauthorized access returns DECERR and
    has no memory/peripheral side effect. A burst must fit a single authorized
    region."
  - `axi.md` §2 AXI-05: "Rejected well-formed reads return zero data, DECERR for
    mapping/permission or SLVERR for unsupported attributes, for exactly LEN+1
    beats."
- **observation** Both rules can apply to the same request (for example an
  unmapped address issued with `ARSIZE=1`, or a 4 KiB-crossing burst that also
  leaves its region). The spec defines the two response codes but never their
  precedence, so two implementations can legally return different codes for the
  same stimulus.
- **why_it_blocks** The response code is directly observable and will be
  compared by independent DV; a fabric and a golden model that pick different
  precedences disagree on every overlapping-error stimulus.
- **options**
  1. Mapping/permission first (DECERR wins). Consequence: SYS-04's unconditional
     "returns DECERR" always holds; attribute errors are only visible on
     mapped+authorized addresses.
  2. Attributes first (SLVERR wins). Consequence: an unmapped access with an
     illegal size reports a target error instead of a decode error, weakening
     the firewall's decode signal.
  3. Add an explicit precedence sentence to AXI-05 covering the overlap.
- **your_recommendation** Option 1, stated explicitly in AXI-05.
- **what_you_implemented_meanwhile** Option 1: `aw_err`/`ar_err` evaluate
  `!mapped_and_authorized -> DECERR` before `attribute_bad -> SLVERR`.

---

## ISSUE-fabric-02 — AXI-07 obligation (e) is unreachable when AXI-03's backpressure option is taken

- **spec_ref**
  - `axi.md` §1 AXI-03: "The receiver must still tolerate W handshaking before
    AW using a one-beat holding register **or backpressure** without deadlock,
    and must not infer an address from W."
  - `axi.md` §2 AXI-07: "(e) early accepted W waiting for its AW, begun on the
    first early W handshake and cleared only by that AW. ... An early-W-with-no-AW
    timeout is still monitored as an illegal/incomplete input sequence".
- **observation** AXI-07 (e) is defined on an *accepted* early W. A receiver that
  legitimately chooses the backpressure option (as this fabric does, because it
  removes any possibility of mixing W data between sources) never accepts a W
  before its AW, so obligation (e) has no reachable state. The illegal sequence
  is still detected, but through obligation (a) on that source's W channel.
- **why_it_blocks** Non-blocking for behaviour (both paths give reason 3 with the
  same fault_addr rule), but a DV item written literally against (e) may expect a
  W handshake to occur before AW.
- **options**
  1. Confirm in AXI-07 that (e) applies only to implementations choosing the
     holding-register option, and that (a) covers the backpressure option.
  2. Mandate the one-beat holding register in AXI-03 so (e) is always reachable.
  3. Leave as is and let each implementation choose (current state).
- **your_recommendation** Option 1 — one sentence in AXI-07.
- **what_you_implemented_meanwhile** Backpressure: `WREADY` is asserted only to
  the source owning the retained AW. An early W with no AW times out through
  obligation (a) with reason 3 and `fault_addr` = the offered AW address if the
  initiator offered one, otherwise 0 (SYS-12).

---

## ISSUE-fabric-03 — response for an AXI ID that is not the port's fixed source ID

- **spec_ref**
  - `axi.md` §2 AXI-02: "CPU source ID shall be 0 and NPU source ID 1 at both
    ingress and target ports. IDs 2/3 are reserved; no dynamically programmable
    identity."
  - `axi.md` §2 AXI-05: "Source identity remains physical port identity,
    independently of PROT."
- **observation** The spec fixes the ID per port and reserves 2/3, but does not
  say what a target port does when an initiator presents a different ID (for
  example CPU port with `AWID=2`, or CPU port with `AWID=1`). It is neither a
  mapping error nor an obviously "well-formed" attribute, and it is not listed
  among the protocol violations that latch reason 6 either.
- **why_it_blocks** DV needs a defined observable: SLVERR, DECERR, fatal reason 6
  or "don't care". Permission is unaffected (physical identity is used
  regardless), so only the response code is in question.
- **options**
  1. Unsupported attribute -> SLVERR, response echoes the accepted ID.
     Consequence: illegal IDs are visible and harmless.
  2. Protocol violation -> fatal reason 6. Consequence: an ID typo kills the run.
  3. Ignore the ID field entirely and always answer with the port's fixed ID.
- **your_recommendation** Option 1.
- **what_you_implemented_meanwhile** Option 1: `AWID/ARID != {1'b0, port}` is part
  of the unsupported-attribute term (SLVERR), permission always uses the physical
  port, and the error response echoes the accepted ID.

---

## ISSUE-fabric-04 — no source/channel attribution for a target response with no live transaction

- **spec_ref**
  - `system.md` §4 SYS-12: "Within fabric multiple same-reason candidates select
    source ID0 before 1, then channel order AW,W,B,AR,R."
  - `axi.md` §2 AXI-07: "(a) every offered VALID waiting for its corresponding
    READY".
- **observation** A target that asserts `BVALID`/`RVALID` while the fabric has no
  live write/read is an offered VALID with no corresponding initiator, so it has
  no source to attribute the timeout to under SYS-12's tie-break rule.
- **why_it_blocks** Without a rule the event either has to be dropped (a stuck
  spurious response would never produce fatal) or attributed arbitrarily.
- **options**
  1. Attribute to source ID 0 with `fault_addr=0` and reason 3 (report it).
  2. Treat a response with no outstanding transaction as protocol violation
     reason 6 immediately, without waiting for the timeout.
  3. Exclude ownerless target VALIDs from the monitor.
- **your_recommendation** Option 2 is the most informative, but it needs a spec
  sentence; option 1 is the conservative reading of AXI-07 (a).
- **what_you_implemented_meanwhile** Option 1: `wr_own_oh`/`rd_own_oh` default to
  source 0 when no transaction is live, so such a timeout is reported as reason 3
  with `fault_addr=0` rather than dropped.

---

## ISSUE-fabric-05 — "stop on the fatal detection edge" vs "a handshake on the threshold edge wins"

- **spec_ref**
  - `system.md` §4 SYS-12: "Producers stop offering new transactions on their own
    fatal detection edge ... Fabric drains/routs retained work but accepts no
    newly offered transaction after the stop boundary".
  - `axi.md` §2 AXI-07: "A matching handshake on the threshold edge wins and
    clears/restarts its counter".
- **observation** Taken together at the same edge these two rules make the
  arbiter's READY depend on the timeout decision, while the timeout decision
  depends on whether that same READY produces a handshake — a combinational
  cycle (Verilator UNOPTFLAT confirms it is not just a modelling artefact). One
  of the two must be evaluated with the pre-edge state.
- **why_it_blocks** It decides whether an AW/AR presented on the very edge a
  progress timeout is latched is accepted (and drained as retained work) or
  refused.
- **options**
  1. Timeout is registered; blocking starts on the next edge. At most one
     transaction is accepted on the detection edge and it becomes retained work
     that drains normally. Keeps AXI-07's "handshake on the threshold edge wins"
     exactly.
  2. Block combinationally on the timeout. Requires excluding this fabric's own
     AW/AR READY from the (a) obligations' progress terms, which weakens AXI-07.
  3. Spec adds one sentence choosing between them.
- **your_recommendation** Option 1, stated in SYS-12 as "no transaction is
  accepted after the edge on which fatal is captured".
- **what_you_implemented_meanwhile** Option 1: `block_new =
  i_stop_new_transactions | fault_valid_q | proto_hit` (protocol violations do
  not create the cycle, so they do block on their own detection edge).
