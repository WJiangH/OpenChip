#ifndef ESTIMATE_IRQ_H
#define ESTIMATE_IRQ_H

#include <stdint.h>

extern volatile uint32_t g_stream_done;
extern volatile uint32_t g_stream_error;
extern volatile uint32_t g_npu_done;
extern volatile uint32_t g_uart_rx_ready;

void irq_dispatch(uint32_t pending);
void irq_wait_stream_done(void);
void irq_wait_npu_done(void);

#endif
