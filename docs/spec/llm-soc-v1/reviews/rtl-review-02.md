# Architecture review 02 — RTL/IP integration

Verdict: **REQUEST CHANGES** for release of the partitioned SIM-L1 implementation contract.
Reviewer: rtl-engineer, 2026-09-05. Scope is the eight-file `docs/spec/architecture-review-02/` snapshot plus previously pinned intake sources. No DV, testbench, golden or other-worktree implementation was read. Only this review file was added; previous intake artifacts remain unchanged. This is a contract review, not a gate execution or hardware validation.

## Findings requiring resolution

### R02-01 — P1: machine AXI-Lite protocol omits every VALID signal

Locations: `contract.json:245`–307; `axi.md:25`.

The machine `axi4_lite.signals` contains 14 signals but lacks AWVALID, WVALID, BVALID, ARVALID and RVALID. The prose names all five. Every C08–C11 peripheral connection uses this incomplete protocol. A module or wrapper generated from the machine contract cannot identify a request or response transfer; READY alone is insufficient.

Change: add the five width-1 signals with initiator ownership for AW/W/AR and target ownership for B/R. Keep machine/prose interface sets identical. Owner: architect; applies before independent peripheral RTL interfaces are frozen.

### R02-02 — P1: fabric cannot enforce the specified R-versus-X permissions

Locations: `system.md:38`–55; `axi.md:7`; `contract.json:309`–318, C01/C02 at 405–423.

SYS-04 requires the fabric to enforce a table in which only ROM/SRAM have X. The native core supplies `mem_instr`, but AXI-02 requires CPU PROT=0, there is no USER/other fetch sideband, and C02 is ordinary AXI4. Physical CPU source-port identity distinguishes CPU from NPU but does not distinguish instruction fetch from CPU data read.

Trigger: the CPU jumps to a readable model or expected-data address. Its fetch becomes indistinguishable from an allowed data AR; the fabric cannot produce the required execute denial. Instruction fetch to a peripheral likewise loses its classification before the CSR boundary.

Change: either enforce all instruction-region checks in the native bridge using `mem_instr` before issuing AR, and explicitly assign that portion of SYS-04 to the bridge; or preserve a hardware-derived instruction tag to the firewall (for example ARPROT[2] produced only by the fixed bridge) and revise AXI-02. It must not be software-programmable privilege. Mirror the choice in the machine contract. Owner: architect/CPU-interface partition.

### R02-03 — P1: native CPU subword semantics are assigned to the wrong boundary and cannot support instruction-size rejection as written

Locations: `system.md:55`, `system.md:65`, `system.md:75`; `axi.md:7`, `axi.md:25`; `contract.json:309`–318.

Pinned official `picorv32.v:382` outputs an already word-aligned address; lines 410–424 replicate store data/set byte strobes and select the returned read lane **inside the CPU**. Native protocol provides neither original read byte offset nor load size. `mem_addr` is registered from this aligned address at line575. The bridge must return the unshifted complete 32-bit RDATA, not perform a second lane selection.

Triggers:

- `LBU` from SRAM base+1: a bridge implementing the prose “reads obtain word then select lane” literally cannot recover the original offset, and a shifted response would be selected again inside PicoRV32.
- `LB` versus `LW` of a CSR, or `LB` at CSR+1: both produce the same aligned native read request. The bridge/CSR cannot reject the former for non-word size or original offset if SYS-08 intends instruction-level enforcement.
- An AXI error on a byte load: SYS FAULT_ADDR cannot record the original offending byte address from this native port; only its aligned bus word address is available.

Change: explicitly assign lane selection/sign extension to the CPU, pass native store payload/strobes unchanged, and define CSR full-word/alignment checks at the **bus transaction** boundary. Document that software must use word CSR loads and that hardware cannot distinguish CPU subword reads through this core interface. Define FAULT_ADDR as the emitted aligned AXI address (or add an explicitly reviewed extra core sideband if original effective address/instruction-size enforcement is a requirement). Owner: architect/CPU interface. No core behavior should be silently patched to satisfy an impossible external-port assumption.

### R02-04 — P1: NPU split-module command context/group packing is not closed

Locations: `npu.md:7`, `npu.md:11`, `npu.md:52`; `contract.json:335`–346, 369–380; C12/C13/C14/C15 at 502–536.

Only npu_ctl and npu_dma receive the dispatch descriptor. The only functional input to npu_local is C14 `local_bytes`: a fetched word, keep, kind, index, row, group_last and row_last. No K/G context reaches local, while local must generate group_first/group_last/group_index for the dot unit. The prose does not define C14 group_last/row_last, lane coordinate mapping, or whether a fetched word must be split/replayed when it spans several groups.

Trigger: identical K=4,N=1 and fetched X/W words with G=1,2,4 require respectively four, two and one group result. A producer emitting each fetched word once cannot express multiple terminal boundaries with one group_last. A producer splitting/replaying the word could support this, but the consumer has no normative contract saying it receives that representation. G=1/2 are explicitly legal and required, not optional extensions.

Change: choose one concrete partition contract: give local the immutable descriptor and let it split groups, or require DMA to emit group-contained local beats with exact keep/index/first/last semantics (including repeated aligned words and valid lane-to-k mapping). Define valid-byte and group marker meaning for activation versus weight traffic. This is implementable but currently permits incompatible producer/consumer implementations. A monolithic NPU can internalize the decision; the current document explicitly also permits independent module delivery, so that route needs closure. Owner: architect/NPU partition.

### R02-05 — P1: raw NPU IRQ status and masked IRQ wiring disagree

Locations: `system.md:84`; `npu.md:34`, `npu.md:39`; `contract.json:547`–568 and 1341–1362.

SYS IRQ.PENDING bits0/1 are specified as NPU.DONE/NPU.ERROR. C17/C18 instead carry `done_irq/error_irq`, which NPU-06 defines as DONE/ERROR gated by NPU.IRQ_ENABLE. There is no separate raw-status connection to the IRQ block.

Trigger: complete a valid NPU command with NPU.IRQ_ENABLE reset0. SYS prose expects PENDING[0]=1; the machine-wired IRQ input is 0. Polling PENDING and enabling the central interrupt controller produce different results depending on which document the author follows.

Change: define PENDING as the post-NPU-enable IRQ level, or supply raw DONE/ERROR to the IRQ block and specify exactly where both masks apply. Also clarify live RO reset readback: UART READY/TX_EMPTY=1 when reset completes, so live PENDING[2] is 1 while the machine register says reset0. Mark such fields as live derived state rather than contradictory stored reset values. Owner: architect/CSR/IRQ interface.

### R02-06 — P1: required fatal event/control paths are missing from the exact connection contract

Locations: `system.md:5`, `system.md:61`, `system.md:74`–75; `axi.md:9`, `axi.md:19`; `npu.md:41`; `contract.json:400`–753 (connections).

The connection list contains only one input to sys, C08 AXI-Lite. It contains no CPU trap→sys, CPU bridge fault/address→sys, fabric progress/protocol fault→sys, NPU watchdog→sys, or sys fatal/stop-issue→initiators links. CPU clock/reset CR00 exists, but common reset alone cannot stop new NPU issuance while preserving live AXI state: SYS-07 explicitly resets only CPU locally and retains bridge/fabric transactions. A shared hidden wire is not part of the advertised exact endpoint contract.

Trigger: CPU read SLVERR or NPU command watchdog. The modules detect a fault but have no specified event payload/retention handshake to latch the system cause/address and no specified fatal fanout to prohibit new DMA. A protocol violation also has no assigned FATAL reason in the current 1..5 reason list. Simultaneous CPU response error and watchdog have no defined cause/address priority, despite FAULT_ADDR being first-offender state.

Change: add explicit event and stop-issuance protocols/connections with sticky/pulse or valid/ready semantics, reason codes, first-fault capture and simultaneous-event priority. Clarify that already asserted but unaccepted AW/AR/W remains live and must keep VALID/payload; subsequent W beats belonging to an already-issued burst remain permitted while **new transaction** initiation stops. Assign protocol violations a reason. Mirror CPU local reset versus common coordinated reset in the machine clock/reset bindings. Owner: architect/system-control partition.

## Non-blocking observations and accepted choices

- Native core plus explicit failed-response reset is consistent with the pinned IP's lack of memory-error port. Do not substitute official `picorv32_axi` without changing that contract.
- SYS-10's external IRQ bits4..6, MASKED_IRQ=0xffffff8f, LATCHED_IRQ=0 and disabled timer are compatible with the actual custom IRQ ABI; internal illegal/misalignment sources remain masked and can reach core trap. No standard CSR/mret assumption is present. This exact configuration differs from the earlier generic intake probe and appropriately remains an implementation configuration to validate later, not a review blocker itself.
- Serialized single CPU request and NPU output B-before-DONE ordering give a coherent uncached load-after-completion path. FENCE.I exclusion and load-before-initial-jump boot strategy are compatible with the selected core.
- 32-bit IDs0/1 fixed at ingress and egress match a custom bounded fabric. The design no longer quietly instantiates a generic crossbar that appends source ID bits.
- Passive Caliptra mode, disconnected manager, real firmware service, application CPU running trusted ROM instead of being held in a boot dependency cycle, and S1's separate unreleased binding status are consistent with intake. No missing S1 frontend/firmware/OTP/entropy detail is counted as a new B1 blocker. Actual S1 needs a fetch/phase authority consistent with R02-02 and cannot use CPU-port identity alone as ROM privilege.
- NPU integer bound, group-tail allocation, output nonoverlap and expected-memory deny policy are implementable. The group accumulator bound includes -128 operands and stays within INT32.
- `traceability.md:48` ends at LLM-10 while `workload.md:34` and `contract.json:1977` contain LLM-11. Add the missing traceability row during document synchronization; this is a minor manifest/ownership discrepancy rather than a new datapath blocker.
- Missing draft dependencies/budget/downstream artifacts were explicitly excluded from defect counting. No finding merely says that implementation has not been compiled.

## Read-only check evidence

Mechanical inspection (Python JSON parse and connection/protocol enumeration, no testbench):

```text
Native protocol has no original read-size or effective-byte-offset field.
local config inputs: C14(local_bytes), CR13(clock_reset).
sys incoming connections: C08(axi4_lite) only.
fatal/fault/trap/watchdog named connections: none.
AXI-Lite signal list: AWREADY,AWADDR,AWPROT,ARREADY,ARADDR,ARPROT,
 WREADY,WDATA,WSTRB,BREADY,BRESP,RREADY,RDATA,RRESP.
```

Snapshot SHA256 identities:

```text
README.md        e0eebaec328ceee9c9abff0a087ef7dc84c02ab90979de21eff5927c809bee03
axi.md           3e7b9f0acfc5865c9a0c75c2b538fd6e458dcb7d7e81efe41cf15adf821b18a6
contract.json    72d6db8ca366e9774b339dcc41815094c4a53294aba2ac41895ee5e17f4fa73b
npu.md           b23f234e997acb17bc5e25997f816b2a934dfe4b39577122e49d341d6d520665
security.md      452e2437ea0e3229f24512cee48eb8254e920849fead22d799d0637fece7064f
system.md        e0ec267386a8ddb70a2c09b974c1eb9cf5944881331d4bf08e793c851e1180dd
traceability.md  c8cd12f9bfd586576916083ec5ef41a5a3fc7c53fae86785ee7606ba28cb2d2f
workload.md      1d86d5e9765fe5d4b9d421ba0a0fe92b7ffcc2b79c005fb469b5855da7304241
```

Official CPU source identity remains PicoRV32 `a473fc8fca393771d83b0ffcf0b14db3393339d8`, locally retained in `sources/picorv32/picorv32.v`; its source hash/URL are unchanged in the intake's `sourcehash.json`.

Friction:
- Machine interface inventory and prose disagree at the Lite handshake, native subword, IRQ and fatal-control boundaries.

Skill candidates:
- rtl-engineer/references/external-ip-intake.md — Review which metadata an imported native port actually exposes before assigning access control, CSR rejection or fault-address duties to a bridge.
