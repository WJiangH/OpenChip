/* IRQ dispatch, footprint-estimate skeleton (issue #6).
 *
 * docs/spec/soc_1.md §4.4: PicoRV32's native irq[31:0] input does the actual
 * latch/mask (maskirq/waitirq/retirq custom instructions); the CSR block at
 * SOC1_IRQ_BASE is only a software-visible pending mirror. The real trap
 * entry/exit sequence (picorv32's getq/setq/retirq custom-instruction ABI,
 * per the upstream README already cited in the spec) is not re-derived here
 * — Q-SOC1-06 leaves the core's reset/IRQ interface to be confirmed at RTL
 * intake, so this skeleton only sizes the C-level dispatch body below, not
 * the trap glue that would call it.
 */
#include "irq.h"
#include "soc1_regmap.h"

volatile uint32_t g_stream_done;
volatile uint32_t g_stream_error;
volatile uint32_t g_npu_done;
volatile uint32_t g_uart_rx_ready;

void irq_dispatch(uint32_t pending)
{
    if (pending & (1u << IRQ_LINE_UART_RX)) {
        g_uart_rx_ready = 1;
    }
    if (pending & (1u << IRQ_LINE_STREAM_DONE)) {
        g_stream_done = 1;
    }
    if (pending & (1u << IRQ_LINE_STREAM_ERROR)) {
        g_stream_error = 1;
    }
    if (pending & (1u << IRQ_LINE_NPU_DONE)) {
        /* SOC1-20: NPU compute-done is distinct from stream-done — the
         * accumulate/requantise tail can still be running after the last
         * weight byte arrives. */
        g_npu_done = 1;
    }
}

void irq_wait_stream_done(void)
{
    while (!g_stream_done && !g_stream_error) {
        /* busy-wait; real firmware would waitirq here (§4.4) */
    }
}

void irq_wait_npu_done(void)
{
    while (!g_npu_done) {
        /* busy-wait; real firmware would waitirq here (§4.4) */
    }
}
