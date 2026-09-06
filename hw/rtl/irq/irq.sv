// irq.sv — IRQ registers at 0x40002000 (llm-soc-v1, ADR-0004).
// Spec: docs/spec/llm-soc-v1/system.md SYS-08 (CSR semantics), SYS §3 IRQ
// equation; contract.json csr_registers block "irq", irqs[], connections
// C10 (lite_bridge->irq), C17/C18 (npu_csr->irq, already IRQ_ENABLE-gated
// done_irq/error_irq), C19 (uart->irq, raw tx_empty), C20-C22 (irq->cpu).
//
// PENDING is live-derived, not a stored register (contract.json
// derived_live=true): bit0/1 are the already-gated NPU done_irq/error_irq
// levels, bit2 is the raw ungated UART tx_empty level. ACTIVE = PENDING &
// this block's own ENABLE. The custom PicoRV32 irq[31:0] bus carries ACTIVE
// on bits 4/5/6 (spec-assigned); bits 0..2 are reserved for the core's own
// use and are not driven here; all other bits are zero.
`default_nettype none

module irq (
    input wire clk,
    input wire rst_n,

    // AXI4-Lite target (C10: lite_bridge -> irq)
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

    // Level sources (contract.json connections C17/C18/C19)
    input wire i_npu_done_irq,   // C17: NPU.STATUS.DONE & NPU.IRQ_ENABLE.done
    input wire i_npu_error_irq,  // C18: NPU.STATUS.ERROR & NPU.IRQ_ENABLE.error
    input wire i_uart_tx_empty,  // C19: raw UART READY level (ungated)

    // Custom PicoRV32 IRQ bus (bits4/5/6 driven; 0..2 core-owned; rest zero)
    output logic [31:0] o_irq
);

  // -------------------------------------------------------------------
  // Register offsets (block "irq", contract.json csr_registers)
  // -------------------------------------------------------------------
  localparam logic [11:0] OFF_PENDING = 12'h000;
  localparam logic [11:0] OFF_ENABLE  = 12'h004;
  localparam logic [11:0] OFF_ACTIVE  = 12'h008;

  wire unused_awprot = |s_axil_awprot;
  wire unused_arprot = |s_axil_arprot;
  // Only the low 12 bits (in-window offset) are decoded; lite_bridge
  // (AXI-09) guarantees the upper bits already select this target.
  wire unused_awaddr_hi = |s_axil_awaddr[31:12];
  wire unused_araddr_hi = |s_axil_araddr[31:12];

  // -------------------------------------------------------------------
  // PENDING (live-derived, RO) and ACTIVE (=PENDING & ENABLE, RO)
  // -------------------------------------------------------------------
  logic [2:0] enable_r;

  wire [2:0] pending = {i_uart_tx_empty, i_npu_error_irq, i_npu_done_irq};
  wire [2:0] active  = pending & enable_r;

  assign o_irq = {25'd0, active[2], active[1], active[0], 4'd0};

  // -------------------------------------------------------------------
  // AXI4-Lite write channel
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
        OFF_ENABLE: wr_slverr = (cur_wdata[31:3] != 29'd0);
        default:    wr_slverr = 1'b1;  // PENDING/ACTIVE (RO) and unmapped offsets (SYS-08)
      endcase
    end
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      aw_v_q       <= 1'b0;
      awaddr_off_q <= 12'd0;
      w_v_q        <= 1'b0;
      wdata_q      <= 32'd0;
      wstrb_q      <= 4'd0;
      bvalid_r     <= 1'b0;
      bresp_r      <= 2'b00;
      enable_r     <= 3'd0;
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
            OFF_ENABLE: enable_r <= cur_wdata[2:0];
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
  // AXI4-Lite read channel
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
        OFF_PENDING: rdata_mux = {29'd0, pending};
        OFF_ENABLE:  rdata_mux = {29'd0, enable_r};
        OFF_ACTIVE:  rdata_mux = {29'd0, active};
        default: begin
          rdata_mux = 32'd0;
          rd_slverr = 1'b1;  // unmapped offset (SYS-08)
        end
      endcase
    end
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      rvalid_r <= 1'b0;
      rdata_r  <= 32'd0;
      rresp_r  <= 2'b00;
    end else begin
      if (rvalid_r && s_axil_rready) begin
        rvalid_r <= 1'b0;
      end
      if (ar_hs) begin
        rvalid_r <= 1'b1;
        rdata_r  <= rdata_mux;
        rresp_r  <= rd_slverr ? 2'b10 : 2'b00;
      end
    end
  end

  assign s_axil_rvalid = rvalid_r;
  assign s_axil_rdata  = rdata_r;
  assign s_axil_rresp  = rresp_r;

endmodule

`default_nettype wire
