// npu_local.sv — 4096-byte activation store + weight transfer buffer, and the
// 4-lane operand generator that feeds npu_dot.
//
// Spec: docs/spec/llm-soc-v1/npu.md NPU-01/NPU-02/NPU-03 and §4.
// Machine ICD: contract.json block "npu_local"; connections
//   C25  npu_ctl  -> npu_local   protocol dispatch      -> i_dispatch_*
//   C14  npu_dma  -> npu_local   protocol local_bytes   -> i_local_bytes_*
//   C15  npu_local-> npu_dot     protocol dot_operands  -> o_dot_operands_*
//   CR13 sys      -> npu_local   protocol clock_reset   -> clk / rst_n
// Every port below carries the contract.json field name of its protocol,
// lowercase, prefixed i_/o_ (AGENTS.md).
`default_nettype none

module npu_local (
    // CR13 clock_reset {clk, rst_n}
    input wire clk,
    input wire rst_n,

    // C25 dispatch {valid, ready, opcode, x_base, w_base, y_base, k, n,
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

    // C14 local_bytes {valid, ready, data, keep, kind, index, row} — consumer.
    input  wire        i_local_bytes_valid,
    output logic       o_local_bytes_ready,
    input  wire [31:0] i_local_bytes_data,
    input  wire [ 3:0] i_local_bytes_keep,
    input  wire [ 1:0] i_local_bytes_kind,
    input  wire [11:0] i_local_bytes_index,
    input  wire [11:0] i_local_bytes_row,

    // C15 dot_operands {valid, ready, x_data, w_data, keep, group_first,
    //                   group_last, row, group_index, command_last} — producer.
    output logic        o_dot_operands_valid,
    input  wire         i_dot_operands_ready,
    output logic [31:0] o_dot_operands_x_data,
    output logic [31:0] o_dot_operands_w_data,
    output logic [ 3:0] o_dot_operands_keep,
    output logic        o_dot_operands_group_first,
    output logic        o_dot_operands_group_last,
    output logic [11:0] o_dot_operands_row,
    output logic [11:0] o_dot_operands_group_index,
    output logic        o_dot_operands_command_last
);

  // ------------------------------------------------------------------
  // Storage (NPU-03: "a 4096-byte activation store and a minimum 64-byte
  // weight transfer buffer").
  // Both are data arrays, not control state: every activation word is written
  // by the current command before it is read (npu.md §4 orders the whole
  // activation load ahead of weight computation) and every weight-buffer entry
  // is written before the pointers that reset can address it. Their contents
  // are therefore deliberately not reset; all sequencing state below is.
  // ISSUE-npu_local-02 (CHANGE_ORDER_rc4: spec-gap, provisional confirmed) —
  // the arrays this exemption covers, named here per NPU-03 (rc4, R4-09):
  //   act_mem_q    — the 4096-byte activation store.
  //   wfifo_data_q — the 64-byte weight transfer buffer.
  //   wfifo_row_q, wfifo_idx_q — its tag arrays (row / first-byte coordinate
  //                  k of each buffered word).
  // NPU-03 (rc4, R4-09), verbatim: "The contents of the activation store,
  // weight transfer buffer and output write buffer are not reset and are
  // undefined after reset; every pointer, counter, valid, output register
  // and descriptor field resets (SYS-03), and DV shall not assume storage
  // contents after reset (rc4). This exemption from the every-flop-resets
  // house rule is conditional on the AGENTS.md storage-array clause
  // recommended in CHANGE_ORDER_rc4 §Rule-level; until that clause lands,
  // the module header shall name the array and cite this sentence
  // (rc4, R4-09)."
  // ------------------------------------------------------------------
  logic [31:0] act_mem_q [0:1023];  // 4096 bytes, word b holds X[4*idx+b]
  logic [31:0] wfifo_data_q [0:15]; // 64 bytes of weight transfer buffer
  logic [11:0] wfifo_row_q  [0:15]; // n of that word (local_bytes.row)
  logic [11:0] wfifo_idx_q  [0:15]; // first byte coordinate k (local_bytes.index)

  logic [3:0] wf_head_q;
  logic [3:0] wf_tail_q;
  logic [4:0] wf_cnt_q;

  // Descriptor fields this block needs (npu.md §4: "Local knows K,N,G,W_STRIDE
  // from its dispatch"). Addresses are not needed here because npu_dma tags
  // every fetched word with kind/index/row; W_STRIDE is likewise implicit in
  // that tagging (ISSUE-npu_local-01).
  logic [12:0] k_q;
  logic [12:0] n_q;
  logic [12:0] g_q;
  logic [12:0] gcount_q;   // ceil(K/G)
  logic [ 3:0] gshift_q;   // log2(G)
  logic [ 1:0] ss_q;       // log2(lanes per operand beat) = min(2, log2 G)
  logic        armed_q;

  // ISSUE-npu_local-03: provisional — an accepted dispatch is the only flush
  // this block has, so it re-initialises every sequencer unconditionally.
  // Dispatch is accepted unconditionally: exactly one command is live
  // (npu.md §4) and npu_ctl issues a new one only after the previous command
  // reached a terminal state, so a dispatch always supersedes whatever
  // sequencing state an aborted command left behind (NPU-06 CLEAR-and-reuse).
  assign o_dispatch_ready = 1'b1;
  wire dispatch_fire_c = i_dispatch_valid & o_dispatch_ready;

  logic [3:0] gshift_c;
  always_comb begin
    gshift_c = 4'd0;
    for (int gi = 0; gi < 13; gi++) begin
      if (i_dispatch_group[gi]) gshift_c = gi[3:0];
    end
  end
  wire [13:0] gsum_c   = {1'b0, i_dispatch_k[12:0]} + {1'b0, i_dispatch_group[12:0]} - 14'd1;
  wire [13:0] gcount_c = gsum_c >> gshift_c;
  wire [ 1:0] ss_c     = (gshift_c >= 4'd2) ? 2'd2 : gshift_c[1:0];

  // ------------------------------------------------------------------
  // Ingress from npu_dma (C14). Padded lanes (keep=0) are forced to zero on
  // the way in: NPU-02 forbids assuming W padding contains zero, and NPU-01
  // requires padded bytes to contribute zero products.
  // ------------------------------------------------------------------
  wire [31:0] in_masked_c = {i_local_bytes_keep[3] ? i_local_bytes_data[31:24] : 8'h00,
                             i_local_bytes_keep[2] ? i_local_bytes_data[23:16] : 8'h00,
                             i_local_bytes_keep[1] ? i_local_bytes_data[15: 8] : 8'h00,
                             i_local_bytes_keep[0] ? i_local_bytes_data[ 7: 0] : 8'h00};

  wire wf_full_c  = (wf_cnt_q == 5'd16);
  wire wf_empty_c = (wf_cnt_q == 5'd0);
  // Activation words always precede weight words, so the buffer is empty
  // during the activation phase and this single condition never stalls them.
  assign o_local_bytes_ready = armed_q & ~wf_full_c;
  wire in_fire_c = i_local_bytes_valid & o_local_bytes_ready;
  wire in_act_c  = in_fire_c & (i_local_bytes_kind == 2'd0);
  wire in_wgt_c  = in_fire_c & (i_local_bytes_kind != 2'd0);

  // ------------------------------------------------------------------
  // Operand generation (npu.md §4). The weight buffer head supplies the row
  // and the first byte coordinate of the word; sub_q walks the groups inside
  // that word. Lanes per beat S = min(4, G): for G>=4 a fetched word lies
  // wholly inside one group, for G=2 and G=1 the held word is reused for
  // several operand beats with disjoint keep masks, so products from different
  // groups never share an accumulator update.
  // ------------------------------------------------------------------
  logic [1:0] sub_q;  // byte offset of the current beat inside the held word

  wire [11:0] head_idx_c = wfifo_idx_q[wf_head_q];
  wire [11:0] head_row_c = wfifo_row_q[wf_head_q];
  wire [31:0] head_w_c   = wfifo_data_q[wf_head_q];

  wire [12:0] sstep_c  = 13'd1 << ss_q;
  wire [12:0] k_lo_c   = {1'b0, head_idx_c} + {11'd0, sub_q};
  wire [12:0] k_hi_c   = k_lo_c + sstep_c - 13'd1;
  wire [12:0] gmask_c  = g_q - 13'd1;                 // G is a power of two
  wire [12:0] gstart_c = k_lo_c & ~gmask_c;           // g*G
  wire [13:0] gfull_c  = {1'b0, gstart_c} + {1'b0, g_q};
  // Group tail is valid, not rounded up (NPU-01): end = min(K, (g+1)*G).
  wire [13:0] gend_c   = (gfull_c > {1'b0, k_q}) ? {1'b0, k_q} : gfull_c;
  wire [12:0] gidx_c   = k_lo_c >> gshift_q;
  wire [12:0] wbase_c  = {k_lo_c[12:2], 2'b00};

  wire gfirst_c = (k_lo_c == gstart_c);
  wire glast_c  = (({1'b0, k_hi_c} + 14'd1) >= gend_c);

  logic [3:0] keep_c;
  always_comb begin
    keep_c = 4'd0;
    for (int b = 0; b < 4; b++) begin
      logic [12:0] kb;
      kb = wbase_c + 13'(b);
      keep_c[b] = (kb >= k_lo_c) & (kb <= k_hi_c) & ({1'b0, kb} < gend_c);
    end
  end

  // command_last: group_last, final row and final group (npu.md §4).
  wire clast_c = glast_c & ({1'b0, head_row_c} == (n_q - 13'd1))
                         & (gidx_c == (gcount_q - 13'd1));

  wire [3:0] sub_next_c  = {2'd0, sub_q} + sstep_c[3:0];
  wire       word_done_c = (sub_next_c >= 4'd4);

  wire can_issue_c = armed_q & ~wf_empty_c & (k_lo_c < k_q);
  // Lanes past K in the last word of a row belong to no group at all; the word
  // is retired without an operand beat.
  wire skip_c      = armed_q & ~wf_empty_c & ~(k_lo_c < k_q);

  logic        op_valid_q;
  logic [31:0] op_x_q;
  logic [31:0] op_w_q;
  logic [ 3:0] op_keep_q;
  logic        op_gfirst_q;
  logic        op_glast_q;
  logic [11:0] op_row_q;
  logic [11:0] op_gidx_q;
  logic        op_clast_q;

  wire load_c = can_issue_c & (~op_valid_q | i_dot_operands_ready);
  wire pop_c  = skip_c | (load_c & word_done_c);

  assign o_dot_operands_valid        = op_valid_q;
  assign o_dot_operands_x_data       = op_x_q;
  assign o_dot_operands_w_data       = op_w_q;
  assign o_dot_operands_keep         = op_keep_q;
  assign o_dot_operands_group_first  = op_gfirst_q;
  assign o_dot_operands_group_last   = op_glast_q;
  assign o_dot_operands_row          = op_row_q;
  assign o_dot_operands_group_index  = op_gidx_q;
  assign o_dot_operands_command_last = op_clast_q;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      k_q         <= 13'd0;
      n_q         <= 13'd0;
      g_q         <= 13'd0;
      gcount_q    <= 13'd0;
      gshift_q    <= 4'd0;
      ss_q        <= 2'd0;
      armed_q     <= 1'b0;
      wf_head_q   <= 4'd0;
      wf_tail_q   <= 4'd0;
      wf_cnt_q    <= 5'd0;
      sub_q       <= 2'd0;
      op_valid_q  <= 1'b0;
      op_x_q      <= 32'd0;
      op_w_q      <= 32'd0;
      op_keep_q   <= 4'd0;
      op_gfirst_q <= 1'b0;
      op_glast_q  <= 1'b0;
      op_row_q    <= 12'd0;
      op_gidx_q   <= 12'd0;
      op_clast_q  <= 1'b0;
    end else begin
      // ---- ingress ----
      if (in_act_c) act_mem_q[i_local_bytes_index[11:2]] <= in_masked_c;
      if (in_wgt_c) begin
        wfifo_data_q[wf_tail_q] <= in_masked_c;
        wfifo_row_q[wf_tail_q]  <= i_local_bytes_row;
        wfifo_idx_q[wf_tail_q]  <= i_local_bytes_index;
        wf_tail_q               <= wf_tail_q + 4'd1;
      end

      // ---- operand issue ----
      if (op_valid_q & i_dot_operands_ready) op_valid_q <= 1'b0;
      if (load_c) begin
        op_valid_q  <= 1'b1;
        op_x_q      <= act_mem_q[wbase_c[11:2]];
        op_w_q      <= head_w_c;
        op_keep_q   <= keep_c;
        op_gfirst_q <= gfirst_c;
        op_glast_q  <= glast_c;
        op_row_q    <= head_row_c;
        op_gidx_q   <= gidx_c[11:0];
        op_clast_q  <= clast_c;
        sub_q       <= word_done_c ? 2'd0 : sub_next_c[1:0];
      end
      if (pop_c) begin
        wf_head_q <= wf_head_q + 4'd1;
        sub_q     <= 2'd0;
      end

      // ---- weight buffer occupancy ----
      if (in_wgt_c & ~pop_c) wf_cnt_q <= wf_cnt_q + 5'd1;
      else if (~in_wgt_c & pop_c) wf_cnt_q <= wf_cnt_q - 5'd1;

      // ---- dispatch (C25) ----
      if (dispatch_fire_c) begin
        k_q        <= i_dispatch_k[12:0];
        n_q        <= i_dispatch_n[12:0];
        g_q        <= i_dispatch_group[12:0];
        gcount_q   <= gcount_c[12:0];
        gshift_q   <= gshift_c;
        ss_q       <= ss_c;
        armed_q    <= 1'b1;
        wf_head_q  <= 4'd0;
        wf_tail_q  <= 4'd0;
        wf_cnt_q   <= 5'd0;
        sub_q      <= 2'd0;
        op_valid_q <= 1'b0;
      end
    end
  end

  // Ports carried for ICD completeness (contract.json protocol "dispatch")
  // but not consumed here: npu_ctl validates the opcode and owns the tag, and
  // all addressing reaches this block as local_bytes kind/index/row tags.
  wire unused_ports = &{1'b0,
                        i_dispatch_opcode,
                        i_dispatch_tag,
                        i_dispatch_x_base,
                        i_dispatch_w_base,
                        i_dispatch_y_base,
                        i_dispatch_w_stride,
                        i_dispatch_k[31:13],
                        i_dispatch_n[31:13],
                        i_dispatch_group[31:13],
                        gcount_c[13],
                        gidx_c[12],
                        1'b0};

endmodule

`default_nettype wire
