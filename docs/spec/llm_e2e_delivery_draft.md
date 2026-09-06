# LLM SoC 首批端到端交付合同草稿

Status: draft · Owner: chief-architect · Date: 2026-09-05
本文件仅整理交付顺序与验收义务；未冻结接口、未授权按 TBD 实现、未宣称芯片运行成功。
范围：LLM 应用 → 整芯片 RTL 仿真执行真实程序 → FPGA；全部本地交付，不 push、不建远端 PR。

## §1 目标与证据基线

- 目标是通过 agents 框架交付可运行芯片；技能从真实研发阻塞和修复中积累，不安排人为注错、增删 block 或独立考试。
- 方向保留 LLM、AXI 主干与 Caliptra 安全域研究；第一批贯穿启动、软件、存储、计算与输出，不派孤立 FIFO 任务充当系统进展。
- 既有 `soc_1.md`/`npu.md` 是 Wishbone 草稿；ADR-0001/0002/0003 记录旧总线、1×8 INT8 GEMV 与 PicoRV32 决策，不能把旧实现自动算作新 AXI 平台。
- `workloads/tinystories/profile.md` 记录旧 checkpoint 头部读取及解析工作量；不是本轮重新下载、完整权重校验或推理结果。
- `explore/llm-target-v0/` 记录配置快照、12 组容量估算及 36 组预算比较；没有 checkpoint 推理、量化质量或校准性能证据。
- stories260K 小模型、Qwen3 0.6B/1.7B/4B 和相应性能数值仍是候选；本文件不把建议变成已选模型或产品承诺。
- Rev 0.2 图纸与接口登记册是候选连接关系，AXI 宽度、事务语义、地址及安全接口尚非可实施 ICD。

## §2 最短主路径与分层退出条件

最短主路径：实际软件参考探针 + IP 可运行性探针 → 发布首批范围合同 → 软件/顶层 RTL/独立系统 DV → B1 → L1 → FPGA。
Caliptra 探针与主路径并行；安全配置的 S1 在 FPGA 安全集成验收前单独通过，不能由非安全 B1/L1 代替。

| 关卡 | 系统应完成的真实路径 | 通过证据与限制 |
|---|---|---|
| B1：整芯片 bring-up | reset → CPU 从 ROM 取指 → 装载并执行固件 → 经 AXI 装载非零输入/权重 → CPU 提交 NPU 命令 → NPU 计算 → DMA 写回 → completion/IRQ → CPU 读回核对 | 同一运行保存固件/输入 hash、启动与事务证据、CPU 比较结果及周期数；至少两组不同输入均符合独立预期；不是完整 LLM |
| L1：完整小模型 | B1 之上执行完整 prefill、全部层、logits、token 选择、KV 更新与后续 decode | 候选规模为 32 输入 token + 16 生成步，待 checkpoint probe 后固定；逐步比较 KV/数值检查点与 token 序列；不能据此宣称 Qwen3 或产品吞吐达标 |
| S1：安全启动集成 | 实际 Caliptra RTL/所需固件服务 → 镜像授权 → 访问保护生效 → 应用释放；拒绝与恢复分支可观察 | 有效镜像成功，篡改/未授权镜像不能执行，未授权 DMA 被拒绝；仅数字功能证据，不证明物理安全 |
| F1：FPGA | 用相同软件合同和选定模型重跑 B1/L1，安全配置重跑 S1 | 记录板卡、存储适配、资源、时钟、实际延迟与差异；FPGA 不等于 ASIC 签核 |

B1 不要求先实现所有 Transformer 算子，但必须经过计划采用的 AXI、DMA、NPU 和 CPU 软件接口。
L1 应固定每个算子的 CPU/NPU 归属；矩阵计算实际走 NPU，其他算子的 CPU 回退必须由片上 CPU 执行并计入时间。
L1 退出时不得存在未声明的回退；全 NPU 数值路径及大模型吞吐另设产品验收，不能从功能结果推定。
确定性策略应固定 tokenizer、prompt/token IDs、采样配置、种子及平局规则；仅 token 相同不足以替代中间数值验证。

## §3 首批合同必须覆盖的闭环

| 合同 ID | 下发前必须给出的可测试行为 |
|---|---|
| E2E-01 启动 | reset 极性/同步/释放顺序、CPU 型号/ISA/reset vector、ROM 内容与装载源、固件地址/容量/入口、失败状态；禁止用 testbench 直接跳 PC 代替启动 |
| E2E-02 内存 | 地址图、字节序/对齐/权限、ROM/SRAM/外存容量、模型与 KV/scratch 布局、CPU/DMA 可达范围、初始化方法及越界响应 |
| E2E-03 AXI | 各 initiator/target 与 bridge、版本和 address/data/ID/USER 位宽、burst/在途数/排序、背压、错误、超时及 reset 中事务处置 |
| E2E-04 命令 | CSR offset/reset/access、描述符格式与长度边界、输入/输出地址及 layout、提交/忙/拒绝/取消、错误恢复与重用规则 |
| E2E-05 数值 | 权重/activation/scale/累加/KV 格式、量化粒度、舍入/饱和/溢出、非线性近似及容差；算子输入输出足以独立建模 |
| E2E-06 完成 | 写回的可见性点、AXI 写响应与状态/IRQ 的先后、CPU cache/屏障合同、清状态和下一命令；CPU 不得在完成前核对旧数据 |
| E2E-07 可观察性 | 固件 PASS/FAIL/错误码出口、超时界限与进度、CPU 核对的数据/独立预期来源、可复现实验清单；不能只检查“有 UART 输出” |

上述字段先对 B1 子集闭合，再按真实模型增加 L1 合同；未确定内容由架构任务裁决，不交给 RTL/DV 各自猜测。
首批数值合同必须真实装载并读回 activation，不能仅有 ACT_BASE 寄存器而无可达数据路径。

## §4 可执行的首批任务与依赖

| 工作项 / owner | 可立即开展的交付 | 前置合同 / 退出条件 |
|---|---|---|
| A1 / chief-architect | 整理 AXI 迁移 change order、B1 地址/启动/命令/数值 ICD 和受影响清单 | 使用 W1/I1 证据裁决 E2E-01…07；B1 发布范围内零 TBD，L1 未决项单列 |
| W1 / sw-engineer | 获取合法 checkpoint/tokenizer/runtime 并固定 revision/hash；运行浮点与量化参考、导出模型/形状/内存峰值/检查点 | 先做主机软件探针，不依赖 RTL；质量阈值、数据集与数值差异提交 A1 裁决；主机结果只作为独立参考 |
| I1 / 各候选 IP 的 rtl-engineer；架构裁决 | 在各自 worktree 对 CPU、AXI fabric/bridge、Caliptra、内存控制器候选固定版本并做最小编译/仿真 intake | 先给定探针边界；交付 license/配置/工具命令/真实日志/资源与接口缺口，不声称已完成 SoC 集成 |
| W2 / sw-engineer | ROM/loader、linker map、驱动与 B1 应用，再接 L1 runtime | A1 发布；真实编译产物/大小/栈与堆预算，CPU 读回比较及失败处理齐备 |
| R1 / rtl-engineer | 有明确作者的顶层模块连接 CPU/ROM/SRAM/AXI/NPU DMA/计算/写回/IRQ/reset；依赖模块分别分支交付 | A1 发布、I1 可用；按合同做连接与实现，禁止修改系统 DV；先满足完整 B1，再接 L1 算子 |
| V1 / verif-architect → 独立 dv-engineer | 从规格建立系统 vplan/数值 golden/真实固件测试及存储外设模型，完成 B1/L1 与异常覆盖 | A1/W1 是独立预期依据；不读 RTL 生成答案，不修改 R1；合同歧义退架构、实现缺陷退对应 RTL owner |
| G1 / orchestrator；integrator 审阅 | 接通本地固件构建和 SoC 仿真入口、保存工具与产物身份、汇总依赖及 gate 状态 | 流程缺口由 flow owner 处理；本草稿不修改 Makefile，不以占位命令为通过 |

现在可并行推进 W1、I1 和 A1 的未决项整理；W2/R1/V1 的实现发布取决于 A1，不能靠增添孤立模块绕过合同缺失。
各角色保持自己的交付目录与独立 worktree；本地审阅记录承担交付 manifest，不创建远程 PR；已批准旧 gate 保留。

## §5 Wishbone → AXI 的显式迁移依赖

迁移记录应逐项标明保留、桥接、改写或废弃：ADR-0001、ADR-0002/0003、SoC/NPU spec、项目总线规则、软件 ABI、DV/模型和构建入口。
chief-architect 负责 ADR/spec；integrator 审阅规则迁移；orchestrator 处理平台/flow；各实现 owner 按已发布版本迁移自己的工件。
保留旧 CPU 或 NPU 算术核心可以评估，但适配成本、ISA/IRQ 差异、DMA 与写回接口必须有证据；不得默认为旧 Wishbone 规格自动兼容 AXI。
首批容量、阵列与时钟依据真实 B1/L1 需求选择；旧 2 KB SRAM、32-bit PSRAM、50 MHz、INT8 和吞吐估值不得直接继承为新产品保证。

## §6 尚不可冻结项与真实探针

| 依赖 | 已有证据 | 还需执行 / 冻结前阻塞 |
|---|---|---|
| checkpoint 与运行时 | 小模型旧头部记录；Qwen3 配置快照 | 完整文件/hash/license、tokenizer 相容性、真实多步推理、非零输入与确定性输出；stories260K 尚未选定 |
| quantization/numeric | 旧 NPU 定义了 INT8/INT32 与 requant；新预算仅假定 W4/W8 存储 | 实际导出与质量评估，逐算子格式/误差及 scale 传输合同；旧“每输出通道 scale”与单描述符 `(M,s)` 如何一致须裁决，不能直接复用 |
| CPU/AXI/Caliptra 外部 IP | 旧 CPU ADR；新接口候选图 | release/commit、配置、依赖和工具兼容日志；CPU 启动/IRQ/ISA 验证、bridge 协议、Caliptra 主机模式/ROM/固件与所需资源尚待 probe |
| 存储与成本 | 解析权重/KV 数量级 | 真实 runtime/activation/scratch 峰值、DMA trace、外存控制器/模型的可用性、延迟/带宽/仲裁；先测 RTL 回归墙钟再定日常回归规模 |
| 产品与 FPGA | 小模型功能路径和大模型预算候选 | 产品质量/TTFT/TPOT、资源/功耗、板卡及存储配置另行裁决；B1 不等待 ASIC 全部参数，但不得代表这些指标通过 |

Caliptra 的 core/subsystem 及 release 尚未选定；SOC-02 必须拆清安全域 initiator 与 mailbox target，不能凭一条 trusted USER 图线推断安全接通。
I1 必须回答谁负责验证镜像、谁释放应用 CPU、谁执行访问隔离、失败如何锁住/恢复，以及 ROM/OTP/熵源/固件/调试模式的外部依赖。
非安全 B1 可明确使用开发启动配置；固定“授权成功”的替身不得作为 S1，也不得悄悄替代最终 Caliptra 集成。
外存模型可预装 ROM、固件、权重与输入字节，并模拟读写、延迟、背压和错误；NPU 算术与 CPU 程序必须由 DUT 执行。
AXI target 存储替身可支持功能仿真，但若替掉控制器，必须标出该边界未验证；FPGA 仍须真实控制器/存储链路验收。
testbench/主机不得计算 DUT logits/KV/token、补写结果、注入 NPU 内部 activation 或伪造完成；参考计算仅用于比较。

## §7 本次交付与后续验收记录

本轮只新增本草稿，保留现有文档；仅检查本地文档与根 Makefile，没有读取 RTL/DV 源码或运行硬件。
根 Makefile 当前 `soc-sim` 与 `compliance` recipe 为提示后 `exit 1`；这是只读检查结果，不是本轮执行 gate 的输出。
后续 manifest 应包含规格/代码/IP/固件/模型 hash、命令/seed、实际工具摘要、周期与墙钟、覆盖分母和失败/跳过项；占位或空跑不可标为通过。
本轮 gate 状态：文档范围检查适用；lint/sim/coverage/formal/compliance/synth/FPGA/物理 gate 均未运行，不产生芯片完成声明。

Friction:
- 新 AXI 合同未发布、软件数值基线未执行、系统仿真入口仍占位，当前阻塞真实端到端交付。

Skill candidates:
- chief-architect/references/spec-authoring-patterns.md — 首批任务以真实启动到 CPU 核对的闭环为交付单位，技能只从实际交付问题提炼。
