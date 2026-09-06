# LLM 容量与吞吐预算探针

状态：解析估算；未校准；不是实测性能或 PPA。

配置来源见 [需求草案](README.md#来源)。GB=10⁹ B，GiB=2³⁰ B；1 MAC 不写成 1 OPS。

| 模型 | Context | 权重位数 | 权重含 scales GB | KV GiB | 权重+KV GiB | 20 token/s 所需建模带宽 GB/s |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3-0.6B | 2048 | 4 | 0.307 | 0.219 | 0.505 | 10.85 |
| Qwen3-0.6B | 2048 | 8 | 0.605 | 0.219 | 0.783 | 16.81 |
| Qwen3-0.6B | 8192 | 4 | 0.307 | 0.875 | 1.161 | 24.94 |
| Qwen3-0.6B | 8192 | 8 | 0.605 | 0.875 | 1.439 | 30.90 |
| Qwen3-1.7B | 2048 | 4 | 0.887 | 0.219 | 1.045 | 22.45 |
| Qwen3-1.7B | 2048 | 8 | 1.748 | 0.219 | 1.846 | 39.65 |
| Qwen3-1.7B | 8192 | 4 | 0.887 | 0.875 | 1.701 | 36.54 |
| Qwen3-1.7B | 8192 | 8 | 1.748 | 0.875 | 2.503 | 53.74 |
| Qwen3-4B | 2048 | 4 | 2.074 | 0.281 | 2.213 | 47.53 |
| Qwen3-4B | 2048 | 8 | 4.086 | 0.281 | 4.086 | 87.75 |
| Qwen3-4B | 8192 | 4 | 2.074 | 1.125 | 3.057 | 65.65 |
| Qwen3-4B | 8192 | 8 | 4.086 | 1.125 | 4.930 | 105.87 |

容量列不含运行时、激活、scratch、固件、分配碎片、ECC 或模型装载副本，不能据此直接选 DRAM 容量。

## 预算点比较

预算点均为假设，不代表已选 MAC 阵列、频率、存储器或可实现的功耗面积。

| 预算点 | 峰值 TMAC/s | 外存有效 GB/s |
|---|---:|---:|
| A | 0.25 | 16 |
| B | 1 | 32 |
| C | 4 | 64 |

下表取 W4、context=2048、batch=1。Decode 是给定流量模型的乐观上界；prefill 是仅计算下界，二者都不是延迟预测。

| 模型 | 预算点 | Decode 上界 token/s | 1024-token prefill 计算下界 s |
|---|---|---:|---:|
| Qwen3-0.6B | A | 29.50 | 2.045 |
| Qwen3-0.6B | B | 58.99 | 0.511 |
| Qwen3-0.6B | C | 117.99 | 0.128 |
| Qwen3-1.7B | A | 14.26 | 6.014 |
| Qwen3-1.7B | B | 28.51 | 1.504 |
| Qwen3-1.7B | C | 57.02 | 0.376 |
| Qwen3-4B | A | 6.73 | 15.503 |
| Qwen3-4B | B | 13.47 | 3.876 |
| Qwen3-4B | C | 26.93 | 0.969 |

## 可审计公式与限制

H=hidden，F=intermediate，L=layers，Q=heads×head_dim，K=kv_heads×head_dim，V=vocab。
- Transformer 矩阵参数 B=L×(2HQ+2HK+3HF)；共享 embedding/head 为 VH。
- Norm 参数=L×(2H+2head_dim)+H；包括 Q/K norm。
- W4/W8 是本次假设的对称量化存储；所有矩阵包括 embedding/head 均量化，每 128 权重附一个 16-bit scale；norm 16-bit。并非上游原始 BF16 checkpoint 的实际文件大小，也未验证该量化质量。
- KV=2×L×K×context×2 bytes，batch=1；cache 精度尚未冻结。
- Decode MAC=B+VH+2LQT；建模流量=W+KV+一 token KV 写入+一行 embedding。假定权重每 token 从外存扫描一次，KV 在 GQA 查询头间充分复用。
- Prefill useful MAC=B×S+LQ×S(S+1)+VH，S=1024，只计算最后一个 token 的 logits，因果三角有效计算。未优化方阵执行、全 prompt logits 会更贵。
- Decode 上界=min(峰值 MAC/s ÷ MAC/token，有效外存 B/s ÷ 建模 B/token)。充分片上驻留、batch 复用会改变流量；重复读取、冲突和中间张量溢出会增加流量。
- 未计入 dequant、激活量化、softmax/norm/RoPE/SwiGLU 时延、CPU 调度、AXI 竞争与在途事务、片上端口和 SRAM 能耗、memory refresh；prefill 未建立完整 IO 模型。
- 原有 TinyStories profiler 将 head_dim 从 H/heads 推导，不能直接套用这些 Qwen3 配置。
