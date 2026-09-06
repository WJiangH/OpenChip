# llm_soc_top — connection binding table

SIM-L1, spec `docs/spec/llm-soc-v1/` @ 1.0-rc4 (repo commit `bd3b438d`,
CHANGE_ORDER_rc4.md). Written by the rtl-engineer role as the integration record
for `hw/rtl/llm_soc_top/llm_soc_top.sv`.

rc4 delta for this top: exactly one new connection, **C34** `dot_lifecycle`
{flush} from `npu_ctl` to `npu_dot` (NPU-09(b)); `contract.json connections[]`
now holds **48** ids (C01..C34 + CR00..CR06, CR08..CR14). ISSUE-top-01 (C23
level-vs-pulse) is ruled and closed by rc4 NPU-09(c): `dma_terminal` is a
registered level. Every port of all fourteen instantiated modules was re-checked
against the rc4-updated sources; C34 is the only port-level change.

This file is normative for anyone binding to the top **without reading the RTL**:
every contract.json `connections[]` id maps to exactly one producer port, one
consumer port and one top-level wire (or top port) name, spelled exactly as the
elaborated design spells it. Bus bundles are given as a prefix plus the signal
suffix appendix at the end; the full wire name is `<prefix><suffix>`.

Status vocabulary: `wired` (connected as the contract requires), `ISSUE-top-NN`
(recorded deviation, see ISSUES.md), `sunk-unused` (module output with no
contract consumer, tied into an `unused_*` sink), `external-dv` (the endpoint is
outside this top by contract disposition, so the harness owns it).

## 1. Top ports vs SYS-01

SYS-01: "The top shall expose `i_clk`, synchronous active-low `i_rst_n`,
`o_uart_tx`, `o_cpu_trap`, `o_fatal`, `o_result_valid`, `o_result_code[31:0]`,
and the external-memory AXI target-facing interface specified in axi.md."

| SYS-01 name | top port | dir | width | driven by | note |
|---|---|---|---|---|---|
| `i_clk` | `clk` | in | 1 | harness | **renamed**: AGENTS.md RTL conventions require the house name `clk`. Single 50 MHz simulation clock; no CDC, no gating. |
| `i_rst_n` | `rst_n` | in | 1 | harness | **renamed** for the same reason (`rst_n`, synchronous, active low). Held low >= 16 rising edges by the harness; also the coordinated reset of the DV external-memory model (SYS-03). |
| `o_uart_tx` | `o_uart_tx` | out | 1 | `uart.o_uart_tx` | idle 1 (SYS-11). |
| `o_cpu_trap` | `o_cpu_trap` | out | 1 | `cpu.o_trap` | direct mirror, not sticky (SYS-12). |
| `o_fatal` | `o_fatal` | out | 1 | `sys.o_fatal` | sticky, reset-only (SYS-07). |
| `o_result_valid` | `o_result_valid` | out | 1 | `sys.o_result_valid` | set by RESULT_COMMIT, holds until reset. |
| `o_result_code[31:0]` | `o_result_code` | out | 32 | `sys.o_result_code` | latched RESULT_CODE. |
| external-memory AXI4 | `m_axi_*` | 37 signals | see appendix A | `fabric` target port 2 | **initiator side** of C06 exported at the boundary; the DV-owned 16 MiB functional target (AXI-10) attaches here as the target. Signal set and widths are exactly AXI-01 / `protocols.axi4` (ID width 2, data 32, addr 32, no USER/REGION). |

Nothing else crosses the boundary. In particular there is **no** debug, trace,
scan, JTAG, security or "boot done" port, and no port for the `caliptra` block.

Top port count: 44 ports (2 + 5 + 37).

## 2. contract.json `connections[]`

### 2.1 Data-path and register-path connections

| id | protocol | producer `module.port` | consumer `module.port` | top wire | status |
|---|---|---|---|---|---|
| C01 | native | `cpu.o_mem_valid/o_mem_instr/o_mem_addr/o_mem_wdata/o_mem_wstrb`, in: `cpu.i_mem_ready/i_mem_rdata` | `cpu_bridge.i_mem_valid/i_mem_instr/i_mem_addr/i_mem_wdata/i_mem_wstrb`, out: `cpu_bridge.o_mem_ready/o_mem_rdata` | `nat_mem_valid`, `nat_mem_instr`, `nat_mem_ready`, `nat_mem_addr`, `nat_mem_wdata`, `nat_mem_wstrb`, `nat_mem_rdata` | wired |
| C02 | axi4 (fixed_id 0) | `cpu_bridge.axi_*` | `fabric.s0_axi_*` | `cb_axi_*` | wired |
| C03 | axi4 (fixed_id 1) | `npu_dma.m_axi_*` | `fabric.s1_axi_*` | `dma_axi_*` | wired |
| C04 | axi4 | `fabric.m0_axi_*` | `rom.s_axi_*` | `rom_axi_*` | wired |
| C05 | axi4 | `fabric.m1_axi_*` | `sram.s_axi_*` | `sram_axi_*` | wired |
| C06 | axi4 | `fabric.m2_axi_*` | *(extmem, DV model)* | top port `m_axi_*` (no internal wire) | wired to boundary / `external-dv` beyond it |
| C07 | axi4 | `fabric.m3_axi_*` | `lite_bridge.s_axi_*` | `lb_axi_*` | wired |
| C08 | axi4_lite | `lite_bridge.m0_axil_*` | `sys.s_axil_*` | `sys_axil_*` | wired |
| C09 | axi4_lite | `lite_bridge.m1_axil_*` | `npu_csr.s_axil_*` | `csr_axil_*` | wired |
| C10 | axi4_lite | `lite_bridge.m2_axil_*` | `irq.s_axil_*` | `irq_axil_*` | wired |
| C11 | axi4_lite | `lite_bridge.m3_axil_*` | `uart.s_axil_*` | `uart_axil_*` | wired |
| C12 | dispatch | `npu_csr.o_dispatch_<f>`, in: `npu_csr.i_dispatch_ready` | `npu_ctl.i_dispatch_<f>`, out: `npu_ctl.o_dispatch_ready` | `csr_disp_<f>` | wired |
| C13 | dispatch | `npu_ctl.o_dma_dispatch_<f>`, in: `npu_ctl.i_dma_dispatch_ready` | `npu_dma.i_dispatch_<f>`, out: `npu_dma.o_dispatch_ready` | `dma_disp_<f>` | wired |
| C25 | dispatch | `npu_ctl.o_local_dispatch_<f>`, in: `npu_ctl.i_local_dispatch_ready` | `npu_local.i_dispatch_<f>`, out: `npu_local.o_dispatch_ready` | `loc_disp_<f>` | wired |
| C14 | local_bytes | `npu_dma.o_local_bytes_<f>`, in: `npu_dma.i_local_bytes_ready` | `npu_local.i_local_bytes_<f>`, out: `npu_local.o_local_bytes_ready` | `lbytes_<f>` | wired |
| C15 | dot_operands | `npu_local.o_dot_operands_<f>`, in: `npu_local.i_dot_operands_ready` | `npu_dot.i_dot_operands_<f>`, out: `npu_dot.o_dot_operands_ready` | `dotop_<f>` | wired |
| C16 | group_result | `npu_dot.o_group_result_<f>`, in: `npu_dot.i_group_result_ready` | `npu_dma.i_group_result_<f>`, out: `npu_dma.o_group_result_ready` | `gres_<f>` | wired |
| C23 | dma_terminal | `npu_dma.o_dma_terminal_done` / `o_dma_terminal_error` / `o_dma_terminal_error_code` | `npu_ctl.i_dma_done` / `i_dma_error` / `i_dma_error_code` | `dmaterm_done`, `dmaterm_error`, `dmaterm_error_code` | wired (registered levels, NPU-09(c); ISSUE-top-01 closed by rc4) |
| C34 | dot_lifecycle | `npu_ctl.o_dot_lifecycle_flush` | `npu_dot.i_dot_lifecycle_flush` | `dotlife_flush` | wired |
| C24 | terminal | `npu_ctl.o_terminal_valid/o_terminal_tag/o_terminal_error_code/o_terminal_cycles`, in: `npu_ctl.i_terminal_ready` | `npu_csr.i_terminal_valid/i_terminal_tag/i_terminal_error_code/i_terminal_cycles`, out: `npu_csr.o_terminal_ready` | `term_valid`, `term_ready`, `term_tag`, `term_error_code`, `term_cycles` | wired |

`<f>` field sets (contract.json `protocols`, all fields present on both sides,
widths verified equal):

- `dispatch`: `valid`, `ready`, `opcode`, `x_base`, `w_base`, `y_base`, `k`, `n`,
  `group`, `w_stride`, `tag` (all payload 32 bits).
- `local_bytes`: `valid`, `ready`, `data`[32], `keep`[4], `kind`[2], `index`[12], `row`[12].
- `dot_operands`: `valid`, `ready`, `x_data`[32], `w_data`[32], `keep`[4],
  `group_first`, `group_last`, `row`[12], `group_index`[12], `command_last`.
- `group_result`: `valid`, `ready`, `data`[32], `row`[12], `group_index`[12], `last`.
- `terminal`: `valid`, `ready`, `tag`[32], `error_code`[3], `cycles`[32].
- `dma_terminal`: `done`, `error`, `error_code`[3] — no handshake; registered
  levels held until npu_dma's next C13 handshake or reset (NPU-09(c)).
- `dot_lifecycle`: `flush` — one registered level, no handshake, npu_ctl ->
  npu_dot (NPU-09(b)). It carries lifecycle state, not a static configuration:
  `dotlife_flush` is a named wire and must never be tied to a constant in any
  bind, wrapper or stub. Constant 0 restores the pre-rc4 npu_dot behaviour that
  NPU-09(b) forbids (a result or accumulator formed before a terminal survives
  into the next command, and the C25/dispatch-re-arm race reopens); constant 1
  masks `group_result.valid` forever, so no command can ever complete. Both are
  NPU-09(b) violations.

### 2.2 Interrupt connections

| id | source_signal / cpu_bit | producer `module.port` | consumer `module.port` | top wire | status |
|---|---|---|---|---|---|
| C17 | `done_irq`, cpu bit 4 | `npu_csr.o_done_irq` | `irq.i_npu_done_irq` | `npu_done_irq` | wired |
| C18 | `error_irq`, cpu bit 5 | `npu_csr.o_error_irq` | `irq.i_npu_error_irq` | `npu_error_irq` | wired |
| C19 | `tx_empty`, cpu bit 6 | `uart.o_tx_empty` | `irq.i_uart_tx_empty` | `uart_tx_empty` | wired |
| C20 | cpu bit 4 | `irq.o_irq[4]` | `cpu.i_irq[4]` | `cpu_irq[4]` | wired |
| C21 | cpu bit 5 | `irq.o_irq[5]` | `cpu.i_irq[5]` | `cpu_irq[5]` | wired |
| C22 | cpu bit 6 | `irq.o_irq[6]` | `cpu.i_irq[6]` | `cpu_irq[6]` | wired |

`cpu_irq` is one 32-bit wire: `irq.o_irq` drives all 32 bits and ties
`[31:7]` and `[3:0]` to zero (SYS-09 "all other external bits zero";
`[2:0]` stay core-owned and are permanently masked by `MASKED_IRQ=0xffffff8f`).
C20/C21/C22 are three bit slices of that single wire, not three separate wires.

### 2.3 Fault, reset and stop connections (SYS-12)

| id | protocol | producer `module.port` | consumer `module.port` | top wire | status |
|---|---|---|---|---|---|
| C26 | fault_event (reason 4) | `cpu.o_fault_valid/o_fault_reason/o_fault_addr` | `sys.i_cpu_fault_valid/i_cpu_fault_reason/i_cpu_fault_addr` | `cpu_fault_valid`, `cpu_fault_reason`, `cpu_fault_addr` | wired |
| C27 | fault_event (reason 1/2) | `cpu_bridge.o_fault_valid/o_fault_reason/o_fault_addr` | `sys.i_cpu_bridge_fault_valid/i_cpu_bridge_fault_reason/i_cpu_bridge_fault_addr` | `cb_fault_valid`, `cb_fault_reason`, `cb_fault_addr` | wired |
| C28 | fault_event (reason 3/6) | `fabric.o_fault_valid/o_fault_reason/o_fault_addr` | `sys.i_fabric_fault_valid/i_fabric_fault_reason/i_fabric_fault_addr` | `fab_fault_valid`, `fab_fault_reason`, `fab_fault_addr` | wired |
| C29 | fault_event (reason 5) | `npu_ctl.o_fault_valid/o_fault_reason/o_fault_addr` | `sys.i_npu_ctl_fault_valid/i_npu_ctl_fault_reason/i_npu_ctl_fault_addr` | `ctl_fault_valid`, `ctl_fault_reason`, `ctl_fault_addr` | wired |
| C30 | stop_issue | `sys.o_stop_new_transactions` | `cpu_bridge.i_stop_new_transactions` | `stop_new_transactions` | wired |
| C31 | stop_issue | `sys.o_stop_new_transactions` | `npu_ctl.i_stop_new_transactions` | `stop_new_transactions` | wired |
| C32 | stop_issue | `sys.o_stop_new_transactions` | `npu_dma.i_stop_new_transactions` | `stop_new_transactions` | wired |
| C33 | stop_issue | `sys.o_stop_new_transactions` | `fabric.i_stop_new_transactions` | `stop_new_transactions` | wired |

C30..C33 are one net with four loads, as SYS-12 describes ("sys drives sticky
`stop_new_transactions` to CPU bridge, NPU controller, NPU DMA, fabric").
`npu_local`, `npu_dot`, `npu_csr`, the memories and the peripherals have no stop
input in the contract and get none here.

### 2.4 Clock/reset connections

| id | target block | top wire(s) | status |
|---|---|---|---|
| CR00 | cpu (`cpu_clock_reset`) | `clk`, `rst_n` (sticky fault metadata) **and** `cpu_local_rst_n` = `sys.o_cpu_local_rst_n` -> `cpu.i_cpu_local_rst_n` (PicoRV32 core only) | wired |
| CR01 | cpu_bridge | `clk`, `rst_n` | wired |
| CR02 | fabric | `clk`, `rst_n` | wired |
| CR03 | rom | `clk`, `rst_n` | wired |
| CR04 | sram | `clk`, `rst_n` | wired |
| CR05 | extmem | — | external-dv: the model is not instantiated in this top (AXI-10). The harness must drive it from the same `clk`/`rst_n` it drives into the top, so that SYS-03's single coordinated reset epoch holds. |
| CR06 | lite_bridge | `clk`, `rst_n` | wired |
| CR08 | irq | `clk`, `rst_n` | wired |
| CR09 | uart | `clk`, `rst_n` | wired |
| CR10 | npu_csr | `clk`, `rst_n` | wired |
| CR11 | npu_ctl | `clk`, `rst_n` | wired |
| CR12 | npu_dma | `clk`, `rst_n` | wired |
| CR13 | npu_local | `clk`, `rst_n` | wired |
| CR14 | npu_dot | `clk`, `rst_n` | wired |

`contract.json` has no `CR07`: the ids skip from CR06 to CR08 and no `sys` self
clock/reset connection exists. `sys` is nevertheless clocked from the same
`clk`/`rst_n` as every other block — there is only one clock and one common
reset in SIM-L1 (SYS-01). Recorded here so the gap is not read as an omission
in this top.

## 3. Blocks in `contract.json` that are not instantiated

| block | disposition | why absent |
|---|---|---|
| `extmem` | `model` | AXI-10 makes it a DV-owned AXI functional target with configurable latency, seeds and error injection. It attaches to the `m_axi_*` boundary port. |
| `caliptra` | `integrate-S1-only` | S1 is a separate unreleased configuration. No instance, **no stub and no constant-success signal** (README: "no constant-success security block is permitted"). Its reserved aperture `0x40010000..0x4001FFFF` is simply not decoded by the delivered `fabric`, so a CPU access there takes the normal unmapped path (DECERR, no side effect, SYS-04). |

## 4. Delivered outputs with no contract consumer

| module.port | width | top wire | status |
|---|---|---|---|
| `cpu.o_eoi` | 32 | `unused_cpu_eoi` | sunk-unused. `contract.json` defines no connection carrying PicoRV32's end-of-interrupt vector, and SYS-10 binds software to the upstream `retirq` sequence rather than to a hardware EOI consumer. |
| `cpu.o_trace_valid` | 1 | `unused_cpu_trace_valid` | sunk-unused. `ENABLE_TRACE=1` is an integration-evidence parameter (dependencies.md); no top port for it exists in SYS-01. |
| `cpu.o_trace_data` | 36 | `unused_cpu_trace_data` | sunk-unused, same reason. |

All three are collected into `unused_ok` at the bottom of `llm_soc_top.sv`. They
remain observable to DV through hierarchical probes
(`<tb>.dut.u_cpu.unused_cpu_trace_data` etc. — note the sink wires are in the
top, the source pins are `u_cpu`'s outputs); nothing else in the design reads
them, so driving or forcing them cannot affect behaviour.

No input of any instantiated module is left undriven, and no connection listed in
`contract.json` is missing. Verified mechanically against the rc4 module sources:
all 778 pins of the fourteen instantiated modules (`clk`/`rst_n` included) are
accounted for by exactly one row above; 0 width mismatches, 0 direction
mismatches, and every internal net has exactly one driver and at least one load
except the three `unused_*` sinks in §4.

`hw/rtl/blink` and `hw/rtl/npu` are ADR-0001 Wishbone modules from the other
design family and are not part of this top.

## Appendix A — AXI4 signal suffixes (`protocols.axi4`, AXI-01)

Full wire name = bundle prefix from §2.1 + suffix. 37 signals; initiator drives
26, target drives 11; no USER, no REGION.

| suffix | width | driver |
|---|---|---|
| `awvalid` | 1 | initiator |
| `awready` | 1 | target |
| `awaddr` | 32 | initiator |
| `awid` | 2 | initiator |
| `awlen` | 8 | initiator |
| `awsize` | 3 | initiator |
| `awburst` | 2 | initiator |
| `awlock` | 1 | initiator |
| `awcache` | 4 | initiator |
| `awprot` | 3 | initiator |
| `awqos` | 4 | initiator |
| `wvalid` | 1 | initiator |
| `wready` | 1 | target |
| `wdata` | 32 | initiator |
| `wstrb` | 4 | initiator |
| `wlast` | 1 | initiator |
| `bvalid` | 1 | target |
| `bready` | 1 | initiator |
| `bresp` | 2 | target |
| `bid` | 2 | target |
| `arvalid` | 1 | initiator |
| `arready` | 1 | target |
| `araddr` | 32 | initiator |
| `arid` | 2 | initiator |
| `arlen` | 8 | initiator |
| `arsize` | 3 | initiator |
| `arburst` | 2 | initiator |
| `arlock` | 1 | initiator |
| `arcache` | 4 | initiator |
| `arprot` | 3 | initiator |
| `arqos` | 4 | initiator |
| `rvalid` | 1 | target |
| `rready` | 1 | initiator |
| `rdata` | 32 | target |
| `rresp` | 2 | target |
| `rid` | 2 | target |
| `rlast` | 1 | target |

## Appendix B — AXI4-Lite signal suffixes (`protocols.axi4_lite`, AXI-09)

19 signals; no ID, LEN, SIZE, BURST, LOCK, CACHE, QOS or LAST.

| suffix | width | driver |
|---|---|---|
| `awvalid` | 1 | initiator |
| `awready` | 1 | target |
| `awaddr` | 32 | initiator |
| `awprot` | 3 | initiator |
| `wvalid` | 1 | initiator |
| `wready` | 1 | target |
| `wdata` | 32 | initiator |
| `wstrb` | 4 | initiator |
| `bvalid` | 1 | target |
| `bready` | 1 | initiator |
| `bresp` | 2 | target |
| `arvalid` | 1 | initiator |
| `arready` | 1 | target |
| `araddr` | 32 | initiator |
| `arprot` | 3 | initiator |
| `rvalid` | 1 | target |
| `rready` | 1 | initiator |
| `rdata` | 32 | target |
| `rresp` | 2 | target |

## Appendix C — instance names

| instance | module | instance | module |
|---|---|---|---|
| `u_cpu` | `cpu` (contains `u_picorv32`) | `u_cpu_bridge` | `cpu_bridge` |
| `u_fabric` | `fabric` | `u_lite_bridge` | `lite_bridge` |
| `u_rom` | `rom` | `u_sram` | `sram` |
| `u_sys` | `sys` | `u_irq` | `irq` |
| `u_uart` | `uart` | `u_npu_csr` | `npu_csr` |
| `u_npu_ctl` | `npu_ctl` | `u_npu_dma` | `npu_dma` |
| `u_npu_local` | `npu_local` | `u_npu_dot` | `npu_dot` |
