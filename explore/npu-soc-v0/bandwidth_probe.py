"""Analytical capacity comparison, not calibrated performance or PPA.

Reuse the repository's TinyStories arithmetic; do not download checkpoints.
All clock / bandwidth / MAC values are exploration inputs, not chip targets.
"""
from pathlib import Path
import importlib.util
import json
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('openchip_profile',ROOT/'workloads/tinystories/profile.py')
wl=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=wl
spec.loader.exec_module(wl)
cfg=wl.MODELS_BY_NAME['stories15M']
decode=wl.summarise(cfg,128)
prefill=wl.prefill_summary(cfg,128)
rows=[]
for macs in [8,64,256,1024]:
    for mhz in [100,200]:
        for gbps in [1,4,8]:
            peak=macs*mhz*1e6
            dm=gbps*1e9*decode['arith_intensity']
            pm=gbps*1e9*prefill['arith_intensity']
            rows.append(dict(macs_per_cycle=macs,clock_mhz=mhz,effective_external_gbps=gbps,
                             peak_gmac_s=peak/1e9,decode_optimistic_gmac_s=min(peak,dm)/1e9,
                             prefill_optimistic_gmac_s=min(peak,pm)/1e9))
data=dict(status='analytical-only, all utilization assumed ideal',context=128,
          model=cfg.name,decode_macs=decode['gemm_macs'],decode_bytes=decode['total_bytes'],
          decode_mac_per_byte=decode['arith_intensity'],prefill_macs=prefill['macs'],
          prefill_weight_bytes=prefill['weight_bytes'],prefill_mac_per_byte=prefill['arith_intensity'],rows=rows)
(HERE/'bandwidth-estimates.json').write_text(json.dumps(data,indent=2)+'\n')
lines=['# 带宽与 MAC 容量探针（解析估算）','',
       '状态：未校准；不是 RTL/FPGA 性能结果，不是新的芯片规格。',
       '来源：当前仓库 workloads/tinystories/profile.py；stories15M，context=128，INT8 权重/KV 假设。','',
       f"- Decode：{decode['gemm_macs']:,} MAC，{decode['total_bytes']:,} 建模字节，{decode['arith_intensity']:.4f} MAC/B。",
       f"- Prefill：{prefill['macs']:,} MAC，{prefill['weight_bytes']:,} 权重字节，{prefill['arith_intensity']:.4f} MAC/B。",'',
       'Prefill 分母只包含该模型统计的权重流量，未完整计入 KV、中间张量及溢出搬运，属于乐观口径。',
       '公式：peak = MAC/cycle × clock；optimistic capacity = min(peak, effective external bandwidth × arithmetic intensity)。',
       '假定 MAC 利用率为 100%；没有模拟 GEMV 阵列映射、片上 SRAM 端口、算子开销、总线竞争、burst 效率、面积、功耗或时序。',
       'GB/s 为十进制有效带宽输入，已经是条件假设；100/200 MHz 和表中配置均未获时序验证。','',
       '| MAC/cycle | MHz | GB/s | 峰值 GMAC/s | Decode 容量上界 GMAC/s | Prefill 容量上界 GMAC/s |',
       '|---:|---:|---:|---:|---:|---:|']
for r in rows:
    lines.append(f"| {r['macs_per_cycle']} | {r['clock_mhz']} | {r['effective_external_gbps']} | {r['peak_gmac_s']:.2f} | {r['decode_optimistic_gmac_s']:.2f} | {r['prefill_optimistic_gmac_s']:.2f} |")
lines += ['', '决策含义：先确定 decode/prefill/其他网络的目标比例，再选择数据流和阵列规模；必须独立评估向量与非线性算子。此探针仅支持功能组织候选，不支持冻结某个阵列或承诺应用吞吐。','']
(HERE/'bandwidth-estimates.md').write_text('\n'.join(lines))
print(f"Analytical probe: PASS; {len(rows)} configurations; decode={decode['arith_intensity']:.4f} MAC/B; prefill={prefill['arith_intensity']:.4f} MAC/B (weight-only denominator).")
