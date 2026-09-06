// uart.sv — UART TX-only registers at 0x40003000 (llm-soc-v1, ADR-0004).
// Spec: docs/spec/llm-soc-v1/system.md SYS-01, SYS-08, SYS-11, SYS §3 UART
// table; contract.json csr_registers block "uart", connection C11
// (lite_bridge->uart), C19 (uart->irq, tx_empty=READY).
//
// One-byte holding slot + a DIVISOR-clocked start/8-data-LSB-first/stop
// shifter. READY=1 when the holding slot is empty; TX_DATA while not ready
// returns SLVERR (never silently dropped). DIVISOR writes reject while
// BUSY. Idle line level is 1. No RX, no FIFO deeper than one, no baud
// tolerance modeling (SYS-11).
//
// rc4 (CHANGE_ORDER_rc4.md F-07, ISSUE-uart-01 ruled reject): a DIVISOR
// write whose 16-bit field value is below 2 additionally returns SLVERR, no
// state change (the "legal 2..65535" range is hardware-enforced, not just
// documentation). See hw/rtl/uart/ISSUES.md for the ruling record.
`default_nettype none

module uart (
    input wire clk,
    input wire rst_n,

    // AXI4-Lite target (C11: lite_bridge -> uart)
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

    // Serial output (SYS-01)
    output logic o_uart_tx,

    // Level output to irq block (C19: tx_empty = READY)
    output logic o_tx_empty
);

  // -------------------------------------------------------------------
  // Register offsets (block "uart", contract.json csr_registers)
  // -------------------------------------------------------------------
  localparam logic [11:0] OFF_TX_DATA = 12'h000;
  localparam logic [11:0] OFF_STATUS  = 12'h004;
  localparam logic [11:0] OFF_DIVISOR = 12'h008;

  wire unused_awprot = |s_axil_awprot;
  wire unused_arprot = |s_axil_arprot;
  // Only the low 12 bits (in-window offset) are decoded; lite_bridge
  // (AXI-09) guarantees the upper bits already select this target.
  wire unused_awaddr_hi = |s_axil_awaddr[31:12];
  wire unused_araddr_hi = |s_axil_araddr[31:12];

  // -------------------------------------------------------------------
  // Holding slot + serializer
  // -------------------------------------------------------------------
  typedef enum logic [1:0] {
    TX_IDLE,
    TX_START,
    TX_DATA,
    TX_STOP
  } tx_state_t;

  tx_state_t   tx_state;
  logic        holding_valid;
  logic [ 7:0] holding_byte;
  logic [ 7:0] shift_reg;
  logic [ 2:0] bit_idx;
  logic [15:0] divisor_r;
  logic [15:0] baud_cnt;

  wire ready = !holding_valid;
  wire busy  = (tx_state != TX_IDLE);

  assign o_tx_empty = ready;

  always_comb begin
    unique case (tx_state)
      TX_IDLE:  o_uart_tx = 1'b1;
      TX_START: o_uart_tx = 1'b0;
      TX_DATA:  o_uart_tx = shift_reg[bit_idx];
      TX_STOP:  o_uart_tx = 1'b1;
      default:  o_uart_tx = 1'b1;
    endcase
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      tx_state      <= TX_IDLE;
      holding_valid <= 1'b0;
      holding_byte  <= 8'd0;
      shift_reg     <= 8'd0;
      bit_idx       <= 3'd0;
      baud_cnt      <= 16'd0;
      divisor_r     <= 16'd16;  // reset16 (contract.json)
    end else begin
      // Holding slot: written by the CSR write side (below); consumed here
      // whenever the shifter goes idle and a byte is waiting (SYS-11).
      unique case (tx_state)
        TX_IDLE: begin
          if (holding_valid) begin
            shift_reg     <= holding_byte;
            holding_valid <= 1'b0;
            tx_state      <= TX_START;
            baud_cnt      <= divisor_r - 16'd1;
          end
        end
        TX_START: begin
          if (baud_cnt == 16'd0) begin
            tx_state <= TX_DATA;
            bit_idx  <= 3'd0;
            baud_cnt <= divisor_r - 16'd1;
          end else begin
            baud_cnt <= baud_cnt - 16'd1;
          end
        end
        TX_DATA: begin
          if (baud_cnt == 16'd0) begin
            if (bit_idx == 3'd7) begin
              tx_state <= TX_STOP;
            end else begin
              bit_idx <= bit_idx + 3'd1;
            end
            baud_cnt <= divisor_r - 16'd1;
          end else begin
            baud_cnt <= baud_cnt - 16'd1;
          end
        end
        TX_STOP: begin
          if (baud_cnt == 16'd0) begin
            tx_state <= TX_IDLE;
          end else begin
            baud_cnt <= baud_cnt - 16'd1;
          end
        end
        default: tx_state <= TX_IDLE;
      endcase

      // CSR holding-slot write, applied after the FSM case above. This can
      // never race the TX_IDLE consume path in the same cycle: TX_IDLE only
      // clears holding_valid when it samples the (pre-edge) value 1, while
      // wr_slverr rejects a TX_DATA write whenever that same pre-edge value
      // is 1 (not READY) — the two paths never both act on one edge.
      if (csr_tx_data_write) begin
        holding_byte  <= cur_wdata[7:0];
        holding_valid <= 1'b1;
      end

      if (csr_divisor_write) begin
        divisor_r <= cur_wdata[15:0];
      end
    end
  end

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
        OFF_TX_DATA: wr_slverr = (cur_wdata[31:8] != 24'd0) || holding_valid;  // not READY
        // rc4 (CHANGE_ORDER_rc4.md F-07, ISSUE-uart-01 ruled reject):
        // "legal 2..65535" is hardware-enforced. A divisor field value below
        // 2 returns SLVERR, no state change, in addition to the pre-existing
        // reserved-bits check and the BUSY-reject; see hw/rtl/uart/ISSUES.md.
        OFF_DIVISOR:
        wr_slverr = (cur_wdata[31:16] != 16'd0) || busy || (cur_wdata[15:0] < 16'd2);
        default: wr_slverr = 1'b1;  // STATUS (RO) and unmapped offsets (SYS-08)
      endcase
    end
  end

  wire csr_tx_data_write = do_write && !wr_slverr && (waddr_off == OFF_TX_DATA);
  wire csr_divisor_write = do_write && !wr_slverr && (waddr_off == OFF_DIVISOR);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      aw_v_q       <= 1'b0;
      awaddr_off_q <= 12'd0;
      w_v_q        <= 1'b0;
      wdata_q      <= 32'd0;
      wstrb_q      <= 4'd0;
      bvalid_r     <= 1'b0;
      bresp_r      <= 2'b00;
    end else begin
      if (bvalid_r && s_axil_bready) begin
        bvalid_r <= 1'b0;
      end

      if (do_write) begin
        bvalid_r <= 1'b1;
        bresp_r  <= wr_slverr ? 2'b10 : 2'b00;
        aw_v_q   <= 1'b0;
        w_v_q    <= 1'b0;
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
        OFF_TX_DATA: rdata_mux = 32'd0;  // WO reads return zero, no side effect
        OFF_STATUS:  rdata_mux = {30'd0, busy, ready};
        OFF_DIVISOR: rdata_mux = {16'd0, divisor_r};
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
