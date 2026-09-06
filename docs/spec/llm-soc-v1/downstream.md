# Dependency-ordered implementation deliverables

Version1.0-rc3. Owners work independently in role-scoped local worktrees. No commit/push/remote PR is requested. Each deliverable records the exact spec/hash/config and test result, preserves gates and reports unresolved failures. A check is not complete because an owner is assigned.

| Work item | Owner /deliverable | Dependencies /exit evidence |
|---|---|---|
| A-REVIEW |chief architect + independent verification/integration review| all RC docs/maps numeric bindings; defects ruled spec-bug and corrected with changed-file list before release |
| CPU-INTAKE |RTL CPU owner| pinned CPU+final params, error-aware bridge+fatal integration; custom IRQ/reset/byte lane requirements; strict lint resolution, no implicit exception behavior |
| FABRIC |RTL interconnect owner| AXI ICD; two-source separate read/write serialized routing, source identity firewall, full→Lite converter and independent timeout retention logic |
| MEMORY |RTL memory owner; DV owns external model| ROM/SRAM actual target implementations, explicit init policy, external AXI model with deterministic latency/stalls/errors; no DDR controller claim |
| NPU |RTL command/DMA/datapath owners| single grouped-dot command, arbitrary tail, buffered write bursts, integer results and completion/error/reset semantics; each module's DV author independent |
| SYS |RTL infrastructure owner| reset/fatal/counter/result/IRQ/UART CSR specification; no CPU progress dependency for fatal observation |
| SW-B1 |software owner| ROM/ELF/linker/custom IRQ driver; nonzero signed fixtures exact CPU comparison, polling and IRQ cases, boot CRC negatives; compiled size+stack budget |
| V-B1 |verification architect then independent DV| derive vplan, fixture golden, fabric/error/reset properties from spec; real ROM boot→NPU→CPU compare; at least two distinct fixture inputs |
| SW-L1 |software owner| published deployment blob/input/expected container; strict soft-float runtime,36 NPU calls/forward, full48forward path, standalone reference identity; no host arithmetic in DUT path |
| V-L1 |independent DV/model owners| quantized reference, every-group exact checks, specified checkpoints/tokens and rejection coverage; host full reference separated from CPU validation blobs |
| FLOW |orchestrator/flow owner| real build/sim entrypoints replacing placeholders; pinned firmware/artifacts loaded automatically; timeouts/progress/trace/chunk/hash receipts |
| ISA/FORMAL |independent DV/formal| RV32IM riscv-arch-test/RISCOF vs pinned Spike with applicable-test denominator, AXI safety/progress assumptions, arithmetic bounds, noninterference/reset properties |
| B1 EXIT |integrator| same-run immutable identities+reset/ROM/CPU AXI traces+NPU signed arithmetic+write response before done+CPU exact comparison+IRQ evidence; lint/sim/coverage/formal results separated |
| L1 EXIT |integrator| complete model shape/layer/path evidence, all48forwards,16 output IDs, numeric checkpoints, CPU/NPU cycle breakdown and true walltime; all fallback documented |
| SEC-S1 |security RTL/SW/verification owners| security.md supplement with full native IP ports+policy/ROM/fuses/entropy; real Caliptra services; signed/tampered/denied/recovery execution evidence |
| FPGA-F1 |platform/backend owner| select board/controller/clock/reset memories, synth/route/resources, real B1/L1 repeat; secure config repeats S1; measure bandwidth/power where available |
| PRODUCT-P1 |chief architect→model/backend/SW probes| full1.7B quality/trace/live tensors, vector/attention numeric supplement, calibrated architecture DSE then hardware operator task release |

No module author may write its testbench. The architecture requirement matrix expresses verification obligations only; verification architect authors the actual independent vplan/golden. Flow defects are reported to FLOW; role owners do not patch shared gates to obtain a green status. Simulation success does not imply synthesis/coverage/ISA/formal/timing/FPGA/DRC/LVS success. Physical acceptance requires its own manifest with process corners, macro/PHY identities and real gate output.

## Gate manifest shape

Per run: spec release+hash, source/IP/ROM/ELF/model/tokenizer/input/expected hashes, compiler/simulator versions and exact commands, reset/latency/fault seeds, parameter echo, true tests-run/pass/fail/skip counts, coverage numerator/denominator and exclusions, elapsed cycles+walltime, result code, trace location/hash, open bugs. Tool output summary must be pasted, not replaced by the word PASS. A stale output or empty lint file selection fails evidence validity even if process exit is0.
