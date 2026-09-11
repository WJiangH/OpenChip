# CoralNPU autonomous small-model SoC

## 1. Target and status

Version 0.1 — **LOGICAL_TARGET_BASELINE; detailed execution and physical freeze OPEN**.
This specification defines the complete intended chip. It does not report an
implemented SoC, numerical acceptance or physical feasibility. The purpose is
open hardware that autonomously runs a complete small pretrained language model
and can progress through fabrication and silicon validation.

The first-silicon acceptance anchor is the complete FP32 **stories260K** model
pinned in [the workload profile](../../workloads/coralnpu_llm/profile.json): five
layers, width 64, FFN 172, query/KV heads 8/4, head width 8, vocabulary 512 and 260,032
unique trained parameters. Its pretrained context is 512; the supported runtime
capacity is 40, with at most 32 input tokens including specials and eight generated
tokens. This limits request length without removing trained layers or weights.
It is a tiny trained language model, without a practical dialogue-quality claim.

[ADR0006](../adr/0006-autonomous-small-model-soc.md) explains the selection.
The [CoreAXI experiment](coralnpu_external_memory.md) and
[complete-model experiment](coralnpu_llm.md) retain their existing configurations
and acceptance scope. Their host loading, highmem addresses and behavioral
memory are not this chip's boot or physical memory implementation.

## 2. Physical boundary and connections

**TSOC-01 (integration)** shall implement the following target blocks. Named
capacities are architectural budgets; macro, code and liveness fit require §7.

| On chip | Responsibility |
|---|---|
| One `RvvCoreMiniAxi`, RV32, RVV VLEN128, Float enabled | Scalar control, tokenization, complete model execution and detokenization |
| Native 8 KiB ITCM and 32 KiB DTCM | Hot code, stack and live workspace |
| 16 KiB immutable boot ROM | Initialization, image validation and recovery |
| 64 KiB working SRAM | All five layers' KV plus bounded input/output/run state |
| Native AXI manager decoder and MMIO bridge | Route instruction/data accesses to ROM, SRAM, flash and peripherals; preserve IDs and return bounded errors |
| Serial-flash controller, read buffers and serial I/O pads | Real SPI initialization, quad reads, XIP and ROM-controlled programming |
| UART, GPIO, timer, interrupt pending/mask block, watchdog | Input/output, time, progress and fault handling |
| Clock/reset logic and autonomous boot sequencer | Core clock/reset and separate subordinate-CSR startup control |
| JTAG test access, scan control and SRAM MBIST | Logic and memory test paths |
| Signal, reference-clock, reset and power pads | Qualified electrical/package boundary |

The board shall provide **4 MiB SPI NOR** holding firmware, the entire model and
tokenizer; reference clock, reset supervision and power; UART and test connectors.
No external working DRAM, DDR controller/PHY or second CPU is selected. Serial
controller timing and real I/O pads remain physical implementation obligations.
JTAG here denotes test/scan access, not an already integrated RISC-V debug module.
UART ROM recovery also provides functional debug. The prototype assumes trusted
provisioning and physical access; secure boot is not specified.

**TSOC-02 (integration)** shall connect core manager AXI to the system fabric,
then ROM/SRAM/flash/MMIO; the flash controller connects through serial pads to
NOR. The core accesses its native TCMs directly. UART connects to the terminal.
A separate on-chip boot sequencer owns the core **subordinate CSR port** during
startup; ordinary manager accesses are not assumed to configure that port.
Timer events route to `timer_irq`, software events to `software_irq`, and enabled
peripheral events to `irq`. Core faults/watchdog route to latched recovery cause
and reset control. Test access reaches scan and every writable memory's test path.

Use one functional reference-clock domain with qualified core clock gating and
test override. Synchronize external inputs/reset release and qualify test-clock
crossings. An external supervisor may supply power-on reset; this does not assume
an on-chip analog POR or PLL. A same-clock watchdog cannot detect loss of its own
reference clock; board supervision/external reset covers that failure.

## 3. Autonomous boot and recovery

**TSOC-03 (boot integration)** shall start execution from on-chip ROM without
host loading or CSR writes. Hold `boot_addr=0x20000000` through reset/startup;
observe native reset synchronization; read RESET_CONTROL=3; program and read back
PC_START; write RESET_CONTROL=1; wait at least ten core-clock edges; then write 0.
Each subordinate transaction awaits successful completion. The small target's
CSR base is `0x00030000`: RESET_CONTROL+0, PC_START+4, STATUS+8. Bind exact lanes,
strobes and handshakes before executable freeze. Initial manager instruction
fetches shall reach ROM independently of NOR contents. Native behavior is
source-linked in [CoreAXI §4](coralnpu_external_memory.md#4-host-csr-reset-and-boot);
its highmem absolute addresses and simulation clock do not apply here.

**TSOC-04 (boot software)** shall initialize stack/mutable state, UART and
watchdog; initialize flash in conservative single-bit SPI mode and then the
selected device's quad-read mode. ROM shall validate the versioned image
directory, lengths, bounds, entry addresses and integrity checks for complete
firmware/model/tokenizer before jumping to XIP firmware. Use CRC32 for accidental
corruption detection, not authentication. Provisioning/delivery checks shall bind
the expected trained-model SHA256 from the public profile. Exact image fields,
checksum byte coverage and provisioning transformations require §7. All ROM and
recovery dependencies must fit the ROM budget.

**TSOC-05 (integration and software)** shall preserve a reset cause outside the
core reset domain and enter ROM recovery on missing/bad flash image, fabric
error, core fault or watchdog expiry. Invalid external code shall never execute.
Recovery UART shall work without usable flash. After a failed autonomous boot
or run, remain in recovery rather than endlessly retrying. ROM may accept bounded
checksummed programming commands and shall verify readback before restart;
XIP is forbidden during erase/program. Fabric requests shall have finite
error/timeout handling. Reset during generation invalidates partial output and
requires fresh run identity/KV. Detailed register/error/timeout semantics remain
execution-freeze dependencies, not permission to guess them.

## 4. Complete computation and observable output

**TSOC-06 (software)** shall run both stored acceptance prompts automatically after
cold boot, without a connected terminal or computational host. Each fixture must
emit at least five tokens, demonstrating at least four actual feedback decode
evaluations after prefill; EOS ends normally. Retain every trained layer/head and
vocabulary entry and use the full graph in [CLLM-03](coralnpu_llm.md#2-artifact-and-graph-identity).
The core shall tokenize input, evaluate every prompt position, maintain all-layer
KV, form all 512 logits, select the lowest-ID greedy maximum and feed its own
selected token back. No host-computed activation, logit or token decision qualifies.
The target also shall accept UART UTF-8 text of at most 256 bytes, reject invalid
encoding or input exceeding 32 tokens including specials, and stop at EOS or the
eight-new-token cap. Reject over-capacity requests; never silently truncate them.
On-chip tokenization/detokenization shall match the pinned tokenizer, including
BOS/EOS and whitespace. Exact fixtures, tokenizer implementation/notices and target
arithmetic remain subject to independent qualification.

**TSOC-07 (software and independent DV)** shall expose decoded output via UART
115200 baud, 8N1 and completion/fault via GPIO. Diagnostic mode shall stream all 512
FP32 logits for every evaluated position, plus run/position identity and progress;
retain only a bounded frame/vector on chip. The independent observer shall retain
and compare every frame, exact generated token, decoded byte and termination.
Separate teacher-forced localization from real free-running feedback. NaN/Inf,
missing/mismatched records or token divergence reject acceptance. Existing host
reference, compiler flags or traffic observations do not qualify the target's
linked arithmetic. Numerical tolerances/FMA/underflow and math semantics require
an architecture-owned freeze; do not weaken them to fit a library.

**TSOC-08 (software and integration)** shall pause the producer on transmit
backpressure without overwriting evidence. Normal output needs no terminal
acknowledgement. Input overflow aborts the command with an error; an abandoned
diagnostic transfer is an aborted run, never success. Full-logit streaming is a
new target output contract, not a change to the older experiment's retained result
map. Additional stage-vector capture requires an explicitly reviewed budget.

## 5. Address space and storage budget

Intervals are half-open. Native small-map values come from pinned upstream
[BUILD 730–741](https://github.com/google-coral/coralnpu/blob/561c59d33fea8a02e7f1062956ec77740e0eb955/hdl/chisel/src/coralnpu/BUILD#L730-L741)
and [Parameters.scala 42–57](https://github.com/google-coral/coralnpu/blob/561c59d33fea8a02e7f1062956ec77740e0eb955/hdl/chisel/src/coralnpu/Parameters.scala#L42-L57).
The selected upstream revision is `561c59d33fea8a02e7f1062956ec77740e0eb955`.
The generated small core requires qualification; highmem acceptance does not transfer.

| Interval | Capacity | Target allocation |
|---|---:|---|
| `0x00000000–0x00002000` | 8 KiB | Native ITCM, optional hot code |
| `0x00010000–0x00018000` | 32 KiB | Native DTCM: 16 KiB stack, 5,984-byte operator workspace, 10,400 bytes for remaining BSS/tokenizer/guards |
| `0x00030000–0x00031000` | 4 KiB window | Native subordinate CSR, not extra RAM |
| `0x20000000–0x20004000` | 16 KiB | Immutable ROM |
| `0x21000000–0x21010000` | 64 KiB | Working SRAM |
| `0x22000000–0x22010000` | 64 KiB window | MMIO decode, not extra RAM |
| `0x30000000–0x30400000` | 4 MiB | Physical NOR XIP/data |

**TSOC-09 (software and memory integration)** shall respect these budgets and
freeze exact object bounds/guards, layout, overflow checks and peak liveness.
Working SRAM offsets allocate `0x0000–0xc800` to 51,200-byte KV,
`0xc800–0xd000` to 2,048-byte guards/alignment, and three 4 KiB regions at
`0xd000`, `0xe000`, `0xf000` to run state, output and input respectively.
KV is `2 × 5 × 40 × 32 × 4 = 51,200` bytes. The 5,984-byte serial operator workspace
already includes one 2,048-byte logit vector. No hidden heap or duplicate whole
model is budgeted. Remaining space is not proof that tokenizer/libc/stack fits.

Named writable arrays total 104 KiB = 106,496 bytes; 16 KiB ROM makes 120 KiB = 122,880 bytes
of named storage. Core register files, controller buffers and implementation
overhead are additional. Compared with 2 MiB highmem TCMs, this is a 94.921875%
reduction in named writable byte capacity, **not a physical area estimate**.

NOR aggregate budgets are 1,056,540 bytes for the whole model, 512 KiB firmware,
16 KiB tokenizer and 64 KiB image/recovery metadata: 1,662,748 bytes total, leaving
2,531,556 bytes in 4 MiB before detailed erase-block/alignment/update allocation.
Preserve the full 28-byte header, 1,040,128-byte trained tensors and 16,384-byte stored
RoPE tables; read them in place. Both pinned tokenizer files total 13,872 bytes.
The target representation and redistribution notices need independent review.

## 6. Operating design budgets and analytical cost

These are declared **design targets**, not measured timing or operating guarantees:

| Quantity | Initial target |
|---|---:|
| External reference clock | 25 MHz |
| Serial clock | ≤12.5 MHz |
| Boot to fixture start | ≤30 s |
| Each capped normal generation | ≤600 s |
| Interval without useful progress | ≤30 s |
| Serial input/diagnostic queue stall | ≤10 s |

**TSOC-10 (integration and software)** shall use prescaled timekeeping, avoiding
32-bit raw 25 MHz-counter overflow across 600 s. Watchdog refresh shall accompany
validated progress, not a spin loop; boot may refresh per verified block. UART
draining is bounded by its own transfer timeout. Demonstrate these limits at the
approved operating point before executable freeze or request a reviewed revision.
A timeout is failure; a clock change requires operating-point review.

The [reproducible analytical worksheet](../../explore/coralnpu_llm/README.md)
counts 259,328 linear MACs and 1,037,312 streamed weight bytes per evaluated position;
attention adds at most 25,600 MACs at capacity 40. Its conservative 80-position bound
for two runs is 22,794,240 MACs and 82,984,960 linear-weight bytes. Quad 12.5 MHz has a
raw ceiling of 6.25 MB/s; those weight bytes alone require at least 13.28 s under that
streaming algorithm. Single-bit mode is four times slower at the same clock.
Instructions, norms/RoPE, command/address/dummy cycles, arbitration, computation
and output add cost. This is a conditional bandwidth lower bound, not runtime or
tokens/s evidence. Read buffering and hot ITCM code need measured qualification.
UART alone takes at least 0.178 s per 2,048-byte logit payload at 115200 baud, 8N1,
before framing/progress. Streaming permits full evidence within the RAM budget.

## 7. Detailed freeze, dependent work and final acceptance

Logical definition precedes implementation. Before executable freeze, owners shall
resolve the following; ambiguous behavior remains OPEN and shall not be guessed.

| Owner | Required next contract/evidence |
|---|---|
| Architect | Register/interrupt/error/image/frame ABI, exact fixtures, numeric semantics/limits and measured operating budgets |
| RTL/integration | Small-core identity; fabric, boot sequencer, ROM/SRAM/flash/peripherals/reset/test implementation against that contract |
| Software | On-chip tokenizer/detokenizer and licenses, ROM/XIP/runtime image, actual ELF/ISA/ABI/math, stack/workspace fit |
| Independent model/DV/formal | Full oracle, all-logit/token checks and checker negatives; malformed image/input, stalls/errors/reset/recovery and startup properties |
| Backend/memory/IO/test | Qualified SRAM/ROM/pad/clock/reset implementations, banking/ports/latency/masks, flash part/protocol/voltage, scan/MBIST, package/board/power plan |
| Maintainer and physical owners | Process/shuttle/budget decision, physical constraints and all applicable lifecycle release gates |

No SRAM macro suitability, PPA, process, package or spending commitment is inferred
from byte counts or available tools. Never silently map large arrays to flops or
reuse unrelated reference-design PPA. Follow the separate implementation,
physical, tapeout and post-silicon decisions in the
[silicon lifecycle](../SILICON_LIFECYCLE.md). Changes to this target require a
versioned spec/ADR and affected-role review; prior experiment records remain scoped.

**TSOC-11 (system acceptance)** shall demonstrate on actual silicon: cold power-on
with programmed physical NOR and no computational host; validated ROM boot; both
complete fixtures with at least four feedback decode evaluations each; exact
independent token/decoded-output and frozen all-logit acceptance; UART text input
processed on chip; bounded completion at the approved operating point; correct
bad-image, fault, reset and overflow recovery; and usable independent test/debug.
Complete the agreed manufacturing, physical signoff and board-bring-up evidence
chain. Host reference, behavioral-memory simulation, FPGA execution or a layout
job alone does not establish that final result.
