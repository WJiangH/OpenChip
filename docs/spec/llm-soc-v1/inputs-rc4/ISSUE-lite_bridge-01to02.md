# lite_bridge — spec issues raised during RTL implementation

Spec baseline: `docs/spec/llm-soc-v1/` 1.0-rc3 (axi.md AXI-09, system.md SYS-08,
contract.json C07..C11).

---

## ISSUE-lite_bridge-01 — response code for a transaction the bridge rejects without issuing a Lite request

- **spec_ref**
  - `axi.md` §3 AXI-09: "It accepts only full-word single-beat CPU transactions
    after firewall validation and rejects bursts without issuing Lite requests."
    (No response code is given for the rejection.)
  - `system.md` §3 SYS-08: "Other sizes, strobes, offsets or writes to RO
    registers return SLVERR, reads return zero on error and no state changes."
- **observation** AXI-09 says a burst is rejected but not with which `BRESP`/
  `RRESP`; SYS-08 gives SLVERR for sizes/strobes/offsets, and says nothing about
  `AWLEN>0`. Separately, the bridge decodes four 4 KiB windows: an address that
  hits no window cannot occur behind the fabric firewall, but the bridge must
  still answer something.
- **why_it_blocks** The response code is directly observable; a golden model must
  predict it exactly.
- **options**
  1. Burst / bad strobe / bad size / misaligned -> SLVERR (attribute class);
     address outside the four windows -> DECERR (decode class).
  2. All bridge rejections -> SLVERR, including an undecodable address.
  3. All bridge rejections -> DECERR.
- **your_recommendation** Option 1: it keeps the same DECERR = decode /
  SLVERR = attribute split the fabric uses, and matches SYS-08 for the shape
  errors it does enumerate.
- **what_you_implemented_meanwhile** Option 1. In both directions the rejected
  transaction still consumes exactly LEN+1 W beats (write) or produces exactly
  LEN+1 zero-data error beats (read) per AXI-05, and no Lite port is touched.

---

## ISSUE-lite_bridge-02 — a single-beat write whose W beat does not assert WLAST

- **spec_ref**
  - `axi.md` §1 AXI-03: "Exactly LEN+1 W beats and correct WLAST are required.
    ... Protocol violations such as incorrect WLAST are illegal initiator
    behavior ... protocol monitor latches fatal".
  - `axi.md` §3 AXI-09: the Lite bridge is not listed as a fatal producer, and
    contract.json gives it no `fault_event` connection.
- **observation** The fabric's protocol monitor already latches reason 6 for a
  WLAST mismatch, so the bridge cannot see one behind a correct fabric. The
  bridge nevertheless has to define a behaviour for the case, having no way to
  report a fault itself.
- **why_it_blocks** Not blocking; it only decides what an isolated
  module-level testbench sees when it drives a malformed single-beat write.
- **options**
  1. Reject as a shape error (SLVERR), issue no Lite request.
  2. Ignore WLAST entirely and perform the write.
- **your_recommendation** Option 1.
- **what_you_implemented_meanwhile** Option 1: `wb_last` must be 1 on the single
  beat of a `AWLEN=0` write, otherwise the write is rejected with SLVERR and no
  Lite request is issued.
