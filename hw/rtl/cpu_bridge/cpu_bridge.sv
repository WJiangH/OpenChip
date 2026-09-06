// cpu_bridge.sv — error-aware PicoRV32-native to AXI4 initiator adapter (CPU, ID 0).
//
// Spec: docs/spec/llm-soc-v1/system.md SYS-02 (project-owned error-aware native->AXI
// adapter, not picorv32_wb / picorv32_axi), SYS-04 (native address/data/strobes passed
// unchanged), SYS-07 (non-OK response latches fatal + reason 1 read / 2 write, no
// successful native completion for the failed operation, bridge retains AXI state),
// SYS-08 (aligned word CSR access is a software obligation; the bridge cannot see the
// original size/offset and does not try), SYS-12 (sticky fault_event, stop_new_transactions,
// bridge unaffected by cpu_local_rst_n);
// docs/spec/llm-soc-v1/axi.md AXI-01 (signal set), AXI-02 (ID 0, SIZE=2, INCR, LEN=0,
// AWPROT=0, ARPROT[2]=mem_instr, unshifted RDATA), AXI-03 (VALID/payload stable until
// READY, VALID never waits for READY, AW offered no later than first W and without
// waiting for AWREADY), AXI-04 (one native request outstanding in total),
// AXI-08 (ordering follows from the serialized single-transaction bridge);
// docs/spec/llm-soc-v1/contract.json connections C01, C02 (fixed_id 0), C27 (fault_event
// to sys), C30 (stop_issue from sys), CR01 (common clock/reset only).
//
// AXI-07 progress timeout is NOT implemented here: SYS-12 assigns reason 3 (progress)
// and 6 (protocol) to the fabric monitor; the bridge only ever reports reason 1/2.
// See ISSUES.md ISSUE-cpu_bridge-01 for the contract.json owner_modules coarseness.
`default_nettype none

module cpu_bridge (
    input wire clk,
    input wire rst_n,  // common reset only (contract CR01); no local CPU reset input

    // --- C01: native target port (contract.json protocols.native) ------------
    input  wire         i_mem_valid,
    input  wire         i_mem_instr,
    output logic        o_mem_ready,
    input  wire  [31:0] i_mem_addr,
    input  wire  [31:0] i_mem_wdata,
    input  wire  [ 3:0] i_mem_wstrb,
    output logic [31:0] o_mem_rdata,

    // --- C02: AXI4 initiator port (AXI-01 signal set, 32b addr/data, 2b ID) ---
    output logic        axi_awvalid,
    input  wire         axi_awready,
    output logic [31:0] axi_awaddr,
    output logic [ 1:0] axi_awid,
    output logic [ 7:0] axi_awlen,
    output logic [ 2:0] axi_awsize,
    output logic [ 1:0] axi_awburst,
    output logic        axi_awlock,
    output logic [ 3:0] axi_awcache,
    output logic [ 2:0] axi_awprot,
    output logic [ 3:0] axi_awqos,

    output logic        axi_wvalid,
    input  wire         axi_wready,
    output logic [31:0] axi_wdata,
    output logic [ 3:0] axi_wstrb,
    output logic        axi_wlast,

    input  wire        axi_bvalid,
    output logic       axi_bready,
    input  wire [ 1:0] axi_bresp,
    input  wire [ 1:0] axi_bid,

    output logic        axi_arvalid,
    input  wire         axi_arready,
    output logic [31:0] axi_araddr,
    output logic [ 1:0] axi_arid,
    output logic [ 7:0] axi_arlen,
    output logic [ 2:0] axi_arsize,
    output logic [ 1:0] axi_arburst,
    output logic        axi_arlock,
    output logic [ 3:0] axi_arcache,
    output logic [ 2:0] axi_arprot,
    output logic [ 3:0] axi_arqos,

    input  wire         axi_rvalid,
    output logic        axi_rready,
    input  wire  [31:0] axi_rdata,
    input  wire  [ 1:0] axi_rresp,
    input  wire  [ 1:0] axi_rid,
    input  wire         axi_rlast,

    // --- C27: fault_event to sys (sticky, no READY) --------------------------
    output logic        o_fault_valid,
    output logic [ 2:0] o_fault_reason,
    output logic [31:0] o_fault_addr,

    // --- C30: stop_issue from sys (sticky at the source) ---------------------
    input wire i_stop_new_transactions
);

  // AXI-02/AXI-05: only OKAY is a success; EXOKAY is never generated, SLVERR and
  // DECERR are both "non-OK" for SYS-07 purposes.
  localparam logic [1:0] AxiOkay = 2'b00;

  // SYS-07 fault reasons owned by this block.
  localparam logic [2:0] FaultReasonRead  = 3'd1;
  localparam logic [2:0] FaultReasonWrite = 3'd2;

  localparam logic [2:0] StIdle  = 3'd0;
  localparam logic [2:0] StRead  = 3'd1;
  localparam logic [2:0] StWrite = 3'd2;
  localparam logic [2:0] StResp  = 3'd3;
  localparam logic [2:0] StFault = 3'd4;

  logic [2:0] state_q;

  // Captured native request (AXI-03: payload stable until READY; SYS-04: unchanged).
  logic [31:0] addr_q;
  logic [31:0] wdata_q;
  logic [ 3:0] wstrb_q;
  logic        instr_q;

  logic        arvalid_q;
  logic        awvalid_q;
  logic        wvalid_q;
  logic        rready_q;
  logic        bready_q;

  logic [31:0] rdata_q;
  logic        mem_ready_q;

  logic        fault_valid_q;
  logic [ 2:0] fault_reason_q;
  logic [31:0] fault_addr_q;

  // ISSUE-cpu_bridge-01: provisional. contract.json protocols.native lists the native
  // signals but no handshake semantics; upstream PicoRV32 semantics are used here.
  // A native request with any strobe set is a store; mem_wstrb == 0 is a load
  // (read, possibly an instruction fetch flagged by mem_instr).
  logic req_is_write;
  assign req_is_write = |i_mem_wstrb;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state_q        <= StIdle;
      addr_q         <= 32'h0000_0000;
      wdata_q        <= 32'h0000_0000;
      wstrb_q        <= 4'h0;
      instr_q        <= 1'b0;
      arvalid_q      <= 1'b0;
      awvalid_q      <= 1'b0;
      wvalid_q       <= 1'b0;
      rready_q       <= 1'b0;
      bready_q       <= 1'b0;
      rdata_q        <= 32'h0000_0000;
      mem_ready_q    <= 1'b0;
      fault_valid_q  <= 1'b0;
      fault_reason_q <= 3'd0;
      fault_addr_q   <= 32'h0000_0000;
    end else begin
      // o_mem_ready is a single-cycle completion pulse.
      mem_ready_q <= 1'b0;

      case (state_q)
        // AXI-04: exactly one native request is accepted at a time. SYS-12: no new
        // transaction is offered once sys has raised stop_new_transactions.
        // ISSUE-cpu_bridge-03: provisional. stop is sampled at the same edge that
        // captures the request; a request captured at or before the fatal capture
        // edge is still offered afterwards and then held per AXI-03.
        // ISSUE-cpu_bridge-01: provisional. A new request may follow the completion
        // pulse with no idle gap; mem_valid is not required to drop in between.
        StIdle: begin
          if (i_mem_valid && !i_stop_new_transactions) begin
            addr_q  <= i_mem_addr;
            wdata_q <= i_mem_wdata;
            wstrb_q <= i_mem_wstrb;
            instr_q <= i_mem_instr;
            if (req_is_write) begin
              // AXI-03: AW is offered together with the first (only) W beat and
              // never waits for AWREADY.
              awvalid_q <= 1'b1;
              wvalid_q  <= 1'b1;
              state_q   <= StWrite;
            end else begin
              arvalid_q <= 1'b1;
              state_q   <= StRead;
            end
          end
        end

        StRead: begin
          if (arvalid_q && axi_arready) begin
            arvalid_q <= 1'b0;
          end
          // RREADY is raised once AR is accepted, so a response can only be taken
          // for a transaction the fabric has actually accepted (AXI-03).
          if (!arvalid_q || axi_arready) begin
            rready_q <= 1'b1;
          end
          if (axi_rvalid && rready_q) begin
            rready_q <= 1'b0;
            if (axi_rresp == AxiOkay) begin
              // AXI-02: the complete unshifted 32-bit word goes back to the core.
              rdata_q     <= axi_rdata;
              mem_ready_q <= 1'b1;
              state_q     <= StResp;
            end else begin
              // SYS-07: latch fault, never complete the native request.
              fault_valid_q  <= 1'b1;
              fault_reason_q <= FaultReasonRead;
              fault_addr_q   <= addr_q;
              state_q        <= StFault;
            end
          end
        end

        StWrite: begin
          if (awvalid_q && axi_awready) begin
            awvalid_q <= 1'b0;
          end
          if (wvalid_q && axi_wready) begin
            wvalid_q <= 1'b0;
          end
          // BREADY is raised once both AW and the single W beat are accepted
          // (AXI-03: BVALID follows accepted AW and final W, never earlier).
          if ((!awvalid_q || axi_awready) && (!wvalid_q || axi_wready)) begin
            bready_q <= 1'b1;
          end
          if (axi_bvalid && bready_q) begin
            bready_q <= 1'b0;
            if (axi_bresp == AxiOkay) begin
              mem_ready_q <= 1'b1;
              state_q     <= StResp;
            end else begin
              fault_valid_q  <= 1'b1;
              fault_reason_q <= FaultReasonWrite;
              fault_addr_q   <= addr_q;
              state_q        <= StFault;
            end
          end
        end

        // Completion pulse cycle; mem_ready_q self-clears above.
        StResp: begin
          state_q <= StIdle;
        end

        // StFault (and unreachable encodings): terminal until common reset.
        // SYS-07/SYS-12 — no further native request is accepted, no mem_ready is
        // ever produced for the failed operation, and no already offered VALID is
        // retracted; every AXI register simply holds.
        default: begin
          state_q <= StFault;
        end
      endcase
    end
  end

  assign o_mem_ready = mem_ready_q;
  assign o_mem_rdata = rdata_q;

  // AXI-02 constant attributes: single aligned 32-bit INCR beat, CPU source ID 0.
  assign axi_awvalid = awvalid_q;
  assign axi_awaddr  = addr_q;
  assign axi_awid    = 2'd0;
  assign axi_awlen   = 8'd0;
  assign axi_awsize  = 3'b010;
  assign axi_awburst = 2'b01;
  assign axi_awlock  = 1'b0;
  assign axi_awcache = 4'h0;
  assign axi_awprot  = 3'b000;
  assign axi_awqos   = 4'h0;

  assign axi_wvalid = wvalid_q;
  assign axi_wdata  = wdata_q;
  assign axi_wstrb  = wstrb_q;
  assign axi_wlast  = 1'b1;

  assign axi_bready = bready_q;

  assign axi_arvalid = arvalid_q;
  assign axi_araddr  = addr_q;
  assign axi_arid    = 2'd0;
  assign axi_arlen   = 8'd0;
  assign axi_arsize  = 3'b010;
  assign axi_arburst = 2'b01;
  assign axi_arlock  = 1'b0;
  assign axi_arcache = 4'h0;
  // AXI-02/AXI-05: instruction-fetch identity is carried by ARPROT[2] = mem_instr,
  // produced only here (values 0 or 4).
  assign axi_arprot  = {instr_q, 2'b00};
  assign axi_arqos   = 4'h0;

  assign axi_rready = rready_q;

  assign o_fault_valid  = fault_valid_q;
  assign o_fault_reason = fault_reason_q;
  assign o_fault_addr   = fault_addr_q;

  // AXI-01 requires these target-driven signals to exist on the interface. With one
  // outstanding LEN=0 transaction and fixed ID 0 there is nothing for the bridge to
  // decide from them: ID echo and RLAST placement are target obligations policed by
  // the fabric protocol monitor (AXI-03/AXI-07), not by this initiator.
  wire unused_axi_response_meta;
  assign unused_axi_response_meta = &{1'b0, axi_rid, axi_rlast, axi_bid};

endmodule

`default_nettype wire
