# Workload profile — llama2.c "tinyllamas" (TinyStories), int8 decode

Role: chief-architect · Status: data deliverable (no spec implied) · Date: 2026-07-26

Reproduce every number in this file with:

```bash
.venv/bin/python3 workloads/tinystories/profile.py            # stories15M, ctx 64/128/256
.venv/bin/python3 workloads/tinystories/profile.py --model stories260K
```

The profile is **analytical**, not measured: a decoder-only transformer's per-token
work is a closed-form function of its hyperparameters, so no PyTorch, no checkpoint
download and no sampling is needed. That also makes it auditable — every count in
`profile.py` is arithmetic you can check by hand.

---

## 1. Model configurations — verified, not assumed

The llama2.c legacy export writes a 28-byte header of seven `int32`s:
`(dim, hidden_dim, n_layers, n_heads, n_kv_heads, vocab_size, seq_len)`
([`export.py`, `legacy_export()`](https://github.com/karpathy/llama2.c/blob/master/export.py),
consumed by [`run.c`](https://github.com/karpathy/llama2.c/blob/master/run.c)).
I read those 28 bytes straight out of the published checkpoints rather than trusting
any secondary table:

```bash
for m in stories260K/stories260K stories15M stories42M stories110M; do
  curl -sL -r 0-27 "https://huggingface.co/karpathy/tinyllamas/resolve/main/$m.bin" \
  | python3 -c "import struct,sys; print(struct.unpack('<7i', sys.stdin.buffer.read(28)))"
done
```

Raw output (2026-07-26, HTTP 206 on all four):

| checkpoint | raw header tuple |
|---|---|
| `stories260K/stories260K.bin` | `(64, 172, 5, 8, 4, 512, 512)` |
| `stories15M.bin` | `(288, 768, 6, 6, 6, 32000, 256)` |
| `stories42M.bin` | `(512, 1376, 8, 8, 8, 32000, 1024)` |
| `stories110M.bin` | `(768, 2048, 12, 12, 12, 32000, 1024)` |

Decoded, with derived quantities and an independent parameter-count check:

| model | dim | hidden_dim | n_layers | n_heads | n_kv_heads | head_dim | kv_dim | vocab | max_seq_len | params (exact) | published |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| stories260K | 64 | 172 | 5 | 8 | **4** | 8 | 32 | 512 | 512 | 260,032 | ~260 K |
| **stories15M** | **288** | **768** | **6** | **6** | **6** | **48** | **288** | **32000** | **256** | **15,191,712** | ~15 M |
| stories42M | 512 | 1376 | 8 | 8 | 8 | 64 | 512 | 32000 | 1024 | 41,689,600 | ~42 M |
| stories110M | 768 | 2048 | 12 | 12 | 12 | 64 | 768 | 32000 | 1024 | 109,529,856 | ~110 M |

Cross-checks that the decode is right, not just plausible:

- **stories260K lands on 260,032 params** — within 0.01 % of its name. That only
  works if `hidden_dim = 172`, which is `multiple_of = 4` applied to
  `⌊⅔·4·dim⌋ = 170`. A guessed `multiple_of = 32` (→ 192) or the Llama default
  `256` (→ 256) both miss the published size. The header settles it.
- The `vocab_size` field is **positive** in all four headers. In llama2.c a negative
  `vocab_size` is the flag for *unshared* classifier weights, so all four models
  **tie the output head to the token-embedding matrix**
  ([`run.c`, `read_checkpoint()`](https://github.com/karpathy/llama2.c/blob/master/run.c)).
  The parameter counts above assume tying and match; without tying stories15M
  would be 24.4 M, which contradicts its name.
- stories260K is the only one using **GQA** (`n_kv_heads = 4 < n_heads = 8`), so its
  KV cache is half-width. The other three are plain MHA.

Architecture (per [llama2.c README](https://github.com/karpathy/llama2.c)): RoPE
positional embeddings, RMSNorm (no LayerNorm, no bias), SwiGLU FFN, `bias=False` on
every `nn.Linear`. Sources: [llama2.c repo](https://github.com/karpathy/llama2.c),
[karpathy/tinyllamas on HuggingFace](https://huggingface.co/karpathy/tinyllamas).

**Primary target: stories15M.** It is the smallest checkpoint that produces
recognisably coherent English (val loss 1.072 vs 1.297 for stories260K), so it is the
right acceptance anchor. stories260K is kept in scope as the *bring-up* model.

---

## 2. The money question: how much of a token is GEMM?

Per generated token, stories15M at ctx = 128:

| | count | share |
|---|---:|---:|
| GEMV MACs | 15,630,336 | — |
| GEMV FLOPs (2/MAC) | 31,260,672 | **98.89 %** |
| non-GEMM FLOPs | 352,448 | 1.11 % |
| **total FLOPs/token** | **31,613,120** | 100 % |

Across the family (`ctx = 128`):

| model | GEMV MACs/token | GEMM % of FLOPs | weight bytes (int8) | KV bytes | **MAC/byte** |
|---|---:|---:|---:|---:|---:|
| stories260K | 341,248 | 93.51 % | 260,800 | 41,280 | 1.13 |
| **stories15M** | **15,630,336** | **98.89 %** | **15,195,744** | **445,824** | **1.00** |
| stories42M | 42,729,472 | 99.40 % | 41,698,816 | 1,056,768 | 1.00 |
| stories110M | 111,869,952 | 99.61 % | 109,549,824 | 2,377,728 | 1.00 |

**Answer: ~99 % of per-token work is GEMM.** That is the accelerate-this case, and it
is unambiguous — there is no second hotspot worth a datapath.

### But the shapes are the story, not the fraction

Every one of those GEMMs has **M = 1**. Autoregressive decode with batch 1 issues
matrix-*vector* products, not matrix-matrix. Full inventory for one stories15M token
at ctx = 128:

| op | M | K | N | instances | MACs total | % of MACs | weight bytes |
|---|---:|---:|---:|---:|---:|---:|---:|
| `wq` q proj | 1 | 288 | 288 | 6 | 497,664 | 3.18 % | 497,664 |
| `wk` k proj | 1 | 288 | 288 | 6 | 497,664 | 3.18 % | 497,664 |
| `wv` v proj | 1 | 288 | 288 | 6 | 497,664 | 3.18 % | 497,664 |
| attn scores `q·Kᵀ` | 1 | 48 | 128 | 36 | 221,184 | 1.42 % | 0 (KV cache) |
| attn out `p·V` | 1 | 128 | 48 | 36 | 221,184 | 1.42 % | 0 (KV cache) |
| `wo` out proj | 1 | 288 | 288 | 6 | 497,664 | 3.18 % | 497,664 |
| `w1` ffn gate | 1 | 288 | 768 | 6 | 1,327,104 | 8.49 % | 1,327,104 |
| `w3` ffn up | 1 | 288 | 768 | 6 | 1,327,104 | 8.49 % | 1,327,104 |
| `w2` ffn down | 1 | 768 | 288 | 6 | 1,327,104 | 8.49 % | 1,327,104 |
| **`lm_head` logits** | **1** | **288** | **32000** | **1** | **9,216,000** | **58.96 %** | **9,216,000** |
| **TOTAL** | | | | | **15,630,336** | 100 % | **15,195,744** |

Two things fall out immediately:

1. **The classifier head is the workload.** 59 % of MACs and 59 % of weight bytes are
   one single GEMV: `1×288 @ 288×32000`. The entire six-layer transformer body is the
   *other* 41 %. Any architecture that optimises the transformer body and treats the
   vocabulary projection as an afterthought has optimised 41 % of the problem.
   (This is a property of *tiny* models: 32000 vocab against dim 288 is a wildly
   top-heavy ratio. stories260K, with vocab 512, does not have this problem at all.)
2. **All reduction lengths K are small and friendly**: 288, 768, 48, 128 — every one
   divisible by 16. Output lengths N are 288 / 768 / 32000 / 128 / 48 — also all
   divisible by 16 except head_dim = 48 (divisible by 16) and ctx (a power of two).
   A 16-wide datapath pads nothing on this model.

### Non-GEMM work (ctx = 128, stories15M)

| op | elements | FLOPs/elem | instances | FLOPs | share | transcendentals |
|---|---:|---:|---:|---:|---:|---:|
| RMSNorm (attn + ffn) | 288 | 4 | 12 | 13,824 | 3.9 % | 12 rsqrt |
| RoPE (q) | 288 | 3 | 6 | 5,184 | 1.5 % | 0 |
| RoPE (k) | 288 | 3 | 6 | 5,184 | 1.5 % | 0 |
| score scale `1/√head_dim` | 128 | 1 | 36 | 4,608 | 1.3 % | 0 |
| softmax (per head) | 128 | 4 | 36 | 18,432 | 5.2 % | 4,608 exp |
| SwiGLU | 768 | 5 | 6 | 23,040 | 6.5 % | 4,608 exp |
| residual add | 288 | 1 | 12 | 3,456 | 1.0 % | 0 |
| **requantise int32→int8** | 49,856 | 3 | 1 | **149,568** | **42.4 %** | 0 |
| final RMSNorm | 288 | 4 | 1 | 1,152 | 0.3 % | 1 rsqrt |
| output softmax / sampling | 32,000 | 4 | 1 | **128,000** | **36.3 %** | 32,000 exp |
| **TOTAL** | | | | **352,448** | 100 % | **41,229** |

The per-element cost model is spelled out in `vector_inventory()` in `profile.py` so it
can be argued with. Two honest caveats:

- The FLOP column charges **1 flop per `exp` / `rsqrt` / reciprocal**. In hardware each
  is a LUT plus a Newton step. It is the **transcendental column (41,229/token)** that
  sizes the special-function unit, not the FLOP column.
- 79 % of the non-GEMM FLOPs are **requantisation and output softmax** — both direct
  consequences of the int8 + 32000-vocab choice, not of the transformer maths.

The non-GEMM tail totals **106,336 element-operations per token**. Amdahl's law on that
number: at 8 MACs/cycle with an 8-wide vector lane it costs 13,292 cycles against
1,953,792 GEMV cycles — **0.7 %** of the token, ignorable. At 256 MACs/cycle the GEMV
work drops to 61,056 cycles and the same tail through a *one-element-per-cycle* lane
would cost 106,336 cycles — **64 %** of the token, i.e. the "accelerator" would spend
most of its time not accelerating. The wider the array, the wider the vector lane has
to be to keep up (see `explore/npu-dse/results.md`).

---

## 3. Bytes: the number that actually decides the architecture

Per token, stories15M at ctx = 128:

| traffic | bytes |
|---|---:|
| int8 linear weights | 15,191,712 |
| RMSNorm gains (int16) + embedding row | 4,032 |
| KV-cache read (`2 · kv_dim · ctx · n_layers`) | 442,368 |
| KV-cache write | 3,456 |
| **total per token** | **15,641,568** |
| full KV cache at max_seq_len = 256 | 884,736 |

**Arithmetic intensity = 15,630,336 MAC / 15,641,568 B = 1.00 MAC/byte.**

That is not a coincidence and it is not model-specific: in int8 decode with batch 1,
every weight byte is loaded, used for exactly one multiply-accumulate, and discarded.
The value is ~1.0 for all four models at all context lengths (stories260K drifts to
1.13 only because its 512-entry vocabulary makes its KV/attention share larger).

### Implication, stated plainly

> **Decode is memory-bound, not TOPS-bound.** Sustained MACs/cycle can never exceed
> sustained weight *bytes*/cycle. At 50 MHz, N MACs/cycle requires exactly N B/cycle
> = N × 50 MB/s of weight delivery. Any MAC array wider than the weight port is
> silicon that idles.

Concretely (stories15M, ctx = 128, 50 MHz), the compute-bound and memory-bound tables
are numerically identical:

| MACs/cycle = bytes/cycle | cycles/token | tokens/s |
|---:|---:|---:|
| 1 | 15,630,336 | 3.20 |
| 2 | 7,815,168 | 6.40 |
| 4 | 3,907,584 | 12.80 |
| **8** | **1,953,792** | **25.6** |
| 16 | 976,896 | 51.2 |
| 64 | 244,224 | 204.7 |
| 256 | 61,056 | 818.9 |

For calibration: comfortable human reading speed is roughly 4–6 tokens/s, so
**4–8 MACs/cycle already delivers a live, readable demo** on stories15M.

---

## 4. Prefill is a different workload — do not size for it

| model | decode MAC/byte | prefill (128 tok) MACs | prefill MAC/byte | intensity ratio |
|---|---:|---:|---:|---:|
| stories260K | 1.13 | 34,316,288 | 131.6 | 116× |
| stories15M | 1.00 | 802,160,640 | 52.8 | 53× |
| stories42M | 1.00 | 3,322,019,840 | 79.7 | 80× |
| stories110M | 1.00 | 11,048,386,560 | 100.9 | 101× |

Prefill has M = ctx, so each weight is reused `ctx` times and the workload becomes
compute-bound — the regime a square systolic array is designed for. But prefill runs
**once per prompt** and decode runs **once per token**. A TinyStories demo prompt is a
handful of tokens. Sizing the chip for prefill buys a one-off latency win and pays for
it on every token thereafter.

---

## 5. What this profile does NOT settle

Deliberately out of scope here; these belong to the DSE and then the spec:

1. **Quantisation arithmetic.** Per-tensor vs per-channel scales, rounding mode,
   accumulator width, saturation behaviour. The 49,856 requantisations/token are
   ~42 % of non-GEMM FLOPs, so this is a real datapath decision, not a detail.
2. **Where the weights live.** 15.2 MB does not fit on a sky130 die by three orders of
   magnitude — see `explore/npu-dse/results.md` Table B. This profile only establishes
   *how many bytes must move*.
3. **KV-cache precision.** Modelled at int8. fp16 doubles KV traffic (still < 6 % of
   the token at ctx ≤ 256, so it is affordable if accuracy needs it).
4. **Softmax numerics.** The max-subtraction pass is counted but its precision
   requirement is unanalysed; it is the classic source of token-mismatch against
   PyTorch.
5. **Tokeniser / sampling.** Argmax vs temperature sampling changes nothing in the
   GEMM profile but does change the bit-exactness contract with PyTorch.

---

## Sources

- llama2.c repository (architecture, model table, checkpoint URLs): <https://github.com/karpathy/llama2.c>
- llama2.c `model.py` (`ModelArgs`, `FeedForward` hidden_dim rule, RMSNorm, RoPE): <https://github.com/karpathy/llama2.c/blob/master/model.py>
- llama2.c `run.c` (`read_checkpoint`, negative-vocab shared-weights flag): <https://github.com/karpathy/llama2.c/blob/master/run.c>
- llama2.c `export.py` (`legacy_export` header layout): <https://github.com/karpathy/llama2.c/blob/master/export.py>
- tinyllamas checkpoints (headers read via HTTP range request, §1): <https://huggingface.co/karpathy/tinyllamas>
