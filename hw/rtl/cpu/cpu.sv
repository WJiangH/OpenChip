// cpu.sv — application CPU wrapper: pinned PicoRV32 native core (hw/ip/picorv32).
//
// Spec: docs/spec/llm-soc-v1/system.md SYS-02 (RV32IM native core, no caches/MMU,
// reset vector 0x00000000, IRQ vector 0x00000100, stack 0x10040000), SYS-10 (PicoRV32
// q-register IRQ ABI, MASKED_IRQ/LATCHED_IRQ binding), SYS-12 (common rst_n for sticky
// fault metadata, cpu_local_rst_n for the core only; trap reported as reason 4 with
// address 0; o_cpu_trap mirrors trap directly);
// docs/spec/llm-soc-v1/dependencies.md "CPU parameter binding";
// docs/spec/llm-soc-v1/contract.json connections C01 (native to cpu_bridge),
// C20..C22 (level IRQ into irq[4..6]), C26 (fault_event to sys), CR00 (cpu_clock_reset).
//
// The core file hw/ip/picorv32/picorv32.v is byte-frozen imported IP; house style
// applies to this wrapper only. Wiring plus the SYS-12 sticky trap latch is all the
// logic here: no protocol translation, that is cpu_bridge.
`default_nettype none

module cpu (
    input wire clk,
    // Common (coordinated) reset — sticky fault metadata only (SYS-12).
    input wire rst_n,
    // Local CPU reset — the PicoRV32 core only (SYS-07/SYS-12, contract cpu_clock_reset).
    input wire i_cpu_local_rst_n,

    // C01 native memory initiator port (contract.json protocols.native)
    output logic        o_mem_valid,
    output logic        o_mem_instr,
    input  wire         i_mem_ready,
    output logic [31:0] o_mem_addr,
    output logic [31:0] o_mem_wdata,
    output logic [ 3:0] o_mem_wstrb,
    input  wire  [31:0] i_mem_rdata,

    // C20..C22 level IRQ inputs (bits 4/5/6 used; SYS-09/SYS-10) and PicoRV32 eoi
    input  wire  [31:0] i_irq,
    output logic [31:0] o_eoi,

    // Direct trap mirror (SYS-01 o_cpu_trap, SYS-12 "mirrors CPU trap")
    output logic o_trap,

    // ENABLE_TRACE=1 integration-evidence trace port (dependencies.md)
    output logic        o_trace_valid,
    output logic [35:0] o_trace_data,

    // C26 fault_event to sys (SYS-12: sticky, no READY, reason 4 = core trap,
    // address 0; cleared only by common rst_n)
    output logic        o_fault_valid,
    output logic [ 2:0] o_fault_reason,
    output logic [31:0] o_fault_addr
);

  // --- Core trap reason (SYS-07: "core trap reason=4") -----------------------
  localparam logic [2:0] FaultReasonTrap = 3'd4;

  logic core_trap;
  logic fault_valid_q;

  // Unused PicoRV32 outputs: the look-ahead memory interface (the registered
  // mem_* port is the contract native port, protocols.native) and the external
  // PCPI initiator side (ENABLE_PCPI=0 — the multiplier/divider are internal).
  logic        mem_la_read;
  logic        mem_la_write;
  logic [31:0] mem_la_addr;
  logic [31:0] mem_la_wdata;
  logic [ 3:0] mem_la_wstrb;
  logic        pcpi_valid;
  logic [31:0] pcpi_insn;
  logic [31:0] pcpi_rs1;
  logic [31:0] pcpi_rs2;

  // Parameter binding is exactly dependencies.md "CPU parameter binding".
  // LATCHED_MEM_RDATA is the only upstream parameter that list does not name; it
  // retains the pinned upstream default 0 (mem_rdata sampled in the mem_ready cycle).
  picorv32 #(
      .ENABLE_COUNTERS     (1),
      .ENABLE_COUNTERS64   (1),
      .ENABLE_REGS_16_31   (1),
      .ENABLE_REGS_DUALPORT(1),
      .TWO_STAGE_SHIFT     (1),
      .BARREL_SHIFTER      (0),
      .TWO_CYCLE_COMPARE   (0),
      .TWO_CYCLE_ALU       (0),
      .COMPRESSED_ISA      (0),
      .CATCH_MISALIGN      (1),
      .CATCH_ILLINSN       (1),
      .ENABLE_PCPI         (0),
      .ENABLE_MUL          (1),
      .ENABLE_FAST_MUL     (0),
      .ENABLE_DIV          (1),
      .ENABLE_IRQ          (1),
      .ENABLE_IRQ_QREGS    (1),
      .ENABLE_IRQ_TIMER    (0),
      .ENABLE_TRACE        (1),
      .REGS_INIT_ZERO      (0),
      .MASKED_IRQ          (32'hffff_ff8f),
      .LATCHED_IRQ         (32'h0000_0000),
      .PROGADDR_RESET      (32'h0000_0000),
      .PROGADDR_IRQ        (32'h0000_0100),
      .STACKADDR           (32'h1004_0000)
  ) u_picorv32 (
      .clk   (clk),
      .resetn(i_cpu_local_rst_n),
      .trap  (core_trap),

      .mem_valid(o_mem_valid),
      .mem_instr(o_mem_instr),
      .mem_ready(i_mem_ready),
      .mem_addr (o_mem_addr),
      .mem_wdata(o_mem_wdata),
      .mem_wstrb(o_mem_wstrb),
      .mem_rdata(i_mem_rdata),

      .mem_la_read (mem_la_read),
      .mem_la_write(mem_la_write),
      .mem_la_addr (mem_la_addr),
      .mem_la_wdata(mem_la_wdata),
      .mem_la_wstrb(mem_la_wstrb),

      // PCPI tied off (ENABLE_PCPI=0)
      .pcpi_valid(pcpi_valid),
      .pcpi_insn (pcpi_insn),
      .pcpi_rs1  (pcpi_rs1),
      .pcpi_rs2  (pcpi_rs2),
      .pcpi_wr   (1'b0),
      .pcpi_rd   (32'h0000_0000),
      .pcpi_wait (1'b0),
      .pcpi_ready(1'b0),

      .irq(i_irq),
      .eoi(o_eoi),

      .trace_valid(o_trace_valid),
      .trace_data (o_trace_data)
  );

  // SYS-12: o_cpu_trap mirrors CPU trap directly (not sticky).
  assign o_trap = core_trap;

  // SYS-12 / change order RTL RC2-02: the fault report must survive the local core
  // reset that the trap itself causes, so it is sticky under common rst_n only.
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      fault_valid_q <= 1'b0;
    end else if (core_trap) begin
      fault_valid_q <= 1'b1;
    end
  end

  assign o_fault_valid  = fault_valid_q;
  assign o_fault_reason = FaultReasonTrap;
  assign o_fault_addr   = 32'h0000_0000;  // SYS-12: CPU wrapper trap address is 0

  // Imported-IP outputs this integration does not consume (see declarations above).
  wire unused_picorv32_outputs;
  assign unused_picorv32_outputs = &{1'b0, mem_la_read, mem_la_write, mem_la_addr,
                                     mem_la_wdata, mem_la_wstrb, pcpi_valid, pcpi_insn,
                                     pcpi_rs1, pcpi_rs2};

endmodule

`default_nettype wire
