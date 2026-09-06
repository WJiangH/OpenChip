// sram.sv -- 256 KiB firmware SRAM, AXI4 target.
// Spec: docs/spec/llm-soc-v1/system.md §2 address table (base 0x10000000,
// 262144 bytes, CPU R/W/X, NPU deny) and axi.md AXI-01/02/03/06/08. Region
// permission/decode is enforced upstream by the fabric (SYS-04 "physical
// source-port identity"); this module is address-window agnostic and
// trusts that every request it receives already belongs to its window
// and fits within it (AXI-02 "no region crossing").
//
// This is a simulation target: a single inferred memory array with
// byte-enable writes, no vendor RAM macro and no timing model implied
// (axi.md AXI-06: "simulation target obligations; no ... PHY validated").
// The storage array `mem` (declared below) is never reset (system.md
// SYS-03: "mutable SRAM/external bytes need not retain meaningful data";
// "Firmware shall initialize every mutable location before reading it" is
// the write-before-read discipline this exemption relies on) -- but every
// control flop below resets. This is the same every-flop-resets exemption
// npu.md NPU-03 takes for its storage arrays (rc4, R4-09): conditional on
// the AGENTS.md storage-array clause recommended in CHANGE_ORDER_rc4
// §Rule-level item 2 ("A storage array ... whose every read within a
// reset epoch is preceded by a write may omit reset; the module header
// must name the array and the spec clause that guarantees write-before-
// read"); until that clause lands, this header names the array (`mem`)
// and cites SYS-03 as that clause (rc4, ISSUE-mem-01 / rule-level item 2).
`default_nettype none

module sram (
    input wire clk,
    input wire rst_n,

    // AXI4 target port (fabric is always the initiator here). Full
    // signal list per AXI-01; USER/REGION are absent (zero-width, not
    // trusted signals) and therefore not present as ports.
    input  wire        s_axi_awvalid,
    output logic        s_axi_awready,
    input  wire [31:0] s_axi_awaddr,
    input  wire [ 1:0] s_axi_awid,
    input  wire [ 7:0] s_axi_awlen,
    input  wire [ 2:0] s_axi_awsize,
    input  wire [ 1:0] s_axi_awburst,
    input  wire        s_axi_awlock,
    input  wire [ 3:0] s_axi_awcache,
    input  wire [ 2:0] s_axi_awprot,
    input  wire [ 3:0] s_axi_awqos,

    input  wire        s_axi_wvalid,
    output logic        s_axi_wready,
    input  wire [31:0] s_axi_wdata,
    input  wire [ 3:0] s_axi_wstrb,
    input  wire        s_axi_wlast,

    output logic        s_axi_bvalid,
    input  wire        s_axi_bready,
    output logic [ 1:0] s_axi_bresp,
    output logic [ 1:0] s_axi_bid,

    input  wire        s_axi_arvalid,
    output logic        s_axi_arready,
    input  wire [31:0] s_axi_araddr,
    input  wire [ 1:0] s_axi_arid,
    input  wire [ 7:0] s_axi_arlen,
    input  wire [ 2:0] s_axi_arsize,
    input  wire [ 1:0] s_axi_arburst,
    input  wire        s_axi_arlock,
    input  wire [ 3:0] s_axi_arcache,
    input  wire [ 2:0] s_axi_arprot,
    input  wire [ 3:0] s_axi_arqos,

    output logic        s_axi_rvalid,
    input  wire        s_axi_rready,
    output logic [31:0] s_axi_rdata,
    output logic [ 1:0] s_axi_rresp,
    output logic [ 1:0] s_axi_rid,
    output logic        s_axi_rlast
);

  localparam int SRAM_BYTES = 262144;  // system.md §2: fixed size, never resized
  localparam int WORDS = SRAM_BYTES / 4;  // 65536
  localparam int IDX_W = $clog2(WORDS);  // 16
  localparam int IDX_HI = IDX_W + 1;  // 17 (word index occupies addr[17:2])

  // `mem`: single inferred memory array, byte-enable write, no vendor
  // macro. Not reset (SYS-03: "mutable SRAM/external bytes need not
  // retain meaningful data"; firmware initializes what it uses, including
  // BSS, before reading it -- the write-before-read discipline SYS-03
  // requires). Storage-array reset exemption per CHANGE_ORDER_rc4
  // §Rule-level item 2, cited in the module header above (rc4, R4-09
  // pattern); every control flop in this module still resets.
  logic [31:0] mem[0:WORDS-1];

  // AXI-02 restricts DUT initiators to aligned SIZE=2 INCR beats with no
  // region crossing; AWSIZE/AWBURST/AWLOCK/AWCACHE/AWPROT/AWQOS and their
  // AR counterparts (besides ARLEN, used below) are validated upstream by
  // the fabric decode (SYS-04) and the protocol monitor (AXI-07), not by
  // this target. AWLEN is likewise unused: the write-response FSM keys
  // off WLAST rather than a beat count (see below). Sink to keep lint
  // clean.
  wire unused_axi_fields = |{
    s_axi_awlen, s_axi_awsize, s_axi_awburst, s_axi_awlock, s_axi_awcache, s_axi_awprot, s_axi_awqos,
    s_axi_arsize, s_axi_arburst, s_axi_arlock, s_axi_arcache, s_axi_arprot, s_axi_arqos
  };

  // -------------------------------------------------------------------
  // Read channel (AXI-06: respond within 16 cycles of an accepted read;
  // this design responds the cycle after AR is accepted and on every
  // beat thereafter -- well inside the bound). Combinational read of
  // the registered running address; a write committed on a prior cycle
  // is therefore visible to a read issued afterward (AXI-08).
  // -------------------------------------------------------------------
  logic        r_busy;
  logic [31:0] r_addr;
  logic [ 1:0] r_id;
  logic [ 7:0] r_len;
  logic [ 7:0] r_beat;

  assign s_axi_arready = !r_busy;
  assign s_axi_rvalid  = r_busy;
  assign s_axi_rdata   = mem[r_addr[IDX_HI:2]];
  assign s_axi_rresp   = 2'b00;  // OKAY; fabric already authorized this access (SYS-04)
  assign s_axi_rid     = r_id;
  assign s_axi_rlast   = (r_beat == r_len);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      // SYS-03: reset epoch rule -- no pre-reset response may leak into
      // the new epoch, so every control flop resets, including mid-burst
      // state (memory contents themselves are intentionally excluded).
      r_busy <= 1'b0;
      r_addr <= '0;
      r_id   <= '0;
      r_len  <= '0;
      r_beat <= '0;
    end else if (!r_busy) begin
      if (s_axi_arvalid) begin
        r_busy <= 1'b1;
        r_addr <= s_axi_araddr;
        r_id   <= s_axi_arid;
        r_len  <= s_axi_arlen;
        r_beat <= '0;
      end
    end else begin
      if (s_axi_rvalid && s_axi_rready) begin
        if (s_axi_rlast) begin
          r_busy <= 1'b0;
        end else begin
          r_addr <= r_addr + 32'd4;
          r_beat <= r_beat + 8'd1;
        end
      end
    end
  end

  // -------------------------------------------------------------------
  // Write channel -- INCR bursts LEN 0..15, byte-strobed 32-bit beats
  // (SYS-04). BVALID follows accepted AW and final W, never earlier
  // (AXI-03), and every enabled byte is committed to `mem` on the same
  // edge the final W beat is accepted -- one full cycle before BVALID
  // can assert -- satisfying AXI-08's "commit before presenting
  // successful BVALID". WLAST alone gates the response (not a count
  // against AWLEN). Early W-before-AW is tolerated by simple
  // backpressure: WREADY stays low until AW is known (needed here,
  // since the write address comes only from AW), which the spec
  // guarantees arrives no later than the first W of the same
  // transaction (AXI-03); this cannot deadlock because AWREADY does not
  // depend on the write side.
  // -------------------------------------------------------------------
  logic        w_aw_have;
  logic [31:0] w_addr;  // running write pointer, latched from AWADDR
  logic [ 1:0] w_id;
  logic        w_last_seen;
  logic        w_b_valid;

  assign s_axi_awready = !w_aw_have;
  assign s_axi_wready  = w_aw_have && !w_last_seen;
  assign s_axi_bvalid  = w_b_valid;
  assign s_axi_bid     = w_id;
  assign s_axi_bresp   = 2'b00;  // OKAY; fabric already authorized region/alignment (SYS-04/AXI-02)

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      w_aw_have   <= 1'b0;
      w_addr      <= '0;
      w_id        <= '0;
      w_last_seen <= 1'b0;
      w_b_valid   <= 1'b0;
    end else begin
      if (s_axi_awvalid && s_axi_awready) begin
        w_aw_have <= 1'b1;
        w_addr    <= s_axi_awaddr;
        w_id      <= s_axi_awid;
      end
      if (s_axi_wvalid && s_axi_wready) begin
        if (s_axi_wstrb[0]) mem[w_addr[IDX_HI:2]][7:0] <= s_axi_wdata[7:0];
        if (s_axi_wstrb[1]) mem[w_addr[IDX_HI:2]][15:8] <= s_axi_wdata[15:8];
        if (s_axi_wstrb[2]) mem[w_addr[IDX_HI:2]][23:16] <= s_axi_wdata[23:16];
        if (s_axi_wstrb[3]) mem[w_addr[IDX_HI:2]][31:24] <= s_axi_wdata[31:24];
        w_addr <= w_addr + 32'd4;
        if (s_axi_wlast) w_last_seen <= 1'b1;
      end
      if (w_aw_have && w_last_seen && !w_b_valid) begin
        w_b_valid <= 1'b1;  // AXI-03: BVALID follows accepted AW and final W, never earlier
      end
      if (s_axi_bvalid && s_axi_bready) begin
        w_b_valid   <= 1'b0;
        w_aw_have   <= 1'b0;
        w_last_seen <= 1'b0;
      end
    end
  end

endmodule

`default_nettype wire
