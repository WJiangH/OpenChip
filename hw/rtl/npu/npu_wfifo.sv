// npu_wfifo.sv — 2-deep weight-stream ingress FIFO.
// Spec: docs/spec/npu.md §2.3 (NPU-06/07), soc_1.md SOC1-11 (stall, never
// drop). o_push_ready deasserts only when both slots hold unconsumed data.
`default_nettype none

module npu_wfifo #(
    parameter int WIDTH = 32
) (
    input  wire clk,
    input  wire rst_n,

    input  wire             i_push_valid,
    input  wire [WIDTH-1:0] i_push_data,
    output logic            o_push_ready,

    input  wire         i_pop,
    output logic         o_valid,
    output logic [WIDTH-1:0] o_data
);

  logic [WIDTH-1:0] slot0, slot1;
  logic             slot0_v, slot1_v;

  wire push_en = i_push_valid && o_push_ready;
  wire pop_en  = i_pop && slot0_v;

  assign o_push_ready = !(slot0_v && slot1_v);
  assign o_valid       = slot0_v;
  assign o_data        = slot0;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      slot0_v <= 1'b0;
      slot1_v <= 1'b0;
      slot0   <= '0;
      slot1   <= '0;
    end else begin
      case ({push_en, pop_en})
        2'b01: begin  // pop only: shift slot1 -> slot0
          slot0   <= slot1;
          slot0_v <= slot1_v;
          slot1_v <= 1'b0;
        end
        2'b10: begin  // push only
          if (!slot0_v) begin
            slot0   <= i_push_data;
            slot0_v <= 1'b1;
          end else begin
            slot1   <= i_push_data;
            slot1_v <= 1'b1;
          end
        end
        2'b11: begin  // push and pop in the same cycle
          slot0   <= slot1_v ? slot1 : i_push_data;
          slot0_v <= 1'b1;
          slot1   <= i_push_data;
          slot1_v <= slot1_v;
        end
        default: begin  // 2'b00: hold
        end
      endcase
    end
  end

endmodule

`default_nettype wire
