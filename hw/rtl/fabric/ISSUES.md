# fabric — spec issues raised during RTL implementation

Spec baseline: `docs/spec/llm-soc-v1/` 1.0-rc4 (system.md, axi.md, contract.json)
— filed against 1.0-rc3 and ruled by `CHANGE_ORDER_rc4.md`. Every issue below is
now closed; each entry keeps its original text and adds an **rc4_ruling** block
stating the disposition and whether `fabric.sv` changed. The `// ISSUE-fabric-NN`
comments in `fabric.sv` were rewritten from `provisional` to the ruling they now
cite; only ISSUE-fabric-04 required a logic change.

Status summary (rc4):

| Issue | Disposition | RTL change |
|---|---|---|
| ISSUE-fabric-01 | spec-gap, provisional confirmed | none |
| ISSUE-fabric-02 | spec-clear, provisional confirmed | none |
| ISSUE-fabric-03 | spec-gap, provisional confirmed | none |
| ISSUE-fabric-04 | spec-gap, **provisional rejected** | ownerless target BVALID/RVALID -> immediate reason 6, fault_addr 0 |
| ISSUE-fabric-05 | spec-clear, provisional confirmed | none |

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
- **rc4_ruling** `CHANGE_ORDER_rc4.md` ISSUE-fabric-01: **spec-gap**, option 1
  adopted, provisional confirmed, "RTL: fabric none". `axi.md` AXI-05 now reads
  "a request that is unmapped or unauthorized returns DECERR even if its
  attributes are also unsupported; SLVERR for unsupported attributes is reported
  only for mapped, authorized addresses (rc4)".
- **rc4_status** Closed, no code change. Verified against `fabric.sv`: `aw_err`
  and `ar_err` still test `!aw_ok`/`!ar_ok` (region hit AND burst fits that one
  region AND physical-port permission) before `*_attr_bad`, so DECERR wins
  whenever both apply. One interpretation is recorded rather than changed: the
  burst footprint fed to `region_lookup` is computed from the legal 4-byte beat
  size, so a mapped start address whose 4-byte-derived burst leaves its region
  reports DECERR even if the offending attribute is `AWSIZE`/`ARSIZE` itself.
  This stays inside the ruling — SYS-04 makes a burst that does not fit one
  authorized region unauthorized, and DECERR is the unauthorized code.

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
- **rc4_ruling** `CHANGE_ORDER_rc4.md` ISSUE-fabric-02: **spec-clear**, no spec
  text changed. AXI-07 "(e) early *accepted* W waiting for its AW" plus AXI-03's
  "one-beat holding register **or** backpressure": under the backpressure option
  (e) is vacuous and (a) bounds the illegal early W. Provisional confirmed; the
  note lands in the traceability AXI-07 row, and DV tests condition (e) against
  the implementation's stated option — this fabric's is backpressure.
- **rc4_status** Closed, no code change. The chosen option is stated in the
  `fabric.sv` header ("Early-W policy (AXI-03)") for DV to read off.

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
- **rc4_ruling** `CHANGE_ORDER_rc4.md` ISSUE-fabric-03: **spec-gap**, option 1
  adopted, provisional confirmed, "RTL: fabric none". `axi.md` AXI-05 now reads
  "An AWID/ARID other than the port's fixed source ID (AXI-02) is an unsupported
  attribute: SLVERR, response echoing the presented ID, permission still decided
  by physical port identity (rc4)".
- **rc4_status** Closed, no code change. Verified against `fabric.sv`: the ID
  mismatch sits in `aw_attr_bad`/`ar_attr_bad` (SLVERR, and DECERR still wins if
  the address is also unmapped/unauthorized per ISSUE-fabric-01); `wr_id`/`rd_id`
  capture `s_awid[wr_gsrc]`/`s_arid[rd_gsrc]` — the *presented* ID — and drive
  `b_id_o`/`r_id_o`, so the error response echoes it; `region_lookup` is called
  with the physical port index `wr_gsrc`/`rd_gsrc`, never with the ID.

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
- **rc4_ruling** `CHANGE_ORDER_rc4.md` ISSUE-fabric-04: **spec-gap**, option 2
  adopted; "**Provisional (source0/reason3 after timeout) is wrong.**" `axi.md`
  AXI-07 now reads "A target asserting BVALID or RVALID on a channel with no live
  transaction routed to that target is a protocol violation: the fabric latches
  fatal reason 6 with fault_addr 0 on the first edge it samples such a VALID,
  without waiting for any timer (rc4)". R4-13 records the cost as accepted: a
  timer-attributed reason 3 would misname a protocol violation as a timeout.
- **rc4_status** Closed, **`fabric.sv` changed**:
  - new `wr_routed`/`rd_routed` (write channel routed to a target in
    `WS_AW`/`WS_DATA`/`WS_RESP`, read channel in `RS_AR`/`RS_DATA`), decoded to
    `wr_tgt_oh`/`rd_tgt_oh`;
  - `b_ownerless = m_bvalid & ~wr_tgt_oh`, `r_ownerless = m_rvalid & ~rd_tgt_oh`,
    `ownerless_resp = |b_ownerless | |r_ownerless`;
  - `ownerless_resp` joins `proto_hit` (reason 6) with `proto_addr` left at 0,
    and through `proto_hit` it also blocks new transactions on its own detection
    edge, consistent with ISSUE-fabric-05;
  - the SYS-12 tie-break is unchanged: `timeout_hit` (reason 3) is still tested
    before `proto_hit` (reason 6) in the fault register, so the lowest reason
    wins on a simultaneous edge.
  Scope decisions taken while implementing the ruling, offered for DV review:
  (i) "routed to that target" spans from the state in which the fabric first
  offers the request to that target through its response, so a response that is
  merely *early* on the target that does own the live transaction is not an
  ownerless VALID — that remains an AXI-03 ordering question; (ii) a
  firewall-rejected transaction (`WS_DRAIN`/`WS_ERRB`, `RS_ERR`) reaches no
  target, so any target response during it is ownerless; (iii) an ownerless
  response has no source, so among simultaneous reason-6 candidates it is ranked
  after `wlast_bad`/`rlast_bad`, which do carry a source and a known address —
  the reason is 6 either way and AXI-07 fixes the ownerless address at 0.
  The target-side (a) obligation counters on B/R are left in place; they can no
  longer be the first to fire for an ownerless VALID, so the source-0 default in
  `wr_own_oh`/`rd_own_oh` is now only a mux default.

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
- **rc4_ruling** `CHANGE_ORDER_rc4.md` ISSUE-fabric-05: **spec-clear**, no spec
  text changed. AXI-07 "A matching handshake on the threshold edge wins and
  clears/restarts its counter" and SYS-12's stop being sys's sticky output driven
  "at the fatal capture edge" together give option 1: the timeout is registered,
  blocking starts on the next edge, and the transaction accepted on the detection
  edge is retained work that drains normally. Provisional confirmed.
- **rc4_status** Closed, no code change. `block_new` is unchanged; the rc4
  ownerless-response term added for ISSUE-fabric-04 enters it through `proto_hit`,
  i.e. on the same combinational protocol-violation path that already blocked on
  its own detection edge, so the registered-timeout property is untouched.
