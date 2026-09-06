// npu_dot.sv — NPU grouped signed-dot datapath: four parallel signed INT8xINT8
// lanes, signed reduction, one independent signed INT32 group accumulator.
//
// Spec (the only source of behaviour):
//   docs/spec/llm-soc-v1/npu.md  §1 NPU-01, NPU-02, NPU-03
//   docs/spec/llm-soc-v1/npu.md  §4 "Internal partition interface semantics"
//   docs/spec/llm-soc-v1/contract.json (machine ICD; wins for names/widths)
//     blocks[].id          "npu_dot" — "four signed-byte products, grouped INT32 sum"
//     connections C15      npu_local -> npu_dot, protocol "dot_operands"
//     connections C16      npu_dot   -> npu_dma, protocol "group_result"
//     connections CR14     sys       -> npu_dot, protocol "clock_reset"
//
// Port naming: "<i_|o_><protocol>_<field>", where every <field> is spelled
// exactly as contract.json protocols.<protocol>.signals lists it, and the
// direction prefix follows the source/target roles of C15/C16.
//
// Deliberately NOT present (NPU-01: "No bias, requantization, rounding,
// saturation or scale multiplication occurs in this opcode"): no bias adder,
// no rounding, no saturation/clamp, no requantizer, no scale multiplier.
// The legacy Wishbone NPU's requantizer is a different design (npu.md line 3).
//
// Structural identity (NPU-03): this datapath is the same for every legal
// K, N, G — including G=1 and incomplete final groups. K/N/G never reach this
// module; only npu_local's group_first/group_last/keep control bits differ.
`default_nettype none

module npu_dot (
    // CR14 clock_reset {clk, rst_n} — synchronous, active-low reset.
    input  wire         clk,
    input  wire         rst_n,

    // C15 npu_local -> npu_dot, protocol "dot_operands"
    // {valid, ready, x_data[32], w_data[32], keep[4], group_first, group_last,
    //  row[12], group_index[12], command_last}
    input  wire         i_dot_operands_valid,
    output logic        o_dot_operands_ready,
    input  wire  [31:0] i_dot_operands_x_data,
    input  wire  [31:0] i_dot_operands_w_data,
    input  wire   [3:0] i_dot_operands_keep,
    input  wire         i_dot_operands_group_first,
    input  wire         i_dot_operands_group_last,
    input  wire  [11:0] i_dot_operands_row,
    input  wire  [11:0] i_dot_operands_group_index,
    input  wire         i_dot_operands_command_last,

    // C16 npu_dot -> npu_dma, protocol "group_result"
    // {valid, ready, data[32], row[12], group_index[12], last}
    output logic        o_group_result_valid,
    input  wire         i_group_result_ready,
    output logic [31:0] o_group_result_data,
    output logic [11:0] o_group_result_row,
    output logic [11:0] o_group_result_group_index,
    output logic        o_group_result_last
);

  // NPU-03: "four parallel signed byte multipliers feeding a signed reduction
  // and INT32 accumulation". The lane count is fixed at four by the spec and by
  // the 32-bit x_data/w_data/4-bit keep widths of contract.json "dot_operands";
  // it is written out explicitly below rather than parameterised.

  // ---------------------------------------------------------------------------
  // Width / overflow derivation (NPU-01) — recorded, not enforced by logic.
  //
  //   X[k], W[n,k] are signed two's-complement INT8, range -128..127.
  //   Per-lane product extremes: (-128)*(-128) = +16384 (max),
  //                              (-128)*( 127) = -16256 (min).
  //   So |product| <= 16384 and every product is EXACT in signed INT16
  //   (INT16 range -32768..32767). No product can overflow, ever.
  //
  //   One operand beat sums the four lane products:
  //     |beat_sum| <= 4 * 16384 = 65536, exact in signed 18 bits (+/-131072).
  //
  //   One group accumulates at most min(K, G) <= 4096 products (NPU-01 bounds
  //   1<=K<=4096 and G a power of two in 1..4096; a tail group is shorter, so
  //   4096 is the worst case):
  //     |group sum| <= 4096 * 16384 = 67108864 = 2^26,
  //   which is the "Maximum absolute sum <= 4096*16384 = 67108864" of NPU-01.
  //   Signed INT32 spans -2147483648..2147483647 = +/-2^31, i.e. 5 binary
  //   digits of headroom over 2^26. NPU-01 states "no valid command overflows
  //   INT32" and forbids saturation, so there is deliberately no saturation,
  //   clamp or overflow-flag logic below: plain two's-complement wrap on a
  //   32-bit accumulator is the specified behaviour.
  // ---------------------------------------------------------------------------

  // --- lane products ---------------------------------------------------------
  // npu.md §4: "lane b maps to k=index+b" on the fetched-word interface, and
  // npu_local forwards the same lane order here, so byte lane b of x_data/w_data
  // pairs with byte lane b of w_data.
  //
  // NPU-02: "padded bytes contribute zero products. No assumption that W
  // padding contains zero is allowed." npu.md §4: "keep bits select valid
  // products ... Invalid lanes contribute zero". Hence the keep mask forces the
  // PRODUCT to zero; the operand bytes themselves are treated as arbitrary.
  //
  // One lane. The INT8 operands are sign-extended to 16 bits by explicit bit
  // replication (not by a cast) BEFORE multiplying, so the multiply is a full
  // signed 8x8 product held exactly in INT16 (see derivation above). Written as
  // a function purely so the four lanes are provably identical; it is
  // combinational, automatic and holds no state.
  function automatic logic signed [15:0] lane_product(input logic [7:0] x_byte,
                                                      input logic [7:0] w_byte,
                                                      input logic       keep_bit);
    logic signed [15:0] x_ext;
    logic signed [15:0] w_ext;
    begin
      x_ext = {{8{x_byte[7]}}, x_byte};
      w_ext = {{8{w_byte[7]}}, w_byte};
      lane_product = keep_bit ? (x_ext * w_ext) : 16'sd0;
    end
  endfunction

  logic signed [15:0] prod0;
  logic signed [15:0] prod1;
  logic signed [15:0] prod2;
  logic signed [15:0] prod3;

  assign prod0 = lane_product(i_dot_operands_x_data[7:0], i_dot_operands_w_data[7:0],
                              i_dot_operands_keep[0]);
  assign prod1 = lane_product(i_dot_operands_x_data[15:8], i_dot_operands_w_data[15:8],
                              i_dot_operands_keep[1]);
  assign prod2 = lane_product(i_dot_operands_x_data[23:16], i_dot_operands_w_data[23:16],
                              i_dot_operands_keep[2]);
  assign prod3 = lane_product(i_dot_operands_x_data[31:24], i_dot_operands_w_data[31:24],
                              i_dot_operands_keep[3]);

  // --- signed reduction of one beat -----------------------------------------
  // NPU-03: "four parallel signed byte multipliers feeding a signed reduction".
  // Integer addition is associative, so the reduction order is immaterial.
  logic signed [17:0] beat_sum;

  // 18'(x) is a size cast: IEEE 1800 keeps the operand's signedness, so a
  // signed [15:0] product is SIGN-extended to 18 bits. The casts are written
  // out because Verilator -Wall (WIDTHEXPAND) rejects the implicit widening.
  assign beat_sum = 18'(prod0) + 18'(prod1) + 18'(prod2) + 18'(prod3);

  // --- group accumulator -----------------------------------------------------
  // NPU-01: "each independent group accumulator signed INT32 initialized to
  // zero". npu.md §4: "group_first clears the accumulator before that beat's
  // products", so a beat with group_first=1 adds its products to zero, not to
  // the previous group's total. A beat with group_first=1 and group_last=1
  // (single-beat group, e.g. G<=4) is therefore handled by the same expression.
  logic signed [31:0] acc_q;
  logic signed [31:0] acc_base;
  logic signed [31:0] acc_next;

  always_comb begin
    acc_base = i_dot_operands_group_first ? 32'sd0 : acc_q;
    // 32'(beat_sum) sign-extends the signed [17:0] beat sum to 32 bits (size
    // cast preserves signedness); then a plain two's-complement add.
    acc_next = acc_base + 32'(beat_sum);
  end

  // --- result register (C16 payload) ----------------------------------------
  // ISSUE-npu_dot-01: provisional. NPU-06 requires that "no ... unconsumed
  // result remains" before an error terminal, but contract.json gives npu_dot
  // no status output and no flush input, so the only drain path is npu_dma
  // asserting i_group_result_ready. Implemented as exactly the C15/C16 fields
  // the contract lists, with at most one result outstanding. See ISSUES.md.
  logic        result_valid_q;
  logic [31:0] result_data_q;
  logic [11:0] result_row_q;
  logic [11:0] result_group_index_q;
  logic        result_last_q;

  // Handshake rules (npu.md §4: "no combinational VALID dependence on READY;
  // payload remains stable when stalled"):
  //   o_dot_operands_ready is a function of a REGISTER only — it depends
  //   neither on i_dot_operands_valid nor on i_group_result_ready.
  //   o_group_result_valid is a register.
  //   The C16 payload registers change only on an accepted operand beat, and
  //   an operand beat can only be accepted while the result register is empty,
  //   so a stalled result is held bit-stable until i_group_result_ready.
  assign o_dot_operands_ready = !result_valid_q;

  logic operand_fire;
  logic result_fire;

  assign operand_fire = i_dot_operands_valid && o_dot_operands_ready;
  assign result_fire  = o_group_result_valid && i_group_result_ready;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      acc_q                <= 32'sd0;
      result_valid_q       <= 1'b0;
      result_data_q        <= 32'd0;
      result_row_q         <= 12'd0;
      result_group_index_q <= 12'd0;
      result_last_q        <= 1'b0;
    end else begin
      if (result_fire) begin
        result_valid_q <= 1'b0;
      end
      if (operand_fire) begin
        // NPU-01: accumulator is reset to zero at group start; clearing it on
        // group_last as well makes the idle state deterministic and agrees
        // with the group_first clear of the next group.
        acc_q <= i_dot_operands_group_last ? 32'sd0 : acc_next;

        if (i_dot_operands_group_last) begin
          // npu.md §4: "group_last causes one INT32 result" — exactly one
          // C16 beat per group, carrying that group's (row, group_index).
          result_valid_q       <= 1'b1;
          result_data_q        <= acc_next;
          result_row_q         <= i_dot_operands_row;
          result_group_index_q <= i_dot_operands_group_index;
          // npu.md §4 / contract.json dot_operands.semantics: "command_last iff
          // group_last and final descriptor row/group; forwarded to
          // group_result.last". Dot "retains this marker with the accumulated
          // result and forwards it as group_result.last, including under result
          // backpressure" — it is registered alongside the data, so a stalled
          // result keeps its marker.
          result_last_q        <= i_dot_operands_command_last;
        end
      end
    end
  end

  // result_fire and operand_fire are mutually exclusive by construction
  // (operand_fire requires result_valid_q==0, result_fire requires it ==1), so
  // the two result_valid_q assignments above never race.

  assign o_group_result_valid       = result_valid_q;
  assign o_group_result_data        = result_data_q;
  assign o_group_result_row         = result_row_q;
  assign o_group_result_group_index = result_group_index_q;
  assign o_group_result_last        = result_last_q;

  // ---------------------------------------------------------------------------
  // Pipeline depth and result ordering
  //
  // Depth: ONE clock. A result becomes visible on C16 in the cycle after the
  // accepted operand beat that carried group_last. There is no deeper pipeline
  // and no reorder buffer.
  //
  // Ordering: this module holds exactly one in-flight group result. Operand
  // beats are accepted only while that register is empty
  // (o_dot_operands_ready = !result_valid_q), so the first beat of group i+1
  // cannot be accepted until the result of group i has been handshaken away.
  // Group results therefore leave on C16 in exactly the order npu_local
  // presented the groups, which npu.md §4 fixes ("No group interleaving is
  // allowed") and NPU-02 fixes as g fastest within n — the (n,g) order the
  // write path expects for Y at Y_BASE+4*(n*ceil(K/G)+g). The ordering argument
  // uses only the single-result-outstanding property, not the latency: adding
  // or removing pipeline stages inside the lanes could not reorder results.
  //
  // Cost of the simple form: at least one idle operand cycle per group. NPU-03:
  // "Implementation may use more cycles but not change results" and "No cycle
  // count per dot is an architectural correctness guarantee."
  // ---------------------------------------------------------------------------

endmodule

`default_nettype wire
