# hw/rtl/ — synthesizable RTL. Written ONLY by the rtl-engineer role.

One directory per module: `hw/rtl/<mod>/<mod>.sv` (+ submodules). No testbench
code here, ever. Conventions (authoritative list in /AGENTS.md): Yosys-safe SV
subset, `default_nettype none`, `always_ff`/`always_comb` only, sync active-low
`rst_n`, every flop reset, `i_`/`o_` port prefixes, Wishbone B4 pipelined bus.
Gate to merge: `make lint MOD=<mod>` zero warnings + DV suite green.
