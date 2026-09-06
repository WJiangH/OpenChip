// fabric.sv — AXI4 fabric: static port firewall, serialized dual-channel
// routing and per-obligation progress monitor.
//
// Spec: docs/spec/llm-soc-v1/system.md §2 SYS-04 (region table, physical source
//   identity, DECERR without side effect, burst must fit one authorized
//   region), §4 SYS-12 (sticky fault_event, stop_new_transactions, retained
//   work); axi.md AXI-01 (signal list), AXI-02 (IDs / supported attributes),
//   AXI-03 (VALID stability, AW/W independence, no address inferred from W),
//   AXI-04 (one read + one write live, separate round-robin), AXI-05
//   (permission/attribute validation, exact LEN+1 error beats, drain-then-error),
//   AXI-07 (per-obligation progress counters, threshold 65536, reason 3),
//   AXI-08 (no reordering; response order preserved by construction).
//   contract.json: C02/C03 initiator ports, C04..C07 target ports, C28
//   fault_event->sys, C33 stop_issue<-sys, address_regions.
//
// Target ports follow contract.json connection order:
//   m0 = rom (C04), m1 = sram (C05), m2 = extmem (C06, top-level target-facing
//   interface per SYS-01), m3 = lite_bridge (C07; the four 4 KiB peripheral
//   windows are decoded further inside lite_bridge per AXI-09 / C08..C11).
//
// Early-W policy (AXI-03): this fabric takes the *backpressure* option that
// AXI-03 explicitly permits ("using a one-beat holding register or
// backpressure without deadlock").  WREADY is asserted only to the source that
// owns the retained AW, so no W beat is ever accepted before its AW, no address
// is ever inferred from W, and data from another source can never mix into a
// write.  Deadlock is impossible because both DUT initiators assert AWVALID no
// later than their first WVALID and never wait for AWREADY (AXI-03).  AXI-07
// obligation (e) ("early *accepted* W waiting for its AW") therefore has no
// reachable state; an illegal early W with no AW is still monitored by
// obligation (a) on that source's W channel and times out to reason 3 with
// fault_addr = the offered AW address if one was ever offered, else 0 (SYS-12).
//
// The region table and the progress threshold are localparams bound to the
// spec values; SYS-04 forbids runtime programmability.
`default_nettype none

module fabric (
    input  wire         clk,
    input  wire         rst_n,

    // ---------------- C02: CPU bridge initiator, source ID 0 ---------------
    input  wire         s0_axi_awvalid,
    output logic        s0_axi_awready,
    input  wire  [31:0] s0_axi_awaddr,
    input  wire  [1:0]  s0_axi_awid,
    input  wire  [7:0]  s0_axi_awlen,
    input  wire  [2:0]  s0_axi_awsize,
    input  wire  [1:0]  s0_axi_awburst,
    input  wire         s0_axi_awlock,
    input  wire  [3:0]  s0_axi_awcache,
    input  wire  [2:0]  s0_axi_awprot,
    input  wire  [3:0]  s0_axi_awqos,
    input  wire         s0_axi_wvalid,
    output logic        s0_axi_wready,
    input  wire  [31:0] s0_axi_wdata,
    input  wire  [3:0]  s0_axi_wstrb,
    input  wire         s0_axi_wlast,
    output logic        s0_axi_bvalid,
    input  wire         s0_axi_bready,
    output logic [1:0]  s0_axi_bresp,
    output logic [1:0]  s0_axi_bid,
    input  wire         s0_axi_arvalid,
    output logic        s0_axi_arready,
    input  wire  [31:0] s0_axi_araddr,
    input  wire  [1:0]  s0_axi_arid,
    input  wire  [7:0]  s0_axi_arlen,
    input  wire  [2:0]  s0_axi_arsize,
    input  wire  [1:0]  s0_axi_arburst,
    input  wire         s0_axi_arlock,
    input  wire  [3:0]  s0_axi_arcache,
    input  wire  [2:0]  s0_axi_arprot,
    input  wire  [3:0]  s0_axi_arqos,
    output logic        s0_axi_rvalid,
    input  wire         s0_axi_rready,
    output logic [31:0] s0_axi_rdata,
    output logic [1:0]  s0_axi_rresp,
    output logic [1:0]  s0_axi_rid,
    output logic        s0_axi_rlast,

    // ---------------- C03: NPU DMA initiator, source ID 1 ------------------
    input  wire         s1_axi_awvalid,
    output logic        s1_axi_awready,
    input  wire  [31:0] s1_axi_awaddr,
    input  wire  [1:0]  s1_axi_awid,
    input  wire  [7:0]  s1_axi_awlen,
    input  wire  [2:0]  s1_axi_awsize,
    input  wire  [1:0]  s1_axi_awburst,
    input  wire         s1_axi_awlock,
    input  wire  [3:0]  s1_axi_awcache,
    input  wire  [2:0]  s1_axi_awprot,
    input  wire  [3:0]  s1_axi_awqos,
    input  wire         s1_axi_wvalid,
    output logic        s1_axi_wready,
    input  wire  [31:0] s1_axi_wdata,
    input  wire  [3:0]  s1_axi_wstrb,
    input  wire         s1_axi_wlast,
    output logic        s1_axi_bvalid,
    input  wire         s1_axi_bready,
    output logic [1:0]  s1_axi_bresp,
    output logic [1:0]  s1_axi_bid,
    input  wire         s1_axi_arvalid,
    output logic        s1_axi_arready,
    input  wire  [31:0] s1_axi_araddr,
    input  wire  [1:0]  s1_axi_arid,
    input  wire  [7:0]  s1_axi_arlen,
    input  wire  [2:0]  s1_axi_arsize,
    input  wire  [1:0]  s1_axi_arburst,
    input  wire         s1_axi_arlock,
    input  wire  [3:0]  s1_axi_arcache,
    input  wire  [2:0]  s1_axi_arprot,
    input  wire  [3:0]  s1_axi_arqos,
    output logic        s1_axi_rvalid,
    input  wire         s1_axi_rready,
    output logic [31:0] s1_axi_rdata,
    output logic [1:0]  s1_axi_rresp,
    output logic [1:0]  s1_axi_rid,
    output logic        s1_axi_rlast,

    // ---------------- C04: boot ROM target ---------------------------------
    output logic        m0_axi_awvalid,
    input  wire         m0_axi_awready,
    output logic [31:0] m0_axi_awaddr,
    output logic [1:0]  m0_axi_awid,
    output logic [7:0]  m0_axi_awlen,
    output logic [2:0]  m0_axi_awsize,
    output logic [1:0]  m0_axi_awburst,
    output logic        m0_axi_awlock,
    output logic [3:0]  m0_axi_awcache,
    output logic [2:0]  m0_axi_awprot,
    output logic [3:0]  m0_axi_awqos,
    output logic        m0_axi_wvalid,
    input  wire         m0_axi_wready,
    output logic [31:0] m0_axi_wdata,
    output logic [3:0]  m0_axi_wstrb,
    output logic        m0_axi_wlast,
    input  wire         m0_axi_bvalid,
    output logic        m0_axi_bready,
    input  wire  [1:0]  m0_axi_bresp,
    input  wire  [1:0]  m0_axi_bid,
    output logic        m0_axi_arvalid,
    input  wire         m0_axi_arready,
    output logic [31:0] m0_axi_araddr,
    output logic [1:0]  m0_axi_arid,
    output logic [7:0]  m0_axi_arlen,
    output logic [2:0]  m0_axi_arsize,
    output logic [1:0]  m0_axi_arburst,
    output logic        m0_axi_arlock,
    output logic [3:0]  m0_axi_arcache,
    output logic [2:0]  m0_axi_arprot,
    output logic [3:0]  m0_axi_arqos,
    input  wire         m0_axi_rvalid,
    output logic        m0_axi_rready,
    input  wire  [31:0] m0_axi_rdata,
    input  wire  [1:0]  m0_axi_rresp,
    input  wire  [1:0]  m0_axi_rid,
    input  wire         m0_axi_rlast,

    // ---------------- C05: SRAM target -------------------------------------
    output logic        m1_axi_awvalid,
    input  wire         m1_axi_awready,
    output logic [31:0] m1_axi_awaddr,
    output logic [1:0]  m1_axi_awid,
    output logic [7:0]  m1_axi_awlen,
    output logic [2:0]  m1_axi_awsize,
    output logic [1:0]  m1_axi_awburst,
    output logic        m1_axi_awlock,
    output logic [3:0]  m1_axi_awcache,
    output logic [2:0]  m1_axi_awprot,
    output logic [3:0]  m1_axi_awqos,
    output logic        m1_axi_wvalid,
    input  wire         m1_axi_wready,
    output logic [31:0] m1_axi_wdata,
    output logic [3:0]  m1_axi_wstrb,
    output logic        m1_axi_wlast,
    input  wire         m1_axi_bvalid,
    output logic        m1_axi_bready,
    input  wire  [1:0]  m1_axi_bresp,
    input  wire  [1:0]  m1_axi_bid,
    output logic        m1_axi_arvalid,
    input  wire         m1_axi_arready,
    output logic [31:0] m1_axi_araddr,
    output logic [1:0]  m1_axi_arid,
    output logic [7:0]  m1_axi_arlen,
    output logic [2:0]  m1_axi_arsize,
    output logic [1:0]  m1_axi_arburst,
    output logic        m1_axi_arlock,
    output logic [3:0]  m1_axi_arcache,
    output logic [2:0]  m1_axi_arprot,
    output logic [3:0]  m1_axi_arqos,
    input  wire         m1_axi_rvalid,
    output logic        m1_axi_rready,
    input  wire  [31:0] m1_axi_rdata,
    input  wire  [1:0]  m1_axi_rresp,
    input  wire  [1:0]  m1_axi_rid,
    input  wire         m1_axi_rlast,

    // ------- C06: external memory target (top-level facing, SYS-01) --------
    output logic        m2_axi_awvalid,
    input  wire         m2_axi_awready,
    output logic [31:0] m2_axi_awaddr,
    output logic [1:0]  m2_axi_awid,
    output logic [7:0]  m2_axi_awlen,
    output logic [2:0]  m2_axi_awsize,
    output logic [1:0]  m2_axi_awburst,
    output logic        m2_axi_awlock,
    output logic [3:0]  m2_axi_awcache,
    output logic [2:0]  m2_axi_awprot,
    output logic [3:0]  m2_axi_awqos,
    output logic        m2_axi_wvalid,
    input  wire         m2_axi_wready,
    output logic [31:0] m2_axi_wdata,
    output logic [3:0]  m2_axi_wstrb,
    output logic        m2_axi_wlast,
    input  wire         m2_axi_bvalid,
    output logic        m2_axi_bready,
    input  wire  [1:0]  m2_axi_bresp,
    input  wire  [1:0]  m2_axi_bid,
    output logic        m2_axi_arvalid,
    input  wire         m2_axi_arready,
    output logic [31:0] m2_axi_araddr,
    output logic [1:0]  m2_axi_arid,
    output logic [7:0]  m2_axi_arlen,
    output logic [2:0]  m2_axi_arsize,
    output logic [1:0]  m2_axi_arburst,
    output logic        m2_axi_arlock,
    output logic [3:0]  m2_axi_arcache,
    output logic [2:0]  m2_axi_arprot,
    output logic [3:0]  m2_axi_arqos,
    input  wire         m2_axi_rvalid,
    output logic        m2_axi_rready,
    input  wire  [31:0] m2_axi_rdata,
    input  wire  [1:0]  m2_axi_rresp,
    input  wire  [1:0]  m2_axi_rid,
    input  wire         m2_axi_rlast,

    // ---------------- C07: AXI4-Lite bridge target -------------------------
    output logic        m3_axi_awvalid,
    input  wire         m3_axi_awready,
    output logic [31:0] m3_axi_awaddr,
    output logic [1:0]  m3_axi_awid,
    output logic [7:0]  m3_axi_awlen,
    output logic [2:0]  m3_axi_awsize,
    output logic [1:0]  m3_axi_awburst,
    output logic        m3_axi_awlock,
    output logic [3:0]  m3_axi_awcache,
    output logic [2:0]  m3_axi_awprot,
    output logic [3:0]  m3_axi_awqos,
    output logic        m3_axi_wvalid,
    input  wire         m3_axi_wready,
    output logic [31:0] m3_axi_wdata,
    output logic [3:0]  m3_axi_wstrb,
    output logic        m3_axi_wlast,
    input  wire         m3_axi_bvalid,
    output logic        m3_axi_bready,
    input  wire  [1:0]  m3_axi_bresp,
    input  wire  [1:0]  m3_axi_bid,
    output logic        m3_axi_arvalid,
    input  wire         m3_axi_arready,
    output logic [31:0] m3_axi_araddr,
    output logic [1:0]  m3_axi_arid,
    output logic [7:0]  m3_axi_arlen,
    output logic [2:0]  m3_axi_arsize,
    output logic [1:0]  m3_axi_arburst,
    output logic        m3_axi_arlock,
    output logic [3:0]  m3_axi_arcache,
    output logic [2:0]  m3_axi_arprot,
    output logic [3:0]  m3_axi_arqos,
    input  wire         m3_axi_rvalid,
    output logic        m3_axi_rready,
    input  wire  [31:0] m3_axi_rdata,
    input  wire  [1:0]  m3_axi_rresp,
    input  wire  [1:0]  m3_axi_rid,
    input  wire         m3_axi_rlast,

    // ---------------- C28: fault_event -> sys (SYS-12) ---------------------
    output logic        o_fault_valid,
    output logic [2:0]  o_fault_reason,
    output logic [31:0] o_fault_addr,

    // ---------------- C33: stop_issue <- sys (SYS-12) ----------------------
    input  wire         i_stop_new_transactions
);

  // =====================================================================
  // Constants (SYS-04 forbids runtime programmability: all localparam)
  // =====================================================================
  // AXI response codes.
  localparam logic [1:0] RESP_OKAY   = 2'b00;
  localparam logic [1:0] RESP_SLVERR = 2'b10;
  localparam logic [1:0] RESP_DECERR = 2'b11;

  // Target port index (contract.json C04..C07 order).
  localparam logic [1:0] T_ROM  = 2'd0;
  localparam logic [1:0] T_SRAM = 2'd1;
  localparam logic [1:0] T_EXT  = 2'd2;
  localparam logic [1:0] T_LITE = 2'd3;

  // Permission bits {X,W,R} (system.md §2 CPU / NPU columns).
  localparam logic [2:0] P_NONE = 3'b000;
  localparam logic [2:0] P_R    = 3'b001;
  localparam logic [2:0] P_W    = 3'b010;
  localparam logic [2:0] P_X    = 3'b100;
  localparam logic [2:0] P_RW   = P_R | P_W;
  localparam logic [2:0] P_RX   = P_R | P_X;
  localparam logic [2:0] P_RWX  = P_R | P_W | P_X;

  // Region table — system.md §2 / contract.json address_regions.  Base/size
  // pairs are byte addresses with half-open ranges.
  localparam logic [31:0] BASE_ROM      = 32'h0000_0000;  // immutable boot ROM
  localparam logic [31:0] SIZE_ROM      = 32'h0001_0000;  //  65536
  localparam logic [31:0] BASE_SRAM     = 32'h1000_0000;  // firmware SRAM
  localparam logic [31:0] SIZE_SRAM     = 32'h0004_0000;  // 262144
  localparam logic [31:0] BASE_SYSREG   = 32'h4000_0000;  // system registers
  localparam logic [31:0] SIZE_SYSREG   = 32'h0000_1000;  //   4096
  localparam logic [31:0] BASE_NPUCSR   = 32'h4000_1000;  // NPU registers
  localparam logic [31:0] SIZE_NPUCSR   = 32'h0000_1000;
  localparam logic [31:0] BASE_IRQREG   = 32'h4000_2000;  // IRQ registers
  localparam logic [31:0] SIZE_IRQREG   = 32'h0000_1000;
  localparam logic [31:0] BASE_UARTREG  = 32'h4000_3000;  // UART registers
  localparam logic [31:0] SIZE_UARTREG  = 32'h0000_1000;
  localparam logic [31:0] BASE_SECRSV   = 32'h4001_0000;  // reserved S1 mailbox
  localparam logic [31:0] SIZE_SECRSV   = 32'h0001_0000;  //  65536, deny/deny
  localparam logic [31:0] BASE_BOOTIMG  = 32'h8000_0000;  // boot image + pad
  localparam logic [31:0] SIZE_BOOTIMG  = 32'h0010_0000;  // 1048576
  localparam logic [31:0] BASE_MODEL    = 32'h8010_0000;  // model immutable
  localparam logic [31:0] SIZE_MODEL    = 32'h0040_0000;  // 4194304
  localparam logic [31:0] BASE_KV       = 32'h8050_0000;  // KV arena
  localparam logic [31:0] SIZE_KV       = 32'h0010_0000;
  localparam logic [31:0] BASE_SCRATCH  = 32'h8060_0000;  // NPU scratch
  localparam logic [31:0] SIZE_SCRATCH  = 32'h0010_0000;
  localparam logic [31:0] BASE_EXPECTED = 32'h8070_0000;  // expected checkpoint
  localparam logic [31:0] SIZE_EXPECTED = 32'h0010_0000;
  localparam logic [31:0] BASE_IO       = 32'h8080_0000;  // token in / result
  localparam logic [31:0] SIZE_IO       = 32'h0001_0000;  //  65536
  localparam logic [31:0] BASE_EXTRSV   = 32'h8081_0000;  // reserved backing
  localparam logic [31:0] SIZE_EXTRSV   = 32'h007F_0000;  // 8323072, deny/deny

  // AXI-07 progress threshold.  cnt holds the number of consecutive rising
  // edges without matching progress since the obligation was created; the
  // fatal edge is the one that would make it reach PROGRESS_TIMEOUT.
  localparam int unsigned PROGRESS_TIMEOUT = 65536;
  localparam int unsigned CNT_W            = $clog2(PROGRESS_TIMEOUT);
  localparam logic [CNT_W-1:0] CNT_LAST    = CNT_W'(PROGRESS_TIMEOUT - 1);

  // Supported transaction attributes (AXI-02).
  localparam logic [2:0] AXSIZE_4B  = 3'd2;
  localparam logic [1:0] AXBURST_IN = 2'b01;
  localparam logic [7:0] AXLEN_MAX  = 8'd15;

  // Fault reasons (SYS-07 / SYS-12).
  localparam logic [2:0] REASON_PROGRESS = 3'd3;
  localparam logic [2:0] REASON_PROTOCOL = 3'd6;

  // =====================================================================
  // Region lookup
  // =====================================================================
  function automatic logic in_region(input logic [31:0] a,
                                     input logic [31:0] base,
                                     input logic [31:0] size);
    in_region = (a >= base) && ((a - base) < size);
  endfunction

  // A burst must fit a single authorized region (SYS-04).  last is the
  // inclusive last byte address in 33 bits so a 32-bit wrap cannot alias.
  function automatic logic fits_region(input logic [32:0] last,
                                       input logic [31:0] base,
                                       input logic [31:0] size);
    fits_region = ((last - {1'b0, base}) < {1'b0, size});
  endfunction

  // Returns {ok, tgt[1:0]}.  ok = mapped AND the whole burst inside that one
  // region AND the physical source port holds every needed permission bit.
  // Anything else is DECERR without side effect (SYS-04).
  function automatic logic [2:0] region_lookup(input logic [31:0] a,
                                               input logic [32:0] last,
                                               input logic        npu,
                                               input logic [2:0]  need);
    logic        hit;
    logic [1:0]  tgt;
    logic [2:0]  perm;
    logic        fit;
    begin
      hit  = 1'b1;
      tgt  = T_EXT;
      perm = P_NONE;
      fit  = 1'b0;
      if (in_region(a, BASE_ROM, SIZE_ROM)) begin
        tgt = T_ROM;  perm = npu ? P_NONE : P_RX;
        fit = fits_region(last, BASE_ROM, SIZE_ROM);
      end else if (in_region(a, BASE_SRAM, SIZE_SRAM)) begin
        tgt = T_SRAM; perm = npu ? P_NONE : P_RWX;
        fit = fits_region(last, BASE_SRAM, SIZE_SRAM);
      end else if (in_region(a, BASE_SYSREG, SIZE_SYSREG)) begin
        tgt = T_LITE; perm = npu ? P_NONE : P_RW;
        fit = fits_region(last, BASE_SYSREG, SIZE_SYSREG);
      end else if (in_region(a, BASE_NPUCSR, SIZE_NPUCSR)) begin
        tgt = T_LITE; perm = npu ? P_NONE : P_RW;
        fit = fits_region(last, BASE_NPUCSR, SIZE_NPUCSR);
      end else if (in_region(a, BASE_IRQREG, SIZE_IRQREG)) begin
        tgt = T_LITE; perm = npu ? P_NONE : P_RW;
        fit = fits_region(last, BASE_IRQREG, SIZE_IRQREG);
      end else if (in_region(a, BASE_UARTREG, SIZE_UARTREG)) begin
        tgt = T_LITE; perm = npu ? P_NONE : P_RW;
        fit = fits_region(last, BASE_UARTREG, SIZE_UARTREG);
      end else if (in_region(a, BASE_SECRSV, SIZE_SECRSV)) begin
        tgt = T_LITE; perm = P_NONE;  // S1 mailbox aperture: deny in SIM-L1
        fit = fits_region(last, BASE_SECRSV, SIZE_SECRSV);
      end else if (in_region(a, BASE_BOOTIMG, SIZE_BOOTIMG)) begin
        tgt = T_EXT;  perm = npu ? P_NONE : P_R;
        fit = fits_region(last, BASE_BOOTIMG, SIZE_BOOTIMG);
      end else if (in_region(a, BASE_MODEL, SIZE_MODEL)) begin
        tgt = T_EXT;  perm = P_R;   // model: CPU R and NPU R
        fit = fits_region(last, BASE_MODEL, SIZE_MODEL);
      end else if (in_region(a, BASE_KV, SIZE_KV)) begin
        tgt = T_EXT;  perm = npu ? P_NONE : P_RW;
        fit = fits_region(last, BASE_KV, SIZE_KV);
      end else if (in_region(a, BASE_SCRATCH, SIZE_SCRATCH)) begin
        tgt = T_EXT;  perm = P_RW;  // scratch: CPU R/W and NPU R/W
        fit = fits_region(last, BASE_SCRATCH, SIZE_SCRATCH);
      end else if (in_region(a, BASE_EXPECTED, SIZE_EXPECTED)) begin
        tgt = T_EXT;  perm = npu ? P_NONE : P_R;
        fit = fits_region(last, BASE_EXPECTED, SIZE_EXPECTED);
      end else if (in_region(a, BASE_IO, SIZE_IO)) begin
        tgt = T_EXT;  perm = npu ? P_NONE : P_RW;
        fit = fits_region(last, BASE_IO, SIZE_IO);
      end else if (in_region(a, BASE_EXTRSV, SIZE_EXTRSV)) begin
        tgt = T_EXT;  perm = P_NONE;  // reserved external backing: deny/deny
        fit = fits_region(last, BASE_EXTRSV, SIZE_EXTRSV);
      end else begin
        hit = 1'b0;                    // unmapped
      end
      region_lookup = {hit && fit && ((perm & need) == need), tgt};
    end
  endfunction

  // =====================================================================
  // Port vectors: index 0 = CPU bridge (ID 0), index 1 = NPU DMA (ID 1);
  // target index per T_* above.  Request payload is broadcast to every target
  // port and only VALID/READY are steered, so no transaction can reach a
  // target it was not decoded to.
  // =====================================================================
  logic [1:0]       s_awvalid, s_wvalid, s_wlast, s_arvalid, s_bready, s_rready;
  logic [1:0]       s_awlock, s_arlock;
  logic [1:0][31:0] s_awaddr, s_araddr, s_wdata;
  logic [1:0][1:0]  s_awid, s_arid, s_awburst, s_arburst;
  logic [1:0][7:0]  s_awlen, s_arlen;
  logic [1:0][2:0]  s_awsize, s_arsize, s_awprot, s_arprot;
  logic [1:0][3:0]  s_awcache, s_arcache, s_awqos, s_arqos, s_wstrb;

  assign s_awvalid = {s1_axi_awvalid, s0_axi_awvalid};
  assign s_awaddr  = {s1_axi_awaddr,  s0_axi_awaddr};
  assign s_awid    = {s1_axi_awid,    s0_axi_awid};
  assign s_awlen   = {s1_axi_awlen,   s0_axi_awlen};
  assign s_awsize  = {s1_axi_awsize,  s0_axi_awsize};
  assign s_awburst = {s1_axi_awburst, s0_axi_awburst};
  assign s_awlock  = {s1_axi_awlock,  s0_axi_awlock};
  assign s_awcache = {s1_axi_awcache, s0_axi_awcache};
  assign s_awprot  = {s1_axi_awprot,  s0_axi_awprot};
  assign s_awqos   = {s1_axi_awqos,   s0_axi_awqos};
  assign s_wvalid  = {s1_axi_wvalid,  s0_axi_wvalid};
  assign s_wdata   = {s1_axi_wdata,   s0_axi_wdata};
  assign s_wstrb   = {s1_axi_wstrb,   s0_axi_wstrb};
  assign s_wlast   = {s1_axi_wlast,   s0_axi_wlast};
  assign s_bready  = {s1_axi_bready,  s0_axi_bready};
  assign s_arvalid = {s1_axi_arvalid, s0_axi_arvalid};
  assign s_araddr  = {s1_axi_araddr,  s0_axi_araddr};
  assign s_arid    = {s1_axi_arid,    s0_axi_arid};
  assign s_arlen   = {s1_axi_arlen,   s0_axi_arlen};
  assign s_arsize  = {s1_axi_arsize,  s0_axi_arsize};
  assign s_arburst = {s1_axi_arburst, s0_axi_arburst};
  assign s_arlock  = {s1_axi_arlock,  s0_axi_arlock};
  assign s_arcache = {s1_axi_arcache, s0_axi_arcache};
  assign s_arprot  = {s1_axi_arprot,  s0_axi_arprot};
  assign s_arqos   = {s1_axi_arqos,   s0_axi_arqos};
  assign s_rready  = {s1_axi_rready,  s0_axi_rready};

  logic [3:0]       m_awready, m_wready, m_bvalid, m_arready, m_rvalid, m_rlast;
  logic [3:0][1:0]  m_bresp, m_bid, m_rresp, m_rid;
  logic [3:0][31:0] m_rdata;

  assign m_awready = {m3_axi_awready, m2_axi_awready, m1_axi_awready, m0_axi_awready};
  assign m_wready  = {m3_axi_wready,  m2_axi_wready,  m1_axi_wready,  m0_axi_wready};
  assign m_bvalid  = {m3_axi_bvalid,  m2_axi_bvalid,  m1_axi_bvalid,  m0_axi_bvalid};
  assign m_bresp   = {m3_axi_bresp,   m2_axi_bresp,   m1_axi_bresp,   m0_axi_bresp};
  assign m_bid     = {m3_axi_bid,     m2_axi_bid,     m1_axi_bid,     m0_axi_bid};
  assign m_arready = {m3_axi_arready, m2_axi_arready, m1_axi_arready, m0_axi_arready};
  assign m_rvalid  = {m3_axi_rvalid,  m2_axi_rvalid,  m1_axi_rvalid,  m0_axi_rvalid};
  assign m_rdata   = {m3_axi_rdata,   m2_axi_rdata,   m1_axi_rdata,   m0_axi_rdata};
  assign m_rresp   = {m3_axi_rresp,   m2_axi_rresp,   m1_axi_rresp,   m0_axi_rresp};
  assign m_rid     = {m3_axi_rid,     m2_axi_rid,     m1_axi_rid,     m0_axi_rid};
  assign m_rlast   = {m3_axi_rlast,   m2_axi_rlast,   m1_axi_rlast,   m0_axi_rlast};

  logic [1:0]  s_awready, s_wready, s_bvalid, s_arready, s_rvalid;
  logic [3:0]  m_awvalid, m_wvalid, m_bready, m_arvalid, m_rready;

  // =====================================================================
  // Fatal state (SYS-12): sticky, common reset only.  A fatal detected by the
  // fabric itself blocks new transactions from the same edge, exactly like the
  // sticky stop input; retained work keeps draining.
  // =====================================================================
  logic        fault_valid_q;
  logic [2:0]  fault_reason_q;
  logic [31:0] fault_addr_q;
  logic        timeout_hit;   // any AXI-07 obligation reaches the threshold
  logic        proto_hit;     // any burst-format violation (AXI-03/AXI-05)
  logic        block_new;

  // New transactions are blocked by the sticky stop input, by a fatal already
  // captured here, and combinationally by a protocol violation detected on
  // this edge.  ISSUE-fabric-05: provisional — a progress timeout is
  // deliberately *not* in this term, because AXI-07 requires a matching
  // handshake on the threshold edge to win and arbitration therefore must not
  // depend on this cycle's timeout decision; fault_valid_q blocks every later
  // edge, so at most the one transaction accepted on the detection edge itself
  // joins the retained drain set.
  assign block_new = i_stop_new_transactions | fault_valid_q | proto_hit;

  assign o_fault_valid  = fault_valid_q;
  assign o_fault_reason = fault_reason_q;
  assign o_fault_addr   = fault_addr_q;

  // =====================================================================
  // Write channel: state, arbitration, firewall decode
  // =====================================================================
  localparam logic [2:0] WS_IDLE  = 3'd0;  // arbitrate + accept one AW
  localparam logic [2:0] WS_AW    = 3'd1;  // offer AW to the decoded target
  localparam logic [2:0] WS_DATA  = 3'd2;  // relay exactly LEN+1 W beats
  localparam logic [2:0] WS_RESP  = 3'd3;  // relay target B to the owner
  localparam logic [2:0] WS_DRAIN = 3'd4;  // rejected: drain LEN+1 W beats
  localparam logic [2:0] WS_ERRB  = 3'd5;  // rejected: one error B

  logic [2:0]  wr_state;
  logic        wr_rr;        // round-robin priority holder for AW
  logic        wr_owner;     // source that owns the live write
  logic [31:0] wr_addr;
  logic [1:0]  wr_id;
  logic [7:0]  wr_len;
  logic [1:0]  wr_tgt;
  logic [1:0]  wr_err;
  logic [7:0]  wr_beat;      // W beats already accepted

  logic        wr_live;
  assign wr_live = (wr_state != WS_IDLE);

  logic        wr_gsrc, wr_gnt;
  logic [32:0] aw_last;
  logic        aw_ok, aw_attr_bad;
  logic [1:0]  aw_tgt, aw_err;
  logic [2:0]  aw_lookup;

  always_comb begin
    // Fair round-robin at transaction boundaries; the pointer advances on a
    // completed grant (AXI-04).
    if (s_awvalid[0] && s_awvalid[1]) wr_gsrc = wr_rr;
    else                              wr_gsrc = s_awvalid[1];
    wr_gnt = (wr_state == WS_IDLE) && !block_new && (s_awvalid[0] | s_awvalid[1]);
  end

  assign aw_last   = {1'b0, s_awaddr[wr_gsrc]} + {23'd0, s_awlen[wr_gsrc], 2'b00} + 33'd3;
  assign aw_lookup = region_lookup(s_awaddr[wr_gsrc], aw_last, wr_gsrc, P_W);
  assign aw_ok     = aw_lookup[2];
  assign aw_tgt    = aw_lookup[1:0];

  // AXI-02 supported attributes; source identity is the physical port, so an
  // AWID that is not this port's fixed ID is an unsupported attribute.
  assign aw_attr_bad = (s_awsize[wr_gsrc]  != AXSIZE_4B)
                     | (s_awburst[wr_gsrc] != AXBURST_IN)
                     | (s_awlen[wr_gsrc]   >  AXLEN_MAX)
                     |  s_awlock[wr_gsrc]
                     | (s_awcache[wr_gsrc] != 4'd0)
                     | (s_awqos[wr_gsrc]   != 4'd0)
                     | (s_awprot[wr_gsrc]  != 3'b000)
                     | (s_awaddr[wr_gsrc][1:0] != 2'b00)
                     | (s_awid[wr_gsrc]    != {1'b0, wr_gsrc})
                     |  aw_last[32]
                     | (aw_last[31:12] != s_awaddr[wr_gsrc][31:12]);

  // ISSUE-fabric-01: provisional — SYS-04 states unconditionally that an
  // unmapped/unauthorized access returns DECERR, so mapping/permission is
  // reported ahead of the AXI-05 unsupported-attribute SLVERR when both apply.
  assign aw_err = !aw_ok      ? RESP_DECERR :
                  aw_attr_bad ? RESP_SLVERR : RESP_OKAY;

  // =====================================================================
  // Read channel: state, arbitration, firewall decode
  // =====================================================================
  localparam logic [1:0] RS_IDLE = 2'd0;
  localparam logic [1:0] RS_AR   = 2'd1;
  localparam logic [1:0] RS_DATA = 2'd2;
  localparam logic [1:0] RS_ERR  = 2'd3;  // exactly LEN+1 zero-data error beats

  logic [1:0]  rd_state;
  logic        rd_rr;
  logic        rd_owner;
  logic [31:0] rd_addr;
  logic [1:0]  rd_id;
  logic [7:0]  rd_len;
  logic [1:0]  rd_tgt;
  logic [1:0]  rd_err;
  logic [7:0]  rd_beat;

  logic        rd_live;
  assign rd_live = (rd_state != RS_IDLE);

  logic        rd_gsrc, rd_gnt;
  logic [32:0] ar_last;
  logic        ar_ok, ar_attr_bad;
  logic [1:0]  ar_tgt, ar_err;
  logic [2:0]  ar_lookup, ar_need;

  always_comb begin
    if (s_arvalid[0] && s_arvalid[1]) rd_gsrc = rd_rr;
    else                              rd_gsrc = s_arvalid[1];
    rd_gnt = (rd_state == RS_IDLE) && !block_new && (s_arvalid[0] | s_arvalid[1]);
  end

  // AXI-05: a CPU read with ARPROT[2]=1 is an instruction fetch and needs X;
  // every other legal read needs R.  Identity stays physical port identity.
  assign ar_need   = (!rd_gsrc && s_arprot[rd_gsrc][2]) ? P_X : P_R;
  assign ar_last   = {1'b0, s_araddr[rd_gsrc]} + {23'd0, s_arlen[rd_gsrc], 2'b00} + 33'd3;
  assign ar_lookup = region_lookup(s_araddr[rd_gsrc], ar_last, rd_gsrc, ar_need);
  assign ar_ok     = ar_lookup[2];
  assign ar_tgt    = ar_lookup[1:0];

  // Only CPU ARPROT 0/4 is legal; NPU ARPROT must be 0 (PROT4 rejected).
  assign ar_attr_bad = (s_arsize[rd_gsrc]  != AXSIZE_4B)
                     | (s_arburst[rd_gsrc] != AXBURST_IN)
                     | (s_arlen[rd_gsrc]   >  AXLEN_MAX)
                     |  s_arlock[rd_gsrc]
                     | (s_arcache[rd_gsrc] != 4'd0)
                     | (s_arqos[rd_gsrc]   != 4'd0)
                     | (rd_gsrc ? (s_arprot[rd_gsrc]      != 3'b000)
                                : (s_arprot[rd_gsrc][1:0] != 2'b00))
                     | (s_araddr[rd_gsrc][1:0] != 2'b00)
                     | (s_arid[rd_gsrc]    != {1'b0, rd_gsrc})
                     |  ar_last[32]
                     | (ar_last[31:12] != s_araddr[rd_gsrc][31:12]);

  // ISSUE-fabric-01: provisional — same DECERR-before-SLVERR ordering.
  assign ar_err = !ar_ok      ? RESP_DECERR :
                  ar_attr_bad ? RESP_SLVERR : RESP_OKAY;

  // =====================================================================
  // Write datapath (independent of the read datapath, AXI-04)
  // =====================================================================
  logic        wr_src_wvalid, wr_src_wlast;
  logic [31:0] wr_src_wdata;
  logic [3:0]  wr_src_wstrb;
  logic [2:0]  wr_prot;
  logic        w_hs, b_hs, aw_fwd_hs, w_last_exp, wlast_bad;
  logic [1:0]  b_resp_o, b_id_o;

  assign wr_src_wvalid = s_wvalid[wr_owner];
  assign wr_src_wlast  = s_wlast[wr_owner];
  assign wr_src_wdata  = s_wdata[wr_owner];
  assign wr_src_wstrb  = s_wstrb[wr_owner];
  assign w_last_exp    = (wr_beat == wr_len);

  always_comb begin
    s_awready = 2'b00;
    s_wready  = 2'b00;
    s_bvalid  = 2'b00;
    m_awvalid = 4'b0000;
    m_wvalid  = 4'b0000;
    m_bready  = 4'b0000;
    b_resp_o  = wr_err;
    b_id_o    = wr_id;

    if (wr_gnt) s_awready[wr_gsrc] = 1'b1;

    case (wr_state)
      WS_AW: begin
        m_awvalid[wr_tgt] = 1'b1;
      end
      WS_DATA: begin
        // W follows the retained AW owner only; another source cannot mix in.
        s_wready[wr_owner] = m_wready[wr_tgt];
        m_wvalid[wr_tgt]   = wr_src_wvalid;
      end
      WS_RESP: begin
        s_bvalid[wr_owner] = m_bvalid[wr_tgt];
        m_bready[wr_tgt]   = s_bready[wr_owner];
        b_resp_o           = m_bresp[wr_tgt];
        b_id_o             = m_bid[wr_tgt];
      end
      WS_DRAIN: begin
        // AXI-05: a rejected write drains exactly LEN+1 W beats and touches
        // no target; B is only reported after the drain.
        s_wready[wr_owner] = 1'b1;
      end
      WS_ERRB: begin
        s_bvalid[wr_owner] = 1'b1;
      end
      default: ;  // WS_IDLE
    endcase
  end

  assign w_hs      = wr_src_wvalid & s_wready[wr_owner];
  assign b_hs      = s_bvalid[wr_owner] & s_bready[wr_owner];
  assign aw_fwd_hs = (wr_state == WS_AW) & m_awready[wr_tgt];
  // AXI-03: exactly LEN+1 W beats with correct WLAST; anything else is an
  // illegal initiator sequence, latched as a protocol fatal (SYS-07 reason 6).
  assign wlast_bad = w_hs & (wr_src_wlast != w_last_exp);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      wr_state <= WS_IDLE;
      wr_rr    <= 1'b0;
      wr_owner <= 1'b0;
      wr_addr  <= 32'h0;
      wr_id    <= 2'b00;
      wr_len   <= 8'h00;
      wr_tgt   <= T_ROM;
      wr_err   <= RESP_OKAY;
      wr_beat  <= 8'h00;
      wr_prot  <= 3'b000;
    end else begin
      case (wr_state)
        WS_IDLE: begin
          if (wr_gnt) begin
            wr_owner <= wr_gsrc;
            wr_addr  <= s_awaddr[wr_gsrc];
            wr_id    <= s_awid[wr_gsrc];
            wr_len   <= s_awlen[wr_gsrc];
            wr_prot  <= s_awprot[wr_gsrc];
            wr_tgt   <= aw_tgt;
            wr_err   <= aw_err;
            wr_beat  <= 8'h00;
            wr_state <= (aw_err == RESP_OKAY) ? WS_AW : WS_DRAIN;
          end
        end
        WS_AW: begin
          if (aw_fwd_hs) wr_state <= WS_DATA;
        end
        WS_DATA: begin
          if (w_hs) begin
            wr_beat <= wr_beat + 8'd1;
            if (w_last_exp) wr_state <= WS_RESP;
          end
        end
        WS_RESP: begin
          if (b_hs) begin
            wr_state <= WS_IDLE;
            wr_rr    <= ~wr_owner;   // completed grant advances priority
          end
        end
        WS_DRAIN: begin
          if (w_hs) begin
            wr_beat <= wr_beat + 8'd1;
            if (w_last_exp) wr_state <= WS_ERRB;
          end
        end
        WS_ERRB: begin
          if (b_hs) begin
            wr_state <= WS_IDLE;
            wr_rr    <= ~wr_owner;
          end
        end
        default: wr_state <= WS_IDLE;
      endcase
    end
  end

  // =====================================================================
  // Read datapath
  // =====================================================================
  logic        r_hs, ar_fwd_hs, r_last_exp, rlast_bad;
  logic [31:0] r_data_o;
  logic [1:0]  r_resp_o, r_id_o;
  logic [2:0]  rd_prot;

  assign r_last_exp = (rd_beat == rd_len);

  always_comb begin
    s_arready = 2'b00;
    s_rvalid  = 2'b00;
    m_arvalid = 4'b0000;
    m_rready  = 4'b0000;
    r_data_o  = 32'h0;
    r_resp_o  = rd_err;
    r_id_o    = rd_id;

    if (rd_gnt) s_arready[rd_gsrc] = 1'b1;

    case (rd_state)
      RS_AR: begin
        m_arvalid[rd_tgt] = 1'b1;
      end
      RS_DATA: begin
        s_rvalid[rd_owner] = m_rvalid[rd_tgt];
        m_rready[rd_tgt]   = s_rready[rd_owner];
        r_data_o           = m_rdata[rd_tgt];
        r_resp_o           = m_rresp[rd_tgt];
        r_id_o             = m_rid[rd_tgt];
      end
      RS_ERR: begin
        // AXI-05: a rejected read returns zero data for exactly LEN+1 beats.
        s_rvalid[rd_owner] = 1'b1;
      end
      default: ;  // RS_IDLE
    endcase
  end

  assign r_hs      = s_rvalid[rd_owner] & s_rready[rd_owner];
  assign ar_fwd_hs = (rd_state == RS_AR) & m_arready[rd_tgt];
  // A target that mis-marks the final beat is a burst-format violation
  // (AXI-05); the beat count presented to the initiator stays well formed.
  assign rlast_bad = (rd_state == RS_DATA) & r_hs & (m_rlast[rd_tgt] != r_last_exp);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      rd_state <= RS_IDLE;
      rd_rr    <= 1'b0;
      rd_owner <= 1'b0;
      rd_addr  <= 32'h0;
      rd_id    <= 2'b00;
      rd_len   <= 8'h00;
      rd_tgt   <= T_ROM;
      rd_err   <= RESP_OKAY;
      rd_beat  <= 8'h00;
      rd_prot  <= 3'b000;
    end else begin
      case (rd_state)
        RS_IDLE: begin
          if (rd_gnt) begin
            rd_owner <= rd_gsrc;
            rd_addr  <= s_araddr[rd_gsrc];
            rd_id    <= s_arid[rd_gsrc];
            rd_len   <= s_arlen[rd_gsrc];
            rd_prot  <= s_arprot[rd_gsrc];
            rd_tgt   <= ar_tgt;
            rd_err   <= ar_err;
            rd_beat  <= 8'h00;
            rd_state <= (ar_err == RESP_OKAY) ? RS_AR : RS_ERR;
          end
        end
        RS_AR: begin
          if (ar_fwd_hs) rd_state <= RS_DATA;
        end
        RS_DATA, RS_ERR: begin
          if (r_hs) begin
            rd_beat <= rd_beat + 8'd1;
            if (r_last_exp) begin
              rd_state <= RS_IDLE;
              rd_rr    <= ~rd_owner;
            end
          end
        end
        default: rd_state <= RS_IDLE;
      endcase
    end
  end

  // =====================================================================
  // Port output drive.  Request payload is broadcast; only VALID/READY steer.
  // SIZE/BURST/LOCK/CACHE/QOS are the single legal AXI-02 encoding because a
  // transaction with any other encoding is never forwarded; PROT is passed
  // through because ARPROT[2] carries the CPU instruction-fetch identity.
  // =====================================================================
  assign s0_axi_awready = s_awready[0];
  assign s1_axi_awready = s_awready[1];
  assign s0_axi_wready  = s_wready[0];
  assign s1_axi_wready  = s_wready[1];
  assign s0_axi_bvalid  = s_bvalid[0];
  assign s1_axi_bvalid  = s_bvalid[1];
  assign s0_axi_bresp   = b_resp_o;
  assign s1_axi_bresp   = b_resp_o;
  assign s0_axi_bid     = b_id_o;
  assign s1_axi_bid     = b_id_o;
  assign s0_axi_arready = s_arready[0];
  assign s1_axi_arready = s_arready[1];
  assign s0_axi_rvalid  = s_rvalid[0];
  assign s1_axi_rvalid  = s_rvalid[1];
  assign s0_axi_rdata   = r_data_o;
  assign s1_axi_rdata   = r_data_o;
  assign s0_axi_rresp   = r_resp_o;
  assign s1_axi_rresp   = r_resp_o;
  assign s0_axi_rid     = r_id_o;
  assign s1_axi_rid     = r_id_o;
  assign s0_axi_rlast   = r_last_exp;
  assign s1_axi_rlast   = r_last_exp;

  assign m0_axi_awvalid = m_awvalid[0];
  assign m1_axi_awvalid = m_awvalid[1];
  assign m2_axi_awvalid = m_awvalid[2];
  assign m3_axi_awvalid = m_awvalid[3];
  assign m0_axi_wvalid  = m_wvalid[0];
  assign m1_axi_wvalid  = m_wvalid[1];
  assign m2_axi_wvalid  = m_wvalid[2];
  assign m3_axi_wvalid  = m_wvalid[3];
  assign m0_axi_bready  = m_bready[0];
  assign m1_axi_bready  = m_bready[1];
  assign m2_axi_bready  = m_bready[2];
  assign m3_axi_bready  = m_bready[3];
  assign m0_axi_arvalid = m_arvalid[0];
  assign m1_axi_arvalid = m_arvalid[1];
  assign m2_axi_arvalid = m_arvalid[2];
  assign m3_axi_arvalid = m_arvalid[3];
  assign m0_axi_rready  = m_rready[0];
  assign m1_axi_rready  = m_rready[1];
  assign m2_axi_rready  = m_rready[2];
  assign m3_axi_rready  = m_rready[3];

  assign m0_axi_awaddr  = wr_addr;
  assign m1_axi_awaddr  = wr_addr;
  assign m2_axi_awaddr  = wr_addr;
  assign m3_axi_awaddr  = wr_addr;
  assign m0_axi_awid    = wr_id;
  assign m1_axi_awid    = wr_id;
  assign m2_axi_awid    = wr_id;
  assign m3_axi_awid    = wr_id;
  assign m0_axi_awlen   = wr_len;
  assign m1_axi_awlen   = wr_len;
  assign m2_axi_awlen   = wr_len;
  assign m3_axi_awlen   = wr_len;
  assign m0_axi_awprot  = wr_prot;
  assign m1_axi_awprot  = wr_prot;
  assign m2_axi_awprot  = wr_prot;
  assign m3_axi_awprot  = wr_prot;
  assign m0_axi_awsize  = AXSIZE_4B;
  assign m1_axi_awsize  = AXSIZE_4B;
  assign m2_axi_awsize  = AXSIZE_4B;
  assign m3_axi_awsize  = AXSIZE_4B;
  assign m0_axi_awburst = AXBURST_IN;
  assign m1_axi_awburst = AXBURST_IN;
  assign m2_axi_awburst = AXBURST_IN;
  assign m3_axi_awburst = AXBURST_IN;
  assign m0_axi_awlock  = 1'b0;
  assign m1_axi_awlock  = 1'b0;
  assign m2_axi_awlock  = 1'b0;
  assign m3_axi_awlock  = 1'b0;
  assign m0_axi_awcache = 4'h0;
  assign m1_axi_awcache = 4'h0;
  assign m2_axi_awcache = 4'h0;
  assign m3_axi_awcache = 4'h0;
  assign m0_axi_awqos   = 4'h0;
  assign m1_axi_awqos   = 4'h0;
  assign m2_axi_awqos   = 4'h0;
  assign m3_axi_awqos   = 4'h0;

  assign m0_axi_wdata   = wr_src_wdata;
  assign m1_axi_wdata   = wr_src_wdata;
  assign m2_axi_wdata   = wr_src_wdata;
  assign m3_axi_wdata   = wr_src_wdata;
  assign m0_axi_wstrb   = wr_src_wstrb;
  assign m1_axi_wstrb   = wr_src_wstrb;
  assign m2_axi_wstrb   = wr_src_wstrb;
  assign m3_axi_wstrb   = wr_src_wstrb;
  assign m0_axi_wlast   = w_last_exp;
  assign m1_axi_wlast   = w_last_exp;
  assign m2_axi_wlast   = w_last_exp;
  assign m3_axi_wlast   = w_last_exp;

  assign m0_axi_araddr  = rd_addr;
  assign m1_axi_araddr  = rd_addr;
  assign m2_axi_araddr  = rd_addr;
  assign m3_axi_araddr  = rd_addr;
  assign m0_axi_arid    = rd_id;
  assign m1_axi_arid    = rd_id;
  assign m2_axi_arid    = rd_id;
  assign m3_axi_arid    = rd_id;
  assign m0_axi_arlen   = rd_len;
  assign m1_axi_arlen   = rd_len;
  assign m2_axi_arlen   = rd_len;
  assign m3_axi_arlen   = rd_len;
  assign m0_axi_arprot  = rd_prot;
  assign m1_axi_arprot  = rd_prot;
  assign m2_axi_arprot  = rd_prot;
  assign m3_axi_arprot  = rd_prot;
  assign m0_axi_arsize  = AXSIZE_4B;
  assign m1_axi_arsize  = AXSIZE_4B;
  assign m2_axi_arsize  = AXSIZE_4B;
  assign m3_axi_arsize  = AXSIZE_4B;
  assign m0_axi_arburst = AXBURST_IN;
  assign m1_axi_arburst = AXBURST_IN;
  assign m2_axi_arburst = AXBURST_IN;
  assign m3_axi_arburst = AXBURST_IN;
  assign m0_axi_arlock  = 1'b0;
  assign m1_axi_arlock  = 1'b0;
  assign m2_axi_arlock  = 1'b0;
  assign m3_axi_arlock  = 1'b0;
  assign m0_axi_arcache = 4'h0;
  assign m1_axi_arcache = 4'h0;
  assign m2_axi_arcache = 4'h0;
  assign m3_axi_arcache = 4'h0;
  assign m0_axi_arqos   = 4'h0;
  assign m1_axi_arqos   = 4'h0;
  assign m2_axi_arqos   = 4'h0;
  assign m3_axi_arqos   = 4'h0;

  // =====================================================================
  // AXI-07 progress monitor
  //
  // One independent counter per obligation.  Every counter is cleared while
  // its obligation does not exist and by a matching handshake only, so an
  // unrelated source/channel handshake can never hide a stalled obligation.
  // Obligations implemented:
  //   (a) every offered VALID waiting for its corresponding READY — one per
  //       channel per port, on both the initiator side and the target side;
  //   (b) accepted AR waiting for the first/next R beat, until RLAST;
  //   (c) accepted AW waiting for the first/next W beat, until expected WLAST;
  //   (d) final W accepted waiting for its B, active only once AW is accepted;
  //   (e) early accepted W waiting for its AW — unreachable here, see the
  //       early-W policy note in the file header; obligation (a) on that
  //       source's W channel covers the illegal sequence.
  // A W beat already accepted before its obligation would be created is not
  // awaited twice: (c)/(d) are derived from the accepted-beat count.
  // =====================================================================
  localparam int unsigned OB_SAW   = 0;   // +port
  localparam int unsigned OB_SW    = 2;   // +port
  localparam int unsigned OB_SB    = 4;   // +port
  localparam int unsigned OB_SAR   = 6;   // +port
  localparam int unsigned OB_SR    = 8;   // +port
  localparam int unsigned OB_MAW   = 10;  // +target
  localparam int unsigned OB_MW    = 14;  // +target
  localparam int unsigned OB_MB    = 18;  // +target
  localparam int unsigned OB_MAR   = 22;  // +target
  localparam int unsigned OB_MR    = 26;  // +target
  localparam int unsigned OB_RDATA = 30;  // (b)
  localparam int unsigned OB_WBEAT = 31;  // (c)
  localparam int unsigned OB_WRESP = 32;  // (d)
  localparam int unsigned NOB      = 33;

  // Obligations 0..OB_RDATA-1 are the (a) "offered VALID waiting for READY"
  // family: their existence is visible in the same cycle as the offer, so the
  // edge that first samples the offer is their creating edge and must load 0.
  // The transaction obligations (b)..(d) are derived from state that already
  // changed on their creating edge, so their counter is already 0 there.
  localparam logic [NOB-1:0] OFFER_MASK = (33'd1 << OB_RDATA) - 33'd1;

  logic [NOB-1:0]            ob_active, ob_active_q, ob_prog, ob_start, ob_timeout;
  logic [NOB-1:0][CNT_W-1:0] ob_cnt;

  always_comb begin
    ob_active = '0;
    ob_prog   = '0;
    for (int unsigned p = 0; p < 2; p++) begin
      ob_active[OB_SAW + p] = s_awvalid[p];
      ob_prog  [OB_SAW + p] = s_awvalid[p] & s_awready[p];
      ob_active[OB_SW  + p] = s_wvalid[p];
      ob_prog  [OB_SW  + p] = s_wvalid[p] & s_wready[p];
      ob_active[OB_SB  + p] = s_bvalid[p];
      ob_prog  [OB_SB  + p] = s_bvalid[p] & s_bready[p];
      ob_active[OB_SAR + p] = s_arvalid[p];
      ob_prog  [OB_SAR + p] = s_arvalid[p] & s_arready[p];
      ob_active[OB_SR  + p] = s_rvalid[p];
      ob_prog  [OB_SR  + p] = s_rvalid[p] & s_rready[p];
    end
    for (int unsigned t = 0; t < 4; t++) begin
      ob_active[OB_MAW + t] = m_awvalid[t];
      ob_prog  [OB_MAW + t] = m_awvalid[t] & m_awready[t];
      ob_active[OB_MW  + t] = m_wvalid[t];
      ob_prog  [OB_MW  + t] = m_wvalid[t] & m_wready[t];
      ob_active[OB_MB  + t] = m_bvalid[t];
      ob_prog  [OB_MB  + t] = m_bvalid[t] & m_bready[t];
      ob_active[OB_MAR + t] = m_arvalid[t];
      ob_prog  [OB_MAR + t] = m_arvalid[t] & m_arready[t];
      ob_active[OB_MR  + t] = m_rvalid[t];
      ob_prog  [OB_MR  + t] = m_rvalid[t] & m_rready[t];
    end
    // (b) accepted AR owes LEN+1 R beats to its initiator.
    ob_active[OB_RDATA] = (rd_state == RS_AR) | (rd_state == RS_DATA) | (rd_state == RS_ERR);
    ob_prog  [OB_RDATA] = r_hs;
    // (c) accepted AW owes exactly LEN+1 W beats from its own initiator.
    ob_active[OB_WBEAT] = (wr_state == WS_AW) | (wr_state == WS_DATA) | (wr_state == WS_DRAIN);
    ob_prog  [OB_WBEAT] = w_hs;
    // (d) final W accepted, AW accepted, waiting for the matching B.
    ob_active[OB_WRESP] = (wr_state == WS_RESP) | (wr_state == WS_ERRB);
    ob_prog  [OB_WRESP] = b_hs;
  end

  assign ob_start = OFFER_MASK & ob_active & ~ob_active_q;

  always_ff @(posedge clk) begin
    if (!rst_n) ob_active_q <= '0;
    else        ob_active_q <= ob_active;
  end

  generate
    for (genvar gi = 0; gi < int'(NOB); gi++) begin : g_progress_cnt
      always_ff @(posedge clk) begin
        if (!rst_n) begin
          ob_cnt[gi] <= '0;
        end else if (!ob_active[gi] || ob_prog[gi] || ob_start[gi]) begin
          // Obligation absent, created on this edge (initialised to 0), or a
          // matching handshake — a handshake on the threshold edge wins and
          // clears/restarts the counter.
          ob_cnt[gi] <= '0;
        end else begin
          ob_cnt[gi] <= ob_cnt[gi] + {{(CNT_W-1){1'b0}}, 1'b1};
        end
      end
      // The next edge would make this counter reach PROGRESS_TIMEOUT.
      assign ob_timeout[gi] = ob_active[gi] & ~ob_prog[gi] & ~ob_start[gi]
                            & (ob_cnt[gi] == CNT_LAST);
    end
  endgenerate

  // =====================================================================
  // Fault selection (SYS-12): simultaneous events take the lowest reason
  // (progress 3 before protocol 6); within the fabric, source ID 0 before 1,
  // then channel order AW, W, B, AR, R.  Target-side and transaction
  // obligations are attributed to the owning source and its channel.
  // =====================================================================
  logic [1:0] to_aw, to_w, to_b, to_ar, to_r;
  logic [1:0] wr_own_oh, rd_own_oh;
  logic [1:0][31:0] wr_known_addr, rd_known_addr;

  // Owner of the live transaction, one-hot.  ISSUE-fabric-04: provisional —
  // a target-side VALID with no live transaction (a spurious response) has no
  // owner in SYS-12's tie-break rule; it is attributed to the lowest source ID
  // so that the timeout is still reported instead of silently dropped.
  assign wr_own_oh = (wr_live && wr_owner) ? 2'b10 : 2'b01;
  assign rd_own_oh = (rd_live && rd_owner) ? 2'b10 : 2'b01;

  always_comb begin
    for (int unsigned p = 0; p < 2; p++) begin
      // The aligned start address retained from the accepted AW/AR of this
      // source, else from an address it is currently offering, else 0 when no
      // matching address was ever offered (SYS-12).
      if (wr_live && (wr_owner == p[0])) wr_known_addr[p] = {wr_addr[31:2], 2'b00};
      else if (s_awvalid[p])             wr_known_addr[p] = {s_awaddr[p][31:2], 2'b00};
      else                               wr_known_addr[p] = 32'h0;

      if (rd_live && (rd_owner == p[0])) rd_known_addr[p] = {rd_addr[31:2], 2'b00};
      else if (s_arvalid[p])             rd_known_addr[p] = {s_araddr[p][31:2], 2'b00};
      else                               rd_known_addr[p] = 32'h0;
    end
  end

  assign to_aw = ob_timeout[OB_SAW+:2]
               | ({2{|ob_timeout[OB_MAW+:4]}} & wr_own_oh);
  assign to_w  = ob_timeout[OB_SW +:2]
               | ({2{(|ob_timeout[OB_MW+:4]) | ob_timeout[OB_WBEAT]}} & wr_own_oh);
  assign to_b  = ob_timeout[OB_SB +:2]
               | ({2{(|ob_timeout[OB_MB+:4]) | ob_timeout[OB_WRESP]}} & wr_own_oh);
  assign to_ar = ob_timeout[OB_SAR+:2]
               | ({2{|ob_timeout[OB_MAR+:4]}} & rd_own_oh);
  assign to_r  = ob_timeout[OB_SR +:2]
               | ({2{(|ob_timeout[OB_MR+:4]) | ob_timeout[OB_RDATA]}} & rd_own_oh);

  logic [31:0] timeout_addr, proto_addr;

  always_comb begin
    timeout_hit  = 1'b1;
    timeout_addr = 32'h0;
    if      (to_aw[0]) timeout_addr = wr_known_addr[0];
    else if (to_w [0]) timeout_addr = wr_known_addr[0];
    else if (to_b [0]) timeout_addr = wr_known_addr[0];
    else if (to_ar[0]) timeout_addr = rd_known_addr[0];
    else if (to_r [0]) timeout_addr = rd_known_addr[0];
    else if (to_aw[1]) timeout_addr = wr_known_addr[1];
    else if (to_w [1]) timeout_addr = wr_known_addr[1];
    else if (to_b [1]) timeout_addr = wr_known_addr[1];
    else if (to_ar[1]) timeout_addr = rd_known_addr[1];
    else if (to_r [1]) timeout_addr = rd_known_addr[1];
    else               timeout_hit  = 1'b0;
  end

  always_comb begin
    proto_hit  = wlast_bad | rlast_bad;
    proto_addr = 32'h0;
    if      (wlast_bad) proto_addr = wr_known_addr[wr_owner];
    else if (rlast_bad) proto_addr = rd_known_addr[rd_owner];
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      fault_valid_q  <= 1'b0;
      fault_reason_q <= 3'd0;
      fault_addr_q   <= 32'h0;
    end else if (!fault_valid_q) begin
      if (timeout_hit) begin
        fault_valid_q  <= 1'b1;
        fault_reason_q <= REASON_PROGRESS;
        fault_addr_q   <= timeout_addr;
      end else if (proto_hit) begin
        fault_valid_q  <= 1'b1;
        fault_reason_q <= REASON_PROTOCOL;
        fault_addr_q   <= proto_addr;
      end
    end
  end

endmodule

`default_nettype wire
