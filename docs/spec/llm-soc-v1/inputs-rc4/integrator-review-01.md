# integrator-review-01 — B1 RTL+SW deliveries vs SIM-L1 1.0-rc3

Reviewer: integrator (requested model Fable), read-only. Baseline `7fcb251866907fe2926c1846b1be1f1c8229b49c`. Spec bytes: `.local-designs/platform-lifecycle/docs/spec/llm-soc-v1/` (README, system.md, axi.md, npu.md, contract.json, dependencies.md, traceability.md, CHANGE_ORDER_rc3.md). Not read: any `hw/dv/`, `run002/verification/`. Nothing in any worktree was modified; all tool outputs below are my own runs (logs in the session scratchpad).

## (a) Verdicts

| Delivery | Verdict | Blocking / attached finding ids |
|---|---|---|
| rtl-cpu_bridge (`cpu`, `cpu_bridge`) | accept-for-DV | — |
| rtl-fabric (`fabric`, `lite_bridge`) | accept-for-DV | — |
| rtl-mem (`rom`, `sram`) | accept-with-findings | F-08 |
| rtl-sys (`sys`, `irq`, `uart`) | accept-with-findings | F-05, F-07, F-08 |
| rtl-npu_ctl (`npu_csr`, `npu_ctl`) | accept-with-findings | F-04, F-05, F-06 |
| rtl-npu_dma (`npu_dma`, `npu_local`) | request-changes | F-01 |
| rtl-npu_dot (`npu_dot`) | accept-with-findings | F-01 (counterpart; port change possible after ruling) |
| sw-b1 (`sw/`) | request-changes | F-02, F-03 |

## (b) Findings

| id | sev | delivery | file:line | claim vs evidence | fix owner |
|---|---|---|---|---|---|
| F-01 | major | rtl-npu_dma (+npu_dot, npu_local) | `npu_dma.sv:299` `o_group_result_ready = busy_q & ~err_any_c & (~st_valid_q \| wr_append_c)`; `npu_dma.sv:519-523` ERROR terminal on `rd_quiet_c & wr_quiet_c` only; `npu_dot.sv:173` `o_dot_operands_ready = !result_valid_q`, `npu_dot.sv:190-214` result register drained only by `i_group_result_ready`; `npu_local.sv:94,256-269` dispatch re-arms local but no path reaches npu_dot | Manifest claims NPU-06 "on first non-OKAY ... drain ... report code 5/6" and "CLEAR-and-reuse ... safe" (npu_dma commit d15ddc7, `npu_dma.sv:534-536`). Spec NPU-06: "Only after no offered/accepted transaction **or unconsumed result** remains shall it set ... ERROR=1"; "It is safe to CLEAR and reuse only after terminal error". Evidence: after a read/write error `o_group_result_ready` is held 0, so a completed group sitting in npu_dot (`result_valid_q=1`) is never consumed; ERROR is reported anyway (NPU-06 letter violated). On the next SUBMIT npu_dma re-arms (`busy_q=1`, `err_*_q=0`, `npu_dma.sv:537-571`) and immediately accepts the stale result, forming `res_addr_c` (`npu_dma.sv:285-287`) from the **new** `y_base_q/gcount_q` and the **old** row/group_index → silent write into (or past) the new command's Y allocation. Reachable whenever an error lands while the dot pipeline holds a result (normal case during W streaming). This is the ISSUE-npu_dot-01 / ISSUE-npu_local-03 gap, but the two authors' provisional choices conflict: npu_dot's recommendation was "npu_dma holds group_result.ready=1 while draining after an error"; npu_dma implemented the opposite (`~err_any_c`). Note for the ruling: ready=1-while-idle alone still leaves a one-cycle race (an operand accepted by npu_dot on the dispatch edge yields a result in the first busy cycle of the new command). Blocks NPU-08 B1 cases "bus read/write errors", "terminal reuse". | RTL author (npu_dma: drain path) + architect (ruling on ISSUE-npu_dot-01/npu_local-03; flush or idle signal) |
| F-02 | major | sw-b1 | `sw/rom/rom_start.S:39-46` (`li t0 ...; lw t0; li t1,2; bne; li t0,0x10000080; jr t0`); `sw/common/crt0.S:33-63` saves x5/x6 **after** the trampoline already overwrote them; objdump rom.elf `0x100..0x11c` confirms | Manifest: "0x100 IRQ trampoline forwarding to 0x10000080 after BOOT_STAGE=2" and SYS-10 compliance. SYS-10: software shall "preserve interrupted integer registers/stack". PicoRV32 README (hw/ip/picorv32/README.md:510-521): IRQ entry preserves all GPRs; `q2`/`q3` exist "as temporary storage when saving/restoring register values in the IRQ handler". Evidence: t0/t1 of the interrupted code are destroyed on every forwarded IRQ; the firmware save routine stores the clobbered values. Latent in this exact binary (objdump b1.elf: no x5/x6 use outside `picorv32_irq_common_entry`), but any compiler/flag/firmware change flips it, and the IRQ-driven B1 case relies on it. | SW author (stash t0/t1 in q2/q3 via `setq` in the ROM trampoline and restore via `getq` at 0x10000080 before the GPR save, or forward with a register-free sequence) |
| F-03 | major | sw-b1 (manifest) | commit `b29b092` body ("Gates: `make sw` clean under -Werror; ... --selftest all OK") | Packet `packets/sw_b1.md` item 5 required "paste the size table and the sha256 of rom.bin, b1.elf, b1_extmem.bin"; integrator SKILL step 0/4: claims without tool output → request-changes. The body contains no tool output, no size table, no hashes; the three hashes the task asked me to compare do not exist in the manifest. My clean rebuild (table (c)) reproduces byte-identical artifacts, so the build itself is honest; the traceability record is incomplete. | SW author (amend manifest with the required lines) |
| F-04 | minor | rtl-npu_ctl vs rtl-npu_dma | `npu_ctl.sv:66-70` "done/error are one-cycle, mutually-exclusive pulses"; `npu_dma.sv:321-326` "driven as sticky levels ... held until the next accepted dispatch" | Two authors document opposite semantics for `dma_terminal` (contract.json gives none). Composition happens to be correct: npu_dma clears `done_q/error_q` on the dispatch handshake edge (`npu_dma.sv:537-548`) and npu_ctl only enters `ST_WAIT_DONE` after that same handshake (`npu_ctl.sv:200-204`), so no stale level is sampled. Must be pinned by ISSUE-npu_dma-02 ruling; npu_ctl comment is false as written. | architect (ruling) + npu_ctl author (comment) |
| F-05 | minor | rtl-npu_ctl vs rtl-sys | `npu_csr.sv:356-357,374-375` SUBMIT/CLEAR with value != 1 → SLVERR; `sys.sv:224,258` RESULT_COMMIT with bit0=0 and reserved bits zero → OKAY, no effect | NPU-04 says "write1 only"; SYS-08 table says "write1 latches"; SYS-08 general: "reserved write bits must be zero or the write is rejected atomically". The two blocks give different BRESP for a WO write of 0. Each is defensible from its own row; the family-wide rule is not stated. | architect (one sentence on WO write-0 response) |
| F-06 | minor | rtl-npu_ctl | `npu_ctl.sv:191` (`cycle_ctr_q <= 1` at accept), `npu_ctl.sv:211-217` (increment on the edge that samples `i_dma_done`), `npu_csr.sv:460-471` (CSR latch one cycle later) | NPU-04 LAST_CYCLES "from submit acceptance to terminal edge inclusive". ISSUE-npu_ctl-02 pins the start edge; the far endpoint (ctl sampling edge vs CSR terminal edge, off by one) is not stated by author or spec. Bit-exact observable for DV. | architect |
| F-07 | minor | rtl-sys | `sys.sv:218,255` BOOT_STAGE accepts any 32-bit value | SYS-08 table: BOOT_STAGE "0..4 only". Not enforced; author acknowledged only inside ISSUE-uart-01 text, no ISSUE id of its own. Same class as ISSUE-uart-01 (value-range wording without a rejection sentence). | architect (rule for both) |
| F-08 | minor | rtl-mem, rtl-sys, sw-b1 (attribution) | `git log`: e82873b, 3d75a60 (mem), 4973c10, d1d8e56, 0285d19 (sys), b29b092 (sw) carry `Co-Authored-By: Claude Fable 5.1` while authored `*-Sonnet5-default`; the Opus-signed commits and npu_ctl (Sonnet) carry no trailer | AGENTS.md: "The model/effort in the signature is what the session actually ran on — no honorary upgrades." dispatch.json already records observed model as `unattested-harness-param`; the trailer is a second, contradictory model claim inside the same commit. Not a product defect; a traceability defect in the run ledger. | flow/orchestrator (attestation policy; do not rewrite history) |
| F-09 | minor | sw-b1 / flow | `git diff --name-only` for b29b092: `sw/rom/rom.hex`, `sw/b1/b1.hex`, `sw/b1_extmem*.json` committed; no `.bin` | Packet names `rom.bin`/`b1_extmem.bin` as the SW→ROM-RTL and SW→DV interface artifacts; root `.gitignore sw/**/*.bin` drops them from the delivered diff (already FLOW-003). Reproducible from source (table (c)); still, the delivered branch does not contain the interface bytes and `b1_extmem.json:bin_sha256` points at an uncommitted file. | flow (gitignore negation on baseline) |

Checked and found conforming (no finding): SYS-04 region table in `fabric.sv:309-336,387-431` — all 14 rows (base, size, CPU/NPU permission incl. X-vs-R by ARPROT[2] at `:619`) match system.md §2 / contract.json `address_regions`; AXI-07 in `fabric.sv:1009-1097` — 33 per-obligation counters, counter loads 0 on the creating edge (`ob_start`), `ob_timeout` at `cnt==65535 & active & ~prog` so fatal latches on the edge the count would reach 65536 and a same-edge handshake wins (`:1084-1095`), (e) absent because backpressure option is taken (`:21-31`); SYS-12 tie-break ID0-before-1 then AW,W,B,AR,R (`:1144-1158`) and known-or-zero `fault_addr` (`:1116-1129`); AXI-03 in `cpu_bridge.sv:165-170` (AW and W raised together, never waiting AWREADY) and `npu_dma.sv:460-471` (AW only after full burst buffered, AWVALID with first WVALID); SYS-07 in `cpu_bridge.sv:189-200,216-226` (non-OKAY → sticky reason 1/2 with issued address, no `mem_ready`, terminal `StFault`); SYS-12 wrapper in `cpu.sv:140-150` (reason 4, addr 0, common rst_n; core on `i_cpu_local_rst_n`); `cpu.sv:73-98` all 25 dependencies.md parameters match; NPU-04 register table/offsets/reset in `npu_csr.sv:78-96,264-286` match contract.json `csr_registers[block==npu_csr]`; NPU-05 SUBMIT/CLEAR gating and priority 1..4 validation with 64-bit endpoints (`npu_csr.sv:190-249,353-383`); NPU-01/02 arithmetic: `npu_dot.sv:100-151` exact INT16 products under keep mask, 18-bit beat sum, 32-bit wrap accumulator, group_first clear; `npu_local.sv:141-167` group start/end `min(K,(g+1)G)`, disjoint keep masks for G=1/2, `command_last` per §4 — hand-traced for (K,G) = (5,4),(5,8),(5,2),(1,1); NPU-02 Y address `npu_dma.sv:285-287`; sys FATAL/FAULT_ADDR/CYCLE/RESULT_COMMIT (`sys.sv:98-135,304-313`) match SYS-08 table; irq PENDING/ENABLE/ACTIVE and bits 4/5/6 (`irq.sv:68-71`); uart framing and READY/BUSY/DIVISOR rules (`uart.sv:104-142,192-197`); rom/sram AXI target behaviour incl. write-commit-before-B (`sram.sv:178-188`) and defensive SLVERR on ROM writes (`rom.sv:160-164`); lite_bridge AXI-09 (`lite_bridge.sv:240-280,353-361`); SYS-05/06 in `rom_main.c:42-126` (magic/ABI/length/load/entry, 64-bit bounds, copy, CRC over destination, BSS clear, BOOT_STAGE=2, jump only on success; failure codes 0xB001/2/3 + single RESULT_COMMIT then loop) and linker placement (`link_rom.ld:30`, `link_b1.ld:19-24,53-54`); NPU-08 driver sequence in `b1_main.c:147-190,197-272` (CLEAR → X/W/sentinel → barrier → shadows → SUBMIT → wait → DONE&&!ERROR&&tag → barrier → exact compare), IRQ masks keep bits 0..2 masked (`b1_main.c:220`, `b1_start.S:44-45`). Grep over all delivered `hw/rtl` files: no `initial`, `$readmemh`, `lint_off`, delays or testbench files; `hw/ip/` untouched.

Cross-module consistency (field sets / widths / polarity), all match contract.json: `dispatch` 9×32b + valid/ready (npu_csr:49-59 → npu_ctl:27-37; npu_ctl:40-63 → npu_dma:24-34, npu_local:21-31); `local_bytes` data32/keep4/kind2/index12/row12 (npu_dma:37-43 ↔ npu_local:34-40); `dot_operands` x32/w32/keep4/first/last/row12/gidx12/command_last (npu_local:44-53 ↔ npu_dot:35-44); `group_result` data32/row12/gidx12/last (npu_dot:48-53 ↔ npu_dma:46-51); `dma_terminal` done/error/error_code[2:0] (npu_dma:54-56 ↔ npu_ctl:71-73, semantics see F-04); `terminal` tag32/error_code3/cycles32 (npu_ctl:76-80 ↔ npu_csr:63-67); `fault_event` valid/reason[2:0]/addr[31:0] from cpu:46-48, cpu_bridge:80-82, fabric:276-278, npu_ctl:84-86 ↔ sys:41-55; `stop_new_transactions` sys:59 (single net) ↔ cpu_bridge:85, fabric:281, npu_ctl:91, npu_dma:59; `cpu_local_rst_n` sys:58 ↔ cpu:22; irq levels npu_csr:71-72, uart:42 ↔ irq:41-43; Lite 19-signal sets lite_bridge m0..m3 ↔ sys/npu_csr/irq/uart `s_axil_*`; full AXI 44-signal sets fabric m0..m3 ↔ rom/sram/lite_bridge `s_axi_*`, cpu_bridge `axi_*`/npu_dma `m_axi_*` ↔ fabric `s0/s1_axi_*`. Port *identifiers* differ by prefix only (e.g. `i_dma_done` vs `o_dma_terminal_done`, `o_dma_dispatch_k` vs `i_dispatch_k`) — top-level wiring work, already ISSUE-npu_dma-01/FLOW-002.

## (c) Reproduced gates (my runs)

Lint: `make lint MOD=<m>` in each worktree; Yosys: `yosys -l <log> -p 'read_verilog -sv <files>; hierarchy -check -top <m>; proc; opt; memory -nomap; check -assert; stat'` (`cpu` read with `hw/ip/picorv32/picorv32.v`; `rom` with `-Ihw/rtl/rom`).

| module | make lint (exit / tail) | `%Warning` lines | Yosys check | Yosys warnings |
|---|---|---|---|---|
| cpu | 0 / `lint: PASS (cpu)` | 0 | `Found and reported 0 problems.` | 0 |
| cpu_bridge | 0 / `lint: PASS (cpu_bridge)` | 0 | `Found and reported 0 problems.` | 0 |
| fabric | 0 / `lint: PASS (fabric)` | 0 | `Found and reported 0 problems.` | 0 |
| lite_bridge | 0 / `lint: PASS (lite_bridge)` | 0 | `Found and reported 0 problems.` | 0 |
| rom | 0 / `lint: PASS (rom)` | 0 | `Found and reported 0 problems.` | 0 |
| sram | 0 / `lint: PASS (sram)` | 0 | `Found and reported 0 problems.` | 0 |
| sys | 0 / `lint: PASS (sys)` | 0 | `Found and reported 0 problems.` | 0 |
| irq | 0 / `lint: PASS (irq)` | 0 | `Found and reported 0 problems.` | 0 |
| uart | 0 / `lint: PASS (uart)` | 0 | `Found and reported 0 problems.` | 0 |
| npu_csr | 0 / `lint: PASS (npu_csr)` | 0 | `Found and reported 0 problems.` | 0 |
| npu_ctl | 0 / `lint: PASS (npu_ctl)` | 0 | `Found and reported 0 problems.` | 0 |
| npu_dma | 0 / `lint: PASS (npu_dma)` | 0 | `Found and reported 0 problems.` | 0 |
| npu_local | 0 / `lint: PASS (npu_local)` | 0 | `Found and reported 0 problems.` | 0 |
| npu_dot | 0 / `lint: PASS (npu_dot)` | 0 | `Found and reported 0 problems.` | 0 |

All 14 lint/Yosys claims in the commit manifests reproduce. Cell/flop counts were not re-derived (not a gate).

sw-b1 (`make -C sw clean; make sw` from the worktree root): exit 0; every compile line carries `-march=rv32im -mabi=ilp32 ... -Os -Wall -Wextra -Werror -ffreestanding -nostdlib`; `riscv-none-elf-size b1.elf` → `text 2936 data 0 bss 16 dec 2952`; `b1.bin: 3060 bytes (<= 196608 / 0x30000)`. sha256 before rebuild == after rebuild:

```
6e4ca25250f93489c5832db705aafaa214a25e613a32a0a76e69871c8b158bb4  sw/rom/rom.bin
143ae83423b0c51b71fb1885281ca6973f96c778debbccb3410701f2b7c116b3  sw/b1/b1.elf
e94f62a911c7357a688e3cbf9a9af1c99786cca119b5fc98a95d45393a76f194  sw/b1_extmem.bin
```
`rom.bin`/`b1_extmem.bin` match the orchestrator's partial hashes in FLOW-002 (6e4ca252…, e94f62a9…); `b1_extmem.json:bin_sha256` == e94f62a9…. The commit body itself states no hashes (F-03).

Independent checks (my scripts, scratchpad): expected-Y blob at 0x80700000 recomputed from `fixtures.h` arrays with a from-scratch NPU-01/02 loop (group end `min(K,(g+1)G)`): both records match word-for-word (`0xa5a50001`: 9 words, `0xa5a50002`: 4 words), blob CRC ok; NPU-02 allocation intervals for both commands lie in scratch, `W_STRIDE >= round_up(K,4)`, Y disjoint from X/W. Boot header in `b1_extmem.bin`: `magic 4c4c4d31 abi 1 len 3060 load 10000000 entry 10000000 crc 3e2a467a bss 10000bf4/16 rsvd all 0`; CRC over payload == zlib CRC-32 (ISO-HDLC) ok; payload sha == `b1.bin`; `bss_start >= round_up4(load+len)`, `bss_end <= 0x10030000`; negative variants: bad_magic `magic b3b3b2ce`, bad_crc `crc c1d5b985`. Interface check rom.bin → `gen_rom.py` → `rom.sv` (copies in scratchpad): 16384 words emitted, word0 `32'h10040137` == first bytes of rom.bin (`37 01 04 10`), `verilator --lint-only -Wall` on the copy: PASS.

Boundary: `python3 audit_scope.py` → `AUDIT PASS violations=0` (8 delivered items; all authors match `<role>-agent-<Model>5-default <role@agents.openchip>`; diffs confined to allowlists; no `hw/ip/` edits; no `hw/dv/` files). Independently confirmed with `git diff --name-only <baseline>..HEAD` per worktree.

## (d) Issue triage (proposed dispositions for the chief-architect)

| id | disposition | blocks B1 DV closure? | note (spec text) |
|---|---|---|---|
| ISSUE-cpu_bridge-01 | spec-gap (needs change order) | yes (unit-level cpu_bridge DV cannot drive the native port from spec text) | SYS-02 names "PicoRV32 native interface" and dependencies.md pins the commit; `contract.json protocols.native` lists signals only. Cheapest ruling: normatively reference `hw/ip/picorv32/README.md` "Memory Interface" and permit DV to read it. |
| ISSUE-cpu_bridge-02 | traceability-metadata only | no | SYS-12 assigns reasons 3/6 to fabric; `owner_modules` is a participation list. |
| ISSUE-cpu_bridge-03 | spec-clear (author misread) | no | SYS-12: "Producers stop offering ... on their **own** fatal detection edge; sys drives sticky stop ... at the fatal capture edge" and "Fabric ... accepts no newly offered transaction after the stop boundary". A post-stop offer is legal, simply never accepted, retained until reset; nothing labels it reason 6. Both implementations already agree. |
| ISSUE-fabric-01 | spec-gap (needs change order) | yes (BRESP/RRESP directly compared by DV on overlapping-error stimuli) | SYS-04 "returns DECERR" vs AXI-05 "SLVERR for unsupported attributes"; provisional DECERR-first is the conservative reading. |
| ISSUE-fabric-02 | spec-clear | no | AXI-03 permits "backpressure"; (e) is defined on an *accepted* early W. DV must condition (e) tests on the holding-register option. |
| ISSUE-fabric-03 | spec-gap (needs change order) | no (DUT initiators never emit foreign IDs) | AXI-02 fixes IDs, gives no response code for violation. |
| ISSUE-fabric-04 | spec-gap (needs change order) | no (needs a misbehaving target) | SYS-12 tie-break has no ownerless case. |
| ISSUE-fabric-05 | spec-clear | no | AXI-07 "A matching handshake on the threshold edge wins" is explicit; stop is sys's registered output; provisional reading follows text. |
| ISSUE-lite_bridge-01 | spec-clear | no | SYS-08 "Other sizes, strobes, offsets ... return SLVERR"; AXI-05 SLVERR for unsupported attributes covers LEN>0; undecodable address is unreachable behind the fabric (DECERR consistent with SYS-04). |
| ISSUE-lite_bridge-02 | spec-clear | no | AXI-03: incorrect WLAST is an initiator protocol violation latched by the fabric monitor (reason 6); bridge-local behaviour is system-unobservable. |
| ISSUE-mem-01 | traceability-metadata only | no | Add rom/sram to `owner_modules` of AXI-01/02/03/06/08. |
| ISSUE-npu_csr-01 | spec-clear | no | NPU-04 SUBMIT: "validate and atomically snapshot descriptor"; NPU-05: malformed idle SUBMIT "returns OKAY at the CSR layer ... issues no DMA". CSR validates. DV of npu_ctl must not expect codes 1..4 there. |
| ISSUE-npu_ctl-01 | spec-clear | no | npu.md §4: "local derives all group boundaries from its descriptor"; the packet sentence was an orchestrator paraphrase (FLOW-002). |
| ISSUE-npu_ctl-02 | spec-gap (needs change order) | no (B1 PASS does not read LAST_CYCLES) | Define both endpoints of LAST_CYCLES (see F-06). |
| ISSUE-npu_dma-01 | rule-level (AGENTS.md / ICD port-identifier convention) | no | Top-level item reconciles; future ICDs should carry RTL port names. |
| ISSUE-npu_dma-02 | spec-gap (needs change order) | no for B1 PASS; yes for any DV assertion on `dma_terminal` | Level-held-until-next-dispatch (npu_dma) vs pulse (npu_ctl doc) — see F-04. |
| ISSUE-npu_dma-03 | traceability-metadata only | no | contract.json C16 (dot→dma) is decisive; reword `blocks[npu_local].purpose`. |
| ISSUE-npu_dma-04 | spec-gap (needs change order) | no | §4 "issues no memory request until both handshakes finish" is unimplementable in the partition without a wire; provisional reading (local back-pressures `local_bytes`) is not the literal one but is safe given `npu_local.o_dispatch_ready = 1`. |
| ISSUE-npu_dma-05 | spec-clear | no | SYS-12: fatal "makes the run fail; it does not ... promise recovery without full reset"; NPU-07 "requires coordinated reset". BUSY-until-reset with `o_fatal` as observable is consistent. |
| ISSUE-npu_dot-01 | spec-gap (needs change order) | **yes** (F-01: "bus read/write errors", "terminal reuse" cases) | NPU-06 "no ... unconsumed result remains" has no observability/flush path in contract.json. Prefer an explicit flush/idle (options 2/3) over ready-while-draining alone (race noted in F-01). |
| ISSUE-npu_local-01 | traceability-metadata only | no | Note in §4 that W_STRIDE reaches local implicitly via DMA tagging. |
| ISSUE-npu_local-02 | rule-level (AGENTS.md "every flop resets" vs data arrays) | no | SYS-03 already exempts mutable bytes; needs a one-line house-rule clarification for storage arrays (also `npu_dma.wbuf_q`, `sram.mem`). |
| ISSUE-npu_local-03 | spec-gap (needs change order) | **yes** (same cases as npu_dot-01) | Dispatch-as-re-arm is the right reading for local; the dot has no dispatch. Rule together with npu_dot-01. |
| ISSUE-sys-01 | spec-gap (needs change order) | no (B1 commits once) | "additional commits rejected" without a BRESP; see also F-05 for WO write-0. |
| ISSUE-uart-01 | spec-gap (needs change order) | no | "legal 2..65535" without a rejection sentence; rule together with BOOT_STAGE "0..4 only" (F-07). |
| ISSUE-sw_b1-01 | spec-clear | no | SYS-05: header "words 8..15 zero" + "ROM validates header ... before copy" — a nonzero reserved word is not a valid header; reject (0xB001) is the conservative and literal reading. |
| ISSUE-sw_b1-02 | spec-gap (needs change order) | no (B1 negative variants are magic/CRC only) | 0xB001 vs 0xB003 taxonomy for byte_length/load/entry is not stated; DV exact-code assertions need it. |

## (e)

Friction:
- Yosys `check` under `-q` prints nothing; `-l <log>` without `-q` is the only way to get a citable "Found and reported 0 problems" line (FLOW-002 already records this).
- `sw/**/*.bin` gitignore means the SW→ROM/DV interface bytes are not in the delivered diff; reproduction required a clean rebuild in the author's worktree (FLOW-003).
- Read tool caps a 1188-line file at ~1005 lines; fabric.sv needed two reads.
- `b1_extmem.json` uses `addr`/`file_offset` keys; no schema is stated anywhere for the DV loader.
- Harness-added `Co-Authored-By` trailers contradict the role-signature model tag on six commits; no attested model id exists to arbitrate.

Skill candidates:
- `integrator/references/review-checklist.md` — start every multi-author review with a cross-module table of provisional choices per shared interface (producer choice vs consumer choice); F-01 and F-04 are both "two conservative readings that disagree" and are invisible in per-module review.
- `integrator/references/review-checklist.md` — for SW deliveries, rebuild from clean and hash the interface artifacts before reading code; then diff the manifest against the packet's explicit "paste" list (F-03 found in one step).
- `rtl-engineer/references/partition-interfaces.md` — when contract.json gives a signal set without valid/ready (e.g. `dma_terminal`), state pulse-vs-level in the ISSUE **and** name the peer module's assumption; never document the peer's behaviour from your own assumption (F-04).
- `rtl-engineer/references/partition-interfaces.md` — any module that holds a result/operand register and has no dispatch/flush input must file the drain question against the *consumer's* ready policy, with the exact ready expression the consumer must keep (F-01).
- `sw-engineer/references/picorv32-irq.md` — the 0x100 trampoline runs before any register save; use `setq q2/q3` for scratch, never GPRs, until the firmware save routine has run (F-02).
- `chief-architect/references/icd-authoring.md` — every internal protocol in contract.json needs `semantics` (pulse/level, who clears, flush/abort path) and RTL port identifiers; four of the 27 filed issues are exactly these omissions.
- `orchestrator` (packet template) — require the commit body to contain the packet's "paste" items verbatim and reject at dispatch-close if absent; make `Co-Authored-By` policy explicit relative to the role signature.
