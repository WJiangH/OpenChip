# sw/ — RISC-V firmware. Written ONLY by the firmware-engineer role.

Lands in M3: crt0.S, link.ld (from the spec memory map), libminic/ (uart_putc,
printf-lite, timer), apps/hello, apps/irq_test, apps/coremark. Programs against
docs/spec/ register maps only — RTL-behavior workarounds require
`// WORKAROUND(issue#NN)` + an open issue. Every app prints a parseable
PASS/FAIL line over UART for the system testbench.
