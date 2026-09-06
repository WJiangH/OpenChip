// llm_soc_top_deps.sv — NOT a module. Source-resolution shim for `make lint MOD=llm_soc_top`.
//
// Why it exists: the flow lint recipe (Makefile "Gate 1") runs
//   $(VERILATOR) --lint-only ... -Ihw/rtl -Ihw/rtl/$(MOD) ... hw/rtl/$(MOD)/*.sv
// and the tool resolves a missing module `x` as <incdir>/x.sv, but every delivered
// module lives at hw/rtl/<x>/<x>.sv, so -Ihw/rtl finds none of them and an
// integration top fails with %Error-MODMISSING. The recipe would need `-y` per
// module directory (or a filelist); flow/ and the Makefile are owned by the
// orchestrator, so this shim is the in-directory workaround (AGENTS.md
// "Flow-level defects ... work around inside your own directories and flag it").
// Reported as friction; see CONNECTIONS.md "Filelist" before reusing this tree.
//
// It contains no declarations of its own: it only textually includes the
// fourteen delivered module files, which -Ihw/rtl resolves as <mod>/<mod>.sv.
// hw/ip/picorv32/picorv32.v is resolved by the recipe's own -Ihw/ip/picorv32.
//
// ANY OTHER TOOL FLOW (yosys, DV elaboration, synthesis) MUST list the module
// files explicitly and MUST NOT read this file: doing both duplicates every
// module definition.
`include "cpu/cpu.sv"
`include "cpu_bridge/cpu_bridge.sv"
`include "fabric/fabric.sv"
`include "rom/rom.sv"
`include "sram/sram.sv"
`include "lite_bridge/lite_bridge.sv"
`include "sys/sys.sv"
`include "irq/irq.sv"
`include "uart/uart.sv"
`include "npu_csr/npu_csr.sv"
`include "npu_ctl/npu_ctl.sv"
`include "npu_dma/npu_dma.sv"
`include "npu_local/npu_local.sv"
`include "npu_dot/npu_dot.sv"
