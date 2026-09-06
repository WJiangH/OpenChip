// sys.sv — system registers at 0x40000000 (llm-soc-v1, ADR-0004).
// Spec: docs/spec/llm-soc-v1/system.md SYS-01,03,07,08,09,12; axi.md AXI-09;
// contract.json csr_registers block "sys", connections C08,C26-C29,C30-C33,CR00.
//
// AXI4-Lite target (single outstanding read + single outstanding write, no
// ID/LEN/SIZE/BURST/LAST per AXI-09). Fault-event fan-in from the four
// SYS-12 producers (cpu:reason4, cpu_bridge:reason1/2, fabric:reason3/6,
// npu_ctl:reason5); earliest-edge-wins, lowest-numeric-reason tie-break,
// sticky until common reset. Free-running 64-bit cycle counter (SYS-09).
// Drives cpu_local_rst_n (SYS-12: rst_n & boot_delay_done & !FATAL) and a
// single broadcast stop_new_transactions net (fanned out at integration to
// cpu_bridge/npu_ctl/npu_dma/fabric per C30-C33 — one field, four sinks).
//
// rc4 (CHANGE_ORDER_rc4.md F-05/F-07, ISSUE-sys-01): RESULT_COMMIT (the only
// WO command register in this block) accepts exactly the written word value
// 1; any other value, including 0, returns SLVERR with no state change. A
// repeat RESULT_COMMIT write of 1 while o_result_valid=1 also returns
// SLVERR, no state change. BOOT_STAGE write above 4 returns SLVERR, no
// state change. See hw/rtl/sys/ISSUES.md for the ruling record.
`default_nettype none

module sys (
    input wire clk,
    input wire rst_n,

    // AXI4-Lite target (C08: lite_bridge -> sys)
    input  wire        s_axil_awvalid,
    output logic       s_axil_awready,
    input  wire [31:0] s_axil_awaddr,
    input  wire [ 2:0] s_axil_awprot,
    input  wire        s_axil_wvalid,
    output logic       s_axil_wready,
    input  wire [31:0] s_axil_wdata,
    input  wire [ 3:0] s_axil_wstrb,
    output logic        s_axil_bvalid,
    input  wire        s_axil_bready,
    output logic [1:0] s_axil_bresp,
    input  wire        s_axil_arvalid,
    output logic       s_axil_arready,
    input  wire [31:0] s_axil_araddr,
    input  wire [ 2:0] s_axil_arprot,
    output logic        s_axil_rvalid,
    input  wire        s_axil_rready,
    output logic [31:0] s_axil_rdata,
    output logic [ 1:0] s_axil_rresp,

    // SYS-12 fault_event fan-in (sticky until common reset; no READY)
    input wire        i_cpu_fault_valid,        // C26: reason4, addr always 0
    input wire [ 2:0] i_cpu_fault_reason,
    input wire [31:0] i_cpu_fault_addr,

    input wire        i_cpu_bridge_fault_valid,  // C27: reason1/2
    input wire [ 2:0] i_cpu_bridge_fault_reason,
    input wire [31:0] i_cpu_bridge_fault_addr,

    input wire        i_fabric_fault_valid,      // C28: reason3/6
    input wire [ 2:0] i_fabric_fault_reason,
    input wire [31:0] i_fabric_fault_addr,

    input wire        i_npu_ctl_fault_valid,     // C29: reason5, addr always 0
    input wire [ 2:0] i_npu_ctl_fault_reason,
    input wire [31:0] i_npu_ctl_fault_addr,

    // SYS-12 control fan-out
    output logic o_cpu_local_rst_n,        // CR00: to cpu block
    output logic o_stop_new_transactions,  // C30-C33: to cpu_bridge, npu_ctl, npu_dma, fabric

    // Top-level outputs (SYS-01)
    output logic        o_fatal,
    output logic        o_result_valid,
    output logic [31:0] o_result_code
);

  // -------------------------------------------------------------------
  // Register offsets (block "sys", contract.json csr_registers)
  // -------------------------------------------------------------------
  localparam logic [11:0] OFF_ID            = 12'h000;
  localparam logic [11:0] OFF_VERSION       = 12'h004;
  localparam logic [11:0] OFF_BOOT_STAGE    = 12'h008;
  localparam logic [11:0] OFF_FATAL         = 12'h00c;
  localparam logic [11:0] OFF_FAULT_ADDR    = 12'h010;
  localparam logic [11:0] OFF_RESULT_CODE   = 12'h014;
  localparam logic [11:0] OFF_RESULT_COMMIT = 12'h018;
  localparam logic [11:0] OFF_CYCLE_LO      = 12'h01c;
  localparam logic [11:0] OFF_CYCLE_HI      = 12'h020;
  localparam logic [11:0] OFF_BUILD_CONFIG  = 12'h024;

  // AWPROT/ARPROT are firewall inputs consumed upstream in fabric (SYS-04);
  // this target never inspects permission bits. Sink to keep lint clean.
  wire unused_awprot = |s_axil_awprot;
  wire unused_arprot = |s_axil_arprot;
  // Only the low 12 bits (in-window offset) are decoded; lite_bridge
  // (AXI-09) guarantees the upper bits already select this target.
  wire unused_awaddr_hi = |s_axil_awaddr[31:12];
  wire unused_araddr_hi = |s_axil_araddr[31:12];

  // -------------------------------------------------------------------
  // SYS-12 fault-event arbitration: earliest edge wins, lowest numeric
  // reason breaks a same-edge tie. Reason domains are disjoint per source
  // (cpu=4, cpu_bridge=1|2, fabric=3|6, npu_ctl=5) so a plain per-source
  // min reduces to picking the currently valid source with smallest reason.
  // -------------------------------------------------------------------
  localparam logic [2:0] REASON_NONE = 3'd7;  // sentinel: no defined reason uses 7

  wire [2:0] r_cpu    = i_cpu_fault_valid        ? i_cpu_fault_reason        : REASON_NONE;
  wire [2:0] r_bridge = i_cpu_bridge_fault_valid  ? i_cpu_bridge_fault_reason : REASON_NONE;
  wire [2:0] r_fabric = i_fabric_fault_valid      ? i_fabric_fault_reason     : REASON_NONE;
  wire [2:0] r_npu    = i_npu_ctl_fault_valid     ? i_npu_ctl_fault_reason    : REASON_NONE;

  logic [2:0] min01, min23, min_all;
  logic       sel_valid;
  logic [31:0] sel_addr;

  always_comb begin
    min01     = (r_cpu <= r_bridge) ? r_cpu : r_bridge;
    min23     = (r_fabric <= r_npu) ? r_fabric : r_npu;
    min_all   = (min01 <= min23) ? min01 : min23;
    sel_valid = i_cpu_fault_valid | i_cpu_bridge_fault_valid | i_fabric_fault_valid | i_npu_ctl_fault_valid;
    case (min_all)
      3'd1, 3'd2: sel_addr = i_cpu_bridge_fault_addr;
      3'd3, 3'd6: sel_addr = i_fabric_fault_addr;
      3'd4:       sel_addr = i_cpu_fault_addr;
      3'd5:       sel_addr = i_npu_ctl_fault_addr;
      default:    sel_addr = 32'd0;
    endcase
  end

  logic       fatal_q;
  logic [2:0] reason_q;
  logic [31:0] addr_q;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      fatal_q  <= 1'b0;
      reason_q <= 3'd0;
      addr_q   <= 32'd0;
    end else if (!fatal_q && sel_valid) begin
      fatal_q  <= 1'b1;
      reason_q <= min_all;
      addr_q   <= sel_addr;
    end
  end

  assign o_fatal                 = fatal_q;
  assign o_stop_new_transactions = fatal_q;  // asserted the same edge fatal_q sets (SYS-12)

  // -------------------------------------------------------------------
  // SYS-01: reset stays asserted 4 extra rising edges after common release;
  // SYS-12: cpu_local_rst_n = rst_n & boot_delay_done & !FATAL.
  // -------------------------------------------------------------------
  localparam int BOOT_DELAY_CYCLES = 4;
  logic [2:0] boot_cnt;
  logic       boot_delay_done;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      boot_cnt <= 3'd0;
    end else if (!boot_delay_done) begin
      boot_cnt <= boot_cnt + 3'd1;
    end
  end

  assign boot_delay_done  = (boot_cnt >= 3'(BOOT_DELAY_CYCLES));
  assign o_cpu_local_rst_n = rst_n & boot_delay_done & !fatal_q;

  // -------------------------------------------------------------------
  // SYS-09: free-running 64-bit cycle counter, wraps mod 2^64, increments
  // every clk after common reset release regardless of fatal/CPU state.
  // -------------------------------------------------------------------
  logic [63:0] cycle_counter;
  logic [31:0] cyc_hi_shadow;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      cycle_counter <= 64'd0;
    end else begin
      cycle_counter <= cycle_counter + 64'd1;
    end
  end

  // -------------------------------------------------------------------
  // Register storage
  // -------------------------------------------------------------------
  logic [31:0] boot_stage_r;
  logic [31:0] result_code_r;
  logic        result_valid_r;
  logic [31:0] result_code_latched;

  assign o_result_valid = result_valid_r;
  assign o_result_code  = result_code_latched;

  // -------------------------------------------------------------------
  // AXI4-Lite write channel — single outstanding AW/W pair, independent
  // AW/W buffering (AXI-03/AXI-09), one write side effect per pair.
  // -------------------------------------------------------------------
  logic        aw_v_q;
  logic [11:0] awaddr_off_q;
  logic        w_v_q;
  logic [31:0] wdata_q;
  logic [ 3:0] wstrb_q;
  logic        bvalid_r;
  logic [ 1:0] bresp_r;

  wire aw_hs = s_axil_awvalid && s_axil_awready;
  wire w_hs  = s_axil_wvalid && s_axil_wready;

  assign s_axil_awready = !aw_v_q && !bvalid_r;
  assign s_axil_wready  = !w_v_q && !bvalid_r;

  wire aw_present = aw_v_q || aw_hs;
  wire w_present  = w_v_q || w_hs;

  wire [11:0] waddr_off = aw_v_q ? awaddr_off_q : s_axil_awaddr[11:0];
  wire [31:0] cur_wdata = w_v_q ? wdata_q : s_axil_wdata;
  wire [ 3:0] cur_wstrb = w_v_q ? wstrb_q : s_axil_wstrb;

  wire do_write = aw_present && w_present && !bvalid_r;

  logic wr_slverr;
  always_comb begin
    if (waddr_off[1:0] != 2'b00 || cur_wstrb != 4'hf) begin
      wr_slverr = 1'b1;
    end else begin
      case (waddr_off)
        // rc4/F-07 (ISSUE-uart-01 sibling ruling): BOOT_STAGE write above 4
        // returns SLVERR, no state change (system.md SYS-08 / BOOT_STAGE row).
        OFF_BOOT_STAGE:  wr_slverr = (cur_wdata > 32'd4);
        OFF_RESULT_CODE: wr_slverr = 1'b0;
        // rc4/F-05 (ISSUE-sys-01 confirmed): a WO command register accepts
        // exactly the written word value 1; any other word, including 0,
        // returns SLVERR with no effect (system.md SYS-08). A repeat commit
        // (cur_wdata==1 while result_valid_r is already 1) is separately
        // SLVERR per the RESULT_COMMIT row / ISSUE-sys-01.
        OFF_RESULT_COMMIT: wr_slverr = (cur_wdata != 32'd1) || result_valid_r;
        default: wr_slverr = 1'b1;  // RO registers and unmapped offsets (SYS-08)
      endcase
    end
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      aw_v_q               <= 1'b0;
      awaddr_off_q         <= 12'd0;
      w_v_q                <= 1'b0;
      wdata_q              <= 32'd0;
      wstrb_q              <= 4'd0;
      bvalid_r             <= 1'b0;
      bresp_r              <= 2'b00;
      boot_stage_r         <= 32'd0;
      result_code_r        <= 32'd0;
      result_valid_r       <= 1'b0;
      result_code_latched  <= 32'd0;
    end else begin
      if (bvalid_r && s_axil_bready) begin
        bvalid_r <= 1'b0;
      end

      if (do_write) begin
        bvalid_r <= 1'b1;
        bresp_r  <= wr_slverr ? 2'b10 : 2'b00;
        aw_v_q   <= 1'b0;
        w_v_q    <= 1'b0;
        if (!wr_slverr) begin
          case (waddr_off)
            OFF_BOOT_STAGE:  boot_stage_r  <= cur_wdata;
            OFF_RESULT_CODE: result_code_r <= cur_wdata;
            OFF_RESULT_COMMIT: begin
              // wr_slverr already guarantees cur_wdata==1 and
              // !result_valid_r whenever this branch is reached.
              result_valid_r      <= 1'b1;
              result_code_latched <= result_code_r;
            end
            default: ;  // unreachable when !wr_slverr
          endcase
        end
      end else begin
        if (aw_hs && !w_present) begin
          aw_v_q       <= 1'b1;
          awaddr_off_q <= s_axil_awaddr[11:0];
        end
        if (w_hs && !aw_present) begin
          w_v_q   <= 1'b1;
          wdata_q <= s_axil_wdata;
          wstrb_q <= s_axil_wstrb;
        end
      end
    end
  end

  assign s_axil_bvalid = bvalid_r;
  assign s_axil_bresp  = bresp_r;

  // -------------------------------------------------------------------
  // AXI4-Lite read channel — single outstanding AR, registered response.
  // CYCLE_LO read side effect: latch the coherent high half (SYS §3).
  // -------------------------------------------------------------------
  logic        rvalid_r;
  logic [31:0] rdata_r;
  logic [ 1:0] rresp_r;

  assign s_axil_arready = !rvalid_r;
  wire ar_hs = s_axil_arvalid && s_axil_arready;
  wire [11:0] raddr_off = s_axil_araddr[11:0];

  logic        rd_slverr;
  logic [31:0] rdata_mux;
  always_comb begin
    if (raddr_off[1:0] != 2'b00) begin
      rd_slverr = 1'b1;
      rdata_mux = 32'd0;
    end else begin
      rd_slverr = 1'b0;
      case (raddr_off)
        OFF_ID:            rdata_mux = 32'h4c4c_4d31;
        OFF_VERSION:       rdata_mux = 32'h0001_0000;
        OFF_BOOT_STAGE:    rdata_mux = boot_stage_r;
        OFF_FATAL:         rdata_mux = {16'd0, 5'd0, reason_q, 7'd0, fatal_q};
        OFF_FAULT_ADDR:    rdata_mux = addr_q;
        OFF_RESULT_CODE:   rdata_mux = result_code_r;
        OFF_RESULT_COMMIT: rdata_mux = 32'd0;
        OFF_CYCLE_LO:      rdata_mux = cycle_counter[31:0];
        OFF_CYCLE_HI:      rdata_mux = cyc_hi_shadow;
        OFF_BUILD_CONFIG:  rdata_mux = 32'd1;
        default: begin
          rdata_mux = 32'd0;
          rd_slverr = 1'b1;  // unmapped offset (SYS-08)
        end
      endcase
    end
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      rvalid_r      <= 1'b0;
      rdata_r       <= 32'd0;
      rresp_r       <= 2'b00;
      cyc_hi_shadow <= 32'd0;
    end else begin
      if (rvalid_r && s_axil_rready) begin
        rvalid_r <= 1'b0;
      end
      if (ar_hs) begin
        rvalid_r <= 1'b1;
        rdata_r  <= rdata_mux;
        rresp_r  <= rd_slverr ? 2'b10 : 2'b00;
        if (!rd_slverr && raddr_off == OFF_CYCLE_LO) begin
          cyc_hi_shadow <= cycle_counter[63:32];
        end
      end
    end
  end

  assign s_axil_rvalid = rvalid_r;
  assign s_axil_rdata  = rdata_r;
  assign s_axil_rresp  = rresp_r;

endmodule

`default_nettype wire
