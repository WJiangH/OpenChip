// lite_bridge.sv — AXI4 to AXI4-Lite peripheral bridge.
//
// Spec: docs/spec/llm-soc-v1/axi.md AXI-09 (Lite signal set, full-word
//   single-beat only, bursts rejected without issuing Lite requests, AW and W
//   buffered independently, full-AXI ID retained until B, response errors
//   relayed, one read and one write live, at most one write side effect per
//   complete AW/W pair, independent Lite target ports selected by address);
//   AXI-01/AXI-02 (full-AXI target signal set and legal attributes);
//   AXI-05 (rejected reads return zero data for exactly LEN+1 beats, rejected
//   writes drain exactly LEN+1 W beats then return one error B);
//   system.md SYS-08 (aligned 32-bit single transfers, WSTRB=0xf on writes,
//   other sizes/strobes/offsets return SLVERR and change no state);
//   contract.json C07 (fabric -> lite_bridge, axi4), C08..C11 (lite_bridge ->
//   sys / npu_csr / irq / uart, axi4_lite), CR06 (clock_reset).
//
// Lite port order follows contract.json C08..C11, which is also address order:
//   m0 = sys     0x40000000..0x40000fff  (C08)
//   m1 = npu_csr 0x40001000..0x40001fff  (C09)
//   m2 = irq     0x40002000..0x40002fff  (C10)
//   m3 = uart    0x40003000..0x40003fff  (C11)
// contract.json gives lite_bridge four independent Lite initiator connections
// and AXI-09 states "NPU CSR, system, IRQ and UART use independent Lite target
// ports selected by address", so the 4 KiB window decode lives here.
//
// The upstream firewall (fabric) has already validated region, permission and
// the AXI-02 attribute set; this bridge additionally enforces the AXI-09 /
// SYS-08 CSR transaction shape (single beat, 4-byte size, aligned, all four
// byte strobes on writes) and rejects anything else without touching a Lite
// port.  Window bases/sizes are localparams bound to the spec values.
`default_nettype none

module lite_bridge (
    input  wire         clk,
    input  wire         rst_n,

    // ---------------- C07: full-AXI target port (from fabric) --------------
    input  wire         s_axi_awvalid,
    output logic        s_axi_awready,
    input  wire  [31:0] s_axi_awaddr,
    input  wire  [1:0]  s_axi_awid,
    input  wire  [7:0]  s_axi_awlen,
    input  wire  [2:0]  s_axi_awsize,
    input  wire  [1:0]  s_axi_awburst,
    input  wire         s_axi_awlock,
    input  wire  [3:0]  s_axi_awcache,
    input  wire  [2:0]  s_axi_awprot,
    input  wire  [3:0]  s_axi_awqos,
    input  wire         s_axi_wvalid,
    output logic        s_axi_wready,
    input  wire  [31:0] s_axi_wdata,
    input  wire  [3:0]  s_axi_wstrb,
    input  wire         s_axi_wlast,
    output logic        s_axi_bvalid,
    input  wire         s_axi_bready,
    output logic [1:0]  s_axi_bresp,
    output logic [1:0]  s_axi_bid,
    input  wire         s_axi_arvalid,
    output logic        s_axi_arready,
    input  wire  [31:0] s_axi_araddr,
    input  wire  [1:0]  s_axi_arid,
    input  wire  [7:0]  s_axi_arlen,
    input  wire  [2:0]  s_axi_arsize,
    input  wire  [1:0]  s_axi_arburst,
    input  wire         s_axi_arlock,
    input  wire  [3:0]  s_axi_arcache,
    input  wire  [2:0]  s_axi_arprot,
    input  wire  [3:0]  s_axi_arqos,
    output logic        s_axi_rvalid,
    input  wire         s_axi_rready,
    output logic [31:0] s_axi_rdata,
    output logic [1:0]  s_axi_rresp,
    output logic [1:0]  s_axi_rid,
    output logic        s_axi_rlast,

    // ---------------- C08: system registers Lite port ----------------------
    output logic        m0_axil_awvalid,
    input  wire         m0_axil_awready,
    output logic [31:0] m0_axil_awaddr,
    output logic [2:0]  m0_axil_awprot,
    output logic        m0_axil_wvalid,
    input  wire         m0_axil_wready,
    output logic [31:0] m0_axil_wdata,
    output logic [3:0]  m0_axil_wstrb,
    input  wire         m0_axil_bvalid,
    output logic        m0_axil_bready,
    input  wire  [1:0]  m0_axil_bresp,
    output logic        m0_axil_arvalid,
    input  wire         m0_axil_arready,
    output logic [31:0] m0_axil_araddr,
    output logic [2:0]  m0_axil_arprot,
    input  wire         m0_axil_rvalid,
    output logic        m0_axil_rready,
    input  wire  [31:0] m0_axil_rdata,
    input  wire  [1:0]  m0_axil_rresp,

    // ---------------- C09: NPU CSR Lite port -------------------------------
    output logic        m1_axil_awvalid,
    input  wire         m1_axil_awready,
    output logic [31:0] m1_axil_awaddr,
    output logic [2:0]  m1_axil_awprot,
    output logic        m1_axil_wvalid,
    input  wire         m1_axil_wready,
    output logic [31:0] m1_axil_wdata,
    output logic [3:0]  m1_axil_wstrb,
    input  wire         m1_axil_bvalid,
    output logic        m1_axil_bready,
    input  wire  [1:0]  m1_axil_bresp,
    output logic        m1_axil_arvalid,
    input  wire         m1_axil_arready,
    output logic [31:0] m1_axil_araddr,
    output logic [2:0]  m1_axil_arprot,
    input  wire         m1_axil_rvalid,
    output logic        m1_axil_rready,
    input  wire  [31:0] m1_axil_rdata,
    input  wire  [1:0]  m1_axil_rresp,

    // ---------------- C10: IRQ registers Lite port -------------------------
    output logic        m2_axil_awvalid,
    input  wire         m2_axil_awready,
    output logic [31:0] m2_axil_awaddr,
    output logic [2:0]  m2_axil_awprot,
    output logic        m2_axil_wvalid,
    input  wire         m2_axil_wready,
    output logic [31:0] m2_axil_wdata,
    output logic [3:0]  m2_axil_wstrb,
    input  wire         m2_axil_bvalid,
    output logic        m2_axil_bready,
    input  wire  [1:0]  m2_axil_bresp,
    output logic        m2_axil_arvalid,
    input  wire         m2_axil_arready,
    output logic [31:0] m2_axil_araddr,
    output logic [2:0]  m2_axil_arprot,
    input  wire         m2_axil_rvalid,
    output logic        m2_axil_rready,
    input  wire  [31:0] m2_axil_rdata,
    input  wire  [1:0]  m2_axil_rresp,

    // ---------------- C11: UART registers Lite port ------------------------
    output logic        m3_axil_awvalid,
    input  wire         m3_axil_awready,
    output logic [31:0] m3_axil_awaddr,
    output logic [2:0]  m3_axil_awprot,
    output logic        m3_axil_wvalid,
    input  wire         m3_axil_wready,
    output logic [31:0] m3_axil_wdata,
    output logic [3:0]  m3_axil_wstrb,
    input  wire         m3_axil_bvalid,
    output logic        m3_axil_bready,
    input  wire  [1:0]  m3_axil_bresp,
    output logic        m3_axil_arvalid,
    input  wire         m3_axil_arready,
    output logic [31:0] m3_axil_araddr,
    output logic [2:0]  m3_axil_arprot,
    input  wire         m3_axil_rvalid,
    output logic        m3_axil_rready,
    input  wire  [31:0] m3_axil_rdata,
    input  wire  [1:0]  m3_axil_rresp
);

  // =====================================================================
  // Constants
  // =====================================================================
  localparam logic [1:0] RESP_OKAY   = 2'b00;
  localparam logic [1:0] RESP_SLVERR = 2'b10;
  localparam logic [1:0] RESP_DECERR = 2'b11;

  localparam logic [2:0] AXSIZE_4B  = 3'd2;
  localparam logic [1:0] AXBURST_IN = 2'b01;
  localparam logic [3:0] WSTRB_ALL = 4'hf;

  // Peripheral windows (system.md §2 / contract.json address_regions).
  localparam logic [31:0] BASE_SYS     = 32'h4000_0000;
  localparam logic [31:0] BASE_NPU_CSR = 32'h4000_1000;
  localparam logic [31:0] BASE_IRQ     = 32'h4000_2000;
  localparam logic [31:0] BASE_UART    = 32'h4000_3000;
  localparam logic [31:0] SIZE_WINDOW  = 32'h0000_1000;  // 4096 each

  localparam logic [1:0] SEL_SYS     = 2'd0;
  localparam logic [1:0] SEL_NPU_CSR = 2'd1;
  localparam logic [1:0] SEL_IRQ     = 2'd2;
  localparam logic [1:0] SEL_UART    = 2'd3;

  function automatic logic in_window(input logic [31:0] a, input logic [31:0] base);
    in_window = (a >= base) && ((a - base) < SIZE_WINDOW);
  endfunction

  // Returns {hit, sel[1:0]}.
  function automatic logic [2:0] window_decode(input logic [31:0] a);
    logic       hit;
    logic [1:0] sel;
    begin
      hit = 1'b1;
      sel = SEL_SYS;
      if      (in_window(a, BASE_SYS))     sel = SEL_SYS;
      else if (in_window(a, BASE_NPU_CSR)) sel = SEL_NPU_CSR;
      else if (in_window(a, BASE_IRQ))     sel = SEL_IRQ;
      else if (in_window(a, BASE_UART))    sel = SEL_UART;
      else                                 hit = 1'b0;
      window_decode = {hit, sel};
    end
  endfunction

  // =====================================================================
  // Lite port vectors: payload is broadcast, only VALID/READY are steered.
  // =====================================================================
  logic [3:0]       l_awready, l_wready, l_bvalid, l_arready, l_rvalid;
  logic [3:0][1:0]  l_bresp, l_rresp;
  logic [3:0][31:0] l_rdata;
  logic [3:0]       l_awvalid, l_wvalid, l_bready, l_arvalid, l_rready;

  assign l_awready = {m3_axil_awready, m2_axil_awready, m1_axil_awready, m0_axil_awready};
  assign l_wready  = {m3_axil_wready,  m2_axil_wready,  m1_axil_wready,  m0_axil_wready};
  assign l_bvalid  = {m3_axil_bvalid,  m2_axil_bvalid,  m1_axil_bvalid,  m0_axil_bvalid};
  assign l_bresp   = {m3_axil_bresp,   m2_axil_bresp,   m1_axil_bresp,   m0_axil_bresp};
  assign l_arready = {m3_axil_arready, m2_axil_arready, m1_axil_arready, m0_axil_arready};
  assign l_rvalid  = {m3_axil_rvalid,  m2_axil_rvalid,  m1_axil_rvalid,  m0_axil_rvalid};
  assign l_rdata   = {m3_axil_rdata,   m2_axil_rdata,   m1_axil_rdata,   m0_axil_rdata};
  assign l_rresp   = {m3_axil_rresp,   m2_axil_rresp,   m1_axil_rresp,   m0_axil_rresp};

  // =====================================================================
  // Write path: AW buffer, independent one-beat W buffer, one live write.
  // =====================================================================
  localparam logic [2:0] WS_IDLE  = 3'd0;  // no AW captured
  localparam logic [2:0] WS_WAITW = 3'd1;  // AW captured, waiting for a W beat
  localparam logic [2:0] WS_LITE  = 3'd2;  // issuing the single Lite AW/W
  localparam logic [2:0] WS_BRESP = 3'd3;  // relaying the Lite B
  localparam logic [2:0] WS_DRAIN = 3'd4;  // rejected: drain remaining W beats
  localparam logic [2:0] WS_ERRB  = 3'd5;  // rejected: one error B

  logic [2:0]  wr_state;
  logic [31:0] aw_addr;
  logic [1:0]  aw_id;
  logic [7:0]  aw_len;
  logic [2:0]  aw_prot;
  logic [1:0]  aw_sel;
  logic [1:0]  wr_resp;       // error response for a rejected write
  logic [7:0]  wr_beat;       // W beats already consumed
  logic        aw_sent, w_sent;

  // Independent one-beat W buffer (AXI-09: AW and W are buffered separately;
  // a W beat may be accepted before its AW and no address is inferred from it).
  logic        wb_valid;
  logic [31:0] wb_data;
  logic [3:0]  wb_strb;
  logic        wb_last;
  logic        wb_take;

  logic [2:0]  aw_dec;
  logic        aw_shape_bad;

  assign aw_dec       = window_decode(s_axi_awaddr);
  // AXI-09 / SYS-08: only full-word single-beat transfers with the AXI-02
  // attribute encoding are accepted; everything else is rejected here without
  // issuing any Lite request (defence in depth behind the fabric firewall).
  assign aw_shape_bad = (s_axi_awlen   != 8'd0)
                      | (s_axi_awsize  != AXSIZE_4B)
                      | (s_axi_awburst != AXBURST_IN)
                      |  s_axi_awlock
                      | (s_axi_awcache != 4'd0)
                      | (s_axi_awqos   != 4'd0)
                      | (s_axi_awaddr[1:0] != 2'b00);

  assign s_axi_awready = (wr_state == WS_IDLE);
  assign s_axi_wready  = !wb_valid;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      wb_valid <= 1'b0;
      wb_data  <= 32'h0;
      wb_strb  <= 4'h0;
      wb_last  <= 1'b0;
    end else if (s_axi_wvalid && s_axi_wready) begin
      wb_valid <= 1'b1;
      wb_data  <= s_axi_wdata;
      wb_strb  <= s_axi_wstrb;
      wb_last  <= s_axi_wlast;
    end else if (wb_take) begin
      wb_valid <= 1'b0;
    end
  end


  logic [1:0] aw_err_c;
  logic       wstrb_bad;
  logic       wr_lite_aw_hs, wr_lite_w_hs, wr_b_hs;

  // ISSUE-lite_bridge-01: provisional — an address that decodes to no window
  // is DECERR, an in-window transaction whose shape is not a full-word single
  // beat is SLVERR (SYS-08 "other sizes, strobes, offsets ... return SLVERR");
  // when both apply the mapping error is reported, matching the fabric.
  assign aw_err_c  = !aw_dec[2]    ? RESP_DECERR :
                     aw_shape_bad  ? RESP_SLVERR : RESP_OKAY;
  assign wstrb_bad = (wb_strb != WSTRB_ALL);

  assign wr_lite_aw_hs = l_awvalid[aw_sel] & l_awready[aw_sel];
  assign wr_lite_w_hs  = l_wvalid[aw_sel]  & l_wready[aw_sel];
  assign wr_b_hs       = s_axi_bvalid & s_axi_bready;

  // The buffered W beat is released to the Lite port on its W handshake, and
  // discarded beat by beat while a rejected write drains.
  always_comb begin
    case (wr_state)
      WS_WAITW: wb_take = wb_valid & (wstrb_bad | ~wb_last);  // rejected here
      WS_LITE:  wb_take = wr_lite_w_hs;
      WS_DRAIN: wb_take = wb_valid;
      default:  wb_take = 1'b0;
    endcase
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      wr_state <= WS_IDLE;
      aw_addr  <= 32'h0;
      aw_id    <= 2'b00;
      aw_len   <= 8'h00;
      aw_prot  <= 3'b000;
      aw_sel   <= SEL_SYS;
      wr_resp  <= RESP_OKAY;
      wr_beat  <= 8'h00;
      aw_sent  <= 1'b0;
      w_sent   <= 1'b0;
    end else begin
      case (wr_state)
        WS_IDLE: begin
          if (s_axi_awvalid && s_axi_awready) begin
            aw_addr  <= s_axi_awaddr;
            aw_id    <= s_axi_awid;      // retained until B (AXI-09)
            aw_len   <= s_axi_awlen;
            aw_prot  <= s_axi_awprot;
            aw_sel   <= aw_dec[1:0];
            wr_resp  <= aw_err_c;
            wr_beat  <= 8'h00;
            aw_sent  <= 1'b0;
            w_sent   <= 1'b0;
            // A burst is rejected without ever issuing a Lite request; its W
            // beats are still drained (AXI-05).
            wr_state <= (aw_err_c == RESP_OKAY) ? WS_WAITW : WS_DRAIN;
          end
        end
        WS_WAITW: begin
          if (wb_valid) begin
            if (wstrb_bad || !wb_last) begin
              // Not a full-word single-beat write: no Lite request is issued.
              // aw_len is 0 here, so this beat is the whole burst.
              wr_resp  <= RESP_SLVERR;
              wr_beat  <= wr_beat + 8'd1;
              wr_state <= WS_ERRB;
            end else begin
              wr_state <= WS_LITE;
            end
          end
        end
        WS_LITE: begin
          // At most one write side effect per AW/W pair: each VALID is
          // dropped after its own handshake and never re-issued.
          if (wr_lite_aw_hs) aw_sent <= 1'b1;
          if (wr_lite_w_hs)  w_sent  <= 1'b1;
          if ((aw_sent | wr_lite_aw_hs) && (w_sent | wr_lite_w_hs)) wr_state <= WS_BRESP;
        end
        WS_BRESP: begin
          if (wr_b_hs) wr_state <= WS_IDLE;
        end
        WS_DRAIN: begin
          if (wb_valid) begin
            wr_beat <= wr_beat + 8'd1;
            if (wr_beat == aw_len) wr_state <= WS_ERRB;
          end
        end
        WS_ERRB: begin
          if (wr_b_hs) wr_state <= WS_IDLE;
        end
        default: wr_state <= WS_IDLE;
      endcase
    end
  end

  // =====================================================================
  // Read path: one live read, error beats generated locally.
  // =====================================================================
  localparam logic [1:0] RS_IDLE = 2'd0;
  localparam logic [1:0] RS_LITE = 2'd1;  // offering the Lite AR
  localparam logic [1:0] RS_R    = 2'd2;  // relaying the Lite R beat
  localparam logic [1:0] RS_ERR  = 2'd3;  // exactly LEN+1 zero-data error beats

  logic [1:0]  rd_state;
  logic [31:0] ar_addr;
  logic [1:0]  ar_id;
  logic [7:0]  ar_len;
  logic [2:0]  ar_prot;
  logic [1:0]  ar_sel;
  logic [1:0]  rd_resp;
  logic [7:0]  rd_beat;

  logic [2:0]  ar_dec;
  logic        ar_shape_bad;
  logic [1:0]  ar_err_c;
  logic        rd_lite_ar_hs, rd_r_hs, rd_last;

  assign ar_dec       = window_decode(s_axi_araddr);
  assign ar_shape_bad = (s_axi_arlen   != 8'd0)
                      | (s_axi_arsize  != AXSIZE_4B)
                      | (s_axi_arburst != AXBURST_IN)
                      |  s_axi_arlock
                      | (s_axi_arcache != 4'd0)
                      | (s_axi_arqos   != 4'd0)
                      | (s_axi_araddr[1:0] != 2'b00);
  // ISSUE-lite_bridge-01: provisional — same ordering as the write path.
  assign ar_err_c     = !ar_dec[2]   ? RESP_DECERR :
                        ar_shape_bad ? RESP_SLVERR : RESP_OKAY;

  assign s_axi_arready = (rd_state == RS_IDLE);
  assign rd_lite_ar_hs = l_arvalid[ar_sel] & l_arready[ar_sel];
  assign rd_r_hs       = s_axi_rvalid & s_axi_rready;
  assign rd_last       = (rd_beat == ar_len);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      rd_state <= RS_IDLE;
      ar_addr  <= 32'h0;
      ar_id    <= 2'b00;
      ar_len   <= 8'h00;
      ar_prot  <= 3'b000;
      ar_sel   <= SEL_SYS;
      rd_resp  <= RESP_OKAY;
      rd_beat  <= 8'h00;
    end else begin
      case (rd_state)
        RS_IDLE: begin
          if (s_axi_arvalid && s_axi_arready) begin
            ar_addr  <= s_axi_araddr;
            ar_id    <= s_axi_arid;      // retained until the last R beat
            ar_len   <= s_axi_arlen;
            ar_prot  <= s_axi_arprot;
            ar_sel   <= ar_dec[1:0];
            rd_resp  <= ar_err_c;
            rd_beat  <= 8'h00;
            rd_state <= (ar_err_c == RESP_OKAY) ? RS_LITE : RS_ERR;
          end
        end
        RS_LITE: begin
          if (rd_lite_ar_hs) rd_state <= RS_R;
        end
        RS_R, RS_ERR: begin
          if (rd_r_hs) begin
            rd_beat <= rd_beat + 8'd1;
            if (rd_last) rd_state <= RS_IDLE;
          end
        end
        default: rd_state <= RS_IDLE;
      endcase
    end
  end

  // =====================================================================
  // Full-AXI response drive
  // =====================================================================
  always_comb begin
    s_axi_bvalid = 1'b0;
    s_axi_bresp  = wr_resp;
    s_axi_rvalid = 1'b0;
    s_axi_rdata  = 32'h0;
    s_axi_rresp  = rd_resp;

    if (wr_state == WS_BRESP) begin
      s_axi_bvalid = l_bvalid[aw_sel];
      s_axi_bresp  = l_bresp[aw_sel];   // response errors are relayed
    end else if (wr_state == WS_ERRB) begin
      s_axi_bvalid = 1'b1;
    end

    if (rd_state == RS_R) begin
      s_axi_rvalid = l_rvalid[ar_sel];
      s_axi_rdata  = l_rdata[ar_sel];
      s_axi_rresp  = l_rresp[ar_sel];
    end else if (rd_state == RS_ERR) begin
      s_axi_rvalid = 1'b1;              // zero data, exactly LEN+1 beats
    end
  end

  assign s_axi_bid   = aw_id;
  assign s_axi_rid   = ar_id;
  assign s_axi_rlast = rd_last;

  // =====================================================================
  // Lite port drive: payload broadcast, VALID/READY steered by the window.
  // =====================================================================
  always_comb begin
    l_awvalid = 4'b0000;
    l_wvalid  = 4'b0000;
    l_bready  = 4'b0000;
    l_arvalid = 4'b0000;
    l_rready  = 4'b0000;

    if (wr_state == WS_LITE) begin
      l_awvalid[aw_sel] = ~aw_sent;
      l_wvalid[aw_sel]  = ~w_sent;
    end
    if (wr_state == WS_BRESP) l_bready[aw_sel] = s_axi_bready;
    if (rd_state == RS_LITE)  l_arvalid[ar_sel] = 1'b1;
    if (rd_state == RS_R)     l_rready[ar_sel]  = s_axi_rready;
  end

  assign m0_axil_awvalid = l_awvalid[0];
  assign m1_axil_awvalid = l_awvalid[1];
  assign m2_axil_awvalid = l_awvalid[2];
  assign m3_axil_awvalid = l_awvalid[3];
  assign m0_axil_wvalid  = l_wvalid[0];
  assign m1_axil_wvalid  = l_wvalid[1];
  assign m2_axil_wvalid  = l_wvalid[2];
  assign m3_axil_wvalid  = l_wvalid[3];
  assign m0_axil_bready  = l_bready[0];
  assign m1_axil_bready  = l_bready[1];
  assign m2_axil_bready  = l_bready[2];
  assign m3_axil_bready  = l_bready[3];
  assign m0_axil_arvalid = l_arvalid[0];
  assign m1_axil_arvalid = l_arvalid[1];
  assign m2_axil_arvalid = l_arvalid[2];
  assign m3_axil_arvalid = l_arvalid[3];
  assign m0_axil_rready  = l_rready[0];
  assign m1_axil_rready  = l_rready[1];
  assign m2_axil_rready  = l_rready[2];
  assign m3_axil_rready  = l_rready[3];

  assign m0_axil_awaddr  = aw_addr;
  assign m1_axil_awaddr  = aw_addr;
  assign m2_axil_awaddr  = aw_addr;
  assign m3_axil_awaddr  = aw_addr;
  assign m0_axil_awprot  = aw_prot;
  assign m1_axil_awprot  = aw_prot;
  assign m2_axil_awprot  = aw_prot;
  assign m3_axil_awprot  = aw_prot;
  assign m0_axil_wdata   = wb_data;
  assign m1_axil_wdata   = wb_data;
  assign m2_axil_wdata   = wb_data;
  assign m3_axil_wdata   = wb_data;
  assign m0_axil_wstrb   = wb_strb;
  assign m1_axil_wstrb   = wb_strb;
  assign m2_axil_wstrb   = wb_strb;
  assign m3_axil_wstrb   = wb_strb;
  assign m0_axil_araddr  = ar_addr;
  assign m1_axil_araddr  = ar_addr;
  assign m2_axil_araddr  = ar_addr;
  assign m3_axil_araddr  = ar_addr;
  assign m0_axil_arprot  = ar_prot;
  assign m1_axil_arprot  = ar_prot;
  assign m2_axil_arprot  = ar_prot;
  assign m3_axil_arprot  = ar_prot;

endmodule

`default_nettype wire
