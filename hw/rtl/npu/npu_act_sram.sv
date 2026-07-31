// npu_act_sram.sv — behavioral placeholder for the 2 kB activation SRAM.
// Spec: docs/spec/npu.md §2.4 (ACT_SRAM_BYTES), §7 Q3 — ADR-0002 D5 commits
// this to the sky130_sram_2kbyte_1rw1r_32x512_8 OpenRAM macro; the backend
// role swaps this array for that hard macro at PD intake. Port shape (1
// read-write port A, 1 read-only port B, synchronous 1-cycle read latency,
// byte-addressed) matches the macro's behavior so the swap is drop-in.
//
// Per npu.md NPU-01, the macro's data contents are not required to reset
// (only the sequencer's addressing/control state resets, in npu.sv) — this
// module intentionally has no rst_n port.
`default_nettype none

module npu_act_sram #(
    parameter int BYTES = 2048,
    parameter int AW    = 11
) (
    input wire clk,

    // Port A: read-write (requantised output writeback, normal mode)
    input wire [AW-1:0] i_addr_a,
    input wire           i_we_a,
    input wire [   7:0] i_wdata_a,

    // Port B: read-only (activation-vector reads, broadcast per k-step)
    input  wire [AW-1:0] i_addr_b,
    output logic [  7:0] o_rdata_b
);

  logic [7:0] mem[0:BYTES-1];

  always_ff @(posedge clk) begin
    if (i_we_a) mem[i_addr_a] <= i_wdata_a;
  end

  always_ff @(posedge clk) begin
    o_rdata_b <= mem[i_addr_b];
  end

endmodule

`default_nettype wire
