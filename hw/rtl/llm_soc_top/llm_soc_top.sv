// llm_soc_top.sv — SIM-L1 top level: structural integration only.
//
// Spec: docs/spec/llm-soc-v1/system.md SYS-01 (top port list, 50 MHz sim
//   timebase, reset >=16 edges), §1 block diagram, §2 address map (decode lives
//   in fabric/lite_bridge, not here), §4 SYS-12 (fault_event fan-in,
//   cpu_local_rst_n, stop_new_transactions fan-out);
//   docs/spec/llm-soc-v1/axi.md AXI-01 (signal set), AXI-09 (Lite port set),
//   AXI-10 (external memory is a DV-owned functional target outside this top);
//   docs/spec/llm-soc-v1/npu.md §4 (dispatch / local_bytes / dot_operands /
//   group_result / dma_terminal / terminal internal partition interfaces),
//   NPU-09(b) (dot_lifecycle flush level, C34), NPU-09(c) (dma_terminal is a
//   registered level, not a pulse — CHANGE_ORDER_rc4 F-04 closed ISSUE-top-01);
//   docs/spec/llm-soc-v1/contract.json connections C01..C34, CR00..CR14.
//
// Spec baseline: docs/spec/llm-soc-v1/ @ 1.0-rc4 (CHANGE_ORDER_rc4.md). rc4
// adds exactly one connection to this top, C34 dot_lifecycle {flush}; no other
// port of any instantiated module changed.
//
// This file contains no logic: instances, wires and renames only. Every port
// pair it joins was checked for width, direction and field set; the audit and
// the id -> wire -> port table are in CONNECTIONS.md, deviations in ISSUES.md.
//
// Deliberate absences:
//   - caliptra (contract blocks[caliptra], disposition integrate-S1-only) is NOT
//     instantiated and has no stub: README forbids a constant-success security
//     block in SIM-L1. Its 0x40010000 aperture is simply not decoded by fabric.
//   - extmem (contract blocks[extmem], disposition "model") is not instantiated:
//     AXI-10 makes it a DV-owned functional target. Fabric target port 2 (C06)
//     leaves this top as `m_axi_*`; the model shares the harness clk/rst_n
//     (CR05), which SYS-03 requires to be the same coordinated reset.
//   - hw/rtl/blink and hw/rtl/npu are ADR-0001 Wishbone modules from the other
//     design family and are not part of this top (AGENTS.md: never mix buses).
//
// Port naming: SYS-01 writes `i_clk` / `i_rst_n`; this top keeps the house
// names `clk` / `rst_n` (AGENTS.md "Clock named clk", "reset named rst_n").
// That rename is recorded in CONNECTIONS.md; no other SYS-01 port is renamed.
`default_nettype none

module llm_soc_top (
    // SYS-01 clock and synchronous active-low reset (house names, see above).
    input wire clk,
    input wire rst_n,

    // SYS-01 observable outputs.
    output logic        o_uart_tx,       // uart.o_uart_tx (SYS-11)
    output logic        o_cpu_trap,      // cpu.o_trap, direct mirror (SYS-12)
    output logic        o_fatal,         // sys.o_fatal, sticky (SYS-07/SYS-12)
    output logic        o_result_valid,  // sys.o_result_valid (RESULT_COMMIT)
    output logic [31:0] o_result_code,   // sys.o_result_code (RESULT_CODE)

    // C06 external-memory AXI4 port, initiator side (fabric m2 -> extmem).
    output logic         m_axi_awvalid,
    input  wire          m_axi_awready,
    output logic [31:0]  m_axi_awaddr,
    output logic [ 1:0]  m_axi_awid,
    output logic [ 7:0]  m_axi_awlen,
    output logic [ 2:0]  m_axi_awsize,
    output logic [ 1:0]  m_axi_awburst,
    output logic         m_axi_awlock,
    output logic [ 3:0]  m_axi_awcache,
    output logic [ 2:0]  m_axi_awprot,
    output logic [ 3:0]  m_axi_awqos,
    output logic         m_axi_wvalid,
    input  wire          m_axi_wready,
    output logic [31:0]  m_axi_wdata,
    output logic [ 3:0]  m_axi_wstrb,
    output logic         m_axi_wlast,
    input  wire          m_axi_bvalid,
    output logic         m_axi_bready,
    input  wire  [ 1:0]  m_axi_bresp,
    input  wire  [ 1:0]  m_axi_bid,
    output logic         m_axi_arvalid,
    input  wire          m_axi_arready,
    output logic [31:0]  m_axi_araddr,
    output logic [ 1:0]  m_axi_arid,
    output logic [ 7:0]  m_axi_arlen,
    output logic [ 2:0]  m_axi_arsize,
    output logic [ 1:0]  m_axi_arburst,
    output logic         m_axi_arlock,
    output logic [ 3:0]  m_axi_arcache,
    output logic [ 2:0]  m_axi_arprot,
    output logic [ 3:0]  m_axi_arqos,
    input  wire          m_axi_rvalid,
    output logic         m_axi_rready,
    input  wire  [31:0]  m_axi_rdata,
    input  wire  [ 1:0]  m_axi_rresp,
    input  wire  [ 1:0]  m_axi_rid,
    input  wire          m_axi_rlast
);

  // ==========================================================================
  // Wires. One block per contract.json connection id; names are <id-role>_<field>.
  // ==========================================================================

  // C01 native: cpu (initiator) -> cpu_bridge (target)
  logic         nat_mem_valid;
  logic         nat_mem_instr;
  logic         nat_mem_ready;
  logic [31:0]  nat_mem_addr;
  logic [31:0]  nat_mem_wdata;
  logic [ 3:0]  nat_mem_wstrb;
  logic [31:0]  nat_mem_rdata;

  // C02 axi4: cpu_bridge -> fabric s0 (source ID 0)
  logic         cb_axi_awvalid;
  logic         cb_axi_awready;
  logic [31:0]  cb_axi_awaddr;
  logic [ 1:0]  cb_axi_awid;
  logic [ 7:0]  cb_axi_awlen;
  logic [ 2:0]  cb_axi_awsize;
  logic [ 1:0]  cb_axi_awburst;
  logic         cb_axi_awlock;
  logic [ 3:0]  cb_axi_awcache;
  logic [ 2:0]  cb_axi_awprot;
  logic [ 3:0]  cb_axi_awqos;
  logic         cb_axi_wvalid;
  logic         cb_axi_wready;
  logic [31:0]  cb_axi_wdata;
  logic [ 3:0]  cb_axi_wstrb;
  logic         cb_axi_wlast;
  logic         cb_axi_bvalid;
  logic         cb_axi_bready;
  logic [ 1:0]  cb_axi_bresp;
  logic [ 1:0]  cb_axi_bid;
  logic         cb_axi_arvalid;
  logic         cb_axi_arready;
  logic [31:0]  cb_axi_araddr;
  logic [ 1:0]  cb_axi_arid;
  logic [ 7:0]  cb_axi_arlen;
  logic [ 2:0]  cb_axi_arsize;
  logic [ 1:0]  cb_axi_arburst;
  logic         cb_axi_arlock;
  logic [ 3:0]  cb_axi_arcache;
  logic [ 2:0]  cb_axi_arprot;
  logic [ 3:0]  cb_axi_arqos;
  logic         cb_axi_rvalid;
  logic         cb_axi_rready;
  logic [31:0]  cb_axi_rdata;
  logic [ 1:0]  cb_axi_rresp;
  logic [ 1:0]  cb_axi_rid;
  logic         cb_axi_rlast;

  // C03 axi4: npu_dma -> fabric s1 (source ID 1)
  logic         dma_axi_awvalid;
  logic         dma_axi_awready;
  logic [31:0]  dma_axi_awaddr;
  logic [ 1:0]  dma_axi_awid;
  logic [ 7:0]  dma_axi_awlen;
  logic [ 2:0]  dma_axi_awsize;
  logic [ 1:0]  dma_axi_awburst;
  logic         dma_axi_awlock;
  logic [ 3:0]  dma_axi_awcache;
  logic [ 2:0]  dma_axi_awprot;
  logic [ 3:0]  dma_axi_awqos;
  logic         dma_axi_wvalid;
  logic         dma_axi_wready;
  logic [31:0]  dma_axi_wdata;
  logic [ 3:0]  dma_axi_wstrb;
  logic         dma_axi_wlast;
  logic         dma_axi_bvalid;
  logic         dma_axi_bready;
  logic [ 1:0]  dma_axi_bresp;
  logic [ 1:0]  dma_axi_bid;
  logic         dma_axi_arvalid;
  logic         dma_axi_arready;
  logic [31:0]  dma_axi_araddr;
  logic [ 1:0]  dma_axi_arid;
  logic [ 7:0]  dma_axi_arlen;
  logic [ 2:0]  dma_axi_arsize;
  logic [ 1:0]  dma_axi_arburst;
  logic         dma_axi_arlock;
  logic [ 3:0]  dma_axi_arcache;
  logic [ 2:0]  dma_axi_arprot;
  logic [ 3:0]  dma_axi_arqos;
  logic         dma_axi_rvalid;
  logic         dma_axi_rready;
  logic [31:0]  dma_axi_rdata;
  logic [ 1:0]  dma_axi_rresp;
  logic [ 1:0]  dma_axi_rid;
  logic         dma_axi_rlast;

  // C04 axi4: fabric m0 -> rom
  logic         rom_axi_awvalid;
  logic         rom_axi_awready;
  logic [31:0]  rom_axi_awaddr;
  logic [ 1:0]  rom_axi_awid;
  logic [ 7:0]  rom_axi_awlen;
  logic [ 2:0]  rom_axi_awsize;
  logic [ 1:0]  rom_axi_awburst;
  logic         rom_axi_awlock;
  logic [ 3:0]  rom_axi_awcache;
  logic [ 2:0]  rom_axi_awprot;
  logic [ 3:0]  rom_axi_awqos;
  logic         rom_axi_wvalid;
  logic         rom_axi_wready;
  logic [31:0]  rom_axi_wdata;
  logic [ 3:0]  rom_axi_wstrb;
  logic         rom_axi_wlast;
  logic         rom_axi_bvalid;
  logic         rom_axi_bready;
  logic [ 1:0]  rom_axi_bresp;
  logic [ 1:0]  rom_axi_bid;
  logic         rom_axi_arvalid;
  logic         rom_axi_arready;
  logic [31:0]  rom_axi_araddr;
  logic [ 1:0]  rom_axi_arid;
  logic [ 7:0]  rom_axi_arlen;
  logic [ 2:0]  rom_axi_arsize;
  logic [ 1:0]  rom_axi_arburst;
  logic         rom_axi_arlock;
  logic [ 3:0]  rom_axi_arcache;
  logic [ 2:0]  rom_axi_arprot;
  logic [ 3:0]  rom_axi_arqos;
  logic         rom_axi_rvalid;
  logic         rom_axi_rready;
  logic [31:0]  rom_axi_rdata;
  logic [ 1:0]  rom_axi_rresp;
  logic [ 1:0]  rom_axi_rid;
  logic         rom_axi_rlast;

  // C05 axi4: fabric m1 -> sram
  logic         sram_axi_awvalid;
  logic         sram_axi_awready;
  logic [31:0]  sram_axi_awaddr;
  logic [ 1:0]  sram_axi_awid;
  logic [ 7:0]  sram_axi_awlen;
  logic [ 2:0]  sram_axi_awsize;
  logic [ 1:0]  sram_axi_awburst;
  logic         sram_axi_awlock;
  logic [ 3:0]  sram_axi_awcache;
  logic [ 2:0]  sram_axi_awprot;
  logic [ 3:0]  sram_axi_awqos;
  logic         sram_axi_wvalid;
  logic         sram_axi_wready;
  logic [31:0]  sram_axi_wdata;
  logic [ 3:0]  sram_axi_wstrb;
  logic         sram_axi_wlast;
  logic         sram_axi_bvalid;
  logic         sram_axi_bready;
  logic [ 1:0]  sram_axi_bresp;
  logic [ 1:0]  sram_axi_bid;
  logic         sram_axi_arvalid;
  logic         sram_axi_arready;
  logic [31:0]  sram_axi_araddr;
  logic [ 1:0]  sram_axi_arid;
  logic [ 7:0]  sram_axi_arlen;
  logic [ 2:0]  sram_axi_arsize;
  logic [ 1:0]  sram_axi_arburst;
  logic         sram_axi_arlock;
  logic [ 3:0]  sram_axi_arcache;
  logic [ 2:0]  sram_axi_arprot;
  logic [ 3:0]  sram_axi_arqos;
  logic         sram_axi_rvalid;
  logic         sram_axi_rready;
  logic [31:0]  sram_axi_rdata;
  logic [ 1:0]  sram_axi_rresp;
  logic [ 1:0]  sram_axi_rid;
  logic         sram_axi_rlast;

  // C06 axi4: fabric m2 -> extmem leaves the top directly as m_axi_* (no wire).

  // C07 axi4: fabric m3 -> lite_bridge
  logic         lb_axi_awvalid;
  logic         lb_axi_awready;
  logic [31:0]  lb_axi_awaddr;
  logic [ 1:0]  lb_axi_awid;
  logic [ 7:0]  lb_axi_awlen;
  logic [ 2:0]  lb_axi_awsize;
  logic [ 1:0]  lb_axi_awburst;
  logic         lb_axi_awlock;
  logic [ 3:0]  lb_axi_awcache;
  logic [ 2:0]  lb_axi_awprot;
  logic [ 3:0]  lb_axi_awqos;
  logic         lb_axi_wvalid;
  logic         lb_axi_wready;
  logic [31:0]  lb_axi_wdata;
  logic [ 3:0]  lb_axi_wstrb;
  logic         lb_axi_wlast;
  logic         lb_axi_bvalid;
  logic         lb_axi_bready;
  logic [ 1:0]  lb_axi_bresp;
  logic [ 1:0]  lb_axi_bid;
  logic         lb_axi_arvalid;
  logic         lb_axi_arready;
  logic [31:0]  lb_axi_araddr;
  logic [ 1:0]  lb_axi_arid;
  logic [ 7:0]  lb_axi_arlen;
  logic [ 2:0]  lb_axi_arsize;
  logic [ 1:0]  lb_axi_arburst;
  logic         lb_axi_arlock;
  logic [ 3:0]  lb_axi_arcache;
  logic [ 2:0]  lb_axi_arprot;
  logic [ 3:0]  lb_axi_arqos;
  logic         lb_axi_rvalid;
  logic         lb_axi_rready;
  logic [31:0]  lb_axi_rdata;
  logic [ 1:0]  lb_axi_rresp;
  logic [ 1:0]  lb_axi_rid;
  logic         lb_axi_rlast;

  // C08 axi4_lite: lite_bridge m0 -> sys
  logic         sys_axil_awvalid;
  logic         sys_axil_awready;
  logic [31:0]  sys_axil_awaddr;
  logic [ 2:0]  sys_axil_awprot;
  logic         sys_axil_wvalid;
  logic         sys_axil_wready;
  logic [31:0]  sys_axil_wdata;
  logic [ 3:0]  sys_axil_wstrb;
  logic         sys_axil_bvalid;
  logic         sys_axil_bready;
  logic [ 1:0]  sys_axil_bresp;
  logic         sys_axil_arvalid;
  logic         sys_axil_arready;
  logic [31:0]  sys_axil_araddr;
  logic [ 2:0]  sys_axil_arprot;
  logic         sys_axil_rvalid;
  logic         sys_axil_rready;
  logic [31:0]  sys_axil_rdata;
  logic [ 1:0]  sys_axil_rresp;

  // C09 axi4_lite: lite_bridge m1 -> npu_csr
  logic         csr_axil_awvalid;
  logic         csr_axil_awready;
  logic [31:0]  csr_axil_awaddr;
  logic [ 2:0]  csr_axil_awprot;
  logic         csr_axil_wvalid;
  logic         csr_axil_wready;
  logic [31:0]  csr_axil_wdata;
  logic [ 3:0]  csr_axil_wstrb;
  logic         csr_axil_bvalid;
  logic         csr_axil_bready;
  logic [ 1:0]  csr_axil_bresp;
  logic         csr_axil_arvalid;
  logic         csr_axil_arready;
  logic [31:0]  csr_axil_araddr;
  logic [ 2:0]  csr_axil_arprot;
  logic         csr_axil_rvalid;
  logic         csr_axil_rready;
  logic [31:0]  csr_axil_rdata;
  logic [ 1:0]  csr_axil_rresp;

  // C10 axi4_lite: lite_bridge m2 -> irq
  logic         irq_axil_awvalid;
  logic         irq_axil_awready;
  logic [31:0]  irq_axil_awaddr;
  logic [ 2:0]  irq_axil_awprot;
  logic         irq_axil_wvalid;
  logic         irq_axil_wready;
  logic [31:0]  irq_axil_wdata;
  logic [ 3:0]  irq_axil_wstrb;
  logic         irq_axil_bvalid;
  logic         irq_axil_bready;
  logic [ 1:0]  irq_axil_bresp;
  logic         irq_axil_arvalid;
  logic         irq_axil_arready;
  logic [31:0]  irq_axil_araddr;
  logic [ 2:0]  irq_axil_arprot;
  logic         irq_axil_rvalid;
  logic         irq_axil_rready;
  logic [31:0]  irq_axil_rdata;
  logic [ 1:0]  irq_axil_rresp;

  // C11 axi4_lite: lite_bridge m3 -> uart
  logic         uart_axil_awvalid;
  logic         uart_axil_awready;
  logic [31:0]  uart_axil_awaddr;
  logic [ 2:0]  uart_axil_awprot;
  logic         uart_axil_wvalid;
  logic         uart_axil_wready;
  logic [31:0]  uart_axil_wdata;
  logic [ 3:0]  uart_axil_wstrb;
  logic         uart_axil_bvalid;
  logic         uart_axil_bready;
  logic [ 1:0]  uart_axil_bresp;
  logic         uart_axil_arvalid;
  logic         uart_axil_arready;
  logic [31:0]  uart_axil_araddr;
  logic [ 2:0]  uart_axil_arprot;
  logic         uart_axil_rvalid;
  logic         uart_axil_rready;
  logic [31:0]  uart_axil_rdata;
  logic [ 1:0]  uart_axil_rresp;

  // C12 dispatch: npu_csr -> npu_ctl
  logic csr_disp_valid;
  logic csr_disp_ready;
  logic [31:0] csr_disp_opcode;
  logic [31:0] csr_disp_x_base;
  logic [31:0] csr_disp_w_base;
  logic [31:0] csr_disp_y_base;
  logic [31:0] csr_disp_k;
  logic [31:0] csr_disp_n;
  logic [31:0] csr_disp_group;
  logic [31:0] csr_disp_w_stride;
  logic [31:0] csr_disp_tag;

  // C13 dispatch: npu_ctl -> npu_dma
  logic dma_disp_valid;
  logic dma_disp_ready;
  logic [31:0] dma_disp_opcode;
  logic [31:0] dma_disp_x_base;
  logic [31:0] dma_disp_w_base;
  logic [31:0] dma_disp_y_base;
  logic [31:0] dma_disp_k;
  logic [31:0] dma_disp_n;
  logic [31:0] dma_disp_group;
  logic [31:0] dma_disp_w_stride;
  logic [31:0] dma_disp_tag;

  // C25 dispatch: npu_ctl -> npu_local
  logic loc_disp_valid;
  logic loc_disp_ready;
  logic [31:0] loc_disp_opcode;
  logic [31:0] loc_disp_x_base;
  logic [31:0] loc_disp_w_base;
  logic [31:0] loc_disp_y_base;
  logic [31:0] loc_disp_k;
  logic [31:0] loc_disp_n;
  logic [31:0] loc_disp_group;
  logic [31:0] loc_disp_w_stride;
  logic [31:0] loc_disp_tag;

  // C14 local_bytes: npu_dma -> npu_local
  logic        lbytes_valid;
  logic        lbytes_ready;
  logic [31:0] lbytes_data;
  logic [ 3:0] lbytes_keep;
  logic [ 1:0] lbytes_kind;
  logic [11:0] lbytes_index;
  logic [11:0] lbytes_row;

  // C15 dot_operands: npu_local -> npu_dot
  logic        dotop_valid;
  logic        dotop_ready;
  logic [31:0] dotop_x_data;
  logic [31:0] dotop_w_data;
  logic [ 3:0] dotop_keep;
  logic        dotop_group_first;
  logic        dotop_group_last;
  logic [11:0] dotop_row;
  logic [11:0] dotop_group_index;
  logic        dotop_command_last;

  // C16 group_result: npu_dot -> npu_dma
  logic        gres_valid;
  logic        gres_ready;
  logic [31:0] gres_data;
  logic [11:0] gres_row;
  logic [11:0] gres_group_index;
  logic        gres_last;

  // C34 dot_lifecycle: npu_ctl -> npu_dot (one registered level, NPU-09(b)).
  // Never a constant here: 0 would restore the pre-rc4 npu_dot behaviour that
  // NPU-09(b) forbids (a result formed before a terminal could survive into the
  // next command), 1 would mask group_result.valid forever, so no command could
  // ever complete. Both are NPU-09(b) violations.
  logic        dotlife_flush;

  // C23 dma_terminal: npu_dma -> npu_ctl. No handshake; done/error/error_code
  // are registered levels held until npu_dma's next C13 handshake or reset
  // (NPU-09(c), rc4 F-04 — ISSUE-top-01 closed).
  logic        dmaterm_done;
  logic        dmaterm_error;
  logic [ 2:0] dmaterm_error_code;

  // C24 terminal: npu_ctl -> npu_csr
  logic        term_valid;
  logic        term_ready;
  logic [31:0] term_tag;
  logic [ 2:0] term_error_code;
  logic [31:0] term_cycles;

  // C17/C18/C19 irq_level sources -> irq; C20/C21/C22 irq -> cpu (bits 4/5/6)
  logic        npu_done_irq;
  logic        npu_error_irq;
  logic        uart_tx_empty;
  logic [31:0] cpu_irq;

  // C26..C29 fault_event -> sys (sticky, no READY; SYS-12)
  logic        cpu_fault_valid;
  logic [ 2:0] cpu_fault_reason;
  logic [31:0] cpu_fault_addr;
  logic        cb_fault_valid;
  logic [ 2:0] cb_fault_reason;
  logic [31:0] cb_fault_addr;
  logic        fab_fault_valid;
  logic [ 2:0] fab_fault_reason;
  logic [31:0] fab_fault_addr;
  logic        ctl_fault_valid;
  logic [ 2:0] ctl_fault_reason;
  logic [31:0] ctl_fault_addr;

  // CR00 cpu_clock_reset (sys -> cpu core only) and C30..C33 stop_issue fan-out
  logic        cpu_local_rst_n;
  logic        stop_new_transactions;

  // Delivered outputs with no consumer in contract.json connections[].
  logic [31:0] unused_cpu_eoi;
  logic        unused_cpu_trace_valid;
  logic [35:0] unused_cpu_trace_data;

  // ==========================================================================
  // CPU domain
  // ==========================================================================

  // CR00: common rst_n for the sticky fault metadata, cpu_local_rst_n for the
  // PicoRV32 core only (SYS-12).
  cpu u_cpu (
      .clk               (clk),
      .rst_n             (rst_n),
      .i_cpu_local_rst_n (cpu_local_rst_n),
      // C01 native initiator
      .o_mem_valid       (nat_mem_valid),
      .o_mem_instr       (nat_mem_instr),
      .i_mem_ready       (nat_mem_ready),
      .o_mem_addr        (nat_mem_addr),
      .o_mem_wdata       (nat_mem_wdata),
      .o_mem_wstrb       (nat_mem_wstrb),
      .i_mem_rdata       (nat_mem_rdata),
      // C20..C22 level IRQ bus (bits 4/5/6 driven by irq, all others zero)
      .i_irq             (cpu_irq),
      .o_eoi             (unused_cpu_eoi),
      // SYS-01 direct trap mirror
      .o_trap            (o_cpu_trap),
      // ENABLE_TRACE=1 evidence port: no consumer in contract.json
      .o_trace_valid     (unused_cpu_trace_valid),
      .o_trace_data      (unused_cpu_trace_data),
      // C26 fault_event -> sys (reason 4, addr 0)
      .o_fault_valid     (cpu_fault_valid),
      .o_fault_reason    (cpu_fault_reason),
      .o_fault_addr      (cpu_fault_addr)
  );

  cpu_bridge u_cpu_bridge (
      .clk                     (clk),
      .rst_n                   (rst_n),
      // C01 native target
      .i_mem_valid             (nat_mem_valid),
      .i_mem_instr             (nat_mem_instr),
      .o_mem_ready             (nat_mem_ready),
      .i_mem_addr              (nat_mem_addr),
      .i_mem_wdata             (nat_mem_wdata),
      .i_mem_wstrb             (nat_mem_wstrb),
      .o_mem_rdata             (nat_mem_rdata),
      // C02 AXI4 initiator, fixed ID 0
      .axi_awvalid            (cb_axi_awvalid),
      .axi_awready            (cb_axi_awready),
      .axi_awaddr             (cb_axi_awaddr),
      .axi_awid               (cb_axi_awid),
      .axi_awlen              (cb_axi_awlen),
      .axi_awsize             (cb_axi_awsize),
      .axi_awburst            (cb_axi_awburst),
      .axi_awlock             (cb_axi_awlock),
      .axi_awcache            (cb_axi_awcache),
      .axi_awprot             (cb_axi_awprot),
      .axi_awqos              (cb_axi_awqos),
      .axi_wvalid             (cb_axi_wvalid),
      .axi_wready             (cb_axi_wready),
      .axi_wdata              (cb_axi_wdata),
      .axi_wstrb              (cb_axi_wstrb),
      .axi_wlast              (cb_axi_wlast),
      .axi_bvalid             (cb_axi_bvalid),
      .axi_bready             (cb_axi_bready),
      .axi_bresp              (cb_axi_bresp),
      .axi_bid                (cb_axi_bid),
      .axi_arvalid            (cb_axi_arvalid),
      .axi_arready            (cb_axi_arready),
      .axi_araddr             (cb_axi_araddr),
      .axi_arid               (cb_axi_arid),
      .axi_arlen              (cb_axi_arlen),
      .axi_arsize             (cb_axi_arsize),
      .axi_arburst            (cb_axi_arburst),
      .axi_arlock             (cb_axi_arlock),
      .axi_arcache            (cb_axi_arcache),
      .axi_arprot             (cb_axi_arprot),
      .axi_arqos              (cb_axi_arqos),
      .axi_rvalid             (cb_axi_rvalid),
      .axi_rready             (cb_axi_rready),
      .axi_rdata              (cb_axi_rdata),
      .axi_rresp              (cb_axi_rresp),
      .axi_rid                (cb_axi_rid),
      .axi_rlast              (cb_axi_rlast),
      // C27 fault_event -> sys (reason 1 read / 2 write)
      .o_fault_valid           (cb_fault_valid),
      .o_fault_reason          (cb_fault_reason),
      .o_fault_addr            (cb_fault_addr),
      // C30 stop_issue <- sys
      .i_stop_new_transactions (stop_new_transactions)
  );

  // ==========================================================================
  // Interconnect
  // ==========================================================================

  fabric u_fabric (
      .clk                     (clk),
      .rst_n                   (rst_n),
      // C02 initiator port s0 = cpu_bridge (source ID 0)
      .s0_axi_awvalid         (cb_axi_awvalid),
      .s0_axi_awready         (cb_axi_awready),
      .s0_axi_awaddr          (cb_axi_awaddr),
      .s0_axi_awid            (cb_axi_awid),
      .s0_axi_awlen           (cb_axi_awlen),
      .s0_axi_awsize          (cb_axi_awsize),
      .s0_axi_awburst         (cb_axi_awburst),
      .s0_axi_awlock          (cb_axi_awlock),
      .s0_axi_awcache         (cb_axi_awcache),
      .s0_axi_awprot          (cb_axi_awprot),
      .s0_axi_awqos           (cb_axi_awqos),
      .s0_axi_wvalid          (cb_axi_wvalid),
      .s0_axi_wready          (cb_axi_wready),
      .s0_axi_wdata           (cb_axi_wdata),
      .s0_axi_wstrb           (cb_axi_wstrb),
      .s0_axi_wlast           (cb_axi_wlast),
      .s0_axi_bvalid          (cb_axi_bvalid),
      .s0_axi_bready          (cb_axi_bready),
      .s0_axi_bresp           (cb_axi_bresp),
      .s0_axi_bid             (cb_axi_bid),
      .s0_axi_arvalid         (cb_axi_arvalid),
      .s0_axi_arready         (cb_axi_arready),
      .s0_axi_araddr          (cb_axi_araddr),
      .s0_axi_arid            (cb_axi_arid),
      .s0_axi_arlen           (cb_axi_arlen),
      .s0_axi_arsize          (cb_axi_arsize),
      .s0_axi_arburst         (cb_axi_arburst),
      .s0_axi_arlock          (cb_axi_arlock),
      .s0_axi_arcache         (cb_axi_arcache),
      .s0_axi_arprot          (cb_axi_arprot),
      .s0_axi_arqos           (cb_axi_arqos),
      .s0_axi_rvalid          (cb_axi_rvalid),
      .s0_axi_rready          (cb_axi_rready),
      .s0_axi_rdata           (cb_axi_rdata),
      .s0_axi_rresp           (cb_axi_rresp),
      .s0_axi_rid             (cb_axi_rid),
      .s0_axi_rlast           (cb_axi_rlast),
      // C03 initiator port s1 = npu_dma (source ID 1)
      .s1_axi_awvalid         (dma_axi_awvalid),
      .s1_axi_awready         (dma_axi_awready),
      .s1_axi_awaddr          (dma_axi_awaddr),
      .s1_axi_awid            (dma_axi_awid),
      .s1_axi_awlen           (dma_axi_awlen),
      .s1_axi_awsize          (dma_axi_awsize),
      .s1_axi_awburst         (dma_axi_awburst),
      .s1_axi_awlock          (dma_axi_awlock),
      .s1_axi_awcache         (dma_axi_awcache),
      .s1_axi_awprot          (dma_axi_awprot),
      .s1_axi_awqos           (dma_axi_awqos),
      .s1_axi_wvalid          (dma_axi_wvalid),
      .s1_axi_wready          (dma_axi_wready),
      .s1_axi_wdata           (dma_axi_wdata),
      .s1_axi_wstrb           (dma_axi_wstrb),
      .s1_axi_wlast           (dma_axi_wlast),
      .s1_axi_bvalid          (dma_axi_bvalid),
      .s1_axi_bready          (dma_axi_bready),
      .s1_axi_bresp           (dma_axi_bresp),
      .s1_axi_bid             (dma_axi_bid),
      .s1_axi_arvalid         (dma_axi_arvalid),
      .s1_axi_arready         (dma_axi_arready),
      .s1_axi_araddr          (dma_axi_araddr),
      .s1_axi_arid            (dma_axi_arid),
      .s1_axi_arlen           (dma_axi_arlen),
      .s1_axi_arsize          (dma_axi_arsize),
      .s1_axi_arburst         (dma_axi_arburst),
      .s1_axi_arlock          (dma_axi_arlock),
      .s1_axi_arcache         (dma_axi_arcache),
      .s1_axi_arprot          (dma_axi_arprot),
      .s1_axi_arqos           (dma_axi_arqos),
      .s1_axi_rvalid          (dma_axi_rvalid),
      .s1_axi_rready          (dma_axi_rready),
      .s1_axi_rdata           (dma_axi_rdata),
      .s1_axi_rresp           (dma_axi_rresp),
      .s1_axi_rid             (dma_axi_rid),
      .s1_axi_rlast           (dma_axi_rlast),
      // C04 target port m0 = rom (0x00000000, 64 KiB)
      .m0_axi_awvalid         (rom_axi_awvalid),
      .m0_axi_awready         (rom_axi_awready),
      .m0_axi_awaddr          (rom_axi_awaddr),
      .m0_axi_awid            (rom_axi_awid),
      .m0_axi_awlen           (rom_axi_awlen),
      .m0_axi_awsize          (rom_axi_awsize),
      .m0_axi_awburst         (rom_axi_awburst),
      .m0_axi_awlock          (rom_axi_awlock),
      .m0_axi_awcache         (rom_axi_awcache),
      .m0_axi_awprot          (rom_axi_awprot),
      .m0_axi_awqos           (rom_axi_awqos),
      .m0_axi_wvalid          (rom_axi_wvalid),
      .m0_axi_wready          (rom_axi_wready),
      .m0_axi_wdata           (rom_axi_wdata),
      .m0_axi_wstrb           (rom_axi_wstrb),
      .m0_axi_wlast           (rom_axi_wlast),
      .m0_axi_bvalid          (rom_axi_bvalid),
      .m0_axi_bready          (rom_axi_bready),
      .m0_axi_bresp           (rom_axi_bresp),
      .m0_axi_bid             (rom_axi_bid),
      .m0_axi_arvalid         (rom_axi_arvalid),
      .m0_axi_arready         (rom_axi_arready),
      .m0_axi_araddr          (rom_axi_araddr),
      .m0_axi_arid            (rom_axi_arid),
      .m0_axi_arlen           (rom_axi_arlen),
      .m0_axi_arsize          (rom_axi_arsize),
      .m0_axi_arburst         (rom_axi_arburst),
      .m0_axi_arlock          (rom_axi_arlock),
      .m0_axi_arcache         (rom_axi_arcache),
      .m0_axi_arprot          (rom_axi_arprot),
      .m0_axi_arqos           (rom_axi_arqos),
      .m0_axi_rvalid          (rom_axi_rvalid),
      .m0_axi_rready          (rom_axi_rready),
      .m0_axi_rdata           (rom_axi_rdata),
      .m0_axi_rresp           (rom_axi_rresp),
      .m0_axi_rid             (rom_axi_rid),
      .m0_axi_rlast           (rom_axi_rlast),
      // C05 target port m1 = sram (0x10000000, 256 KiB)
      .m1_axi_awvalid         (sram_axi_awvalid),
      .m1_axi_awready         (sram_axi_awready),
      .m1_axi_awaddr          (sram_axi_awaddr),
      .m1_axi_awid            (sram_axi_awid),
      .m1_axi_awlen           (sram_axi_awlen),
      .m1_axi_awsize          (sram_axi_awsize),
      .m1_axi_awburst         (sram_axi_awburst),
      .m1_axi_awlock          (sram_axi_awlock),
      .m1_axi_awcache         (sram_axi_awcache),
      .m1_axi_awprot          (sram_axi_awprot),
      .m1_axi_awqos           (sram_axi_awqos),
      .m1_axi_wvalid          (sram_axi_wvalid),
      .m1_axi_wready          (sram_axi_wready),
      .m1_axi_wdata           (sram_axi_wdata),
      .m1_axi_wstrb           (sram_axi_wstrb),
      .m1_axi_wlast           (sram_axi_wlast),
      .m1_axi_bvalid          (sram_axi_bvalid),
      .m1_axi_bready          (sram_axi_bready),
      .m1_axi_bresp           (sram_axi_bresp),
      .m1_axi_bid             (sram_axi_bid),
      .m1_axi_arvalid         (sram_axi_arvalid),
      .m1_axi_arready         (sram_axi_arready),
      .m1_axi_araddr          (sram_axi_araddr),
      .m1_axi_arid            (sram_axi_arid),
      .m1_axi_arlen           (sram_axi_arlen),
      .m1_axi_arsize          (sram_axi_arsize),
      .m1_axi_arburst         (sram_axi_arburst),
      .m1_axi_arlock          (sram_axi_arlock),
      .m1_axi_arcache         (sram_axi_arcache),
      .m1_axi_arprot          (sram_axi_arprot),
      .m1_axi_arqos           (sram_axi_arqos),
      .m1_axi_rvalid          (sram_axi_rvalid),
      .m1_axi_rready          (sram_axi_rready),
      .m1_axi_rdata           (sram_axi_rdata),
      .m1_axi_rresp           (sram_axi_rresp),
      .m1_axi_rid             (sram_axi_rid),
      .m1_axi_rlast           (sram_axi_rlast),
      // C06 target port m2 = extmem, exported as the top m_axi_* port
      .m2_axi_awvalid         (m_axi_awvalid),
      .m2_axi_awready         (m_axi_awready),
      .m2_axi_awaddr          (m_axi_awaddr),
      .m2_axi_awid            (m_axi_awid),
      .m2_axi_awlen           (m_axi_awlen),
      .m2_axi_awsize          (m_axi_awsize),
      .m2_axi_awburst         (m_axi_awburst),
      .m2_axi_awlock          (m_axi_awlock),
      .m2_axi_awcache         (m_axi_awcache),
      .m2_axi_awprot          (m_axi_awprot),
      .m2_axi_awqos           (m_axi_awqos),
      .m2_axi_wvalid          (m_axi_wvalid),
      .m2_axi_wready          (m_axi_wready),
      .m2_axi_wdata           (m_axi_wdata),
      .m2_axi_wstrb           (m_axi_wstrb),
      .m2_axi_wlast           (m_axi_wlast),
      .m2_axi_bvalid          (m_axi_bvalid),
      .m2_axi_bready          (m_axi_bready),
      .m2_axi_bresp           (m_axi_bresp),
      .m2_axi_bid             (m_axi_bid),
      .m2_axi_arvalid         (m_axi_arvalid),
      .m2_axi_arready         (m_axi_arready),
      .m2_axi_araddr          (m_axi_araddr),
      .m2_axi_arid            (m_axi_arid),
      .m2_axi_arlen           (m_axi_arlen),
      .m2_axi_arsize          (m_axi_arsize),
      .m2_axi_arburst         (m_axi_arburst),
      .m2_axi_arlock          (m_axi_arlock),
      .m2_axi_arcache         (m_axi_arcache),
      .m2_axi_arprot          (m_axi_arprot),
      .m2_axi_arqos           (m_axi_arqos),
      .m2_axi_rvalid          (m_axi_rvalid),
      .m2_axi_rready          (m_axi_rready),
      .m2_axi_rdata           (m_axi_rdata),
      .m2_axi_rresp           (m_axi_rresp),
      .m2_axi_rid             (m_axi_rid),
      .m2_axi_rlast           (m_axi_rlast),
      // C07 target port m3 = lite_bridge (0x40000000 peripheral window)
      .m3_axi_awvalid         (lb_axi_awvalid),
      .m3_axi_awready         (lb_axi_awready),
      .m3_axi_awaddr          (lb_axi_awaddr),
      .m3_axi_awid            (lb_axi_awid),
      .m3_axi_awlen           (lb_axi_awlen),
      .m3_axi_awsize          (lb_axi_awsize),
      .m3_axi_awburst         (lb_axi_awburst),
      .m3_axi_awlock          (lb_axi_awlock),
      .m3_axi_awcache         (lb_axi_awcache),
      .m3_axi_awprot          (lb_axi_awprot),
      .m3_axi_awqos           (lb_axi_awqos),
      .m3_axi_wvalid          (lb_axi_wvalid),
      .m3_axi_wready          (lb_axi_wready),
      .m3_axi_wdata           (lb_axi_wdata),
      .m3_axi_wstrb           (lb_axi_wstrb),
      .m3_axi_wlast           (lb_axi_wlast),
      .m3_axi_bvalid          (lb_axi_bvalid),
      .m3_axi_bready          (lb_axi_bready),
      .m3_axi_bresp           (lb_axi_bresp),
      .m3_axi_bid             (lb_axi_bid),
      .m3_axi_arvalid         (lb_axi_arvalid),
      .m3_axi_arready         (lb_axi_arready),
      .m3_axi_araddr          (lb_axi_araddr),
      .m3_axi_arid            (lb_axi_arid),
      .m3_axi_arlen           (lb_axi_arlen),
      .m3_axi_arsize          (lb_axi_arsize),
      .m3_axi_arburst         (lb_axi_arburst),
      .m3_axi_arlock          (lb_axi_arlock),
      .m3_axi_arcache         (lb_axi_arcache),
      .m3_axi_arprot          (lb_axi_arprot),
      .m3_axi_arqos           (lb_axi_arqos),
      .m3_axi_rvalid          (lb_axi_rvalid),
      .m3_axi_rready          (lb_axi_rready),
      .m3_axi_rdata           (lb_axi_rdata),
      .m3_axi_rresp           (lb_axi_rresp),
      .m3_axi_rid             (lb_axi_rid),
      .m3_axi_rlast           (lb_axi_rlast),
      // C28 fault_event -> sys (reason 3 progress / 6 protocol)
      .o_fault_valid           (fab_fault_valid),
      .o_fault_reason          (fab_fault_reason),
      .o_fault_addr            (fab_fault_addr),
      // C33 stop_issue <- sys
      .i_stop_new_transactions (stop_new_transactions)
  );

  lite_bridge u_lite_bridge (
      .clk              (clk),
      .rst_n            (rst_n),
      // C07 full-AXI target from fabric m3
      .s_axi_awvalid   (lb_axi_awvalid),
      .s_axi_awready   (lb_axi_awready),
      .s_axi_awaddr    (lb_axi_awaddr),
      .s_axi_awid      (lb_axi_awid),
      .s_axi_awlen     (lb_axi_awlen),
      .s_axi_awsize    (lb_axi_awsize),
      .s_axi_awburst   (lb_axi_awburst),
      .s_axi_awlock    (lb_axi_awlock),
      .s_axi_awcache   (lb_axi_awcache),
      .s_axi_awprot    (lb_axi_awprot),
      .s_axi_awqos     (lb_axi_awqos),
      .s_axi_wvalid    (lb_axi_wvalid),
      .s_axi_wready    (lb_axi_wready),
      .s_axi_wdata     (lb_axi_wdata),
      .s_axi_wstrb     (lb_axi_wstrb),
      .s_axi_wlast     (lb_axi_wlast),
      .s_axi_bvalid    (lb_axi_bvalid),
      .s_axi_bready    (lb_axi_bready),
      .s_axi_bresp     (lb_axi_bresp),
      .s_axi_bid       (lb_axi_bid),
      .s_axi_arvalid   (lb_axi_arvalid),
      .s_axi_arready   (lb_axi_arready),
      .s_axi_araddr    (lb_axi_araddr),
      .s_axi_arid      (lb_axi_arid),
      .s_axi_arlen     (lb_axi_arlen),
      .s_axi_arsize    (lb_axi_arsize),
      .s_axi_arburst   (lb_axi_arburst),
      .s_axi_arlock    (lb_axi_arlock),
      .s_axi_arcache   (lb_axi_arcache),
      .s_axi_arprot    (lb_axi_arprot),
      .s_axi_arqos     (lb_axi_arqos),
      .s_axi_rvalid    (lb_axi_rvalid),
      .s_axi_rready    (lb_axi_rready),
      .s_axi_rdata     (lb_axi_rdata),
      .s_axi_rresp     (lb_axi_rresp),
      .s_axi_rid       (lb_axi_rid),
      .s_axi_rlast     (lb_axi_rlast),
      // C08 Lite m0 -> sys (0x40000000)
      .m0_axil_awvalid (sys_axil_awvalid),
      .m0_axil_awready (sys_axil_awready),
      .m0_axil_awaddr  (sys_axil_awaddr),
      .m0_axil_awprot  (sys_axil_awprot),
      .m0_axil_wvalid  (sys_axil_wvalid),
      .m0_axil_wready  (sys_axil_wready),
      .m0_axil_wdata   (sys_axil_wdata),
      .m0_axil_wstrb   (sys_axil_wstrb),
      .m0_axil_bvalid  (sys_axil_bvalid),
      .m0_axil_bready  (sys_axil_bready),
      .m0_axil_bresp   (sys_axil_bresp),
      .m0_axil_arvalid (sys_axil_arvalid),
      .m0_axil_arready (sys_axil_arready),
      .m0_axil_araddr  (sys_axil_araddr),
      .m0_axil_arprot  (sys_axil_arprot),
      .m0_axil_rvalid  (sys_axil_rvalid),
      .m0_axil_rready  (sys_axil_rready),
      .m0_axil_rdata   (sys_axil_rdata),
      .m0_axil_rresp   (sys_axil_rresp),
      // C09 Lite m1 -> npu_csr (0x40001000)
      .m1_axil_awvalid (csr_axil_awvalid),
      .m1_axil_awready (csr_axil_awready),
      .m1_axil_awaddr  (csr_axil_awaddr),
      .m1_axil_awprot  (csr_axil_awprot),
      .m1_axil_wvalid  (csr_axil_wvalid),
      .m1_axil_wready  (csr_axil_wready),
      .m1_axil_wdata   (csr_axil_wdata),
      .m1_axil_wstrb   (csr_axil_wstrb),
      .m1_axil_bvalid  (csr_axil_bvalid),
      .m1_axil_bready  (csr_axil_bready),
      .m1_axil_bresp   (csr_axil_bresp),
      .m1_axil_arvalid (csr_axil_arvalid),
      .m1_axil_arready (csr_axil_arready),
      .m1_axil_araddr  (csr_axil_araddr),
      .m1_axil_arprot  (csr_axil_arprot),
      .m1_axil_rvalid  (csr_axil_rvalid),
      .m1_axil_rready  (csr_axil_rready),
      .m1_axil_rdata   (csr_axil_rdata),
      .m1_axil_rresp   (csr_axil_rresp),
      // C10 Lite m2 -> irq (0x40002000)
      .m2_axil_awvalid (irq_axil_awvalid),
      .m2_axil_awready (irq_axil_awready),
      .m2_axil_awaddr  (irq_axil_awaddr),
      .m2_axil_awprot  (irq_axil_awprot),
      .m2_axil_wvalid  (irq_axil_wvalid),
      .m2_axil_wready  (irq_axil_wready),
      .m2_axil_wdata   (irq_axil_wdata),
      .m2_axil_wstrb   (irq_axil_wstrb),
      .m2_axil_bvalid  (irq_axil_bvalid),
      .m2_axil_bready  (irq_axil_bready),
      .m2_axil_bresp   (irq_axil_bresp),
      .m2_axil_arvalid (irq_axil_arvalid),
      .m2_axil_arready (irq_axil_arready),
      .m2_axil_araddr  (irq_axil_araddr),
      .m2_axil_arprot  (irq_axil_arprot),
      .m2_axil_rvalid  (irq_axil_rvalid),
      .m2_axil_rready  (irq_axil_rready),
      .m2_axil_rdata   (irq_axil_rdata),
      .m2_axil_rresp   (irq_axil_rresp),
      // C11 Lite m3 -> uart (0x40003000)
      .m3_axil_awvalid (uart_axil_awvalid),
      .m3_axil_awready (uart_axil_awready),
      .m3_axil_awaddr  (uart_axil_awaddr),
      .m3_axil_awprot  (uart_axil_awprot),
      .m3_axil_wvalid  (uart_axil_wvalid),
      .m3_axil_wready  (uart_axil_wready),
      .m3_axil_wdata   (uart_axil_wdata),
      .m3_axil_wstrb   (uart_axil_wstrb),
      .m3_axil_bvalid  (uart_axil_bvalid),
      .m3_axil_bready  (uart_axil_bready),
      .m3_axil_bresp   (uart_axil_bresp),
      .m3_axil_arvalid (uart_axil_arvalid),
      .m3_axil_arready (uart_axil_arready),
      .m3_axil_araddr  (uart_axil_araddr),
      .m3_axil_arprot  (uart_axil_arprot),
      .m3_axil_rvalid  (uart_axil_rvalid),
      .m3_axil_rready  (uart_axil_rready),
      .m3_axil_rdata   (uart_axil_rdata),
      .m3_axil_rresp   (uart_axil_rresp)
  );

  // ==========================================================================
  // Memories (extmem is DV-owned, see header)
  // ==========================================================================

  rom u_rom (
      .clk    (clk),
      .rst_n  (rst_n),
      .s_axi_awvalid(rom_axi_awvalid),
      .s_axi_awready(rom_axi_awready),
      .s_axi_awaddr(rom_axi_awaddr),
      .s_axi_awid  (rom_axi_awid),
      .s_axi_awlen (rom_axi_awlen),
      .s_axi_awsize(rom_axi_awsize),
      .s_axi_awburst(rom_axi_awburst),
      .s_axi_awlock(rom_axi_awlock),
      .s_axi_awcache(rom_axi_awcache),
      .s_axi_awprot(rom_axi_awprot),
      .s_axi_awqos (rom_axi_awqos),
      .s_axi_wvalid(rom_axi_wvalid),
      .s_axi_wready(rom_axi_wready),
      .s_axi_wdata (rom_axi_wdata),
      .s_axi_wstrb (rom_axi_wstrb),
      .s_axi_wlast (rom_axi_wlast),
      .s_axi_bvalid(rom_axi_bvalid),
      .s_axi_bready(rom_axi_bready),
      .s_axi_bresp (rom_axi_bresp),
      .s_axi_bid   (rom_axi_bid),
      .s_axi_arvalid(rom_axi_arvalid),
      .s_axi_arready(rom_axi_arready),
      .s_axi_araddr(rom_axi_araddr),
      .s_axi_arid  (rom_axi_arid),
      .s_axi_arlen (rom_axi_arlen),
      .s_axi_arsize(rom_axi_arsize),
      .s_axi_arburst(rom_axi_arburst),
      .s_axi_arlock(rom_axi_arlock),
      .s_axi_arcache(rom_axi_arcache),
      .s_axi_arprot(rom_axi_arprot),
      .s_axi_arqos (rom_axi_arqos),
      .s_axi_rvalid(rom_axi_rvalid),
      .s_axi_rready(rom_axi_rready),
      .s_axi_rdata (rom_axi_rdata),
      .s_axi_rresp (rom_axi_rresp),
      .s_axi_rid   (rom_axi_rid),
      .s_axi_rlast (rom_axi_rlast)
  );

  sram u_sram (
      .clk    (clk),
      .rst_n  (rst_n),
      .s_axi_awvalid(sram_axi_awvalid),
      .s_axi_awready(sram_axi_awready),
      .s_axi_awaddr(sram_axi_awaddr),
      .s_axi_awid  (sram_axi_awid),
      .s_axi_awlen (sram_axi_awlen),
      .s_axi_awsize(sram_axi_awsize),
      .s_axi_awburst(sram_axi_awburst),
      .s_axi_awlock(sram_axi_awlock),
      .s_axi_awcache(sram_axi_awcache),
      .s_axi_awprot(sram_axi_awprot),
      .s_axi_awqos (sram_axi_awqos),
      .s_axi_wvalid(sram_axi_wvalid),
      .s_axi_wready(sram_axi_wready),
      .s_axi_wdata (sram_axi_wdata),
      .s_axi_wstrb (sram_axi_wstrb),
      .s_axi_wlast (sram_axi_wlast),
      .s_axi_bvalid(sram_axi_bvalid),
      .s_axi_bready(sram_axi_bready),
      .s_axi_bresp (sram_axi_bresp),
      .s_axi_bid   (sram_axi_bid),
      .s_axi_arvalid(sram_axi_arvalid),
      .s_axi_arready(sram_axi_arready),
      .s_axi_araddr(sram_axi_araddr),
      .s_axi_arid  (sram_axi_arid),
      .s_axi_arlen (sram_axi_arlen),
      .s_axi_arsize(sram_axi_arsize),
      .s_axi_arburst(sram_axi_arburst),
      .s_axi_arlock(sram_axi_arlock),
      .s_axi_arcache(sram_axi_arcache),
      .s_axi_arprot(sram_axi_arprot),
      .s_axi_arqos (sram_axi_arqos),
      .s_axi_rvalid(sram_axi_rvalid),
      .s_axi_rready(sram_axi_rready),
      .s_axi_rdata (sram_axi_rdata),
      .s_axi_rresp (sram_axi_rresp),
      .s_axi_rid   (sram_axi_rid),
      .s_axi_rlast (sram_axi_rlast)
  );

  // ==========================================================================
  // Peripherals
  // ==========================================================================

  sys u_sys (
      .clk                       (clk),
      .rst_n                     (rst_n),
      .s_axil_awvalid           (sys_axil_awvalid),
      .s_axil_awready           (sys_axil_awready),
      .s_axil_awaddr            (sys_axil_awaddr),
      .s_axil_awprot            (sys_axil_awprot),
      .s_axil_wvalid            (sys_axil_wvalid),
      .s_axil_wready            (sys_axil_wready),
      .s_axil_wdata             (sys_axil_wdata),
      .s_axil_wstrb             (sys_axil_wstrb),
      .s_axil_bvalid            (sys_axil_bvalid),
      .s_axil_bready            (sys_axil_bready),
      .s_axil_bresp             (sys_axil_bresp),
      .s_axil_arvalid           (sys_axil_arvalid),
      .s_axil_arready           (sys_axil_arready),
      .s_axil_araddr            (sys_axil_araddr),
      .s_axil_arprot            (sys_axil_arprot),
      .s_axil_rvalid            (sys_axil_rvalid),
      .s_axil_rready            (sys_axil_rready),
      .s_axil_rdata             (sys_axil_rdata),
      .s_axil_rresp             (sys_axil_rresp),
      // C26 cpu fault_event
      .i_cpu_fault_valid         (cpu_fault_valid),
      .i_cpu_fault_reason        (cpu_fault_reason),
      .i_cpu_fault_addr          (cpu_fault_addr),
      // C27 cpu_bridge fault_event
      .i_cpu_bridge_fault_valid  (cb_fault_valid),
      .i_cpu_bridge_fault_reason (cb_fault_reason),
      .i_cpu_bridge_fault_addr   (cb_fault_addr),
      // C28 fabric fault_event
      .i_fabric_fault_valid      (fab_fault_valid),
      .i_fabric_fault_reason     (fab_fault_reason),
      .i_fabric_fault_addr       (fab_fault_addr),
      // C29 npu_ctl fault_event
      .i_npu_ctl_fault_valid     (ctl_fault_valid),
      .i_npu_ctl_fault_reason    (ctl_fault_reason),
      .i_npu_ctl_fault_addr      (ctl_fault_addr),
      // CR00 / C30..C33 control fan-out
      .o_cpu_local_rst_n         (cpu_local_rst_n),
      .o_stop_new_transactions   (stop_new_transactions),
      // SYS-01 outputs
      .o_fatal                   (o_fatal),
      .o_result_valid            (o_result_valid),
      .o_result_code             (o_result_code)
  );

  irq u_irq (
      .clk              (clk),
      .rst_n            (rst_n),
      .s_axil_awvalid  (irq_axil_awvalid),
      .s_axil_awready  (irq_axil_awready),
      .s_axil_awaddr   (irq_axil_awaddr),
      .s_axil_awprot   (irq_axil_awprot),
      .s_axil_wvalid   (irq_axil_wvalid),
      .s_axil_wready   (irq_axil_wready),
      .s_axil_wdata    (irq_axil_wdata),
      .s_axil_wstrb    (irq_axil_wstrb),
      .s_axil_bvalid   (irq_axil_bvalid),
      .s_axil_bready   (irq_axil_bready),
      .s_axil_bresp    (irq_axil_bresp),
      .s_axil_arvalid  (irq_axil_arvalid),
      .s_axil_arready  (irq_axil_arready),
      .s_axil_araddr   (irq_axil_araddr),
      .s_axil_arprot   (irq_axil_arprot),
      .s_axil_rvalid   (irq_axil_rvalid),
      .s_axil_rready   (irq_axil_rready),
      .s_axil_rdata    (irq_axil_rdata),
      .s_axil_rresp    (irq_axil_rresp),
      // C17/C18/C19 gated level sources
      .i_npu_done_irq   (npu_done_irq),
      .i_npu_error_irq  (npu_error_irq),
      .i_uart_tx_empty  (uart_tx_empty),
      // C20/C21/C22 PicoRV32 custom IRQ bus, bits 4/5/6
      .o_irq            (cpu_irq)
  );

  uart u_uart (
      .clk              (clk),
      .rst_n            (rst_n),
      .s_axil_awvalid  (uart_axil_awvalid),
      .s_axil_awready  (uart_axil_awready),
      .s_axil_awaddr   (uart_axil_awaddr),
      .s_axil_awprot   (uart_axil_awprot),
      .s_axil_wvalid   (uart_axil_wvalid),
      .s_axil_wready   (uart_axil_wready),
      .s_axil_wdata    (uart_axil_wdata),
      .s_axil_wstrb    (uart_axil_wstrb),
      .s_axil_bvalid   (uart_axil_bvalid),
      .s_axil_bready   (uart_axil_bready),
      .s_axil_bresp    (uart_axil_bresp),
      .s_axil_arvalid  (uart_axil_arvalid),
      .s_axil_arready  (uart_axil_arready),
      .s_axil_araddr   (uart_axil_araddr),
      .s_axil_arprot   (uart_axil_arprot),
      .s_axil_rvalid   (uart_axil_rvalid),
      .s_axil_rready   (uart_axil_rready),
      .s_axil_rdata    (uart_axil_rdata),
      .s_axil_rresp    (uart_axil_rresp),
      // SYS-01 serial output and C19 level source
      .o_uart_tx        (o_uart_tx),
      .o_tx_empty       (uart_tx_empty)
  );

  // ==========================================================================
  // NPU
  // ==========================================================================

  npu_csr u_npu_csr (
      .clk                   (clk),
      .rst_n                 (rst_n),
      .s_axil_awvalid       (csr_axil_awvalid),
      .s_axil_awready       (csr_axil_awready),
      .s_axil_awaddr        (csr_axil_awaddr),
      .s_axil_awprot        (csr_axil_awprot),
      .s_axil_wvalid        (csr_axil_wvalid),
      .s_axil_wready        (csr_axil_wready),
      .s_axil_wdata         (csr_axil_wdata),
      .s_axil_wstrb         (csr_axil_wstrb),
      .s_axil_bvalid        (csr_axil_bvalid),
      .s_axil_bready        (csr_axil_bready),
      .s_axil_bresp         (csr_axil_bresp),
      .s_axil_arvalid       (csr_axil_arvalid),
      .s_axil_arready       (csr_axil_arready),
      .s_axil_araddr        (csr_axil_araddr),
      .s_axil_arprot        (csr_axil_arprot),
      .s_axil_rvalid        (csr_axil_rvalid),
      .s_axil_rready        (csr_axil_rready),
      .s_axil_rdata         (csr_axil_rdata),
      .s_axil_rresp         (csr_axil_rresp),
      // C12 dispatch -> npu_ctl
      .o_dispatch_valid      (csr_disp_valid),
      .i_dispatch_ready      (csr_disp_ready),
      .o_dispatch_opcode    (csr_disp_opcode),
      .o_dispatch_x_base    (csr_disp_x_base),
      .o_dispatch_w_base    (csr_disp_w_base),
      .o_dispatch_y_base    (csr_disp_y_base),
      .o_dispatch_k         (csr_disp_k),
      .o_dispatch_n         (csr_disp_n),
      .o_dispatch_group     (csr_disp_group),
      .o_dispatch_w_stride  (csr_disp_w_stride),
      .o_dispatch_tag       (csr_disp_tag),
      // C24 terminal <- npu_ctl
      .i_terminal_valid      (term_valid),
      .o_terminal_ready      (term_ready),
      .i_terminal_tag        (term_tag),
      .i_terminal_error_code (term_error_code),
      .i_terminal_cycles     (term_cycles),
      // C17/C18 irq_level -> irq
      .o_done_irq            (npu_done_irq),
      .o_error_irq           (npu_error_irq)
  );

  npu_ctl u_npu_ctl (
      .clk                     (clk),
      .rst_n                   (rst_n),
      // C12 dispatch <- npu_csr
      .i_dispatch_valid        (csr_disp_valid),
      .o_dispatch_ready        (csr_disp_ready),
      .i_dispatch_opcode      (csr_disp_opcode),
      .i_dispatch_x_base      (csr_disp_x_base),
      .i_dispatch_w_base      (csr_disp_w_base),
      .i_dispatch_y_base      (csr_disp_y_base),
      .i_dispatch_k           (csr_disp_k),
      .i_dispatch_n           (csr_disp_n),
      .i_dispatch_group       (csr_disp_group),
      .i_dispatch_w_stride    (csr_disp_w_stride),
      .i_dispatch_tag         (csr_disp_tag),
      // C13 dispatch -> npu_dma
      .o_dma_dispatch_valid    (dma_disp_valid),
      .i_dma_dispatch_ready    (dma_disp_ready),
      .o_dma_dispatch_opcode  (dma_disp_opcode),
      .o_dma_dispatch_x_base  (dma_disp_x_base),
      .o_dma_dispatch_w_base  (dma_disp_w_base),
      .o_dma_dispatch_y_base  (dma_disp_y_base),
      .o_dma_dispatch_k       (dma_disp_k),
      .o_dma_dispatch_n       (dma_disp_n),
      .o_dma_dispatch_group   (dma_disp_group),
      .o_dma_dispatch_w_stride(dma_disp_w_stride),
      .o_dma_dispatch_tag     (dma_disp_tag),
      // C25 dispatch -> npu_local
      .o_local_dispatch_valid  (loc_disp_valid),
      .i_local_dispatch_ready  (loc_disp_ready),
      .o_local_dispatch_opcode(loc_disp_opcode),
      .o_local_dispatch_x_base(loc_disp_x_base),
      .o_local_dispatch_w_base(loc_disp_w_base),
      .o_local_dispatch_y_base(loc_disp_y_base),
      .o_local_dispatch_k     (loc_disp_k),
      .o_local_dispatch_n     (loc_disp_n),
      .o_local_dispatch_group (loc_disp_group),
      .o_local_dispatch_w_stride(loc_disp_w_stride),
      .o_local_dispatch_tag   (loc_disp_tag),
      // C34 dot_lifecycle -> npu_dot (NPU-09(b) flush level)
      .o_dot_lifecycle_flush   (dotlife_flush),
      // C23 dma_terminal <- npu_dma (registered levels, NPU-09(c))
      .i_dma_done              (dmaterm_done),
      .i_dma_error             (dmaterm_error),
      .i_dma_error_code        (dmaterm_error_code),
      // C24 terminal -> npu_csr
      .o_terminal_valid        (term_valid),
      .i_terminal_ready        (term_ready),
      .o_terminal_tag          (term_tag),
      .o_terminal_error_code   (term_error_code),
      .o_terminal_cycles       (term_cycles),
      // C29 fault_event -> sys (reason 5 watchdog, addr 0)
      .o_fault_valid           (ctl_fault_valid),
      .o_fault_reason          (ctl_fault_reason),
      .o_fault_addr            (ctl_fault_addr),
      // C31 stop_issue <- sys
      .i_stop_new_transactions (stop_new_transactions)
  );

  npu_dma u_npu_dma (
      .clk                       (clk),
      .rst_n                     (rst_n),
      // C13 dispatch <- npu_ctl
      .i_dispatch_valid          (dma_disp_valid),
      .o_dispatch_ready          (dma_disp_ready),
      .i_dispatch_opcode        (dma_disp_opcode),
      .i_dispatch_x_base        (dma_disp_x_base),
      .i_dispatch_w_base        (dma_disp_w_base),
      .i_dispatch_y_base        (dma_disp_y_base),
      .i_dispatch_k             (dma_disp_k),
      .i_dispatch_n             (dma_disp_n),
      .i_dispatch_group         (dma_disp_group),
      .i_dispatch_w_stride      (dma_disp_w_stride),
      .i_dispatch_tag           (dma_disp_tag),
      // C14 local_bytes -> npu_local
      .o_local_bytes_valid       (lbytes_valid),
      .i_local_bytes_ready       (lbytes_ready),
      .o_local_bytes_data        (lbytes_data),
      .o_local_bytes_keep        (lbytes_keep),
      .o_local_bytes_kind        (lbytes_kind),
      .o_local_bytes_index       (lbytes_index),
      .o_local_bytes_row         (lbytes_row),
      // C16 group_result <- npu_dot
      .i_group_result_valid      (gres_valid),
      .o_group_result_ready      (gres_ready),
      .i_group_result_data       (gres_data),
      .i_group_result_row        (gres_row),
      .i_group_result_group_index(gres_group_index),
      .i_group_result_last       (gres_last),
      // C23 dma_terminal -> npu_ctl
      .o_dma_terminal_done       (dmaterm_done),
      .o_dma_terminal_error      (dmaterm_error),
      .o_dma_terminal_error_code (dmaterm_error_code),
      // C32 stop_issue <- sys
      .i_stop_new_transactions   (stop_new_transactions),
      // C03 AXI4 initiator, fixed ID 1
      .m_axi_awvalid            (dma_axi_awvalid),
      .m_axi_awready            (dma_axi_awready),
      .m_axi_awaddr             (dma_axi_awaddr),
      .m_axi_awid               (dma_axi_awid),
      .m_axi_awlen              (dma_axi_awlen),
      .m_axi_awsize             (dma_axi_awsize),
      .m_axi_awburst            (dma_axi_awburst),
      .m_axi_awlock             (dma_axi_awlock),
      .m_axi_awcache            (dma_axi_awcache),
      .m_axi_awprot             (dma_axi_awprot),
      .m_axi_awqos              (dma_axi_awqos),
      .m_axi_wvalid             (dma_axi_wvalid),
      .m_axi_wready             (dma_axi_wready),
      .m_axi_wdata              (dma_axi_wdata),
      .m_axi_wstrb              (dma_axi_wstrb),
      .m_axi_wlast              (dma_axi_wlast),
      .m_axi_bvalid             (dma_axi_bvalid),
      .m_axi_bready             (dma_axi_bready),
      .m_axi_bresp              (dma_axi_bresp),
      .m_axi_bid                (dma_axi_bid),
      .m_axi_arvalid            (dma_axi_arvalid),
      .m_axi_arready            (dma_axi_arready),
      .m_axi_araddr             (dma_axi_araddr),
      .m_axi_arid               (dma_axi_arid),
      .m_axi_arlen              (dma_axi_arlen),
      .m_axi_arsize             (dma_axi_arsize),
      .m_axi_arburst            (dma_axi_arburst),
      .m_axi_arlock             (dma_axi_arlock),
      .m_axi_arcache            (dma_axi_arcache),
      .m_axi_arprot             (dma_axi_arprot),
      .m_axi_arqos              (dma_axi_arqos),
      .m_axi_rvalid             (dma_axi_rvalid),
      .m_axi_rready             (dma_axi_rready),
      .m_axi_rdata              (dma_axi_rdata),
      .m_axi_rresp              (dma_axi_rresp),
      .m_axi_rid                (dma_axi_rid),
      .m_axi_rlast              (dma_axi_rlast)
  );

  npu_local u_npu_local (
      .clk                        (clk),
      .rst_n                      (rst_n),
      // C25 dispatch <- npu_ctl
      .i_dispatch_valid           (loc_disp_valid),
      .o_dispatch_ready           (loc_disp_ready),
      .i_dispatch_opcode         (loc_disp_opcode),
      .i_dispatch_x_base         (loc_disp_x_base),
      .i_dispatch_w_base         (loc_disp_w_base),
      .i_dispatch_y_base         (loc_disp_y_base),
      .i_dispatch_k              (loc_disp_k),
      .i_dispatch_n              (loc_disp_n),
      .i_dispatch_group          (loc_disp_group),
      .i_dispatch_w_stride       (loc_disp_w_stride),
      .i_dispatch_tag            (loc_disp_tag),
      // C14 local_bytes <- npu_dma
      .i_local_bytes_valid        (lbytes_valid),
      .o_local_bytes_ready        (lbytes_ready),
      .i_local_bytes_data         (lbytes_data),
      .i_local_bytes_keep         (lbytes_keep),
      .i_local_bytes_kind         (lbytes_kind),
      .i_local_bytes_index        (lbytes_index),
      .i_local_bytes_row          (lbytes_row),
      // C15 dot_operands -> npu_dot
      .o_dot_operands_valid       (dotop_valid),
      .i_dot_operands_ready       (dotop_ready),
      .o_dot_operands_x_data      (dotop_x_data),
      .o_dot_operands_w_data      (dotop_w_data),
      .o_dot_operands_keep        (dotop_keep),
      .o_dot_operands_group_first (dotop_group_first),
      .o_dot_operands_group_last  (dotop_group_last),
      .o_dot_operands_row         (dotop_row),
      .o_dot_operands_group_index (dotop_group_index),
      .o_dot_operands_command_last(dotop_command_last)
  );

  npu_dot u_npu_dot (
      .clk                        (clk),
      .rst_n                      (rst_n),
      // C15 dot_operands <- npu_local
      .i_dot_operands_valid       (dotop_valid),
      .o_dot_operands_ready       (dotop_ready),
      .i_dot_operands_x_data      (dotop_x_data),
      .i_dot_operands_w_data      (dotop_w_data),
      .i_dot_operands_keep        (dotop_keep),
      .i_dot_operands_group_first (dotop_group_first),
      .i_dot_operands_group_last  (dotop_group_last),
      .i_dot_operands_row         (dotop_row),
      .i_dot_operands_group_index (dotop_group_index),
      .i_dot_operands_command_last(dotop_command_last),
      // C34 dot_lifecycle <- npu_ctl (NPU-09(b) flush level)
      .i_dot_lifecycle_flush      (dotlife_flush),
      // C16 group_result -> npu_dma
      .o_group_result_valid       (gres_valid),
      .i_group_result_ready       (gres_ready),
      .o_group_result_data        (gres_data),
      .o_group_result_row         (gres_row),
      .o_group_result_group_index (gres_group_index),
      .o_group_result_last        (gres_last)
  );

  // ==========================================================================
  // Sinks for delivered outputs that contract.json gives no consumer.
  // cpu.o_eoi (PicoRV32 custom IRQ ABI end-of-interrupt vector) and the
  // ENABLE_TRACE=1 trace port are observed by DV through hierarchical probes,
  // not through a SYS-01 top port. Listed in CONNECTIONS.md as sunk-unused.
  // ==========================================================================
  wire unused_ok;
  assign unused_ok = &{1'b0, unused_cpu_eoi, unused_cpu_trace_valid,
                       unused_cpu_trace_data};

endmodule

`default_nettype wire
