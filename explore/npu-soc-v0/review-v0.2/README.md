# OpenChip 传统架构评审交付包 - Rev 0.2

状态：本地候选稿，未冻结、未发布给 RTL/DV 实现。日期：2026-09-05。

本 Rev 0.2 提供 Visio 可编辑图纸、PDF 评审件与接口连接登记册。用户后续确认 draw.io 同样可以使用；不强制后续文档使用 Visio。最新产品方向见 [LLM 需求与架构取舍草案](../../llm-target-v0/README.md)，当前图纸尚未按该需求冻结。

## 本次交付

- [Visio 主图纸](openchip-architecture-review-v0.2.vsdx)：A3 横向，四张图，带图号、版本、日期和状态；55 个连接图形，110 条端点附着记录，独立可编辑方框、文字和连接线。
- [PDF 评审版](openchip-architecture-review-v0.2.pdf)：从 VSDX 通过 LibreOffice 实际导入导出，用于图面审阅。
- [接口连接登记册](interface-register.md)：对应图中 SOC/NPU/BOOT/CR 编号，区分接口、接口束与流程；登记端点、位宽状态及待冻结字段。
- [机器可读登记数据](interface-register.json)：本地工作数据，非 IP-XACT，也不是 RTL netlist。

## 后续按同一交付习惯补齐

| 交付物 | 作用 | 当前状态 |
|---|---|---|
| SoC architecture specification | 工作负载、功能、预算、系统行为与边界 | [候选说明](../README.md)，未冻结 |
| Block diagram / microarchitecture | 层次、功能块和接口连接 | 本次四页图纸 |
| Interface control document (ICD) | 每个真实端口的协议、位宽、时序、错误和责任 | 登记册初稿；不能视为完整 ICD |
| Address / interrupt / register maps | 软件与硬件接口 | 尚未按新架构冻结 |
| Clock / reset / power / DFT views | 时钟复位、低功耗与测试结构 | 时钟复位候选视图；power/DFT 待设计 |
| Verification plan / coverage matrix | 每项要求的独立验证义务与状态 | 待 verification architect 独立交付 |
| Change order / review record | 增改删替换与版本影响追踪 | 流程草案已定义；尚无实施发布 |

统一原则：图纸版本与规格/ICD/验证计划关联；未定字段明确标为 TBD，并在架构冻结前裁决。不能因为文件变成 VSDX，就将候选草图视为完整工程规格。

## 验证与限制

本次验证了：VSDX ZIP/XML 可解析、四页、55 个连接图形、110 条端点引用；LibreOffice 26.2.2.2 实际导入为 Draw 文档并导出四页 A3 PDF；PDF 渲染后逐页检查。

本机没有对 Microsoft Visio 原生程序的打开、拖动和自动重布线行为做实机验证。不能把 LibreOffice 导入成功等同于全部 Visio 编辑行为已经验证。

没有 RTL/DV、formal、综合或 FPGA 验证；芯片架构仍是候选。图中的主从角色和安全接口束拆分要求见登记册；BOOT-* 表达启动流程，不是可直接接线的信号。

没有推送、提交远端或创建 PR。所有文件位于主仓库忽略的 `.local-designs/` 内。

Friction:
- OPC relationship 类型、主文档 MIME 和 metadata 默认命名空间影响实际导入；最终已通过 LibreOffice 导入，Microsoft Visio 原生交互未验证。

Skill candidates:
- chief-architect/references/spec-authoring-patterns.md — 对传统架构包要求图纸编号、接口登记与冻结状态联动。
