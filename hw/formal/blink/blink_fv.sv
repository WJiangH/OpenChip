// blink_fv.sv — formal property wrapper for `blink`.
// Spec: docs/spec/blink.md (BLINK-01..08). Written by the formal-verification
// role; every property below is derived from the SPEC prose, not from the RTL
// implementation. Restricted subset: immediate assertions inside clocked
// always_ff blocks, explicit delay registers instead of $past, `initial` used
// only in this formal-only file (permitted by /CLAUDE.md).
//
// The proof instance uses a small HALF_PERIOD (see blink.sby [tasks]);
// BLINK-07 states behavior is identical in structure for every
// HALF_PERIOD >= 1, differing only in the numeric cycle count of the toggles.
`default_nettype none

module blink_fv #(
    parameter int HALF_PERIOD = 3  // overridden per task, see blink.sby
) (
    input wire clk,
    input wire rst_n
);

  localparam int FULL_PERIOD = 2 * HALF_PERIOD;   // spec §4 / BLINK-05
  localparam int PH_W = $clog2(FULL_PERIOD + 1);  // holds 0 .. FULL_PERIOD-1

  wire o_led;

  blink #(
      .HALF_PERIOD(HALF_PERIOD)
  ) u_dut (
      .clk  (clk),
      .rst_n(rst_n),
      .o_led(o_led)
  );

  // The DUT's internal counter. Read-only observation of design state; the
  // RTL is not modified. Referenced for BLINK-01 (counter resets to 0) and the
  // §4 counter invariant.
  // (Zero-extended to a fixed 32 bits so this file makes no assumption about
  // the RTL's chosen counter width.)
  wire [31:0] f_cnt;
  assign f_cnt = u_dut.cnt;

  // --------------------------------------------------------------------------
  // Spec reference model (NOT copied from the RTL): `phase` is the spec's
  // "number of clock cycles elapsed since rst_n deasserted" (BLINK-03 wording),
  // taken modulo one full period (BLINK-04/05). BLINK-02 requires this count to
  // restart at 0 on every reset with no residual phase, which is exactly the
  // reset behavior modelled here.
  // --------------------------------------------------------------------------
  logic [PH_W-1:0] phase;
  logic            reset_seen;    // 1 once the module has been reset at least once
  logic            f_past_valid;  // 1 once the delay registers below are meaningful

  // Delay registers (portable stand-in for $past).
  logic            rst_n_q;
  logic            o_led_q;
  logic            reset_seen_q;

  initial phase        = '0;
  initial reset_seen   = 1'b0;
  initial f_past_valid = 1'b0;
  initial rst_n_q      = 1'b0;
  initial o_led_q      = 1'b0;
  initial reset_seen_q = 1'b0;

  always_ff @(posedge clk) begin
    f_past_valid <= 1'b1;
    rst_n_q      <= rst_n;
    o_led_q      <= o_led;
    reset_seen_q <= reset_seen;
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      phase      <= '0;
      reset_seen <= 1'b1;
    end else begin
      phase <= (phase == PH_W'(FULL_PERIOD - 1)) ? '0 : phase + 1'b1;
    end
  end

  // Model well-formedness. Proven, not assumed: it is needed so that the
  // `prove` (k-induction) run cannot start from an unreachable phase value.
  always_ff @(posedge clk) begin
    a_model_phase_range :
    assert (phase < FULL_PERIOD);
  end

  // --------------------------------------------------------------------------
  // ASSUMPTIONS
  // None. `clk` is the only clock and `rst_n` is left completely free: spec §6
  // explicitly requires reset to be legal at arbitrary points relative to the
  // counter phase, including re-assertion mid-period, so constraining rst_n
  // would be over-assumption. Properties are instead *guarded* by `reset_seen`,
  // which is the spec's own precondition ("after rst_n deasserts",
  // BLINK-02/BLINK-03), not a restriction on the environment.
  // --------------------------------------------------------------------------

  // --------------------------------------------------------------------------
  // BLINK-01 (reset value): while rst_n is low, on the next rising edge of clk
  // the module shall set o_led = 0 and reset the internal counter to 0. This
  // fires at *every* edge at which rst_n was low, so holding rst_n low for many
  // cycles keeps both at their reset values (spec §6 bullet 4).
  // --------------------------------------------------------------------------
  always_ff @(posedge clk) begin
    if (f_past_valid && !rst_n_q) begin
      a_blink01_led_reset :
      assert (o_led == 1'b0);
      a_blink01_cnt_reset :
      assert (f_cnt == 0);
    end
  end

  // --------------------------------------------------------------------------
  // BLINK-02/03/04/05 (main functional property): once the module has been
  // reset, o_led is exactly the spec's function of elapsed post-reset cycles —
  // low for the first HALF_PERIOD cycles, high for the next HALF_PERIOD,
  // repeating forever. Because `phase` restarts at 0 on every reset, this also
  // discharges BLINK-02 (no residual phase carried across reset).
  // --------------------------------------------------------------------------
  always_ff @(posedge clk) begin
    if (reset_seen) begin
      a_blink0345_led_eq_phase :
      assert (o_led == (phase >= HALF_PERIOD));

      // BLINK-03 (first toggle timing), stated separately for traceability:
      // no 0->1 toggle before post-reset cycle HALF_PERIOD ...
      if (phase < HALF_PERIOD) begin
        a_blink03_no_early_toggle :
        assert (o_led == 1'b0);
      end
      // ... and o_led is high exactly on post-reset cycle HALF_PERIOD.
      if (phase == HALF_PERIOD) begin
        a_blink03_first_toggle :
        assert (o_led == 1'b1);
      end
      // BLINK-05 (50% duty cycle): within every FULL_PERIOD window o_led is
      // high for exactly the HALF_PERIOD cycles with phase >= HALF_PERIOD and
      // low for exactly the HALF_PERIOD cycles with phase < HALF_PERIOD — the
      // two guarded asserts split the window into two equal halves.
      if (phase >= HALF_PERIOD) begin
        a_blink05_high_half :
        assert (o_led == 1'b1);
      end
    end
  end

  // --------------------------------------------------------------------------
  // BLINK-04 (steady-state period): o_led shall change value if and only if the
  // number of elapsed post-reset cycles is a nonzero multiple of HALF_PERIOD
  // (toggle N at cycle N*HALF_PERIOD), i.e. exactly when phase wraps to 0 or
  // reaches HALF_PERIOD. The "only if" direction is what forbids extra toggles;
  // together with BLINK-06 (registered output) this bounds o_led to at most one
  // change per clock cycle.
  // --------------------------------------------------------------------------
  always_ff @(posedge clk) begin
    if (f_past_valid && reset_seen && reset_seen_q && rst_n_q) begin
      a_blink04_toggle_iff_multiple :
      assert ((o_led != o_led_q) == ((phase == 0) || (phase == HALF_PERIOD)));
    end
  end

  // --------------------------------------------------------------------------
  // Counter invariant (spec §4: "every clock cycle that cnt reaches
  // HALF_PERIOD - 1, o_led is inverted and cnt restarts from 0"): the internal
  // counter shall never reach or exceed HALF_PERIOD, and shall equal the
  // elapsed post-reset cycle count modulo HALF_PERIOD.
  // --------------------------------------------------------------------------
  always_ff @(posedge clk) begin
    if (reset_seen) begin
      a_cnt_below_half_period :
      assert (f_cnt < HALF_PERIOD);
      a_cnt_tracks_phase :
      assert (f_cnt == (phase % HALF_PERIOD));
    end
  end

  // --------------------------------------------------------------------------
  // COVER — reachability evidence. An assertion over unreachable states proves
  // nothing, so every interesting state named by the spec is covered.
  // --------------------------------------------------------------------------
  logic [2:0] toggle_cnt;  // saturating count of observed o_led transitions
  initial toggle_cnt = '0;
  always_ff @(posedge clk) begin
    if (!rst_n) toggle_cnt <= '0;
    else if (f_past_valid && reset_seen && (o_led != o_led_q) && (toggle_cnt != 3'd7))
      toggle_cnt <= toggle_cnt + 3'd1;
  end

  always_ff @(posedge clk) begin
    // BLINK-03: the first 0->1 toggle actually happens.
    c_led_high :
    cover (reset_seen && o_led);
    // BLINK-04/05: the 1->0 toggle happens too, i.e. a full period completes.
    c_led_fall :
    cover (f_past_valid && reset_seen && o_led_q && !o_led);
    // BLINK-04: two complete periods (four toggles) are reachable.
    c_two_full_periods :
    cover (toggle_cnt == 3'd4);
    // Spec §4: the counter really does reach its terminal value HALF_PERIOD-1.
    c_cnt_terminal :
    cover (reset_seen && f_cnt == (HALF_PERIOD - 1));
    // Spec §6 bullet 3: reset re-asserted mid-period, while o_led is high.
    c_reset_mid_period :
    cover (f_past_valid && reset_seen && !rst_n && o_led_q && rst_n_q);
    // Spec §6 bullet 4: rst_n held low for more than one cycle.
    c_long_reset :
    cover (f_past_valid && !rst_n && !rst_n_q);
  end

endmodule

`default_nettype wire
