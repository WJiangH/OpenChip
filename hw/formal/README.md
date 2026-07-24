# formal/ — SymbiYosys proofs. Written ONLY by the formal-verifier role.

`formal/<mod>/<mod>.sby` + a properties file (Yosys-safe SVA) bound to the DUT.
Standard sets: Wishbone B4 compliance on every bus port, FIFO invariants,
core safety properties. Every `assume` cites a spec §. Bounded results are
reported as "bounded to N", never "proven". Run: `make formal MOD=<mod>`.
