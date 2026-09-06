/* sw/common/mmio.h — aligned 32-bit MMIO access helpers.
 *
 * SYS-08: "All CSR bus transactions shall be aligned 32-bit single transfers
 * with WSTRB=0xf on writes... Software must issue aligned word CSR
 * loads/stores; the native CPU port does not expose original read size/byte
 * offset, so hardware cannot distinguish a CPU LB/LH from LW of the same
 * word." A plain `volatile uint32_t` load/store from a 4-aligned address
 * compiles to exactly one aligned LW/SW, satisfying that ABI requirement
 * exactly (no sub-word access is ever emitted for these helpers).
 *
 * SYS-07: any non-OK AXI response to a CPU request latches FATAL and holds
 * the CPU core in local reset permanently (cpu_local_rst_n never releases
 * again short of full system reset) — so every offset/address passed here
 * must already be known-good per the register map; there is no software
 * recovery path from a CSR-layer protocol mistake.
 */
#ifndef OPENCHIP_SW_COMMON_MMIO_H
#define OPENCHIP_SW_COMMON_MMIO_H

#include <stdint.h>

static inline uint32_t mmio_read32(uint32_t addr) {
    return *(volatile uint32_t *)addr;
}

static inline void mmio_write32(uint32_t addr, uint32_t val) {
    *(volatile uint32_t *)addr = val;
}

#endif /* OPENCHIP_SW_COMMON_MMIO_H */
