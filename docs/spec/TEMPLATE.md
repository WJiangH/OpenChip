# <Module> Specification

Status: draft | reviewed | frozen
Owner: spec-architect · Implements: milestone M<n>

## §1 Overview
One paragraph: what the module does and where it sits in SoC-1.

## §2 Interface
### §2.1 Clock & reset
`clk` (in), `rst_n` (in, synchronous, active-low). All state shall reset.

### §2.2 Bus interface
Wishbone B4 pipelined slave: `wb_cyc, wb_stb, wb_we, wb_adr[..], wb_dat_w[..],
wb_sel[..], wb_stall, wb_ack, wb_dat_r[..], wb_err`. The module shall ack every
accepted request within N cycles (state N).

### §2.3 Other signals
| Signal | Dir | Width | Description |

## §3 Register map
Base: (from soc_1.md memory map). All registers 32-bit, aligned.

| Offset | Name | Reset | Access | Description |
|---|---|---|---|---|
| 0x00 | CTRL | 0x0 | RW | ... |

### §3.1 <REG> details
Field-by-field: bits, name, access, reset, behavior ("shall" statements).

## §4 Functional behavior
Numbered "shall" statements. State machines as tables/mermaid. Timing contracts.

## §5 Error conditions
Behavior on illegal address, misaligned access, protocol violation. `wb_err` policy.

## §6 Verification notes (advisory)
Corner cases the architect knows about; DV shall treat these as a floor, not a ceiling.

## §7 Open questions
Tracked to zero before status: frozen.
