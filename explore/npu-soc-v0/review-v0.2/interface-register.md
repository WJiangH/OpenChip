# OpenChip 接口连接登记册 - Rev 0.2

状态：架构候选；本登记册尚未完成接口控制文件（ICD）的冻结条件。
编号对应 Visio 图中的连接与 Shape Data。BOOT-* 是流程步骤，不是硬件端口；其余也可能表示接口束。

## AXI 端点角色裁决（候选）

- CPU、NPU DMA 是系统互连的 initiator；SRAM、外存控制器、ROM、外设桥和 NPU CSR 是 target。
- CPU 经适配进入 AXI4；NPU CSR 前的 AXI4-to-Lite 适配必须成为独立的可验证交付物。
- 安全域 SOC-02 图线是接口束：安全域 initiator 到系统 target，以及系统获授权 initiator 到安全域 mailbox target；下发规格前必须拆成两套接口。
- M/S 角色不由双向箭头决定；箭头包含请求和返回流量。
- 图中信号名称是候选端点，不是从现有 RTL 提取的端口，不能据此宣称连线已正确实现。

## 逐连接清单

| ID | 图/类型 | 来源 | 目标 | 接口或事件 | 位宽状态 |
|---|---|---|---|---|---|
| SOC-01 | logical interface | `cpu` | `fabric` | AXI4-Lite + adapter | D=32 candidate; address/ID/adaptation TBD |
| SOC-02 | logical interface | `security` | `fabric` | AXI4 + trusted USER | TBD - no implementation release |
| SOC-03 | logical interface | `security` | `recovery` | I3C | TBD - no implementation release |
| SOC-04 | logical interface | `crm` | `fabric` | clk / rst | TBD - no implementation release |
| SOC-05 | logical interface | `fabric` | `rom` | AXI | TBD - no implementation release |
| SOC-06 | logical interface | `fabric` | `sram` | AXI4 | TBD - no implementation release |
| SOC-07 | logical interface | `fabric` | `memory` | AXI4 | TBD - no implementation release |
| SOC-08 | logical interface | `memory` | `dram` | Physical memory interface | TBD - no implementation release |
| SOC-09 | logical interface | `fabric` | `apb` | AXI4 | TBD - no implementation release |
| SOC-10 | logical interface | `apb` | `periph` | APB | TBD - no implementation release |
| SOC-11 | logical interface | `fabric` | `npu_csr` | AXI4 to Lite | TBD - no implementation release |
| SOC-12 | logical interface | `npu_dma` | `fabric` | AXI4 bursts | TBD - no implementation release |
| SOC-13 | logical interface | `npu_csr` | `npu_dma` | dispatch | TBD - no implementation release |
| SOC-14 | logical interface | `npu_dma` | `npu_core` | local data | TBD - no implementation release |
| SOC-15 | logical interface | `npu` | `irq` | done / fault | event bundle; source count/polarity TBD |
| SOC-16 | logical interface | `periph` | `irq` | IRQ | event bundle; source count/polarity TBD |
| SOC-17 | logical interface | `irq` | `cpu` | CPU IRQ | event bundle; source count/polarity TBD |
| NPU-01 | logical interface | `host` | `queue` | AXI4-Lite | TBD - no implementation release |
| NPU-02 | logical interface | `queue` | `ctl` | commands | TBD - no implementation release |
| NPU-03 | logical interface | `queue` | `dma` | DMA descriptors | TBD - no implementation release |
| NPU-04 | logical interface | `ctl` | `local` | ownership | TBD - no implementation release |
| NPU-05 | logical interface | `ctl` | `matrix` | issue / done | TBD - no implementation release |
| NPU-06 | logical interface | `ctl` | `vector` | issue / done | TBD - no implementation release |
| NPU-07 | logical interface | `axi` | `dma` | AXI4 | TBD - no implementation release |
| NPU-08 | logical interface | `dma` | `local` | local fabric | TBD - no implementation release |
| NPU-09 | logical interface | `local` | `matrix` | W + X | TBD - no implementation release |
| NPU-10 | logical interface | `local` | `vector` | vectors | TBD - no implementation release |
| NPU-11 | logical interface | `matrix` | `acc` | partial sums | TBD - no implementation release |
| NPU-12 | logical interface | `acc` | `vector` | postprocess | TBD - no implementation release |
| NPU-13 | logical interface | `acc` | `out` | results | TBD - no implementation release |
| NPU-14 | logical interface | `local` | `out` | vector results | TBD - no implementation release |
| NPU-15 | logical interface | `out` | `dma` | writeback stream | TBD - no implementation release |
| NPU-16 | logical interface | `out` | `irq` | status | TBD - no implementation release |
| BOOT-01 | FLOW (not hardware port) | `por` | `seq` | stable / reset | TBD - no implementation release |
| BOOT-02 | FLOW (not hardware port) | `seq` | `rot` | ordered bring-up | TBD - no implementation release |
| BOOT-03 | FLOW (not hardware port) | `source` | `stage` | image data | TBD - no implementation release |
| BOOT-04 | FLOW (not hardware port) | `seq` | `stage` | ROM load control | TBD - no implementation release |
| BOOT-05 | FLOW (not hardware port) | `rot` | `verify` | security services | TBD - no implementation release |
| BOOT-06 | FLOW (not hardware port) | `stage` | `verify` | image / manifest | TBD - no implementation release |
| BOOT-07 | FLOW (not hardware port) | `verify` | `permit` | authorized | TBD - no implementation release |
| BOOT-08 | FLOW (not hardware port) | `verify` | `fail` | rejected | TBD - no implementation release |
| BOOT-09 | FLOW (not hardware port) | `permit` | `run` | release | TBD - no implementation release |
| BOOT-10 | FLOW (not hardware port) | `run` | `fault` | fault / watchdog | TBD - no implementation release |
| BOOT-11 | FLOW (not hardware port) | `fault` | `fail` | contain / recover | TBD - no implementation release |
| CR-01 | CLOCK/RESET bundle | `ref` | `clk` | reference clock | TBD - no implementation release |
| CR-02 | CLOCK/RESET bundle | `ref` | `rst` | external reset | TBD - no implementation release |
| CR-03 | CLOCK/RESET bundle | `clk` | `sec` | soc_clk | 1-bit clock; frequency TBD |
| CR-04 | CLOCK/RESET bundle | `clk` | `cpu` | soc_clk | 1-bit clock; frequency TBD |
| CR-05 | CLOCK/RESET bundle | `clk` | `npu` | soc_clk | 1-bit clock; frequency TBD |
| CR-06 | CLOCK/RESET bundle | `clk` | `mem` | soc_clk | 1-bit clock; frequency TBD |
| CR-07 | CLOCK/RESET bundle | `rst` | `sec` | reset / pwrgood | TBD - no implementation release |
| CR-08 | CLOCK/RESET bundle | `rst` | `cpu` | cpu_rst | TBD - no implementation release |
| CR-09 | CLOCK/RESET bundle | `rst` | `npu` | system resets | TBD - no implementation release |
| CR-10 | CLOCK/RESET bundle | `rst` | `mem` | memory reset | TBD - no implementation release |
| CR-11 | CLOCK/RESET bundle | `sec` | `rst` | boot authorization / escalation | TBD - no implementation release |

## 下发 RTL/DV 前的必填字段

- 单独的端口名、方向、协议版本、数据/地址/ID/USER 宽度及转换。
- burst、在途事务、排序、对齐、字节使能、错误、超时、取消与复位中事务处理。
- 地址窗口、访问身份、默认权限与 DMA 可访问范围。
- 时钟频率/来源、复位极性/同步性/顺序、CDC/RDC、必要电源隔离和 retention。
- block owner、对应规格版本、独立 DV 测试/属性 ID、变更影响列表。
- 未定项由架构师裁决，不允许实现 agent 自行补齐接口语义。
