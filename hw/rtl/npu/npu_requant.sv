// npu_requant.sv — fixed-point requantiser: sat8(round((acc*M) >> s)).
// Spec: docs/spec/npu.md §4.1, NPU-11 (round-half-away-from-zero rounding),
// NPU-12 (signed-int8 saturate).
`default_nettype none

module npu_requant (
    input  wire signed [31:0] i_acc,    // final 32-bit signed lane accumulator
    input  wire        [15:0] i_m,      // SCALE_M, unsigned 16-bit
    input  wire        [ 4:0] i_shift,  // SCALE_SHIFT, unsigned 5-bit (0..31)
    output logic signed [7:0] o_val     // sat8(round((acc*M) >> shift))
);

  // t = acc * M — 32-bit signed x 16-bit unsigned (zero-extended to a
  // non-negative 17-bit signed operand), full-precision 48-bit signed
  // product (worst case |t| < 2^47, fits with margin).
  logic signed [31:0] acc_s;
  logic signed [16:0] m_s;
  logic signed [47:0] t;

  assign acc_s = i_acc;
  assign m_s   = {1'b0, i_m};
  assign t     = acc_s * m_s;

  logic        [46:0] mag;
  logic        [46:0] half;
  logic        [46:0] rounded_mag;
  logic signed [48:0] rounded;

  always_comb begin
    half = 47'd0;
    mag  = t[47] ? (~t[46:0] + 47'd1) : t[46:0];

    if (i_shift == 5'd0) begin
      rounded_mag = mag;
    end else begin
      half        = 47'd1 << (i_shift - 5'd1);
      rounded_mag = (mag + half) >> i_shift;
    end

    rounded = t[47] ? -{2'b00, rounded_mag} : {2'b00, rounded_mag};

    if (rounded > 49'sd127) begin
      o_val = 8'sd127;
    end else if (rounded < -49'sd128) begin
      o_val = -8'sd128;
    end else begin
      o_val = rounded[7:0];
    end
  end

endmodule

`default_nettype wire
