# blink — physical signoff record

Module: `blink` (docs/spec/blink.md, RTL `hw/rtl/blink/blink.sv`)
Milestone: M0 tracer bullet · Role: backend-engineer
Run tag: `m0-blink-signoff` · Completed: 2026-07-26 12:12:02 local
Flow: LibreLane `Classic`, 80/80 steps, exit 0

`runs/` is gitignored (Iron Rule / repo policy). Everything a reviewer needs to
judge the run is in this file; the raw run is reproducible from the command at
the bottom.

## 1. Provenance

| Item | Value |
|------|-------|
| LibreLane image | `ghcr.io/librelane/librelane:3.0.5` |
| Image digest | `sha256:ecabd075d0ddf6a2bd1cd4a32109c7dbb861ec007f7e4e423a9a081f8d23b8e2` |
| Image platform | `linux/arm64` (multi-arch index also carries `linux/amd64`) |
| LibreLane version | v3.0.5 |
| PDK | sky130A, ciel version `8afc8346a57fe1ab7934ba5a6056ea8b43078e71` |
| SCL | `sky130_fd_sc_hd` |
| OpenROAD | git `dcf36133a369abc8f3c5e5738cd4d82e4903c0e0` |
| Yosys (in image) | 0.62 |
| Magic | 8.3 rev 623 |
| Netgen | 1.5.316 |
| KLayout | 0.30.7 |
| ciel | 2.4.0 |
| Host Yosys (`make synth`) | 0.67+94 (oss-cad-suite `2026-07-26`) |
| Docker | 29.5.2 (darwin/arm64 host) |
| `hw/rtl/blink/blink.sv` sha256 | `631ead217511b062…` |
| `hw/pd/blink/config.yaml` sha256 | `a138242b385abd78…` |
| Repo commit at run time | `a7cec3f` (config/script files still uncommitted) |

**Image-tag verification.** `flow/versions.mk` pins
`ghcr.io/librelane/librelane:3.0.0` with a `TODO M0: verify` note. Result of the
check against the ghcr registry (201 tags enumerated): `3.0.0` exists and is a
valid multi-arch tag, there is **no `latest` tag** in this repository, and the
newest stable release is **`3.0.5`** (tag list ends `… 3.0.2, 3.0.3, 3.0.4,
3.0.5`; everything above that is `3.1.0.devNN` pre-releases). This signoff used
`3.0.5`. Recommendation for the orchestrator: pin
`LIBRELANE_IMAGE := ghcr.io/librelane/librelane:3.0.5` — ideally by digest,
since ghcr tags are mutable.

## 2. Constraints (never relaxed)

| Constraint | Value | Source |
|------------|-------|--------|
| Clock period | 20 ns (50 MHz) on `clk` | `flow/gates.mk` CLOCK_PERIOD_NS |
| WNS target | ≥ 0 | `flow/gates.mk` WNS_MIN |
| Max transition | 0.75 ns | PDK default, unchanged |
| Max capacitance | 0.2 pF | PDK default, unchanged |
| Max fanout | 10 | PDK default, unchanged |
| Corners analysed | 9 (nom/min/max × tt_025C_1v80 / ss_100C_1v60 / ff_n40C_1v95) | LibreLane STA_CORNERS |

The human-readable constraint reference lives in `hw/syn/blink.sdc`. LibreLane
generated its own SDC from `CLOCK_PORT`/`CLOCK_PERIOD`; the two agree on the
numbers that matter (20 ns period, 0.25 ns uncertainty, 0.15 ns clock
transition, 4 ns = 20% I/O delay).

## 3. Signoff numbers

### Area / utilisation
| Metric | Value |
|--------|-------|
| Die area | 150 × 150 µm = 22 500 µm² |
| Core area | 17 759.5 µm² |
| Std-cell area | 1 934.36 µm² |
| Core utilisation | **10.89 %** |
| Std-cell instances | **390** = 245 tap + 26 sequential + 26 timing-repair buffers + 7 clock buffers + 86 combinational |
| Tap cells | 245 |
| Fill cells | 4 383 |
| Routed wirelength | 2 509 µm (longest net 93.91 µm) |
| Total power (nom_tt) | 147.3 µW |
| Worst IR drop | 60.1 µV |

Utilisation is low by construction: 390 cells cannot fill a die that has to be
large enough for a sane PDN strap pitch and core ring. This is a tracer bullet,
not an area-optimised block.

### Timing @ 20 ns (50 MHz)
| Metric | Value | Gate |
|--------|-------|------|
| Setup WNS | **0** (no violating paths) | ≥ 0 ✅ |
| Setup TNS | 0 | ✅ |
| Setup worst slack | **+11.382 ns** (worst corner `max_ss_100C_1v60`) | — |
| Hold WNS | **0** | ≥ 0 ✅ |
| Hold TNS | 0 | ✅ |
| Hold worst slack | **+0.1069 ns** (worst corner `min_ff_n40C_1v95`) | — |
| Clock skew (setup / hold) | 0.2510 ns / −0.2510 ns | — |

Setup worst slack per corner (ns): ss 11.382 / 11.421 / 11.462 · tt 14.029 /
14.044 / 14.061 · ff 14.690 / 14.699 / 14.710. The counter's critical path uses
~43 % of the period at the slow corner; blink has ~8.6 ns of margin to the spec
clock even at ss_100C_1v60.

### Design rules and physical verification
| Check | Result | Gate |
|-------|--------|------|
| Magic DRC | **0 errors** | 0 ✅ |
| KLayout DRC | **0 errors** | 0 ✅ |
| Magic illegal overlaps | 0 | ✅ |
| Detailed-route DRC | 0 (converged at iteration 3: 13 → 7 → 7 → 0) | ✅ |
| Netgen LVS | **"Circuits match uniquely."** — 0 errors, 0 unmatched nets / devices / pins, 0 property fails | clean ✅ |
| Antenna | **0 net violations, 0 pin violations**, 0 diodes inserted | 0 ✅ |
| KLayout XOR (magic vs klayout streamout) | 0 differences | ✅ |
| Disconnected pins | 0 | ✅ |
| Power-grid violations | 0 (VPWR 0, VGND 0) | ✅ |
| Max slew violations | **0** in all 9 corners | ✅ |
| Max cap violations | 0 in all 9 corners | ✅ |
| Max fanout violations | 0 in all 9 corners | ✅ |
| Manufacturability report | Antenna ✅ / LVS ✅ / DRC ✅ | ✅ |

GDS: `runs/m0-blink-signoff/final/gds/blink.gds` (plus LEF, DEF, SPEF, SDF,
netlists, `.lib` under `final/`). Not committed — regenerate with the command in
§6.

## 4. Violations closed — cause → action

**V1 · 11 max-slew violations in all three `*_ss_100C_1v60` corners** (first run,
tag `…-a`, stock settings): 0.921 ns against the 0.75 ns limit, all 11 pins on
one net — `net3`, the buffered `rst_n` distribution net, and its 10 loads.

- *Cause:* blink is ~145 logic instances (plus 245 tap cells) on a die sized by
  PDN strap pitch rather than by the logic, so utilisation is ~11 % and nets
  sprawl. `net3` was routed as a single **162.58 µm
  unbuffered wire**. OpenROAD's design-repair steps run with no wire-length cap
  by default (`DESIGN_REPAIR_MAX_WIRE_LENGTH: 0`), so nothing ever broke that
  wire up; its RC plus 10 load pins exceeds the transition limit as soon as the
  slow libraries are used. The tt corner stayed under the limit, which is why
  the repair steps (which optimise against the default corner with an estimated
  parasitic model) saw nothing to fix.
- *Action:* cap the wire length the repair steps tolerate at 60 µm
  (`DESIGN_REPAIR_MAX_WIRE_LENGTH` / `GRT_DESIGN_REPAIR_MAX_WIRE_LENGTH`) and
  raise their slew margin to 45 % to cover the corner spread. Both settings make
  the optimiser's target **stricter**; the 0.75 ns limit, the 20 ns clock and
  every checker threshold are untouched (Iron Rule 5).
- *Evidence:* longest net fell 162.58 µm → 93.91 µm, max-slew violations 11 → 0
  in all 9 corners, at the cost of 3 extra cells (387 → 390) and no timing loss
  (setup worst slack actually improved 10.95 → 11.38 ns).

Dead ends, recorded here and in `config.yaml` so nobody re-treads them. Only the
baseline (`m0-blink-20260726`, the run that *shows* the 11 violations) and the
final `m0-blink-signoff` run were kept on disk; the intermediate run
directories were deleted after their numbers were transcribed here.

| Run | Change | Result |
|-----|--------|--------|
| `…-b` | exclude `clkdlybuf4s*` cells | 11 violations and **worse** (1.064 ns) — the resizer just picked `buf_1`; cell choice was a symptom |
| `…-c` | `MAX_FANOUT_CONSTRAINT: 6` + margins | slew 0, but the 6-fanout rule then flagged the CTS root buffer `clkbuf_0_clk/X` (8 sinks) — trading one violation for another is not closure |
| `…-d` | slew margins only | 11 violations, byte-identical to `…-a` |
| `…-e` | `MAX_FANOUT_CONSTRAINT: 8` | 9 violations — still too wide |
| `…-f` | fanout 6 + `CTS_SINK_CLUSTERING_SIZE: 6` | root fanout stayed 8; the knob does not change what CTS builds here |
| `…-g` | die shrunk to 80 × 80 µm, stock knobs | **21** violations — denser placement did not help |
| `…-h` | 80 × 80 + fanout 6 + clustering | slew 0, fanout still flagged |
| `…-i` | `DEFAULT_CORNER: nom_ss_100C_1v60` | 11 violations, byte-identical to `…-a` |
| `…-j` | wire-length cap 60 µm + margins | all checkers 0 → adopted |

No RTL change was needed, and none was made: the fix is entirely in the physical
flow. No issue filed against `hw/rtl/`.

## 5. Synthesis gate (`make synth MOD=blink`)

Script: `hw/syn/blink.ys` (Tcl — the Makefile invokes `yosys -c`), constraints
reference `hw/syn/blink.sdc`. Status: **PASS (exit 0)**.

- Elaboration clean, `hierarchy -check` clean.
- **Latch check: PASS** — `select -assert-none` finds no `$dlatch/$dlatchsr/$sr`
  or `$_DLATCH_*/$_DLATCHSR_*/$_SR_*` cells.
- Generic: 104 cells — 25 × `$_SDFF_PP0_`, 1 × `$_SDFFE_PN0P_`, 21 × `$_XOR_`,
  41 × `$_AND_`, rest small gates. 26 flops = 25 counter bits + `o_led`,
  all synchronous-reset, matching BLINK-01/06/08.
- Mapped to `sky130_fd_sc_hd` (liberty auto-discovered from the ciel PDK cache,
  honouring the PDK's `no_synth.cells` + `drc_exclude.cells` as `-dont_use` so
  the cell set matches what LibreLane may use): **106 cells, 1 242.44 µm²**,
  26 × `dfxtp_2` (44.5 % of area sequential), no unmapped cells, `check -assert`
  clean.

`make synth` does **not** produce timing numbers: OpenSTA is not installed on
this host, and the oss-cad-suite build in use does not ship it. All timing in §3
comes from the LibreLane OpenSTA steps (multi-corner, post-RCX). If a standalone
OpenSTA appears on the host, `hw/syn/blink.sdc` is ready for it.

## 6. Reproducing this run

```bash
docker run --rm \
  -v "$PWD":/work -w /work \
  -v "$HOME/.ciel":/root/.ciel \
  ghcr.io/librelane/librelane:3.0.5 \
  librelane --pdk-root /root/.ciel --run-tag m0-blink-signoff hw/pd/blink/config.yaml
```

The `-v "$HOME/.ciel":/root/.ciel` mount is what keeps the ~2.1 GB sky130A PDK
out of the container's ephemeral layer; without it every run re-downloads the
whole PDK. `make gds MOD=blink` currently omits this mount (see §7).

## 7. Open items / not covered by this signoff

1. **Gate-level simulation has not been run.** The backend definition of done
   requires GL-sim with the post-layout SDF to re-pass the same stimulus that
   passed at RTL. `make glsim` is still an M4 stub, and blink has no firmware —
   the equivalent obligation is re-running the `hw/dv/blink` cocotb suite against
   `final/nl/blink.nl.v` + `final/sdf/*.sdf`. **Until that passes, this is a
   physical-implementation signoff, not a full signoff.**
2. **`make gds MOD=blink` needs two orchestrator-side fixes** (the Makefile is
   not backend territory): add the PDK cache volume mount and `--pdk-root`, and
   re-pin the image tag to `3.0.5`. As written, the target runs, but it
   re-downloads the entire PDK into a throwaway container layer every time.
3. **`make synth MOD=blink` fails on a stock macOS host** for a reason unrelated
   to the script: Apple ships GNU Make 3.81, which resolves recipe executables
   against make's *own* `PATH`, ignoring the `export PATH :=` in the Makefile.
   The gate passes when the toolchain is on the caller's `PATH`. Orchestrator
   fix: reference tools through an absolute-path variable, or force recipes
   through a shell.
4. **Timing is signed off against LibreLane's generated SDC**, not
   `hw/syn/blink.sdc`. The values agree, but they are two sources. Wiring
   `PNR_SDC_FILE`/`SIGNOFF_SDC_FILE` to a single checked-in SDC is the right
   follow-up once a module has non-trivial I/O timing.
5. Utilisation (10.9 %) and die area are not optimised, deliberately — see §3.
