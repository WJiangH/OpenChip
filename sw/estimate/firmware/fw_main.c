/* Runtime firmware main loop, footprint-estimate skeleton (issue #6).
 * Control flow per docs/spec/soc_1.md SOC1-10 (§4.2 descriptor model) and
 * §4.4 (IRQ dispatch), shaped by the per-token GEMV inventory in
 * workloads/tinystories/profile.md §2 (stories15M, dim 288, hidden 768,
 * 6 layers, vocab 32000): per layer, 7 weight-stream descriptors
 * (wq/wk/wv/wo/w1/w3/w2); per token, one closing lm_head descriptor
 * (SOC1-15). Numeric GEMV/argmax/requantise bodies are out of scope for a
 * top-level-spec-driven skeleton (deferred to the future npu.md) — stubbed.
 */
#include <stdint.h>
#include "soc1_regmap.h"
#include "uart.h"
#include "irq.h"

#define N_LAYERS 6
#define DIM 288
#define HIDDEN_DIM 768
#define VOCAB 32000
#define MAX_TOKENS 16 /* placeholder decode-session length for this estimate */

/* Per-layer weight-stream op inventory (profile.md §2 table), K x N int8. */
typedef struct {
    uint32_t k;
    uint32_t n;
} gemv_op_t;

static const gemv_op_t k_layer_ops[] = {
    {DIM, DIM},        /* wq */
    {DIM, DIM},        /* wk */
    {DIM, DIM},        /* wv */
    {DIM, DIM},        /* wo */
    {DIM, HIDDEN_DIM}, /* w1 */
    {DIM, HIDDEN_DIM}, /* w3 */
    {HIDDEN_DIM, DIM}, /* w2 */
};
#define N_LAYER_OPS (sizeof(k_layer_ops) / sizeof(k_layer_ops[0]))

static const gemv_op_t k_lm_head_op = {DIM, VOCAB}; /* SOC1-15 */

/* Placeholder flash weight layout: a flat running offset. The real layout
 * (per-tensor base addresses in flash address space) is a build-time
 * artifact of the model exporter, not spec content. */
static uint32_t g_flash_cursor;

static void dispatch_weight_stream(uint32_t byte_len)
{
    FLASH_CTRL_SRC_OFF(SOC1_FLASH_CTRL_BASE) = g_flash_cursor;
    FLASH_CTRL_LEN(SOC1_FLASH_CTRL_BASE) = byte_len;
    FLASH_CTRL_CTRL(SOC1_FLASH_CTRL_BASE) =
        FLASH_CTRL_CTRL_START | FLASH_CTRL_CTRL_DST_NPU;
    g_flash_cursor += byte_len;

    g_stream_done = 0;
    g_stream_error = 0;
    irq_wait_stream_done();
}

static void dispatch_npu_gemv(uint32_t k, uint32_t n)
{
    NPU_M(SOC1_NPU_BASE) = 1; /* decode is always M=1, profile.md §2 */
    NPU_K(SOC1_NPU_BASE) = k;
    NPU_N(SOC1_NPU_BASE) = n;
    NPU_CTRL(SOC1_NPU_BASE) = NPU_CTRL_START;

    g_npu_done = 0;
    irq_wait_npu_done();
}

/* Result-path consumption (argmax over VOCAB logits) is Q-SOC1-07, deferred
 * to the future npu.md — stub returns a placeholder token id. */
static uint32_t pick_next_token(void)
{
    return NPU_STATUS(SOC1_NPU_BASE) & 0xFFu;
}

static void run_token(void)
{
    for (uint32_t layer = 0; layer < N_LAYERS; layer++) {
        for (uint32_t op = 0; op < N_LAYER_OPS; op++) {
            uint32_t k = k_layer_ops[op].k;
            uint32_t n = k_layer_ops[op].n;
            dispatch_weight_stream(k * n);
            dispatch_npu_gemv(k, n);
        }
    }

    /* lm_head: ordinary descriptor, longer length (SOC1-15) */
    dispatch_weight_stream(k_lm_head_op.k * k_lm_head_op.n);
    dispatch_npu_gemv(k_lm_head_op.k, k_lm_head_op.n);

    uint32_t tok = pick_next_token();
    uart_put_u32_hex(tok);
    uart_puts(" ");
}

int main(void)
{
    for (uint32_t t = 0; t < MAX_TOKENS; t++) {
        run_token();
    }
    uart_puts("\r\nPASS\r\n");
    for (;;) {
        /* end of session; real firmware would idle/wait for next prompt */
    }
}
