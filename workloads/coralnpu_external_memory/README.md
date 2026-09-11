# External-memory experiment workload v0.4

Workload for [CN-EXTMEM-01 v0.4](../../docs/spec/coralnpu_external_memory.md).
Repository publication candidate. This specifies execution against external
instruction/data memory, not a model-quality or throughput benchmark.

The required program performs two signed INT8 GEMVs, M=1, (K,N)=(64,64) and
(5,33). These exercise a full vector-sized problem and K/N tails already present
in the pinned upstream kernel family. Code, constants, operands, result arrays
and completion records reside in external memory; a 16 KiB DTCM stack is allowed.
No operand array is staged into TCM. Inputs change after ELF loading and before
release, so compiling correct answers into the image cannot pass both runs.

For run salt s in {0,17}, case number c in {0,1}, zero-based k,n:

- A[k] = ((13*k + 7*c + s) mod 31) - 15.
- B[k*N+n] = ((5*k + 3*n + 11*c + 2*s) mod 29) - 14; row-major K by N.
- C[n] = sum over k of int32(A[k])*int32(B[k*N+n]).
- Signature = sum over n of uint32(C[n])*(n+1), modulo 2^32.

Products and signed sums are exact, no rounding, zero-point, saturation or
requantization. The worst absolute sum is at most 64*15*14=13,440, so signed
INT32 overflow cannot occur. Signature multiplication/addition is unsigned
modulo arithmetic. The independent DV oracle derives the above equations and
must not import the software kernel. Host-side cost calculations in
[profile.json](profile.json) are input-size data, not a golden-model implementation.

| Case | A bytes | B bytes | C bytes | MAC operations | Useful data minimum |
|---|---:|---:|---:|---:|---:|
| 0 | 64 | 4096 | 256 | 4096 | 4416 bytes |
| 1 | 5 | 165 | 132 | 165 | 302 bytes |

Minimum counts exclude instruction traffic, repeated operand reads, 16-byte
fetch rounding, masked/padded data reads, stack, descriptors and status. They
are not predicted traffic, performance or efficiency. Each result acceptance
checks all 97 signed elements, not just the signature. Separate byte/halfword/
word probe locations exercise size and strobe behavior; they do not replace GEMV.

The chosen simulation memory aperture is 1 MiB at 0x20000000, with 64 KiB
executable budget and separate 4 KiB operand/result windows. This fits the small
experiment with guard space; it is not a DDR capacity recommendation. Fixed
single clock with a nominal simulation period of 10 ns is a time unit only.
Area, frequency closure, process/PDK, power, full model/weights, KV cache,
prefill/decode sizes and token-quality/throughput targets remain OPEN.

Selected source assets: pinned `tests/cocotb/rvv/ml_ops/gemma_kernels/`
`rvv_int8_matmul.cc` and `rvv_int8_matmul_runner.cc`. The separately reviewed software fixture belongs at
`sw/coralnpu_external_memory/`, including its tail-bounded RVV adaptation and
linker/startup/driver. This contract publication depends on that separate
software migration and contains no firmware.

Revision 0.2: each C has a 16-byte guard immediately before and after its
logical extent; all 64 guard bytes start and finish at 0xa5. Exact addresses
are in contract §3 and profile.json. These guard bytes add no useful GEMV data
traffic. Acceptance separately checks the startup `_ret` return slot and the
two designated external fetch lines; it does not require fetching unreachable
code or interpret fetches as retired instructions.

Revision 0.3: transfer-based coverage counts 4,330 input bytes and 388 C bytes.
The probe requires seven written bytes (+1,+6–+7,+12–+15), with 25 other bytes
retained at 0xa5. Positive record coverage requires 32 explicit write bytes;
negative record coverage requires 36, as enumerated in contract §6. Initialized
zero fields outside those mandatory sets may remain zero or be stored as zero;
all 64 record bytes are compared. The software deliverable is explicitly a
tail-bounded adaptation; the upstream hardware/generator remain unchanged.

Revision 0.4: the seven isolated error fixtures require independently observed
startup sentinel followed by handler return1 and 32 stable clocks after terminal
edge T, under contract CNEM-31. This prevents a stale return slot or transient
halt/record snapshot from establishing handler completion. The error workload
still stops before GEMV; no positive GEMV/probe coverage is added. The extra
observation is exactly 32 external clock edges, at most 320 ns in the nominal
simulation time unit, not a silicon performance target. The terminal deadline
is unchanged at cycle 1,000,000 inclusive; observation may end at 1,000,032.
Both reset profiles retain the abort/reload/positive-salt17 workload unchanged.
