/* Boot ROM first-stage loader, footprint-estimate skeleton (issue #6).
 * Control flow per docs/spec/soc_1.md SOC1-08:
 *   (a) program the flash/PSRAM controller's clock-divider/mode CSR
 *   (b) issue a stream-descriptor read of the firmware image from a fixed
 *       flash offset into firmware SRAM (0x0001_0000), via the same
 *       weight-stream datapath (§4.2) with destination = SRAM
 *   (c) jump to 0x0001_0000 once transfer-complete status is observed
 *
 * Real values (flash clock-divider setting, fixed image offset, image
 * length) are firmware-build-time constants in the eventual M3 tree, not
 * spec content — placeholders here are marked below.
 */
#include "soc1_regmap.h"
#include "uart.h"

/* Placeholders — real values come from the flash layout / build system,
 * not from docs/spec/soc_1.md (out of scope for this top-level spec). */
#define BOOT_FLASH_MODE_50MHZ_SDR 0x00000001u
#define BOOT_FW_IMAGE_FLASH_OFFSET 0x00100000u
#define BOOT_FW_IMAGE_LEN_BYTES 8192u /* placeholder; real size is a linker/build symbol */

static void jump_to_firmware(void) __attribute__((noreturn));

int main(void)
{
    /* (a) program flash/PSRAM controller clock-divider/mode CSR */
    FLASH_CTRL_MODE(SOC1_FLASH_CTRL_BASE) = BOOT_FLASH_MODE_50MHZ_SDR;

    /* (b) arm a stream descriptor: flash offset -> firmware SRAM */
    FLASH_CTRL_SRC_OFF(SOC1_FLASH_CTRL_BASE) = BOOT_FW_IMAGE_FLASH_OFFSET;
    FLASH_CTRL_LEN(SOC1_FLASH_CTRL_BASE) = BOOT_FW_IMAGE_LEN_BYTES;
    FLASH_CTRL_CTRL(SOC1_FLASH_CTRL_BASE) =
        FLASH_CTRL_CTRL_START | FLASH_CTRL_CTRL_DST_SRAM;

    /* (c) poll transfer-complete status (SOC1-13/14) — no IRQs armed yet
     * this early in boot, so a busy-poll is the right primitive here. */
    for (;;) {
        uint32_t status = FLASH_CTRL_STATUS(SOC1_FLASH_CTRL_BASE);
        if (status & FLASH_CTRL_STATUS_ERROR) {
            uart_puts("BOOT: stream error\r\n");
            for (;;) {
                /* halt; nothing else this stage can do (SOC1-14) */
            }
        }
        if (status & FLASH_CTRL_STATUS_DONE) {
            break;
        }
    }

    jump_to_firmware();
}

static void jump_to_firmware(void)
{
    void (*fw_entry)(void) = (void (*)(void))SOC1_FW_SRAM_BASE;
    fw_entry();
    for (;;) {
        /* unreachable */
    }
}
