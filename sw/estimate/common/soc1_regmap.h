/* Register map for the footprint-estimate skeleton (issue #6, Q-SOC1-03).
 *
 * Block base addresses are frozen by docs/spec/soc_1.md §3.2 (SOC1-05):
 * sixteen 64 KB windows selected by wb_adr[19:16].
 *
 * Per-block offsets below (FLASH_CTRL_*, NPU_*, UART_*, IRQ_*) are NOT part
 * of soc_1.md — npu.md/flash_ctrl.md/uart.md/irqc.md are unwritten
 * (Q-SOC1-04). They are this estimate's own placeholder layout, chosen only
 * to give the skeleton real 32-bit CSR loads/stores to size against.
 */
#ifndef SOC1_REGMAP_H
#define SOC1_REGMAP_H

#include <stdint.h>

#define SOC1_BOOT_ROM_BASE   0x00000000u  /* §3.2, RO */
#define SOC1_FW_SRAM_BASE    0x00010000u  /* §3.2, RW code+data */
#define SOC1_NPU_BASE        0x00020000u  /* §3.2, CSR/descriptor only */
#define SOC1_FLASH_CTRL_BASE 0x00030000u  /* §3.2, CSR only */
#define SOC1_UART_BASE       0x00040000u  /* §3.2 */
#define SOC1_IRQ_BASE        0x00050000u  /* §3.2, status/mask mirror */
#define SOC1_GPIO_BASE       0x00060000u  /* §3.2 */

#define SOC1_REG32(base, off) (*(volatile uint32_t *)((base) + (off)))

/* --- Flash/PSRAM controller CSR (placeholder offsets, §4.2/§4.3) --------- */
#define FLASH_CTRL_MODE(b)    SOC1_REG32((b), 0x00) /* clk-div/mode, SOC1-08a */
#define FLASH_CTRL_SRC_OFF(b) SOC1_REG32((b), 0x04) /* descriptor: flash byte offset */
#define FLASH_CTRL_LEN(b)     SOC1_REG32((b), 0x08) /* descriptor: length in bytes */
#define FLASH_CTRL_CTRL(b)    SOC1_REG32((b), 0x0C) /* bit0 START, bit1 DST_SEL (SOC1-12) */
#define FLASH_CTRL_STATUS(b)  SOC1_REG32((b), 0x10) /* bit0 BUSY, bit1 DONE, bit2 ERROR */

#define FLASH_CTRL_CTRL_START    (1u << 0)
#define FLASH_CTRL_CTRL_DST_NPU  (0u << 1)  /* SOC1-12 dest mode bit */
#define FLASH_CTRL_CTRL_DST_SRAM (1u << 1)
#define FLASH_CTRL_STATUS_BUSY   (1u << 0)
#define FLASH_CTRL_STATUS_DONE   (1u << 1)  /* SOC1-13 */
#define FLASH_CTRL_STATUS_ERROR  (1u << 2)  /* SOC1-14 */

/* --- NPU CSR/descriptor block (placeholder offsets, SOC1-10) ------------- */
#define NPU_CTRL(b)   SOC1_REG32((b), 0x00) /* bit0 START (dispatch) */
#define NPU_STATUS(b) SOC1_REG32((b), 0x04) /* bit0 BUSY, bit1 DONE */
#define NPU_M(b)      SOC1_REG32((b), 0x08) /* GEMV dims, per descriptor */
#define NPU_K(b)      SOC1_REG32((b), 0x0C)
#define NPU_N(b)      SOC1_REG32((b), 0x10)

#define NPU_CTRL_START  (1u << 0)
#define NPU_STATUS_BUSY (1u << 0)
#define NPU_STATUS_DONE (1u << 1)

/* --- UART (PicoSoC divisor/data precedent, §3.1) ------------------------- */
#define UART_DIV(b)  SOC1_REG32((b), 0x00)
#define UART_DATA(b) SOC1_REG32((b), 0x04) /* write: TX byte; read: RX byte or -1 if empty */

/* --- IRQ status/mask mirror (§4.4) --------------------------------------- */
#define IRQ_PENDING(b) SOC1_REG32((b), 0x00) /* RO mirror of irq[31:0] */
#define IRQ_MASK(b)    SOC1_REG32((b), 0x04) /* RW, software convenience only */

#define IRQ_LINE_UART_RX    3  /* §4.4 table */
#define IRQ_LINE_STREAM_DONE  4
#define IRQ_LINE_STREAM_ERROR 5
#define IRQ_LINE_NPU_DONE     6

#endif /* SOC1_REGMAP_H */
