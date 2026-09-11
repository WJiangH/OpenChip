# CoralNPU external-memory experiment contract

## 1. Identity, status and interpretation

Behavioral version **0.4**, profile **CN-EXTMEM-01**. Repository edition 1;
publication candidate, owned by the chief architect. This edition preserves
the v0.4 behavioral requirements and supplies stable repository references.
Upstream: `google-coral/coralnpu` commit
`561c59d33fea8a02e7f1062956ec77740e0eb955`, tree
`9dbf21aa935571f43e79a2fe15df28275f7d6636`.

Purpose: real compiled software fetching external instructions and reading and
writing external data on the unchanged core. [Workload and equations][workload]
and [ADR 0004][adr] are part of this version. Sources S01–S19 below and their
SHA-256/line ranges are bound in [sources.json][sources]. `U` labels source-backed
upstream behavior to be checked, not a vendor warranty or proven execution;
`E` labels a selected experiment environment/software obligation; `A` labels
acceptance evidence. Every numbered CNEM requirement has one owning subject.

**CNEM-01 (E, flow)** shall bind the actual generated top, parameter header,
source tree, tools/flags, simulator, ELF, linker map, input image, contract version
and hashes in its execution receipt; disagreement with §2 blocks that profile.

This contract selects no production memory technology, clock frequency, model,
quantization scheme, security architecture or PPA target. Repository import,
contract review and execution acceptance are separate decisions. Each execution
claim binds its own candidate and version; §7 does not imply general exception
or reset coverage.

## 2. Exact core and port profile

**CNEM-02 (E, flow)** shall use `RvvCoreMiniHighmemAxi`, generator target
`//hdl/chisel/src/coralnpu:rvv_core_mini_highmem_axi_cc_library_emit_verilog`,
RV32, VLEN128, fetch/LSU/AXI data128, AXI address32/ID6, ITCM=DTCM=1024 KiB,
RVV/Float/Zfbfmin/vectorBF16 enabled, FetchL0/VME/verification/debug-trace disabled,
and AXI instruction fetch enabled, with no changes to pinned upstream hardware
or generator sources. The experiment software is separately authored and may
adapt the pinned kernel under CNEM-06; its source diff/hash is recorded separately
from the immutable hardware tree. [S01–S04]

Generated Chisel names are used: `io_aclk`, `io_aresetn`, `io_boot_addr[31:0]`,
`io_irq`, `io_timer_irq`, `io_software_irq`, `io_te`; outputs `io_halted`,
`io_fault`, `io_wfi`. All status/interrupt/test signals are one bit.
AXI prefixes are `io_axi_master` (core manager) and `io_axi_slave` (core
subordinate). Channel suffixes are `_read_addr` (AR), `_read_data` (R),
`_write_addr` (AW), `_write_data` (W), `_write_resp` (B), each `_valid`, `_ready`,
and `_bits_<field>`. AR/AW fields: addr32, id6, len8, size3, burst2, lock1,
cache4, prot3, qos4, region4. W: data128, strb16, last1; no WID. R: data128,
id6, resp2, last1. B: id6, resp2. No USER fields. [S04,S05]

**CNEM-03 (E, harness)** shall wire all these fields with their declared widths
and directions, preserving IDs end to end (AR/AW/W flow manager to subordinate,
R/B in reverse, READY opposite VALID), without truncating ID1. [S04,S05]

**CNEM-04 (E, harness)** shall tie `irq`, `timer_irq`, `software_irq`, `te` and
`io_dm_req_valid` low, DM request address32/data32/op2 to zero (NOP), and
`io_dm_rsp_ready` high throughout each run; DM outputs are observed but unused.
The optional trace `debug` interface is absent in this profile. [S04,S17]

## 3. Address space, data and program placement

All intervals below include both endpoints. Local subordinate addresses are
identity mapped; there is no host base subtraction or translation. External
addresses refer to the separate manager-side memory responder, not a subordinate
pass-through. Endianness is little endian; byte lane j denotes data[8*j+7:8*j].

| Address range | Ownership and allowed purpose |
|---|---|
| 0x00000000–0x000fffff | Upstream ITCM; no positive-run executable or operand placement |
| 0x00100000–0x001fffff | Upstream DTCM; only stack at 0x001fc000–0x001fffff is used |
| 0x00200000–0x00200fff | Host CSR window; only offsets §4 are legal for this profile |
| 0x20000000–0x200fffff | 1 MiB experiment external memory aperture |
| 0x20000000–0x2000ffff | All ELF executable code, startup, trap handler and read-only constants |
| 0x20010000–0x2001003f | Case 0 A (64 bytes) |
| 0x20011000–0x20011fff | Case 0 B (4096 bytes) |
| 0x20012ff0–0x20012fff | Case 0 preceding guard (16 bytes) |
| 0x20013000–0x200130ff | Case 0 C (256 bytes) |
| 0x20013100–0x2001310f | Case 0 following guard (16 bytes) |
| 0x20014000–0x20014004 | Case 1 A (5 bytes) |
| 0x20015000–0x200150a4 | Case 1 B (165 bytes) |
| 0x20015ff0–0x20015fff | Case 1 preceding guard (16 bytes) |
| 0x20016000–0x20016083 | Case 1 C (132 bytes) |
| 0x20016084–0x20016093 | Case 1 following guard (16 bytes) |
| 0x20018000–0x2001803f | Descriptor: salt at +0, run_id at +4 (32-bit); rest zero |
| 0x20018100–0x2001813f | Completion/trap record, §6 |
| 0x20018200–0x2001821f | Access-size probe, §5 |
| 0x20020000–0x2002ffff | Additional ELF data/BSS and startup metadata if required |
| 0x200ff000–0x200ff00f | Dedicated fault-injection line, excluded from positive code/data |

All other external bytes start at zero, except C buffers, guards, record and
probe initialized below. The four guard intervals contain exactly 64 bytes
total; each starts at 0xa5 and is compared byte-for-byte after termination.
The case 1 following guard starts immediately after its last INT32 output,
including the unused tail lanes of that 16-byte line. Mapping outside the aperture has no valid backing memory.
The aperture has no modeled execute/read/write protection; the table expresses
legal experiment placement and stimulus, not an MPU.

**CNEM-05 (E, software)** shall link its entry and every executable section,
including startup/trap code and called GEMV kernel, in the executable window;
place operands/results/descriptor/record at the fixed addresses above; place all
other static data/BSS in the designated metadata window; and use DTCM only for
the 16 KiB stack (initial SP=0x00200000, growing downward). The ELF exposes a
32-bit, four-byte-aligned `_ret` symbol in the metadata window, separate from
the record and guards. Its kernel entry and ELF entry occupy distinct 16-byte
fetch lines. [S01,S04]

**CNEM-06 (E, software)** shall compute both GEMVs and unsigned signatures using
the exact [workload equations][workload], consuming the host salt/inputs after
release without TCM operand shadows, DMA, debugger access, semihosting or
host-computed results; register operands and ordinary stack spills are allowed.
The selected software deliverable is a separately authored, tail-bounded RVV
GEMV kernel exported as `rvv_gemv_int8`, adapting the pinned source where needed
while preserving notices and the exact mathematical result. It must write only
the logical C extents for both N values; padding C or relaxing guards to
accommodate full-vector tail stores is not permitted. The ELF contains and calls
that compiled kernel; independent software review checks its source/disassembly
and records every change from the pinned software asset, since fetch traffic
alone is not retirement. This contract does not require unchanged upstream
software and does not authorize hardware modifications.

**CNEM-07 (E, loader)** shall parse ELF32 PT_LOAD segments, validate physical and
virtual addresses against §3 (equal in this profile), reject overlaps/reserved
windows, load file bytes and zero p_memsz minus p_filesz before release, then
write formula inputs and descriptor for salt 0 or 17, fill C/probe and all four guard intervals with 0xa5 and
zero the record; no expected output bytes are supplied to the DUT.

Direct initialization of the separate external memory model is an explicit
simulation-host privilege. It does not traverse either core AXI port and proves
no production loading path. TCM memory backdoors, register deposits and forcing
internal pipeline state are excluded from positive execution.

**CNEM-08 (E, loader)** shall finish and log all initialization before RESET_CONTROL
is cleared, then disable all direct host writes to external memory until run
termination/reset; subsequent memory changes can originate only from accepted
manager AW/W, except the explicitly selected §7 read-error response substitution.

## 4. Host CSR, reset and boot

Register width is 32 bits; transactions use single-beat INCR, SIZE=2, LEN=0,
LOCK/CACHE/QOS/REGION=0, PROT=0, host ID=0, one total outstanding request. WDATA
uses address-selected lane: offset0 in bits31:0, offset4 in bits63:32; WSTRB is
0x000f or 0x00f0 respectively. Reading offset8 extracts bits95:64. [S05,S08,S09]

| Offset / absolute | Access | Reset / behavior |
|---|---|---|
| +0 / 0x00200000 RESET_CONTROL | RW | 3; bit0 active-high core reset, bit1 clock gate; host writes only 3,1,0 |
| +4 / 0x00200004 PC_START | RW | initially0; captures boot_addr on first internal clock after global reset; then host-programmable |
| +8 / 0x00200008 STATUS | RO | initially0; registered {fault,halted} bits1:0, upper bits zero |

CSR byte strobes are not a general byte-write guarantee: CoreCSR write logic
selects fixed 32-bit lanes and does not apply WSTRB. Only full aligned words above
are legal. Unknown offsets, partial writes and running PC/control rewrites are
excluded, not newly specified error semantics. [S08]

**CNEM-09 (E, host)** shall hold aresetn=0 for at least 10 aclk rising edges,
release it on a falling edge, wait 10 rising edges before CSR traffic, and hold
boot_addr equal to the ELF entry from before assertion until PC programming
completes. `aclk` runs continuously at a nominal 10 ns simulation period.
Upstream uses asynchronous assertion with internally synchronized release,
not a synchronous active-low reset assumption. [S04,S10]

**CNEM-10 (E, host)** shall wait for each request's OKAY response, read
RESET_CONTROL=3 and PC_START=boot_addr, program PC_START=ELF entry and read it
back, finish §3 loading, write RESET_CONTROL=1, wait 10 aclk edges while reset
remains asserted, then write RESET_CONTROL=0; that write's B handshake defines
release cycle 0. No host accesses to TCM or CSR occur during execution. [S08,S11]

**CNEM-11 (E, harness)** shall sample public outputs and manager traffic every
aclk rising edge beginning before release; top-level fault at any time in a
positive run fails it, and halted alone never establishes success.

## 5. Legal external transaction and memory behavior

This is a restricted single-beat AXI experiment, not AXI compliance closure.
Transfers occur only when VALID and READY are both 1 at a rising aclk edge.
A producer holds VALID and its entire payload stable until that handshake.

**CNEM-12 (U, manager)** shall emit AR ID1 for aligned16 instruction reads,
AR/AW ID0 for data, LEN=0, BURST=INCR(1), PROT=2, LOCK/CACHE/QOS/REGION=0,
AW/W only for data with WLAST=1, and SIZE=4 for fetch or SIZE in {0,1,2,4}
for data (1,2,4,16 bytes); addresses are aligned to 2^SIZE. [S05–S07,S12]

**CNEM-13 (E, responder)** shall supply one matching-ID, RLAST=1 response for
each accepted AR and one BID0 response after both corresponding AW and W are
accepted, never before the cycle following the last necessary request handshake.
It accepts AW and W independently in either order and pairs them in issue order.
No unsolicited/duplicate response or invalid ID is legal stimulus. [S04–S07]

**CNEM-14 (E, responder)** shall preserve order within each read ID and the
write stream, while allowing ID0 and ID1 read responses in either cross-ID
order; it shall provision capacity for one outstanding instruction read, one
data transaction, and independently arriving AW/W, without dropping traffic.
This profile expects at most one outstanding data operation and one instruction
read; accepted-response handshakes retire the corresponding external outstanding
entry. A bound violation is recorded as a contract/source divergence. [S06,S07]

**CNEM-15 (E, responder)** shall return for each legal successful read the
current bytes beginning at ARADDR for 2^ARSIZE bytes in their address-selected
128-bit lanes, with other lanes zero; on successful writes update only lanes
with WSTRB=1 at address (AWADDR & ~15)+lane, preserving every unstroked byte.
Write strobes outside [AWADDR, AWADDR+2^AWSIZE) are illegal manager behavior;
zero strobes leave memory unchanged. [S05,S12]

**CNEM-16 (E, responder)** shall commit a successful write after both AW/W
handshakes and before asserting BVALID, and let subsequent reads observe that
commit; the environment provides no speculative host writes, cache coherence,
write combining or memory-mapped side effects. Code remains immutable after load.

**CNEM-17 (E, software)** shall perform separate volatile byte/halfword/word
stores to probe offsets +1/+6/+12 with values 0x5a/0x1234/0x89abcdef, load them
back at the same widths and confirm equality before success; all other probe
bytes remain 0xa5. The manager trace verifies legal sizes/strobes and memory
bytes. Naturally aligned accesses and unit-stride RVV array operations are the
legal software subset; AMO/exclusive, bursts, self-modifying code, unaligned
scalar accesses, wraparound and MMIO are excluded from this experiment.

**CNEM-18 (E, responder)** shall run positive execution in two schedules:
P0 always-ready request channels with responses available 1 cycle after eligible
request; P1 deterministic independent AR/AW/W READY stalls of 0–7 cycles and
R/B eligibility delays of 1–15 cycles, recording the seed and actual schedule.
Once asserted, R/B VALID/payload remain stable until consumed; no channel is
held off indefinitely. Cross-ID reordering is allowed, not required to occur
if requests never overlap. AXI producer stability applies equally to the DUT.

**CNEM-19 (A, DV)** shall fail a read without its matching R handshake by
AR-handshake cycle +256, a write without its matching B handshake by
max(AW-handshake cycle, W-handshake cycle)+256, an unmatched AW or W half whose
counterpart has not handshaken by first-half-handshake cycle +64, any positive
run without terminal success within 1,000,000 aclk cycles of release, or any
protocol/data mismatch;
each deadline permits a handshake on the deadline edge and fails after
sampling that edge without it. Watchdogs count external aclk rising edges,
are per request/pair, and are canceled for the coordinated-abort epoch in
CNEM-26. The unmatched-half check is a DUT/environment progress obligation
under P0/P1, separate from the responder B-latency check. These are experiment
watchdogs under §5 assumptions, not promised silicon latency/throughput. P1 must record at least one stalled AR and AW or W, and one
delayed R and B; otherwise that schedule is NOT_EXERCISED and needs adjustment
within its fixed bounds rather than a PASS.

## 6. Completion, fault and return record

The external record is 16 little-endian uint32 words, initially zero. Positive
completion requires observed successful manager writes to exactly the following
mandatory byte set: offsets +0–+27 and +44–+47 (32 distinct bytes). Offsets
+28–+43 and +48–+63 (32 bytes) may retain their initialized zero or be explicitly
stored as zero. All 64 bytes are compared at termination. Additional repeated
stores within the record are allowed; mandatory coverage counts unique bytes,
not the number of transactions. The magic at +0–+3 is still committed last.

For isolated negative completion, the mandatory record byte set is +0–+15
and +28–+47 (36 distinct bytes); +16–+27 and +48–+63 (28 bytes) may retain zero
or receive zero stores. All 64 bytes are compared against CNEM-21 values.
No initialized byte by itself counts as an observed manager write.

| Offset | Value at normal completion |
|---|---|
| +0 | magic 0x434e454d, written last |
| +4 | version 1 |
| +8 | run_id copied from descriptor |
| +12 | result_code 0 success; nonzero software failure |
| +16, +20 | signatures for cases 0,1 |
| +24 | completed_cases=2 |
| +28 | trap_count=0 |
| +32,+36,+40 | mcause,mepc,mtval all0 |
| +44 | architectural return value=0 |
| +48–+60 | zero reserved |

**CNEM-20 (E, software)** shall install an external direct-mode mtvec handler
before kernel/probe work, commit results/record fields before the final magic
store, then terminate by upstream clean `mpause` encoding 0x08000073 with
main return0 captured in `_ret` by the upstream startup path (or an explicitly
reviewed equivalent return sequence); it must not use EBREAK as normal success.
The startup first writes `_ret`=0x0badd00d before calling main, then writes the
actual main return there. The final record return field equals that return.
`a0` at mpause is not the oracle: the upstream success path overwrites it with
retirement-counter data after preserving `_ret`. [S13–S16]

**CNEM-21 (E, software)** shall on a memory trap write result_code=1,
trap_count=1, the observed mcause/mepc/mtval and return field1, store `_ret`=1, retain
run_id/version, leave completed_cases=0 and signatures=0 in the isolated negative
program, write the same magic last and execute mpause without resuming the
faulting instruction. In each isolated negative program, startup first writes
`_ret`=0x0badd00d before entering main or issuing the designated faulting
operation; the handler later writes `_ret`=1. This makes the negative startup
obligation explicit rather than inheriting positive acceptance from CNEM-22.
Handler/startup/stack/record never share the fault line.

**CNEM-22 (A, DV)** shall accept positive termination only after manager-observed
record/result writes and all their B handshakes, halted=1, fault=0, wfi=0,
correct record/run_id, an observed manager store of `_ret`=0 after its
0x0badd00d startup store, final `_ret` matching record return0, and all 97
output elements/probe bytes and 64 guard bytes match;
status and memory remain observed for 32 more clocks with no data writes.
Instruction prefetch reads during that observation may complete normally.

**CNEM-31 (A, DV)** shall accept terminal evidence for each of the seven
isolated negative profiles in CNEM-23/25 only when all of the following hold:

- Successful ID0 manager writes cover all four bytes of `_ret` with
  0x0badd00d, followed by successful ID0 writes covering all four bytes with 1.
  All B handshakes for the sentinel stores precede the first accepted AW or W
  half of the handler return stores. The exact slot is bound by CNEM-29;
  initialized memory or the record return field alone cannot supply either
  observation. Final `_ret` is 1 and equals record offset +44.
- Successful manager writes cover the 36 mandatory negative record bytes above,
  with all corresponding B handshakes complete. All 64 record bytes equal the
  isolated negative values in CNEM-21, including the current run_id, version1,
  signatures0, completed_cases0 and reserved0. The final magic ordering in
  CNEM-21 still applies. The trap fields meet the particular CNEM-24/25 case.
- At terminal edge T, halted=1, fault=0 and wfi=0, the record and `_ret` have
  those final values, and no accepted data transaction remains outstanding:
  no ID0 read awaiting R, no AW-only/W-only half, and no paired write awaiting B.
  A last required handshake on T counts before testing this condition.
- T is the first sampled rising edge satisfying all preceding conditions and
  is no later than release cycle 1,000,000 inclusive; cycle0 is the
  RESET_CONTROL=0 B handshake in CNEM-10. Missing terminal evidence after
  sampling edge 1,000,000 fails the deadline. DV then observes exactly the 32
  additional rising edges T+1 through T+32 inclusive. At every such edge
  halted=1, fault=0 and wfi=0; the entire external memory aperture remains
  byte-identical to its state at T; no manager AW or W handshake occurs and no
  responder write commit occurs. `_ret` and the full record are thus stable.
  Instruction prefetch requests/responses may proceed under §5 normally.
  Any outstanding instruction read remains subject to the normal watchdogs;
  instruction-read drain is not an additional terminal prerequisite.

The 32-edge window is additional to the terminal deadline: T=1,000,000 is
legal and finishes observation at cycle 1,000,032. Any violation fails that
profile; a transient qualifying T cannot be replaced by a later T to erase a
window failure. This is a bounded observation of clean handler termination,
not proof of indefinite quiescence or instruction retirement. CNEM-22 remains
positive-only: its 97-output, input/kernel/probe and guard coverage requirements
are not imported into the isolated negative profile. Existing initialization,
legal-address/protocol, trap and error-response requirements remain in force.
CNEM-31 does not apply to an aborted reset epoch; the new positive epoch in
CNEM-27 continues to use CNEM-22.

A single checksum, halted, elapsed time, upstream test exit or C buffer preload
cannot replace these checks. Upstream `fault` is sticky for a halting usage
fault such as EBREAK; ordinary access traps route to mtvec and need not assert
that pin. Default CRT exception handling uses EBREAK, so the negative program
requires its own handler. [S13–S16]

## 7. Small negative and recovery profiles

These are bounded falsifiable criteria, **EXPLORATORY until that candidate is
run and reviewed**. Source inspection alone does not validate timing or precise
trap delivery. Report them separately from positive external-execution
acceptance; importing source does not transfer a prior execution result.

**CNEM-23 (E, DV)** shall run isolated instruction-fetch, scalar aligned32 load
and scalar aligned32 store error programs, each for SLVERR(2) and DECERR(3),
after installing mtvec and before GEMV; the single targeted operation uses
0x200ff000 and its first corresponding response is replaced with the selected
error. All other responses are OKAY(0). Error reads return zero lanes; error
writes do not mutate memory. EXOKAY(1), malformed/missing responses and multiple
simultaneous faults are outside this profile. [S06,S07]

**CNEM-24 (A, DV)** shall classify each such test PASS only if the program
reaches the CNEM-31 terminal edge within its 1,000,000-cycle bound and
passes its subsequent 32-edge observation, with mcause respectively
1/5/7, mepc equal to the designated fault instruction address (jump target
0x200ff000 for fetch), and mtval respectively0/0x200ff000/0x200ff000;
otherwise record the trace and open a spec-versus-implementation divergence.
Top fault is recorded and expected0 with the custom handler; fault1 or default
handler EBREAK cannot satisfy the intended trap-observation claim. [S13–S15]

**CNEM-25 (E, responder)** shall answer manager requests outside the 1 MiB
aperture with DECERR, no memory mutation and zero read data; a directed aligned
load from 0x21000000 uses CNEM-24's load criterion with mtval=0x21000000.
No host subordinate unmapped-address behavior is accepted by this profile.

**CNEM-26 (E, reset harness)** shall support global reset as coordinated abort:
stop and purge both external responder and host pending requests/responses at
assertion, hold their VALID low, discard unfinished AW-only/W-only writes,
retain any already committed write only as diagnostic state, and reinitialize
all external memory/record/inputs with a new run_id before repeating §4.
TCM contents are unspecified after reset; no retention/rollback guarantee is
inferred. Software-only core reset while transactions are pending is excluded.

**CNEM-27 (A, DV)** shall exercise coordinated abort once after an accepted AR
with R withheld and once with only AW or W accepted, then cold-reload and rerun
positive salt17; PASS requires no old response leaking into the new epoch,
new run_id, correct outputs and §6 success within the same bounds. No requirement
is placed on aborted software completion or on memory content before reload.

## 8. Acceptance evidence and scope limits

**CNEM-28 (A, DV)** shall retain cycle-stamped public AXI handshake traces
(fields including address, ID, size, strobe, response and data) and an independent
byte scoreboard for all four positive runs (two salts × P0/P1), proving:
external ID1 AR/R handshakes transfer the four bytes at the ELF entry and
the four bytes at the selected GEMV kernel function entry on two distinct
16-byte lines (coverage denominator: these two designated lines per run);
external ID0 read responses cover all 4,330 valid A/B bytes; matching successful
ID0 AW/W/B transfers cover all 388 C bytes, the 32 mandatory positive record
bytes defined in §6, and exactly the seven mandatory probe bytes at offsets
+1, +6–+7 and +12–+15 of 0x20018200. The other 25 probe bytes retain 0xa5,
and no write strobe may target those 25 bytes; all 32 probe bytes are compared
at termination. The record permits retained-zero bytes as specified in §6.
Neither host nor TCM preloading supplied
results after release. Bus reads beyond logical array ends inside their padded
16-byte line may occur, but writes outside C/record/probe/ELF metadata windows
fail; all 64 guard bytes at the exact four §3 intervals remain 0xa5.
The required kernel symbol is the concrete called function
`rvv_gemv_int8`, ELF STT_FUNC with nonzero st_size wholly inside the executable
window; the reviewer records [st_value,st_value+st_size). Zero-size/missing/
overlapping ambiguous function extents require corrected build metadata before
this check. The trace must transfer its entry bytes, not every symbol byte or
every potentially unreachable instruction. Fetch evidence proves instruction
bytes crossed the boundary; it is not an instruction-retirement trace.

**CNEM-29 (A, software reviewer)** shall bind ELF symbols, load segments, map,
disassembly and source to §3/§6, independently confirm no TCM operand shadow or
precomputed answers, and locate entry, kernel, handler and error instruction
addresses plus the exact `_ret` symbol address/size for DV; a binary build
without execution is NOT_RUN for acceptance. For error programs `_ret`=1 is
the handler completion code, not a claim that main returned normally. The
negative terminal check includes its manager-observed store and equality with
the record return field.

**CNEM-30 (A, integrator)** shall report separate outcomes for positive external
execution, error profiles and coordinated reset, retaining failures/timeouts/
NOT_EXERCISED, before accepting any claim. This contract does not establish full
AXI/ISA compliance, vector corner-case closure, upstream suite pass, ≥90%
coverage, DMA/DDR/PHY, full-model inference, performance/PPA, FPGA or tapeout.

## 9. Repository dependencies and change control

| Artifact | Role and integration dependency |
|---|---|
| This contract and workload | Normative behavior, arithmetic and fixed placement |
| `hw/ip/coralnpu/` | Planned source pin, acquisition and native generation entry; supplied by the IP flow work item |
| `sw/coralnpu_external_memory/` | Planned separately authored fixture, linker/startup and kernel adaptation; supplied by software migration |
| `hw/dv/coralnpu_external_memory/` | Planned independent host/responder/checkers and bounded profiles; supplied by DV migration |

These implementation paths are dependencies, not assertions that this contract
commit contains working executables. The source index describes cited sources,
not an exhaustive build dependency or license closure. The IP flow manifest
must separately identify the selected dependency closure, retained notices,
upstream patches and any local build configuration. Architecture has not
approved an upstream hardware patch or a Wishbone adapter.

Publication changes paths and explanatory status only. CNEM-01 through CNEM-31,
the register/memory tables, arithmetic and thresholds retain v0.4 semantics.
Historical positive results remain bound to their original v0.3 candidates;
negative/reset results remain bound to their original v0.4 candidates. None
becomes a result for this repository checkout without candidate/dependency
review and applicable reproduction. This document contains no new run verdict.

Behavioral changes require a revision and impact review of the contract,
workload, software, DV and flow. After v1, issue a change order naming one
issue for each affected role. Missing generated identity, program placement,
independent checks or run evidence blocks the corresponding execution claim.
Full-model, boot/security, memory technology, PDK and physical targets remain
separate platform decisions, not unanswered choices in this experiment.

## 10. Source evidence index

All upstream links below pin the exact commit; line numbers and byte hashes are
in [sources.json][sources]. The source index records immutable member hashes; source acquisition must
preserve the distinct SRAM.scala and Sram.scala members.

| ID | Pinned source / relevant contract evidence |
|---|---|
| S01 | Parameters.scala: highmem ranges and defaults |
| S02 | flags.bzl: RVV profile flags |
| S03 | BUILD: highmem generator target |
| S04 | CoreAxi.scala: ports, reset, routing and ID arbitration |
| S05 | bus/Axi.scala: widths, single-beat defaults |
| S06 | DBus2Axi.scala: data request serialization and error detection |
| S07 | IBus2Axi.scala: aligned ID1 fetch, one pending read, faults |
| S08 | CoreAxiCSR.scala: control/PC/status offsets and lane semantics |
| S09 | AxiSlave.scala: subordinate ID/response and independent AW/W queues |
| S10 | RstSync.sv: async assertion, reset and gated-clock release |
| S11 | core_mini_axi_interface.py: upstream loading and host sequence |
| S12 | scalar/Lsu.scala: selected V3 and size/alignment formation |
| S13 | scalar/FaultManager.scala: access mcause/mepc/mtval |
| S14 | scalar/Bru.scala: software traps, MPAUSE, EBREAK fault |
| S15 | scalar/Csr.scala: reset and sticky status |
| S16 | toolchain/crt/coralnpu_start.S: default trap, _ret, clean halt |
| S17 | scalar/Debug.scala: unused DM port widths/operations |
| S18 | soc/CoralNPUChiselSubsystem.scala: alternative interface/adapters |
| S19 | soc/SoCChiselConfig.scala: alternative core/peripherals/SRAM |

Documentation/source conflicts: upstream `doc/integration_guide.md` describes
manager ID always0, active-low irqn and synchronous reset; S04/S10 contradict
those claims for this pin. Old overview SIMD256/cache/64-vector-register prose
is superseded here by S01/S02 (VLEN128, 32 vector registers, FetchL0 disabled).
README Bazel7.4.1 differs from pinned `.bazelversion`8.6.0. No general source or
vendor documentation has been rewritten to hide these conflicts. [sources.json][sources]

[workload]: ../../workloads/coralnpu_external_memory/README.md
[adr]: ../adr/0004-coralnpu-integration-boundary.md
[sources]: coralnpu_external_memory.sources.json
