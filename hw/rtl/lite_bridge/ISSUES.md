# lite_bridge — spec issues raised during RTL implementation

Spec baseline: `docs/spec/llm-soc-v1/` 1.0-rc4 (axi.md AXI-09, system.md SYS-08,
contract.json C07..C11) — filed against 1.0-rc3 and ruled by
`CHANGE_ORDER_rc4.md`. Both issues are now closed with the provisional
implementation confirmed; `lite_bridge.sv` has no logic change, only its
`// ISSUE-lite_bridge-NN` comments rewritten from `provisional` to the ruling
they now cite. rc4 lists lite_bridge under "No change".

Status summary (rc4):

| Issue | Disposition | RTL change |
|---|---|---|
| ISSUE-lite_bridge-01 | spec-gap, provisional confirmed (+ R4-04 precedence) | none |
| ISSUE-lite_bridge-02 | spec-clear, provisional confirmed | none |

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
- **rc4_ruling** `CHANGE_ORDER_rc4.md` ISSUE-lite_bridge-01: **spec-gap**, option
  1 adopted, provisional confirmed, "RTL: lite_bridge none". `axi.md` AXI-09 now
  reads "A transaction the bridge rejects without issuing a Lite request returns
  SLVERR when its shape is unsupported (LEN>0, SIZE!=2, WSTRB!=0xf on writes,
  misaligned address) and DECERR only when the address lies outside the four Lite
  windows; the rejected transfer still consumes exactly LEN+1 W beats or produces
  exactly LEN+1 zero-data error beats (AXI-05) (rc4)". The rc4 amendment R4-04
  adds "AXI-05's precedence applies at the bridge as well: an address outside the
  four windows returns DECERR even when the shape is also unsupported (rc4,
  R4-04)".
- **rc4_status** Closed, no code change. R4-04 rejection order verified against
  `lite_bridge.sv`:
  - `aw_err_c = !aw_dec[2] ? DECERR : aw_shape_bad ? SLVERR : OKAY` and
    `ar_err_c = !ar_dec[2] ? DECERR : ar_shape_bad ? SLVERR : OKAY` — the window
    decode is evaluated before the shape term, so an out-of-window address whose
    LEN/SIZE/BURST/alignment is also unsupported returns DECERR;
  - the one late rejection, `WSTRB != 0xf` (and the ISSUE-lite_bridge-02 `!wb_last`
    term), is reached only from `WS_WAITW`, which is entered only when
    `aw_err_c == OKAY`; an out-of-window AW goes straight to `WS_DRAIN` with
    DECERR already latched in `wr_resp`, so a bad strobe can never displace it;
  - the LEN+1 beat obligation is unaffected: `WS_DRAIN` drains `aw_len+1` W beats
    before `WS_ERRB`, and `RS_ERR` emits `ar_len+1` zero-data beats.

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
- **rc4_ruling** `CHANGE_ORDER_rc4.md` ISSUE-lite_bridge-02: **spec-clear**, no
  spec text changed. AXI-03 "Protocol violations such as incorrect WLAST are
  illegal initiator behavior ... protocol monitor latches fatal": behind a
  conforming fabric the bridge never sees WLAST=0 on a LEN=0 write, so its local
  SLVERR is unobservable and permitted. Provisional confirmed; DV checks WLAST
  violations at the fabric (reason 6), not as a lite_bridge response.
- **rc4_status** Closed, no code change.
