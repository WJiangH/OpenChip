// npu_ctl.sv — NPU command / error controller.
// Spec: docs/spec/llm-soc-v1/npu.md §4 (internal partition interface semantics),
// NPU-06 (terminal transition only after all output B responses OKAY),
// NPU-07 (2^28-cycle command watchdog, fatal reason5), system.md SYS-12
// (fault_event / stop_issue semantics). contract.json connections C12, C13,
// C23, C24, C25, C29, C31, CR11.
//
// Scope note: npu.md §4 states "Local derives all group boundaries from its
// descriptor" and describes the K/N/G/tail group loop entirely in terms of
// npu_local's and npu_dot's own state machines; npu_ctl's own role in §4 is
// limited to (a) broadcasting the snapshotted dispatch to npu_dma and
// npu_local with independent handshakes, holding each valid until its own
// ready, issuing no memory request until both complete, and (b) collecting
// the single dma_terminal done/error pulse and turning it into one terminal
// record for npu_csr. There is no group/row counter implemented here: the
// dispatch fields (K,N,G,W_STRIDE) are latched and forwarded unchanged, and
// the group loop itself lives downstream in npu_local/npu_dot. See
// ISSUES.md ISSUE-npu_ctl-01.
`default_nettype none

module npu_ctl (
    // CR11: sys -> npu_ctl clock_reset.
    input wire clk,
    input wire rst_n,

    // C12: npu_csr -> npu_ctl, protocol dispatch (npu_ctl is consumer).
    input  wire        i_dispatch_valid,
    output logic        o_dispatch_ready,
    input  wire [31:0] i_dispatch_opcode,
    input  wire [31:0] i_dispatch_x_base,
    input  wire [31:0] i_dispatch_w_base,
    input  wire [31:0] i_dispatch_y_base,
    input  wire [31:0] i_dispatch_k,
    input  wire [31:0] i_dispatch_n,
    input  wire [31:0] i_dispatch_group,
    input  wire [31:0] i_dispatch_w_stride,
    input  wire [31:0] i_dispatch_tag,

    // C13: npu_ctl -> npu_dma, protocol dispatch (npu_ctl is producer).
    output logic        o_dma_dispatch_valid,
    input  wire        i_dma_dispatch_ready,
    output logic [31:0] o_dma_dispatch_opcode,
    output logic [31:0] o_dma_dispatch_x_base,
    output logic [31:0] o_dma_dispatch_w_base,
    output logic [31:0] o_dma_dispatch_y_base,
    output logic [31:0] o_dma_dispatch_k,
    output logic [31:0] o_dma_dispatch_n,
    output logic [31:0] o_dma_dispatch_group,
    output logic [31:0] o_dma_dispatch_w_stride,
    output logic [31:0] o_dma_dispatch_tag,

    // C25: npu_ctl -> npu_local, protocol dispatch (npu_ctl is producer).
    output logic        o_local_dispatch_valid,
    input  wire        i_local_dispatch_ready,
    output logic [31:0] o_local_dispatch_opcode,
    output logic [31:0] o_local_dispatch_x_base,
    output logic [31:0] o_local_dispatch_w_base,
    output logic [31:0] o_local_dispatch_y_base,
    output logic [31:0] o_local_dispatch_k,
    output logic [31:0] o_local_dispatch_n,
    output logic [31:0] o_local_dispatch_group,
    output logic [31:0] o_local_dispatch_w_stride,
    output logic [31:0] o_local_dispatch_tag,

    // C23: npu_dma -> npu_ctl, protocol dma_terminal (npu_ctl is consumer).
    // No valid/ready in this protocol (contract.json protocols.dma_terminal):
    // done/error are one-cycle, mutually-exclusive pulses; error_code is only
    // meaningful in the same cycle error is asserted (values 5 read, 6 write;
    // NPU-06 "if read and write error coincide, code5 wins" is resolved by
    // npu_dma before it asserts this pulse).
    input wire        i_dma_done,
    input wire        i_dma_error,
    input wire [ 2:0] i_dma_error_code,

    // C24: npu_ctl -> npu_csr, protocol terminal (npu_ctl is producer).
    output logic        o_terminal_valid,
    input  wire        i_terminal_ready,
    output logic [31:0] o_terminal_tag,
    output logic [ 2:0] o_terminal_error_code,
    output logic [31:0] o_terminal_cycles,

    // C29: npu_ctl -> sys, protocol fault_event (npu_ctl is producer). Sticky
    // until common reset; no READY. NPU-07 watchdog: reason5, addr0 (SYS-12).
    output logic        o_fault_valid,
    output logic [ 2:0] o_fault_reason,
    output logic [31:0] o_fault_addr,

    // C31: sys -> npu_ctl, protocol stop_issue (npu_ctl is consumer). Sticky;
    // gates only the *start* of a new command — an already-offered broadcast
    // valid is never retracted (SYS-12 "stop never means retract VALID").
    input wire i_stop_new_transactions
);

  localparam logic [31:0] WATCHDOG_LIMIT = 32'd268_435_456;  // 2^28, NPU-07

  typedef enum logic [1:0] {
    ST_IDLE      = 2'd0,  // waiting for a dispatch from npu_csr
    ST_BCAST     = 2'd1,  // broadcasting the held command to dma + local
    ST_WAIT_DONE = 2'd2,  // waiting for npu_dma's dma_terminal pulse
    ST_TERM      = 2'd3   // presenting the terminal record to npu_csr
  } ctl_state_e;

  ctl_state_e state_q;

  logic [31:0] opcode_q, x_base_q, w_base_q, y_base_q;
  logic [31:0] k_q, n_q, group_q, w_stride_q, tag_q;
  logic        dma_sent_q, local_sent_q;
  logic [ 2:0] pending_error_code_q;
  logic [31:0] cycle_ctr_q;
  logic        fatal_watchdog_q;

  // ---------------------------------------------------------------------
  // Broadcast handshake bookkeeping (§4: "issues no memory request until
  // both handshakes finish; each recipient sees the command once").
  // ---------------------------------------------------------------------
  assign o_dma_dispatch_valid   = (state_q == ST_BCAST) && !dma_sent_q;
  assign o_local_dispatch_valid = (state_q == ST_BCAST) && !local_sent_q;

  assign o_dma_dispatch_opcode   = opcode_q;
  assign o_dma_dispatch_x_base   = x_base_q;
  assign o_dma_dispatch_w_base   = w_base_q;
  assign o_dma_dispatch_y_base   = y_base_q;
  assign o_dma_dispatch_k        = k_q;
  assign o_dma_dispatch_n        = n_q;
  assign o_dma_dispatch_group    = group_q;
  assign o_dma_dispatch_w_stride = w_stride_q;
  assign o_dma_dispatch_tag      = tag_q;

  assign o_local_dispatch_opcode   = opcode_q;
  assign o_local_dispatch_x_base   = x_base_q;
  assign o_local_dispatch_w_base   = w_base_q;
  assign o_local_dispatch_y_base   = y_base_q;
  assign o_local_dispatch_k        = k_q;
  assign o_local_dispatch_n        = n_q;
  assign o_local_dispatch_group    = group_q;
  assign o_local_dispatch_w_stride = w_stride_q;
  assign o_local_dispatch_tag      = tag_q;

  wire dma_hs   = o_dma_dispatch_valid && i_dma_dispatch_ready;
  wire local_hs = o_local_dispatch_valid && i_local_dispatch_ready;
  wire dma_done_c   = dma_sent_q || dma_hs;
  wire local_done_c = local_sent_q || local_hs;

  assign o_dispatch_ready = (state_q == ST_IDLE) && !fatal_watchdog_q &&
                             !i_stop_new_transactions;

  assign o_terminal_valid      = (state_q == ST_TERM);
  assign o_terminal_tag        = tag_q;
  assign o_terminal_error_code = pending_error_code_q;
  assign o_terminal_cycles     = cycle_ctr_q;

  assign o_fault_valid  = fatal_watchdog_q;
  assign o_fault_reason = 3'd5;
  assign o_fault_addr   = 32'd0;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state_q              <= ST_IDLE;
      opcode_q             <= 32'd0;
      x_base_q             <= 32'd0;
      w_base_q             <= 32'd0;
      y_base_q             <= 32'd0;
      k_q                  <= 32'd0;
      n_q                  <= 32'd0;
      group_q              <= 32'd0;
      w_stride_q           <= 32'd0;
      tag_q                <= 32'd0;
      dma_sent_q           <= 1'b0;
      local_sent_q         <= 1'b0;
      pending_error_code_q <= 3'd0;
      cycle_ctr_q          <= 32'd0;
      fatal_watchdog_q     <= 1'b0;
    end else begin
      case (state_q)
        ST_IDLE: begin
          if (i_dispatch_valid && o_dispatch_ready) begin
            opcode_q     <= i_dispatch_opcode;
            x_base_q     <= i_dispatch_x_base;
            w_base_q     <= i_dispatch_w_base;
            y_base_q     <= i_dispatch_y_base;
            k_q          <= i_dispatch_k;
            n_q          <= i_dispatch_n;
            group_q      <= i_dispatch_group;
            w_stride_q   <= i_dispatch_w_stride;
            tag_q        <= i_dispatch_tag;
            dma_sent_q   <= 1'b0;
            local_sent_q <= 1'b0;
            // NPU-04 LAST_CYCLES: cycles "from submit acceptance ... inclusive".
            // "Acceptance" is this dispatch handshake with npu_csr (the only
            // acceptance edge visible to npu_ctl); see ISSUES.md ISSUE-npu_ctl-02.
            cycle_ctr_q  <= 32'd1;
            state_q      <= ST_BCAST;
          end
        end

        ST_BCAST: begin
          if (dma_hs)   dma_sent_q   <= 1'b1;
          if (local_hs) local_sent_q <= 1'b1;
          if (!fatal_watchdog_q) cycle_ctr_q <= cycle_ctr_q + 32'd1;
          if (dma_done_c && local_done_c && !fatal_watchdog_q) begin
            state_q      <= ST_WAIT_DONE;
            dma_sent_q   <= 1'b0;
            local_sent_q <= 1'b0;
          end
          if (!fatal_watchdog_q && cycle_ctr_q >= WATCHDOG_LIMIT) begin
            fatal_watchdog_q <= 1'b1;  // NPU-07: no terminal transition in time
          end
        end

        ST_WAIT_DONE: begin
          if (!fatal_watchdog_q) cycle_ctr_q <= cycle_ctr_q + 32'd1;
          if (!fatal_watchdog_q && i_dma_error) begin
            pending_error_code_q <= i_dma_error_code;  // 5 read, 6 write (NPU-06)
            state_q              <= ST_TERM;
          end else if (!fatal_watchdog_q && i_dma_done) begin
            pending_error_code_q <= 3'd0;
            state_q              <= ST_TERM;
          end
          if (!fatal_watchdog_q && cycle_ctr_q >= WATCHDOG_LIMIT) begin
            fatal_watchdog_q <= 1'b1;  // NPU-07
          end
        end

        ST_TERM: begin
          if (i_terminal_ready) begin  // o_terminal_valid implied by state_q
            state_q <= ST_IDLE;
          end
        end

        default: state_q <= ST_IDLE;
      endcase
    end
  end

endmodule

`default_nettype wire
