// npu_ctl.sv — NPU command / error controller.
// Spec baseline: docs/spec/llm-soc-v1 1.0-rc4 (CHANGE_ORDER_rc4 rows F-01,
// F-04, F-06 / ISSUE-npu_ctl-01, ISSUE-npu_ctl-02, ISSUE-npu_dma-02,
// ISSUE-npu_dma-04).
// Spec: npu.md §4 (internal partition interface semantics), NPU-04
// (LAST_CYCLES = T-H+1), NPU-06 (terminal transition only after all output B
// responses OKAY), NPU-07 (2^28-cycle command watchdog measured from H, fatal
// reason5), NPU-09(a) (dispatch re-arm, C25 no later than C13), NPU-09(b)
// (dot_lifecycle flush), NPU-09(c) (dma_terminal levels, terminal edge T),
// system.md SYS-12 (fault_event / stop_issue semantics). contract.json
// connections C12, C13, C23, C24, C25, C29, C31, C34, CR11.
//
// Level-at-edge convention (NPU-09 preamble): the value of a level "at" a
// rising edge is its value in the cycle ending at that edge — the value that
// edge samples; a registered level set at edge E is 1 from the cycle starting
// at E. Every "edge" named below (H, T, C12, C13, C25) is read that way.
//
// Scope note: npu.md §4 states "Local derives all group boundaries from its
// descriptor" and describes the K/N/G/tail group loop entirely in terms of
// npu_local's and npu_dot's own state machines; npu_ctl's own role in §4 is
// limited to (a) broadcasting the snapshotted dispatch to npu_dma and
// npu_local with independent handshakes, holding each valid until its own
// ready, completing the npu_local handshake (C25) no later than the npu_dma
// handshake (C13) per NPU-09(a), (b) sampling the registered dma_terminal
// level from the cycle after its own C13 handshake and turning the first
// sampled assertion (the terminal edge T) into one terminal record for
// npu_csr, and (c) driving the dot_lifecycle flush level (C34) that holds
// npu_dot quiescent from reset and from every terminal until the next
// command's C25 handshake. There is no group/row counter implemented here:
// the dispatch fields (K,N,G,W_STRIDE) are latched and forwarded unchanged,
// and the group loop itself lives downstream in npu_local/npu_dot
// (ISSUE-npu_ctl-01, ruled spec-clear in rc4). See ISSUES.md.
//
// Port-naming note: the rc4 contract.json port_identifier_convention
// (<i_|o_><protocol>_<field>) is binding for protocols added from rc4 on, so
// the new C34 port is `o_dot_lifecycle_flush`; the rc3 C13/C25/C23 spellings
// (o_dma_dispatch_*, o_local_dispatch_*, i_dma_done/...) are reconciled in the
// top-level port map, not renamed (rc4, ISSUE-npu_dma-01).
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

    // C34: npu_ctl -> npu_dot, protocol dot_lifecycle (npu_ctl is producer).
    // NPU-09(b): one registered level. Reset value 1, set on the dma_terminal
    // sampling edge T, cleared only on the C25 handshake edge, never on the
    // C12 accept edge (H) — it is therefore NOT ~command_live, since C12 may
    // precede C25. In the cycle ending at the C25 edge flush is still 1, which
    // is what lets npu_dot discard the operand beat a not-yet-re-armed
    // npu_local may offer on that very edge.
    output logic o_dot_lifecycle_flush,

    // C23: npu_dma -> npu_ctl, protocol dma_terminal (npu_ctl is consumer).
    // No valid/ready in this protocol (contract.json protocols.dma_terminal).
    // NPU-09(c) (rc4, F-04): done/error/error_code are *registered levels*,
    // not one-cycle pulses — npu_dma asserts exactly one of done/error on its
    // own assertion edge Td and holds all three until the edge on which its
    // next C13 dispatch handshake completes, or reset. This module therefore
    // samples them only from the cycle after its own C13 handshake edge (that
    // is exactly state ST_WAIT_DONE, which is entered at the C13 edge), takes
    // the first edge at which done|error is sampled 1 as the terminal edge T
    // (so T >= Td+1), and never re-samples the level for the same command; the
    // stale level of the previous command is already cleared by npu_dma at the
    // C13 edge. error_code is 5 (read) or 6 (write) while error=1 and 0
    // otherwise; NPU-06 "if read and write error coincide, code5 wins" is
    // resolved by npu_dma before it asserts the level.
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
    ST_WAIT_DONE = 2'd2,  // sampling npu_dma's dma_terminal level (T)
    ST_TERM      = 2'd3   // presenting the terminal record to npu_csr
  } ctl_state_e;

  ctl_state_e state_q;

  logic [31:0] opcode_q, x_base_q, w_base_q, y_base_q;
  logic [31:0] k_q, n_q, group_q, w_stride_q, tag_q;
  logic        dma_sent_q, local_sent_q;
  logic [ 2:0] pending_error_code_q;
  logic [31:0] cycle_ctr_q;
  logic        fatal_watchdog_q;
  logic        flush_q;

  // ---------------------------------------------------------------------
  // Broadcast handshake bookkeeping (§4: "holds each valid until its own
  // ready; each recipient sees the command once"). Both valids are asserted
  // in the same cycle; NPU-09(a) requires the C25 (local) handshake to
  // complete no later than the C13 (dma) handshake, and the simultaneous
  // broadcast satisfies that because npu_local presents dispatch.ready=1
  // whenever not in reset, so local_hs can never be later than dma_hs
  // (rc4, ISSUE-npu_dma-04). rc4 replaced the rc3 sentence "issues no memory
  // request until both handshakes finish": npu_dma may issue its first AR
  // from the cycle after its own handshake.
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
  wire local_hs = o_local_dispatch_valid && i_local_dispatch_ready;  // C25 edge
  wire dma_done_c   = dma_sent_q || dma_hs;
  wire local_done_c = local_sent_q || local_hs;

  // NPU-09(c): the terminal edge T. ST_WAIT_DONE is entered at this command's
  // own C13 handshake edge, so the first edge that can evaluate this term is
  // the one after C13 — i.e. the level is sampled only from the cycle after
  // the C13 handshake — and the ST_TERM transition below guarantees it is
  // sampled once per command.
  wire terminal_sample_c = (state_q == ST_WAIT_DONE) && !fatal_watchdog_q &&
                           (i_dma_done || i_dma_error);

  // C34 / NPU-09(b): registered flush level driven to npu_dot.
  assign o_dot_lifecycle_flush = flush_q;

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
      flush_q              <= 1'b1;  // NPU-09(b): reset value 1
    end else begin
      // NPU-09(b) dot_lifecycle.flush. Set on the dma_terminal sampling edge
      // T; cleared ONLY on the C25 handshake edge of the next command; never
      // cleared on the C12 accept edge (H), which may precede C25 — hence the
      // clear term is local_hs and not the ST_IDLE dispatch accept. The two
      // terms are mutually exclusive by state (T is sampled in ST_WAIT_DONE,
      // C25 completes in ST_BCAST); set is given priority anyway so that
      // "set at T" holds unconditionally. Because flush_q is only *written*
      // here and read combinationally by npu_dot, its value in the cycle
      // ending at the C25 edge is still 1, as NPU-09(b) requires.
      if (terminal_sample_c) begin
        flush_q <= 1'b1;
      end else if (local_hs) begin
        flush_q <= 1'b0;
      end

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
            // NPU-04 (rc4): LAST_CYCLES = T-H+1, where H is this edge (the
            // C12 dispatch handshake with npu_csr) and T is the dma_terminal
            // sampling edge; both endpoints count. Presetting the counter to 1
            // at H and incrementing on every later edge up to and including T
            // yields exactly T-H+1 (ISSUE-npu_ctl-02, ruled spec-gap in rc4
            // with this provisional choice confirmed; no logic change). The
            // NPU-07 watchdog window (2^28) is measured on the same counter
            // and therefore also starts at H.
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
          if (terminal_sample_c) begin  // this edge is T (NPU-09(c))
            // 5 read, 6 write (NPU-06); npu_dma asserts exactly one of
            // done/error, error takes priority here for defence in depth.
            pending_error_code_q <= i_dma_error ? i_dma_error_code : 3'd0;
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
