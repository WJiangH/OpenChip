// rom_data.svh — include-path shim, part of the llm_soc_top_deps.sv workaround.
//
// hw/rtl/rom/rom.sv line 75 does `include "rom_data.svh"`. Verilator searches
// only the -I directories, the cwd and obj_dir (not the including file's own
// directory), and the lint recipe for MOD=llm_soc_top passes -Ihw/rtl and
// -Ihw/rtl/llm_soc_top but not -Ihw/rtl/rom. This file is found via the latter
// and forwards to the real ROM image, which -Ihw/rtl resolves. It adds no data
// of its own; hw/rtl/rom/rom_data.svh remains the single source of ROM bytes.
`include "rom/rom_data.svh"
