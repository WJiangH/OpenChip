/* sw/b1/npu.c — see npu.h. */
#include "npu.h"
#include "regmap.h"
#include "mmio.h"

void npu_clear(void) {
    mmio_write32(NPU_CSR_CLEAR_ADDR, 1u);
}

void npu_program(const npu_descriptor_t *d) {
    mmio_write32(NPU_CSR_OPCODE_ADDR, d->opcode);
    mmio_write32(NPU_CSR_X_BASE_ADDR, d->x_base);
    mmio_write32(NPU_CSR_W_BASE_ADDR, d->w_base);
    mmio_write32(NPU_CSR_Y_BASE_ADDR, d->y_base);
    mmio_write32(NPU_CSR_K_ADDR, d->k);
    mmio_write32(NPU_CSR_N_ADDR, d->n);
    mmio_write32(NPU_CSR_GROUP_ADDR, d->group);
    mmio_write32(NPU_CSR_W_STRIDE_ADDR, d->w_stride);
    mmio_write32(NPU_CSR_TAG_ADDR, d->tag);
}

void npu_submit(void) {
    mmio_write32(NPU_CSR_SUBMIT_ADDR, 1u);
}

uint32_t npu_status(void) {
    return mmio_read32(NPU_CSR_STATUS_ADDR);
}

uint32_t npu_poll_until_terminal(void) {
    uint32_t st;
    do {
        st = npu_status();
    } while ((st & NPU_CSR_STATUS_BUSY_MASK) != 0u);
    return st;
}

uint32_t npu_completed_tag(void) {
    return mmio_read32(NPU_CSR_COMPLETED_TAG_ADDR);
}

uint32_t npu_error_code(void) {
    return mmio_read32(NPU_CSR_ERROR_CODE_ADDR);
}
