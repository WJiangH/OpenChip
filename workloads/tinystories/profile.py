#!/usr/bin/env python3
"""Analytical operator profile for the llama2.c "tinyllamas" TinyStories models.

No PyTorch, no checkpoint download, no randomness: a decoder-only transformer's
per-token work is a *deterministic* function of its hyperparameters, so the whole
profile is closed-form arithmetic.  That makes this file the auditable source of
every workload number quoted in workloads/tinystories/profile.md,
explore/npu-dse/results.md and docs/adr/0002-npu-architecture.md.

Hyperparameters are NOT guessed.  They are the seven int32 words of the llama2.c
legacy export header (dim, hidden_dim, n_layers, n_heads, n_kv_heads, vocab_size,
seq_len) read directly from the published .bin checkpoints via HTTP range request
-- see profile.md section 1 for the command and the raw output.

Run:
    .venv/bin/python3 workloads/tinystories/profile.py
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Iterable

# ---------------------------------------------------------------------------
# 1. Model configurations -- verified, not assumed.
# ---------------------------------------------------------------------------
# Source of truth: first 28 bytes of each checkpoint at
#   https://huggingface.co/karpathy/tinyllamas/resolve/main/<name>.bin
# decoded as struct '<7i' = (dim, hidden_dim, n_layers, n_heads, n_kv_heads,
# vocab_size, seq_len), the header written by llama2.c export.py legacy_export().
# A positive vocab_size signals a *shared* (tied) classifier weight, i.e. the
# output head reuses the token-embedding matrix.


@dataclass(frozen=True)
class ModelConfig:
    name: str
    dim: int
    hidden_dim: int
    n_layers: int
    n_heads: int
    n_kv_heads: int
    vocab_size: int
    max_seq_len: int
    tied_embeddings: bool = True

    @property
    def head_dim(self) -> int:
        assert self.dim % self.n_heads == 0
        return self.dim // self.n_heads

    @property
    def kv_dim(self) -> int:
        """Width of the K and V projections (< dim when GQA/MQA is used)."""
        return self.n_kv_heads * self.head_dim

    @property
    def n_params(self) -> int:
        """Exact parameter count, for cross-checking against the published size."""
        emb = self.vocab_size * self.dim
        attn = self.dim * self.dim + 2 * self.dim * self.kv_dim + self.dim * self.dim
        ffn = 3 * self.dim * self.hidden_dim
        norms = 2 * self.dim
        body = self.n_layers * (attn + ffn + norms)
        head = 0 if self.tied_embeddings else self.vocab_size * self.dim
        return emb + body + self.dim + head


MODELS = [
    #                     dim  hid   L   H  KVH  vocab   seq
    ModelConfig("stories260K", 64, 172, 5, 8, 4, 512, 512),
    ModelConfig("stories15M", 288, 768, 6, 6, 6, 32000, 256),
    ModelConfig("stories42M", 512, 1376, 8, 8, 8, 32000, 1024),
    ModelConfig("stories110M", 768, 2048, 12, 12, 12, 32000, 1024),
]
MODELS_BY_NAME = {m.name: m for m in MODELS}

# Published parameter counts from the llama2.c README model table, used as an
# independent check that the header decode and the shape algebra agree.
PUBLISHED_PARAMS = {
    "stories260K": 260_000,
    "stories15M": 15_000_000,
    "stories42M": 42_000_000,
    "stories110M": 110_000_000,
}

# ---------------------------------------------------------------------------
# 2. Numeric format assumptions (the acceptance anchor is int8 weights).
# ---------------------------------------------------------------------------
BYTES_PER_WEIGHT = 1  # int8 linear weights
BYTES_PER_KV = 1  # int8 KV cache
BYTES_PER_NORM_WEIGHT = 2  # RMSNorm gains kept at int16/fp16 -- too few to matter
FLOPS_PER_MAC = 2  # one multiply + one add


# ---------------------------------------------------------------------------
# 3. Operator inventory for ONE decode step (autoregressive, batch = 1).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Op:
    """A single matrix op in the decode step.  Shapes are (M x K) @ (K x N)."""

    name: str
    kind: str  # "proj" (has weights) | "attn" (reads KV cache)
    m: int
    k: int
    n: int
    count: int  # how many identical instances per token (e.g. per head, per layer)
    weight_bytes: int  # static weight bytes touched, per instance
    kv_bytes: int  # KV-cache bytes touched, per instance

    @property
    def macs(self) -> int:
        return self.m * self.k * self.n * self.count

    @property
    def flops(self) -> int:
        return FLOPS_PER_MAC * self.macs

    @property
    def total_weight_bytes(self) -> int:
        return self.weight_bytes * self.count

    @property
    def total_kv_bytes(self) -> int:
        return self.kv_bytes * self.count


@dataclass(frozen=True)
class VecOp:
    """A non-GEMM (elementwise / reduction / transcendental) op."""

    name: str
    n_elems: int
    flops_per_elem: float
    count: int
    transcendentals: int = 0  # exp / rsqrt / reciprocal invocations per instance

    @property
    def flops(self) -> int:
        return int(round(self.n_elems * self.flops_per_elem)) * self.count

    @property
    def total_transcendentals(self) -> int:
        return self.transcendentals * self.count


def gemm_inventory(cfg: ModelConfig, ctx: int) -> list[Op]:
    """All matrix ops for one decode step at context length `ctx`.

    `ctx` = number of keys attended to = current sequence length (the new token
    included).  Every projection is M=1 during decode: these are GEMVs.
    """
    d, hd, kvd = cfg.dim, cfg.head_dim, cfg.kv_dim
    L, H = cfg.n_layers, cfg.n_heads
    ops: list[Op] = []

    # -- per-layer projections (weights streamed once per token) --------------
    ops.append(Op("wq  (q proj)", "proj", 1, d, d, L, d * d * BYTES_PER_WEIGHT, 0))
    ops.append(Op("wk  (k proj)", "proj", 1, d, kvd, L, d * kvd * BYTES_PER_WEIGHT, 0))
    ops.append(Op("wv  (v proj)", "proj", 1, d, kvd, L, d * kvd * BYTES_PER_WEIGHT, 0))

    # -- attention: no weights, reads the KV cache ---------------------------
    # scores: per head, q_h[hd] . K_h[ctx, hd]^T  -> ctx logits
    ops.append(Op("attn scores (q.K^T)", "attn", 1, hd, ctx, L * H, 0, 0))
    # attn out: per head, p[ctx] . V_h[ctx, hd]   -> hd values
    ops.append(Op("attn out (p.V)", "attn", 1, ctx, hd, L * H, 0, 0))
    # KV traffic is per-layer, not per-head (heads share the cached K/V rows
    # under GQA), so it is booked once per layer here.
    ops.append(Op("KV-cache read", "attn", 1, 0, 0, L, 0, 2 * kvd * ctx * BYTES_PER_KV))
    ops.append(Op("KV-cache write", "attn", 1, 0, 0, L, 0, 2 * kvd * BYTES_PER_KV))

    ops.append(Op("wo  (out proj)", "proj", 1, d, d, L, d * d * BYTES_PER_WEIGHT, 0))
    ops.append(
        Op("w1  (ffn gate)", "proj", 1, d, cfg.hidden_dim, L, d * cfg.hidden_dim * BYTES_PER_WEIGHT, 0)
    )
    ops.append(
        Op("w3  (ffn up)", "proj", 1, d, cfg.hidden_dim, L, d * cfg.hidden_dim * BYTES_PER_WEIGHT, 0)
    )
    ops.append(
        Op("w2  (ffn down)", "proj", 1, cfg.hidden_dim, d, L, cfg.hidden_dim * d * BYTES_PER_WEIGHT, 0)
    )

    # -- classifier head (tied to the embedding table) ------------------------
    ops.append(
        Op("lm_head (logits)", "proj", 1, d, cfg.vocab_size, 1, d * cfg.vocab_size * BYTES_PER_WEIGHT, 0)
    )
    return ops


def vector_inventory(cfg: ModelConfig, ctx: int) -> list[VecOp]:
    """Non-GEMM ops for one decode step.  Cost model per element is explicit so
    the numbers can be argued with rather than trusted.

      RMSNorm(n) : x*x (n mul) + accumulate (n add) + rsqrt (1) + scale (n mul)
                   + gain (n mul)                                 -> 4n flops + 1 rsqrt
      RoPE(n)    : per rotated pair x' = x*c - y*s, y' = x*s + y*c
                   = 4 mul + 2 add per 2 elements                 -> 3n flops
      softmax(n) : max (n) + exp (n) + sum (n) + scale (n)        -> 4n flops, n exp
      SwiGLU(n)  : silu(a) = a*sigmoid(a) ~ exp + add + recip + mul (4)
                   then * b (1)                                   -> 5n flops, n exp
      residual(n): n adds
      score scale: n muls (1/sqrt(head_dim))
      requant(n) : int32 -> int8: mul + shift/round + saturate    -> 3n flops
    """
    d, hd, kvd = cfg.dim, cfg.head_dim, cfg.kv_dim
    L, H = cfg.n_layers, cfg.n_heads
    v: list[VecOp] = []

    v.append(VecOp("RMSNorm (attn + ffn)", d, 4, 2 * L, transcendentals=1))
    v.append(VecOp("RoPE (q)", d, 3, L))
    v.append(VecOp("RoPE (k)", kvd, 3, L))
    v.append(VecOp("score scale 1/sqrt(hd)", ctx, 1, L * H))
    v.append(VecOp("softmax (per head)", ctx, 4, L * H, transcendentals=ctx))
    v.append(VecOp("SwiGLU", cfg.hidden_dim, 5, L, transcendentals=cfg.hidden_dim))
    v.append(VecOp("residual add", d, 1, 2 * L))
    # int32 accumulator -> int8 requantisation on every GEMV output element
    n_requant = L * (d + 2 * kvd + d + 2 * cfg.hidden_dim + d) + cfg.vocab_size
    v.append(VecOp("requantise int32->int8", n_requant, 3, 1))
    v.append(VecOp("final RMSNorm", d, 4, 1, transcendentals=1))
    v.append(VecOp("output softmax / sampling", cfg.vocab_size, 4, 1, transcendentals=cfg.vocab_size))
    return v


# ---------------------------------------------------------------------------
# 4. Roll-ups
# ---------------------------------------------------------------------------
def summarise(cfg: ModelConfig, ctx: int) -> dict:
    ops = gemm_inventory(cfg, ctx)
    vecs = vector_inventory(cfg, ctx)

    gemm_macs = sum(o.macs for o in ops)
    gemm_flops = sum(o.flops for o in ops)
    nongemm_flops = sum(v.flops for v in vecs)
    transcendentals = sum(v.total_transcendentals for v in vecs)

    weight_bytes = sum(o.total_weight_bytes for o in ops)
    weight_bytes += cfg.n_layers * 2 * cfg.dim * BYTES_PER_NORM_WEIGHT  # RMSNorm gains
    weight_bytes += cfg.dim * BYTES_PER_NORM_WEIGHT  # final norm
    weight_bytes += cfg.dim * BYTES_PER_WEIGHT  # embedding row lookup
    kv_bytes = sum(o.total_kv_bytes for o in ops)

    total_flops = gemm_flops + nongemm_flops
    total_bytes = weight_bytes + kv_bytes
    return {
        "cfg": cfg,
        "ctx": ctx,
        "ops": ops,
        "vecs": vecs,
        "gemm_macs": gemm_macs,
        "gemm_flops": gemm_flops,
        "nongemm_flops": nongemm_flops,
        "total_flops": total_flops,
        "gemm_frac": gemm_flops / total_flops,
        "transcendentals": transcendentals,
        "weight_bytes": weight_bytes,
        "kv_bytes": kv_bytes,
        "total_bytes": total_bytes,
        "arith_intensity": gemm_macs / total_bytes,  # MAC per byte
        "kv_cache_full": 2 * cfg.kv_dim * cfg.max_seq_len * cfg.n_layers * BYTES_PER_KV,
    }


def prefill_summary(cfg: ModelConfig, ctx: int) -> dict:
    """Same weights, but M = ctx.  Included only to contrast arithmetic intensity
    with decode -- this is the case a square systolic array is built for."""
    d, hd, kvd = cfg.dim, cfg.head_dim, cfg.kv_dim
    L, H = cfg.n_layers, cfg.n_heads
    proj_macs_per_tok = 2 * d * d + 2 * d * kvd + 3 * d * cfg.hidden_dim
    # causal attention over the whole prefix: sum_t (t+1) ~ ctx*(ctx+1)/2 per head
    attn_macs = L * H * 2 * hd * ctx * (ctx + 1) // 2
    macs = ctx * L * proj_macs_per_tok + attn_macs + d * cfg.vocab_size
    s = summarise(cfg, ctx)
    return {
        "macs": macs,
        "weight_bytes": s["weight_bytes"],
        "arith_intensity": macs / s["weight_bytes"],
    }


# ---------------------------------------------------------------------------
# 5. Printing
# ---------------------------------------------------------------------------
def _mb(n: int) -> str:
    return f"{n/1e6:.3f} MB"


def _fmt(n) -> str:
    return f"{n:,}"


def print_model_table() -> None:
    print("=" * 108)
    print("TABLE 1 -- tinyllamas configurations (from the checkpoint headers; see profile.md section 1)")
    print("=" * 108)
    hdr = f"{'model':<13}{'dim':>5}{'hidden':>8}{'L':>4}{'H':>4}{'KVH':>5}{'hd':>5}{'kv_dim':>8}{'vocab':>8}{'seq':>6}{'params':>14}{'published':>12}"
    print(hdr)
    print("-" * 108)
    for m in MODELS:
        print(
            f"{m.name:<13}{m.dim:>5}{m.hidden_dim:>8}{m.n_layers:>4}{m.n_heads:>4}{m.n_kv_heads:>5}"
            f"{m.head_dim:>5}{m.kv_dim:>8}{m.vocab_size:>8}{m.max_seq_len:>6}{_fmt(m.n_params):>14}"
            f"{_fmt(PUBLISHED_PARAMS[m.name]):>12}"
        )
    print("-" * 108)
    print("params = exact shape algebra with tied (shared) classifier weights; matches the published")
    print("rounded sizes -- stories260K lands on 260,032, i.e. the header decode is self-consistent.")
    print()


def print_gemm_inventory(cfg: ModelConfig, ctx: int) -> None:
    s = summarise(cfg, ctx)
    print("=" * 108)
    print(f"TABLE 2 -- {cfg.name}: GEMM inventory for ONE decode token at ctx={ctx}")
    print("=" * 108)
    print(f"{'op':<22}{'M':>4}{'K':>7}{'N':>8}{'inst':>6}{'MACs total':>15}{'% MAC':>8}{'wt bytes':>13}{'kv bytes':>12}")
    print("-" * 108)
    tot = s["gemm_macs"]
    for o in s["ops"]:
        if o.macs == 0 and o.total_kv_bytes == 0:
            continue
        shape = f"{o.m:>4}{o.k:>7}{o.n:>8}" if o.macs else f"{'-':>4}{'-':>7}{'-':>8}"
        pct = f"{100*o.macs/tot:>7.2f}%" if o.macs else f"{'-':>8}"
        print(
            f"{o.name:<22}{shape}{o.count:>6}{_fmt(o.macs):>15}{pct}"
            f"{_fmt(o.total_weight_bytes):>13}{_fmt(o.total_kv_bytes):>12}"
        )
    print("-" * 108)
    print(
        f"{'TOTAL':<22}{'':>4}{'':>7}{'':>8}{'':>6}{_fmt(tot):>15}{'100.00%':>8}"
        f"{_fmt(s['weight_bytes']):>13}{_fmt(s['kv_bytes']):>12}"
    )
    print("Every M is 1: autoregressive decode issues GEMVs (matrix-vector), never GEMMs.")
    print()


def print_nongemm(cfg: ModelConfig, ctx: int) -> None:
    s = summarise(cfg, ctx)
    print("=" * 108)
    print(f"TABLE 3 -- {cfg.name}: non-GEMM work for ONE decode token at ctx={ctx}")
    print("=" * 108)
    print(f"{'op':<28}{'elems':>10}{'flops/el':>10}{'inst':>7}{'FLOPs':>14}{'% non-GEMM':>13}{'transcend.':>12}")
    print("-" * 108)
    tot = s["nongemm_flops"]
    for v in s["vecs"]:
        print(
            f"{v.name:<28}{_fmt(v.n_elems):>10}{v.flops_per_elem:>10}{v.count:>7}"
            f"{_fmt(v.flops):>14}{100*v.flops/tot:>12.1f}%{_fmt(v.total_transcendentals):>12}"
        )
    print("-" * 108)
    print(f"{'TOTAL non-GEMM':<28}{'':>10}{'':>10}{'':>7}{_fmt(tot):>14}{'100.0%':>13}{_fmt(s['transcendentals']):>12}")
    print("FLOP counts charge 1 flop per exp/rsqrt/reciprocal.  In hardware each of those is a LUT +")
    print("Newton step, so the transcendental column -- not the FLOP column -- sizes the special-function unit.")
    print()


def print_split(models: Iterable[ModelConfig], ctxs: Iterable[int]) -> None:
    print("=" * 108)
    print("TABLE 4 -- per-token totals: GEMM vs non-GEMM, bytes touched, arithmetic intensity")
    print("=" * 108)
    print(
        f"{'model':<13}{'ctx':>5}{'GEMM MAC':>13}{'GEMM FLOP':>13}{'nonGEMM FLOP':>14}"
        f"{'GEMM %':>9}{'wt bytes':>12}{'KV bytes':>11}{'MAC/byte':>10}"
    )
    print("-" * 108)
    for m in models:
        for c in ctxs:
            if c > m.max_seq_len:
                continue
            s = summarise(m, c)
            print(
                f"{m.name:<13}{c:>5}{_fmt(s['gemm_macs']):>13}{_fmt(s['gemm_flops']):>13}"
                f"{_fmt(s['nongemm_flops']):>14}{100*s['gemm_frac']:>8.2f}%"
                f"{_fmt(s['weight_bytes']):>12}{_fmt(s['kv_bytes']):>11}{s['arith_intensity']:>10.2f}"
            )
        print("-" * 108)
    print("MAC/byte ~ 1.0 for every model at every context length.  That is the whole story: int8 decode")
    print("does one multiply-accumulate per byte of weight delivered, so sustained MACs/cycle can never")
    print("exceed sustained bytes/cycle of weight bandwidth, whatever the MAC array looks like.")
    print()


def print_hotspots(cfg: ModelConfig, ctx: int) -> None:
    s = summarise(cfg, ctx)
    print("=" * 108)
    print(f"TABLE 5 -- {cfg.name} @ ctx={ctx}: where the bytes and the MACs actually go")
    print("=" * 108)
    groups = {
        "attention projections (wq/wk/wv/wo)": ["wq", "wk", "wv", "wo"],
        "FFN (w1/w3/w2)": ["w1", "w3", "w2"],
        "attention math (KV cache)": ["attn"],
        "classifier head (lm_head)": ["lm_head"],
    }
    print(f"{'group':<38}{'MACs':>14}{'% MAC':>9}{'bytes':>14}{'% bytes':>10}")
    print("-" * 108)
    tot_m, tot_b = s["gemm_macs"], s["total_bytes"]
    for label, prefixes in groups.items():
        macs = sum(o.macs for o in s["ops"] if any(o.name.startswith(p) for p in prefixes))
        byts = sum(
            o.total_weight_bytes + o.total_kv_bytes
            for o in s["ops"]
            if any(o.name.startswith(p) for p in prefixes)
        )
        if label.startswith("attention math"):
            byts = s["kv_bytes"]
            macs = sum(o.macs for o in s["ops"] if o.kind == "attn")
        print(f"{label:<38}{_fmt(macs):>14}{100*macs/tot_m:>8.2f}%{_fmt(byts):>14}{100*byts/tot_b:>9.2f}%")
    print("-" * 108)
    print(f"{'TOTAL':<38}{_fmt(tot_m):>14}{'100.00%':>9}{_fmt(tot_b):>14}{'100.00%':>10}")
    print(f"full KV cache at max_seq_len={cfg.max_seq_len}: {_fmt(s['kv_cache_full'])} bytes")
    print()


def print_prefill_contrast(models: Iterable[ModelConfig], ctx: int) -> None:
    print("=" * 108)
    print(f"TABLE 6 -- decode (M=1) vs prefill (M={ctx}) arithmetic intensity")
    print("=" * 108)
    print(f"{'model':<13}{'decode MAC/tok':>16}{'decode MAC/B':>14}{'prefill MACs':>16}{'prefill MAC/B':>15}{'ratio':>9}")
    print("-" * 108)
    for m in models:
        if ctx > m.max_seq_len:
            continue
        d = summarise(m, ctx)
        p = prefill_summary(m, ctx)
        print(
            f"{m.name:<13}{_fmt(d['gemm_macs']):>16}{d['arith_intensity']:>14.2f}"
            f"{_fmt(p['macs']):>16}{p['arith_intensity']:>15.1f}{p['arith_intensity']/d['arith_intensity']:>8.0f}x"
        )
    print("-" * 108)
    print("Prefill reuses each weight `ctx` times, so it is compute-bound and a big MAC array pays off.")
    print("Decode reuses each weight ONCE.  A chip sized for prefill is idle hardware during decode.")
    print()


def print_roofline(cfg: ModelConfig, ctx: int, f_mhz: float = 50.0) -> None:
    s = summarise(cfg, ctx)
    print("=" * 108)
    print(f"TABLE 7 -- {cfg.name} @ ctx={ctx}, {f_mhz:g} MHz: tokens/s bounded by MACs/cycle vs bytes/cycle")
    print("=" * 108)
    print(f"{'MACs/cyc':>9}{'compute cyc/tok':>18}{'tok/s (compute)':>18}   |{'bytes/cyc':>11}{'mem cyc/tok':>14}{'tok/s (mem)':>14}")
    print("-" * 108)
    lanes = [1, 2, 4, 8, 16, 32, 64, 256]
    for n in lanes:
        cyc_c = s["gemm_macs"] / n
        cyc_m = s["total_bytes"] / n
        print(
            f"{n:>9}{cyc_c:>18,.0f}{f_mhz*1e6/cyc_c:>18.2f}   |{n:>11}{cyc_m:>14,.0f}{f_mhz*1e6/cyc_m:>14.2f}"
        )
    print("-" * 108)
    print("The two halves are numerically the same table -- because MAC/byte ~= 1.  Achievable tok/s is")
    print("min(compute, memory), so the design rule is: build exactly as many MACs as you can feed bytes.")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="stories15M", choices=[m.name for m in MODELS])
    ap.add_argument("--ctx", type=int, nargs="*", default=[64, 128, 256])
    ap.add_argument("--freq-mhz", type=float, default=50.0)
    args = ap.parse_args()

    primary = MODELS_BY_NAME[args.model]

    print()
    print("OpenChip workload profile -- llama2.c tinyllamas (TinyStories), int8 decode")
    print(f"primary model: {primary.name}   contexts: {args.ctx}   clock: {args.freq_mhz:g} MHz")
    print()

    print_model_table()
    for c in args.ctx:
        if c <= primary.max_seq_len:
            print_gemm_inventory(primary, c)
    print_nongemm(primary, args.ctx[min(1, len(args.ctx) - 1)])
    print_split(MODELS, args.ctx)
    for c in args.ctx:
        if c <= primary.max_seq_len:
            print_hotspots(primary, c)
    print_prefill_contrast(MODELS, 128)
    print_roofline(primary, 128, args.freq_mhz)


if __name__ == "__main__":
    main()
