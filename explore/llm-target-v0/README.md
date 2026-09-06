# OpenChip LLM 需求与架构取舍草案 Rev 0.1

日期：2026-09-05。角色：chief-architect。状态：LOCAL / CANDIDATE，未发布给 RTL/DV 实现。

## 1. 已确定与工作假设

用户已确定：芯片以 LLM 为主目标；先整芯片仿真运行真实程序，再推进 FPGA；系统互连优先 AXI，安全域考虑 Caliptra；agent 流程须涵盖 block 增改删替换与独立 RTL/DV，后续延伸至物理实现和 digital twin。全部设计草稿只保存在本地。

本次架构师建议、尚未由用户确认：第一版定位单用户本地推理，batch=1，稠密 decoder-only Transformer；以 Qwen3-1.7B 为预算主样本，0.6B 为缩小后的集成样本，4B 为扩展压力样本。训练、微调、MoE、多模态和服务器多请求调度暂列后续范围，不代表平台或 agents 不支持这些架构。

选择这些模型是为了获得明确、可复查的维度与相同家族的规模对照，不代表它们是当前最优模型，也不承诺任意 1–4B 模型均受支持。正式 workload freeze 要增加另一个模型家族的形状/算子交叉检查。

draw.io 可继续作为可编辑框图；Visio/PDF 保留用于已有评审。图纸格式不改变接口合同和规格的权威性。

## 2. 可测量的目标候选

| ID | 要求候选 | 验收口径与状态 |
|---|---|---|
| LLMP-01 | 产品应完成单请求文本生成，包含 prefill、逐 token decode 和 KV 更新 | 真正执行完整选定模型；不得用预存答案或主机代算 logits；checkpoint/tokenizer/runtime 待固定 |
| LLMP-02 | 主预算样本 Qwen3-1.7B，batch=1、活动 context 至多 2048 时，decode 应达到 ≥20 token/s | 每个 token 计算到结果可见，包含 DMA、后处理与调度；1024-token prompt 后生成 128 token 并加测接近 2048 的边界；目标候选，尚未实测 |
| LLMP-03 | 主样本 1024-token prompt 的 warm TTFT 应 ≤3 s | 从 token IDs 已就绪到首个输出 token 可见；模型已驻外存，无 prefix cache 复用；另外报告原始文本入口的 tokenizer 时间和冷启动时间 |
| LLMP-04 | 扩展探针应覆盖 8192 context 与 Qwen3-4B | 两项分别测量并组合做容量压力；尚未承诺维持主样本速度；超过配置容量应可诊断地拒绝 |
| LLMP-05 | 正确性应同时覆盖数值合同与模型质量 | RTL 对已冻结定点/浮点参考的逐算子合同；量化参考对 BF16 原模型的质量比较分开报告；数据集与容差待定 |
| LLMP-06 | 整芯片仿真应从复位启动并运行完整小模型的多步生成 | 建议 stories260K：32 输入 token、16 个后续生成步骤；固件/权重/输入非零，结果与独立参考一致；checkpoint、量化和确定性 token 策略待固定 |
| LLMP-07 | 安全配置应在授权和访问保护建立后释放应用执行 | 未签名/篡改镜像、越权 DMA、失败恢复分别验收；非安全 bring-up 成功不记为 secure boot 成功 |
| LLMP-08 | 性能报告应列出各算子的 CPU/NPU 分工和回退占比 | 主性能路径目标为 NPU 承担 Transformer 数值计算；CPU 负责控制、tokenizer 与生成策略；任何算术回退计入延迟并显式报告 |

这些行是产品需求候选，不是冻结的 block shall。数值格式、模型版本、质量阈值与平台预算未定之前，不允许标为 frozen。

功能验收规模与产品容量目标分开：stories260K 用来证明全部真实数据路径；不能据其通过声称 Qwen3 功能或性能通过。较大模型在软件参考/系统模型阶段验证，再按可用资源推进 FPGA/加速仿真。0.6B 也可能使逐周期 RTL 回归过慢，需记录运行成本后决定回归层级。

## 3. 数据与预算结论

复现与完整假设见 [12 组工作负载估算及 36 组预算比较](estimates.md) 和 [机器可读结果](estimates.json)。本次只读取公开配置，无 checkpoint 下载、量化或推理执行。

- 在提出的 W4 存储、16-bit KV、2K context 下，1.7B 权重约 0.887 GB、KV 为 224 MiB；20 token/s 对应约 22.45 GB/s 建模流量。4B 对应约 47.53 GB/s。该流量不含完整中间张量/协议开销。
- 1.7B 的 1024-token prefill 约 1.504 TMAC；若要 3 s，光有效矩阵计算就需要约 0.501 TMAC/s，此外还有非线性和数据移动。这使 prefill 成为必须单列的约束。
- 预算点 B（1 TMAC/s 峰值、32 GB/s 有效外存）在理想假设下有研究价值；它不是已选设计。A 的主样本 decode 乐观上界已低于 20 token/s；不能靠软件优化承诺达标。C 用来研究 4B 扩展成本。
- 权重和 KV 显著超出小型片上 SRAM 范围，外存能力、数据复用和 KV 布局必须先于阵列规模决策。片上 SRAM 应按 tile、bank 带宽和 live tensor 生命周期选择，不能只按总容量选。
- Qwen3 配置显式给定 head_dim；0.6B/4B 的 heads×head_dim 不等于 hidden_size。旧 TinyStories profiler 的维度推导不适用，本次单独计算，原文件保持原有范围。

上述都是在固定流量假设下的解析推导。模型权重驻留、分组量化、GQA 复用和张量溢出都会改变结果；尚无校准过的吞吐、时序、面积或功耗证据。

## 4. 对架构的直接要求

| 子系统 | 接下来必须明确的合同/取舍 |
|---|---|
| 矩阵与向量计算 | 同时支持 prefill GEMM 与 batch=1 GEMV；embedding/logits、GQA、Q/K norm、RMSNorm、RoPE、Softmax、SiLU/SwiGLU、残差与数据布局必须有执行归属 |
| 数值格式 | 比较 W4A16、W8A8 与必要混合精度；本次 W4/W8 只证明容量口径，未证明精度或硬件成本。激活、累加、scale、KV 和非线性格式分别定义，不沿用旧 INT8 标签代替决定 |
| 存储与 DMA | 局部 SRAM bank/端口、双缓冲、KV append/read、tile 生命周期、溢出搬运、地址宽度和 DMA 可达范围；外存控制器/PHY 是待 intake 的具体平台依赖 |
| AXI 互连 | 有效带宽、位宽、时钟、burst、ID/USER、在途数、仲裁/QoS、错误与隔离；AXI 名称本身不保证带宽 |
| 控制与软件 | 命令描述符、算子依赖、completion 可见性、cache/屏障、超时/取消/复位恢复；执行格式应表达算子形状，避免硬编码某个模型 |
| 启动与安全 | 固定 Caliptra release 与集成范围；定义模型/固件可信边界、镜像验证至执行之间的保护及 CPU/DMA 权限；LLM 权重是否受认证是待裁决项 |
| 物理与测试 | 工艺/封装、面积与功耗预算、SRAM 宏、DRAM/PHY/IO、时钟复位、电源状态、DFT/MBIST/调试；目前没有足够数据冻结频率或 die size |

预期外部数据通路：外存控制器 ↔ AXI ↔ NPU DMA ↔ banked SRAM ↔ 矩阵/向量单元；CPU 经控制接口提交任务，结果写回完成后接收中断。KV 存在外存、活动 tile 缓存在片上是初始候选，具体映射由 trace 与容量预算裁决。

## 5. 工作分解与阶段退出条件

| 顺序 | 交付责任 | 交付物与退出条件 |
|---|---|---|
| 1 | chief architect | 固定产品场景、模型/提示集、TTFT/TPOT/质量/容量口径；补充芯片功耗面积和 FPGA 平台约束 |
| 2 | chief architect；软件角色后续独立执行探针 | 固定 checkpoint/tokenizer/runtime/hash，完成浮点与量化质量基线；算子 shape、数据量、fallback 清单；不复制 RTL 行为当参考 |
| 3 | chief architect；模型/后端角色分别提供证据 | 用真实 shape/trace 比较阵列、SRAM 和总线；校准成本，淘汰不满足预算的候选；形成 ADR |
| 4 | chief architect | 发布顶层与 block spec/ICD/寄存器/地址/中断/启动/数值合同；冻结范围内无待定行为 |
| 5 | verification architect，独立于 RTL | 完整 vplan、golden 与 requirement→test/property/coverage 映射；本文件的验收意图不冒充已完成的 test plan |
| 6 | 各 block RTL、DV、formal、软件与 integrator | 先跑通 LLMP-06，再增加 Qwen3 特有算子与完整模型；所有实现 gate 保留，阶段证据范围明确 |
| 7 | integrator 与受影响角色 | 用 add/modify/delete/replace 实验验证变更影响、规格更新、回归选择和可追溯性；模型替身与硬件替换分别验收 |
| 8 | backend/平台角色 | FPGA 与物理实现，CDC/RDC、DFT、时序和最终签核依阶段执行；仿真成功不记为流片完成 |

本轮没有启动新的实现 agents；这些是后续职责与交付边界。

## 6. 冻结前未决项

1. 产品定位仍待用户选择：当前按本地推理候选研究，训练/服务器方向会要求重新预算。
2. 功耗、工艺、die/封装成本、外存技术与 FPGA 板卡尚未限定；预算点无法据此证明可实现性。
3. 模型/checkpoint/tokenizer/提示集与量化方法、质量容差、确定性验证策略未固定。greedy 可用于受控正确性探针，不能替代模型推荐采样下的质量评测。
4. 来源配置是 2026-09-05 人工摘录的字段快照；正式基线须记录不可变 revision、文件 hash 和导出参数，当前不是可复现 checkpoint 发布包。
5. 新 AXI 方向与既有 AGENTS.md、ADR-0001、SoC-1/NPU 的 Wishbone 基线冲突：先发布有影响清单的迁移决策，再由对应角色更新规则与规格，旧 gate 不降低。
6. Caliptra/内存/IP 工具兼容性与集成成本，以及 full-model RTL 仿真墙钟成本，均需实际探针。

## 来源

- [Qwen3-0.6B 官方配置](https://huggingface.co/Qwen/Qwen3-0.6B/raw/main/config.json)：1024 hidden，3072 intermediate，28 layers，16 query heads。
- [Qwen3-1.7B 官方配置](https://huggingface.co/Qwen/Qwen3-1.7B/raw/main/config.json)：2048 hidden，6144 intermediate，28 layers，16 query heads。
- [Qwen3-4B 官方配置](https://huggingface.co/Qwen/Qwen3-4B/raw/main/config.json)：2560 hidden，9728 intermediate，36 layers，32 query heads。
- 上述三个配置共同用于本次计算的字段：head_dim=128、kv_heads=8、vocab=151936、共享 embedding/head。权重与 KV 字节数是本地提出的精度假设下的推导，非上游性能声明。
- [Transformers v4.51.3 Qwen3 实现](https://github.com/huggingface/transformers/blob/v4.51.3/src/transformers/models/qwen3/modeling_qwen3.py)：用于核实 projection shape 和 Q/K norm 参数；没有复制为本项目 golden model。
- [Qwen3-1.7B 官方模型卡](https://huggingface.co/Qwen/Qwen3-1.7B)：采样建议与 thinking/non-thinking 区别。质量评估配置须另行固定。
- 既有本地 `workloads/tinystories/profile.py` 与 `profile.md`：小模型 bring-up 候选及旧假设范围，本轮未重新获取其 checkpoint。

## 本轮验证

解析探针：12 组模型/精度/context、36 组预算比较，KV 手算交叉检查通过。仅为架构算术；没有推理、量化质量、RTL/DV、formal、综合、FPGA 或物理 gate 结果。未对本次文档变更运行不相关的 make gate。

全部位于主仓库本地忽略目录；没有 push 或远端 PR。

Friction:
- 旧 workload 的 head_dim 推导与新候选模型不兼容；采用独立解析探针，未修改旧基线。

Skill candidates:
- chief-architect/references/spec-authoring-patterns.md — LLM 需求分开定义 prefill/decode、权重与 KV 精度、功能与性能验收规模。
