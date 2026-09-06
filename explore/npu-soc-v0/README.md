# OpenChip NPU SoC v0.1：候选架构与连接视图

状态：本地讨论稿；不替代既有 SoC-1/ADR，不是可直接下发 RTL 的冻结规格。
日期：2026-09-05。角色：chief-architect。用户要求：仅本地保存，不推送、不创建远端 PR。

## 1. 架构师的具体选择

建议采用：**RISC-V 控制 CPU + AXI 系统互连 + 独立 DMA 的 NPU 子系统 + 分层存储 + 独立安全/启动域**。

CPU 下发有地址、形状、步长和依赖信息的任务，NPU 自主搬运和计算。NPU 内含矩阵 MAC、向量/归约/非线性运算、局部 SRAM 和结果写回。完整应用不能只依靠 MAC 阵列：量化、激活、归约与数据布局也必须纳入软硬件合同。

主干采用 AXI4 候选；控制寄存器用 AXI4-Lite，低速外设用 APB。芯片不要求每条局部 SRAM 连线都改成 AXI。局部流接口若选择 AXI4-Stream，必须明确并验证该协议的完整约定；ready/valid 信号本身不代表合规。

第一版控制核按 RV32 候选研究，不预设 Linux/多核/缓存一致性需求。CPU 接口可从 AXI4-Lite 通过明确适配接入 AXI4 主干。若未来引入数据缓存，CPU/DMA 共享数据的维护、屏障与所有权规则必须加入合同；v0 不假定硬件缓存一致性。

## 2. 图纸包

**图纸评审入口：[Visio / PDF 架构评审包 Rev 0.2](review-v0.2/README.md)。** draw.io 同样可用于后续编辑与评审；传统交付要求落实在规格、接口和版本管理。最新产品方向见 [LLM 需求与架构取舍草案](../llm-target-v0/README.md)，尚未冻结。

| 图 | 表达内容 | 本地文件 |
|---|---|---|
| 顶层 SoC block diagram | 计算、控制、安全、存储和外部接口连接 | [SVG](01-soc.svg) / [PNG](01-soc.png) |
| NPU microarchitecture block diagram | 命令、DMA、局部 SRAM、MAC、向量和写回 | [SVG](02-npu.svg) / [PNG](02-npu.png) |
| Reset / secure-boot flow | 管理 ROM、固件授权、CPU 释放、拒绝/恢复 | [SVG](03-boot.svg) / [PNG](03-boot.png) |
| Clock / reset connectivity | 共用功能时钟、独立复位输出和内存平台边界 | [SVG](04-domains.svg) / [PNG](04-domains.png) |

[可编辑的四页 draw.io 源文件](openchip-npu-v0.drawio)。图中方框是功能边界，位置不代表版图面积或物理摆放。双箭头表示双向接口流量，不是 AXI 通道逐根画线。时钟图共线路径表示同一时钟源；复位输出按各目标分别控制。

用矩形功能块、层次边界和带协议/方向标注的连接表达 SoC，是本次采用的架构图方式。逻辑框图、RTL schematic、物理 floorplan 和时序图分别回答不同问题，不能互相代替。draw.io 是编辑文件格式，不是芯片行业统一强制标准。

后续若要让工具交换 IP、接口和集成元数据，可评估 **IP-XACT / IEEE 1685**；它采用 XML 描述，不是规定方框外观的画图格式。当前 `diagram-data.json` 只是本地图形数据，**不宣称 IP-XACT 合规，也不能用于直接生成芯片**。

## 3. 关键接口清单

| 来源 → 目标 | 接口候选 | 目的与需要冻结的合同 |
|---|---|---|
| CPU → AXI 主干 | 32-bit AXI4-Lite + AXI4 adapter | 指令/数据和寄存器访问；地址、响应、权限、异常 |
| 主干 → NPU command processor | AXI4-to-Lite | doorbell、队列位置、状态和错误；不靠 CPU 逐字搬权重 |
| NPU DMA ↔ 主干 ↔ SRAM/外存 | AXI4 burst | 描述符、权重、激活、KV、输出；宽度、burst、ID、在途数量、顺序和边界 |
| NPU DMA ↔ 局部 SRAM | 本地仲裁/存储接口 | 数据布局、bank 冲突、双缓冲 ownership |
| 局部 SRAM ↔ MAC/vector | 多 bank 读写/本地数据流 | 数据供给、partial sums、算子依赖、数值精度 |
| 安全域 ↔ AXI 主干 | 按 Caliptra release 固定的 AXI/USER | 可信请求者身份、mailbox/内存访问；adapter 不可丢失授权语义 |
| 安全域 → boot/reset 控制 | 授权与错误 sideband | 谁能释放应用 CPU，失败是否保持隔离；不是靠 AXI 自动实现 |
| 主干 → APB 外设 | AXI-to-APB | UART、GPIO、timer、watchdog；响应、超时和中断 |
| NPU/外设 → IRQ 聚合 → CPU | 事件信号和寄存器 | pending/mask/ack、并发与清除竞争 |
| 时钟/复位控制 → 各域 | soc_clk 与分别控制的 reset | 第一候选共用功能时钟；DDR PHY 所需时钟/CDC 由平台适配拥有 |

图中安全请求者身份由可信硬件端口/适配器赋予，不能允许普通软件伪造 USER 身份。禁止访问的响应、调试入口、DMA 地址范围与复位后默认权限必须独立验证。

## 4. 一次真实 NPU 任务怎样走

1. 管理 ROM/启动流程初始化必要平台资源，装载应用；安全配置下，在释放应用 CPU 前完成授权并保护已验证字节。
2. CPU 固件在系统可访问的内存放入非零输入、权重与描述符；明确发布顺序和内存所有权。
3. CPU 写 NPU doorbell；command processor 检查描述符，并安排 DMA 与计算依赖。
4. DMA 经 AXI 从系统 SRAM 或外存读取数据，分块装入局部 SRAM；存储与计算按合同重叠。
5. MAC 执行矩阵/向量乘加，vector/SFU 完成必要后处理，结果经写回 DMA 存入指定内存。
6. 写回完成可见后发出完成事件；CPU 读取真实结果并经 UART 报告。错误路径返回可诊断状态，不能虚报完成。

这条路径显式补足旧 NPU 缺失的非零 activation 装载与完整结果读回，但具体寄存器和时序仍需新规格。

## 5. 为什么这样组织，而不先定一个大阵列

本次重算既有 TinyStories 分析代码，得到 context=128 时：decode 约 **0.9993 MAC/B**；prefill 约 **52.7885 MAC/B**。后者只以模型统计的权重字节为分母，不完整计入中间张量、KV 和溢出搬运，不能直接当作整机带宽效率。

[24 组带宽/MAC 容量探索](bandwidth-estimates.md)保留 8/64/256/1024 MAC/cycle、100/200 MHz、1/4/8 GB/s 的条件假设。它说明需要同时考虑大矩阵数据复用和 decode 数据供给，但没有测出某个阵列/工艺的 PPA。均假设理想 MAC 利用率；GEMV 在二维阵列上的实际映射仍是关键未知。

**建议保留可分块的矩阵计算与 GEMV 映射研究空间，配独立向量通路和可配置局部 SRAM。** INT8 输入与 INT32 累加是初始数值候选；算子集合、非线性精度、舍入/饱和与最大归约长度尚未冻结。不能将 `INT32` 标签视为所有配置下不会溢出的证明。

在新工作负载明确前，不承诺 TOPS、网络吞吐或晶粒面积。旧的 sky130 2×2 mm、50 MHz、2 KB NPU SRAM 和 1×8 GEMV 决策不自动适用于这套更完整的系统。

## 6. 安全域、平台与后续替换

图中选择 **Caliptra subsystem 作为完整安全域候选**，保留其管理 MCU 与应用 CPU 的分工；这比只接 Core 的范围更大。release、ROM/固件、内部存储、OTP/entropy、I3C 与工具兼容性需要独立 intake 后才能冻结。

启动图是我们拟要求的系统安全行为，不是 Caliptra 上游的逐信号启动流程。第一阶段的非安全功能启动与之后的安全配置分别验收。安全配置不得把拒绝后的无签名 fallback 当作成功。

DRAM 控制器/PHY 作为平台适配候选：功能仿真可以使用模型，FPGA 使用匹配板卡和工具链的实现；是否可用开源实现、是否允许 vendor IP、实际面积和授权条件需另行核实。并没有已经选定或可直接流片的 DDR PHY。QSPI 用于启动镜像，不承担未经验证的高速 NPU 权重带宽承诺。

后续 digital twin 位于硬件之外，镜像这些软件可见接口和时序模型。模型替身与实际硬件替换使用不同验收标准。不会在框图上把“数字孪生”画成芯片中的一个硬件 block。

## 7. 还缺什么才算可以开工的规格

- 确定新工作负载组合、算子/精度、延迟和吞吐目标、片内/片外容量与带宽预算。
- 完成 CPU、AXI interconnect、Caliptra 和 memory IP 的固定版本编译/仿真探针。
- 冻结 AXI 宽度、ID/USER、在途事务、访问权限、地址/中断表，以及缓存/DMA 所有权合同。
- 完成 NPU 指令/描述符、bank 结构、数据格式、依赖、错误、复位/取消和精度规格。
- 独立制定完整 test plan，并把 add/modify/delete/replace 任务纳入协作实验。
- 补充低功耗、DFT/MBIST、调试、CDC/RDC 与物理平台视图；这些尚未在本图纸包中完成。

## 8. 来源与验证范围

- [Arm Ethos-U85 技术概述](https://documentation-service.arm.com/static/66617778d72aaf32efecd23f)：参考 NPU 功能块/系统连接图的表达和控制、DMA、内存的分层；本图不是其复刻或实现。
- [Caliptra 2.0 subsystem 集成规范](https://chipsalliance.github.io/caliptra-web/docs/2.0/subsystem/ss_integration_spec.html)：安全域组件、AXI 与存储器集成责任；实际 release 尚未选定。
- [Caliptra Core 集成规范](https://github.com/chipsalliance/caliptra-rtl/blob/main/docs/CaliptraIntegrationSpecification.md)：mailbox 访问身份和集成要求；main 文档是研究来源，不是项目 pin。
- [Accellera IP-XACT](https://www.accellera.org/downloads/standards/ip-xact)：IEEE 1685/XML 的标准范围。
- 本地数据来源：`workloads/tinystories/profile.py`；本次解析探针不是仿真 benchmark。

验证：图形源的节点/连接引用检查；SVG/XML 解析；渲染后逐图检查；解析探针成功完成。未运行 RTL/DV、formal、综合、FPGA、Caliptra 或物理签核，不能据此声称硬件可用。

GitHub 登录已在允许网络与钥匙串访问的环境核实为 WJiangH，账户查询成功；此前“凭据失效”判断由受限环境产生，已更正，无需重新登录。本地草稿目录由主仓库的 `.git/info/exclude` 忽略；没有推送或创建远端 PR。
