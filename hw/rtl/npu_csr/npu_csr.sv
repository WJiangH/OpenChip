// npu_csr.sv — NPU command-shadow register file, AXI4-Lite target at 0x40001000.
// Spec baseline: docs/spec/llm-soc-v1 1.0-rc4 (CHANGE_ORDER_rc4 rows F-05,
// ISSUE-npu_ctl-02/F-06, ISSUE-npu_csr-01, ISSUE-uart-01/F-07).
// Spec: npu.md NPU-04 (register table, LAST_CYCLES = T-H+1 and its
// per-SUBMIT-outcome behaviour), NPU-05, NPU-06 (irq level equations),
// system.md SYS-08 (CSR semantics, WO command registers accept exactly the
// word 1, NPU shadows accept any word while writable and are validated only
// at SUBMIT). contract.json blocks[npu_csr], csr_registers[block==npu_csr],
// connections C09/C12/C17/C18/C24/CR10.
//
// Descriptor validation ("SUBMIT ... validate and atomically snapshot descriptor",
// NPU-04 register table) and the priority-1..4 error classification of NPU-05 are
// both implemented here: contract.json's `requirements` entry for NPU-01..NPU-08
// lists {npu_csr, npu_ctl, npu_dma, npu_dot} jointly as owners and does not itself
// split the validation duty between npu_csr and npu_ctl. The prose is decisive
// (SUBMIT's own field description says "validate ... snapshot"; NPU-05 additionally
// says a malformed idle SUBMIT "returns OKAY at the CSR layer ... issues no DMA",
// i.e. npu_ctl never even sees a malformed command), so validation is placed here.
// rc4 ruled ISSUE-npu_csr-01 spec-clear on exactly this reading ("npu_csr
// validates fully; a dispatch never carries a malformed descriptor"), so this
// implementation stands unchanged. See ISSUES.md ISSUE-npu_csr-01.
`default_nettype none

module npu_csr (
    // CR10: sys -> npu_csr clock_reset. House convention: bare clk/rst_n on
    // internal (non-top) modules; synchronous active-low reset.
    input wire clk,
    input wire rst_n,

    // C09: lite_bridge -> npu_csr, protocol axi4_lite (target role). Bus-prefixed
    // ports carry no i_/o_ direction prefix per AGENTS.md; target-side signal set
    // and widths exactly as contract.json protocols.axi4_lite lists them.
    input  wire        s_axil_awvalid,
    output logic        s_axil_awready,
    input  wire [31:0] s_axil_awaddr,
    input  wire [ 2:0] s_axil_awprot,
    input  wire        s_axil_wvalid,
    output logic        s_axil_wready,
    input  wire [31:0] s_axil_wdata,
    input  wire [ 3:0] s_axil_wstrb,
    output logic        s_axil_bvalid,
    input  wire        s_axil_bready,
    output logic [1:0] s_axil_bresp,
    input  wire        s_axil_arvalid,
    output logic        s_axil_arready,
    input  wire [31:0] s_axil_araddr,
    input  wire [ 2:0] s_axil_arprot,
    output logic        s_axil_rvalid,
    input  wire        s_axil_rready,
    output logic [31:0] s_axil_rdata,
    output logic [ 1:0] s_axil_rresp,

    // C12: npu_csr -> npu_ctl, protocol dispatch (npu_csr is producer). Fields
    // exactly as contract.json protocols.dispatch lists them (valid/ready plus
    // opcode,x_base,w_base,y_base,k,n,group,w_stride,tag, all 32b).
    output logic        o_dispatch_valid,
    input  wire        i_dispatch_ready,
    output logic [31:0] o_dispatch_opcode,
    output logic [31:0] o_dispatch_x_base,
    output logic [31:0] o_dispatch_w_base,
    output logic [31:0] o_dispatch_y_base,
    output logic [31:0] o_dispatch_k,
    output logic [31:0] o_dispatch_n,
    output logic [31:0] o_dispatch_group,
    output logic [31:0] o_dispatch_w_stride,
    output logic [31:0] o_dispatch_tag,

    // C24: npu_ctl -> npu_csr, protocol terminal (npu_csr is consumer). Fields
    // exactly as contract.json protocols.terminal lists them.
    input  wire        i_terminal_valid,
    output logic        o_terminal_ready,
    input  wire [31:0] i_terminal_tag,
    input  wire [ 2:0] i_terminal_error_code,
    input  wire [31:0] i_terminal_cycles,

    // C17/C18: npu_csr -> irq, protocol irq_level, source_signal done_irq/error_irq.
    // Level = (DONE & IRQ_ENABLE[0]) / (ERROR & IRQ_ENABLE[1]) per NPU-06.
    output logic o_done_irq,
    output logic o_error_irq
);

  // ---------------------------------------------------------------------
  // Register offsets (NPU-04 table), expressed as word index addr[11:2].
  // ---------------------------------------------------------------------
  localparam logic [9:0] OFF_VERSION    = 10'h000;  // 0x00 RO
  localparam logic [9:0] OFF_STATUS     = 10'h001;  // 0x04 RO
  localparam logic [9:0] OFF_SUBMIT     = 10'h002;  // 0x08 WO
  localparam logic [9:0] OFF_CLEAR      = 10'h003;  // 0x0c WO
  localparam logic [9:0] OFF_OPCODE     = 10'h004;  // 0x10 RW shadow
  localparam logic [9:0] OFF_X_BASE     = 10'h005;  // 0x14 RW shadow
  localparam logic [9:0] OFF_W_BASE     = 10'h006;  // 0x18 RW shadow
  localparam logic [9:0] OFF_Y_BASE     = 10'h007;  // 0x1c RW shadow
  localparam logic [9:0] OFF_K          = 10'h008;  // 0x20 RW shadow
  localparam logic [9:0] OFF_N          = 10'h009;  // 0x24 RW shadow
  localparam logic [9:0] OFF_GROUP      = 10'h00a;  // 0x28 RW shadow
  localparam logic [9:0] OFF_W_STRIDE   = 10'h00b;  // 0x2c RW shadow
  localparam logic [9:0] OFF_TAG        = 10'h00c;  // 0x30 RW shadow
  localparam logic [9:0] OFF_CTAG       = 10'h00d;  // 0x34 RO
  localparam logic [9:0] OFF_ERR_CODE   = 10'h00e;  // 0x38 RO
  localparam logic [9:0] OFF_IRQ_ENABLE = 10'h00f;  // 0x3c RW, any state
  localparam logic [9:0] OFF_LAST_CYCLE = 10'h010;  // 0x40 RO

  localparam logic [31:0] VERSION_CONST = 32'h0001_0000;  // NPU-04 reset/value

  localparam logic [1:0] AXI_OKAY   = 2'b00;
  localparam logic [1:0] AXI_SLVERR = 2'b10;

  // Descriptor error-code priority order (NPU-05): 1 opcode, 2 shape/group,
  // 3 alignment/stride, 4 range/permission/overlap.
  localparam logic [2:0] ERR_NONE      = 3'd0;
  localparam logic [2:0] ERR_OPCODE    = 3'd1;
  localparam logic [2:0] ERR_SHAPE     = 3'd2;
  localparam logic [2:0] ERR_ALIGN     = 3'd3;
  localparam logic [2:0] ERR_RANGE     = 3'd4;

  // system.md §2 address_regions (model R-only for NPU, scratch RW for NPU).
  // Used only for NPU-02 range/permission/overlap validation (priority-4 check).
  localparam logic [63:0] MODEL_BASE   = 64'h0000_0000_8010_0000;
  localparam logic [63:0] MODEL_END    = 64'h0000_0000_8050_0000;
  localparam logic [63:0] SCRATCH_BASE = 64'h0000_0000_8060_0000;
  localparam logic [63:0] SCRATCH_END  = 64'h0000_0000_8070_0000;

  // Permission/PROT signals are not consulted here: physical source-port
  // identity + region firewalling happen upstream in `fabric` (SYS-04); the
  // Lite target only ever sees traffic already routed to it.
  wire unused_awprot = |s_axil_awprot;
  wire unused_arprot = |s_axil_arprot;
  // Upper address bits are fixed by the 4KiB window firewalled upstream
  // (SYS-04); only addr[11:0] is ever captured/decoded (see aw_addr_q/ar_addr_q).
  wire unused_awaddr_hi = |s_axil_awaddr[31:12];
  wire unused_araddr_hi = |s_axil_araddr[31:12];

  // ---------------------------------------------------------------------
  // AXI4-Lite write channel: independent AW/W capture (AXI-09), single
  // outstanding write (new AW/W not accepted while a B is still pending).
  // ---------------------------------------------------------------------
  // Only the in-block word offset (addr[11:2]) plus alignment bits (addr[1:0])
  // are ever consulted; upper address bits are decoded/firewalled upstream
  // (SYS-04), so only addr[11:0] is captured here.
  logic        aw_valid_q;
  logic [11:0] aw_addr_q;
  logic        w_valid_q;
  logic [31:0] w_data_q;
  logic [ 3:0] w_strb_q;
  logic        b_valid_q;
  logic [ 1:0] b_resp_q;

  assign s_axil_awready = !aw_valid_q && !b_valid_q;
  assign s_axil_wready  = !w_valid_q && !b_valid_q;
  assign s_axil_bvalid  = b_valid_q;
  assign s_axil_bresp   = b_resp_q;

  wire commit_now = aw_valid_q && w_valid_q && !b_valid_q;
  wire generic_bad = (aw_addr_q[1:0] != 2'b00) || (w_strb_q != 4'hf);

  // ---------------------------------------------------------------------
  // AXI4-Lite read channel: single outstanding read.
  // ---------------------------------------------------------------------
  logic        ar_valid_q;
  logic [11:0] ar_addr_q;
  logic        r_valid_q;
  logic [31:0] r_data_q;
  logic [ 1:0] r_resp_q;

  assign s_axil_arready = !ar_valid_q && !r_valid_q;
  assign s_axil_rvalid  = r_valid_q;
  assign s_axil_rdata   = r_data_q;
  assign s_axil_rresp   = r_resp_q;

  wire ar_addr_bad = (ar_addr_q[1:0] != 2'b00);

  // ---------------------------------------------------------------------
  // Command/status state (NPU-04/05/06).
  // ---------------------------------------------------------------------
  logic [31:0] opcode_q, x_base_q, w_base_q, y_base_q;
  logic [31:0] k_q, n_q, group_q, w_stride_q, tag_q;
  logic        busy_q, done_q, error_q;
  // NPU-04 (rc4): LAST_CYCLES is write-once-per-terminal — the ONLY two
  // assignments to last_cycles_q in this file are the reset value 0 and the
  // C24 terminal record that also sets DONE/ERROR/ERROR_CODE/COMPLETED_TAG.
  // No SUBMIT path (accepted, malformed-idle or SLVERR-rejected), no CLEAR and
  // no descriptor write touches it; it therefore holds T-H+1 of the last
  // completed command until the next terminal record or reset.
  logic [31:0] completed_tag_q, error_code_q, last_cycles_q;
  logic [ 1:0] irq_enable_q;   // bit0 done, bit1 error
  logic        dispatch_pending_q;

  wire shadow_locked = busy_q || done_q || error_q;

  // ---------------------------------------------------------------------
  // NPU-01/NPU-02 descriptor validation, priority order 1,2,3,4 (NPU-05).
  // Combinational function of the current shadow registers; only consulted
  // at the moment SUBMIT commits, when the shadow set is guaranteed stable.
  // ---------------------------------------------------------------------
  logic        group_pow2, shape_ok, align_ok, range_ok;
  logic [31:0] round_up_k32, k_plus_g_m1, ceil_k_g32;
  logic [ 3:0] group_shift;
  logic [63:0] round_up_k64, x_end, w_alloc_len, w_end, y_len, y_end;
  logic        x_in_scratch, w_in_model, w_in_scratch, y_in_scratch;
  logic        y_x_overlap, y_w_overlap;
  logic [ 2:0] desc_error_code;

  always_comb begin
    // priority 2: shape/group (NPU-01 K,N,G bounds; G power of two)
    group_pow2 = (group_q != 32'd0) && ((group_q & (group_q - 32'd1)) == 32'd0);
    shape_ok   = (k_q >= 32'd1) && (k_q <= 32'd4096) &&
                 (n_q >= 32'd1) && (n_q <= 32'd4096) &&
                 (group_q >= 32'd1) && (group_q <= 32'd4096) && group_pow2;

    // priority 3: alignment/stride (NPU-02)
    round_up_k32 = (k_q + 32'd3) & ~32'd3;
    align_ok = (x_base_q[1:0] == 2'b00) && (w_base_q[1:0] == 2'b00) &&
               (y_base_q[1:0] == 2'b00) && (w_stride_q[1:0] == 2'b00) &&
               (w_stride_q >= round_up_k32) && (w_stride_q <= 32'd65536);

    // priority 4: range/permission/overlap (NPU-02), unsigned 64-bit endpoints
    case (group_q)
      32'd1:    group_shift = 4'd0;
      32'd2:    group_shift = 4'd1;
      32'd4:    group_shift = 4'd2;
      32'd8:    group_shift = 4'd3;
      32'd16:   group_shift = 4'd4;
      32'd32:   group_shift = 4'd5;
      32'd64:   group_shift = 4'd6;
      32'd128:  group_shift = 4'd7;
      32'd256:  group_shift = 4'd8;
      32'd512:  group_shift = 4'd9;
      32'd1024: group_shift = 4'd10;
      32'd2048: group_shift = 4'd11;
      32'd4096: group_shift = 4'd12;
      default:  group_shift = 4'd0;
    endcase
    k_plus_g_m1  = k_q + group_q - 32'd1;      // <=8191, no 32b overflow risk
    ceil_k_g32   = k_plus_g_m1 >> group_shift;  // ceil(K/G), G power of two

    round_up_k64 = {32'd0, round_up_k32};
    x_end        = {32'd0, x_base_q} + round_up_k64;
    w_alloc_len  = ({32'd0, n_q} - 64'd1) * {32'd0, w_stride_q} + round_up_k64;
    w_end        = {32'd0, w_base_q} + w_alloc_len;
    y_len        = 64'd4 * {32'd0, n_q} * {32'd0, ceil_k_g32};
    y_end        = {32'd0, y_base_q} + y_len;

    x_in_scratch = ({32'd0, x_base_q} >= SCRATCH_BASE) && (x_end <= SCRATCH_END);
    w_in_model   = ({32'd0, w_base_q} >= MODEL_BASE) && (w_end <= MODEL_END);
    w_in_scratch = ({32'd0, w_base_q} >= SCRATCH_BASE) && (w_end <= SCRATCH_END);
    y_in_scratch = ({32'd0, y_base_q} >= SCRATCH_BASE) && (y_end <= SCRATCH_END);

    y_x_overlap = ({32'd0, y_base_q} < x_end) && ({32'd0, x_base_q} < y_end);
    y_w_overlap = ({32'd0, y_base_q} < w_end) && ({32'd0, w_base_q} < y_end);

    range_ok = x_in_scratch && (w_in_model || w_in_scratch) && y_in_scratch &&
               !y_x_overlap && !y_w_overlap;

    // priority order 1,2,3,4
    if (opcode_q != 32'd1)   desc_error_code = ERR_OPCODE;
    else if (!shape_ok)      desc_error_code = ERR_SHAPE;
    else if (!align_ok)      desc_error_code = ERR_ALIGN;
    else if (!range_ok)      desc_error_code = ERR_RANGE;
    else                     desc_error_code = ERR_NONE;
  end

  wire desc_valid = (desc_error_code == ERR_NONE);

  // ---------------------------------------------------------------------
  // Read-data combinational decode (current register values; RO/WO/RW).
  // ---------------------------------------------------------------------
  logic [31:0] rdata_c;
  logic [ 1:0] rresp_c;

  always_comb begin
    rdata_c = 32'd0;
    rresp_c = AXI_OKAY;
    if (ar_addr_bad) begin
      rdata_c = 32'd0;
      rresp_c = AXI_SLVERR;
    end else begin
      case (ar_addr_q[11:2])
        OFF_VERSION:    rdata_c = VERSION_CONST;
        OFF_STATUS:     rdata_c = {29'd0, error_q, done_q, busy_q};
        OFF_SUBMIT:     rdata_c = 32'd0;              // WO reads return zero
        OFF_CLEAR:      rdata_c = 32'd0;              // WO reads return zero
        OFF_OPCODE:     rdata_c = opcode_q;
        OFF_X_BASE:     rdata_c = x_base_q;
        OFF_W_BASE:     rdata_c = w_base_q;
        OFF_Y_BASE:     rdata_c = y_base_q;
        OFF_K:          rdata_c = k_q;
        OFF_N:          rdata_c = n_q;
        OFF_GROUP:      rdata_c = group_q;
        OFF_W_STRIDE:   rdata_c = w_stride_q;
        OFF_TAG:        rdata_c = tag_q;
        OFF_CTAG:       rdata_c = completed_tag_q;
        OFF_ERR_CODE:   rdata_c = error_code_q;
        OFF_IRQ_ENABLE: rdata_c = {30'd0, irq_enable_q};
        OFF_LAST_CYCLE: rdata_c = last_cycles_q;
        default: begin
          rdata_c = 32'd0;
          rresp_c = AXI_SLVERR;                        // undefined offset
        end
      endcase
    end
  end

  // ---------------------------------------------------------------------
  // Sequential state.
  // ---------------------------------------------------------------------
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      aw_valid_q <= 1'b0;
      aw_addr_q  <= 12'd0;
      w_valid_q  <= 1'b0;
      w_data_q   <= 32'd0;
      w_strb_q   <= 4'd0;
      b_valid_q  <= 1'b0;
      b_resp_q   <= AXI_OKAY;

      ar_valid_q <= 1'b0;
      ar_addr_q  <= 12'd0;
      r_valid_q  <= 1'b0;
      r_data_q   <= 32'd0;
      r_resp_q   <= AXI_OKAY;

      opcode_q   <= 32'd0;
      x_base_q   <= 32'd0;
      w_base_q   <= 32'd0;
      y_base_q   <= 32'd0;
      k_q        <= 32'd0;
      n_q        <= 32'd0;
      group_q    <= 32'd0;
      w_stride_q <= 32'd0;
      tag_q      <= 32'd0;

      busy_q          <= 1'b0;
      done_q          <= 1'b0;
      error_q         <= 1'b0;
      completed_tag_q <= 32'd0;
      error_code_q    <= 32'd0;
      irq_enable_q    <= 2'd0;
      last_cycles_q   <= 32'd0;
      dispatch_pending_q <= 1'b0;
    end else begin
      // ---- write address/data capture ----
      if (s_axil_awvalid && s_axil_awready) begin
        aw_addr_q  <= s_axil_awaddr[11:0];
        aw_valid_q <= 1'b1;
      end
      if (s_axil_wvalid && s_axil_wready) begin
        w_data_q  <= s_axil_wdata;
        w_strb_q  <= s_axil_wstrb;
        w_valid_q <= 1'b1;
      end

      // ---- write commit ----
      if (commit_now) begin
        aw_valid_q <= 1'b0;
        w_valid_q  <= 1'b0;
        b_valid_q  <= 1'b1;

        if (generic_bad) begin
          b_resp_q <= AXI_SLVERR;
        end else begin
          case (aw_addr_q[11:2])
            OFF_VERSION, OFF_STATUS, OFF_CTAG, OFF_ERR_CODE, OFF_LAST_CYCLE: begin
              b_resp_q <= AXI_SLVERR;  // RO
            end

            // NPU-05 / SYS-08 (rc4, F-05). Three outcomes, none of which may
            // touch LAST_CYCLES (NPU-04 rc4): SLVERR refusal while busy or
            // terminal-uncleared "changes no state, including LAST_CYCLES";
            // a write of any word other than 1 (including 0) is SLVERR with
            // no effect; a malformed idle descriptor is OKAY at the CSR layer,
            // sets ERROR/ERROR_CODE/COMPLETED_TAG, issues no dispatch and
            // "does not modify LAST_CYCLES". An accepted SUBMIT leaves it at
            // its previous value while BUSY; only the C24 record updates it.
            OFF_SUBMIT: begin
              if (shadow_locked) begin
                b_resp_q <= AXI_SLVERR;                 // NPU-05 command refusal
              end else if (w_data_q != 32'd1) begin
                b_resp_q <= AXI_SLVERR;                 // SYS-08: WO accepts only 1
              end else begin
                b_resp_q <= AXI_OKAY;                   // NPU-05: OKAY at CSR layer
                if (desc_valid) begin
                  busy_q             <= 1'b1;
                  dispatch_pending_q <= 1'b1;
                end else begin
                  error_q         <= 1'b1;
                  error_code_q    <= {29'd0, desc_error_code};
                  completed_tag_q <= tag_q;
                end
              end
            end

            OFF_CLEAR: begin
              if (busy_q) begin
                b_resp_q <= AXI_SLVERR;                 // NPU-04: rejects while BUSY
              end else if (w_data_q != 32'd1) begin
                b_resp_q <= AXI_SLVERR;                 // SYS-08: WO accepts only 1
              end else begin
                // NPU-04: CLEAR clears DONE/ERROR/ERROR_CODE/COMPLETED_TAG and
                // leaves LAST_CYCLES unchanged (rc4).
                b_resp_q        <= AXI_OKAY;
                done_q          <= 1'b0;
                error_q         <= 1'b0;
                error_code_q    <= 32'd0;
                completed_tag_q <= 32'd0;
              end
            end

            OFF_IRQ_ENABLE: begin
              if (w_data_q[31:2] != 30'd0) begin
                b_resp_q <= AXI_SLVERR;                 // reserved bits must be zero
              end else begin
                b_resp_q     <= AXI_OKAY;
                irq_enable_q <= w_data_q[1:0];           // writable in any state
              end
            end

            OFF_OPCODE: begin
              if (shadow_locked) b_resp_q <= AXI_SLVERR;
              else begin b_resp_q <= AXI_OKAY; opcode_q <= w_data_q; end
            end
            OFF_X_BASE: begin
              if (shadow_locked) b_resp_q <= AXI_SLVERR;
              else begin b_resp_q <= AXI_OKAY; x_base_q <= w_data_q; end
            end
            OFF_W_BASE: begin
              if (shadow_locked) b_resp_q <= AXI_SLVERR;
              else begin b_resp_q <= AXI_OKAY; w_base_q <= w_data_q; end
            end
            OFF_Y_BASE: begin
              if (shadow_locked) b_resp_q <= AXI_SLVERR;
              else begin b_resp_q <= AXI_OKAY; y_base_q <= w_data_q; end
            end
            OFF_K: begin
              if (shadow_locked) b_resp_q <= AXI_SLVERR;
              else begin b_resp_q <= AXI_OKAY; k_q <= w_data_q; end
            end
            OFF_N: begin
              if (shadow_locked) b_resp_q <= AXI_SLVERR;
              else begin b_resp_q <= AXI_OKAY; n_q <= w_data_q; end
            end
            OFF_GROUP: begin
              if (shadow_locked) b_resp_q <= AXI_SLVERR;
              else begin b_resp_q <= AXI_OKAY; group_q <= w_data_q; end
            end
            OFF_W_STRIDE: begin
              if (shadow_locked) b_resp_q <= AXI_SLVERR;
              else begin b_resp_q <= AXI_OKAY; w_stride_q <= w_data_q; end
            end
            OFF_TAG: begin
              if (shadow_locked) b_resp_q <= AXI_SLVERR;
              else begin b_resp_q <= AXI_OKAY; tag_q <= w_data_q; end
            end

            default: b_resp_q <= AXI_SLVERR;  // undefined offset
          endcase
        end
      end
      if (b_valid_q && s_axil_bready) begin
        b_valid_q <= 1'b0;
      end

      // ---- read address capture + response ----
      if (s_axil_arvalid && s_axil_arready) begin
        ar_addr_q  <= s_axil_araddr[11:0];
        ar_valid_q <= 1'b1;
      end
      if (ar_valid_q && !r_valid_q) begin
        ar_valid_q <= 1'b0;
        r_valid_q  <= 1'b1;
        r_data_q   <= rdata_c;
        r_resp_q   <= rresp_c;
      end
      if (r_valid_q && s_axil_rready) begin
        r_valid_q <= 1'b0;
      end

      // ---- dispatch handshake to npu_ctl (C12) ----
      if (dispatch_pending_q && i_dispatch_ready) begin
        dispatch_pending_q <= 1'b0;
      end

      // ---- terminal record from npu_ctl (C24), NPU-06 ----
      // The only non-reset write of last_cycles_q: NPU-04 (rc4) "updates it to
      // T-H+1 through the same C24 terminal record that sets DONE or ERROR and
      // COMPLETED_TAG"; npu_ctl guarantees exactly one record per terminal
      // edge T (NPU-09(c)) and o_terminal_ready is constant 1, so the record
      // is consumed on the edge it is offered.
      if (i_terminal_valid) begin  // o_terminal_ready is constant 1
        busy_q <= 1'b0;
        if (i_terminal_error_code == 3'd0) begin
          done_q  <= 1'b1;
          error_q <= 1'b0;
        end else begin
          done_q  <= 1'b0;
          error_q <= 1'b1;
        end
        error_code_q    <= {29'd0, i_terminal_error_code};
        completed_tag_q <= i_terminal_tag;
        last_cycles_q   <= i_terminal_cycles;
      end
    end
  end

  // ---------------------------------------------------------------------
  // Dispatch outputs (C12): descriptor is immutable while busy_q is set, so
  // shadow registers double directly as the snapshot driven to npu_ctl.
  // ---------------------------------------------------------------------
  assign o_dispatch_valid    = dispatch_pending_q;
  assign o_dispatch_opcode   = opcode_q;
  assign o_dispatch_x_base   = x_base_q;
  assign o_dispatch_w_base   = w_base_q;
  assign o_dispatch_y_base   = y_base_q;
  assign o_dispatch_k        = k_q;
  assign o_dispatch_n        = n_q;
  assign o_dispatch_group    = group_q;
  assign o_dispatch_w_stride = w_stride_q;
  assign o_dispatch_tag      = tag_q;

  assign o_terminal_ready = 1'b1;

  // NPU-06: IRQ outputs are level (DONE & IRQ_ENABLE[0]) and (ERROR & IRQ_ENABLE[1]).
  assign o_done_irq  = done_q & irq_enable_q[0];
  assign o_error_irq = error_q & irq_enable_q[1];

endmodule

`default_nettype wire
