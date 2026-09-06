"""Architecture arithmetic only; no inference, cycle model, golden model or PPA.

Source fields transcribed from official Qwen config.json files on 2026-09-05.
Reproduce offline with: python3 profile.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODELS = [
    dict(name="Qwen3-0.6B", hidden=1024, intermediate=3072, layers=28, heads=16),
    dict(name="Qwen3-1.7B", hidden=2048, intermediate=6144, layers=28, heads=16),
    dict(name="Qwen3-4B", hidden=2560, intermediate=9728, layers=36, heads=32),
]
for m in MODELS:
    m.update(kv_heads=8, head_dim=128, vocab=151936, tied_embeddings=True,
             source=f"https://huggingface.co/Qwen/{m['name']}/raw/main/config.json")


def estimate(m, context, weight_bits):
    h, f, l = m["hidden"], m["intermediate"], m["layers"]
    q, k = m["heads"] * m["head_dim"], m["kv_heads"] * m["head_dim"]
    # Q/K/V/O and SwiGLU gate/up/down; q width is NOT necessarily hidden size.
    shapes = [(h, q), (h, k), (h, k), (q, h), (h, f), (h, f), (f, h)]
    body = l * sum(a * b for a, b in shapes)
    head = h * m["vocab"]
    matrix_params = body + head  # Tied embedding / lm_head stored once.
    norm_params = l * (2 * h + 2 * m["head_dim"]) + h
    # Exploration format: symmetric groups of 128, one 16-bit scale/group.
    # All these dimensions divide 128; no padding or zero-points assumed.
    assert all(a % 128 == 0 and b % 128 == 0 for a, b in shapes)
    assert matrix_params % 128 == 0
    weights = matrix_params * weight_bits // 8 + matrix_params // 128 * 2 + norm_params * 2
    kv_per_token = 2 * l * k * 2  # K+V; proposed 16-bit storage, batch=1.
    kv = kv_per_token * context
    # Context includes the token currently being processed. Conservative traffic
    # counts its KV read as well as write, without local reuse across layers.
    traffic = weights + kv + kv_per_token + h * 2
    macs = body + head + 2 * l * q * context
    s = 1024
    # Causal useful attention MACs; full-square execution costs more.
    prefill = body * s + l * q * s * (s + 1) + head
    return dict(model=m["name"], context=context, weight_bits=weight_bits,
                params=matrix_params + norm_params, weight_bytes=weights,
                kv_bytes=kv, resident_floor_bytes=weights + kv,
                decode_bytes=traffic, decode_macs=macs, prefill_1024_macs=prefill,
                bandwidth_for_20_tps_gbps=traffic * 20 / 1e9)


def main():
    rows = [estimate(m, t, b) for m in MODELS for t in [2048, 8192] for b in [4, 8]]
    budgets = [dict(name="A", peak_tmac_s=0.25, effective_gbps=16),
               dict(name="B", peak_tmac_s=1, effective_gbps=32),
               dict(name="C", peak_tmac_s=4, effective_gbps=64)]
    sweep = []
    for row in rows:
        for budget in budgets:
            sweep.append(dict(model=row["model"], context=row["context"], weight_bits=row["weight_bits"],
                              budget=budget["name"],
                              optimistic_tps=min(budget["effective_gbps"] * 1e9 / row["decode_bytes"],
                                                 budget["peak_tmac_s"] * 1e12 / row["decode_macs"]),
                              prefill_compute_floor_s=row["prefill_1024_macs"] / (budget["peak_tmac_s"] * 1e12)))
    data = dict(status="analytical-only; not a frozen requirement or measured performance",
                retrieved="2026-09-05", models=MODELS, rows=rows, budgets=budgets, sweep=sweep)
    (HERE / "estimates.json").write_text(json.dumps(data, indent=2) + "\n")
    lines = ["# LLM 容量与吞吐预算探针", "", "状态：解析估算；未校准；不是实测性能或 PPA。", "",
             "配置来源见 [需求草案](README.md#来源)。GB=10⁹ B，GiB=2³⁰ B；1 MAC 不写成 1 OPS。", "",
             "| 模型 | Context | 权重位数 | 权重含 scales GB | KV GiB | 权重+KV GiB | 20 token/s 所需建模带宽 GB/s |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['model']} | {r['context']} | {r['weight_bits']} | {r['weight_bytes']/1e9:.3f} | {r['kv_bytes']/2**30:.3f} | {r['resident_floor_bytes']/2**30:.3f} | {r['bandwidth_for_20_tps_gbps']:.2f} |")
    lines += ["", "容量列不含运行时、激活、scratch、固件、分配碎片、ECC 或模型装载副本，不能据此直接选 DRAM 容量。", "",
              "## 预算点比较", "", "预算点均为假设，不代表已选 MAC 阵列、频率、存储器或可实现的功耗面积。", "",
              "| 预算点 | 峰值 TMAC/s | 外存有效 GB/s |", "|---|---:|---:|"]
    for b in budgets:
        lines.append(f"| {b['name']} | {b['peak_tmac_s']} | {b['effective_gbps']} |")
    lines += ["", "下表取 W4、context=2048、batch=1。Decode 是给定流量模型的乐观上界；prefill 是仅计算下界，二者都不是延迟预测。", "",
              "| 模型 | 预算点 | Decode 上界 token/s | 1024-token prefill 计算下界 s |", "|---|---|---:|---:|"]
    for r in sweep:
        if r["weight_bits"] == 4 and r["context"] == 2048:
            lines.append(f"| {r['model']} | {r['budget']} | {r['optimistic_tps']:.2f} | {r['prefill_compute_floor_s']:.3f} |")
    lines += ["", "## 可审计公式与限制", "",
              "H=hidden，F=intermediate，L=layers，Q=heads×head_dim，K=kv_heads×head_dim，V=vocab。",
              "- Transformer 矩阵参数 B=L×(2HQ+2HK+3HF)；共享 embedding/head 为 VH。",
              "- Norm 参数=L×(2H+2head_dim)+H；包括 Q/K norm。",
              "- W4/W8 是本次假设的对称量化存储；所有矩阵包括 embedding/head 均量化，每 128 权重附一个 16-bit scale；norm 16-bit。并非上游原始 BF16 checkpoint 的实际文件大小，也未验证该量化质量。",
              "- KV=2×L×K×context×2 bytes，batch=1；cache 精度尚未冻结。",
              "- Decode MAC=B+VH+2LQT；建模流量=W+KV+一 token KV 写入+一行 embedding。假定权重每 token 从外存扫描一次，KV 在 GQA 查询头间充分复用。",
              "- Prefill useful MAC=B×S+LQ×S(S+1)+VH，S=1024，只计算最后一个 token 的 logits，因果三角有效计算。未优化方阵执行、全 prompt logits 会更贵。",
              "- Decode 上界=min(峰值 MAC/s ÷ MAC/token，有效外存 B/s ÷ 建模 B/token)。充分片上驻留、batch 复用会改变流量；重复读取、冲突和中间张量溢出会增加流量。",
              "- 未计入 dequant、激活量化、softmax/norm/RoPE/SwiGLU 时延、CPU 调度、AXI 竞争与在途事务、片上端口和 SRAM 能耗、memory refresh；prefill 未建立完整 IO 模型。",
              "- 原有 TinyStories profiler 将 head_dim 从 H/heads 推导，不能直接套用这些 Qwen3 配置。", ""]
    (HERE / "estimates.md").write_text("\n".join(lines))
    assert estimate(MODELS[1], 2048, 4)["kv_bytes"] == 224 * 2**20
    assert estimate(MODELS[2], 8192, 4)["kv_bytes"] == 1152 * 2**20
    print(f"Analytical budget: PASS; {len(rows)} workload/precision/context cases; {len(sweep)} budget comparisons; KV hand-checks passed. No inference/RTL/PPA executed.")


if __name__ == "__main__":
    main()
