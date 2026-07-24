# rtl/ — synthesizable RTL. Written ONLY by the rtl-designer role.

One directory per module: `rtl/<mod>/<mod>.sv` (+ submodules). No testbench
code here, ever. Conventions (authoritative list in /CLAUDE.md): Yosys-safe SV
subset, `default_nettype none`, `always_ff`/`always_comb` only, sync active-low
`rst_n`, every flop reset, `i_`/`o_` port prefixes, Wishbone B4 pipelined bus.
Gate to merge: `make lint MOD=<mod>` zero warnings + DV suite green.
