// blink.sv — free-running LED blinker, tracer-bullet module for milestone M0.
// Spec: docs/spec/blink.md (BLINK-01..08).
`default_nettype none

module blink #(
    parameter int HALF_PERIOD = 25_000_000  // cycles between o_led toggles
) (
    input  wire clk,
    input  wire rst_n,
    output logic o_led
);

  // Width sized to hold HALF_PERIOD-1; clamp to 1 bit for HALF_PERIOD == 1
  // (where $clog2 would otherwise size to 0 bits).
  localparam int CNT_W = (HALF_PERIOD > 1) ? $clog2(HALF_PERIOD) : 1;

  logic [CNT_W-1:0] cnt;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      cnt   <= '0;
      o_led <= 1'b0;
    end else if (cnt == CNT_W'(HALF_PERIOD - 1)) begin
      cnt   <= '0;
      o_led <= ~o_led;
    end else begin
      cnt <= cnt + 1'b1;
    end
  end

endmodule

`default_nettype wire
