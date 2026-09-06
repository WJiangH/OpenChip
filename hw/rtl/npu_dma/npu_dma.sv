// npu_dma.sv — NPU AXI4 initiator (read X/W, write INT32 group results).
//
// Spec: docs/spec/llm-soc-v1/npu.md NPU-02/NPU-03/NPU-06 and §4, axi.md
// AXI-01..AXI-04/AXI-06/AXI-08, system.md SYS-12.
// Machine ICD: contract.json block "npu_dma"; connections
//   C03  npu_dma -> fabric        protocol axi4 (fixed_id 1)   -> m_axi_*
//   C13  npu_ctl -> npu_dma       protocol dispatch            -> i_dispatch_*
//   C14  npu_dma -> npu_local     protocol local_bytes         -> o_local_bytes_*
//   C16  npu_dot -> npu_dma       protocol group_result        -> i_group_result_*
//   C23  npu_dma -> npu_ctl       protocol dma_terminal        -> o_dma_terminal_*
//   C32  sys     -> npu_dma       protocol stop_issue          -> i_stop_new_transactions
//   CR12 sys     -> npu_dma       protocol clock_reset         -> clk / rst_n
// Every port below carries the contract.json field name of its protocol,
// lowercase, prefixed i_/o_ (AGENTS.md) or m_axi_ for the AXI4 initiator.
`default_nettype none

module npu_dma (
    // CR12 clock_reset {clk, rst_n}
    input wire clk,
    input wire rst_n,

    // C13 dispatch {valid, ready, opcode, x_base, w_base, y_base, k, n,
    //               group, w_stride, tag} — consumer side.
    input  wire        i_dispatch_valid,
    output logic       o_dispatch_ready,
    input  wire [31:0] i_dispatch_opcode,
    input  wire [31:0] i_dispatch_x_base,
    input  wire [31:0] i_dispatch_w_base,
    input  wire [31:0] i_dispatch_y_base,
    input  wire [31:0] i_dispatch_k,
    input  wire [31:0] i_dispatch_n,
    input  wire [31:0] i_dispatch_group,
    input  wire [31:0] i_dispatch_w_stride,
    input  wire [31:0] i_dispatch_tag,

    // C14 local_bytes {valid, ready, data, keep, kind, index, row} — producer.
    output logic        o_local_bytes_valid,
    input  wire         i_local_bytes_ready,
    output logic [31:0] o_local_bytes_data,
    output logic [ 3:0] o_local_bytes_keep,
    output logic [ 1:0] o_local_bytes_kind,
    output logic [11:0] o_local_bytes_index,
    output logic [11:0] o_local_bytes_row,

    // C16 group_result {valid, ready, data, row, group_index, last} — consumer.
    input  wire        i_group_result_valid,
    output logic       o_group_result_ready,
    input  wire [31:0] i_group_result_data,
    input  wire [11:0] i_group_result_row,
    input  wire [11:0] i_group_result_group_index,
    input  wire        i_group_result_last,

    // C23 dma_terminal {done, error, error_code} — producer, no handshake.
    output logic       o_dma_terminal_done,
    output logic       o_dma_terminal_error,
    output logic [2:0] o_dma_terminal_error_code,

    // C32 stop_issue {stop_new_transactions} — consumer, sticky (SYS-12).
    input wire i_stop_new_transactions,

    // C03 axi4 initiator (AXI-01 signal list, id_width 2, data_width 32).
    output logic        m_axi_awvalid,
    input  wire         m_axi_awready,
    output logic [31:0] m_axi_awaddr,
    output logic [ 1:0] m_axi_awid,
    output logic [ 7:0] m_axi_awlen,
    output logic [ 2:0] m_axi_awsize,
    output logic [ 1:0] m_axi_awburst,
    output logic        m_axi_awlock,
    output logic [ 3:0] m_axi_awcache,
    output logic [ 2:0] m_axi_awprot,
    output logic [ 3:0] m_axi_awqos,
    output logic        m_axi_wvalid,
    input  wire         m_axi_wready,
    output logic [31:0] m_axi_wdata,
    output logic [ 3:0] m_axi_wstrb,
    output logic        m_axi_wlast,
    input  wire         m_axi_bvalid,
    output logic        m_axi_bready,
    input  wire  [ 1:0] m_axi_bresp,
    input  wire  [ 1:0] m_axi_bid,
    output logic        m_axi_arvalid,
    input  wire         m_axi_arready,
    output logic [31:0] m_axi_araddr,
    output logic [ 1:0] m_axi_arid,
    output logic [ 7:0] m_axi_arlen,
    output logic [ 2:0] m_axi_arsize,
    output logic [ 1:0] m_axi_arburst,
    output logic        m_axi_arlock,
    output logic [ 3:0] m_axi_arcache,
    output logic [ 2:0] m_axi_arprot,
    output logic [ 3:0] m_axi_arqos,
    input  wire         m_axi_rvalid,
    output logic        m_axi_rready,
    input  wire  [31:0] m_axi_rdata,
    input  wire  [ 1:0] m_axi_rresp,
    input  wire  [ 1:0] m_axi_rid,
    input  wire         m_axi_rlast
);

  // ------------------------------------------------------------------
  // Fixed AXI attributes (AXI-02: aligned 32-bit beats, INCR, LEN 0..15,
  // LOCK/CACHE/QOS/PROT 0, NPU source ID 1).
  // ------------------------------------------------------------------
  localparam logic [1:0] AXI_ID   = 2'd1;
  localparam logic [2:0] AXI_SIZE = 3'd2;
  localparam logic [1:0] AXI_INCR = 2'd1;

  // Read sequencer states.
  localparam logic [2:0] RD_IDLE  = 3'd0;
  localparam logic [2:0] RD_SETUP = 3'd1;  // burst parameters settled, no VALID yet
  localparam logic [2:0] RD_AR    = 3'd2;  // ARVALID offered, waiting for ARREADY
  localparam logic [2:0] RD_DATA  = 3'd3;  // burst accepted, consuming R beats
  localparam logic [2:0] RD_DONE  = 3'd4;
  localparam logic [2:0] RD_STOP  = 3'd5;  // no new bursts (error / stop_issue)

  // Write sequencer states.
  localparam logic [2:0] WR_IDLE = 3'd0;
  localparam logic [2:0] WR_FILL = 3'd1;  // buffering a burst's W data (NPU-06)
  localparam logic [2:0] WR_SEND = 3'd2;  // AW + W offered
  localparam logic [2:0] WR_RESP = 3'd3;  // waiting for B
  localparam logic [2:0] WR_DONE = 3'd4;
  localparam logic [2:0] WR_STOP = 3'd5;

  // ------------------------------------------------------------------
  // Snapshotted descriptor (NPU-05: immutable until terminal). npu_ctl has
  // already validated opcode/shape/alignment/range, so this block performs
  // no descriptor checking (NPU-05 error codes 1..4 are the controller's).
  // ------------------------------------------------------------------
  logic [31:0] w_base_q;
  logic [31:0] y_base_q;
  logic [31:0] w_stride_q;
  logic [12:0] k_q;       // 1..4096 (NPU-01)
  logic [12:0] n_q;       // 1..4096 (NPU-01)
  logic [12:0] gcount_q;  // ceil(K/G), 1..4096 (NPU-02 Y layout)
  logic [10:0] nwords_q;  // round_up(K,4)/4, 1..1024 (NPU-02 X/W allocation)

  logic busy_q;
  logic done_q;
  logic error_q;
  logic [2:0] ecode_q;
  logic err_read_q;
  logic err_write_q;

  wire err_any_c = err_read_q | err_write_q;
  // SYS-12 stop_new_transactions and NPU-06 "stop offering new bursts" have
  // the same local effect: never assert a new AR/AW, never retract one.
  // ISSUE-npu_dma-05: provisional — a stop that is not caused by a DMA
  // response error produces no terminal at all; the command stays BUSY until
  // coordinated reset.
  wire stop_c = i_stop_new_transactions | err_any_c;

  wire dispatch_fire_c = i_dispatch_valid & o_dispatch_ready;
  assign o_dispatch_ready = ~busy_q;

  // ceil(K/G) with G a power of two in 1..4096 (NPU-01).
  logic [3:0] gshift_c;
  always_comb begin
    gshift_c = 4'd0;
    for (int gi = 0; gi < 13; gi++) begin
      if (i_dispatch_group[gi]) gshift_c = gi[3:0];
    end
  end
  wire [13:0] gsum_c   = {1'b0, i_dispatch_k[12:0]} + {1'b0, i_dispatch_group[12:0]} - 14'd1;
  wire [13:0] gcount_c = gsum_c >> gshift_c;
  wire [12:0] ksum_c   = i_dispatch_k[12:0] + 13'd3;  // round_up(K,4)

  // ------------------------------------------------------------------
  // Read engine: X first (kind 0, row 0), then W row by row (kind 1),
  // round_up(K,4) bytes each (NPU-02, npu.md §4 "Activation load of all
  // round_up(K,4) bytes precedes weight computation").
  // At most one read burst outstanding (AXI-04): the next AR is offered only
  // after the previous burst's RLAST beat has been consumed.
  // ------------------------------------------------------------------
  logic [2:0]  rd_state_q;
  logic [31:0] rd_addr_q;      // address of the next beat
  logic [10:0] rd_rem_q;       // 32-bit words still to fetch in this row
  logic [11:0] rd_index_q;     // byte coordinate k of the next beat's lane 0
  logic [11:0] rd_row_q;       // n (0 while fetching X)
  logic [31:0] rd_row_base_q;  // W_BASE + n*W_STRIDE, accumulated exactly
  logic        rd_kind_q;      // 0 = activation, 1 = weight
  logic        rd_done_q;
  logic        ar_valid_q;
  logic [31:0] ar_addr_q;
  logic [ 7:0] ar_len_q;

  // Burst length: <=16 beats (AXI-02 LEN 0..15), never crossing a 4 KiB
  // boundary (AXI-02). Every address_regions[] base/size in contract.json is
  // 4 KiB aligned, so a burst that does not cross a 4 KiB boundary cannot
  // cross a region boundary either; npu_ctl has already proved the whole
  // allocation lies inside one permitted region (NPU-02, SYS-04).
  wire [10:0] rd_to_4k_c = 11'd1024 - {1'b0, rd_addr_q[11:2]};
  wire [10:0] rd_cap_c   = (rd_rem_q < 11'd16) ? rd_rem_q : 11'd16;
  wire [10:0] rd_bw_c    = (rd_to_4k_c < rd_cap_c) ? rd_to_4k_c : rd_cap_c;
  wire [ 4:0] rd_len_c   = rd_bw_c[4:0] - 5'd1;

  // Fetched-word lane mask (npu.md §4): lane b maps to k=index+b and
  // keep[b]=1 only for k<K; padded fetched lanes have keep 0.
  wire [12:0] rd_k0_c = {1'b0, rd_index_q};
  wire [ 3:0] rd_keep_c = {(rd_k0_c + 13'd3) < k_q,
                           (rd_k0_c + 13'd2) < k_q,
                           (rd_k0_c + 13'd1) < k_q,
                           rd_k0_c < k_q};

  // One-entry output register towards npu_local; VALID is a flop, so it never
  // depends combinationally on i_local_bytes_ready (npu.md §4).
  logic        sk_valid_q;
  logic [31:0] sk_data_q;
  logic [ 3:0] sk_keep_q;
  logic [ 1:0] sk_kind_q;
  logic [11:0] sk_index_q;
  logic [11:0] sk_row_q;

  wire sk_room_c  = ~sk_valid_q | i_local_bytes_ready;
  // After any DMA error the output is invalid in its entirety, so read data is
  // discarded and RREADY stays high to drain the burst (NPU-06).
  wire r_fire_c   = m_axi_rvalid & m_axi_rready;
  wire rd_push_c  = r_fire_c & ~err_any_c & (m_axi_rresp == 2'b00);
  wire rd_last_row_c = ({1'b0, rd_row_q} == (n_q - 13'd1));

  assign m_axi_rready = (rd_state_q == RD_DATA) & (err_any_c | sk_room_c);

  assign o_local_bytes_valid = sk_valid_q;
  assign o_local_bytes_data  = sk_data_q;
  assign o_local_bytes_keep  = sk_keep_q;
  assign o_local_bytes_kind  = sk_kind_q;
  assign o_local_bytes_index = sk_index_q;
  assign o_local_bytes_row   = sk_row_q;

  assign m_axi_arvalid = ar_valid_q;
  assign m_axi_araddr  = ar_addr_q;
  assign m_axi_arlen   = ar_len_q;
  assign m_axi_arid    = AXI_ID;
  assign m_axi_arsize  = AXI_SIZE;
  assign m_axi_arburst = AXI_INCR;
  assign m_axi_arlock  = 1'b0;
  assign m_axi_arcache = 4'd0;
  assign m_axi_arprot  = 3'd0;
  assign m_axi_arqos   = 4'd0;

  // ------------------------------------------------------------------
  // Write engine: INT32 Y[n,g] little-endian at Y_BASE+4*(n*ceil(K/G)+g)
  // (NPU-02). The address is recomputed from the immutable descriptor and the
  // group_result row/group_index fields on every result, never from software
  // and never from an assumed emission order; consecutive results are merged
  // into one INCR burst only while their addresses stay contiguous.
  // NPU-06: an AW is offered only after the whole burst's W data is buffered
  // here, AWVALID and the first WVALID are asserted in the same cycle, and
  // neither waits for AWREADY (AXI-03).
  // Micro-architecture choice (not spec-mandated): a single 16x32-bit burst
  // buffer, i.e. results are back-pressured while a burst drains. Reads keep
  // running meanwhile — the read and write sequencers share no buffer and no
  // state, which is the disjoint-buffer overlap AXI-04 allows. The resulting
  // worst-case pause of the result stream is one burst, <=16 beats: even with
  // the slowest legal external model (AXI-06 initial latency 1024, per-beat
  // backpressure 1024) that is ~17k cycles, inside the 65536-cycle AXI-07
  // progress obligation that the stalled RREADY then inherits.
  // ------------------------------------------------------------------
  logic [2:0]  wr_state_q;
  // ISSUE-npu_dma-03: provisional — the burst write buffer lives here, not in
  // npu_local, because contract.json has no npu_local->npu_dma connection.
  // Data array, not control state: wbuf_q holds no meaning outside the burst
  // whose W beats it feeds, and wcount_q/widx_q (which do reset) gate every
  // read of it, so its contents are deliberately not reset.
  logic [31:0] wbuf_q [0:15];
  logic [ 4:0] wcount_q;   // 0..16 words currently buffered
  logic [31:0] wstart_q;   // address of wbuf_q[0]
  logic [31:0] wnext_q;    // address the next contiguous result must have
  logic        wfinal_q;   // buffered set contains the command's last result
  logic        wr_done_q;
  logic        aw_valid_q;
  logic        w_valid_q;
  logic        b_pending_q;
  logic [31:0] aw_addr_q;
  logic [ 7:0] aw_len_q;
  logic [ 3:0] widx_q;

  // One-entry staging register for group_result; also where the NPU-02 Y
  // address is formed (row*ceil(K/G)+group_index, then *4).
  logic        st_valid_q;
  logic [31:0] st_data_q;
  logic [31:0] st_addr_q;
  logic        st_last_q;

  wire [24:0] res_index_c = ({13'd0, i_group_result_row} * {12'd0, gcount_q})
                          + {13'd0, i_group_result_group_index};
  wire [31:0] res_addr_c  = y_base_q + {5'd0, res_index_c, 2'b00};

  // Append rules: contiguous, at most 16 beats, never across a 4 KiB boundary.
  wire wr_can_append_c = (wcount_q == 5'd0)
                       | ((st_addr_q == wnext_q) & (wcount_q < 5'd16)
                          & (st_addr_q[11:2] != 10'd0));
  wire wr_append_c = (wr_state_q == WR_FILL) & st_valid_q & wr_can_append_c;
  wire wr_close_c  = (wr_state_q == WR_FILL) & st_valid_q & ~stop_c
                   & ((~wr_can_append_c & (wcount_q != 5'd0))
                      | (wr_can_append_c & (st_last_q | (wcount_q == 5'd15))));

  wire st_fire_c = i_group_result_valid & o_group_result_ready;
  assign o_group_result_ready = busy_q & ~err_any_c & (~st_valid_q | wr_append_c);

  wire aw_clear_c = ~aw_valid_q | m_axi_awready;
  wire w_last_c   = (widx_q == aw_len_q[3:0]);
  wire w_clear_c  = ~w_valid_q | (m_axi_wready & w_last_c);

  assign m_axi_awvalid = aw_valid_q;
  assign m_axi_awaddr  = aw_addr_q;
  assign m_axi_awlen   = aw_len_q;
  assign m_axi_awid    = AXI_ID;
  assign m_axi_awsize  = AXI_SIZE;
  assign m_axi_awburst = AXI_INCR;
  assign m_axi_awlock  = 1'b0;
  assign m_axi_awcache = 4'd0;
  assign m_axi_awprot  = 3'd0;
  assign m_axi_awqos   = 4'd0;
  assign m_axi_wvalid  = w_valid_q;
  assign m_axi_wdata   = wbuf_q[widx_q];
  assign m_axi_wstrb   = 4'hf;                 // AXI-02: NPU strobes all one
  assign m_axi_wlast   = w_valid_q & w_last_c;
  assign m_axi_bready  = b_pending_q;

  // ISSUE-npu_dma-02: provisional — C23 dma_terminal has no handshake, so
  // done/error are driven as sticky levels: asserted on the terminal edge and
  // held until the next accepted dispatch or reset.
  assign o_dma_terminal_done       = done_q;
  assign o_dma_terminal_error      = error_q;
  assign o_dma_terminal_error_code = ecode_q;

  // Quiescence for NPU-06: no offered or accepted AXI work left.
  wire rd_quiet_c = (rd_state_q != RD_AR) & (rd_state_q != RD_DATA) & ~ar_valid_q;
  wire wr_quiet_c = ~aw_valid_q & ~w_valid_q & ~b_pending_q;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      w_base_q      <= 32'd0;
      y_base_q      <= 32'd0;
      w_stride_q    <= 32'd0;
      k_q           <= 13'd0;
      n_q           <= 13'd0;
      gcount_q      <= 13'd0;
      nwords_q      <= 11'd0;
      busy_q        <= 1'b0;
      done_q        <= 1'b0;
      error_q       <= 1'b0;
      ecode_q       <= 3'd0;
      err_read_q    <= 1'b0;
      err_write_q   <= 1'b0;
      rd_state_q    <= RD_IDLE;
      rd_addr_q     <= 32'd0;
      rd_rem_q      <= 11'd0;
      rd_index_q    <= 12'd0;
      rd_row_q      <= 12'd0;
      rd_row_base_q <= 32'd0;
      rd_kind_q     <= 1'b0;
      rd_done_q     <= 1'b0;
      ar_valid_q    <= 1'b0;
      ar_addr_q     <= 32'd0;
      ar_len_q      <= 8'd0;
      sk_valid_q    <= 1'b0;
      sk_data_q     <= 32'd0;
      sk_keep_q     <= 4'd0;
      sk_kind_q     <= 2'd0;
      sk_index_q    <= 12'd0;
      sk_row_q      <= 12'd0;
      wr_state_q    <= WR_IDLE;
      wcount_q      <= 5'd0;
      wstart_q      <= 32'd0;
      wnext_q       <= 32'd0;
      wfinal_q      <= 1'b0;
      wr_done_q     <= 1'b0;
      aw_valid_q    <= 1'b0;
      w_valid_q     <= 1'b0;
      b_pending_q   <= 1'b0;
      aw_addr_q     <= 32'd0;
      aw_len_q      <= 8'd0;
      widx_q        <= 4'd0;
      st_valid_q    <= 1'b0;
      st_data_q     <= 32'd0;
      st_addr_q     <= 32'd0;
      st_last_q     <= 1'b0;
    end else begin
      // ---------------- read sequencer ----------------
      case (rd_state_q)
        RD_SETUP: begin
          if (stop_c) begin
            rd_state_q <= RD_STOP;
          end else begin
            ar_valid_q <= 1'b1;
            ar_addr_q  <= rd_addr_q;
            ar_len_q   <= {3'd0, rd_len_c};
            rd_state_q <= RD_AR;
          end
        end
        RD_AR: begin
          // ARVALID, once offered, is retained until ARREADY even under
          // stop/error (NPU-06, SYS-12).
          if (m_axi_arready) begin
            ar_valid_q <= 1'b0;
            rd_state_q <= RD_DATA;
          end
        end
        RD_DATA: begin
          if (r_fire_c) begin
            rd_addr_q  <= rd_addr_q + 32'd4;
            rd_index_q <= rd_index_q + 12'd4;
            rd_rem_q   <= rd_rem_q - 11'd1;
            if (m_axi_rresp != 2'b00) err_read_q <= 1'b1;
            if (m_axi_rlast) begin
              if (rd_rem_q == 11'd1) begin
                // row / phase complete
                rd_index_q <= 12'd0;
                rd_rem_q   <= nwords_q;
                if (!rd_kind_q) begin
                  rd_kind_q     <= 1'b1;
                  rd_row_q      <= 12'd0;
                  rd_row_base_q <= w_base_q;
                  rd_addr_q     <= w_base_q;
                  rd_state_q    <= RD_SETUP;
                end else if (rd_last_row_c) begin
                  rd_done_q  <= 1'b1;
                  rd_state_q <= RD_DONE;
                end else begin
                  rd_row_q      <= rd_row_q + 12'd1;
                  rd_row_base_q <= rd_row_base_q + w_stride_q;
                  rd_addr_q     <= rd_row_base_q + w_stride_q;
                  rd_state_q    <= RD_SETUP;
                end
              end else begin
                rd_state_q <= RD_SETUP;
              end
            end
          end
        end
        default: begin
          rd_state_q <= rd_state_q;  // RD_IDLE / RD_DONE / RD_STOP: quiescent
        end
      endcase

      // ---------------- fetched-word output register ----------------
      if (sk_valid_q & i_local_bytes_ready) sk_valid_q <= 1'b0;
      if (rd_push_c) begin
        sk_valid_q <= 1'b1;
        sk_data_q  <= m_axi_rdata;
        sk_keep_q  <= rd_keep_c;
        sk_kind_q  <= {1'b0, rd_kind_q};
        sk_index_q <= rd_index_q;
        sk_row_q   <= rd_kind_q ? rd_row_q : 12'd0;
      end

      // ---------------- write sequencer ----------------
      case (wr_state_q)
        WR_FILL: begin
          if (wr_append_c) begin
            wbuf_q[wcount_q[3:0]] <= st_data_q;
            if (wcount_q == 5'd0) wstart_q <= st_addr_q;
            wnext_q  <= st_addr_q + 32'd4;
            wcount_q <= wcount_q + 5'd1;
            if (st_last_q) wfinal_q <= 1'b1;
            st_valid_q <= 1'b0;
          end
          if (wr_close_c) begin
            // Whole burst is buffered before AW is offered (NPU-06); AWVALID
            // and the first WVALID rise together and do not wait for AWREADY.
            aw_addr_q   <= (wr_append_c & (wcount_q == 5'd0)) ? st_addr_q : wstart_q;
            aw_len_q    <= wr_append_c ? {4'd0, wcount_q[3:0]}
                                       : {4'd0, wcount_q[3:0] - 4'd1};
            aw_valid_q  <= 1'b1;
            w_valid_q   <= 1'b1;
            widx_q      <= 4'd0;
            b_pending_q <= 1'b1;
            wr_state_q  <= WR_SEND;
          end
        end
        WR_SEND: begin
          // Offered AW/W are retained and completed from the local buffer even
          // under stop/error (NPU-06, AXI-03, SYS-12).
          if (aw_valid_q & m_axi_awready) aw_valid_q <= 1'b0;
          if (w_valid_q & m_axi_wready) begin
            if (w_last_c) w_valid_q <= 1'b0;
            else widx_q <= widx_q + 4'd1;
          end
          if (aw_clear_c & w_clear_c) wr_state_q <= WR_RESP;
        end
        WR_RESP: begin
          if (m_axi_bvalid & m_axi_bready) begin
            b_pending_q <= 1'b0;
            if (m_axi_bresp != 2'b00) begin
              err_write_q <= 1'b1;
              wr_state_q  <= WR_STOP;
            end else begin
              wcount_q <= 5'd0;
              if (wfinal_q) begin
                wr_done_q  <= 1'b1;
                wr_state_q <= WR_DONE;
              end else begin
                wr_state_q <= WR_FILL;
              end
            end
          end
        end
        default: begin
          wr_state_q <= wr_state_q;  // WR_IDLE / WR_DONE / WR_STOP
        end
      endcase

      // ---------------- group_result staging ----------------
      if (st_fire_c) begin
        st_valid_q <= 1'b1;
        st_data_q  <= i_group_result_data;
        st_addr_q  <= res_addr_c;
        st_last_q  <= i_group_result_last;
      end

      // ---------------- terminal reporting (NPU-06) ----------------
      if (busy_q) begin
        if (err_any_c) begin
          // Only after every offered/accepted transaction has drained through
          // its final R/B handshake. Buffered results are dropped: output after
          // any error is invalid in its entirety.
          if (rd_quiet_c & wr_quiet_c) begin
            busy_q  <= 1'b0;
            error_q <= 1'b1;
            ecode_q <= err_read_q ? 3'd5 : 3'd6;  // read error wins
          end
        end else if (rd_done_q & wr_done_q) begin
          busy_q <= 1'b0;
          done_q <= 1'b1;  // all output B responses were OKAY (AXI-08)
        end
      end

      // ---------------- dispatch (C13) ----------------
      // ISSUE-npu_dma-04: provisional — the first AR is offered once this
      // block's own dispatch handshake completes; npu_local's handshake is not
      // observable here.
      // Accepted only while idle; clears the previous terminal level and every
      // sequencer, which is what makes CLEAR-and-reuse after a terminal error
      // safe (NPU-06).
      if (dispatch_fire_c) begin
        w_base_q      <= i_dispatch_w_base;
        y_base_q      <= i_dispatch_y_base;
        w_stride_q    <= i_dispatch_w_stride;
        k_q           <= i_dispatch_k[12:0];
        n_q           <= i_dispatch_n[12:0];
        gcount_q      <= gcount_c[12:0];
        nwords_q      <= ksum_c[12:2];
        busy_q        <= 1'b1;
        done_q        <= 1'b0;
        error_q       <= 1'b0;
        ecode_q       <= 3'd0;
        err_read_q    <= 1'b0;
        err_write_q   <= 1'b0;
        rd_state_q    <= RD_SETUP;
        rd_addr_q     <= i_dispatch_x_base;
        rd_rem_q      <= ksum_c[12:2];
        rd_index_q    <= 12'd0;
        rd_row_q      <= 12'd0;
        rd_row_base_q <= i_dispatch_x_base;
        rd_kind_q     <= 1'b0;
        rd_done_q     <= 1'b0;
        ar_valid_q    <= 1'b0;
        sk_valid_q    <= 1'b0;
        wr_state_q    <= WR_FILL;
        wcount_q      <= 5'd0;
        wnext_q       <= 32'd0;
        wfinal_q      <= 1'b0;
        wr_done_q     <= 1'b0;
        aw_valid_q    <= 1'b0;
        w_valid_q     <= 1'b0;
        b_pending_q   <= 1'b0;
        widx_q        <= 4'd0;
        st_valid_q    <= 1'b0;
      end
    end
  end

  // Ports carried for ICD completeness (contract.json protocol field lists)
  // but not consumed here: npu_ctl validates the opcode and owns the tag, and
  // AXI-02 guarantees every response echoes the accepted ID (fixed 1).
  wire unused_ports = &{1'b0,
                        i_dispatch_opcode,
                        i_dispatch_tag,
                        i_dispatch_k[31:13],
                        i_dispatch_n[31:13],
                        i_dispatch_group[31:13],
                        m_axi_rid,
                        m_axi_bid,
                        // Bits that are zero or don't-care by construction:
                        // ceil(K/G)<=4096, round_up(K,4) low bits, and the
                        // burst-length cap that is provably <=16 beats.
                        gcount_c[13],
                        ksum_c[1:0],
                        rd_bw_c[10:5],
                        1'b0};

endmodule

`default_nettype wire
