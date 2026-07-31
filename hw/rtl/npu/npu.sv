// npu.sv — 1x8 weight-streaming int8 GEMV NPU (ADR-0002 D1/D2).
// Spec: docs/spec/npu.md (NPU-01..23). Wishbone B4 pipelined CSR slave
// (§2.2) + dedicated weight-stream ingress port (§2.3) + IRQ mirrors (§2.5).
`default_nettype none

module npu #(
    parameter int WS_WIDTH = 32  // ingress port width, bits (§2.4; must divide C*8=64, multiple of 8)
) (
    input wire clk,
    input wire rst_n,

    // Wishbone B4 pipelined slave — CSR/descriptor window only (soc_1.md
    // §3.2, 0x0002_0000; top-level decoder passes only the 16-bit in-window
    // offset, NPU-02).
    input  wire        wb_cyc,
    input  wire        wb_stb,
    input  wire        wb_we,
    input  wire [15:0] wb_adr,
    input  wire [31:0] wb_dat_w,
    input  wire [ 3:0] wb_sel,
    output logic        wb_stall,
    output logic        wb_ack,
    output logic [31:0] wb_dat_r,
    output logic        wb_err,

    // Weight-stream ingress port (soc_1.md §4.2, npu.md §2.3)
    input  wire                i_ws_valid,
    input  wire [WS_WIDTH-1:0] i_ws_data,
    output logic                o_ws_ready,

    // IRQ outputs (§2.5) — level, mirror STATUS.DONE/ERR
    output logic o_irq_done,
    output logic o_irq_err
);

  // ---------------------------------------------------------------------
  // Parameters (§2.4)
  // ---------------------------------------------------------------------
  localparam int C              = 8;     // output lanes / MACs-per-fed-cycle, fixed (ADR-0002 D2)
  localparam int ACT_SRAM_BYTES = 2048;
  localparam int ASW            = 11;    // $clog2(ACT_SRAM_BYTES)
  localparam int BYTES_PER_WORD = WS_WIDTH / 8;
  localparam int POPS_PER_KSTEP = C / BYTES_PER_WORD;
  localparam int POP_W          = (POPS_PER_KSTEP > 1) ? $clog2(POPS_PER_KSTEP) : 1;
  localparam logic [POP_W-1:0] LAST_POP_IDX = POP_W'(POPS_PER_KSTEP - 1);

  // wb_sel is not honored (NPU-04): every accepted write updates the full
  // 32-bit register regardless of wb_sel. All registers are <= 16 bits
  // wide (§3), so wb_dat_w[31:16] is likewise never consumed. Sink both to
  // keep lint clean.
  wire unused_wb_sel     = |wb_sel;
  wire unused_wb_dat_w_hi = |wb_dat_w[31:16];

  // ---------------------------------------------------------------------
  // Register map (§3)
  // ---------------------------------------------------------------------
  localparam logic [15:0] ADDR_CTRL        = 16'h0000;
  localparam logic [15:0] ADDR_STATUS      = 16'h0004;
  localparam logic [15:0] ADDR_ERR_CODE    = 16'h0008;
  localparam logic [15:0] ADDR_K_LEN       = 16'h000C;
  localparam logic [15:0] ADDR_N_LEN       = 16'h0010;
  localparam logic [15:0] ADDR_ACT_BASE    = 16'h0014;
  localparam logic [15:0] ADDR_OUT_BASE    = 16'h0018;
  localparam logic [15:0] ADDR_SCALE_M     = 16'h001C;
  localparam logic [15:0] ADDR_SCALE_SHIFT = 16'h0020;
  localparam logic [15:0] ADDR_RESULT_IDX  = 16'h0024;
  localparam logic [15:0] ADDR_RESULT_VAL  = 16'h0028;

  // §5 ERR_CODE values
  localparam logic [2:0] ERR_NONE               = 3'd0;
  localparam logic [2:0] ERR_K_ZERO              = 3'd1;
  localparam logic [2:0] ERR_N_ZERO              = 3'd2;
  localparam logic [2:0] ERR_N_NOT_MULTIPLE_OF_C = 3'd3;
  localparam logic [2:0] ERR_ACT_RANGE           = 3'd4;
  localparam logic [2:0] ERR_OUT_RANGE           = 3'd5;
  localparam logic [2:0] ERR_BUSY_REJECT         = 3'd6;

  typedef enum logic [1:0] {
    S_IDLE,
    S_RUN,
    S_DRAIN
  } state_t;

  state_t state;

  // Descriptor staging registers (RW, live — firmware may reprogram the
  // next descriptor while an op is in flight; §4.3 latches a private copy
  // at dispatch, see op_* below).
  logic        mode_r;
  logic [15:0] k_len_r, n_len_r, scale_m_r;
  logic [10:0] act_base_r, out_base_r;
  logic [ 4:0] scale_shift_r;

  logic       status_busy, status_done, status_err;
  logic [2:0] err_code_r;

  logic [15:0] result_idx_r;
  logic [31:0] result_val_r;

  // Descriptor captured at dispatch (used throughout RUN/DRAIN)
  logic        op_mode;
  logic [15:0] op_k, op_n;
  logic [10:0] op_act_base, op_out_base;
  logic [15:0] op_m;
  logic [ 4:0] op_s;

  // Sequencer state
  logic [15:0]       k;
  logic [15:0]       g_base;
  logic [POP_W-1:0]  pop_idx;
  logic [       2:0] drain_lane;
  logic              argmax_first;

  // ---------------------------------------------------------------------
  // Wishbone slave (§2.2)
  // ---------------------------------------------------------------------
  wire wb_txn = wb_cyc && wb_stb;
  wire wb_wr  = wb_txn && wb_we;

  assign wb_stall = 1'b0;  // NPU-02: never backpressures
  assign wb_err   = 1'b0;  // NPU-05: unmapped-region errors are the top-level decoder's job

  wire ctrl_write  = wb_wr && (wb_adr == ADDR_CTRL);
  wire go_pulse    = ctrl_write && wb_dat_w[0];
  wire abort_pulse = ctrl_write && wb_dat_w[2];

  // NPU-03: ack exactly one cycle after every wb_cyc&&wb_stb
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      wb_ack <= 1'b0;
    end else begin
      wb_ack <= wb_txn;
    end
  end

  logic [31:0] rd_mux;
  always_comb begin
    unique case (wb_adr)
      ADDR_CTRL:        rd_mux = {29'b0, 1'b0, mode_r, 1'b0};
      ADDR_STATUS:      rd_mux = {29'b0, status_err, status_done, status_busy};
      ADDR_ERR_CODE:    rd_mux = {29'b0, err_code_r};
      ADDR_K_LEN:       rd_mux = {16'b0, k_len_r};
      ADDR_N_LEN:       rd_mux = {16'b0, n_len_r};
      ADDR_ACT_BASE:    rd_mux = {21'b0, act_base_r};
      ADDR_OUT_BASE:    rd_mux = {21'b0, out_base_r};
      ADDR_SCALE_M:     rd_mux = {16'b0, scale_m_r};
      ADDR_SCALE_SHIFT: rd_mux = {27'b0, scale_shift_r};
      ADDR_RESULT_IDX:  rd_mux = {16'b0, result_idx_r};
      ADDR_RESULT_VAL:  rd_mux = result_val_r;
      default:           rd_mux = 32'h0000_0000;  // NPU-05: unmapped offset reads 0
    endcase
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      wb_dat_r <= 32'h0;
    end else if (wb_txn) begin
      wb_dat_r <= rd_mux;
    end
  end

  // Descriptor RW registers — NPU-05: writes to unmapped offsets silently ignored
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      mode_r        <= 1'b0;
      k_len_r       <= 16'h0;
      n_len_r       <= 16'h0;
      act_base_r    <= 11'h0;
      out_base_r    <= 11'h0;
      scale_m_r     <= 16'h0;
      scale_shift_r <= 5'h0;
    end else if (wb_wr) begin
      unique case (wb_adr)
        ADDR_CTRL:        mode_r        <= wb_dat_w[1];
        ADDR_K_LEN:       k_len_r       <= wb_dat_w[15:0];
        ADDR_N_LEN:       n_len_r       <= wb_dat_w[15:0];
        ADDR_ACT_BASE:    act_base_r    <= wb_dat_w[10:0];
        ADDR_OUT_BASE:    out_base_r    <= wb_dat_w[10:0];
        ADDR_SCALE_M:     scale_m_r     <= wb_dat_w[15:0];
        ADDR_SCALE_SHIFT: scale_shift_r <= wb_dat_w[4:0];
        default: ;  // unmapped, or RO offset (STATUS/ERR_CODE/RESULT_*) — ignored
      endcase
    end
  end

  // ---------------------------------------------------------------------
  // §5 descriptor validity checks (priority order, NPU-21)
  // ---------------------------------------------------------------------
  wire [16:0] act_end = {6'b0, act_base_r} + {1'b0, k_len_r};
  wire [16:0] out_end = {6'b0, out_base_r} + {1'b0, n_len_r};

  wire desc_k_zero    = (k_len_r == 16'd0);
  wire desc_n_zero    = (n_len_r == 16'd0);
  wire desc_n_notmulc = (n_len_r[2:0] != 3'd0);
  wire desc_act_range = (act_end > 17'd2048);
  wire desc_out_range = (!wb_dat_w[1]) && (out_end > 17'd2048);

  wire go_valid       = (state == S_IDLE) && go_pulse &&
                         !desc_k_zero && !desc_n_zero && !desc_n_notmulc &&
                         !desc_act_range && !desc_out_range;

  // ---------------------------------------------------------------------
  // Sequencer combinational helpers
  // ---------------------------------------------------------------------
  wire [WS_WIDTH-1:0] wfifo_data;
  wire                 wfifo_valid;
  wire                 fifo_pop_en = (state == S_RUN) && wfifo_valid;

  wire last_pop   = (pop_idx == LAST_POP_IDX);
  wire last_k     = (k == op_k - 16'd1);
  wire last_group = (g_base + 16'd8) >= op_n;

  wire group_reset = go_valid ||
                      (state == S_DRAIN && drain_lane == 3'd7 && !last_group);

  // ---------------------------------------------------------------------
  // Activation SRAM addressing — port B read is 1-cycle-latency; the
  // address for step k (or the next group's k=0) is always driven one
  // cycle ahead of when its data is consumed, so no extra wait state is
  // needed beyond the FIFO's own availability (NPU-15/16).
  // ---------------------------------------------------------------------
  // k is provably < 2048 whenever a valid op is in flight (dispatch checks
  // act_base+k_len <= 2048), so the low ASW bits of k are exact.
  wire [ASW-1:0] act_addr_cur  = op_act_base + k[ASW-1:0];
  wire [ASW-1:0] act_addr_next = op_act_base + k[ASW-1:0] + 11'd1;

  logic [ASW-1:0] act_rd_addr;
  wire   [   7:0] act_rd_data;

  always_comb begin
    if (go_valid) begin
      act_rd_addr = act_base_r;
    end else if (state == S_RUN && fifo_pop_en && last_pop && !last_k) begin
      act_rd_addr = act_addr_next;
    end else if (state == S_DRAIN && drain_lane == 3'd7 && !last_group) begin
      act_rd_addr = op_act_base;
    end else begin
      act_rd_addr = act_addr_cur;
    end
  end

  // ---------------------------------------------------------------------
  // Requantiser (§4.1, NPU-11/12) — shared, driven by the current drain lane
  // ---------------------------------------------------------------------
  logic signed [31:0] acc[0:C-1];
  wire  signed [31:0] drain_acc_sel = acc[drain_lane];
  wire  signed [ 7:0] req_out;

  npu_requant u_requant (
      .i_acc  (drain_acc_sel),
      .i_m    (op_m),
      .i_shift(op_s),
      .o_val  (req_out)
  );

  // ---------------------------------------------------------------------
  // Activation SRAM output writeback (normal mode, §4.4/NPU-13) port A
  // ---------------------------------------------------------------------
  // g_base+drain_lane is provably < 2048 whenever mode==0 and sram_we is
  // asserted (dispatch checks out_base+n_len <= 2048 for normal mode).
  wire             sram_we      = (state == S_DRAIN) && (op_mode == 1'b0);
  wire [ASW-1:0]   sram_wr_addr = op_out_base + g_base[ASW-1:0] + {8'b0, drain_lane};
  wire [    7:0]   sram_wr_data = req_out;

  npu_act_sram #(
      .BYTES(ACT_SRAM_BYTES),
      .AW   (ASW)
  ) u_act_sram (
      .clk      (clk),
      .i_addr_a (sram_wr_addr),
      .i_we_a   (sram_we),
      .i_wdata_a(sram_wr_data),
      .i_addr_b (act_rd_addr),
      .o_rdata_b(act_rd_data)
  );

  // ---------------------------------------------------------------------
  // Weight-stream ingress FIFO (§2.3, NPU-06/07/14)
  // ---------------------------------------------------------------------
  npu_wfifo #(
      .WIDTH(WS_WIDTH)
  ) u_wfifo (
      .clk         (clk),
      .rst_n       (rst_n),
      .i_push_valid(i_ws_valid),
      .i_push_data (i_ws_data),
      .o_push_ready(o_ws_ready),
      .i_pop       (fifo_pop_en),
      .o_valid     (wfifo_valid),
      .o_data      (wfifo_data)
  );

  // ---------------------------------------------------------------------
  // MAC accumulator bank — 8 x 32-bit signed (NPU-09), bandwidth-following
  // (NPU-15): lane c advances as soon as its byte is unpacked from the
  // popped FIFO word, independent of the other lanes in the same pop.
  // ---------------------------------------------------------------------
  // Fixed 4-bit width (max value C-1=7) for the pop-to-lane base offset,
  // independent of WS_WIDTH — avoids a width-inference corner case at the
  // BYTES_PER_WORD=1 (WS_WIDTH=8) extreme.
  wire [3:0] pop_base = 4'(pop_idx) * 4'(BYTES_PER_WORD);

  genvar gc;
  generate
    for (gc = 0; gc < C; gc = gc + 1) begin : g_lane
      wire lane_active = fifo_pop_en &&
                          (4'(gc) >= pop_base) &&
                          (4'(gc) < pop_base + 4'(BYTES_PER_WORD));
      wire [2:0] byte_idx = 3'(4'(gc) - pop_base);

      wire signed [7:0]  w_byte      = wfifo_data[byte_idx*8+:8];
      wire signed [15:0] product     = w_byte * $signed(act_rd_data);
      wire signed [31:0] product_ext = {{16{product[15]}}, product};

      always_ff @(posedge clk) begin
        if (!rst_n) begin
          acc[gc] <= 32'sd0;
        end else if (group_reset) begin
          acc[gc] <= 32'sd0;
        end else if (lane_active) begin
          acc[gc] <= acc[gc] + product_ext;
        end
      end
    end
  endgenerate

  // ---------------------------------------------------------------------
  // Main sequencer FSM (§4.3)
  // ---------------------------------------------------------------------
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state        <= S_IDLE;
      status_busy  <= 1'b0;
      status_done  <= 1'b0;
      status_err   <= 1'b0;
      err_code_r   <= ERR_NONE;
      k            <= 16'h0;
      g_base       <= 16'h0;
      pop_idx      <= '0;
      drain_lane   <= 3'h0;
      argmax_first <= 1'b1;
      result_idx_r <= 16'h0;
      result_val_r <= 32'h0;
      op_mode      <= 1'b0;
      op_k         <= 16'h0;
      op_n         <= 16'h0;
      op_act_base  <= 11'h0;
      op_out_base  <= 11'h0;
      op_m         <= 16'h0;
      op_s         <= 5'h0;
    end else if (abort_pulse && state != S_IDLE) begin
      // NPU-19/§3.1 ABORT: force IDLE immediately, clear BUSY & in-flight state
      state       <= S_IDLE;
      status_busy <= 1'b0;
    end else if (go_pulse && state != S_IDLE) begin
      // NPU-21 BUSY_REJECT: write rejected, no dispatch, no other state change
      status_err <= 1'b1;
      err_code_r <= ERR_BUSY_REJECT;
    end else begin
      case (state)
        S_IDLE: begin
          if (go_pulse) begin
            // GO accepted (BUSY==0) — DONE/ERR clear the cycle GO is accepted
            status_done <= 1'b0;
            status_err  <= 1'b0;
            if (desc_k_zero) begin
              status_err <= 1'b1;
              err_code_r <= ERR_K_ZERO;
            end else if (desc_n_zero) begin
              status_err <= 1'b1;
              err_code_r <= ERR_N_ZERO;
            end else if (desc_n_notmulc) begin
              status_err <= 1'b1;
              err_code_r <= ERR_N_NOT_MULTIPLE_OF_C;
            end else if (desc_act_range) begin
              status_err <= 1'b1;
              err_code_r <= ERR_ACT_RANGE;
            end else if (desc_out_range) begin
              status_err <= 1'b1;
              err_code_r <= ERR_OUT_RANGE;
            end else begin
              err_code_r   <= ERR_NONE;
              op_mode      <= wb_dat_w[1];
              op_k         <= k_len_r;
              op_n         <= n_len_r;
              op_act_base  <= act_base_r;
              op_out_base  <= out_base_r;
              op_m         <= scale_m_r;
              op_s         <= scale_shift_r;
              state        <= S_RUN;
              status_busy  <= 1'b1;
              k            <= 16'h0;
              g_base       <= 16'h0;
              pop_idx      <= '0;
              argmax_first <= 1'b1;
            end
          end
        end

        S_RUN: begin
          if (fifo_pop_en) begin
            if (last_pop) begin
              pop_idx <= '0;
              if (last_k) begin
                state      <= S_DRAIN;
                drain_lane <= 3'h0;
              end else begin
                k <= k + 16'h1;
              end
            end else begin
              pop_idx <= pop_idx + 1'b1;
            end
          end
        end

        S_DRAIN: begin
          if (op_mode == 1'b1) begin
            if (argmax_first || (req_out > $signed(result_val_r[7:0]))) begin
              result_idx_r <= g_base + {13'b0, drain_lane};
              result_val_r <= {{24{req_out[7]}}, req_out};
              argmax_first <= 1'b0;
            end
          end

          if (drain_lane == 3'd7) begin
            if (last_group) begin
              state       <= S_IDLE;
              status_busy <= 1'b0;
              status_done <= 1'b1;
            end else begin
              state   <= S_RUN;
              g_base  <= g_base + 16'd8;
              k       <= 16'h0;
              pop_idx <= '0;
            end
          end else begin
            drain_lane <= drain_lane + 3'h1;
          end
        end

        default: state <= S_IDLE;
      endcase
    end
  end

  assign o_irq_done = status_done;
  assign o_irq_err  = status_err;

endmodule

`default_nettype wire
