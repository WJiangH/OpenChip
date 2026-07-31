#ifndef ESTIMATE_UART_H
#define ESTIMATE_UART_H

void uart_putc(char c);
void uart_puts(const char *s);
void uart_put_u32_hex(unsigned int v);

#endif
