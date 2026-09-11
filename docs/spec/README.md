# Specifications — the single source of truth

One file per architectural unit (`uart.md`, `rv32_core.md`, `soc_1.md`, …),
written and owned by the **chief-architect** role. RTL, DV, formal, and firmware
all derive from these files and cite sections by number ("spec §3.2").

Rules:
- Numbered sections. Requirements use **shall** (each "shall" = a DV test
  obligation). Implementation freedom uses **may**.
- Registers: offset, reset value, field map with access types (RW/RO/W1C), behavior.
- Interfaces: complete signal table (name, direction, width, meaning).
- A spec is done when a DV engineer who has never seen the RTL can write a
  complete golden model from it alone.

Start from [TEMPLATE.md](TEMPLATE.md).

The [CoralNPU autonomous small-model SoC](coralnpu_soc.md) defines the complete
logical chip target; its detailed executable and physical qualification remain
open. The [CoreAXI](coralnpu_external_memory.md) and [tiny-model](coralnpu_llm.md)
experiments retain their separate contracts.
